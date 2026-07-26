"""EXCRTX MOD-014 (F3) — Sala viva: observe-and-translate layer.

Camada in-process que reflete a sessão lançada no canvas. NUNCA cunha
primitiva bloqueante (só observa clarify/approval multi-subscriber);
NUNCA escreve no runtime da sessão. Gate SALA_ENABLE (default off).
Este arquivo cresce por tarefa: T3=linkagem, T6=sala+stream, T8=observador."""
from __future__ import annotations

import threading
import time
import yaml

from api import canvas_store

_LAUNCHED: dict[str, dict] = {}          # session_id -> {"canvas_id","task_id"}
_LAUNCHED_LOCK = threading.Lock()


def register_launch(session_id: str, canvas_id: str, task_id: str) -> None:
    """Grava a linkagem em memória E num sidecar durável canvas-keyed
    (_tasks/<canvas_id>/launch.yaml), para sobreviver a restart do servidor."""
    with _LAUNCHED_LOCK:
        _LAUNCHED[session_id] = {"canvas_id": canvas_id, "task_id": task_id}
    d = canvas_store.tasks_dir() / canvas_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "launch.yaml").write_text(
        yaml.safe_dump({"session_id": session_id, "task_id": task_id,
                        "launched_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                       allow_unicode=True, sort_keys=False),
        encoding="utf-8")


def resolve(session_id: str) -> dict | None:
    with _LAUNCHED_LOCK:
        v = _LAUNCHED.get(session_id)
        return dict(v) if v else None


def _rebuild_launched() -> None:
    """Cold-start: reconstrói _LAUNCHED varrendo os sidecars em disco
    (mesmo padrão de _list_canvases)."""
    for p in canvas_store.tasks_dir().glob("canvas_*/launch.yaml"):
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        sid = doc.get("session_id")
        if sid:
            with _LAUNCHED_LOCK:
                _LAUNCHED[sid] = {"canvas_id": p.parent.name, "task_id": doc.get("task_id")}


# ── T6: SALA_ROOMS room + non-closing stream + state projection ─────────────
import json
from urllib.parse import parse_qs

SALA_ROOMS: dict[str, dict] = {}
_ROOMS_LOCK = threading.Lock()


def _room(cid: str) -> dict:
    with _ROOMS_LOCK:
        room = SALA_ROOMS.get(cid)
        if room is None:
            room = {"events": [], "cond": threading.Condition()}
            SALA_ROOMS[cid] = room
        return room


def _emit(cid: str, name: str, payload) -> None:
    """Append-only + notify. Cloned from CURADOR_ROOMS: non-closing, cursor-replay."""
    room = _room(cid)
    with room["cond"]:
        room["events"].append((name, payload))
        room["cond"].notify_all()


def _project(room: dict) -> dict:
    phase = None
    columns: dict = {}
    with room["cond"]:
        events = list(room["events"])
    for name, payload in events:
        if name == "sala_phase":
            phase = payload.get("phase")
        elif name == "sala_kanban":
            columns[payload.get("task_id")] = payload.get("column")
    return {"phase": phase, "columns": columns, "n_events": len(events)}


def _j(handler, obj, status=200):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _stream_events(handler, room: dict, cursor: int) -> None:
    """SSE re-anexável; NÃO fecha em terminal (a sala serve a sessão inteira)."""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    try:
        while True:
            with room["cond"]:
                room["cond"].wait_for(lambda: len(room["events"]) > cursor, timeout=30)
                pending = room["events"][cursor:]
            if not pending:
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
                continue
            frames = []
            for name, payload in pending:
                cursor += 1
                data = json.dumps(payload, ensure_ascii=False)
                frames.append(f"id: {cursor}\nevent: {name}\ndata: {data}\n\n")
            handler.wfile.write("".join(frames).encode("utf-8"))
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass


def handle_sala_get(handler, parsed) -> bool:
    if parsed.path == "/api/canvas/sala/stream":
        qs = parse_qs(parsed.query)
        cid = (qs.get("canvas_id") or [""])[0]
        try:
            cursor = int((qs.get("since") or ["0"])[0])
        except (TypeError, ValueError):
            cursor = 0
        if cursor < 0:
            cursor = 0
        # opening the stream starts the observer for the linked session (idempotent).
        link = _link_for_canvas(cid)
        if link:
            start_observer(link)
        _stream_events(handler, _room(cid), cursor)
        return True
    if parsed.path == "/api/canvas/sala/state":
        cid = (parse_qs(parsed.query).get("canvas_id") or [""])[0]
        _j(handler, _project(_room(cid)))
        return True
    return False


def _link_for_canvas(cid: str) -> str | None:
    """Reverse of resolve(): find the session_id linked to a canvas_id."""
    with _LAUNCHED_LOCK:
        for sid, v in _LAUNCHED.items():
            if v.get("canvas_id") == cid:
                return sid
    return None


# ── Temporary stubs (T6): replaced by the real implementations in T8. ───────
# handle_sala_get references start_observer; the forward (T7) references
# handle_sala_post. Both land for real in T8, which removes these stubs.
def start_observer(session_id):  # noqa: D401 — temporary stub, real impl in T8
    pass


def handle_sala_post(handler, path, body) -> bool:  # temporary stub, real impl in T8
    return False
