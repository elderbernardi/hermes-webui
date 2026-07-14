"""Acervo tab backend — MOD-007/008 (HW-1 extraction from api/routes.py).

Every exact-match /api/acervo/*, /api/artifact/* and /api/inbox/* endpoint of
the Acervo tab lives here, moved verbatim from the fork's routes.py (the inline
block appended after _handle_folder_download, plus the MOD-008 inbox handlers).
routes.py keeps only two dispatch delegations plus a re-export block so the
fork-owned Explorer/Studio modules' `routes.<name>` references keep resolving.

Core-route helpers (j, bad, session resolution, folder-zip limits, logger) are
reached through the module-level `import api.routes as routes` binding at the
BOTTOM of this file — safe in both import directions: when routes.py's bottom
re-export triggers this module, api.routes is already in sys.modules with those
names defined; when this module is imported first, its bottom import fully
loads routes, whose re-export then finds all our names already defined.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs

def _read_frontmatter_title(path):
    """Best-effort human title for a loose markdown artifact (no manifest).

    Prefers YAML frontmatter ``title:``, then the first ``# heading``. Returns
    None when neither is present so the caller can fall back to the filename.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
    except OSError:
        return None
    m = re.search(r'^title:\s*(.+?)\s*$', head, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"\'') or None
    m = re.search(r'^#\s+(.+?)\s*$', head, re.MULTILINE)
    if m:
        return m.group(1).strip() or None
    return None


def _normalize_artifact(data, art_id):
    """Flatten a manifest.json into the flat shape the Acervo UI renders.

    Defensive: every field has a fallback, so a partial/legacy manifest still
    produces a usable card (additive contract — missing keys never error).
    """
    ev = data.get("evaluation") if isinstance(data.get("evaluation"), dict) else {}
    pub_root = data.get("publication") if isinstance(data.get("publication"), dict) else {}
    pub = pub_root.get("drive") if isinstance(pub_root.get("drive"), dict) else {}
    prov = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
    friendly = data.get("friendly_name") or data.get("title") or art_id
    return {
        "id": art_id,
        "kind": "package",
        "has_manifest": True,
        "friendly_name": friendly,
        "title": data.get("title") or friendly,
        "status": data.get("status") or "unknown",
        "artifact_type": data.get("artifact_type") or "document",
        "source_type": data.get("source_type"),
        "primary_microverso": data.get("primary_microverso"),
        "related_microversos": data.get("related_microversos") or [],
        "task_id": data.get("task_id"),
        "scope": data.get("scope"),
        "owner": data.get("owner") if isinstance(data.get("owner"), dict) else {},
        "semantic_links": data.get("semantic_links") or [],
        "source_path": data.get("source_path"),
        "rel_path": "_artifacts/items/" + art_id + (
            "/" + data["source_path"] if data.get("source_path") else ""),
        "evaluation_status": ev.get("status"),
        "evaluation_personas": ev.get("personas") or [],
        "publication_status": pub.get("status"),
        "publication_receipt": pub.get("receipt_path"),
        "drive_link": pub.get("folder_link") or pub.get("web_view_link") or "",
        "created_at": prov.get("created_at"),
        "created_by": prov.get("created_by"),
        "origin": prov.get("origin"),
    }


def _handle_acervo_artifacts(handler, parsed):
    """GET /api/acervo/artifacts?session_id=...

    Human-facing artifact catalog: full normalized manifests for every package
    under <workspace>/_artifacts/items/, plus loose markdown notes in that
    folder. Read-only; powers the Acervo tab (MOD-007). Newest first.
    """
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    workspace = routes._resolve_session_workspace(sid)
    if not workspace:
        return routes.bad(handler, "Session not found", 404)
    try:
        items_dir = routes.safe_resolve(Path(workspace), "_artifacts/items")
    except ValueError:
        return routes.j(handler, {"artifacts": [], "count": 0})
    artifacts = []
    if items_dir.is_dir():
        try:
            children = sorted(items_dir.iterdir(), key=lambda p: p.name, reverse=True)
        except OSError:
            children = []
        for child in children:
            try:
                if child.is_dir():
                    mf = child / "manifest.json"
                    if mf.is_file():
                        data = json.loads(mf.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            artifacts.append(_normalize_artifact(data, child.name))
                            continue
                    # Package directory without a readable manifest — still surface it.
                    artifacts.append({
                        "id": child.name, "kind": "package", "has_manifest": False,
                        "friendly_name": child.name, "title": child.name,
                        "status": "unknown", "artifact_type": "folder",
                        "primary_microverso": None, "task_id": None,
                        "rel_path": "_artifacts/items/" + child.name,
                    })
                elif child.is_file() and child.suffix.lower() == ".md":
                    title = _read_frontmatter_title(child) or child.stem
                    artifacts.append({
                        "id": child.name, "kind": "note", "has_manifest": False,
                        "friendly_name": title, "title": title,
                        "status": "loose", "artifact_type": "note",
                        "primary_microverso": None, "task_id": None,
                        "rel_path": "_artifacts/items/" + child.name,
                    })
            except (OSError, ValueError, json.JSONDecodeError):
                continue
    return routes.j(handler, {"artifacts": artifacts, "count": len(artifacts)})


# UI-permitted manifest status transitions. Excludes 'published' (goes through
# the Drive publish flow) and agent-driven states (approved/ask-publication/failed).
_ACERVO_UI_STATUSES = {"draft", "ready", "archived"}


def _handle_acervo_status(handler, body):
    """POST /api/acervo/status {session_id, artifact_id, status}

    Set a package's manifest ``status`` to a UI-permitted value (draft / ready /
    archived), then validate the manifest with the canonical
    validate_artifact_manifest.py. On validation error the change is reverted.
    Non-destructive: only the owned ``status`` field is edited (MOD-007). #82
    """
    try:
        routes.require(body, "session_id", "artifact_id", "status")
    except ValueError as e:
        return routes.bad(handler, str(e))
    new_status = str(body.get("status") or "").strip()
    if new_status not in _ACERVO_UI_STATUSES:
        return routes.bad(handler, "status must be one of: " + ", ".join(sorted(_ACERVO_UI_STATUSES)))
    try:
        s = routes.get_session_for_file_ops(body["session_id"])
    except KeyError:
        return routes.bad(handler, "Session not found", 404)
    artifact_dir = _artifact_dir_for(s, body.get("artifact_id"))
    if artifact_dir is None:
        return routes.bad(handler, "invalid artifact id", 400)
    mf = artifact_dir / "manifest.json"
    if not mf.is_file():
        return routes.j(handler, {"error": "artifact has no manifest"}, status=404)
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as e:
        return routes.j(handler, {"error": "unreadable manifest", "detail": str(e)}, status=500)
    if not isinstance(data, dict):
        return routes.j(handler, {"error": "malformed manifest"}, status=500)
    old_status = data.get("status")
    if old_status == new_status:
        return routes.j(handler, {"ok": True, "status": new_status, "unchanged": True})
    data["status"] = new_status
    try:
        mf.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as e:
        return routes.j(handler, {"error": "failed to write manifest", "detail": str(e)}, status=500)

    # Validate with the canonical tool; revert on hard error (warnings are OK).
    tool = _acervo_tool_path("harness/validate_artifact_manifest.py")
    if tool is not None:
        try:
            proc = subprocess.run(
                [sys.executable, str(tool), str(artifact_dir), "--json"],
                capture_output=True, text=True, timeout=60,
            )
            report = json.loads(proc.stdout) if proc.stdout.strip() else []
            errors = []
            for r in (report or []):
                if isinstance(r, dict) and not r.get("ok"):
                    errors.extend(r.get("errors") or [])
            if errors:
                data["status"] = old_status
                try:
                    mf.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                except OSError:
                    pass
                return routes.j(handler, {"error": "invalid after status change", "errors": errors}, status=400)
        except (subprocess.TimeoutExpired, ValueError, json.JSONDecodeError, OSError):
            # Validator unavailable/erroring — the write already succeeded; don't block.
            pass
    return routes.j(handler, {"ok": True, "status": new_status, "previous": old_status})


def _acervo_root():
    """Resolve the Exocortex acervo root, independent of the session workspace.

    Order: $ACERVO → $EXOCORTEX_HOME/acervo → ~/exocortex/acervo → derived from
    the acervo tool path. Microverse pages live outside the session workspace in
    the general case, so cross-microverse browsing must resolve against this root
    (never the session workspace). (MOD-008)
    """
    acervo = os.environ.get("ACERVO")
    if acervo and Path(acervo).is_dir():
        return Path(acervo)
    exo = os.environ.get("EXOCORTEX_HOME")
    if exo and (Path(exo) / "acervo").is_dir():
        return Path(exo) / "acervo"
    home = Path.home() / "exocortex" / "acervo"
    if home.is_dir():
        return home
    tool = _acervo_tool_path("artifact_publish.py")
    if tool is not None:
        try:
            return tool.parents[2]
        except IndexError:
            pass
    return home


def _humanize_slug(slug):
    """Turn a slug/filename stem into a readable label (display layer only)."""
    s = re.sub(r'[-_]+', ' ', str(slug or '')).strip()
    return (s[:1].upper() + s[1:]) if s else str(slug)


def _read_frontmatter_meta(path, keys):
    """Best-effort extract of scalar frontmatter keys from a markdown/yaml head.

    Reads only the ~4KB head. Returns {key: value} for keys present as top-level
    ``key: value`` lines in the leading ``---`` block (or the head if no block).
    """
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
    except OSError:
        return out
    m = re.match(r'^---\s*\n(.*?)\n---', head, re.DOTALL)
    block = m.group(1) if m else head
    for key in keys:
        mm = re.search(r'^' + re.escape(key) + r':[ \t]*(.+?)[ \t]*$', block, re.MULTILINE)
        if mm:
            val = mm.group(1).strip().strip('"\'')
            if val and val not in ("[]", "{}", "null", "~"):
                out[key] = val
    return out


# Nature subdirectories of a microverse / global / shared layer (MOD-008).
_ACERVO_NATURES = [
    "context", "knowledge", "contracts", "workflows", "decisions",
    "templates", "tools", "skills", "persona", "prompts", "reflections",
]


def _handle_acervo_microverses(handler, parsed):
    """GET /api/acervo/microverses?session_id=...

    List microverses under <acervo_root>/micro/ with friendly identity (from
    _meta/index.md frontmatter → microverso.yaml → humanized slug) and per-Nature
    .md counts. Read-only (MOD-008).
    """
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    if not routes._resolve_session_workspace(sid):
        return routes.bad(handler, "Session not found", 404)
    root = _acervo_root()
    micro_dir = root / "micro"
    out = []
    if micro_dir.is_dir():
        try:
            children = sorted(micro_dir.iterdir(), key=lambda p: p.name)
        except OSError:
            children = []
        for d in children:
            if not d.is_dir() or d.name.startswith(("_", ".")):
                continue
            name = desc = mtype = None
            idx = d / "_meta" / "index.md"
            if idx.is_file():
                meta = _read_frontmatter_meta(idx, ["title", "description", "excrtx_type", "type"])
                name = meta.get("title"); desc = meta.get("description")
                mtype = meta.get("excrtx_type") or meta.get("type")
            if not name:
                yml = d / "microverso.yaml"
                if yml.is_file():
                    ym = _read_frontmatter_meta(yml, ["name", "description", "type"])
                    name = name or ym.get("name"); desc = desc or ym.get("description")
                    mtype = mtype or ym.get("type")
            if name:
                # Strip "Índice —"/"Index —" markers (prefix or suffix) index pages carry.
                name = re.sub(r'^(?:índice|indice|index)\s*[—\-:]\s*', '', name, flags=re.IGNORECASE)
                name = re.sub(r'\s*[—\-:]\s*(?:índice|indice|index)$', '', name, flags=re.IGNORECASE)
                name = name.strip()
                if not name or name == d.name:
                    name = _humanize_slug(d.name)
            if not name:
                name = _humanize_slug(d.name)
            natures = {}
            for nat in _ACERVO_NATURES:
                nd = d / nat
                if nd.is_dir():
                    try:
                        c = sum(1 for f in nd.iterdir() if f.is_file() and f.suffix.lower() == ".md")
                    except OSError:
                        c = 0
                    if c:
                        natures[nat] = c
            out.append({"slug": d.name, "name": name, "description": desc,
                        "type": mtype, "natures": natures})
    return routes.j(handler, {"microverses": out, "count": len(out)})


def _handle_acervo_knowledge(handler, parsed):
    """GET /api/acervo/knowledge?session_id=&scope=micro|global|shared&slug=&nature=

    List knowledge/context pages (friendly titles + metadata) within a microverse
    Nature, or a whole microverse when nature is omitted. Read-only (MOD-008).
    """
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    if not routes._resolve_session_workspace(sid):
        return routes.bad(handler, "Session not found", 404)
    scope = (qs.get("scope", ["micro"])[0] or "micro").strip()
    slug = (qs.get("slug", [""])[0] or "").strip()
    nature = (qs.get("nature", [""])[0] or "").strip()
    root = _acervo_root()
    if scope == "micro":
        if not slug:
            return routes.bad(handler, "slug is required for scope=micro")
        rel_base = "micro/" + slug
    elif scope in ("global", "shared"):
        rel_base = scope
    else:
        return routes.bad(handler, "invalid scope")
    try:
        base = routes.safe_resolve(root, rel_base)
    except ValueError:
        return routes.bad(handler, "invalid path", 400)
    natures = [nature] if nature else _ACERVO_NATURES
    pages = []
    for nat in natures:
        nd = base / nat
        if not nd.is_dir():
            continue
        try:
            files = sorted(nd.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for f in files:
            if not f.is_file() or f.suffix.lower() != ".md" or f.name.startswith("_"):
                continue
            meta = _read_frontmatter_meta(f, ["title", "description", "kind", "class",
                                              "stability", "authority", "type"])
            title = meta.get("title") or _read_frontmatter_title(f) or _humanize_slug(f.stem)
            try:
                rel = str(f.relative_to(root))
            except ValueError:
                rel = f.name
            pages.append({
                "rel_path": rel, "scope": scope, "slug": slug or scope, "nature": nat,
                "title": title, "description": meta.get("description"),
                "kind": meta.get("kind") or meta.get("type"), "class": meta.get("class"),
                "stability": meta.get("stability"), "authority": meta.get("authority"),
            })
    return routes.j(handler, {"pages": pages, "count": len(pages)})


def _handle_acervo_titles(handler, parsed):
    """GET /api/acervo/titles?session_id=&paths=a,b,c

    Batch friendly-title assist for the Sessão view: maps each workspace-relative
    .md path to its frontmatter/heading title (or null). Read-only (MOD-008).
    """
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    workspace = routes._resolve_session_workspace(sid)
    if not workspace:
        return routes.bad(handler, "Session not found", 404)
    raw = qs.get("paths", [""])[0] or ""
    titles = {}
    for p in [x.strip() for x in raw.split(",") if x.strip()][:200]:
        if not p.lower().endswith(".md"):
            titles[p] = None
            continue
        try:
            fp = routes.safe_resolve(Path(workspace), p)
        except ValueError:
            titles[p] = None
            continue
        titles[p] = _read_frontmatter_title(fp) if fp.is_file() else None
    return routes.j(handler, {"titles": titles})


def _handle_acervo_stage_context(handler, body):
    """POST /api/acervo/stage-context {session_id, scope, slug, nature, rel_path|source}

    Copy a chosen acervo page into the session's attachment dir and return an
    attachment object ({name,path,mime,size,is_image}) for the chat composer, so
    it rides along with the next message via the existing attachments pipeline.
    Read-only on the acervo (copies out); same trust boundary as user uploads. (MOD-008)
    """
    import mimetypes as _mt
    try:
        routes.require(body, "session_id")
    except ValueError as e:
        return routes.bad(handler, str(e))
    sid = body["session_id"]
    try:
        routes.get_session_for_file_ops(sid)
    except KeyError:
        return routes.bad(handler, "Session not found", 404)
    source = (body.get("source") or body.get("rel_path") or "").strip()
    if not source:
        return routes.bad(handler, "source or rel_path is required")
    root = _acervo_root()
    try:
        src = routes.safe_resolve(root, source)
    except ValueError:
        return routes.bad(handler, "invalid source path", 400)
    if not src.is_file():
        return routes.j(handler, {"error": "source not found"}, status=404)
    try:
        if src.stat().st_size > 5 * 1024 * 1024:
            return routes.j(handler, {"error": "file too large for context (max 5MB)"}, status=413)
    except OSError:
        return routes.j(handler, {"error": "source not readable"}, status=500)
    from api.upload import _upload_destination, _sanitize_upload_name
    try:
        dest = _upload_destination(sid, _sanitize_upload_name(src.name))
        dest.write_bytes(src.read_bytes())
    except (OSError, ValueError) as e:
        return routes.j(handler, {"error": "failed to stage file", "detail": str(e)}, status=500)
    mime = _mt.guess_type(dest.name)[0] or "text/markdown"
    return routes.j(handler, {"name": dest.name, "path": str(dest),
                       "size": dest.stat().st_size, "mime": mime,
                       "is_image": mime.startswith("image/")})


def _handle_artifact_zip(handler, parsed):
    """GET /api/artifact/zip?session_id=...&id=...

    Stream a zip of the artifact package <workspace>/_artifacts/items/<id>/,
    including ONLY the deliverable parts: source/, exports/ and manifest.json.
    Internal provenance (receipts/, revisions/) is intentionally excluded. #84
    """
    import zipfile

    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    try:
        s = routes.get_session_for_file_ops(sid)
    except KeyError:
        return routes.bad(handler, "Session not found", 404)

    art_id = (qs.get("id", [""])[0] or "").strip().strip("/")
    if not art_id or "/" in art_id or art_id in (".", ".."):
        return routes.bad(handler, "invalid artifact id", 400)
    rel = "_artifacts/items/" + art_id
    try:
        target = routes.safe_resolve(Path(s.workspace), rel)
    except ValueError:
        return routes.bad(handler, "invalid path", 400)
    if not target.exists() or not target.is_dir():
        return routes.j(handler, {"error": "artifact not found"}, status=404)

    workspace_root = Path(s.workspace).resolve()
    files, _total, limit_hit = routes._folder_download_collect(
        target, workspace_root, routes._folder_zip_max_bytes(), routes._folder_zip_max_files()
    )
    if limit_hit:
        return routes.j(handler, {"error": "artifact too large", "reason": limit_hit}, status=413)

    # Keep only the deliverable parts; drop receipts/, revisions/, etc. (#84)
    def _is_deliverable(arc: str) -> bool:
        a = arc.replace("\\", "/")
        return a == "manifest.json" or a.startswith("source/") or a.startswith("exports/")

    files = [(fp, arc) for (fp, arc) in files if _is_deliverable(arc)]

    zip_name = art_id + ".zip"
    handler.send_response(200)
    handler.send_header("Content-Type", "application/zip")
    handler.send_header("Content-Disposition", routes._content_disposition_value("attachment", zip_name))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Connection", "close")
    handler.end_headers()

    with zipfile.ZipFile(handler.wfile, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for fp, arcname in files:
            fd = None
            try:
                fd = routes.open_anchored_fd(workspace_root, fp.resolve(), want_dir=False)
                info = zipfile.ZipInfo(arcname)
                info.compress_type = zipfile.ZIP_DEFLATED
                with os.fdopen(fd, "rb", closefd=True) as src:
                    fd = None
                    with zf.open(info, "w") as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
            except (ValueError, OSError, PermissionError) as e:
                routes.logger.warning("artifact-zip: skipping %s: %s", fp, e)
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass


def _acervo_tool_path(name):
    """Locate an Exocortex Acervo tool (e.g. artifact_publish.py).

    Resolution order: $ACERVO/global/tools, $EXOCORTEX_HOME/acervo/global/tools,
    then ~/exocortex/acervo/global/tools. Returns a Path or None. #82
    """
    candidates = []
    acervo = os.environ.get("ACERVO")
    if acervo:
        candidates.append(Path(acervo) / "global" / "tools" / name)
    exo = os.environ.get("EXOCORTEX_HOME")
    if exo:
        candidates.append(Path(exo) / "acervo" / "global" / "tools" / name)
    candidates.append(Path.home() / "exocortex" / "acervo" / "global" / "tools" / name)
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def _artifact_dir_for(session, art_id):
    """Resolve and validate <workspace>/_artifacts/items/<id>. Returns Path or None."""
    art_id = str(art_id or "").strip().strip("/")
    if not art_id or "/" in art_id or art_id in (".", ".."):
        return None
    try:
        return routes.safe_resolve(Path(session.workspace), "_artifacts/items/" + art_id)
    except ValueError:
        return None


def _handle_artifact_publish(handler, body):
    """POST /api/artifact/publish {session_id, artifact_id}

    Publish an artifact to Google Drive via the deterministic publisher at
    $ACERVO/global/tools/artifact_publish.py. Returns {status, drive_link,
    receipt}. Draft-First note: this is an explicit, user-triggered publish. #82
    """
    try:
        routes.require(body, "session_id", "artifact_id")
    except ValueError as e:
        return routes.bad(handler, str(e))
    try:
        s = routes.get_session_for_file_ops(body["session_id"])
    except KeyError:
        return routes.bad(handler, "Session not found", 404)
    artifact_dir = _artifact_dir_for(s, body.get("artifact_id"))
    if artifact_dir is None:
        return routes.bad(handler, "invalid artifact id", 400)
    if not artifact_dir.is_dir():
        return routes.j(handler, {"error": "artifact not found"}, status=404)
    tool = _acervo_tool_path("artifact_publish.py")
    if tool is None:
        return routes.j(handler, {"error": "artifact_publish.py not found; set ACERVO or EXOCORTEX_HOME"}, status=503)
    try:
        proc = subprocess.run(
            [sys.executable, str(tool), "publish", "--artifact-dir", str(artifact_dir)],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        return routes.j(handler, {"error": "publish timed out"}, status=504)
    if proc.returncode != 0:
        return routes.j(handler, {
            "error": "publish failed",
            "detail": (proc.stderr or proc.stdout or "").strip()[-2000:],
        }, status=502)
    try:
        result = json.loads(proc.stdout)
    except (ValueError, json.JSONDecodeError):
        result = {"raw": proc.stdout.strip()[-2000:]}
    drive_link = ""
    status = "published"
    if isinstance(result, dict):
        status = result.get("status", "published")
        drive_link = result.get("folder_link") or result.get("web_view_link") or ""
        files = result.get("files") or result.get("published_files") or []
        if not drive_link and isinstance(files, list) and files and isinstance(files[0], dict):
            drive_link = files[0].get("webViewLink", "")
    return routes.j(handler, {"ok": True, "status": status, "drive_link": drive_link, "receipt": result})


def _handle_artifact_receipt(handler, parsed):
    """GET /api/artifact/receipt?session_id=...&id=...

    Return the parsed receipts/receipt.google_drive.json for a published
    artifact (web_view_link / folder_path live inside). #82
    """
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    try:
        s = routes.get_session_for_file_ops(sid)
    except KeyError:
        return routes.bad(handler, "Session not found", 404)
    artifact_dir = _artifact_dir_for(s, qs.get("id", [""])[0])
    if artifact_dir is None:
        return routes.bad(handler, "invalid artifact id", 400)
    rcpt = artifact_dir / "receipts" / "receipt.google_drive.json"
    if not rcpt.is_file():
        return routes.j(handler, {"error": "no receipt"}, status=404)
    try:
        data = json.loads(rcpt.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as e:
        return routes.bad(handler, routes._sanitize_error(e), 500)
    return routes.j(handler, {"ok": True, "receipt": data})




def _handle_inbox_status(handler, parsed):
    """GET /api/inbox/status?session_id=...&dir=_inbox

    Count regular files directly under the inbox dir (default ``_inbox``),
    newest first. Powers the tree badge and the inbox panel. A missing inbox
    dir is reported as an empty inbox, not an error.
    """
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    workspace = routes._resolve_session_workspace(sid)
    if workspace is None:
        return routes.bad(handler, "Session not found", 404)
    inbox_rel = qs.get("dir", ["_inbox"])[0]
    try:
        entries = routes.list_dir(Path(workspace), inbox_rel)
    except (FileNotFoundError, ValueError):
        return routes.j(handler, {"count": 0, "files": [], "dir": inbox_rel})
    files = [e for e in entries if e.get("type") == "file"]
    files.sort(key=lambda e: e.get("mtime_ns") or 0, reverse=True)
    return routes.j(
        handler,
        {
            "count": len(files),
            "files": [
                {
                    "name": e["name"],
                    "path": e["path"],
                    "size": e.get("size"),
                    "mtime_ns": e.get("mtime_ns"),
                }
                for e in files
            ],
            "dir": inbox_rel,
        },
    )


def _handle_inbox_move(handler, body):
    """POST /api/inbox/move {session_id, path, dest_dir}

    Move a file out of the inbox into a destination folder (microverso).
    The source must live under the inbox dir — defense in depth, since the UI
    only offers inbox files. Confirmation is enforced in the UI; the backend
    never moves on its own. The race-safe move itself is delegated to the
    shared file-move handler so both paths share one validated implementation.
    """
    try:
        routes.require(body, "session_id", "path", "dest_dir")
    except ValueError as e:
        return routes.bad(handler, str(e))
    inbox_rel = (body.get("inbox_dir") or "_inbox").strip("/")
    norm = str(body.get("path") or "").strip().lstrip("/")
    if not (norm == inbox_rel or norm.startswith(inbox_rel + "/")):
        return routes.bad(handler, f"path must be inside {inbox_rel}/")
    return routes._handle_file_move(handler, body)



# ── HW-1 dispatchers: single acervo/artifact/inbox entry from routes.py ──────

def handle_acervo_get(handler, parsed):
    """GET dispatcher for the Acervo tab (MOD-007/008), the MOD-008 inbox and
    the /x/ prefix (MOD-009/010 Explorer/Studio). True when handled."""
    p = parsed.path
    if p == "/api/artifact/zip":
        return _handle_artifact_zip(handler, parsed)
    if p == "/api/acervo/artifacts":
        return _handle_acervo_artifacts(handler, parsed)
    if p == "/api/acervo/microverses":
        return _handle_acervo_microverses(handler, parsed)
    if p == "/api/acervo/knowledge":
        return _handle_acervo_knowledge(handler, parsed)
    if p == "/api/acervo/titles":
        return _handle_acervo_titles(handler, parsed)
    if p == "/api/artifact/receipt":
        return _handle_artifact_receipt(handler, parsed)
    if p == "/api/inbox/status":
        return _handle_inbox_status(handler, parsed)
    if p.startswith("/api/acervo/x/"):
        import api.acervo_explorer as ax
        return ax.handle_acervo_x_get(handler, parsed)
    return False


def handle_acervo_post(handler, path, body):
    """POST dispatcher (mirror of handle_acervo_get)."""
    if path == "/api/artifact/publish":
        return _handle_artifact_publish(handler, body)
    if path == "/api/acervo/status":
        return _handle_acervo_status(handler, body)
    if path == "/api/acervo/stage-context":
        return _handle_acervo_stage_context(handler, body)
    if path == "/api/inbox/move":
        return _handle_inbox_move(handler, body)
    if path.startswith("/api/acervo/x/"):
        import api.acervo_explorer as ax
        return ax.handle_acervo_x_post(handler, body)
    return False


import api.routes as routes  # noqa: E402  (bottom import — see module docstring)
