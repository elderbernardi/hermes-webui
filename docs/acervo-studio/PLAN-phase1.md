# Acervo Studio — Phase 1 Implementation Plan (Edit & Download & Chat-Bridge)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elevate the read-only Phase 0 Studio into a full manual knowledge manager: an inline **editor** (body + OKF frontmatter, wired to the existing MOD-009 write endpoints `x/{save,tags,status,move}`), **download** (md / raw file / artifact zip via a new `x/download` endpoint), and **stage-to-chat** (`x/stage` → pending-context bridge) — plus the 8 Minor findings deferred from Phase 0. Still **zero agent dependency** (RFC §11 Phase 1).

**Architecture:** New Studio-only backend endpoints start their own module **`api/acervo_studio.py`** (RFC §6.1): the MOD-009 dispatchers in `api/acervo_explorer.py` delegate any `/api/acervo/x/*` sub-path they don't own to it before 404ing, so **`api/routes.py` stays at 0 new lines** (the prefix dispatch installed by MOD-009 covers the new module too). The frontend grows inside the existing `static/acervo-studio.js` IIFE: a quiet toolbar on the reader (Editar · Enviar ao chat · Baixar · ⋯), an inline editor with dirty-guard and perene confirm, and a ⋯ menu (move / status). All writes go through the MOD-009 endpoints — the Studio adds **no new write path** to the acervo; the only new endpoint (`x/download`) is read-only.

**Tech Stack:** Python 3 stdlib HTTP server (no framework), PyYAML; vanilla ES (`sourceType:"script"`, IIFE, no build); pytest (hermetic tmp acervo + duck-typed handler); ESLint runtime-guard.

## Global Constraints

