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


def test_raw_symlink_into_quarantine_blocked(acervo, session_ok, jcap):
    """x/raw must apply the same resolved-path dot-guard as x/download: a
    clean-looking input path (global/knowledge/link.md) that RESOLVES through
    a symlink into .quarantine/ must be rejected, not streamed — even though
    _safe_acervo_path only inspects the literal input components."""
    quarantine = acervo / ".quarantine"
    quarantine.mkdir(parents=True)
    secret = quarantine / "secret.txt"
    secret.write_text("TOP SECRET SENTINEL", encoding="utf-8")

    link_dir = acervo / "global" / "knowledge"
    link_dir.mkdir(parents=True)
    os.symlink(secret, link_dir / "link.md")

    h = _Handler()
    ax.handle_acervo_x_get(h, _get(
        "/api/acervo/x/raw?session_id=sid1&path=global/knowledge/link.md"))
    assert jcap["status"] == 400
    assert h.status != 200
    assert b"TOP SECRET SENTINEL" not in h.wfile.getvalue()


# ── Phase 1: Phase-0 Minors — _micro_title harmonization + tree dispatch ───

def test_micro_title_strips_indice_marker(acervo):
    _w(acervo, "micro/comercial/_meta/index.md",
       "---\ntitle: Índice — Comercial\n---\n\nx\n")
    nodes = ax._micro_nodes(routes, acervo, "", 1)
    by_slug = {n["slug"]: n for n in nodes}
    assert by_slug["comercial"]["title"] == "Comercial"


def test_micro_title_falls_back_to_microverso_yaml(acervo):
    (acervo / "micro" / "vendas-b2b" / "knowledge").mkdir(parents=True)
    (acervo / "micro" / "vendas-b2b" / "microverso.yaml").write_text(
        "name: Vendas B2B\ntype: dominio\n", encoding="utf-8")
    nodes = ax._micro_nodes(routes, acervo, "", 1)
    by_slug = {n["slug"]: n for n in nodes}
    assert by_slug["vendas-b2b"]["title"] == "Vendas B2B"


def test_micro_title_humanizes_when_no_metadata(acervo):
    (acervo / "micro" / "sales-ai" / "knowledge").mkdir(parents=True)
    nodes = ax._micro_nodes(routes, acervo, "", 1)
    by_slug = {n["slug"]: n for n in nodes}
    assert by_slug["sales-ai"]["title"] == "Sales ai"


def test_handle_tree_http_dispatch_micro_scope(acervo, session_ok, jcap):
    _w(acervo, "micro/comercial/knowledge/precificacao.md")
    h = _Handler()
    ax.handle_acervo_x_get(h, _get(
        "/api/acervo/x/tree?session_id=sid1&scope=micro&depth=1"))
    assert jcap["obj"]["scope"] == "micro"
    slugs = [n["slug"] for n in jcap["obj"]["nodes"] if n["type"] == "microverse"]
    assert "comercial" in slugs


# ── Phase 2a: intake capture (api/acervo_studio.py) ────────────────────────
import base64 as _b64
import datetime as _dt


def test_slugify_and_intake_id_shape(acervo):
    assert studio._slugify("Notas de Reunião — Q3!") == "notas-de-reuniao-q3"
    assert studio._slugify("   ") == "item"          # empty -> fallback
    iid = studio._intake_id("hello", now=_dt.datetime(2026, 7, 10, 9, 8, 7))
    assert iid == "int_20260710_090807_hello"
    assert studio._valid_intake_id(iid)
    assert not studio._valid_intake_id("../evil")
    assert not studio._valid_intake_id(".hidden")
    assert not studio._valid_intake_id("has/slash")


def test_write_envelope_text_creates_manifest_and_original(acervo):
    m = studio._write_envelope(
        acervo, content_type="text", caption="a quick note",
        filename="", mime="", payload=b"# hello\n\nworld",
        session_id="sess-1", now=_dt.datetime(2026, 7, 10, 9, 8, 7))
    assert m["intake_id"] == "int_20260710_090807_a-quick-note"
    assert m["channel"] == "dashboard"
    assert m["content_type"] == "text"
    assert m["status"] == "received"
    assert m["session_ref"] == "sess-1"
    env = acervo / "_inbox" / "incoming" / m["intake_id"]
    assert (env / "manifest.json").is_file()
    assert (env / "original" / "note.md").read_text(encoding="utf-8") == "# hello\n\nworld"


