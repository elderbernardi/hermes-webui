# region: imports + module docstring                  (T1)
"""Acervo Explorer backend — MOD-009 (prefix /api/acervo/x/).

Premium semantic file-explorer for the Exocórtex acervo. All paths resolve
against ``_acervo_root()`` (never the session workspace) and pass through
``_safe_acervo_path`` for traversal/symlink/dotfile safety. This is the first
*write-coupling* MOD: it can edit page body + frontmatter, move/rename, set
status, edit tags and stage a page into the chat composer. It can NOT create or
delete, and ``.quarantine/`` is entirely off-limits (any path component starting
with ``.`` is rejected).

Self-contained / rebase-safe: lives in this NEW file. ``api/routes.py`` only
gains two 3-line dispatch blocks (SPEC §5). All heavy reuse (acervo root,
frontmatter helpers, manifest-status validation, stage-context, response
helpers) is done through late ``import api.routes as routes`` inside functions
to avoid a circular import at module load (mirrors ``_handle_acervo_stage_context``).
"""

import os
import re
import datetime
import yaml
from pathlib import Path
from urllib.parse import parse_qs


def _json_safe(value):
    """Coerce a yaml.safe_load result into JSON-serializable types. YAML parses
    unquoted dates (e.g. ``created: 2026-06-21``) into ``datetime.date`` objects
    which json.dumps cannot encode — convert those (and nested ones) to ISO
    strings so the frontmatter survives the /page response."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


# region: path safety  (_safe_acervo_path)            (T1)

def _safe_acervo_path(rel, *, require_md=False):
    """Resolve an acervo-relative path safely, mirroring ``safe_resolve_ws``.

    Anchored on ``_acervo_root()``. Rejects:
      * empty or absolute ``rel``
      * ``..`` traversal / symlink escape (via ``resolved.relative_to(root)``)
      * any path component starting with ``.`` (blocks ``.quarantine/``, ``.git/``)
      * non-``.md`` paths when ``require_md`` (save/tags/status-page)

    Raises ``ValueError("acervo path blocked")`` on any violation; callers
    translate that to ``bad(handler, ..., 400)``.
    """
    import api.routes as routes
    if rel is None:
        raise ValueError("acervo path blocked")
    rel = str(rel).strip()
    if not rel:
        raise ValueError("acervo path blocked")
    if os.path.isabs(rel) or rel.startswith("/") or rel.startswith("\\"):
        raise ValueError("acervo path blocked")

    # Reject any component starting with '.' (covers '.', '..', '.quarantine', '.git').
    parts = re.split(r"[\\/]+", rel)
    for part in parts:
        if not part:
            continue
        if part.startswith("."):
            raise ValueError("acervo path blocked")

    if require_md and not rel.lower().endswith(".md"):
        raise ValueError("acervo path blocked")

    root = routes._acervo_root()
    root_r = root.resolve()
    resolved = (root / rel).resolve()  # collapses symlinks
    try:
        resolved.relative_to(root_r)
    except ValueError:
        raise ValueError("acervo path blocked")
    return resolved


# region: frontmatter  (_split_fm, _merge_fm, _dump)  (T4)

_FM_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)

# Frontmatter timestamp fields auto-bumped on save ONLY when already present.
_FM_TIMESTAMP_KEYS = ("last_accessed_at", "timestamp", "updated")


def _split_fm(raw):
    """Split a raw markdown document into (frontmatter_dict, body_str).

    Returns ``({}, raw)`` when there is no leading ``---`` block or the block is
    not a YAML mapping. ``body`` is the text after the closing ``---`` (with one
    leading blank line stripped) so reassembly stays idempotent.
    """
    m = _FM_RE.match(raw or "")
    if not m:
        return {}, (raw or "")
    block = m.group(1)
    body = raw[m.end():]
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return {}, (raw or "")
    if not isinstance(data, dict):
        return {}, (raw or "")
    return data, body


def _dump_fm(data):
    """YAML-dump a frontmatter dict, preserving key order and unicode."""
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _now_iso():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _reassemble(fm, body):
    """Reassemble ``---\\n{yaml}---\\n\\n{body}`` from a frontmatter dict + body."""
    body = body or ""
    # Normalize so there is exactly one blank line between frontmatter and body.
    body = body.lstrip("\n")
    yaml_text = _dump_fm(fm) if fm else ""
    if not yaml_text.endswith("\n"):
        yaml_text += "\n"
    return "---\n" + yaml_text + "---\n\n" + body


def _atomic_write(target: Path, text: str):
    """Atomic write: temp sibling + ``os.replace``."""
    tmp = target.with_name(target.name + ".tmp." + str(os.getpid()))
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, target)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _save_page_frontmatter(target: Path, fm_updates, body=None):
    """Merge supplied frontmatter keys into the existing page and write atomically.

    OKF preservation: loads the FULL existing frontmatter dict and overwrites
    only the keys present in ``fm_updates``. Auto-bumps any of
    ``last_accessed_at``/``timestamp``/``updated`` ONLY if already present. When
    ``body`` is None the existing body is preserved. Returns the merged fm dict.
    """
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        raw = ""
    existing_fm, existing_body = _split_fm(raw)
    merged = dict(existing_fm)
    if fm_updates:
        for k, v in fm_updates.items():
            merged[k] = v
    now = _now_iso()
    for k in _FM_TIMESTAMP_KEYS:
        if k in merged:
            merged[k] = now
    new_body = existing_body if body is None else body
    _atomic_write(target, _reassemble(merged, new_body))
    return merged


# region: read handlers (tree, page, search)          (T2 tree+page, T3 search)

_MAX_PAGE_BYTES = 5 * 1024 * 1024  # mirror the 5 MB guard (routes.py:12457)
_MAX_RAW_BYTES = 50 * 1024 * 1024  # binary preview (pdf/image) upper bound
_BODY_SCAN_BYTES = 256 * 1024      # per-file cap for full-text search fallback


def _body_snippet(path, q_lower):
    """Bounded full-text search of a page. Returns a snippet (original case)
    around the first match, or None. Reads at most _BODY_SCAN_BYTES per file so a
    content-only term (present in the prose but not the title/tags) is still
    found. Only invoked when the metadata match misses, keeping cost bounded."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read(_BODY_SCAN_BYTES)
    except OSError:
        return None
    idx = text.lower().find(q_lower)
    if idx < 0:
        return None
    start = max(0, idx - 60)
    end = min(len(text), idx + len(q_lower) + 100)
    snip = " ".join(text[start:end].split())
    return ("…" if start > 0 else "") + snip + ("…" if end < len(text) else "")


