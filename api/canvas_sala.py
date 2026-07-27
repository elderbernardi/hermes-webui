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


# ── T8: observer daemon — conduct.jsonl + HITL queues -> reducer -> emit ─────
import logging
import os
import queue

from api import clarify, route_approvals
from api.sala_reducer import SalaState

logger = logging.getLogger("canvas_sala")

_OBSERVERS: dict[str, bool] = {}
_OBS_LOCK = threading.Lock()
_INJECTED: dict[str, object] = {}   # test seam: {"conduct": callable}


def _enabled() -> bool:
    return os.environ.get("SALA_ENABLE") == "1"


def _read_conduct_lines(task_id: str, offset: int) -> tuple[list[dict], int]:
    p = canvas_store.tasks_dir() / task_id / "conduct.jsonl"
    if not p.is_file():
        return [], offset
    lines = p.read_text(encoding="utf-8").splitlines()
    out = []
    for ln in lines[offset:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out, len(lines)


def _frame_from_conduct(obj: dict) -> dict | None:
    t = obj.get("t")
    if t == "phase":
        return {"kind": "phase", "phase": obj.get("phase"), "seq": obj.get("seq")}
    if t == "trace":
        return {"kind": "trace", "trace_kind": obj.get("kind"),
                "title": obj.get("title"), "evidence": obj.get("evidence") or {}}
    if t == "artifact":
        return {"kind": "artifact", "title": obj.get("title"), "atype": obj.get("atype"),
                "path": obj.get("path"), "tool": obj.get("tool")}
    if t == "verify":
        return {"kind": "verify", "subject": obj.get("subject"), "ok": obj.get("ok"),
                "hypothesis": obj.get("hypothesis"), "tried": obj.get("tried"),
                "output": obj.get("output")}
    if t == "search":
        return {"kind": "search", "query_sig": obj.get("query_sig"),
                "empty": obj.get("empty"), "query": obj.get("query")}
    if t == "surprise":
        return {"kind": "surprise", "subject": obj.get("subject"), "code": obj.get("code"),
                "check": obj.get("check"), "spec": obj.get("spec"), "resolution": obj.get("resolution")}
    if t == "next_move":
        return {"kind": "next_move", "text": obj.get("text")}
    if t == "draft":     # the agent's own EX-08 Draft-First declaration -> sala_draft
        return {"kind": "approval", "session_id": None, "approval_id": None,
                "action": obj.get("action"), "draft_text": obj.get("draft_text") or ""}
    return None


def _frame_from_clarify(sid: str, payload: dict) -> dict | None:
    pend = payload.get("pending")
    if not pend:
        return None
    return {"kind": "clarify", "clarify_id": pend.get("clarify_id"), "session_id": sid,
            "question": pend.get("question"), "choices_offered": pend.get("choices_offered") or [],
            "bound_interrupt": pend.get("kind") == "bound_interrupt",
            "hypothesis": pend.get("hypothesis"), "tried": pend.get("tried"), "output": pend.get("output")}


def _frame_from_approval(sid: str, payload: dict) -> dict | None:
    pend = payload.get("pending")
    if not pend:
        return None
    # I1: real approval pending keys = command/pattern_key/description/approval_id
    return {"kind": "approval", "session_id": sid,
            "approval_id": pend.get("approval_id"),
            "action": pend.get("command"),
            "draft_text": pend.get("description") or pend.get("command") or ""}


def _drain(q: queue.Queue) -> list:
    out = []
    try:
        while True:
            out.append(q.get_nowait())
    except queue.Empty:
        pass
    return out


def _emit_frame(st: SalaState, frame) -> int:
    if not frame:
        return 0
    # conduct-declared drafts have no session on the frame; the island needs it.
    if frame.get("kind") == "approval" and not frame.get("session_id"):
        frame["session_id"] = getattr(st, "_sid", None)
    n = 0
    for name, payload in st.ingest(frame):
        _emit(st.cid, name, payload)
        n += 1
    return n


def _poll_once(st: SalaState, ctx: dict) -> int:
    st._sid = ctx["sid"]                       # carry the session for draft frames
    emitted = 0
    for payload in _drain(ctx["clarify_q"]):
        emitted += _emit_frame(st, _frame_from_clarify(ctx["sid"], payload))
    for payload in _drain(ctx["approval_q"]):
        emitted += _emit_frame(st, _frame_from_approval(ctx["sid"], payload))
    conduct_reader = _INJECTED.get("conduct") or _read_conduct_lines
    lines, ctx["conduct_off"] = conduct_reader(st.task_id, ctx["conduct_off"])
    for obj in lines:
        emitted += _emit_frame(st, _frame_from_conduct(obj))
    return emitted


def _prime(st: SalaState, ctx: dict) -> None:
    """M2: sse_subscribe only registers a queue; the routes handler compensates
    with an initial snapshot the observer lacks. Prime once from the current
    clarify pending head so an in-flight clarify at observer start is not missed.
    (M-B2: route_approvals exposes NO get_pending — the approval initial-snapshot
    lives inline in routes.py:19080; the observer starts at launch, BEFORE any
    approval, so approval-priming is intentionally omitted here. Mid-session
    /observe after an already-pending approval is a known v1 gap -> F5.)"""
    st._sid = ctx["sid"]
    head = clarify.get_pending(ctx["sid"])
    if head:
        _emit_frame(st, _frame_from_clarify(ctx["sid"], {"pending": head}))


def start_observer(session_id: str) -> None:
    if not _enabled():
        return
    with _OBS_LOCK:
        if _OBSERVERS.get(session_id):
            return
        _OBSERVERS[session_id] = True
    threading.Thread(target=_run_observer, args=(session_id,), daemon=True).start()


def _run_observer(session_id: str) -> None:
    link = resolve(session_id)
    if not link:
        with _OBS_LOCK:
            _OBSERVERS.pop(session_id, None)
        return
    st = SalaState(link["canvas_id"], link["task_id"])
    _room(link["canvas_id"])
    ctx = {"sid": session_id, "clarify_q": clarify.sse_subscribe(session_id),
           "approval_q": route_approvals._approval_sse_subscribe(session_id),
           "conduct_off": 0}
    _prime(st, ctx)
    interval = float(os.environ.get("SALA_POLL_INTERVAL") or 1.0)
    try:
        while _OBSERVERS.get(session_id):
            try:
                _poll_once(st, ctx)
            except Exception:            # erro-calmo: um frame ruim nunca mata a thread
                logger.exception("sala observer poll failed")
            time.sleep(interval)
    finally:
        clarify.sse_unsubscribe(session_id, ctx["clarify_q"])
        route_approvals._approval_sse_unsubscribe(session_id, ctx["approval_q"])
        with _OBS_LOCK:
            _OBSERVERS.pop(session_id, None)


def handle_sala_post(handler, path: str, body: dict) -> bool:
    if path != "/api/canvas/sala/observe":
        return False
    cid = body.get("canvas_id") or ""
    sid = _link_for_canvas(cid)
    if sid:
        start_observer(sid)
    _j(handler, {"ok": True})
    return True