def test_write_envelope_link_stores_url(acervo):
    m = studio._write_envelope(
        acervo, content_type="link", caption="Open Notebook",
        filename="", mime="", payload=b"https://example.com/x", session_id="s")
    env = acervo / "_inbox" / "incoming" / m["intake_id"]
    assert (env / "original" / "source.txt").read_text(encoding="utf-8") == "https://example.com/x"


def test_write_envelope_file_uses_safe_filename(acervo):
    m = studio._write_envelope(
        acervo, content_type="document", caption="",
        filename="../../etc/passwd", mime="text/plain", payload=b"data",
        session_id="s")
    env = acervo / "_inbox" / "incoming" / m["intake_id"]
    assert (env / "original" / "passwd").read_text(encoding="utf-8") == "data"
    assert m["original_filename"] == "passwd"
    assert m["local_cached_path"] == "original/passwd"


def test_read_and_list_envelopes(acervo):
    m1 = studio._write_envelope(acervo, content_type="text", caption="first",
                                filename="", mime="", payload=b"one", session_id="s")
    m2 = studio._write_envelope(acervo, content_type="link", caption="second",
                                filename="", mime="", payload=b"http://y", session_id="s")
    got = studio._read_envelope(acervo, m1["intake_id"])
    assert got["intake_id"] == m1["intake_id"]
    assert "original/note.md" in got["files"]
    assert studio._read_envelope(acervo, "../escape") is None
    assert studio._read_envelope(acervo, "int_20990101_000000_nope") is None
    listing = studio._list_envelopes(acervo)
    ids = [e["intake_id"] for e in listing]
    assert set(ids) == {m1["intake_id"], m2["intake_id"]}
    assert all("title" in e and "status" in e for e in listing)


# ── Phase 2a T2: intake create routes (text/link/upload base64) ────────────

def test_intake_text_route_creates_envelope(acervo, session_ok, jcap):
    h = _Handler("/api/acervo/x/intake/text")
    studio.handle_studio_post(h, {"session_id": "sid1", "caption": "hi", "text": "hello world"})
    assert jcap["status"] == 200
    iid = jcap["obj"]["intake_id"]
    assert iid.startswith("int_") and jcap["obj"]["ok"] is True
    env = acervo / "_inbox" / "incoming" / iid
    assert (env / "original" / "note.md").read_text(encoding="utf-8") == "hello world"


def test_intake_link_route(acervo, session_ok, jcap):
    h = _Handler("/api/acervo/x/intake/link")
    studio.handle_studio_post(h, {"session_id": "sid1", "url": "https://example.com"})
    assert jcap["status"] == 200
    env = acervo / "_inbox" / "incoming" / jcap["obj"]["intake_id"]
    assert (env / "original" / "source.txt").read_text(encoding="utf-8") == "https://example.com"


def test_intake_upload_base64(acervo, session_ok, jcap):
    b64 = _b64.b64encode(b"PDFDATA").decode("ascii")
    h = _Handler("/api/acervo/x/intake/upload")
    studio.handle_studio_post(h, {"session_id": "sid1", "filename": "report.pdf",
                                  "mime": "application/pdf", "content_b64": b64})
    assert jcap["status"] == 200
    env = acervo / "_inbox" / "incoming" / jcap["obj"]["intake_id"]
    assert (env / "original" / "report.pdf").read_bytes() == b"PDFDATA"


def test_intake_requires_session(acervo, jcap, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: None)
    h = _Handler("/api/acervo/x/intake/text")
    studio.handle_studio_post(h, {"session_id": "bad", "text": "x"})
    assert jcap["status"] in (400, 404)


def test_intake_upload_too_large_413(acervo, session_ok, jcap):
    big = _b64.b64encode(b"x" * (studio._MAX_INTAKE_BYTES + 1)).decode("ascii")
    h = _Handler("/api/acervo/x/intake/upload")
    studio.handle_studio_post(h, {"session_id": "sid1", "filename": "big.bin", "content_b64": big})
    assert jcap["status"] == 413