def _rel_to_root(p: Path, root: Path):
    try:
        return str(p.relative_to(root.resolve()))
    except ValueError:
        return p.name


def _node_for_page(routes, f: Path, root: Path, nature=None, scope=None):
    """Build a page node (friendly title + metadata) for tree/list responses."""
    meta = routes._read_frontmatter_meta(
        f, ["title", "description", "status", "nature", "class", "kind", "type"])
    title = meta.get("title") or routes._read_frontmatter_title(f) or routes._humanize_slug(f.stem)
    return {
        "type": "page",
        "rel_path": _rel_to_root(f, root),
        "title": title,
        "status": meta.get("status"),
        "nature": meta.get("nature") or nature,
        "description": meta.get("description"),
        "class": meta.get("class"),
        "kind": meta.get("kind") or meta.get("type"),
        "scope": scope,
    }


def handle_tree(handler, parsed):
    """GET /api/acervo/x/tree — browse global/shared/macro + artifacts (SPEC §3.1)."""
    import api.routes as routes
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    if not routes._resolve_session_workspace(sid):
        return routes.bad(handler, "Session not found", 404)
    scope = (qs.get("scope", [""])[0] or "").strip()
    if scope not in ("global", "shared", "macro", "artifacts"):
        return routes.bad(handler, "scope must be one of: global, shared, macro, artifacts")
    slug = (qs.get("slug", [""])[0] or "").strip()
    try:
        depth = int(qs.get("depth", ["1"])[0] or "1")
    except ValueError:
        depth = 1
    depth = max(1, min(depth, 3))

    root = routes._acervo_root()

    if scope == "artifacts":
        # Delegate to the existing artifact catalog idiom via the natures-free
        # listing under _artifacts/items — surface as page-like nodes.
        nodes = []
        try:
            base = _safe_acervo_path("_artifacts/items")
        except ValueError:
            base = None
        if base and base.is_dir():
            try:
                children = sorted(base.iterdir(), key=lambda p: p.name, reverse=True)
            except OSError:
                children = []
            for child in children:
                if child.name.startswith("."):
                    continue
                nodes.append({
                    "type": "artifact",
                    "rel_path": _rel_to_root(child, root),
                    "name": child.name,
                    "title": routes._humanize_slug(child.stem if child.is_file() else child.name),
                })
        return routes.j(handler, {"scope": scope, "root": "_artifacts/items",
                                  "nodes": nodes, "count": len(nodes)})

    if scope == "macro":
        rel_base = "macro" + ("/" + slug if slug else "")
    else:
        rel_base = scope

    try:
        base = _safe_acervo_path(rel_base)
    except ValueError:
        return routes.bad(handler, "invalid path", 400)

    nodes = []
    if base.is_dir():
        natures = routes._ACERVO_NATURES
        for nat in natures:
            nd = base / nat
            if not nd.is_dir():
                continue
            try:
                files = [f for f in nd.iterdir()
                         if f.is_file() and f.suffix.lower() == ".md"
                         and not f.name.startswith(("_", "."))]
            except OSError:
                files = []
            nodes.append({
                "type": "nature",
                "name": nat,
                "rel_path": _rel_to_root(nd, root),
                "count": len(files),
            })
            if depth >= 2:
                for f in sorted(files, key=lambda p: p.name):
                    nodes.append(_node_for_page(routes, f, root, nature=nat, scope=scope))
    return routes.j(handler, {"scope": scope, "root": rel_base,
                              "nodes": nodes, "count": len(nodes)})


