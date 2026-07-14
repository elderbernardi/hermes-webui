# Acervo Studio — Phase 2a (Intake Capture) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user capture inbound material (text, link, or file) into the acervo's
`_inbox/incoming/{id}/` as a normalized IntakeEnvelope, and browse/inspect those
envelopes in the Studio — with **zero agent dependency** (works fully with Hermes offline).

**Architecture:** The server owns the `_inbox` envelope filesystem directly (per the
resolved spike: *input is not memory*, so no agent-mediation and no semantic-write
governance applies to intake capture). New endpoints live under the existing
`/api/acervo/x/` prefix and are dispatched from `api/acervo_studio.py`'s
`handle_studio_get/post` (delegated by the MOD-009 dispatcher) → **zero new `api/routes.py`
lines**. File uploads are **base64-in-JSON** (the server has no multipart parser and the
POST dispatch hands handlers a pre-parsed JSON `body`; this matches the intake SKILL's
"stdlib/local, no new deps" MVP guidance). Frontend is a vanilla IIFE extension of the
existing `.axs-*` Studio (`static/acervo-studio.js`), reusing its `AXS`/`_sid`/`_esc`
plumbing.

**Tech Stack:** Python 3 stdlib (`json`, `base64`, `datetime`, `pathlib`), pytest
(hermetic, `_acervo_root` monkeypatched onto `tmp_path`); vanilla ES5-ish IIFE JS
(`sourceType:"script"`, `npm run lint:runtime`), Playwright for the live E2E pass.

## Global Constraints

- **Scope of THIS plan:** capture + browse only. **NO triage, NO promote, NO agent
  call, NO semantic write.** Envelopes stay in `_inbox/incoming/`. Triage/promote =
  Phase 2b (separate plan; first WRITE-coupling → COLLAB).
- **REBASE-SAFETY:** `api/routes.py` = **0 new lines** (reuse the `/api/acervo/x/`
  prefix dispatch; new routes delegate through `acervo_studio.handle_studio_{get,post}`).
  `static/index.html` = **0 new lines** (`acervo-studio.js/.css` already included).
  NEVER edit `style.css` / `ui.js` / `workspace.js` / `acervo.js` / `acervo-explorer.*`
  except the ONE additive line documented in Task 3 (a scope-list membership, fork-owned).
