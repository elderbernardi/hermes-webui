"""MOD-010 Acervo Studio — hermetic backend unit tests (Phase 0).

Tests the pure tree helpers added to api/acervo_explorer.py for the new
`micro` and `inbox` scopes, mirroring the MOD-009 hermetic style:
api.routes._acervo_root is monkeypatched onto a tmp_path acervo.
"""
import pytest

import api.acervo_explorer as ax
import api.routes as routes


@pytest.fixture
def acervo(tmp_path, monkeypatch):
    root = tmp_path / "acervo"
    (root / "micro" / "comercial" / "knowledge").mkdir(parents=True)
    (root / "micro" / "comercial" / "decisions").mkdir(parents=True)
    (root / "micro" / "_template" / "knowledge").mkdir(parents=True)  # underscore -> skipped
    (root / "_inbox" / "incoming").mkdir(parents=True)
    monkeypatch.setattr(routes, "_acervo_root", lambda: root)
    return root


def _w(root, rel, text="---\ntitle: T\n---\n\nbody\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_micro_nodes_lists_microverses_with_counts(acervo):
    _w(acervo, "micro/comercial/knowledge/precificacao.md")
    _w(acervo, "micro/comercial/decisions/alcada.md")
    nodes = ax._micro_nodes(routes, acervo, "", 1)
    slugs = {n["slug"]: n for n in nodes if n["type"] == "microverse"}
    assert "comercial" in slugs
    assert "_template" not in slugs          # underscore dirs skipped
    assert slugs["comercial"]["count"] == 2  # 2 pages across natures


def test_micro_nodes_lists_pages_for_a_slug(acervo):
    _w(acervo, "micro/comercial/knowledge/precificacao.md",
       "---\ntitle: Precificação\nstatus: ready\n---\n\nx\n")
    nodes = ax._micro_nodes(routes, acervo, "comercial", 2)
    natures = [n for n in nodes if n["type"] == "nature"]
    pages = [n for n in nodes if n["type"] == "page"]
    assert any(n["name"] == "knowledge" for n in natures)
    assert any(p["title"] == "Precificação" and p["status"] == "ready" for p in pages)


import json


def test_inbox_nodes_lists_incoming_envelopes(acervo):
    env = acervo / "_inbox" / "incoming" / "int_20260616_open-notebook"
    (env / "original").mkdir(parents=True)
    (env / "manifest.json").write_text(
        json.dumps({"title": "Open Notebook", "status": "received"}),
        encoding="utf-8")
    (acervo / "_inbox" / "incoming" / "int_20260701_bare").mkdir(parents=True)

    nodes = ax._inbox_nodes(routes, acervo)
    by_id = {n["id"]: n for n in nodes}
    assert by_id["int_20260616_open-notebook"]["title"] == "Open Notebook"
    assert by_id["int_20260616_open-notebook"]["status"] == "received"
    # Bare envelope with no manifest still lists, with a defaulted status.
    assert by_id["int_20260701_bare"]["status"] == "received"


@pytest.mark.parametrize("evil", ["../../etc", "../global", "..", "../../"])
def test_micro_nodes_rejects_traversal_slug(acervo, evil):
    # A slug that tries to escape the acervo root must yield nothing (no leak, no raise).
    assert ax._micro_nodes(routes, acervo, evil, 2) == []


# ── Phase 1: x/download + HTTP dispatch (api/acervo_studio.py) ─────────────

import io
import zipfile
from urllib.parse import urlparse

import api.acervo_studio as studio


class _Handler:
    """Minimal duck-typed HTTP handler: captures status/headers/body."""
    def __init__(self, path="/"):
        self.path = path
        self.status = None
        self.headers = {}
        self.wfile = io.BytesIO()

    def send_response(self, code):
        self.status = code

    def send_header(self, k, v):
        self.headers[k] = v

    def end_headers(self):
        pass


@pytest.fixture
def session_ok(monkeypatch):
    """Session gate: only sid1 resolves."""
    monkeypatch.setattr(routes, "_resolve_session_workspace",
                        lambda sid: "/tmp/ws" if sid == "sid1" else None)


@pytest.fixture
def jcap(monkeypatch):
    """Capture routes.j / routes.bad JSON responses without a real socket."""
    calls = {}

    def fake_j(handler, obj, status=200):
        calls["status"], calls["obj"] = status, obj
        return True

    def fake_bad(handler, msg, status=400):
        calls["status"], calls["obj"] = status, {"error": msg}
        return True

    monkeypatch.setattr(routes, "j", fake_j)
    monkeypatch.setattr(routes, "bad", fake_bad)
    return calls


def _get(url):
    return urlparse(url)


def test_download_streams_file_with_attachment_disposition(acervo, session_ok):
    _w(acervo, "global/knowledge/x.md", "---\ntitle: X\n---\n\nbody\n")
    h = _Handler()
    studio.handle_download(h, _get(
        "/api/acervo/x/download?session_id=sid1&path=global/knowledge/x.md"))
    assert h.status == 200
    assert "attachment" in h.headers["Content-Disposition"]
    assert "x.md" in h.headers["Content-Disposition"]
    assert h.headers["X-Content-Type-Options"] == "nosniff"
    assert h.wfile.getvalue() == (acervo / "global/knowledge/x.md").read_bytes()


@pytest.mark.parametrize("evil", [
    "../etc/passwd", ".quarantine/x.md", "global/../../etc/passwd", "", None,
])
def test_download_blocks_unsafe_paths(acervo, session_ok, jcap, evil):
    h = _Handler()
    qs = "" if evil is None else "&path=" + str(evil)
    studio.handle_download(h, _get(
        "/api/acervo/x/download?session_id=sid1" + qs))
    assert jcap["status"] == 400


def test_download_missing_file_404(acervo, session_ok, jcap):
    h = _Handler()
    studio.handle_download(h, _get(
        "/api/acervo/x/download?session_id=sid1&path=global/knowledge/nope.md"))
    assert jcap["status"] == 404


def test_download_requires_known_session(acervo, jcap, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: None)
    h = _Handler()
    studio.handle_download(h, _get(
        "/api/acervo/x/download?session_id=ghost&path=global/knowledge/x.md"))
    assert jcap["status"] == 404


def test_download_artifact_zip_deliverables_only(acervo, session_ok):
    base = acervo / "_artifacts" / "items" / "art_demo"
    (base / "source").mkdir(parents=True)
    (base / "exports").mkdir()
    (base / "receipts").mkdir()
    (base / "manifest.json").write_text("{}", encoding="utf-8")
    (base / "source" / "a.md").write_text("# a\n", encoding="utf-8")
    (base / "exports" / "a.pdf").write_bytes(b"%PDF")
    (base / "receipts" / "r.json").write_text("{}", encoding="utf-8")
    h = _Handler()
    studio.handle_download(h, _get(
        "/api/acervo/x/download?session_id=sid1&artifact_id=art_demo"))
    assert h.status == 200
    assert h.headers["Content-Type"] == "application/zip"
    names = set(zipfile.ZipFile(io.BytesIO(h.wfile.getvalue())).namelist())
    assert names == {"manifest.json", "source/a.md", "exports/a.pdf"}


@pytest.mark.parametrize("bad_id", ["../x", ".hidden", "a/b", ""])
def test_download_artifact_id_validation(acervo, session_ok, jcap, bad_id):
    h = _Handler()
    studio.handle_download(h, _get(
        "/api/acervo/x/download?session_id=sid1&artifact_id=" + bad_id))
    assert jcap["status"] == 400


def test_download_rejects_both_params(acervo, session_ok, jcap):
    h = _Handler()
    studio.handle_download(h, _get(
        "/api/acervo/x/download?session_id=sid1&path=a.md&artifact_id=b"))
    assert jcap["status"] == 400


def test_get_dispatcher_delegates_download_to_studio(acervo, session_ok):
    _w(acervo, "global/knowledge/x.md")
    h = _Handler()
    ax.handle_acervo_x_get(h, _get(
        "/api/acervo/x/download?session_id=sid1&path=global/knowledge/x.md"))
    assert h.status == 200
    assert "attachment" in h.headers["Content-Disposition"]


def test_get_dispatcher_unknown_path_still_404s(acervo, session_ok, jcap):
    h = _Handler()
    ax.handle_acervo_x_get(h, _get("/api/acervo/x/nope?session_id=sid1"))
    assert jcap["status"] == 404


def test_artifacts_tree_nodes_carry_kind(acervo, session_ok, jcap):
    (acervo / "_artifacts" / "items" / "pkg_dir" / "source").mkdir(parents=True)
    _w(acervo, "_artifacts/items/loose.md", "# loose\n")
    h = _Handler()
    ax.handle_acervo_x_get(h, _get(
        "/api/acervo/x/tree?session_id=sid1&scope=artifacts"))
    kinds = {n["name"]: n["kind"] for n in jcap["obj"]["nodes"]}
    assert kinds["pkg_dir"] == "dir"
    assert kinds["loose.md"] == "file"


# ── Security regressions: symlink escapes into .quarantine/ ───────────────

import os


def test_download_file_symlink_into_quarantine_blocked(acervo, session_ok, jcap):
    """A clean-looking input path (global/knowledge/link.md) that RESOLVES
    through a symlink into .quarantine/ must be rejected, even though
    _safe_acervo_path only inspects the literal input components."""
    quarantine = acervo / ".quarantine"
    quarantine.mkdir(parents=True)
    secret = quarantine / "secret.txt"
    secret.write_text("TOP SECRET SENTINEL", encoding="utf-8")

    link_dir = acervo / "global" / "knowledge"
    link_dir.mkdir(parents=True)
    os.symlink(secret, link_dir / "link.md")

    h = _Handler()
    studio.handle_download(h, _get(
        "/api/acervo/x/download?session_id=sid1&path=global/knowledge/link.md"))
    assert jcap["status"] == 400


def test_download_artifact_zip_excludes_escaping_symlink(acervo, session_ok):
    """A symlink inside the artifact dir that resolves OUTSIDE the artifact
    (but still under the acervo root, e.g. into .quarantine/) must be skipped
    by the zip's containment check — the leak must not be zipped."""
    quarantine = acervo / ".quarantine"
    quarantine.mkdir(parents=True)
    secret = quarantine / "secret.txt"
    secret.write_text("TOP SECRET SENTINEL", encoding="utf-8")

    base = acervo / "_artifacts" / "items" / "art_demo"
    (base / "source").mkdir(parents=True)
    (base / "exports").mkdir()
    (base / "receipts").mkdir()
    (base / "manifest.json").write_text("{}", encoding="utf-8")
    (base / "source" / "a.md").write_text("# a\n", encoding="utf-8")
    (base / "exports" / "a.pdf").write_bytes(b"%PDF")
    (base / "receipts" / "r.json").write_text("{}", encoding="utf-8")
    os.symlink(secret, base / "source" / "leak.txt")

    h = _Handler()
    studio.handle_download(h, _get(
        "/api/acervo/x/download?session_id=sid1&artifact_id=art_demo"))
    assert h.status == 200
    zf = zipfile.ZipFile(io.BytesIO(h.wfile.getvalue()))
    names = set(zf.namelist())
    assert names == {"manifest.json", "source/a.md", "exports/a.pdf"}
    for name in names:
        assert b"TOP SECRET SENTINEL" not in zf.read(name)


def test_download_symlinked_artifact_dir_blocked(acervo, session_ok, jcap):
    """If _artifacts/items/<id> itself is a symlink to .quarantine/, the
    input string looks clean ('evil') but resolves onto a dot-prefixed
    component — must be rejected."""
    quarantine = acervo / ".quarantine"
    quarantine.mkdir(parents=True)
    (acervo / "_artifacts" / "items").mkdir(parents=True)
    os.symlink(quarantine, acervo / "_artifacts" / "items" / "evil")

    h = _Handler()
    studio.handle_download(h, _get(
        "/api/acervo/x/download?session_id=sid1&artifact_id=evil"))
    assert jcap["status"] == 400