def test_intake_empty_text_rejected(acervo, session_ok, jcap):
    h = _Handler("/api/acervo/x/intake/text")
    studio.handle_studio_post(h, {"session_id": "sid1", "text": "   "})
    assert jcap["status"] == 400


def test_intake_bad_base64_rejected(acervo, session_ok, jcap):
    h = _Handler("/api/acervo/x/intake/upload")
    studio.handle_studio_post(h, {"session_id": "sid1", "filename": "x.bin",
                                  "content_b64": "!!!not base64!!!"})
    assert jcap["status"] == 400


# ── Phase 2a T3: intake list + detail GET routes ───────────────────────────

def test_intake_list_route(acervo, session_ok, jcap):
    studio._write_envelope(acervo, content_type="text", caption="alpha",
                           filename="", mime="", payload=b"a", session_id="s")
    studio._write_envelope(acervo, content_type="link", caption="beta",
                           filename="", mime="", payload=b"http://b", session_id="s")
    h = _Handler("/api/acervo/x/intake")
    studio.handle_studio_get(h, _get("/api/acervo/x/intake?session_id=sid1"))
    assert jcap["status"] == 200
    assert jcap["obj"]["count"] == 2
    assert {i["title"] for i in jcap["obj"]["items"]} == {"alpha", "beta"}


def test_intake_detail_route(acervo, session_ok, jcap):
    m = studio._write_envelope(acervo, content_type="text", caption="alpha",
                               filename="", mime="", payload=b"hello", session_id="s")
    h = _Handler("/api/acervo/x/intake/item")
    studio.handle_studio_get(h, _get("/api/acervo/x/intake/item?session_id=sid1&id=" + m["intake_id"]))
    assert jcap["status"] == 200
    assert jcap["obj"]["envelope"]["intake_id"] == m["intake_id"]
    assert "original/note.md" in jcap["obj"]["envelope"]["files"]


def test_intake_detail_missing_404(acervo, session_ok, jcap):
    h = _Handler("/api/acervo/x/intake/item")
    studio.handle_studio_get(h, _get("/api/acervo/x/intake/item?session_id=sid1&id=int_20990101_000000_nope"))
    assert jcap["status"] == 404


def test_intake_detail_rejects_bad_id(acervo, session_ok, jcap):
    h = _Handler("/api/acervo/x/intake/item")
    studio.handle_studio_get(h, _get("/api/acervo/x/intake/item?session_id=sid1&id=../../etc"))
    assert jcap["status"] in (400, 404)


def test_get_dispatcher_delegates_intake_list(acervo, session_ok, jcap):
    h = _Handler("/api/acervo/x/intake")
    ax.handle_acervo_x_get(h, _get("/api/acervo/x/intake?session_id=sid1"))
    assert jcap["status"] == 200
    assert "items" in jcap["obj"]


# ── Phase 2a review fixes: id-collision + GET session gates ─────────────────

def test_write_envelope_collision_no_overwrite(acervo):
    now = _dt.datetime(2026, 7, 10, 9, 8, 7)
    m1 = studio._write_envelope(acervo, content_type="text", caption="dup",
                                filename="", mime="", payload=b"first", session_id="s", now=now)
    m2 = studio._write_envelope(acervo, content_type="text", caption="dup",
                                filename="", mime="", payload=b"second", session_id="s", now=now)
    assert m1["intake_id"] != m2["intake_id"]
    assert m2["intake_id"] == m1["intake_id"] + "-2"
    assert studio._valid_intake_id(m2["intake_id"])   # suffixed id still passes the gate
    inc = acervo / "_inbox" / "incoming"
    assert (inc / m1["intake_id"] / "original" / "note.md").read_text(encoding="utf-8") == "first"
    assert (inc / m2["intake_id"] / "original" / "note.md").read_text(encoding="utf-8") == "second"


def test_intake_list_requires_session(acervo, jcap, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: None)
    h = _Handler("/api/acervo/x/intake")
    studio.handle_studio_get(h, _get("/api/acervo/x/intake?session_id=ghost"))
    assert jcap["status"] == 404


def test_intake_detail_requires_session(acervo, jcap, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: None)
    h = _Handler("/api/acervo/x/intake/item")
    studio.handle_studio_get(h, _get("/api/acervo/x/intake/item?session_id=ghost&id=int_20990101_000000_x"))
    assert jcap["status"] == 404


