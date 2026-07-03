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
