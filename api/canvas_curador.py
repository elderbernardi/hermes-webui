"""EXCRTX MOD-013 (F2) — Curador: transporte in-process + worker singleton.

Registro PRÓPRIO (CURADOR_ROOMS ≠ CANVAS_JOBS do enquadrador): ids, ciclo de vida
e transporte independentes — é o que faz os 3 obstáculos herdados do F1b
(stream fecha em canvas_done; _schedule_cleanup de 300s; Cockpit não reabre)
sumirem por construção. Singleton (1 worker/vez) via _CURADOR_BUSY + fila FIFO
global ordenada (_QUEUE, drenada por _pump sob _QLOCK). Só o Artifact destilado
cruza a fronteira SSE (higiene P11)."""
from __future__ import annotations

import collections
import itertools
import json
import logging
import os
import subprocess
import threading
from urllib.parse import parse_qs

from api import canvas_store
from api import curador_a2a as a2a
from api.curador_a2a import TaskStore, new_message, new_task, transition

logger = logging.getLogger("canvas_curador")

RETRIEVE_BUDGET = 6000     # default do acervoctl retrieve
POSTURE_BUDGET = 12000     # default do acervoctl posture
_CLEANUP_DELAY = 300.0     # s — coleta a sala muito tempo após inatividade

CURADOR_ROOMS: dict[str, dict] = {}
_ROOMS_LOCK = threading.Lock()

_STORE = TaskStore()
_CURADOR_BUSY = threading.Lock()          # singleton: 1 worker por vez
_QUEUE: collections.deque[str] = collections.deque()   # FIFO global de task_id
_QLOCK = threading.Lock()                 # protege _QUEUE + handoff do busy
_SEQ = itertools.count()

# Registry de skills — preenchido por T7/T8/T9 (buscar_acervo/sugerir_itens/pesquisar).
_SKILLS: dict[str, callable] = {}


def _j(handler, obj, status=200):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _room(cid: str) -> dict:
    with _ROOMS_LOCK:
        room = CURADOR_ROOMS.get(cid)
        if room is None:
            room = {"events": [], "cond": threading.Condition()}
            CURADOR_ROOMS[cid] = room
        return room


def _emit(cid: str, name: str, payload) -> None:
    """Anexa um evento ao log da sala e acorda streams abertos. Append-only —
    quem lê controla o próprio cursor (replay ilimitado)."""
    room = _room(cid)
    with room["cond"]:
        room["events"].append((name, payload))
        room["cond"].notify_all()


def _schedule_cleanup(cid: str) -> None:
    def _sweep():
        with _ROOMS_LOCK:
            room = CURADOR_ROOMS.get(cid)
            # só derruba se não há Task não-terminal para esta sala
            live = [t for t in _STORE.for_context(cid) if not a2a.is_terminal(t)]
            if room is not None and not live:
                CURADOR_ROOMS.pop(cid, None)

    t = threading.Timer(_CLEANUP_DELAY, _sweep)
    t.daemon = True
    t.start()