- **VANILLA ONLY:** IIFE, `'use strict'`, no ES `import`/`export`. Namespaces stay
  `.axs-*` / `acervoStudio*` / `AXS` (never MOD-009's `.ax-*` / `AX` / `acervoExplorer*`).
  Every new global fn `typeof`-guarded at call sites as the existing code does.
- **PATH SAFETY:** every acervo path goes through `acervo_explorer._safe_acervo_path`
  (rejects traversal / symlink-escape / absolute / any dot-prefixed component, keeping
  `.quarantine/` unreachable) **plus** `acervo_studio._resolved_dot_safe(routes, target)`
  for any resolved path. Envelope ids are validated with a strict regex — no `/`, `\`,
  or leading `.`.
- **SESSION-GATED:** every endpoint requires a valid `session_id`
  (`routes._resolve_session_workspace(sid)`), 404/400 on miss — exactly like MOD-009/
  Phase-1 `handle_download`.
- **SIZE CAP:** reject any single captured payload above **25 MiB** decoded
  (`_MAX_INTAKE_BYTES = 25 * 1024 * 1024`) with HTTP 413. The original is always
  written before any derived work.
- **NO `Date.now()`/`Math.random()` in server code paths that tests must be
  deterministic over:** the envelope timestamp uses `datetime.now()` in the handler
  (fine — not under test assertion), but tests inject the id explicitly or assert on
  shape/prefix, never on the exact clock value.
- **Envelope contract** (from `excrtx-memory-intake/SKILL.md` §IntakeEnvelope, adopted
  verbatim where it fits a GUI-server origin):
  ```json
  {
    "intake_id": "int_YYYYMMDD_HHMMSS_slug",
    "channel": "dashboard",
    "received_at": "<ISO-8601>",
    "content_type": "text|link|document|image|audio|video|zip",
    "original_filename": "<name or ''>",
    "mime_type": "<mime or ''>",
    "local_cached_path": "original/<name>",
    "user_caption": "<caption>",
    "correlation_id": "<uuid4 hex>",
    "session_ref": "<session_id>",
    "status": "received"
  }
  ```
  On-disk layout per envelope: `_inbox/incoming/{intake_id}/` containing `manifest.json`
  (the envelope above), `original/<file>` (the raw payload), and — for `link`/`text` —
  `original/source.txt` / `original/note.md`. `routing.json`, `derived/`, `log.json` are
  **Phase-2b** concerns and are NOT created here.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `api/acervo_studio.py` | modify | Envelope helpers (`_intake_id`, `_valid_intake_id`, `_write_envelope`, `_read_envelope`, `_list_envelopes`) + route intake sub-paths in `handle_studio_get/post`. |
| `tests/test_mod010_acervo_studio.py` | modify | Append hermetic tests for the helpers + HTTP dispatch (mirror the existing `_Handler` + `acervo` fixture). |
| `static/acervo-studio.js` | modify | `intake` unit: "＋ Capturar" panel (text/link/file) + inbox-envelope detail view. |
| `static/acervo-studio.css` | modify | `.axs-cap*` / `.axs-env*` styling (additive, `.axs-` namespaced). |
| `api/acervo_explorer.py` | modify (1 line) | Add `"received"`/status passthrough already present; **only** the `_inbox_nodes` title/status already exist — no change unless Task 3 self-review finds the list route needs the helper. |
| `EXOCRTX_MODIFICATIONS.md` | modify | MOD-010 "Fase 2a" catalog row + rebase note. |

---

## Task 1: Envelope model + write/read/list helpers (backend, pure)

**Files:**
- Modify: `api/acervo_studio.py` (add helpers after the module constants, before
  `_resolved_dot_safe` at line 31)
- Test: `tests/test_mod010_acervo_studio.py`

**Interfaces:**
- Consumes: `acervo_explorer._safe_acervo_path` (already imported at line 26);
  `import api.routes as routes` late-import idiom for `routes._acervo_root()`.
- Produces:
  - `_valid_intake_id(iid: str) -> bool`
  - `_slugify(text: str) -> str` (ascii-lower, non-alnum→`-`, collapse, trim, ≤32 chars)
  - `_intake_id(slug: str, now=None) -> str` → `int_YYYYMMDD_HHMMSS_<slug>`
  - `_write_envelope(root, *, content_type, caption, filename, mime, payload: bytes, session_id, now=None) -> dict` → creates the dir tree, writes `original/…` + `manifest.json`, returns the manifest dict (includes `intake_id`).
  - `_read_envelope(root, iid) -> dict | None` → manifest dict augmented with `files` (list of `original/*` relpaths) or `None` if absent/invalid.
  - `_list_envelopes(root) -> list[dict]` → `[{intake_id, title, status, content_type, received_at}]` newest-first.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_mod010_acervo_studio.py

import base64 as _b64


def test_slugify_and_intake_id_shape(acervo):
    assert studio._slugify("Notas de Reunião — Q3!") == "notas-de-reuniao-q3"
    assert studio._slugify("   ") == "item"          # empty -> fallback
    import datetime as _dt
    iid = studio._intake_id("hello", now=_dt.datetime(2026, 7, 10, 9, 8, 7))
    assert iid == "int_20260710_090807_hello"
    assert studio._valid_intake_id(iid)
    assert not studio._valid_intake_id("../evil")
    assert not studio._valid_intake_id(".hidden")
    assert not studio._valid_intake_id("has/slash")


def test_write_envelope_text_creates_manifest_and_original(acervo):
    import datetime as _dt
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
    # original filename is sanitized to a basename; no escape.
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
    assert studio._read_envelope(acervo, "int_does_not_exist") is None
    listing = studio._list_envelopes(acervo)
    ids = [e["intake_id"] for e in listing]
    assert set(ids) == {m1["intake_id"], m2["intake_id"]}
    assert all("title" in e and "status" in e for e in listing)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd hermes-webui && .venv/bin/python -m pytest tests/test_mod010_acervo_studio.py -k "slugify or write_envelope or read_and_list" -q`
Expected: FAIL (`AttributeError: module 'api.acervo_studio' has no attribute '_slugify'`).

- [ ] **Step 3: Implement the helpers**

Insert into `api/acervo_studio.py` after line 28 (`_MAX_FILE_DOWNLOAD_BYTES = …`):

```python
import base64
import datetime
import json
import re
import uuid

_MAX_INTAKE_BYTES = 25 * 1024 * 1024  # decoded payload cap for capture (HTTP 413)
_INTAKE_ID_RE = re.compile(r"^int_\d{8}_\d{6}_[a-z0-9][a-z0-9-]*$")
# content_type -> (subdir filename for text/link; files use their own basename)
_INTAKE_CONTENT_TYPES = {"text", "link", "document", "image", "audio", "video", "zip"}


def _slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return (s[:32].strip("-") or "item")


def _valid_intake_id(iid):
    return bool(iid) and bool(_INTAKE_ID_RE.match(str(iid)))


def _intake_id(slug, now=None):
    now = now or datetime.datetime.now()
    return "int_%s_%s" % (now.strftime("%Y%m%d_%H%M%S"), _slugify(slug))


def _safe_basename(name):
    """Reduce an arbitrary client filename to a safe basename (no path parts,
    no dot-leading, no separators)."""
    base = os.path.basename(str(name or "").replace("\\", "/"))
    base = base.lstrip(".") or "file"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:120] or "file"


def _write_envelope(root, *, content_type, caption, filename, mime,
                    payload, session_id, now=None):
    """Create _inbox/incoming/{id}/ with original/<file> + manifest.json.
    `root` is the acervo root Path (tests pass tmp_path/acervo). Pure filesystem;
    no agent, no semantic write. Returns the manifest dict."""
    if content_type not in _INTAKE_CONTENT_TYPES:
        raise ValueError("bad content_type")
    now = now or datetime.datetime.now()
    slug_src = caption or filename or content_type
    iid = _intake_id(slug_src, now=now)
    env = root / "_inbox" / "incoming" / iid
    (env / "original").mkdir(parents=True, exist_ok=True)
    if content_type == "text":
        orig_name = "note.md"
    elif content_type == "link":
        orig_name = "source.txt"
    else:
        orig_name = _safe_basename(filename)
    (env / "original" / orig_name).write_bytes(payload)
    manifest = {
        "intake_id": iid,
        "channel": "dashboard",
        "received_at": now.isoformat(),
        "content_type": content_type,
        "original_filename": (orig_name if content_type not in ("text", "link") else ""),
        "mime_type": str(mime or ""),
        "local_cached_path": "original/" + orig_name,
        "user_caption": str(caption or ""),
        "correlation_id": uuid.uuid4().hex,
        "session_ref": str(session_id or ""),
        "status": "received",
    }
    (env / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _envelope_dir(root, iid):
    if not _valid_intake_id(iid):
        return None
    d = root / "_inbox" / "incoming" / iid
    return d if d.is_dir() else None


def _read_envelope(root, iid):
    d = _envelope_dir(root, iid)
    if d is None:
        return None
    try:
        m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        m = {"intake_id": iid, "status": "received"}
    files = []
    orig = d / "original"
    if orig.is_dir():
        for f in sorted(orig.iterdir()):
            if f.is_file():
                files.append("original/" + f.name)
    m["files"] = files
    return m


def _list_envelopes(root):
    inc = root / "_inbox" / "incoming"
    out = []
    if not inc.is_dir():
        return out
    for d in inc.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        title = d.name
        status = "received"
        ctype = ""
        received = ""
        mf = d / "manifest.json"
        if mf.is_file():
            try:
                m = json.loads(mf.read_text(encoding="utf-8"))
                title = m.get("user_caption") or m.get("original_filename") or d.name
                status = m.get("status") or "received"
                ctype = m.get("content_type") or ""
                received = m.get("received_at") or ""
            except (OSError, ValueError):
                pass
        out.append({"intake_id": d.name, "title": title, "status": status,
                    "content_type": ctype, "received_at": received})
    out.sort(key=lambda e: e["intake_id"], reverse=True)  # id embeds timestamp
    return out
```

Note: `os` is already imported at the top of the module (line 22).

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_mod010_acervo_studio.py -k "slugify or write_envelope or read_and_list" -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add api/acervo_studio.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): intake envelope model + write/read/list helpers (Phase 2a T1)"
```

---

## Task 2: Intake create routes — text / link / upload (base64)

**Files:**
- Modify: `api/acervo_studio.py` (new `handle_intake_create`; wire into `handle_studio_post` at line 179)
- Test: `tests/test_mod010_acervo_studio.py`

**Interfaces:**
- Consumes: Task 1 helpers; `routes.j`, `routes.bad`, `routes._resolve_session_workspace`.
- Produces: POST `/api/acervo/x/intake/text|link|upload` → `{ok, intake_id, manifest}`.
  Body shape: `{session_id, caption?, text?}` (text), `{session_id, caption?, url}` (link),
  `{session_id, caption?, filename, mime?, content_b64}` (upload).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_mod010_acervo_studio.py

def _post(path, body):
    h = _Handler(path)
    ok = studio.handle_studio_post(h, body)
    return h, ok


def test_intake_text_route_creates_envelope(acervo, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: True)
    h, _ = _post("/api/acervo/x/intake/text",
                 {"session_id": "s", "caption": "hi", "text": "hello world"})
    assert h.status == 200
    out = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert out["ok"] is True and out["intake_id"].startswith("int_")
    env = acervo / "_inbox" / "incoming" / out["intake_id"]
    assert (env / "original" / "note.md").read_text(encoding="utf-8") == "hello world"


def test_intake_link_route(acervo, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: True)
    h, _ = _post("/api/acervo/x/intake/link",
                 {"session_id": "s", "url": "https://example.com"})
    assert h.status == 200
    out = json.loads(h.wfile.getvalue().decode("utf-8"))
    env = acervo / "_inbox" / "incoming" / out["intake_id"]
    assert (env / "original" / "source.txt").read_text(encoding="utf-8") == "https://example.com"


def test_intake_upload_base64(acervo, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: True)
    b64 = _b64.b64encode(b"PDFDATA").decode("ascii")
    h, _ = _post("/api/acervo/x/intake/upload",
                 {"session_id": "s", "filename": "report.pdf",
                  "mime": "application/pdf", "content_b64": b64})
    assert h.status == 200
    out = json.loads(h.wfile.getvalue().decode("utf-8"))
    env = acervo / "_inbox" / "incoming" / out["intake_id"]
    assert (env / "original" / "report.pdf").read_bytes() == b"PDFDATA"


def test_intake_requires_session(acervo, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: False)
    h, _ = _post("/api/acervo/x/intake/text", {"session_id": "bad", "text": "x"})
    assert h.status in (400, 404)


def test_intake_upload_too_large_413(acervo, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: True)
    big = _b64.b64encode(b"x" * (studio._MAX_INTAKE_BYTES + 1)).decode("ascii")
    h, _ = _post("/api/acervo/x/intake/upload",
                 {"session_id": "s", "filename": "big.bin", "content_b64": big})
    assert h.status == 413


def test_intake_empty_payload_rejected(acervo, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: True)
    h, _ = _post("/api/acervo/x/intake/text", {"session_id": "s", "text": "   "})
    assert h.status == 400
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_mod010_acervo_studio.py -k intake -q`
Expected: FAIL (routes 404 — `handle_studio_post` still stubbed).

- [ ] **Step 3: Implement the create handler + wire dispatch**

Add to `api/acervo_studio.py` (before the `# region: dispatchers` marker at line 169):

```python
def _intake_session(handler, routes, body):
    """Shared session gate for intake POSTs. Returns sid or None (after emitting
    the error response)."""
    sid = str((body or {}).get("session_id", "") or "").strip()
    if not sid:
        routes.bad(handler, "session_id is required")
        return None
    if not routes._resolve_session_workspace(sid):
        routes.bad(handler, "Session not found", 404)
        return None
    return sid


def handle_intake_create(handler, body, kind):
    """POST /api/acervo/x/intake/{text|link|upload} — write an envelope to
    _inbox/incoming/. No agent, no semantic write (input is not memory)."""
    import api.routes as routes
    body = body or {}
    sid = _intake_session(handler, routes, body)
    if sid is None:
        return True
    caption = str(body.get("caption", "") or "").strip()
    if kind == "text":
        text = str(body.get("text", "") or "")
        if not text.strip():
            return routes.bad(handler, "text is required")
        payload, ctype, filename, mime = text.encode("utf-8"), "text", "", "text/markdown"
    elif kind == "link":
        url = str(body.get("url", "") or "").strip()
        if not url:
            return routes.bad(handler, "url is required")
        if not caption:
            caption = url
        payload, ctype, filename, mime = url.encode("utf-8"), "link", "", "text/uri-list"
    elif kind == "upload":
        b64 = str(body.get("content_b64", "") or "")
        filename = str(body.get("filename", "") or "")
        mime = str(body.get("mime", "") or "")
        if not b64:
            return routes.bad(handler, "content_b64 is required")
        # Cheap pre-check on encoded length before decoding (base64 ~ 4/3 of raw).
        if len(b64) > (_MAX_INTAKE_BYTES // 3) * 4 + 8:
            return routes.j(handler, {"error": "file too large"}, status=413)
        try:
            payload = base64.b64decode(b64, validate=True)
        except (ValueError, Exception):
            return routes.bad(handler, "invalid base64 payload")
        if len(payload) > _MAX_INTAKE_BYTES:
            return routes.j(handler, {"error": "file too large"}, status=413)
        if not payload:
            return routes.bad(handler, "empty payload")
        ctype = _content_type_for_mime(mime, filename)
    else:
        return routes.bad(handler, "unknown intake kind", 404)
    root = routes._acervo_root()
    manifest = _write_envelope(
        root, content_type=ctype, caption=caption, filename=filename,
        mime=mime, payload=payload, session_id=sid)
    return routes.j(handler, {"ok": True, "intake_id": manifest["intake_id"],
                              "manifest": manifest})


def _content_type_for_mime(mime, filename):
    m = (mime or "").lower()
    if m.startswith("image/"):
        return "image"
    if m.startswith("audio/"):
        return "audio"
    if m.startswith("video/"):
        return "video"
    if m in ("application/zip", "application/x-zip-compressed") or \
       str(filename or "").lower().endswith(".zip"):
        return "zip"
    return "document"
```

Then extend `handle_studio_post` (currently lines 179–182) to route the intake sub-paths.
Replace its body with:

```python
def handle_studio_post(handler, body):
    """Route Studio POST sub-paths. Phase 2a adds intake/{text,link,upload}."""
    import api.routes as routes
    path = (getattr(handler, "path", "") or "").split("?", 1)[0]
    if path == "/api/acervo/x/intake/text":
        return handle_intake_create(handler, body, "text")
    if path == "/api/acervo/x/intake/link":
        return handle_intake_create(handler, body, "link")
    if path == "/api/acervo/x/intake/upload":
        return handle_intake_create(handler, body, "upload")
    return routes.bad(handler, "unknown acervo explorer endpoint", 404)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_mod010_acervo_studio.py -k intake -q`
Expected: PASS (6 tests). Also `py_compile`: `.venv/bin/python -m py_compile api/acervo_studio.py`.

- [ ] **Step 5: Commit**

```bash
git add api/acervo_studio.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): intake create routes text/link/upload-base64 (Phase 2a T2)"
```

---

## Task 3: Intake list + detail GET routes

**Files:**
- Modify: `api/acervo_studio.py` (`handle_intake_list`, `handle_intake_detail`; wire into `handle_studio_get` at line 171)
- Test: `tests/test_mod010_acervo_studio.py`

**Interfaces:**
- Consumes: Task 1 helpers; `routes.j`, `routes.bad`, `routes._resolve_session_workspace`.
- Produces:
  - GET `/api/acervo/x/intake?session_id=…` → `{items: [...], count}`
  - GET `/api/acervo/x/intake/item?session_id=…&id=<iid>` → `{envelope: {...}}` (404 on miss).
  (Uses a `?id=` query rather than a path segment so the existing exact-path dispatch
  stays trivial and rebase-safe.)

- [ ] **Step 1: Write the failing tests**

```python
def _get(path):
    from urllib.parse import urlparse as _up
    h = _Handler(path)
    ok = studio.handle_studio_get(h, _up(path))
    return h, ok


def test_intake_list_route(acervo, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: True)
    studio._write_envelope(acervo, content_type="text", caption="alpha",
                           filename="", mime="", payload=b"a", session_id="s")
    studio._write_envelope(acervo, content_type="link", caption="beta",
                           filename="", mime="", payload=b"http://b", session_id="s")
    h, _ = _get("/api/acervo/x/intake?session_id=s")
    assert h.status == 200
    out = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert out["count"] == 2
    assert {i["title"] for i in out["items"]} == {"alpha", "beta"}


def test_intake_detail_route(acervo, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: True)
    m = studio._write_envelope(acervo, content_type="text", caption="alpha",
                               filename="", mime="", payload=b"hello", session_id="s")
    h, _ = _get("/api/acervo/x/intake/item?session_id=s&id=" + m["intake_id"])
    assert h.status == 200
    out = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert out["envelope"]["intake_id"] == m["intake_id"]
    assert "original/note.md" in out["envelope"]["files"]


def test_intake_detail_missing_404(acervo, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: True)
    h, _ = _get("/api/acervo/x/intake/item?session_id=s&id=int_20990101_000000_nope")
    assert h.status == 404


def test_intake_detail_rejects_bad_id(acervo, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: True)
    h, _ = _get("/api/acervo/x/intake/item?session_id=s&id=../../etc")
    assert h.status in (400, 404)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_mod010_acervo_studio.py -k "intake_list or intake_detail" -q`
Expected: FAIL (GET routes 404).

- [ ] **Step 3: Implement + wire the GET dispatch**

Add to `api/acervo_studio.py`:

```python
def handle_intake_list(handler, parsed):
    """GET /api/acervo/x/intake — list inbox envelopes."""
    import api.routes as routes
    qs = parse_qs(parsed.query)
    sid = (qs.get("session_id", [""])[0] or "").strip()
    if not sid:
        return routes.bad(handler, "session_id is required")
    if not routes._resolve_session_workspace(sid):
        return routes.bad(handler, "Session not found", 404)
    items = _list_envelopes(routes._acervo_root())
    return routes.j(handler, {"items": items, "count": len(items)})


def handle_intake_detail(handler, parsed):
    """GET /api/acervo/x/intake/item?id=<iid> — one envelope's manifest + files."""
    import api.routes as routes
    qs = parse_qs(parsed.query)
    sid = (qs.get("session_id", [""])[0] or "").strip()
    if not sid:
        return routes.bad(handler, "session_id is required")
    if not routes._resolve_session_workspace(sid):
        return routes.bad(handler, "Session not found", 404)
    iid = (qs.get("id", [""])[0] or "").strip()
    if not _valid_intake_id(iid):
        return routes.bad(handler, "invalid intake id")
    env = _read_envelope(routes._acervo_root(), iid)
    if env is None:
        return routes.j(handler, {"error": "envelope not found"}, status=404)
    return routes.j(handler, {"envelope": env})
```

Extend `handle_studio_get` (lines 171–176) — add the two branches before the download check:

```python
def handle_studio_get(handler, parsed):
    """Route Studio GET sub-paths under /api/acervo/x/ (delegated by MOD-009)."""
    import api.routes as routes
    if parsed.path == "/api/acervo/x/intake":
        return handle_intake_list(handler, parsed)
    if parsed.path == "/api/acervo/x/intake/item":
        return handle_intake_detail(handler, parsed)
    if parsed.path == "/api/acervo/x/download":
        return handle_download(handler, parsed)
    return routes.bad(handler, "unknown acervo explorer endpoint", 404)
```

- [ ] **Step 4: Run to verify pass + no regressions**

Run: `.venv/bin/python -m pytest tests/test_mod010_acervo_studio.py -q`
Expected: PASS (full MOD-010 file, ~32 prior + new). Then
`.venv/bin/python -m py_compile api/acervo_studio.py`.

- [ ] **Step 5: Commit**

```bash
git add api/acervo_studio.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): intake list + detail GET routes (Phase 2a T3)"
```

---

## Task 4: Frontend — "＋ Capturar" panel (text / link / file)

**Files:**
- Modify: `static/acervo-studio.js` (add the `intake` unit near the search fns, ~line 633)
- Modify: `static/acervo-studio.css` (append `.axs-cap*` rules)

**Interfaces:**
- Consumes: `AXS`, `_sid`, `_esc`, `_toast`, `api`, `acervoStudioRenderNav` (all in-IIFE).
- Produces: `window.acervoStudioCapture(kind)`, `acervoStudioSubmitCapture(...)`; a
  capture affordance shown when `AXS.scope === 'inbox'`.

- [ ] **Step 1: Add the capture panel renderer**

In `static/acervo-studio.js`, before `function acervoStudioToggle()` (line 635), add:

```javascript
  // ── Phase 2a: intake capture ─────────────────────────────────────────────
  function _readFileB64(file) {
    return new Promise(function (resolve, reject) {
      var fr = new FileReader();
      fr.onload = function () {
        var res = String(fr.result || '');
        var comma = res.indexOf(',');
        resolve(comma >= 0 ? res.slice(comma + 1) : res);  // strip data: prefix
      };
      fr.onerror = function () { reject(fr.error || new Error('read failed')); };
      fr.readAsDataURL(file);
    });
  }

  function acervoStudioCapture() {
    var root = _root();
    var reader = root && root.querySelector('[data-axs="reader"]');
    if (!reader) return;
    AXS.selectedPath = ''; AXS.page = null; AXS.artifactId = '';
    reader.innerHTML =
      '<div class="axs-crumb"><b>📥 Inbox</b> › Capturar</div>' +
      '<div class="axs-doc axs-cap">' +
      '  <div class="axs-cap-tabs">' +
      '    <button type="button" class="on" data-cap="text">Texto</button>' +
      '    <button type="button" data-cap="link">Link</button>' +
      '    <button type="button" data-cap="file">Arquivo</button>' +
      '  </div>' +
      '  <label class="axs-field"><span>Legenda (opcional)</span>' +
      '    <input type="text" data-cap-fm="caption" placeholder="do que se trata?"></label>' +
      '  <div data-cap-pane="text">' +
      '    <label class="axs-field axs-fgrow"><span>Texto</span>' +
      '      <textarea data-cap-fm="text" spellcheck="false" placeholder="cole ou escreva…"></textarea></label>' +
      '  </div>' +
      '  <div data-cap-pane="link" hidden>' +
      '    <label class="axs-field"><span>URL</span>' +
      '      <input type="url" data-cap-fm="url" placeholder="https://…"></label>' +
      '  </div>' +
      '  <div data-cap-pane="file" hidden>' +
      '    <label class="axs-field"><span>Arquivo (até 25 MB)</span>' +
      '      <input type="file" data-cap-fm="file"></label>' +
      '  </div>' +
      '  <div class="axs-acts"><button type="button" class="axs-act axs-act-primary" ' +
      '     data-cap-submit>Capturar</button></div>' +
      '</div>';
    var kind = { v: 'text' };
    reader.querySelectorAll('[data-cap]').forEach(function (b) {
      b.addEventListener('click', function () {
        kind.v = b.getAttribute('data-cap');
        reader.querySelectorAll('[data-cap]').forEach(function (x) {
          x.classList.toggle('on', x === b);
        });
        reader.querySelectorAll('[data-cap-pane]').forEach(function (p) {
          p.hidden = p.getAttribute('data-cap-pane') !== kind.v;
        });
      });
    });
    reader.querySelector('[data-cap-submit]')
      .addEventListener('click', function () { acervoStudioSubmitCapture(kind.v); });
  }
  window.acervoStudioCapture = acervoStudioCapture;

  async function acervoStudioSubmitCapture(kind) {
    var root = _root();
    var reader = root && root.querySelector('[data-axs="reader"]');
    if (!reader) return;
    var caption = (reader.querySelector('[data-cap-fm="caption"]') || {}).value || '';
    var url, body;
    if (kind === 'text') {
      var text = (reader.querySelector('[data-cap-fm="text"]') || {}).value || '';
      if (!text.trim()) { _toast('Escreva algum texto', 'error'); return; }
      url = '/api/acervo/x/intake/text';
      body = { session_id: _sid(), caption: caption, text: text };
    } else if (kind === 'link') {
      var u = (reader.querySelector('[data-cap-fm="url"]') || {}).value || '';
      if (!u.trim()) { _toast('Informe uma URL', 'error'); return; }
      url = '/api/acervo/x/intake/link';
      body = { session_id: _sid(), caption: caption, url: u.trim() };
    } else {
      var fi = reader.querySelector('[data-cap-fm="file"]');
      var file = fi && fi.files && fi.files[0];
      if (!file) { _toast('Escolha um arquivo', 'error'); return; }
      if (file.size > 25 * 1024 * 1024) { _toast('Arquivo acima de 25 MB', 'error'); return; }
      var b64;
      try { b64 = await _readFileB64(file); }
      catch (e) { _toast('Falha ao ler o arquivo' + _detail(e), 'error'); return; }
      url = '/api/acervo/x/intake/upload';
      body = { session_id: _sid(), caption: caption, filename: file.name,
               mime: file.type || '', content_b64: b64 };
    }
    try {
      await api(url, { method: 'POST', body: JSON.stringify(body) });
    } catch (e) { _toast('Falha ao capturar' + _detail(e), 'error'); return; }
    _toast('Capturado no inbox', 'success');
    AXS.scope = 'inbox';
    if (typeof acervoStudioRenderNav === 'function') await acervoStudioRenderNav();
  }
  window.acervoStudioSubmitCapture = acervoStudioSubmitCapture;
```

- [ ] **Step 2: Surface the capture affordance in the inbox scope**

In `acervoStudioSelectScope` (line 162), after the `sub.innerHTML = out;` assignment
(line 203), add a capture button at the top of the inbox sub-list. Insert right after
line 203:

```javascript
    if (scope === 'inbox') {
      var cap = document.createElement('button');
      cap.type = 'button';
      cap.className = 'axs-cap-add';
      cap.textContent = '＋ Capturar';
      cap.addEventListener('click', acervoStudioCapture);
      sub.insertBefore(cap, sub.firstChild);
    }
```

- [ ] **Step 3: Style it**

Append to `static/acervo-studio.css`:

```css
.axs-cap-tabs { display: flex; gap: 6px; margin-bottom: 10px; }
.axs-cap-tabs button { padding: 4px 12px; border-radius: 6px; border: 1px solid var(--axs-border, #3a3a3a); background: transparent; color: inherit; cursor: pointer; }
.axs-cap-tabs button.on { background: var(--axs-accent, #4a7dff); color: #fff; border-color: transparent; }
.axs-cap textarea { min-height: 180px; }
.axs-cap-add { display: block; width: 100%; margin: 0 0 8px; padding: 6px; border: 1px dashed var(--axs-border, #3a3a3a); border-radius: 6px; background: transparent; color: inherit; cursor: pointer; font-weight: 600; }
.axs-cap-add:hover { border-style: solid; }
```

- [ ] **Step 4: Lint**

Run: `cd hermes-webui && node --check static/acervo-studio.js && npm run lint:runtime`
Expected: clean (no ES import/export; `sourceType:"script"` guard passes).

- [ ] **Step 5: Commit**

```bash
git add static/acervo-studio.js static/acervo-studio.css
git commit -m "feat(acervo-studio): intake capture panel — text/link/file (Phase 2a T4)"
```

---

## Task 5: Frontend — inbox envelope detail view

**Files:**
- Modify: `static/acervo-studio.js` (add `acervoStudioOpenEnvelope`; wire the `type:'intake'` nav node)

**Interfaces:**
- Consumes: `api`, `_sid`, `_esc`, `_root`, `renderMd`, the `x/intake/item` + `x/raw` endpoints.
- Produces: `window.acervoStudioOpenEnvelope(iid)`; clicking an inbox node opens it.

- [ ] **Step 1: Add the envelope reader**

In `static/acervo-studio.js`, add before `acervoStudioToggle` (line 635):

```javascript
  async function acervoStudioOpenEnvelope(iid) {
    var root = _root();
    var reader = root && root.querySelector('[data-axs="reader"]');
    if (!reader) return;
    AXS.selectedPath = ''; AXS.page = null; AXS.artifactId = '';
    reader.innerHTML = '<div class="axs-reader-empty">Carregando…</div>';
    var d;
    try {
      d = await api('/api/acervo/x/intake/item?session_id=' + encodeURIComponent(_sid()) +
        '&id=' + encodeURIComponent(iid));
    } catch (e) { reader.innerHTML = '<div class="axs-reader-empty">Erro ao abrir o envelope.</div>'; return; }
    var env = (d && d.envelope) || {};
    var chips = _chip('📥 ' + (env.content_type || 'intake')) + _chip('✓ ' + (env.status || 'received'));
    var caption = env.user_caption || env.original_filename || env.intake_id || iid;
    var files = env.files || [];
    var body = '';
    // Preview the first original file inline (md rendered; else sandboxed iframe/img).
    if (files.length) {
      var rawUrl = '/api/acervo/x/raw?session_id=' + encodeURIComponent(_sid()) +
        '&path=' + encodeURIComponent('_inbox/incoming/' + iid + '/' + files[0]);
      if (/\.(md|txt)$/i.test(files[0])) {
        var txt;
        try {
          var r = await fetch(rawUrl); txt = await r.text();
        } catch (e) { txt = ''; }
        body = '<div class="axs-md">' +
          ((typeof renderMd === 'function') ? renderMd(txt) : _esc(txt)) + '</div>';
      } else if (env.content_type === 'image') {
        body = '<img class="axs-raw" src="' + _esc(rawUrl) + '" alt="' + _esc(files[0]) + '">';
      } else {
        body = '<iframe class="axs-raw" src="' + _esc(rawUrl) + '" sandbox title="' + _esc(files[0]) + '"></iframe>';
      }
    }
    var fileList = files.map(function (f) { return '<li>' + _esc(f) + '</li>'; }).join('');
    reader.innerHTML =
      '<div class="axs-crumb"><b>📥 Inbox</b> › ' + _esc(env.intake_id || iid) + '</div>' +
      '<div class="axs-doc axs-env">' +
      '  <div class="axs-fm">' + chips + '</div>' +
      '  <h1 class="axs-title">' + _esc(caption) + '</h1>' +
      (fileList ? '<ul class="axs-env-files">' + fileList + '</ul>' : '') +
      body +
      '  <div class="axs-env-note">Aguardando triagem (Fase 2b). Nada foi escrito na memória semântica.</div>' +
      '</div>';
  }
  window.acervoStudioOpenEnvelope = acervoStudioOpenEnvelope;
```

- [ ] **Step 2: Wire the intake node click**

In `acervoStudioSelectScope`, the intake branch currently renders a non-clickable div
(lines 192–194). Replace it with a clickable node carrying the id:

```javascript
      } else if (n.type === 'intake') {
        out += '<div class="axs-pi" data-intake="' + _esc(n.id) + '"><span class="st"></span>' +
          _esc(n.title) + ' · ' + _esc(n.status) + '</div>';
```

And after the existing `sub.querySelectorAll('[data-path]')` wiring block (ends line 214),
add:

```javascript
    sub.querySelectorAll('[data-intake]').forEach(function (el) {
      el.addEventListener('click', function () {
        acervoStudioOpenEnvelope(el.getAttribute('data-intake'));
      });
    });
```

- [ ] **Step 3: Style (append to `static/acervo-studio.css`)**

```css
.axs-env-files { margin: 8px 0; padding-left: 18px; opacity: .8; font-size: 13px; }
.axs-env-note { margin-top: 14px; padding: 8px 10px; border-radius: 6px; background: rgba(127,127,127,.12); font-size: 13px; opacity: .85; }
```

- [ ] **Step 4: Lint**

Run: `node --check static/acervo-studio.js && npm run lint:runtime`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add static/acervo-studio.js static/acervo-studio.css
git commit -m "feat(acervo-studio): inbox envelope detail view (Phase 2a T5)"
```

---

## Task 6: Live E2E pass + governance

**Files:**
- Modify: `EXOCRTX_MODIFICATIONS.md` (MOD-010 "Fase 2a" row)
- No code; verification + catalog.

- [ ] **Step 1: Boot the server against a THROWAWAY fixture acervo**

```bash
cd hermes-webui
FIX=$(mktemp -d)/acervo
mkdir -p "$FIX/_inbox/incoming" "$FIX/micro/comercial/knowledge"
printf -- '---\ntitle: Precos\n---\n\nx\n' > "$FIX/micro/comercial/knowledge/precos.md"
HERMES_HOME="$(mktemp -d)" ACERVO="$FIX" HERMES_WEBUI_PORT=8799 .venv/bin/python server.py --port 8799 &
```

- [ ] **Step 2: Drive the flow in headless Chromium (Playwright)**

Open `http://localhost:8799` → bottom-right **▤ Acervo** (auto-binds a session) →
Inbox scope → **＋ Capturar**:
1. Text: caption "nota de teste", body "conteúdo" → Capturar → toast "Capturado no inbox";
   the Inbox badge increments; the new envelope appears; click it → detail renders the
   markdown + "Aguardando triagem (Fase 2b)".
2. Link: `https://example.com` → Capturar → envelope with `source.txt`.
3. File: upload a small `.pdf`/`.png` → Capturar → detail shows a sandboxed preview.
Verify on disk: `ls "$FIX/_inbox/incoming"` shows 3 `int_*` dirs each with
`manifest.json` + `original/`.
Verify graceful path: stop nothing — capture must work with NO Hermes runtime (there is
none in this fixture boot), proving zero agent dependency.

- [ ] **Step 3: Rebase-safety assertion**

```bash
git diff --stat origin/exocortex/stable -- api/routes.py static/index.html \
  static/style.css static/ui.js static/workspace.js static/acervo.js \
  static/acervo-explorer.js static/acervo-explorer.css
```
Expected: **empty** (only `api/acervo_studio.py`, `static/acervo-studio.{js,css}`,
`tests/…`, and docs changed).

- [ ] **Step 4: Full suite baseline**

Run: `.venv/bin/python -m pytest tests/ -q` — assert the MOD-010 file is fully green and
no NEW failures vs. the documented pre-existing env-sensitive set (verdigris/zh_hant/
turkish/sessiondb-fd, ~16).

- [ ] **Step 5: Catalog + commit**

Add a MOD-010 "Fase 2a — Intake Capture (agentless)" row to `EXOCRTX_MODIFICATIONS.md`
(endpoints `x/intake/{text,link,upload,item}` + `x/intake` list; base64-in-JSON note;
0 routes.py / 0 index.html lines). Then:

```bash
git add EXOCRTX_MODIFICATIONS.md
git commit -m "docs(acervo-studio): catalog MOD-010 Phase 2a intake capture"
```

---

## Deferred to Phase 2b (separate plan — first WRITE-coupling → COLLAB)

- `api/acervo_studio_agent.py` — the Hermes mediation layer (sync in-process
  `run_conversation` + JSON-proposal prompt + parser + schema validate + offline guard),
  per the resolved spike.
- `POST x/intake/item/triage` — server → Hermes → routing proposal (`routing.json`),
  rendered inline in the assistant panel.
- `POST x/intake/item/promote` — agent-mediated semantic write via
  `excrtx-memory-manager`; envelope → `_inbox/promoted/`.
- Graceful "agente offline" states; the propose-then-approve UI.
- COLLAB change record + IDENTITY update (first write-coupling of the intake surface).

## Self-Review (done at authoring)

- **Spec coverage:** RFC §6.1 Intake `upload/text/link` + `GET x/intake` + `GET x/intake/{id}`
  are covered by T2/T3 (promote/triage explicitly deferred to 2b). §5.3 capture UX = T4/T5.
  §9 "large uploads: size caps + original preserved" = the 25 MiB cap + original-first write.
  §8 rebase-safety = the 0-line assertions in T6.
- **Placeholder scan:** none — every step ships complete code.
- **Type consistency:** `_write_envelope`/`_read_envelope`/`_list_envelopes`/`_valid_intake_id`/
  `_intake_id`/`_slugify` names match across T1→T3; frontend `acervoStudioCapture`/
  `acervoStudioSubmitCapture`/`acervoStudioOpenEnvelope` match their wiring. Endpoint paths
  (`/api/acervo/x/intake`, `/intake/item`, `/intake/{text,link,upload}`) match between JS and
  the Python dispatch.