# ── Phase 2b Task 1: agent mediation — propose_triage (mocked agent) ─────────
import api.acervo_studio_agent as studio_agent


def _mk_env(acervo, caption="a client note"):
    return studio._write_envelope(acervo, content_type="text", caption=caption,
                                  filename="", mime="", payload=b"cliente ACME pediu proposta",
                                  session_id="s")


def test_propose_triage_parses_valid_proposal(acervo, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"scope":"micro","slug":"acme","nature":"knowledge",'
                                            '"title":"Proposta ACME","rationale":"cliente","keep_in_inbox":false}')
    out = studio_agent.propose_triage(acervo, m["intake_id"])
    assert out["ok"] is True
    assert out["proposal"]["scope"] == "micro"
    assert out["proposal"]["slug"] == "acme"
    assert out["proposal"]["nature"] == "knowledge"
    assert out["proposal"]["title"] == "Proposta ACME"


def test_propose_triage_handles_fenced_json(acervo, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: 'Sure!\n```json\n{"scope":"global","nature":"knowledge",'
                                            '"title":"Nota","keep_in_inbox":false}\n```\nDone.')
    out = studio_agent.propose_triage(acervo, m["intake_id"])
    assert out["ok"] is True and out["proposal"]["scope"] == "global"
    assert out["proposal"]["slug"] == ""   # non-micro drops slug


def test_propose_triage_offline_when_agent_unavailable(acervo, monkeypatch):
    m = _mk_env(acervo)
    def _boom(sp, up, **k):
        raise studio_agent.AgentUnavailable("no runtime")
    monkeypatch.setattr(studio_agent, "_run_agent_text", _boom)
    out = studio_agent.propose_triage(acervo, m["intake_id"])
    assert out == {"ok": False, "offline": True}


def test_propose_triage_rejects_bad_scope(acervo, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"scope":"../etc","title":"x"}')
    out = studio_agent.propose_triage(acervo, m["intake_id"])
    assert out["ok"] is False and "error" in out


def test_propose_triage_micro_requires_slug(acervo, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"scope":"micro","slug":"","title":"x"}')
    out = studio_agent.propose_triage(acervo, m["intake_id"])
    assert out["ok"] is False


def test_propose_triage_missing_envelope(acervo, monkeypatch):
    monkeypatch.setattr(studio_agent, "_run_agent_text", lambda sp, up, **k: "{}")
    out = studio_agent.propose_triage(acervo, "int_20990101_000000_nope")
    assert out["ok"] is False and out["error"] == "envelope not found"