def handle_page(handler, parsed):
    """GET /api/acervo/x/page — read a single page (SPEC §3.2)."""
    import api.routes as routes
    import mimetypes as _mt
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    if not routes._resolve_session_workspace(sid):
        return routes.bad(handler, "Session not found", 404)
    rel = (qs.get("path", [""])[0] or "").strip()
    try:
        target = _safe_acervo_path(rel)
    except ValueError:
        return routes.bad(handler, "invalid path", 400)
    if not target.is_file():
        return routes.j(handler, {"error": "page not found"}, status=404)

    is_md = target.suffix.lower() == ".md"
    if not is_md:
        # Non-md (pdf/image): no inline edit; point at a (future) raw stream.
        mime = _mt.guess_type(target.name)[0] or "application/octet-stream"
        return routes.j(handler, {
            "rel_path": _rel_to_root(target, routes._acervo_root()),
            "raw_url": "/api/acervo/x/raw?session_id=" + sid + "&path=" + rel,
            "mime": mime,
            "editable": False,
        })

    try:
        size = target.stat().st_size
    except OSError:
        return routes.j(handler, {"error": "page not readable"}, status=500)
    if size > _MAX_PAGE_BYTES:
        return routes.j(handler, {"error": "page too large (max 5MB)"}, status=413)
    try:
        raw = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return routes.j(handler, {"error": "page not readable"}, status=500)
    fm, body = _split_fm(raw)
    title = (fm.get("title") if isinstance(fm, dict) else None) \
        or routes._read_frontmatter_title(target) or routes._humanize_slug(target.stem)
    return routes.j(handler, {
        "rel_path": _rel_to_root(target, routes._acervo_root()),
        "title": title,
        "frontmatter": _json_safe(fm),
        "body": body,
        "raw_size": size,
        "editable": True,
    })