- **Vanilla JS only** — IIFE-scoped, `'use strict'`, **no ES `import`/`export`** (enforced by `npm run lint:runtime`). No framework, no bundler.
- **Rebase-safe / self-contained** — `api/routes.py`: **0 new lines**. `static/index.html`: **0 new lines** (Phase 0's 3 lines already mount everything). Never edit `static/style.css`, `static/ui.js`, `static/workspace.js`, `static/acervo.js`, `static/acervo-explorer.*`. New backend behavior in the NEW file `api/acervo_studio.py`; `api/acervo_explorer.py` (fork-owned) gets only the delegation fallback + small additive edits.
- **Namespaces** — CSS `.axs-*`, JS `acervoStudio*` / `AXS` (never MOD-009's `.ax-*` / `AX` / `acervoExplorer*`).
- **Write boundary (RFC §6.3)** — edit-existing-page only, via MOD-009 `x/{save,tags,status,move}` (OKF-preserving merge, status gated to `_ACERVO_UI_STATUSES` = `{draft, ready, archived}`). **No create, no delete**; `.quarantine/` unreachable (`_safe_acervo_path` rejects any `.`-prefixed component). The new `x/download` is GET/read-only.
- **Path root is always `_acervo_root()`** — never the session workspace. Every endpoint session-gated: GET via `routes._resolve_session_workspace(sid)`, POST via `routes.get_session_for_file_ops(sid)` (the MOD-009 idiom).
- **Reused routes.py helpers (late `import api.routes as routes` inside functions):** `_acervo_root`, `_resolve_session_workspace`, `_ACERVO_NATURES`, `_ACERVO_UI_STATUSES`, `_read_frontmatter_meta`, `_humanize_slug`, `_content_disposition_value`, `_folder_download_collect`, `_folder_zip_max_bytes`, `_folder_zip_max_files`, `open_anchored_fd`, `j`, `bad`.
- **Reused frontend globals (do not redeclare):** `S`, `api(url[,opts])`, `esc`, `showToast(msg, ms, type)`, `renderMd`, `humanizeFilename`, `showConfirmDialog(opts)`, `showPromptDialog(opts)`, `renderStagedContextChips()`. Session id via `S.session.session_id`.
- **Test baseline** — full suite: ≈9070 pass / 17 documented pre-existing fails (~30 observed locally, env-sensitive: live-server/locale/skin/git). Phase 1 must add **zero new failures**. `tests/test_mod010_acervo_studio.py` currently has **7 passing test items**.
- **E2E safety** — Phase 1 E2E exercises WRITES. Never run E2E against `~/exocortex/acervo`; always a throwaway fixture acervo (Task 7 builds one).

---

### Task 1: Backend — `api/acervo_studio.py` with `GET x/download` (file + artifact zip) + dispatcher delegation

**Files:**
- Create: `api/acervo_studio.py`
- Modify: `api/acervo_explorer.py` (dispatcher fallbacks → delegate to the new module; additive `kind` field on artifact nodes)
- Test: `tests/test_mod010_acervo_studio.py` (extend)

**Interfaces:**
- Produces: `acervo_studio.handle_download(handler, parsed)`; `acervo_studio.handle_studio_get(handler, parsed)` / `handle_studio_post(handler, body)` (the delegation targets); HTTP surface `GET /api/acervo/x/download?session_id=…&path=<rel>` (single file, `Content-Disposition: attachment`) and `GET /api/acervo/x/download?session_id=…&artifact_id=<id>` (zip of `_artifacts/items/<id>/`, deliverables only: `manifest.json`, `source/`, `exports/` — mirrors `/api/artifact/zip` #84). Artifact tree nodes gain `"kind": "dir"|"file"`.
- Consumes: `acervo_explorer._safe_acervo_path`; routes helpers listed in Global Constraints.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mod010_acervo_studio.py` (after the last test):

```python
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
    assert jcap["status"] in (400, 404)


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/elder/projetos/projetob/hermes-webui && python -m pytest tests/test_mod010_acervo_studio.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'api.acervo_studio'` (the 7 Phase-0 tests can't even collect until the module exists).

- [ ] **Step 3: Create `api/acervo_studio.py`**

```python
"""Acervo Studio backend — MOD-010 (Phase 1+; prefix /api/acervo/x/).

Studio-only endpoints, kept out of api/acervo_explorer.py (MOD-009) per RFC
§6.1 so each MOD stays focused. The MOD-009 dispatchers delegate any
/api/acervo/x/* sub-path they don't own to handle_studio_get/handle_studio_post
below — so api/routes.py stays at ZERO new lines (the prefix dispatch MOD-009
installed covers this module too).

Phase 1 surface (read-only; no agent dependency):
  GET /api/acervo/x/download?session_id=…&path=<rel>        → single-file attachment
  GET /api/acervo/x/download?session_id=…&artifact_id=<id>  → zip of
      _artifacts/items/<id>/ (deliverables only: manifest.json, source/,
      exports/ — mirrors /api/artifact/zip, #84)

Path safety: every path goes through acervo_explorer._safe_acervo_path
(anchored on _acervo_root(); rejects traversal / symlink escape / absolute /
any dot-prefixed component, which keeps .quarantine/ unreachable). Heavy reuse
happens through late ``import api.routes as routes`` inside functions to avoid
a circular import at module load (the MOD-009 idiom).
"""

import os
import shutil
from urllib.parse import parse_qs

from api.acervo_explorer import _safe_acervo_path

_MAX_FILE_DOWNLOAD_BYTES = 50 * 1024 * 1024  # mirror MOD-009 _MAX_RAW_BYTES


def _download_file(handler, routes, rel):
    """Stream one acervo file as an attachment (md or binary alike)."""
    import mimetypes as _mt
    try:
        target = _safe_acervo_path(rel)
    except ValueError:
        return routes.bad(handler, "invalid path", 400)
    if not target.is_file():
        return routes.j(handler, {"error": "file not found"}, status=404)
    try:
        size = target.stat().st_size
    except OSError:
        return routes.j(handler, {"error": "file not readable"}, status=500)
    if size > _MAX_FILE_DOWNLOAD_BYTES:
        return routes.j(handler, {"error": "file too large"}, status=413)
    try:
        data = target.read_bytes()
    except OSError:
        return routes.j(handler, {"error": "file not readable"}, status=500)
    mime = _mt.guess_type(target.name)[0] or "application/octet-stream"
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header(
        "Content-Disposition",
        routes._content_disposition_value("attachment", target.name))
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)
    return True


def _download_artifact_zip(handler, routes, art_id):
    """Zip an artifact package from the ACERVO root (deliverables only).

    /api/artifact/zip is workspace-anchored and cannot serve the acervo's
    _artifacts/items — this is the acervo-anchored equivalent, with the same
    deliverable filter (#84: manifest.json + source/ + exports/; receipts/ and
    revisions/ are internal provenance) and the same anchored-fd streaming.
    """
    import zipfile
    if "/" in art_id or "\\" in art_id or art_id.startswith("."):
        return routes.bad(handler, "invalid artifact id", 400)
    try:
        target = _safe_acervo_path("_artifacts/items/" + art_id)
    except ValueError:
        return routes.bad(handler, "invalid artifact id", 400)
    if not target.is_dir():
        return routes.j(handler, {"error": "artifact not found"}, status=404)

    root_r = routes._acervo_root().resolve()
    files, _total, limit_hit = routes._folder_download_collect(
        target, root_r, routes._folder_zip_max_bytes(),
        routes._folder_zip_max_files())
    if limit_hit:
        return routes.j(handler, {"error": "artifact too large",
                                  "reason": limit_hit}, status=413)

    def _is_deliverable(arc):
        a = arc.replace("\\", "/")
        return a == "manifest.json" or a.startswith("source/") or a.startswith("exports/")

    files = [(fp, arc) for (fp, arc) in files if _is_deliverable(arc)]

    handler.send_response(200)
    handler.send_header("Content-Type", "application/zip")
    handler.send_header(
        "Content-Disposition",
        routes._content_disposition_value("attachment", art_id + ".zip"))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Connection", "close")
    handler.end_headers()

    with zipfile.ZipFile(handler.wfile, mode="w",
                         compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for fp, arcname in files:
            fd = None
            try:
                fd = routes.open_anchored_fd(root_r, fp.resolve(), want_dir=False)
                info = zipfile.ZipInfo(arcname)
                info.compress_type = zipfile.ZIP_DEFLATED
                with os.fdopen(fd, "rb", closefd=True) as src:
                    fd = None
                    with zf.open(info, "w") as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
            except (ValueError, OSError, PermissionError):
                pass
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
    return True


def handle_download(handler, parsed):
    """GET /api/acervo/x/download — export an acervo file or artifact zip."""
    import api.routes as routes
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    if not routes._resolve_session_workspace(sid):
        return routes.bad(handler, "Session not found", 404)
    art_id = (qs.get("artifact_id", [""])[0] or "").strip().strip("/")
    rel = (qs.get("path", [""])[0] or "").strip()
    if art_id and rel:
        return routes.bad(handler, "pass either path or artifact_id, not both")
    if art_id:
        return _download_artifact_zip(handler, routes, art_id)
    return _download_file(handler, routes, rel)


# region: dispatchers (delegation targets of the MOD-009 fallbacks)

def handle_studio_get(handler, parsed):
    """Route Studio GET sub-paths under /api/acervo/x/ (delegated by MOD-009)."""
    import api.routes as routes
    if parsed.path == "/api/acervo/x/download":
        return handle_download(handler, parsed)
    return routes.bad(handler, "unknown acervo explorer endpoint", 404)


def handle_studio_post(handler, body):
    """Route Studio POST sub-paths (none in Phase 1; Phase 2 adds intake/*)."""
    import api.routes as routes
    return routes.bad(handler, "unknown acervo explorer endpoint", 404)
```

- [ ] **Step 4: Wire the delegation fallbacks in `api/acervo_explorer.py`**

In `handle_acervo_x_get`, replace the final line:

```python
    return routes.bad(handler, "unknown acervo explorer endpoint", 404)
```

with:

```python
    # MOD-010: delegate Studio-only sub-paths (x/download now; intake/publish/
    # assist in later phases) before 404ing. Late import avoids a load cycle.
    import api.acervo_studio as studio
    return studio.handle_studio_get(handler, parsed)
```

In `handle_acervo_x_post`, replace the final line:

```python
    return routes.bad(handler, "unknown acervo explorer endpoint", 404)
```

with:

```python
    import api.acervo_studio as studio
    return studio.handle_studio_post(handler, body)
```

- [ ] **Step 5: Add the `kind` field to artifact tree nodes**

In `handle_tree`'s `scope == "artifacts"` branch in `api/acervo_explorer.py`, replace:

```python
                nodes.append({
                    "type": "artifact",
                    "rel_path": _rel_to_root(child, root),
                    "name": child.name,
                    "title": routes._humanize_slug(child.stem if child.is_file() else child.name),
                })
```

with:

```python
                nodes.append({
                    "type": "artifact",
                    "rel_path": _rel_to_root(child, root),
                    "name": child.name,
                    "kind": "dir" if child.is_dir() else "file",
                    "title": routes._humanize_slug(child.stem if child.is_file() else child.name),
                })
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_mod010_acervo_studio.py -q`
Expected: 21 passed (7 Phase-0 + 14 new: 1+4+1+1+1+4+1+1+1+... — pytest will report the exact param expansion; all green, zero failures).

Also: `python -c "import ast; ast.parse(open('api/acervo_studio.py').read()); ast.parse(open('api/acervo_explorer.py').read())"`
Expected: no syntax error.

- [ ] **Step 7: Commit**

```bash
git add api/acervo_studio.py api/acervo_explorer.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): x/download endpoint in new api/acervo_studio.py + dispatcher delegation (MOD-010 Phase 1)"
```

---

### Task 2: Backend — Phase-0 Minors: `_micro_title` harmonization + `handle_tree` HTTP-dispatch test

**Files:**
- Modify: `api/acervo_explorer.py` (add `_micro_title`; use it in `_micro_nodes`)
- Test: `tests/test_mod010_acervo_studio.py` (extend)

**Interfaces:**
- Produces: `_micro_title(routes, d: Path) -> str` — friendly microverse title harmonized with MOD-008 `_handle_acervo_microverses`: `_meta/index.md` frontmatter `title` → `microverso.yaml` `name` → humanized slug, stripping the `Índice —`/`Index —` markers index pages carry.
- Consumes: `routes._read_frontmatter_meta`, `routes._humanize_slug` (both parse bare-YAML heads too — verified: `_read_frontmatter_meta` falls back to the file head when there is no `---` block).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mod010_acervo_studio.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_mod010_acervo_studio.py -q -k "micro_title or http_dispatch"`
Expected: `test_micro_title_strips_indice_marker` and `test_micro_title_falls_back_to_microverso_yaml` FAIL (current algorithm has no marker-strip and no yaml fallback); the other two pass or fail depending on order — the two named failures are the signal.

- [ ] **Step 3: Add `_micro_title` and use it in `_micro_nodes`**

In `api/acervo_explorer.py`, immediately **before** `def _micro_nodes(...)`, insert:

```python
def _micro_title(routes, d):
    """Friendly microverse title, harmonized with MOD-008's
    _handle_acervo_microverses: _meta/index.md ``title`` → microverso.yaml
    ``name`` → humanized slug; strips the "Índice —"/"Index —" markers index
    pages carry (Phase-0 minor: the two surfaces disagreed)."""
    name = None
    idx = d / "_meta" / "index.md"
    if idx.is_file():
        name = routes._read_frontmatter_meta(idx, ["title"]).get("title")
    if not name:
        yml = d / "microverso.yaml"
        if yml.is_file():
            name = routes._read_frontmatter_meta(yml, ["name"]).get("name")
    if name:
        name = re.sub(r'^(?:índice|indice|index)\s*[—\-:]\s*', '', name,
                      flags=re.IGNORECASE)
        name = re.sub(r'\s*[—\-:]\s*(?:índice|indice|index)$', '', name,
                      flags=re.IGNORECASE)
        name = name.strip()
        if not name or name == d.name:
            name = None
    return name or routes._humanize_slug(d.name)
```

Then in `_micro_nodes`, replace:

```python
            title = (routes._read_frontmatter_title(d / "_meta" / "index.md")
                     or routes._humanize_slug(d.name))
```

with:

```python
            title = _micro_title(routes, d)
```

- [ ] **Step 4: Run the full test file**

Run: `python -m pytest tests/test_mod010_acervo_studio.py -q`
Expected: all pass (25 items), zero failures.

- [ ] **Step 5: Commit**

```bash
git add api/acervo_explorer.py tests/test_mod010_acervo_studio.py
git commit -m "fix(acervo-studio): harmonize microverse titles with MOD-008 + tree dispatch test (MOD-010 Phase 1, deferred minors)"
```

---

### Task 3: Frontend — reader toolbar: stage-to-chat + download + artifact card

**Files:**
- Modify: `static/acervo-studio.js`
- Modify: `static/acervo-studio.css`

**Interfaces:**
- Consumes: `POST /api/acervo/x/stage {session_id, source}` → `{name,path,mime,size,is_image}`; `GET /api/acervo/x/download` (Task 1); `S.pendingContextAttachments` + `renderStagedContextChips()` (MOD-007/008 bridge); artifact nodes' `kind` (Task 1).
- Produces: toolbar renderer `_actionsBar(p)` + wiring `_wireActs(reader)` (Tasks 4–5 extend both); `window.acervoStudioStage()`, `window.acervoStudioDownload()`; helpers `_detail(e)`, `_confirmDiscard()`, `_downloadUrl(qs)`, `_triggerDownload(url)`, `_openArtifact(id, title)`. State keys `AXS.page`, `AXS.editing`, `AXS.dirty`, `AXS.artifactId`. Also fixes two Phase-0 minors in the non-md branch (client-built encoded raw URL; iframe `title`).

- [ ] **Step 1: Extend the module state and fix the `_toast` signature**

In `static/acervo-studio.js`, replace:

```javascript
  var AXS = { built: false, open: false, scope: 'micro', slug: '', selectedPath: '' };
```

with:

```javascript
  var AXS = { built: false, open: false, scope: 'micro', slug: '', selectedPath: '',
    page: null, editing: false, dirty: false, artifactId: '' };
```

Replace:

```javascript
  function _toast(m, t) { if (typeof showToast === 'function') showToast(m, t); }
```

with (the app global is `showToast(msg, ms, type)` — the Phase-0 helper passed `type` into the `ms` slot; it had no call sites, so this is safe):

```javascript
  function _toast(m, type) { if (typeof showToast === 'function') showToast(m, 3000, type || ''); }
```

- [ ] **Step 2: Add the toolbar/bridge helpers**

In `static/acervo-studio.js`, immediately **after** the `_chip` function line, insert:

```javascript
  function _detail(e) {
    var m = e && e.message ? String(e.message) : '';
    return m ? ' — ' + m : '';
  }

  async function _confirmDiscard() {
    if (typeof showConfirmDialog === 'function') {
      return await showConfirmDialog({
        title: 'Descartar alterações?',
        message: 'Há edições não salvas nesta página.',
        confirmLabel: 'Descartar',
        danger: true
      });
    }
    return true;
  }

  function _actionsBar(p) {
    var acts = '';
    acts += '<button type="button" class="axs-act" data-axs-act="stage">⇪ Enviar ao chat</button>';
    acts += '<button type="button" class="axs-act" data-axs-act="download">⬇ Baixar</button>';
    return '<div class="axs-acts">' + acts + '</div>';
  }

  function _wireActs(reader) {
    reader.querySelectorAll('[data-axs-act]').forEach(function (b) {
      b.addEventListener('click', function () {
        var act = b.getAttribute('data-axs-act');
        if (act === 'stage') acervoStudioStage();
        else if (act === 'download') acervoStudioDownload();
      });
    });
  }

  function _downloadUrl(qs) {
    return '/api/acervo/x/download?session_id=' + encodeURIComponent(_sid()) + '&' + qs;
  }

  function _triggerDownload(url) {
    var a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function acervoStudioDownload() {
    if (AXS.artifactId) {
      _triggerDownload(_downloadUrl('artifact_id=' + encodeURIComponent(AXS.artifactId)));
      return;
    }
    if (!AXS.selectedPath) return;
    _triggerDownload(_downloadUrl('path=' + encodeURIComponent(AXS.selectedPath)));
  }
  window.acervoStudioDownload = acervoStudioDownload;

  async function acervoStudioStage() {
    var relPath = AXS.selectedPath;
    if (!relPath) { _toast('Abra uma página primeiro', 'error'); return; }
    var r;
    try {
      r = await api('/api/acervo/x/stage', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), source: relPath })
      });
    } catch (e) {
      _toast('Falha ao adicionar ao contexto' + _detail(e), 'error');
      return;
    }
    if (r && r.path) {
      if (typeof S !== 'undefined' && S) {
        if (!Array.isArray(S.pendingContextAttachments)) S.pendingContextAttachments = [];
        if (!S.pendingContextAttachments.some(function (a) { return a._ctxSource === relPath; })) {
          S.pendingContextAttachments.push({
            name: r.name, path: r.path, mime: r.mime, size: r.size,
            is_image: !!r.is_image, _ctxSource: relPath
          });
        }
      }
      if (typeof renderStagedContextChips === 'function') renderStagedContextChips();
      _toast('Adicionado ao contexto da próxima mensagem', 'success');
    }
  }
  window.acervoStudioStage = acervoStudioStage;

  function _openArtifact(id, title) {
    var root = _root();
    if (!root) return;
    AXS.selectedPath = '';
    AXS.page = null;
    AXS.artifactId = id;
    var reader = root.querySelector('[data-axs="reader"]');
    reader.innerHTML =
      '<div class="axs-crumb"><b>_artifacts</b> › ' + _esc(id) +
      '  <div class="axs-acts"><button type="button" class="axs-act" data-axs-act="download">⬇ Baixar (zip)</button></div></div>' +
      '<div class="axs-doc">' +
      '  <h1 class="axs-title">📦 ' + _esc(title || id) + '</h1>' +
      '  <div class="axs-empty">Pacote de artefato — o download inclui manifest.json, source/ e exports/.</div>' +
      '</div>';
    _wireActs(reader);
  }
```

- [ ] **Step 3: Replace `acervoStudioOpenPage` (toolbar + state + raw-URL/iframe minors)**

Replace the **entire** `acervoStudioOpenPage` function body (from `async function acervoStudioOpenPage(relPath) {` up to — but not including — the `window.acervoStudioOpenPage = acervoStudioOpenPage;` line) with:

```javascript
  async function acervoStudioOpenPage(relPath) {
    var root = _root();
    if (!root) return;
    if (AXS.dirty && !(await _confirmDiscard())) return;
    AXS.dirty = false;
    AXS.editing = false;
    AXS.selectedPath = relPath;
    AXS.artifactId = '';
    var reader = root.querySelector('[data-axs="reader"]');
    // Mark the active page in the nav — runs for both md and non-md branches.
    var nav = root.querySelector('[data-axs="nav"]');
    if (nav) {
      nav.querySelectorAll('.axs-pi').forEach(function (el) {
        el.classList.toggle('on', el.getAttribute('data-path') === relPath);
      });
    }
    reader.innerHTML = '<div class="axs-reader-empty">Carregando…</div>';
    var p;
    try {
      p = await api('/api/acervo/x/page?session_id=' + encodeURIComponent(_sid()) +
        '&path=' + encodeURIComponent(relPath));
    } catch (e) {
      reader.innerHTML = '<div class="axs-reader-empty">Erro ao abrir a página.</div>';
      return;
    }
    var crumb = relPath.split('/').map(function (s, i, a) {
      return i === a.length - 1 ? _esc(s) : '<b>' + _esc(s) + '</b>';
    }).join(' › ');
    if (p && p.editable === false) {
      AXS.page = null;
      // Phase-0 minor fixed: build the raw URL client-side, fully encoded
      // (p.raw_url already embeds session_id unencoded — don't reuse/append).
      var rawUrl = '/api/acervo/x/raw?session_id=' + encodeURIComponent(_sid()) +
        '&path=' + encodeURIComponent(relPath);
      var isImg = (p.mime || '').indexOf('image/') === 0;
      var view = isImg
        ? '<img class="axs-raw" src="' + _esc(rawUrl) + '" alt="' + _esc(relPath) + '">'
        : '<iframe class="axs-raw" src="' + _esc(rawUrl) + '" sandbox title="' + _esc(relPath) + '"></iframe>';
      reader.innerHTML = '<div class="axs-crumb">' + crumb + _actionsBar(p) + '</div>' +
        '<div class="axs-doc">' + view + '</div>';
      _wireActs(reader);
      return;
    }
    AXS.page = p;
    var fm = (p && p.frontmatter) || {};
    var chips = '';
    if (fm.nature) chips += _chip(fm.nature);
    if (fm['class']) {
      var _isPerene = String(fm['class']).toLowerCase().indexOf('peren') === 0;
      chips += _chip((_isPerene ? '🔒 ' : '') + fm['class'], _isPerene ? 'perene' : '');
    }
    if (fm.status) chips += _chip('✓ ' + fm.status);
    (Array.isArray(fm.tags) ? fm.tags : []).forEach(function (t) { chips += _chip('#' + t); });
    var title = p.title || relPath;
    var body = _stripDupTitleH1(p.body || '', title);
    var bodyHtml = (typeof renderMd === 'function') ? renderMd(body) : _esc(body);
    reader.innerHTML =
      '<div class="axs-crumb">' + crumb + _actionsBar(p) + '</div>' +
      '<div class="axs-doc">' +
      '  <div class="axs-fm">' + chips + '</div>' +
      '  <h1 class="axs-title">' + _esc(title) + '</h1>' +
      '  <div class="axs-md">' + bodyHtml + '</div>' +
      '</div>';
    _wireActs(reader);
  }
```

- [ ] **Step 4: Make artifact nodes clickable in the navigator**

In `acervoStudioSelectScope`, replace the artifact branch:

```javascript
      } else if (n.type === 'artifact') {
        out += '<div class="axs-pi">📦 ' + _esc(n.title || n.name) + '</div>';
      }
```

with:

```javascript
      } else if (n.type === 'artifact') {
        out += '<div class="axs-pi" data-art="' + _esc(n.name) +
          '" data-artkind="' + _esc(n.kind || '') +
          '" data-artpath="' + _esc(n.rel_path) +
          '" data-arttitle="' + _esc(n.title || n.name) + '">📦 ' +
          _esc(n.title || n.name) + '</div>';
      }
```

Then, immediately **after** the `sub.querySelectorAll('[data-path]')…` wiring block inside the same function, insert:

```javascript
    sub.querySelectorAll('[data-art]').forEach(function (el) {
      el.addEventListener('click', function () {
        if (el.getAttribute('data-artkind') === 'dir') {
          _openArtifact(el.getAttribute('data-art'), el.getAttribute('data-arttitle'));
        } else if (typeof acervoStudioOpenPage === 'function') {
          acervoStudioOpenPage(el.getAttribute('data-artpath'));
        }
      });
    });
```

- [ ] **Step 5: Add the toolbar CSS**

Append to `static/acervo-studio.css`:

```css
.axs-acts{margin-left:auto;display:flex;gap:6px;align-items:center;}
.axs-act{background:var(--axs-surf);border:1px solid var(--axs-bd2);border-radius:7px;
  padding:4px 9px;color:var(--axs-ink);cursor:pointer;font:600 11px/1 var(--axs-sans);
  white-space:nowrap;}
.axs-act:hover{border-color:var(--axs-acct);color:var(--axs-strong);}
.axs-act-primary{background:var(--axs-acc);border-color:var(--axs-acc);color:#fff;}
.axs-act-primary:hover{color:#fff;filter:brightness(1.08);}
```

- [ ] **Step 6: Lint + syntax-check**

Run: `node --check static/acervo-studio.js && npm run lint:runtime`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add static/acervo-studio.js static/acervo-studio.css
git commit -m "feat(acervo-studio): reader toolbar with stage-to-chat + download; clickable artifacts (MOD-010 Phase 1)"
```

---

### Task 4: Frontend — inline editor (save via MOD-009 `x/save`, dirty guard, perene confirm)

**Files:**
- Modify: `static/acervo-studio.js`
- Modify: `static/acervo-studio.css`

**Interfaces:**
- Consumes: `POST /api/acervo/x/save {session_id, path, frontmatter, body}` (OKF-preserving merge; `status` gated to draft/ready/archived); `AXS.page` (Task 3); `showConfirmDialog`.
- Produces: `window.acervoStudioEdit()`, `window.acervoStudioSave()`; constants `AXS_STATUSES`, `AXS_NATURES`; dirty guard on close + `beforeunload`. `_actionsBar`/`_wireActs` replaced to include the ✎ Editar button.

- [ ] **Step 1: Add the editor constants**

In `static/acervo-studio.js`, immediately **after** the `var SCOPES = [...]` block, insert (mirrors `routes._ACERVO_NATURES` and `routes._ACERVO_UI_STATUSES`):

```javascript
  var AXS_STATUSES = ['draft', 'ready', 'archived'];
  var AXS_NATURES = ['context', 'knowledge', 'contracts', 'workflows', 'decisions',
    'templates', 'tools', 'skills', 'persona', 'prompts', 'reflections'];
```

- [ ] **Step 2: Extend the toolbar with ✎ Editar**

Replace the **entire** `_actionsBar` function (from Task 3) with:

```javascript
  function _actionsBar(p) {
    var md = !!(p && p.editable);
    var acts = '';
    if (md) acts += '<button type="button" class="axs-act" data-axs-act="edit">✎ Editar</button>';
    acts += '<button type="button" class="axs-act" data-axs-act="stage">⇪ Enviar ao chat</button>';
    acts += '<button type="button" class="axs-act" data-axs-act="download">⬇ Baixar</button>';
    return '<div class="axs-acts">' + acts + '</div>';
  }
```

Replace the **entire** `_wireActs` function (from Task 3) with:

```javascript
  function _wireActs(reader) {
    reader.querySelectorAll('[data-axs-act]').forEach(function (b) {
      b.addEventListener('click', function () {
        var act = b.getAttribute('data-axs-act');
        if (act === 'edit') acervoStudioEdit();
        else if (act === 'stage') acervoStudioStage();
        else if (act === 'download') acervoStudioDownload();
      });
    });
  }
```

- [ ] **Step 3: Add the editor + save**

Immediately **after** the `_openArtifact` function (Task 3), insert:

```javascript
  function acervoStudioEdit() {
    var p = AXS.page;
    var root = _root();
    if (!p || !p.editable || !root) return;
    AXS.editing = true;
    var reader = root.querySelector('[data-axs="reader"]');
    var fm = p.frontmatter || {};
    var tagsCsv = Array.isArray(fm.tags) ? fm.tags.join(', ') : (fm.tags || '');
    var stSel = AXS_STATUSES.map(function (s) {
      return '<option value="' + s + '"' +
        ((fm.status || 'draft') === s ? ' selected' : '') + '>' + s + '</option>';
    }).join('');
    var natSel = '<option value="">—</option>' + AXS_NATURES.map(function (n) {
      return '<option value="' + n + '"' +
        ((fm.nature || '') === n ? ' selected' : '') + '>' + n + '</option>';
    }).join('');
    var perene = String(fm['class'] || '').toLowerCase().indexOf('peren') === 0;
    reader.innerHTML =
      '<div class="axs-crumb">✎ ' + _esc(p.rel_path) +
      '  <div class="axs-acts">' +
      '    <button type="button" class="axs-act axs-act-primary" data-axs-ed="save">Salvar</button>' +
      '    <button type="button" class="axs-act" data-axs-ed="cancel">Cancelar</button>' +
      '  </div></div>' +
      '<div class="axs-doc axs-editor">' +
      (perene ? '<div class="axs-warn">⚠ Página perene (class: perene) — edite com cuidado.</div>' : '') +
      '  <label class="axs-field"><span>Título</span>' +
      '    <input type="text" data-axs-fm="title" value="' + _esc(fm.title || '') + '"></label>' +
      '  <div class="axs-frow">' +
      '    <label class="axs-field"><span>Status</span><select data-axs-fm="status">' + stSel + '</select></label>' +
      '    <label class="axs-field"><span>Natureza</span><select data-axs-fm="nature">' + natSel + '</select></label>' +
      '  </div>' +
      '  <label class="axs-field"><span>Tags (CSV)</span>' +
      '    <input type="text" data-axs-fm="tags" value="' + _esc(tagsCsv) + '" placeholder="a, b, c"></label>' +
      '  <label class="axs-field axs-fgrow"><span>Conteúdo</span>' +
      '    <textarea data-axs-ed="body" spellcheck="false">' + _esc(p.body || '') + '</textarea></label>' +
      '</div>';
    var mark = function () { AXS.dirty = true; };
    reader.querySelectorAll('[data-axs-fm],[data-axs-ed="body"]').forEach(function (el) {
      el.addEventListener('input', mark);
      el.addEventListener('change', mark);
    });
    reader.querySelector('[data-axs-ed="save"]').addEventListener('click', acervoStudioSave);
    reader.querySelector('[data-axs-ed="cancel"]').addEventListener('click', async function () {
      if (AXS.dirty && !(await _confirmDiscard())) return;
      AXS.dirty = false;
      AXS.editing = false;
      acervoStudioOpenPage(p.rel_path);
    });
  }
  window.acervoStudioEdit = acervoStudioEdit;

  async function acervoStudioSave() {
    var p = AXS.page;
    var root = _root();
    if (!p || !root) return;
    var reader = root.querySelector('[data-axs="reader"]');
    var fm = {};
    reader.querySelectorAll('[data-axs-fm]').forEach(function (el) {
      var k = el.getAttribute('data-axs-fm');
      var v = el.value;
      if (k === 'tags') {
        fm.tags = String(v).split(',').map(function (t) { return t.trim(); }).filter(Boolean);
      } else if (v !== '') {
        fm[k] = v;
      }
    });
    var bodyEl = reader.querySelector('[data-axs-ed="body"]');
    var body = bodyEl ? bodyEl.value : (p.body || '');
    var isPerene = p.frontmatter &&
      String(p.frontmatter['class'] || '').toLowerCase().indexOf('peren') === 0;
    if (isPerene && typeof showConfirmDialog === 'function') {
      var ok = await showConfirmDialog({
        title: 'Página perene',
        message: 'Esta página é marcada como perene. Salvar mesmo assim?',
        confirmLabel: 'Salvar'
      });
      if (!ok) return;
    }
    try {
      await api('/api/acervo/x/save', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), path: p.rel_path, frontmatter: fm, body: body })
      });
    } catch (e) {
      _toast('Falha ao salvar' + _detail(e), 'error');
      return; // keep the editor open on error
    }
    AXS.dirty = false;
    AXS.editing = false;
    _toast('Página salva', 'success');
    await acervoStudioOpenPage(p.rel_path);   // reload from disk (merged frontmatter)
    acervoStudioSelectScope(AXS.scope, AXS.slug);  // refresh titles/status dots
  }
  window.acervoStudioSave = acervoStudioSave;