def test_propose_triage_unparseable(acervo, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(studio_agent, "_run_agent_text", lambda sp, up, **k: "no json here at all")
    out = studio_agent.propose_triage(acervo, m["intake_id"])
    assert out["ok"] is False and "error" in out


# ── Phase 2b Task 2: triage route (POST x/intake/item/triage) ───────────────

def test_triage_route_happy(acervo, session_ok, jcap, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"scope":"micro","slug":"acme","nature":"knowledge",'
                                            '"title":"ACME","keep_in_inbox":false}')
    h = _Handler("/api/acervo/x/intake/item/triage")
    studio.handle_studio_post(h, {"session_id": "sid1", "id": m["intake_id"]})
    assert jcap["status"] == 200
    assert jcap["obj"]["proposal"]["slug"] == "acme"
    # proposal persisted to routing.json
    rj = json.loads((acervo / "_inbox" / "incoming" / m["intake_id"] / "routing.json")
                    .read_text(encoding="utf-8"))
    assert rj["proposal"]["scope"] == "micro"


def test_triage_route_offline(acervo, session_ok, jcap, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    def _boom(sp, up, **k):
        raise studio_agent.AgentUnavailable("no runtime")
    monkeypatch.setattr(studio_agent, "_run_agent_text", _boom)
    h = _Handler("/api/acervo/x/intake/item/triage")
    studio.handle_studio_post(h, {"session_id": "sid1", "id": m["intake_id"]})
    # operational states => 200 with ok flag (so the UI renders them calmly)
    assert jcap["status"] == 200 and jcap["obj"]["offline"] is True and jcap["obj"]["ok"] is False


def test_triage_route_missing_envelope_404(acervo, session_ok, jcap, monkeypatch):
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    h = _Handler("/api/acervo/x/intake/item/triage")
    studio.handle_studio_post(h, {"session_id": "sid1", "id": "int_20990101_000000_nope"})
    assert jcap["status"] == 404


def test_triage_route_bad_id_400(acervo, session_ok, jcap):
    h = _Handler("/api/acervo/x/intake/item/triage")
    studio.handle_studio_post(h, {"session_id": "sid1", "id": "../../etc"})
    assert jcap["status"] == 400


def test_triage_route_requires_session(acervo, jcap, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: None)
    h = _Handler("/api/acervo/x/intake/item/triage")
    studio.handle_studio_post(h, {"session_id": "ghost", "id": "int_20990101_000000_x"})
    assert jcap["status"] in (400, 404)


# ── Phase 2b Task 3: promote route (agent crafts body, server writes via acervoctl) ──

def _mock_commit_ok(monkeypatch, acervo):
    """Mock the deterministic acervoctl write to succeed with a receipt, and
    actually drop a page file so created_path is real-ish."""
    def _fake(root, slug, nature, title, body_md, class_name, description, tags=None):
        rel = "micro/%s/%s/%s.md" % (slug, nature, studio._slugify(title))
        p = acervo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body_md, encoding="utf-8")
        return {"status": "committed", "microverso": slug, "nature": nature,
                "relative_output": rel, "entry_type": "CREATED"}
    monkeypatch.setattr(studio_agent, "_commit_via_acervoctl", _fake)


def _routing(slug="acme", nature="knowledge", title="Proposta ACME", scope="micro"):
    return {"scope": scope, "slug": slug, "nature": nature, "title": title}


def test_promote_happy_writes_and_moves(acervo, session_ok, jcap, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"body_markdown":"# Proposta\\n\\ncorpo","class":"volátil","description":"d"}')
    _mock_commit_ok(monkeypatch, acervo)
    h = _Handler("/api/acervo/x/intake/item/promote")
    studio.handle_studio_post(h, {"session_id": "sid1", "id": m["intake_id"], "routing": _routing()})
    assert jcap["status"] == 200 and jcap["obj"]["ok"] is True
    assert jcap["obj"]["created_path"] == "micro/acme/knowledge/proposta-acme.md"
    assert (acervo / "micro/acme/knowledge/proposta-acme.md").is_file()
    # envelope moved incoming -> promoted
    assert not (acervo / "_inbox" / "incoming" / m["intake_id"]).exists()
    assert (acervo / "_inbox" / "promoted" / m["intake_id"]).is_dir()


def test_promote_rejects_non_micro_scope(acervo, session_ok, jcap, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    monkeypatch.setattr(studio_agent, "_run_agent_text", lambda sp, up, **k: "{}")
    h = _Handler("/api/acervo/x/intake/item/promote")
    studio.handle_studio_post(h, {"session_id": "sid1", "id": m["intake_id"],
                                  "routing": _routing(scope="global")})
    assert jcap["status"] == 200 and jcap["obj"]["ok"] is False and "micro" in jcap["obj"]["error"]
    # nothing moved
    assert (acervo / "_inbox" / "incoming" / m["intake_id"]).is_dir()


def test_promote_offline_keeps_envelope(acervo, session_ok, jcap, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    def _boom(sp, up, **k):
        raise studio_agent.AgentUnavailable("no runtime")
    monkeypatch.setattr(studio_agent, "_run_agent_text", _boom)
    h = _Handler("/api/acervo/x/intake/item/promote")
    studio.handle_studio_post(h, {"session_id": "sid1", "id": m["intake_id"], "routing": _routing()})
    assert jcap["status"] == 200 and jcap["obj"]["offline"] is True
    assert (acervo / "_inbox" / "incoming" / m["intake_id"]).is_dir()  # not moved


def test_promote_write_rejected_keeps_envelope(acervo, session_ok, jcap, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"body_markdown":"x","class":"volátil"}')
    def _reject(*a, **k):
        raise studio_agent.PromoteError("write rejected: cross_microverso_write_blocked")
    monkeypatch.setattr(studio_agent, "_commit_via_acervoctl", _reject)
    h = _Handler("/api/acervo/x/intake/item/promote")
    studio.handle_studio_post(h, {"session_id": "sid1", "id": m["intake_id"], "routing": _routing()})
    assert jcap["status"] == 200 and jcap["obj"]["ok"] is False and "rejected" in jcap["obj"]["error"]
    assert (acervo / "_inbox" / "incoming" / m["intake_id"]).is_dir()  # not moved


def test_promote_requires_routing(acervo, session_ok, jcap, monkeypatch):
    m = _mk_env(acervo)
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    h = _Handler("/api/acervo/x/intake/item/promote")
    studio.handle_studio_post(h, {"session_id": "sid1", "id": m["intake_id"]})
    assert jcap["status"] == 400


def test_promote_scaffolds_microverso_meta(acervo, monkeypatch):
    # _scaffold_microverso creates _meta/index.md + log.md when absent
    studio_agent._scaffold_microverso(acervo, "brandnew")
    assert (acervo / "micro" / "brandnew" / "_meta" / "index.md").read_text().startswith("# Index")
    assert (acervo / "micro" / "brandnew" / "_meta" / "log.md").read_text().startswith("# Log")


# ── Phase 2b review fixes: promote write-boundary + session gate ────────────

@pytest.mark.parametrize("bad_slug", ["../evil", "_meta", ".quarantine", "a/b", ""])
def test_promote_rejects_bad_slug(acervo, session_ok, jcap, monkeypatch, bad_slug):
    """The module's own write-boundary guard: a bad slug is rejected BEFORE any
    agent turn or write, and the envelope is not moved."""
    m = _mk_env(acervo)
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    # if the guard is bypassed the agent would be called — make that loud
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: (_ for _ in ()).throw(AssertionError("guard bypassed")))
    h = _Handler("/api/acervo/x/intake/item/promote")
    studio.handle_studio_post(h, {"session_id": "sid1", "id": m["intake_id"],
                                  "routing": _routing(slug=bad_slug)})
    assert jcap["status"] == 200 and jcap["obj"]["ok"] is False
    assert (acervo / "_inbox" / "incoming" / m["intake_id"]).is_dir()  # not moved


def test_promote_requires_session(acervo, jcap, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: None)
    h = _Handler("/api/acervo/x/intake/item/promote")
    studio.handle_studio_post(h, {"session_id": "ghost", "id": "int_20990101_000000_x",
                                  "routing": _routing()})
    assert jcap["status"] in (400, 404)


# ── Phase 3 Task 1: publish module — safety + tools resolution ──────────────

import api.acervo_studio_publish as studio_pub


def _mk_artifact(acervo, art_id="art_20260712_relatorio", status="draft",
                 title="Relatório"):
    d = acervo / "_artifacts" / "items" / art_id
    (d / "source").mkdir(parents=True)
    (d / "exports").mkdir()
    (d / "source" / "source.md").write_text("# rel\n\nconteudo\n", encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({
        "artifact_id": art_id, "title": title, "status": status,
        "artifact_type": "document", "source_type": "markdown",
        "source_path": "source/source.md",
        "provenance": {"created_at": "2026-07-12T00:00:00Z"},
        "drive_target": {"provider": "google_drive",
                         "folder_path": "exocortex/inbox",
                         "visibility": "private"},
    }, ensure_ascii=False), encoding="utf-8")
    return d


@pytest.mark.parametrize("bad", ["", "../evil", "a/b", "a\\b", ".hidden", "x" * 129])
def test_pub_valid_artifact_id_rejects(bad):
    assert studio_pub._valid_artifact_id(bad) is False


def test_pub_valid_artifact_id_accepts():
    assert studio_pub._valid_artifact_id("art_20260712_relatorio") is True


def test_pub_artifact_dir_resolves(acervo):
    d = _mk_artifact(acervo)
    assert studio_pub._artifact_dir(acervo, "art_20260712_relatorio") == d


def test_pub_artifact_dir_missing_none(acervo):
    assert studio_pub._artifact_dir(acervo, "art_20990101_nope") is None


def test_pub_artifact_dir_blocks_symlink_into_quarantine(acervo):
    (acervo / ".quarantine" / "evil").mkdir(parents=True)
    (acervo / "_artifacts" / "items").mkdir(parents=True, exist_ok=True)
    (acervo / "_artifacts" / "items" / "linked").symlink_to(
        acervo / ".quarantine" / "evil", target_is_directory=True)
    assert studio_pub._artifact_dir(acervo, "linked") is None


def test_pub_resolve_tools_dir_prefers_root_copy(acervo, monkeypatch):
    tools = acervo / "global" / "tools"
    (tools / "harness").mkdir(parents=True)
    (tools / "artifact_publish.py").write_text("# stub\n", encoding="utf-8")
    (tools / "harness" / "validate_artifact_manifest.py").write_text(
        "# stub\n", encoding="utf-8")
    assert studio_pub._resolve_tools_dir(acervo) == str(tools)


def test_pub_resolve_tools_dir_none_when_absent(acervo, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "nohermes"))
    monkeypatch.setenv("EXOCORTEX_HOME", str(tmp_path / "noexo"))
    assert studio_pub._resolve_tools_dir(acervo) is None


# ── Phase 3 Task 2: CLI runners against fake tools in the fixture ────────────

def _mk_tools(acervo, *, validator_json=None, publish_json=None, publish_rc=0,
              publish_stderr=""):
    """Fake artifact_publish.py + validate_artifact_manifest.py inside the
    fixture acervo. The publisher touches ran.flag so tests can assert
    whether it was executed."""
    tools = acervo / "global" / "tools"
    (tools / "harness").mkdir(parents=True, exist_ok=True)
    vj = validator_json if validator_json is not None else [
        {"artifact": "x", "ok": True, "errors": [], "warnings": []}]
    (tools / "harness" / "validate_artifact_manifest.py").write_text(
        "import json, sys\n"
        "print(json.dumps(%r))\n"
        "sys.exit(0 if %r else 1)\n" % (vj, bool(vj[0].get("ok"))),
        encoding="utf-8")
    pj = publish_json if publish_json is not None else {
        "status": "published", "folder_path": "exocortex/inbox",
        "folder_id": "f1", "folder_link": "https://drive.example/f1",
        "files": [{"name": "source.md", "drive_file_id": "d1",
                   "webViewLink": "https://drive.example/d1",
                   "sha256": "aa" * 32, "size": 12}]}
    (tools / "artifact_publish.py").write_text(
        "import json, os, sys\n"
        "open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ran.flag'), 'w').close()\n"
        "sys.stderr.write(%r)\n"
        "print(json.dumps(%r, ensure_ascii=False))\n"
        "sys.exit(%d)\n" % (publish_stderr, pj, publish_rc),
        encoding="utf-8")
    return tools


def test_pub_run_validator_parses_ok(acervo):
    d = _mk_artifact(acervo)
    tools = _mk_tools(acervo)
    gate = studio_pub._run_validator(str(tools), acervo, d)
    assert gate == {"ok": True, "errors": [], "warnings": []}


def test_pub_run_validator_reports_errors(acervo):
    d = _mk_artifact(acervo)
    tools = _mk_tools(acervo, validator_json=[
        {"artifact": "x", "ok": False,
         "errors": ["Missing required field: title"],
         "warnings": ["No owner.id — artifact is orphaned"]}])
    gate = studio_pub._run_validator(str(tools), acervo, d)
    assert gate["ok"] is False
    assert gate["errors"] == ["Missing required field: title"]
    assert gate["warnings"] == ["No owner.id — artifact is orphaned"]


def test_pub_run_validator_unparseable_raises(acervo):
    d = _mk_artifact(acervo)
    tools = acervo / "global" / "tools"
    (tools / "harness").mkdir(parents=True, exist_ok=True)
    (tools / "harness" / "validate_artifact_manifest.py").write_text(
        "print('not json')\n", encoding="utf-8")
    (tools / "artifact_publish.py").write_text("", encoding="utf-8")
    with pytest.raises(studio_pub.PublishError):
        studio_pub._run_validator(str(tools), acervo, d)


def test_pub_run_publish_parses_receipt(acervo):
    d = _mk_artifact(acervo)
    tools = _mk_tools(acervo)
    receipt = studio_pub._run_publish(str(tools), acervo, d)
    assert receipt["status"] == "published"
    assert receipt["files"][0]["sha256"] == "aa" * 32
    assert (tools / "ran.flag").is_file()


def test_pub_run_publish_drive_unconfigured(acervo):
    d = _mk_artifact(acervo)
    tools = _mk_tools(acervo, publish_rc=1, publish_stderr=
                      "google_api.py não encontrado. Verifique a skill "
                      "productivity/google-workspace no runtime Hermes.\n")
    with pytest.raises(studio_pub.DriveNotConfigured):
        studio_pub._run_publish(str(tools), acervo, d)


def test_pub_run_publish_other_failure_raises(acervo):
    d = _mk_artifact(acervo)
    tools = _mk_tools(acervo, publish_rc=1, publish_stderr="boom: quota\n",
                      publish_json={"status": "error"})
    with pytest.raises(studio_pub.PublishError):
        studio_pub._run_publish(str(tools), acervo, d)


# ── Phase 3 Task 3: prepare + publish policies ───────────────────────────────

def test_pub_prepare_happy(acervo):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    out = studio_pub.prepare(acervo, "art_20260712_relatorio")
    assert out["ok"] is True
    assert out["artifact"]["id"] == "art_20260712_relatorio"
    assert out["artifact"]["title"] == "Relatório"
    assert out["artifact"]["status"] == "draft"
    assert out["artifact"]["drive_target"] == "exocortex/inbox"
    assert out["gate"]["ok"] is True and out["can_publish"] is True
    vis = {v["value"]: v for v in out["visibility_options"]}
    assert vis["private"]["enabled"] is True
    assert vis["public"]["enabled"] is False and vis["public"]["gate"]


def test_pub_prepare_tools_missing(acervo, tmp_path, monkeypatch):
    _mk_artifact(acervo)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "nohermes"))
    monkeypatch.setenv("EXOCORTEX_HOME", str(tmp_path / "noexo"))
    out = studio_pub.prepare(acervo, "art_20260712_relatorio")
    assert out == {"ok": False, "tools_missing": True}