def handle_search(handler, parsed):
    """GET /api/acervo/x/search — bounded metadata search (SPEC §3.3)."""
    import api.routes as routes
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    if not routes._resolve_session_workspace(sid):
        return routes.bad(handler, "Session not found", 404)

    q = (qs.get("q", [""])[0] or "").strip().lower()
    f_nature = (qs.get("nature", [""])[0] or "").strip()
    f_status = (qs.get("status", [""])[0] or "").strip()
    f_micro = (qs.get("microverso", [""])[0] or "").strip()
    f_tag = (qs.get("tag", [""])[0] or "").strip().lower()

    root = routes._acervo_root()
    natures = [f_nature] if f_nature else routes._ACERVO_NATURES

    # Build the list of base layers to walk.
    bases = []
    for layer in ("global", "shared"):
        bases.append(root / layer)
    micro_dir = root / "micro"
    if f_micro:
        bases.append(micro_dir / f_micro)
    elif micro_dir.is_dir():
        try:
            for d in sorted(micro_dir.iterdir(), key=lambda p: p.name):
                if d.is_dir() and not d.name.startswith(("_", ".")):
                    bases.append(d)
        except OSError:
            pass

    MAX_SCANNED = 5000
    MAX_RESULTS = 200
    scanned = 0
    truncated = False
    results = []

    for base in bases:
        if not base.is_dir():
            continue
        for nat in natures:
            nd = base / nat
            if not nd.is_dir():
                continue
            try:
                entries = sorted(nd.iterdir(), key=lambda p: p.name)
            except OSError:
                continue
            for f in entries:
                if not f.is_file() or f.suffix.lower() != ".md" or f.name.startswith(("_", ".")):
                    continue
                if scanned >= MAX_SCANNED:
                    truncated = True
                    break
                scanned += 1
                meta = routes._read_frontmatter_meta(
                    f, ["title", "description", "status", "nature", "tags"])
                status = meta.get("status")
                if f_status and status != f_status:
                    continue
                tags_raw = meta.get("tags") or ""
                tags = [t.strip().strip('"\'') for t in re.split(r"[,\[\]]+", tags_raw) if t.strip()]
                if f_tag and f_tag not in [t.lower() for t in tags]:
                    continue
                title = meta.get("title") or routes._read_frontmatter_title(f) or routes._humanize_slug(f.stem)
                desc = meta.get("description") or ""
                score = 0
                snippet = ""
                if q:
                    if q in title.lower():
                        score += 5
                    if q in desc.lower():
                        score += 3
                        snippet = desc[:200]
                    if q in f.name.lower():
                        score += 2
                    if q in " ".join(tags).lower():
                        score += 3
                    if score == 0:
                        # Metadata missed — fall back to a bounded full-text body
                        # scan so content-only terms are still found (e.g. a word
                        # that appears only in the page prose).
                        body_hit = _body_snippet(f, q)
                        if body_hit is None:
                            continue
                        score = 1
                        snippet = snippet or body_hit
                else:
                    score = 1
                results.append({
                    "rel_path": _rel_to_root(f, root),
                    "title": title,
                    "nature": meta.get("nature") or nat,
                    "status": status,
                    "tags": tags,
                    "score": score,
                    "snippet": snippet,
                })
                if len(results) >= MAX_RESULTS:
                    truncated = True
                    break
            if truncated:
                break
        if truncated:
            break

    results.sort(key=lambda r: (-r["score"], r["rel_path"]))
    return routes.j(handler, {"results": results, "count": len(results),
                              "truncated": truncated})


def handle_raw(handler, parsed):
    """GET /api/acervo/x/raw — stream a non-md acervo file (pdf/image) for preview."""
    import api.routes as routes
    import mimetypes as _mt
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return routes.bad(handler, "session_id is required")
    if not routes._resolve_session_workspace(sid):
        return routes.bad(handler, "Session not found", 404)
    rel = (qs.get("path", [""])[0] or "").strip()
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
    if size > _MAX_RAW_BYTES:
        return routes.j(handler, {"error": "file too large"}, status=413)
    try:
        data = target.read_bytes()
    except OSError:
        return routes.j(handler, {"error": "file not readable"}, status=500)
    mime = _mt.guess_type(target.name)[0] or "application/octet-stream"
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(data)))
    # Defense-in-depth: acervo files may be SVG/HTML; sandbox + nosniff so a direct
    # navigation can't run privileged same-origin script (mirrors the plugin-asset
    # serving pattern in routes.py).
    handler.send_header("Content-Security-Policy", "sandbox allow-scripts allow-popups")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(data)
    return True