```

- [ ] **Step 4: Dirty-guard the Chat toggle and the tab close**

Replace the **entire** `_close` function with:

```javascript
  async function _close() {
    if (AXS.dirty && !(await _confirmDiscard())) return;
    AXS.dirty = false;
    AXS.editing = false;
    var root = _root();
    if (root) root.hidden = true;
    AXS.open = false;
    _showLauncher(true);
  }
```

Then, immediately **before** the `if (document.readyState === 'loading') {` block at the bottom of the IIFE, insert:

```javascript
  window.addEventListener('beforeunload', function (e) {
    if (AXS.open && AXS.dirty) { e.preventDefault(); e.returnValue = ''; return ''; }
  });
```

- [ ] **Step 5: Add the editor CSS**

Append to `static/acervo-studio.css`:

```css
.axs-warn{background:var(--axs-accbg);border:1px solid var(--axs-accbd);color:var(--axs-acct);
  border-radius:8px;padding:8px 11px;font:600 11.5px/1.4 var(--axs-sans);margin-bottom:12px;}
.axs-editor{display:flex;flex-direction:column;gap:10px;}
.axs-field{display:flex;flex-direction:column;gap:4px;font:600 10.5px/1 var(--axs-sans);
  color:var(--axs-mut);}
.axs-field input,.axs-field select,.axs-field textarea{background:var(--axs-surf);
  border:1px solid var(--axs-bd2);border-radius:7px;padding:7px 9px;color:var(--axs-ink);
  font:400 12.5px/1.4 var(--axs-sans);outline:none;}
.axs-field input:focus,.axs-field select:focus,.axs-field textarea:focus{border-color:var(--axs-acc);}
.axs-field textarea{font-family:var(--axs-mono);min-height:46vh;line-height:1.55;resize:vertical;}
.axs-frow{display:flex;gap:10px;}
.axs-frow .axs-field{flex:1;}
.axs-fgrow{flex:1;}
```

- [ ] **Step 6: Lint + syntax-check**

Run: `node --check static/acervo-studio.js && npm run lint:runtime`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add static/acervo-studio.js static/acervo-studio.css
git commit -m "feat(acervo-studio): inline editor with OKF-preserving save, dirty guard, perene confirm (MOD-010 Phase 1)"
```

---

### Task 5: Frontend — ⋯ menu: move/rename + status

**Files:**
- Modify: `static/acervo-studio.js`
- Modify: `static/acervo-studio.css`

**Interfaces:**
- Consumes: `POST /api/acervo/x/move {session_id, path, dest}` (409 if dest exists); `POST /api/acervo/x/status {session_id, path, status}`; `showPromptDialog`; `AXS_STATUSES` (Task 4).
- Produces: `window.acervoStudioMove()`, `window.acervoStudioSetStatus(status)`; `_toggleMenu(anchor)`. `_actionsBar`/`_wireActs` replaced to include the ⋯ button (md pages only).

- [ ] **Step 1: Extend the toolbar with ⋯**

Replace the **entire** `_actionsBar` function (from Task 4) with:

```javascript
  function _actionsBar(p) {
    var md = !!(p && p.editable);
    var acts = '';
    if (md) acts += '<button type="button" class="axs-act" data-axs-act="edit">✎ Editar</button>';
    acts += '<button type="button" class="axs-act" data-axs-act="stage">⇪ Enviar ao chat</button>';
    acts += '<button type="button" class="axs-act" data-axs-act="download">⬇ Baixar</button>';
    if (md) acts += '<button type="button" class="axs-act" data-axs-act="more" ' +
      'aria-haspopup="true" aria-label="Mais ações">⋯</button>';
    return '<div class="axs-acts">' + acts + '</div>';
  }
```

Replace the **entire** `_wireActs` function (from Task 4) with:

```javascript
  function _wireActs(reader) {
    reader.querySelectorAll('[data-axs-act]').forEach(function (b) {
      b.addEventListener('click', function () {
        var act = b.getAttribute('data-axs-act');
        if (act === 'edit') acervoStudioEdit();
        else if (act === 'stage') acervoStudioStage();
        else if (act === 'download') acervoStudioDownload();
        else if (act === 'more') _toggleMenu(b);
      });
    });
  }
```

- [ ] **Step 2: Add the menu + move + status**

Immediately **after** the `acervoStudioSave` function (Task 4), insert:

```javascript
  function _toggleMenu(anchor) {
    var old = document.getElementById('axsMenu');
    if (old) { old.remove(); return; }
    var m = document.createElement('div');
    m.id = 'axsMenu';
    m.className = 'axs-menu';
    m.innerHTML =
      '<button type="button" data-axs-m="move">Mover / renomear…</button>' +
      '<div class="axs-menu-sep"></div>' +
      AXS_STATUSES.map(function (s) {
        return '<button type="button" data-axs-m="st:' + s + '">Status: ' + s + '</button>';
      }).join('');
    document.body.appendChild(m);
    var r = anchor.getBoundingClientRect();
    m.style.top = (r.bottom + 4) + 'px';
    m.style.right = Math.max(8, window.innerWidth - r.right) + 'px';
    m.querySelectorAll('[data-axs-m]').forEach(function (b) {
      b.addEventListener('click', function () {
        m.remove();
        var v = b.getAttribute('data-axs-m');
        if (v === 'move') acervoStudioMove();
        else if (v.indexOf('st:') === 0) acervoStudioSetStatus(v.slice(3));
      });
    });
    setTimeout(function () {
      document.addEventListener('click', function h(ev) {
        if (!m.contains(ev.target)) {
          m.remove();
          document.removeEventListener('click', h);
        }
      });
    }, 0);
  }

  async function acervoStudioMove() {
    var p = AXS.page;
    if (!p || !p.rel_path) return;
    var dest = (typeof showPromptDialog === 'function')
      ? await showPromptDialog({
        title: 'Mover / renomear',
        message: 'Novo caminho (relativo ao acervo):',
        defaultValue: p.rel_path,
        confirmLabel: 'Mover'
      }) : null;
    if (dest == null) return;
    dest = String(dest).trim();
    if (!dest || dest === p.rel_path) return;
    var r;
    try {
      r = await api('/api/acervo/x/move', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), path: p.rel_path, dest: dest })
      });
    } catch (e) {
      _toast('Falha ao mover' + _detail(e), 'error');
      return;
    }
    _toast('Movido', 'success');
    var newRel = (r && r.rel_path) || dest;
    await acervoStudioOpenPage(newRel);
    acervoStudioSelectScope(AXS.scope, AXS.slug);
  }
  window.acervoStudioMove = acervoStudioMove;

  async function acervoStudioSetStatus(status) {
    var p = AXS.page;
    if (!p || !p.rel_path) return;
    try {
      await api('/api/acervo/x/status', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), path: p.rel_path, status: status })
      });
    } catch (e) {
      _toast('Falha ao atualizar status' + _detail(e), 'error');
      return;
    }
    _toast('Status atualizado', 'success');
    await acervoStudioOpenPage(p.rel_path);
    acervoStudioSelectScope(AXS.scope, AXS.slug);
  }
  window.acervoStudioSetStatus = acervoStudioSetStatus;
```

- [ ] **Step 3: Add the menu CSS**

Append to `static/acervo-studio.css`:

```css
.axs-menu{position:fixed;z-index:1300;background:var(--axs-surf);border:1px solid var(--axs-bd2);
  border-radius:9px;padding:4px;box-shadow:0 10px 26px -8px rgba(0,0,0,.45);
  display:flex;flex-direction:column;min-width:190px;}
.axs-menu button{background:none;border:none;border-radius:6px;padding:7px 10px;
  text-align:left;color:var(--axs-ink);cursor:pointer;font:500 12px/1 var(--axs-sans);}
.axs-menu button:hover{background:var(--axs-surf2);color:var(--axs-strong);}
.axs-menu-sep{height:1px;background:var(--axs-line);margin:4px 2px;}
```

- [ ] **Step 4: Lint + syntax-check**

Run: `node --check static/acervo-studio.js && npm run lint:runtime`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add static/acervo-studio.js static/acervo-studio.css
git commit -m "feat(acervo-studio): move/rename + page status via kebab menu (MOD-010 Phase 1)"
```

---

### Task 6: Frontend — remaining Phase-0 Minors (guards, badge fetch, `.axs-sub`)

**Files:**
- Modify: `static/acervo-studio.js`
- Modify: `static/acervo-studio.css`

**Interfaces:**
- Produces: hardened `acervoStudioRenderNav` (single inbox fetch, passed through), `acervoStudioSelectScope(scope, slug, prefetched?)` (root null-guard + optional prefetched tree), `acervoStudioSearch` (root null-guard + dirty guard + typeof guard). `.axs-sub` styled. No API/behavior change beyond the guards.

- [ ] **Step 1: Replace `acervoStudioRenderNav` (single inbox fetch)**

Replace the **entire** `acervoStudioRenderNav` function with:

```javascript
  async function acervoStudioRenderNav() {
    var root = _root();
    var nav = root && root.querySelector('[data-axs="nav"]');
    if (!nav) return;
    if (!_sid()) { nav.innerHTML = '<div class="axs-empty">Sem sessão ativa.</div>'; return; }
    var html = '<div class="axs-sec">Acervo</div>';
    // Inbox count badge (best-effort). Fetched ONCE and passed through to
    // acervoStudioSelectScope when inbox is the active scope (Phase-0 minor:
    // the same tree was fetched twice).
    var inboxData = null;
    try { inboxData = await _tree('inbox', ''); } catch (e) { /* badge only */ }
    var inboxCount = (inboxData && inboxData.count) || 0;
    SCOPES.forEach(function (s) {
      var on = AXS.scope === s.key ? ' on' : '';
      var badge = (s.key === 'inbox' && inboxCount) ?
        '<span class="ct">' + inboxCount + '</span>' : '';
      html += '<div class="axs-ni' + on + '" data-scope="' + s.key + '">' +
        '<span class="ico">' + s.ico + '</span>' + _esc(s.label) + badge + '</div>' +
        '<div class="axs-sub" data-sub="' + s.key + '"></div>';
    });
    nav.innerHTML = html;
    nav.querySelectorAll('.axs-ni').forEach(function (el) {
      el.addEventListener('click', function () {
        acervoStudioSelectScope(el.getAttribute('data-scope'), '');
      });
    });
    if (AXS.scope) {
      acervoStudioSelectScope(AXS.scope, AXS.slug,
        AXS.scope === 'inbox' && !AXS.slug ? inboxData : null);
    }
  }
```

- [ ] **Step 2: Replace the head of `acervoStudioSelectScope` (null-guard + prefetch param)**

Replace the function signature and first lines:

```javascript
  async function acervoStudioSelectScope(scope, slug) {
    AXS.scope = scope; AXS.slug = slug || '';
    var nav = _root().querySelector('[data-axs="nav"]');
```

with:

```javascript
  async function acervoStudioSelectScope(scope, slug, prefetched) {
    var root = _root();
    if (!root) return;
    AXS.scope = scope; AXS.slug = slug || '';
    var nav = root.querySelector('[data-axs="nav"]');
    if (!nav) return;
```

Then, in the same function, replace:

```javascript
    try { data = await _tree(scope, slug); }
```

with:

```javascript
    try { data = prefetched || await _tree(scope, slug); }
```

- [ ] **Step 3: Replace the head of `acervoStudioSearch` (guards)**

Replace:

```javascript
  async function acervoStudioSearch(q) {
    q = (q || '').trim();
    var reader = _root().querySelector('[data-axs="reader"]');
```

with:

```javascript
  async function acervoStudioSearch(q) {
    var root = _root();
    if (!root) return;
    if (AXS.dirty && !(await _confirmDiscard())) return;
    AXS.dirty = false;
    AXS.editing = false;
    q = (q || '').trim();
    var reader = root.querySelector('[data-axs="reader"]');
```

Then, in the same function's result-click wiring, replace:

```javascript
      el.addEventListener('click', function () { acervoStudioOpenPage(el.getAttribute('data-path')); });
```

with:

```javascript
      el.addEventListener('click', function () {
        if (typeof acervoStudioOpenPage === 'function')
          acervoStudioOpenPage(el.getAttribute('data-path'));
      });
```

- [ ] **Step 4: Style `.axs-sub`**

Append to `static/acervo-studio.css`:

```css
.axs-sub{margin:1px 0 3px;}
.axs-sub:empty{display:none;}
```

- [ ] **Step 5: Lint + syntax-check**

Run: `node --check static/acervo-studio.js && npm run lint:runtime`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add static/acervo-studio.js static/acervo-studio.css
git commit -m "fix(acervo-studio): null-guards, single inbox fetch, .axs-sub styling (MOD-010 Phase 1, deferred minors)"
```

---

### Task 7: Consolidated live E2E + lint + full-suite regression

**Files:** none (verification only; fixes go back through the relevant task's files).

**Interfaces:** none.

- [ ] **Step 1: Build a THROWAWAY fixture acervo (E2E now writes — never use the real one)**

```bash
E2E_ROOT="$(mktemp -d)"
E2E_ACERVO="$E2E_ROOT/acervo"
mkdir -p "$E2E_ACERVO/global/knowledge" \
         "$E2E_ACERVO/micro/demo/knowledge" "$E2E_ACERVO/micro/demo/_meta" \
         "$E2E_ACERVO/_inbox/incoming/int_20260702_demo" \
         "$E2E_ACERVO/_artifacts/items/art_demo/source" \
         "$E2E_ACERVO/_artifacts/items/art_demo/exports" \
         "$E2E_ACERVO/_artifacts/items/art_demo/receipts"
cat > "$E2E_ACERVO/global/knowledge/editavel.md" <<'EOF'
---
title: Página Editável
status: draft
nature: knowledge
tags: [teste]
updated: 2026-01-01T00:00:00Z
---

Corpo original para o E2E.
EOF
cat > "$E2E_ACERVO/global/knowledge/perene.md" <<'EOF'
---
title: Página Perene
class: perene
status: ready
nature: knowledge
---

Não mexa sem confirmar.
EOF
cat > "$E2E_ACERVO/micro/demo/_meta/index.md" <<'EOF'
---
title: Índice — Demo
---
EOF
cat > "$E2E_ACERVO/micro/demo/knowledge/pagina.md" <<'EOF'
---
title: Página do Demo
status: ready
nature: knowledge
---

Conteúdo micro.
EOF
echo '{}' > "$E2E_ACERVO/_artifacts/items/art_demo/manifest.json"
echo '# a' > "$E2E_ACERVO/_artifacts/items/art_demo/source/a.md"
echo 'x' > "$E2E_ACERVO/_artifacts/items/art_demo/exports/a.txt"
echo '{}' > "$E2E_ACERVO/_artifacts/items/art_demo/receipts/r.json"
echo "Fixture at $E2E_ACERVO"
```

- [ ] **Step 2: Start the isolated server + create a session**

```bash
cd /home/elder/projetos/projetob/hermes-webui
HERMES_HOME="$(mktemp -d)" ACERVO="$E2E_ACERVO" HERMES_WEBUI_PORT=8799 \
  .venv/bin/python server.py --port 8799 &
sleep 2
curl -s -X POST http://localhost:8799/api/session/new | head -c 200   # note the session_id
```

- [ ] **Step 3: API-level smoke of the new endpoint (curl, exact assertions)**

With `SID` set to the created session id:

```bash
curl -s -D- -o /tmp/dl.md "http://localhost:8799/api/acervo/x/download?session_id=$SID&path=global/knowledge/editavel.md" | grep -i 'content-disposition'
# Expected: Content-Disposition: attachment; filename*=…editavel.md…
curl -s -o /tmp/art.zip "http://localhost:8799/api/acervo/x/download?session_id=$SID&artifact_id=art_demo" && python3 -c "import zipfile;print(sorted(zipfile.ZipFile('/tmp/art.zip').namelist()))"
# Expected: ['exports/a.txt', 'manifest.json', 'source/a.md']   (receipts/ excluded)
curl -s "http://localhost:8799/api/acervo/x/download?session_id=$SID&path=../etc/passwd"
# Expected: {"error": "invalid path"} (HTTP 400)
```

- [ ] **Step 4: Browser E2E (headless Chromium / Playwright) — drive every Phase-1 flow**

At `http://localhost:8799`: pick the created conversation in the sidebar (binds `S.session`), click the **▤ Acervo** launcher, then verify:

1. **Toolbar** — open `Global ▸ editavel.md`: toolbar shows ✎ Editar · ⇪ Enviar ao chat · ⬇ Baixar · ⋯.
2. **Edit + save** — Editar → change title to `Página Editada` + append body text → Salvar → toast `Página salva`; reader shows the new title/body; re-open: frontmatter `updated` bumped, `tags` survived (OKF preserved).
3. **Dirty guard** — Editar → type → click another page in the nav → discard dialog appears; Cancel keeps the editor.
4. **Perene confirm** — open `perene.md` → Editar → change body → Salvar → "Página perene" confirm dialog appears before saving.
5. **Status** — ⋯ → `Status: ready` → toast; the ✓ chip and nav dot update.
6. **Move** — ⋯ → Mover / renomear… → dest `global/knowledge/renomeada.md` → page re-opens at the new path; nav updates.
7. **Download** — ⬇ Baixar on the md page triggers a download; on the `art_demo` artifact card, `⬇ Baixar (zip)` downloads the zip.
8. **Stage-to-chat** — ⇪ Enviar ao chat → toast; switch to Chat → the context chip for the page shows in the composer tray.
9. **Non-md + micro title** — Microversos shows `Demo` (not `Índice — Demo`); an inbox envelope lists under Inbox with its badge.
10. **Console** — zero errors from `acervo-studio.js` across all flows.

Fix any failure at the source task before proceeding. Kill the server and `rm -rf "$E2E_ROOT"` when done.

- [ ] **Step 5: Full-suite regression + lint**

```bash
cd /home/elder/projetos/projetob/hermes-webui
node --check static/acervo-studio.js && npm run lint:runtime
python -m pytest -q 2>&1 | tail -5
git diff exocortex/stable --stat -- api/routes.py static/index.html static/style.css static/ui.js static/workspace.js static/acervo-explorer.js
```

Expected: lint clean; pytest shows the baseline (≈9070+ pass; only the documented pre-existing env-sensitive fails — **zero new failures**; the mod010 file now contributes 25 items); the `git diff --stat` prints **nothing** (upstream-owned and MOD-009 frontend files untouched).

- [ ] **Step 6: Commit (only if fixes were applied during E2E)**

```bash
git add -A && git commit -m "fix(acervo-studio): E2E findings (MOD-010 Phase 1)"
```

---

### Task 8: Governance docs (MOD-010 catalog + umbrella COLLAB record + IDENTITY)

**Files:**
- Modify: `EXOCRTX_MODIFICATIONS.md` (extend the MOD-010 entry to Phase 0+1)
- Create: `/home/elder/projetos/projetob/.harness/changes/<TODAY>_collab_hermes-webui-acervo-studio-phase1.md` — *umbrella repo* (use the actual current date)
- Modify: `/home/elder/projetos/projetob/.harness/subprojects/hermes-webui/IDENTITY.md` — *umbrella repo*

**Interfaces:** none (docs + audit trail).

- [ ] **Step 1: Extend the MOD-010 catalog entry**

In `EXOCRTX_MODIFICATIONS.md`, update the `### MOD-010: Acervo Studio (Phase 0 — read-only)` heading to `### MOD-010: Acervo Studio (Phases 0–1 — navegação + edição/download/bridge)` and extend the entry (keep the Portuguese register of the file):

- **Arquivos** — add: `api/acervo_studio.py` (**novo** — endpoint `x/download`; dispatchers-alvo da delegação), delegação de fallback + `_micro_title` + `kind` em `api/acervo_explorer.py` (edit aditivo fork-owned), crescimento de `static/acervo-studio.{js,css}` (toolbar/editor/menu), testes novos em `tests/test_mod010_acervo_studio.py`. **`api/routes.py` — segue 0 linhas; `static/index.html` — 0 linhas novas** (as 3 da Fase 0 cobrem tudo).
- **Tipo** — corrigir a frase da Fase 0: a escrita agora TAMBÉM flui pelo Studio (editor inline → endpoints MOD-009 `x/{save,tags,status,move}` + `x/stage`); **nenhum caminho de escrita novo** foi criado — `x/download` é read-only.
- **Fronteira de escrita** — inalterada (RFC §6.3): editar-existente apenas; sem create/delete; `.quarantine/` inalcançável; perene com confirmação.

- [ ] **Step 2: Write the umbrella COLLAB record**

Create `/home/elder/projetos/projetob/.harness/changes/<TODAY>_collab_hermes-webui-acervo-studio-phase1.md` following `.harness/conventions/CHANGE_LOG_PROTOCOL.md` and mirroring the Phase-0 record (`2026-07-02_collab_hermes-webui-acervo-studio.md`). Content requirements:

- **Why COLLAB:** the Studio surface now *drives* the MOD-009 write endpoints (`/api/acervo/x/{save,tags,status,move,stage}`) against the Exocórtex-governed acervo, and adds one read-only endpoint (`x/download`) to the shared `/api/acervo/x/` contract surface.
- **Surface delta:** `GET x/download` (file attachment / artifact-deliverables zip); additive `kind` on artifact tree nodes; `_micro_title` harmonization. Additive-only → **not breaking**.
- **Boundaries respected:** no create/delete; `.quarantine/` blocked by `_safe_acervo_path`; OKF-preserving merge on save; statuses gated to draft/ready/archived; session-gated; E2E ran against a fixture acervo, never the live one.
- **Branch:** `collab/acervo-studio-p1` in hermes-webui, merged `--no-ff` to `exocortex/stable` (local, not pushed).

- [ ] **Step 3: Update IDENTITY.md**

In `/home/elder/projetos/projetob/.harness/subprojects/hermes-webui/IDENTITY.md`, update the Acervo Studio (MOD-010) line: Phase 0+1 — full-screen surface with unified navigation **plus** inline OKF-preserving editing, download (md/raw/artifact-zip) and stage-to-chat, all through the MOD-009 write surface; still agentless; Phases 2+ (intake/publish/assist) pending the Hermes-invocation spike.

- [ ] **Step 4: Commit (two repos)**

```bash
# hermes-webui
git -C /home/elder/projetos/projetob/hermes-webui add EXOCRTX_MODIFICATIONS.md
git -C /home/elder/projetos/projetob/hermes-webui commit -m "docs(acervo-studio): MOD-010 catalog — Phase 1 (edit/download/bridge)"
# umbrella
git -C /home/elder/projetos/projetob add .harness/changes/ .harness/subprojects/hermes-webui/IDENTITY.md
git -C /home/elder/projetos/projetob commit -m "docs(harness): COLLAB record — acervo-studio MOD-010 Phase 1"
```

---

## Self-Review

**Spec coverage (Phase 1 slice of `docs/rfcs/acervo-studio.md`):**
- §11 Phase 1 "Elevated editor (reuse MOD-009 write surface)" → Task 4 (save) + Task 5 (move/status); tags ride the editor form (`frontmatter.tags` via `x/save` — the dedicated `x/tags` endpoint remains MOD-009-panel-only, no duplication needed). ✓
- §11 "download (md/raw/zip)" → Task 1 (backend `x/download`: file attachment + artifact-deliverables zip, acervo-anchored since `/api/artifact/zip` is workspace-anchored) + Task 3 (UI wiring incl. artifact card). ✓
- §11 "stage-to-chat" / §7 chat bridge → Task 3 (`x/stage` → `S.pendingContextAttachments` → `renderStagedContextChips`, session-contract only, no DOM coupling). ✓
- §6.1 new module `api/acervo_studio.py`, dispatcher delegation, 0 routes.py lines → Task 1. ✓
- §6.3 write boundary (edit-existing only; no create/delete; `.quarantine` unreachable; perene care) → Global Constraints + Task 4 perene confirm + no new write endpoints anywhere. ✓
- §9 dirty editor (`beforeunload` + nav guard), non-md preview stays raw/sandboxed → Tasks 4 + 3. ✓
- §8 coexistence (new files, no upstream-owned edits, `.axs-*` namespaces) → Global Constraints; Task 7 Step 5 asserts the upstream-file diff is empty. ✓
- 8 deferred Phase-0 Minors: micro-title harmonization (T2), handle_tree HTTP-dispatch test (T2), `_root()` null-guards (T3 OpenPage + T6 SelectScope/Search/RenderNav), redundant inbox fetch (T6), `.axs-sub` styling (T6), redundant/unencoded raw session param (T3), iframe `title` (T3), search typeof guard (T6). ✓ (8/8)
- Correctly out of scope: intake/triage/promote (Phase 2, gated on the Hermes-invocation spike), publish (Phase 3), assist (Phase 4), MOD-009 panel retirement (Phase 5).

**Placeholder scan:** none — every code step contains complete content; no "TBD"/"handle errors"/"similar to Task N". ✓

**Type/name consistency:** `AXS.page/editing/dirty/artifactId` set in T3 and consumed in T4–T6; `_actionsBar`/`_wireActs` replaced wholesale in T4 and T5 (no drift); `acervoStudioEdit/Save/Move/SetStatus/Stage/Download` names match between definitions, `_wireActs`, and window exports; backend `handle_studio_get/post` names match the T1 delegation edit and tests; `kind` field name matches T1 backend, T1 test, and T3 nav wiring; `AXS_STATUSES` matches `_ACERVO_UI_STATUSES` and `AXS_NATURES` matches `_ACERVO_NATURES` (verified against routes.py). ✓
