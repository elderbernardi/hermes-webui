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

import base64
import datetime
import json
import os
import re
import shutil
import unicodedata
import uuid
from urllib.parse import parse_qs

from api.acervo_explorer import _safe_acervo_path

_MAX_FILE_DOWNLOAD_BYTES = 50 * 1024 * 1024  # mirror MOD-009 _MAX_RAW_BYTES

# ── Phase 2a: intake capture (agentless — input is not memory) ──────────────
_MAX_INTAKE_BYTES = 25 * 1024 * 1024  # decoded payload cap for capture (HTTP 413)
_INTAKE_ID_RE = re.compile(r"^int_\d{8}_\d{6}_[a-z0-9][a-z0-9-]*$")
_INTAKE_CONTENT_TYPES = {"text", "link", "document", "image", "audio", "video", "zip"}


def _slugify(text):
    # NFKD-normalize so accented chars fold to ASCII (ã→a) instead of becoming
    # separators; then collapse any remaining non-alnum runs to single dashes.
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "-", s.strip().lower()).strip("-")
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
    `root` is the acervo root Path. Pure filesystem; no agent, no semantic
    write. Returns the manifest dict."""
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


def _resolved_dot_safe(routes, target):
    """Reject a symlink-RESOLVED path that lands on a dot-prefixed component
    (.quarantine/.git/...) even though _safe_acervo_path passed on the input
    string. _safe_acervo_path only checks the literal input components, so a
    clean-looking path that resolves through a symlink into e.g. .quarantine/
    would otherwise slip through.
    """
    root_r = routes._acervo_root().resolve()
    try:
        parts = target.relative_to(root_r).parts
    except ValueError:
        return False
    return not any(p.startswith(".") for p in parts)


def _download_file(handler, routes, rel):
    """Stream one acervo file as an attachment (md or binary alike)."""
    import mimetypes as _mt
    try:
        target = _safe_acervo_path(rel)
    except ValueError:
        return routes.bad(handler, "invalid path", 400)
    if not _resolved_dot_safe(routes, target):
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
    if not _resolved_dot_safe(routes, target):
        return routes.bad(handler, "invalid artifact id", 400)
    if not target.is_dir():
        return routes.j(handler, {"error": "artifact not found"}, status=404)

    # Anchor containment on the artifact's OWN directory (not the whole acervo
    # root): a symlink inside the artifact that resolves elsewhere under the
    # acervo root (e.g. into .quarantine/) must NOT be treated as contained
    # just because it stays under the acervo root as a whole.
    art_root = target.resolve()
    files, _total, limit_hit = routes._folder_download_collect(
        target, art_root, routes._folder_zip_max_bytes(),
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
                fd = routes.open_anchored_fd(art_root, fp.resolve(), want_dir=False)
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


# region: intake (Phase 2a — capture; agentless)

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
        except (ValueError, TypeError):
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


# region: dispatchers (delegation targets of the MOD-009 fallbacks)

def handle_studio_get(handler, parsed):
    """Route Studio GET sub-paths under /api/acervo/x/ (delegated by MOD-009)."""
    import api.routes as routes
    if parsed.path == "/api/acervo/x/download":
        return handle_download(handler, parsed)
    return routes.bad(handler, "unknown acervo explorer endpoint", 404)


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