# region: write handlers (save, tags, move, status, stage) (T4 save+tags, T5 move+status+stage)

def handle_save(handler, body):
    """POST /api/acervo/x/save — edit body + frontmatter (SPEC §3.4)."""
    import api.routes as routes
    try:
        routes.require(body, "session_id", "path")
    except ValueError as e:
        return routes.bad(handler, str(e))
    try:
        routes.get_session_for_file_ops(body["session_id"])
    except KeyError:
        return routes.bad(handler, "Session not found", 404)
    try:
        target = _safe_acervo_path(body.get("path"), require_md=True)
    except ValueError:
        return routes.bad(handler, "invalid path", 400)
    if not target.is_file():
        return routes.j(handler, {"error": "page not found"}, status=404)

    fm_updates = body.get("frontmatter")
    if fm_updates is not None and not isinstance(fm_updates, dict):
        return routes.bad(handler, "frontmatter must be an object")
    fm_updates = dict(fm_updates or {})
    if "status" in fm_updates and fm_updates["status"] is not None:
        if str(fm_updates["status"]) not in routes._ACERVO_UI_STATUSES:
            return routes.bad(handler, "status must be one of: "
                              + ", ".join(sorted(routes._ACERVO_UI_STATUSES)))

    body_text = body.get("body")  # None => preserve existing body
    try:
        _save_page_frontmatter(target, fm_updates, body=body_text)
    except OSError as e:
        return routes.j(handler, {"error": "failed to write page", "detail": str(e)}, status=500)
    return routes.j(handler, {"ok": True,
                              "rel_path": _rel_to_root(target, routes._acervo_root())})


def handle_tags(handler, body):
    """POST /api/acervo/x/tags — add/remove frontmatter tags (SPEC §3.7)."""
    import api.routes as routes
    try:
        routes.require(body, "session_id", "path")
    except ValueError as e:
        return routes.bad(handler, str(e))
    try:
        routes.get_session_for_file_ops(body["session_id"])
    except KeyError:
        return routes.bad(handler, "Session not found", 404)
    try:
        target = _safe_acervo_path(body.get("path"), require_md=True)
    except ValueError:
        return routes.bad(handler, "invalid path", 400)
    if not target.is_file():
        return routes.j(handler, {"error": "page not found"}, status=404)

    add = body.get("add") or []
    remove = body.get("remove") or []
    if not isinstance(add, list) or not isinstance(remove, list):
        return routes.bad(handler, "add/remove must be arrays")
    add = [str(t).strip() for t in add if str(t).strip()]
    remove_set = {str(t).strip() for t in remove if str(t).strip()}

    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as e:
        return routes.j(handler, {"error": "page not readable", "detail": str(e)}, status=500)
    fm, _ = _split_fm(raw)
    cur = fm.get("tags")
    if cur is None:
        tags = []
    elif isinstance(cur, list):
        tags = [str(t) for t in cur]
    else:
        tags = [str(cur)]
    for t in add:
        if t not in tags:
            tags.append(t)
    tags = [t for t in tags if t not in remove_set]

    try:
        _save_page_frontmatter(target, {"tags": tags}, body=None)
    except OSError as e:
        return routes.j(handler, {"error": "failed to write page", "detail": str(e)}, status=500)
    return routes.j(handler, {"ok": True, "tags": tags})