def test_pub_prepare_artifact_missing(acervo):
    _mk_tools(acervo)
    out = studio_pub.prepare(acervo, "art_20990101_nope")
    assert out["ok"] is False and out["error"] == "artifact not found"


def test_pub_prepare_bad_manifest(acervo):
    d = _mk_artifact(acervo)
    _mk_tools(acervo)
    (d / "manifest.json").write_text("{not json", encoding="utf-8")
    out = studio_pub.prepare(acervo, "art_20260712_relatorio")
    assert out["ok"] is False and "manifest" in out["error"]


def test_pub_publish_happy(acervo):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    out = studio_pub.publish(acervo, "art_20260712_relatorio")
    assert out["ok"] is True
    assert out["receipt"]["status"] == "published"


def test_pub_publish_gate_failed_blocks_and_skips_upload(acervo):
    _mk_artifact(acervo, status="ready")
    tools = _mk_tools(acervo, validator_json=[
        {"artifact": "x", "ok": False,
         "errors": ["Anti-slop quality check failed (score: 20/50...)"],
         "warnings": []}])
    out = studio_pub.publish(acervo, "art_20260712_relatorio")
    assert out["ok"] is False and out["gate_failed"] is True
    assert out["gate"]["errors"]
    assert not (tools / "ran.flag").exists()   # publish CLI never executed


def test_pub_publish_public_requires_flag(acervo):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    out = studio_pub.publish(acervo, "art_20260712_relatorio",
                             visibility="public")
    assert out["ok"] is False and "approve_public" in out["error"]


def test_pub_publish_public_gated_even_with_flag(acervo):
    _mk_artifact(acervo)
    tools = _mk_tools(acervo)
    out = studio_pub.publish(acervo, "art_20260712_relatorio",
                             visibility="public", approve_public=True)
    assert out["ok"] is False and out["public_gated"] is True
    assert not (tools / "ran.flag").exists()   # nothing uploaded


def test_pub_publish_invalid_visibility(acervo):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    out = studio_pub.publish(acervo, "art_20260712_relatorio",
                             visibility="unlisted")
    assert out["ok"] is False and "visibility" in out["error"]


def test_pub_publish_drive_unconfigured(acervo):
    _mk_artifact(acervo)
    _mk_tools(acervo, publish_rc=1, publish_stderr=
              "google_api.py não encontrado.\n")
    out = studio_pub.publish(acervo, "art_20260712_relatorio")
    assert out["ok"] is False and out["drive_unconfigured"] is True
