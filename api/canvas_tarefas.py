"""EXCRTX MOD-011 (F1) — endpoints /api/canvas/* (prefix dispatch, padrão MOD-009/010).

ADR-CT-04: registro de job replayable — troca a `queue.Queue` single-consumer
do spike F0 por `CANVAS_JOBS: dict[str, dict]` com log de eventos (append-only)
+ `threading.Condition`. Produtores só ANEXAM a `events` (nunca consomem), o
que permite N leitores replay a partir de qualquer cursor (`GET
/api/canvas/stream?since=N`) — mata a corrida de "segunda aba reconecta e
perde tudo" do F0 (single `queue.Queue` = um único consumidor destrutivo).
"""
from __future__ import annotations

import json
import threading
from urllib.parse import parse_qs

from api import canvas_store
from api.canvas_enquadrador import enquadrar

CANVAS_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_CLEANUP_DELAY = 300.0  # s — coleta jobs muito tempo após done (spike single-user)


def _j(handler, obj, status=200):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _new_job() -> dict:
    return {
        "status": "running",
        "valid": None,
        "errors": [],
        "events": [],  # [(nome, payload), ...] — append-only, replay ilimitado
        "cond": threading.Condition(),
    }


def _emit(canvas_id: str, name: str, payload) -> None:
    """Anexa um evento ao log do job e acorda quem estiver bloqueado em
    `cond.wait()` (streams SSE abertos). Nunca remove eventos — quem lê
    controla o próprio cursor."""
    with _LOCK:
        job = CANVAS_JOBS.get(canvas_id)
    if job is None:
        return
    with job["cond"]:
        job["events"].append((name, payload))
        job["cond"].notify_all()


def _emit_final(canvas_id: str, valid: bool, errors: list[str],
                name: str, payload) -> None:
    """Transição atômica pro estado done: status/valid/errors E o append do
    evento final (mais o notify_all) sob UMA ÚNICA seção crítica de
    `job["cond"]`. Sem isto, um poll em `/api/canvas/job` podia observar
    `status="done"` com `n_events` um a menos (o evento `canvas_done` ainda
    não anexado) — corrigido por review."""
    with _LOCK:
        job = CANVAS_JOBS.get(canvas_id)
    if job is None:
        return
    with job["cond"]:
        job["status"] = "done"
        job["valid"] = valid
        job["errors"] = errors
        job["events"].append((name, payload))
        job["cond"].notify_all()


def _schedule_cleanup(canvas_id: str) -> None:
    def _sweep():
        with _LOCK:
            CANVAS_JOBS.pop(canvas_id, None)

    t = threading.Timer(_CLEANUP_DELAY, _sweep)
    t.daemon = True
    t.start()


def _run_enquadrador(canvas_id: str, texto: str) -> None:
    errors: list[str] = []
    try:
        core, errors = enquadrar(texto, session=None)
        ops = canvas_store.core_to_patch(core) if not errors else []
        if ops:
            canvas = canvas_store.load_canvas(canvas_id)
            canvas_store.save_canvas(canvas_id, canvas_store.apply_patch(canvas, ops))
            _emit(canvas_id, "canvas_delta", ops)
    except Exception as exc:
        errors = [f"enquadrador quebrou: {exc}"]
    _emit_final(canvas_id, not errors, errors,
                "canvas_done", {"valid": not errors, "errors": errors})
    _schedule_cleanup(canvas_id)


def handle_canvas_post(handler, path: str, body: dict) -> bool:
    if path != "/api/canvas/draft":
        return False
    texto = (body.get("text") or "").strip()
    if not texto:
        _j(handler, {"error": "text obrigatório"}, 400)
        return True
    canvas_id, canvas = canvas_store.create_draft(texto)
    with _LOCK:
        CANVAS_JOBS[canvas_id] = _new_job()
    _emit(canvas_id, "canvas_snapshot", canvas)
    threading.Thread(target=_run_enquadrador, args=(canvas_id, texto),
                     daemon=True).start()
    _j(handler, {"canvas_id": canvas_id})
    return True


def _job_payload(job: dict) -> dict:
    with job["cond"]:
        return {
            "status": job["status"],
            "valid": job["valid"],
            "errors": list(job["errors"]),
            "n_events": len(job["events"]),
        }


def _list_canvases() -> list[dict]:
    """GET /api/canvas/list — para o Hangar/Átrio. Lê `canvas.yaml` de cada
    `_tasks/canvas_*/` (fonte da verdade em disco, não o registro em memória),
    reaproveitando `canvas_store.load_canvas` (normalização T1 de `vetor`
    incluída). `status` vem de `CANVAS_JOBS` quando o job ainda está vivo,
    senão "idle" (draft antigo/servidor reiniciado)."""
    dirs = sorted(canvas_store.tasks_dir().glob("canvas_*/canvas.yaml"),
                  key=lambda p: p.parent.name, reverse=True)[:50]
    out = []
    for p in dirs:
        cid = p.parent.name
        try:
            doc = canvas_store.load_canvas(cid)
        except Exception:
            continue
        with _LOCK:
            status = CANVAS_JOBS.get(cid, {}).get("status", "idle")
        out.append({
            "canvas_id": cid,
            "focus": doc.get("focus", ""),
            "vetor": doc.get("vetor", ""),
            "status": status,
        })
    return out


def _stream_events(handler, job: dict, cursor: int) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    try:
        while True:
            with job["cond"]:
                job["cond"].wait_for(lambda: len(job["events"]) > cursor, timeout=30)
                pending = job["events"][cursor:]
            if not pending:
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
                continue
            for name, payload in pending:
                cursor += 1
                data = json.dumps(payload, ensure_ascii=False)
                handler.wfile.write(
                    f"id: {cursor}\nevent: {name}\ndata: {data}\n\n".encode("utf-8"))
                handler.wfile.flush()
                if name == "canvas_done":
                    return
    except (BrokenPipeError, ConnectionResetError):
        pass


def handle_canvas_get(handler, parsed) -> bool:
    if parsed.path == "/api/canvas/get":
        cid = (parse_qs(parsed.query).get("canvas_id") or [""])[0]
        try:
            _j(handler, canvas_store.load_canvas(cid))
        except Exception:
            _j(handler, {"error": "canvas desconhecido"}, 404)
        return True
    if parsed.path == "/api/canvas/job":
        cid = (parse_qs(parsed.query).get("canvas_id") or [""])[0]
        with _LOCK:
            job = CANVAS_JOBS.get(cid)
        if job is None:
            _j(handler, {"error": "job desconhecido"}, 404)
            return True
        _j(handler, _job_payload(job))
        return True
    if parsed.path == "/api/canvas/list":
        _j(handler, _list_canvases())
        return True
    if parsed.path != "/api/canvas/stream":
        return False
    qs = parse_qs(parsed.query)
    cid = (qs.get("canvas_id") or [""])[0]
    try:
        cursor = int((qs.get("since") or ["0"])[0])
    except (TypeError, ValueError):
        cursor = 0
    if cursor < 0:
        cursor = 0
    with _LOCK:
        job = CANVAS_JOBS.get(cid)
    if job is None:
        _j(handler, {"error": "job desconhecido"}, 404)
        return True
    _stream_events(handler, job, cursor)
    return True