def _call_llm_seam(cmd: str, prompt: str) -> str:
    proc = subprocess.run(cmd, shell=True, input=prompt.encode("utf-8"),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(
            f"CURADOR_LLM_CMD exit {proc.returncode}: "
            f"{proc.stderr.decode('utf-8', 'replace')[-200:]}")
    return proc.stdout.decode("utf-8", "replace")


def _call_llm_curator(prompt: str) -> str:
    """Turno LLM no role AUXILIAR (task='curator', slot já em AUXILIARY_TASK_CATALOG
    — zero mudança de schema/config). Seam CURADOR_LLM_CMD para teste/dev (próprio,
    não reusa CANVAS_LLM_CMD do enquadrador)."""
    cmd = os.environ.get("CURADOR_LLM_CMD")
    if cmd:
        return _call_llm_seam(cmd, prompt)
    from api import profiles as profiles_api
    active = profiles_api.get_active_profile_name() or "default"
    with profiles_api.profile_env_for_background_worker(
            active, "canvas curador", logger_override=logger):
        from agent.auxiliary_client import call_llm
        resp = call_llm(task="curator",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0)
        return resp.choices[0].message.content or ""


def _run_skill(task) -> tuple[dict | None, str | None]:
    """Dispatch por skill via registry. Retorna (artifact, gap_reason); exatamente
    um não-None. As skills reais são registradas em _SKILLS por T7/T8/T9."""
    fn = _SKILLS.get(task["metadata"]["skill"])
    if fn is None:
        return (None, f"skill não registrada: {task['metadata']['skill']}")
    return fn(task)


def _pump() -> None:
    """Drena a próxima Task submitted em ordem FIFO, respeitando o singleton.
    claim + popleft + spawn são atômicos sob _QLOCK."""
    with _QLOCK:
        if not _QUEUE:
            return
        if not _CURADOR_BUSY.acquire(blocking=False):
            return  # um worker roda; ele re-pumpa no finally
        task_id = _QUEUE.popleft()
    threading.Thread(target=_run_curador, args=(task_id,), daemon=True).start()


def _run_curador(task_id: str) -> None:
    task = _STORE.get(task_id)
    cid = task["contextId"]
    try:
        transition(task, "working")
        _emit(cid, "curador_status", {"delegacao_id": task_id, "estado": "working"})
        artifact, gap = _run_skill(task)
        if artifact is not None:
            _emit(cid, "curador_sugestao", artifact)
            transition(task, "completed")
            _emit(cid, "curador_status", {"delegacao_id": task_id, "estado": "completed"})
        else:
            reason = gap or "Curador não encontrou resultado citável"
            ops = [{"op": "add", "path": "/gaps/-", "value": reason}]
            _emit(cid, "curador_gap",
                  {"delegacao_id": task_id, "motivo": reason, "ops": ops})
            transition(task, "failed", message=new_message(
                role="agent", skill=task["metadata"]["skill"], task_id=task_id,
                text=reason))
            _emit(cid, "curador_status", {"delegacao_id": task_id, "estado": "failed"})
    except Exception as exc:  # thread daemon: nunca deixa exceção subir (erro-calmo)
        try:
            if not a2a.is_terminal(task):
                transition(task, "failed")
        except Exception:
            pass
        _emit(cid, "curador_status",
              {"delegacao_id": task_id, "estado": "failed", "erro": str(exc)[-200:]})
    finally:
        _CURADOR_BUSY.release()
        _pump()
        _schedule_cleanup(cid)


def delegar(canvas_id: str, kind: str, *, query=None, escopo=None, tema=None,
            allow_scopes=None) -> str:
    budget = POSTURE_BUDGET if kind == "sugerir_itens" else RETRIEVE_BUDGET
    task = new_task(contextId=canvas_id, skill=kind, budget_tokens=budget)
    task["metadata"]["args"] = {"query": query, "escopo": escopo, "tema": tema,
                                "allow_scopes": list(allow_scopes or [])}
    task["metadata"]["seq"] = next(_SEQ)
    task["history"].append(new_message(
        role="user", skill=kind, task_id=task["id"],
        metadata=task["metadata"]["args"], text=kind))
    _STORE.add(task)
    _room(canvas_id)                        # garante sala p/ o stream anexar
    with _QLOCK:
        _QUEUE.append(task["id"])
    _pump()
    return task["id"]


def _valid_allow_scopes(scopes) -> bool:
    """Firewall de sharing validado SERVER-SIDE (achado M3): cada allow_scope tem
    de ser um microverso conhecido em disco. A única invariante estrutural é
    sensitivity:restricted (deny-sempre, dentro do retrieve); cross-scope é
    decisão do chamador single-user. Nunca confia na lista do cliente."""
    if not isinstance(scopes, list):
        return False
    try:
        micro = canvas_store.acervo_root() / "micro"
        known = {p.name for p in micro.iterdir()
                 if p.is_dir() and not p.name.startswith(("_", "."))} if micro.is_dir() else set()
    except Exception:
        known = set()
    return all(isinstance(s, str) and s in known for s in scopes)


def _stream_events(handler, room: dict, cursor: int) -> None:
    """SSE re-anexável. Diferente do enquadrador, NÃO fecha em evento terminal —
    a sala do Curador serve N delegações ao longo da sessão; o stream só encerra
    quando o cliente desconecta. Resolve o obstáculo F1b 'stream fecha em canvas_done'."""
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


def handle_curador_post(handler, path, body) -> bool:
    if path != "/api/canvas/curador/delegar":
        return False
    cid = body.get("canvas_id") or ""
    kind = body.get("kind") or ""
    if kind not in ("buscar_acervo", "sugerir_itens", "pesquisar"):
        _j(handler, {"error": "kind inválido"}, 400)
        return True
    if kind == "pesquisar" and os.environ.get("CURADOR_ENABLE_PESQUISAR") != "1":
        _j(handler, {"error": "pesquisar desabilitado (CURADOR_ENABLE_PESQUISAR)"}, 400)
        return True
    allow = body.get("allow_scopes") or []
    if not _valid_allow_scopes(allow):
        _j(handler, {"error": "allow_scopes inválido"}, 400)
        return True
    try:
        canvas_store.load_canvas(cid)
    except Exception:
        _j(handler, {"error": "canvas desconhecido"}, 404)
        return True
    did = delegar(cid, kind, query=body.get("query"), escopo=body.get("escopo"),
                  tema=body.get("tema"), allow_scopes=allow)
    _j(handler, {"delegacao_id": did})
    return True


def handle_curador_get(handler, parsed) -> bool:
    if parsed.path == "/api/canvas/curador/stream":
        qs = parse_qs(parsed.query)
        cid = (qs.get("canvas_id") or [""])[0]
        try:
            cursor = int((qs.get("since") or ["0"])[0])
        except (TypeError, ValueError):
            cursor = 0
        if cursor < 0:
            cursor = 0
        _stream_events(handler, _room(cid), cursor)
        return True
    if parsed.path == "/api/canvas/curador/job":
        qs = parse_qs(parsed.query)
        did = (qs.get("delegacao_id") or [""])[0]
        task = _STORE.get(did)
        if task is None:
            _j(handler, {"error": "delegação desconhecida"}, 404)
            return True
        m = task["metadata"]
        _j(handler, {"state": task["status"]["state"],
                     "empty_lookups": m.get("empty_lookups", 0),
                     "attempts": m.get("attempts", 0),
                     "hygiene": m.get("hygiene", {})})
        return True
    return False