def handle_move(handler, body):
    """POST /api/acervo/x/move — move/rename a page (SPEC §3.5)."""
    import api.routes as routes
    try:
        routes.require(body, "session_id", "path", "dest")
    except ValueError as e:
        return routes.bad(handler, str(e))
    try:
        routes.get_session_for_file_ops(body["session_id"])
    except KeyError:
        return routes.bad(handler, "Session not found", 404)
    try:
        src = _safe_acervo_path(body.get("path"))
        dest = _safe_acervo_path(body.get("dest"))
    except ValueError:
        return routes.bad(handler, "invalid path", 400)
    if not src.is_file():
        return routes.j(handler, {"error": "source not found"}, status=404)
    if dest.exists():
        return routes.bad(handler, "destination already exists", 409)
    if not dest.parent.is_dir():
        return routes.bad(handler, "destination parent does not exist", 400)
    try:
        os.replace(src, dest)
    except OSError as e:
        return routes.j(handler, {"error": "failed to move page", "detail": str(e)}, status=500)
    return routes.j(handler, {"ok": True,
                              "rel_path": _rel_to_root(dest, routes._acervo_root())})


def handle_status(handler, body):
    """POST /api/acervo/x/status — artifact OR page status (SPEC §3.6)."""
    import api.routes as routes
    # Artifact case: delegate verbatim to the existing manifest-status handler.
    if body.get("artifact_id"):
        return routes._handle_acervo_status(handler, body)

    # Page case: frontmatter status via the save path, constrained to UI set.
    try:
        routes.require(body, "session_id", "path", "status")
    except ValueError as e:
        return routes.bad(handler, str(e))
    try:
        routes.get_session_for_file_ops(body["session_id"])
    except KeyError:
        return routes.bad(handler, "Session not found", 404)
    new_status = str(body.get("status") or "").strip()
    if new_status not in routes._ACERVO_UI_STATUSES:
        return routes.bad(handler, "status must be one of: "
                          + ", ".join(sorted(routes._ACERVO_UI_STATUSES)))
    try:
        target = _safe_acervo_path(body.get("path"), require_md=True)
    except ValueError:
        return routes.bad(handler, "invalid path", 400)
    if not target.is_file():
        return routes.j(handler, {"error": "page not found"}, status=404)
    try:
        _save_page_frontmatter(target, {"status": new_status}, body=None)
    except OSError as e:
        return routes.j(handler, {"error": "failed to write page", "detail": str(e)}, status=500)
    return routes.j(handler, {"ok": True,
                              "rel_path": _rel_to_root(target, routes._acervo_root()),
                              "status": new_status})


def handle_stage(handler, body):
    """POST /api/acervo/x/stage — stage a page into the chat composer (SPEC §3.8)."""
    import api.routes as routes
    # _handle_acervo_stage_context already accepts {session_id, source}.
    return routes._handle_acervo_stage_context(handler, body)


# region: dispatchers (handle_acervo_x_get/post)      (T1 stub; T2–T5 wire sub-paths)

def handle_acervo_x_get(handler, parsed):
    """Route GET sub-paths under /api/acervo/x/."""
    import api.routes as routes
    path = parsed.path
    if path == "/api/acervo/x/tree":
        return handle_tree(handler, parsed)
    if path == "/api/acervo/x/page":
        return handle_page(handler, parsed)
    if path == "/api/acervo/x/search":
        return handle_search(handler, parsed)
    if path == "/api/acervo/x/raw":
        return handle_raw(handler, parsed)
    return routes.bad(handler, "unknown acervo explorer endpoint", 404)


def handle_acervo_x_post(handler, body):
    """Route POST sub-paths under /api/acervo/x/."""
    import api.routes as routes
    handler_path = getattr(handler, "path", "") or ""
    # Strip any query string defensively.
    path = handler_path.split("?", 1)[0]
    if path == "/api/acervo/x/save":
        return handle_save(handler, body)
    if path == "/api/acervo/x/move":
        return handle_move(handler, body)
    if path == "/api/acervo/x/status":
        return handle_status(handler, body)
    if path == "/api/acervo/x/tags":
        return handle_tags(handler, body)
    if path == "/api/acervo/x/stage":
        return handle_stage(handler, body)
    return routes.bad(handler, "unknown acervo explorer endpoint", 404)
