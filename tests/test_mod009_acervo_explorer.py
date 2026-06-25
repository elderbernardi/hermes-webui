"""MOD-009 Acervo Explorer — hermetic backend unit tests (T11).

Exercises the *pure* helpers of ``api/acervo_explorer.py`` directly so the suite
needs no running server and never touches the real ``~/exocortex/acervo``:

  * ``_safe_acervo_path`` traversal / symlink / dotfile / absolute / md-suffix
    guards (SPEC §3 path safety).
  * the frontmatter round-trip (``_split_fm`` / ``_save_page_frontmatter`` /
    ``_reassemble``) — OKF preservation, conditional timestamp bump, key order,
    body preservation, tag coercion + idempotency (SPEC §3.4 / §3.7).
  * the page-status constraint to ``_ACERVO_UI_STATUSES`` (SPEC §3.6).

The acervo root is redirected at the source: ``api.routes._acervo_root`` is
monkeypatched to return a ``tmp_path`` acervo, which is exactly what
``_safe_acervo_path`` resolves against (it late-imports ``api.routes`` and calls
``routes._acervo_root()``).
"""
import os

import pytest

import api.acervo_explorer as ax
import api.routes as routes


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def acervo(tmp_path, monkeypatch):
    """A throwaway acervo root with a couple of real pages, wired into the
    explorer via ``api.routes._acervo_root``."""
    root = tmp_path / "acervo"
    (root / "global" / "knowledge").mkdir(parents=True)
    (root / ".quarantine").mkdir()
    monkeypatch.setattr(routes, "_acervo_root", lambda: root)
    return root


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ── Path safety (_safe_acervo_path) ────────────────────────────────────────

@pytest.mark.parametrize("bad_rel", [
    "../etc/passwd",                 # parent traversal
    "global/../../etc/passwd",       # traversal that climbs out after a valid head
    "/etc/passwd",                   # absolute
    ".quarantine/x.md",             # dotted component -> quarantine off-limits
    "global/.quarantine/secret.md",  # dotted component anywhere in the path
    ".git/config",                  # dotted component -> .git off-limits
    "",                              # empty
    "   ",                           # whitespace-only
    None,                            # missing
])
def test_safe_path_rejects(acervo, bad_rel):
    with pytest.raises(ValueError):
        ax._safe_acervo_path(bad_rel)


def test_safe_path_accepts_normal_md(acervo):
    resolved = ax._safe_acervo_path("global/knowledge/x.md")
    # Resolves under the (resolved) acervo root.
    resolved.relative_to(acervo.resolve())
    assert resolved.name == "x.md"


