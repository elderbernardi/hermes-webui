"""EXCRTX MOD-011 (spike F0) — endpoints /api/canvas/* (prefix dispatch, padrão MOD-009/010)."""
from __future__ import annotations

import json
import queue
import threading
from urllib.parse import parse_qs

from api import canvas_store
from api.canvas_enquadrador import enquadrar

CANVAS_STREAMS: dict[str, queue.Queue] = {}
_LOCK = threading.Lock()


def _j(handler, obj, status=200):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _run_enquadrador(canvas_id: str, texto: str, q: queue.Queue) -> None:
    core, errors = enquadrar(texto)
    ops = canvas_store.core_to_patch(core)
    if ops:
        canvas = canvas_store.load_canvas(canvas_id)
        canvas_store.save_canvas(canvas_id, canvas_store.apply_patch(canvas, ops))
        q.put(("canvas_delta", ops))
    q.put(("canvas_done", {"valid": not errors, "errors": errors}))


def handle_canvas_post(handler, path: str, body: dict) -> bool:
    if path != "/api/canvas/draft":
        return False
    texto = (body.get("text") or "").strip()
    if not texto:
        _j(handler, {"error": "text obrigatório"}, 400)
        return True
    canvas_id, canvas = canvas_store.create_draft(texto)
    q: queue.Queue = queue.Queue()
    with _LOCK:
        CANVAS_STREAMS[canvas_id] = q
    q.put(("canvas_snapshot", canvas))
    threading.Thread(target=_run_enquadrador, args=(canvas_id, texto, q),
                     daemon=True).start()
    _j(handler, {"canvas_id": canvas_id})
    return True


def handle_canvas_get(handler, parsed) -> bool:
    if parsed.path == "/api/canvas/get":
        cid = (parse_qs(parsed.query).get("canvas_id") or [""])[0]
        try:
            _j(handler, canvas_store.load_canvas(cid))
        except Exception as exc:
            _j(handler, {"error": str(exc)}, 404)
        return True
    if parsed.path != "/api/canvas/stream":
        return False
    cid = (parse_qs(parsed.query).get("canvas_id") or [""])[0]
    with _LOCK:
        q = CANVAS_STREAMS.get(cid)
    if q is None:
        _j(handler, {"error": "stream desconhecido"}, 404)
        return True
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    try:
        while True:
            try:
                name, payload = q.get(timeout=30)
            except queue.Empty:
                handler.wfile.write(b": heartbeat\n\n")
                handler.wfile.flush()
                continue
            data = json.dumps(payload, ensure_ascii=False)
            handler.wfile.write(f"event: {name}\ndata: {data}\n\n".encode("utf-8"))
            handler.wfile.flush()
            if name == "canvas_done":
                break
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        with _LOCK:
            CANVAS_STREAMS.pop(cid, None)
    return True