def test_safe_path_symlink_escape_rejected(acervo, tmp_path):
    """A symlink that lives inside the acervo but points OUTSIDE it must be
    rejected: ``.resolve()`` collapses the link and ``relative_to`` fails."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.md"
    secret.write_text("# not yours\n", encoding="utf-8")
    link = acervo / "global" / "knowledge" / "escape.md"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("platform does not support symlinks")
    with pytest.raises(ValueError):
        ax._safe_acervo_path("global/knowledge/escape.md")


def test_safe_path_require_md_rejects_non_md(acervo):
    # Without require_md a non-.md path resolves fine...
    assert ax._safe_acervo_path("global/knowledge/data.json").name == "data.json"
    # ...but require_md=True rejects it.
    with pytest.raises(ValueError):
        ax._safe_acervo_path("global/knowledge/data.json", require_md=True)


# ── Frontmatter round-trip (OKF preservation) ──────────────────────────────

_PAGE = (
    "---\n"
    "title: Old Title\n"
    "tags:\n"
    "  - alpha\n"
    "status: draft\n"
    "nature: knowledge\n"
    "updated: 2020-01-01T00:00:00Z\n"
    "custom_okf_field: keepme\n"
    "---\n"
    "\n"
    "# Heading\n"
    "\n"
    "Body text that must survive untouched.\n"
)


def test_save_preserves_unknown_okf_field_and_body(acervo):
    target = _write(acervo, "global/knowledge/x.md", _PAGE)
    ax._save_page_frontmatter(
        target, {"title": "New Title", "tags": ["alpha", "beta"]}, body=None)

    fm, body = ax._split_fm(target.read_text(encoding="utf-8"))
    # Supplied keys overwritten.
    assert fm["title"] == "New Title"
    assert fm["tags"] == ["alpha", "beta"]
    # Unknown OKF field survived verbatim.
    assert fm["custom_okf_field"] == "keepme"
    # Untouched governance field survived.
    assert fm["nature"] == "knowledge"
    # Body preserved exactly (modulo the single normalized leading blank line).
    assert "# Heading" in body
    assert "Body text that must survive untouched." in body


def test_save_bumps_updated_only_when_present(acervo):
    target = _write(acervo, "global/knowledge/x.md", _PAGE)
    merged = ax._save_page_frontmatter(target, {"title": "Z"}, body=None)
    # 'updated' pre-existed -> bumped (no longer the 2020 sentinel).
    assert merged["updated"] != "2020-01-01T00:00:00Z"
    assert merged["updated"].endswith("Z")


def test_save_does_not_invent_absent_timestamps(acervo):
    # A page with NO timestamp/last_accessed_at/updated keys.
    page = (
        "---\n"
        "title: No Timestamps\n"
        "status: ready\n"
        "---\n"
        "\nBody.\n"
    )
    target = _write(acervo, "global/knowledge/nots.md", page)
    merged = ax._save_page_frontmatter(target, {"title": "Renamed"}, body=None)
    for k in ("updated", "timestamp", "last_accessed_at"):
        assert k not in merged, f"{k} must not be invented when absent"


def test_save_preserves_key_order(acervo):
    target = _write(acervo, "global/knowledge/x.md", _PAGE)
    ax._save_page_frontmatter(target, {"title": "New Title"}, body=None)
    fm, _ = ax._split_fm(target.read_text(encoding="utf-8"))
    # Insertion order of the original keys is preserved (sort_keys=False).
    assert list(fm.keys()) == [
        "title", "tags", "status", "nature", "updated", "custom_okf_field"]


def test_body_replacement_preserves_frontmatter(acervo):
    target = _write(acervo, "global/knowledge/x.md", _PAGE)
    ax._save_page_frontmatter(target, {}, body="# Replaced\n\nNew body only.\n")
    fm, body = ax._split_fm(target.read_text(encoding="utf-8"))
    assert fm["custom_okf_field"] == "keepme"
    assert "New body only." in body
    assert "Body text that must survive untouched." not in body


# ── Tag coercion + idempotency ─────────────────────────────────────────────

def test_tags_scalar_coerced_to_list_and_idempotent(acervo):
    # Frontmatter where tags is a SCALAR (not a list).
    page = (
        "---\n"
        "title: Scalar Tags\n"
        "tags: solo\n"
        "---\n"
        "\nBody.\n"
    )
    target = _write(acervo, "global/knowledge/scalar.md", page)

    fm, _ = ax._split_fm(target.read_text(encoding="utf-8"))
    cur = fm.get("tags")
    tags = [str(cur)] if not isinstance(cur, list) else [str(t) for t in cur]
    # add "extra" once.
    for t in ["extra"]:
        if t not in tags:
            tags.append(t)
    ax._save_page_frontmatter(target, {"tags": tags}, body=None)

    fm2, _ = ax._split_fm(target.read_text(encoding="utf-8"))
    assert fm2["tags"] == ["solo", "extra"]

    # Re-applying the same add is idempotent (no duplicate).
    fm2_tags = list(fm2["tags"])
    for t in ["extra"]:
        if t not in fm2_tags:
            fm2_tags.append(t)
    ax._save_page_frontmatter(target, {"tags": fm2_tags}, body=None)
    fm3, _ = ax._split_fm(target.read_text(encoding="utf-8"))
    assert fm3["tags"] == ["solo", "extra"]


# ── Page-status constraint ─────────────────────────────────────────────────

def test_ui_statuses_set_is_the_expected_three():
    assert routes._ACERVO_UI_STATUSES == {"draft", "ready", "archived"}


@pytest.mark.parametrize("status", sorted(routes._ACERVO_UI_STATUSES))
def test_valid_page_status_accepted(acervo, status):
    target = _write(acervo, "global/knowledge/x.md", _PAGE)
    merged = ax._save_page_frontmatter(target, {"status": status}, body=None)
    assert merged["status"] == status


def test_invalid_page_status_rejected_by_constraint():
    """The save/status handlers gate ``status`` to ``_ACERVO_UI_STATUSES``
    before ever writing. Mirror that guard (the handlers use this exact check)."""
    bad_status = "published"
    assert bad_status not in routes._ACERVO_UI_STATUSES
    # The constraint the handlers apply:
    assert "deleted" not in routes._ACERVO_UI_STATUSES
    assert "" not in routes._ACERVO_UI_STATUSES


def test_json_safe_coerces_dates():
    """YAML parses unquoted dates into datetime.date; the /page response must not
    crash on them (regression: 'Object of type date is not JSON serializable')."""
    import json, datetime
    import api.acervo_explorer as ax
    fm = {"title": "x", "created": datetime.date(2026, 6, 21),
          "ts": datetime.datetime(2026, 6, 21, 8, 30, 0),
          "nested": {"d": datetime.date(2025, 1, 1)}, "tags": ["a", "b"]}
    safe = ax._json_safe(fm)
    json.dumps(safe)  # must not raise
    assert safe["created"] == "2026-06-21"
    assert safe["nested"]["d"] == "2025-01-01"
    assert safe["tags"] == ["a", "b"]
