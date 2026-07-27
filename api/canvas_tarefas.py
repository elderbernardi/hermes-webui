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
import re
import subprocess
import threading
from urllib.parse import parse_qs

from api import canvas_brief, canvas_store
from api.canvas_enquadrador import enquadrar
from api.canvas_validate import validate_core

CANVAS_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_CLEANUP_DELAY = 300.0  # s — coleta jobs muito tempo após done (spike single-user)

# Whitelist de pointers editáveis via /api/canvas/patch (ADR-CT-04 T5).
# Entradas terminadas em "/*" viram regex de UM segmento (cobre índice
# numérico e o marcador de append "-" do RFC 6902) — casa contra o padrão
# do PAI (ex.: "/gaps/*" casa "/gaps/2" e "/gaps/-"), nunca uma lista de
# paths literais (que não daria conta de arrays).
_WHITELIST_RAW = (
    "/focus", "/vetor", "/intent_type", "/shape", "/done_criteria",
    "/verification", "/microversos/primary", "/microversos/related/*",
    "/gaps/*", "/scope/*", "/assumptions/*", "/artifacts/expected/*",
    "/next_moves/*",
    "/personas/suggested/*", "/acervo_aplicado/*",
    "/authorization/*",
)


def _whitelist_regex(raw: str) -> re.Pattern:
    if raw.endswith("/*"):
        return re.compile(r"^" + re.escape(raw[:-2]) + r"/[^/]+$")
    return re.compile(r"^" + re.escape(raw) + r"$")


_WHITELIST = tuple(_whitelist_regex(p) for p in _WHITELIST_RAW)


def _path_editavel(path: str) -> bool:
    # fullmatch (não match): com match(), "$" ainda casa antes de um "\n"
    # final (ex.: pattern "^/focus$" casa "/focus\n"), o que deixaria vazar
    # um pointer com newline injetado. fullmatch exige consumir a string
    # inteira e fecha essa brecha.
    return any(rx.fullmatch(path) for rx in _WHITELIST)


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


def _handle_patch(handler, body: dict) -> None:
    cid = body.get("canvas_id") or ""
    ops = body.get("ops") or []
    for op in ops:
        if not _path_editavel(op.get("path", "")):
            _j(handler, {"error": "path não editável"}, 400)
            return
    try:
        canvas = canvas_store.load_canvas(cid)
    except Exception:
        _j(handler, {"error": "canvas desconhecido"}, 404)
        return
    # apply_patch/_doc_to_core operam só em memória até aqui — um op que
    # passa na whitelist mas falha em runtime (remove fora do range, add/
    # replace sem "value", ...) vira 400 limpo em vez de propagar a
    # exceção; nada é persistido antes deste ponto.
    try:
        canvas = canvas_store.apply_patch(canvas, ops)
        core = canvas_store._doc_to_core(canvas)
    except Exception as exc:
        _j(handler, {"error": f"op inválida: {exc}"}, 400)
        return
    canvas_store.save_canvas(cid, canvas)
    valid, errors = validate_core(core)
    _emit(cid, "canvas_delta", ops)
    _emit(cid, "canvas_validity", {"valid": valid, "errors": errors})
    _j(handler, {"ok": True, "valid": valid, "errors": errors})


def _new_session():
    """Seam fino sobre `api.models.new_session` — import tardio: mantém o
    boot do módulo barato e permite monkeypatch em teste sem puxar o
    api.models (pesado) para dentro do processo de teste."""
    from api.models import new_session
    return new_session()


_STAGE_MIME = {".md": "text/markdown", ".yaml": "text/yaml", ".yml": "text/yaml"}


def _stage_file(session_id: str, path) -> dict:
    """Seam fino sobre `api.upload._upload_destination` — copia os bytes de
    `path` para o diretório de upload da sessão. Import tardio pelo mesmo
    motivo do `_new_session`; mesmo shape de attachment do endpoint de
    upload (name/path/size/mime/is_image)."""
    from api.upload import _upload_destination
    dest = _upload_destination(session_id, path.name)
    dest.write_bytes(path.read_bytes())
    mime = _STAGE_MIME.get(path.suffix.lower(), "application/octet-stream")
    return {"name": dest.name, "path": str(dest), "size": dest.stat().st_size,
            "mime": mime, "is_image": False}


def _register_task(canvas_path, title: str) -> str:
    """Seam fino: registra a tarefa rodando `register_task_from_canvas.py`
    como subprocesso (script vive no acervo real, fora deste worktree).
    Levanta exceção em qualquer falha — o handler traduz em 500."""
    import os
    import sys

    script = canvas_store.acervo_root() / "global/tools/harness/register_task_from_canvas.py"
    # timeout=30: um register travado não pode prender a thread HTTP para
    # sempre — deixa subprocess.TimeoutExpired propagar; o handler trata
    # esse caso especificamente (500 {"error": "register timeout"}).
    result = subprocess.run(
        [sys.executable, str(script), "--canvas", str(canvas_path), "--title", title],
        env={**os.environ, "ACERVO": str(canvas_store.acervo_root())},
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-200:])
    m = re.search(r"task_id:\s*(\S+)", result.stdout)
    if m:
        return m.group(1)
    # Fallback: script rodou ok mas não imprimiu "task_id: ..." no formato
    # esperado — pega o task_* mais recente em disco.
    candidates = sorted(canvas_store.tasks_dir().glob("task_*"),
                        key=lambda p: p.name, reverse=True)
    if candidates:
        return candidates[0].name
    raise RuntimeError("register não produziu task_id e nenhum task_* em disco")


def _update_links(task_id: str, session_id: str) -> None:
    """Append simples (não reserializa) do session_id no links.yaml da task
    recém-registrada — cria o arquivo/diretório se ainda não existirem
    (cobre o teste, onde `_register_task` é mockado e não cria nada em
    disco)."""
    task_dir = canvas_store.tasks_dir() / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    with (task_dir / "links.yaml").open("a", encoding="utf-8") as f:
        f.write(f"session_id: {session_id}\n")


def _handle_launch(handler, body: dict) -> None:
    cid = body.get("canvas_id") or ""
    try:
        doc = canvas_store.load_canvas(cid)
    except Exception:
        _j(handler, {"error": "canvas desconhecido"}, 404)
        return
    try:
        brief = canvas_brief.compile_brief(doc)
    except ValueError as exc:
        _j(handler, {"error": str(exc)}, 400)
        return

    canvas_dir = canvas_store.tasks_dir() / cid
    canvas_path = canvas_dir / "canvas.yaml"
    brief_path = canvas_dir / "brief.md"
    brief_path.write_text(brief, encoding="utf-8")

    try:
        task_id = _register_task(canvas_path, (doc.get("focus") or "")[:80])
    except subprocess.TimeoutExpired:
        _j(handler, {"error": "register timeout"}, 500)
        return
    except Exception as exc:
        _j(handler, {"error": "register falhou", "detail": str(exc)[-200:]}, 500)
        return

    # A partir daqui `_tasks/<task_id>/` já existe (o register criou). Se
    # qualquer passo seguinte falhar, a task fica órfã mas RECONCILIÁVEL —
    # por isso o 500 carrega o task_id de volta, em vez de vazar uma
    # exceção crua (não-JSON) pro cliente e silenciar o estado parcial.
    try:
        session = _new_session()
        attachments = [_stage_file(session.session_id, p)
                      for p in (canvas_path, brief_path)]
        _update_links(task_id, session.session_id)
    except Exception as exc:
        _j(handler, {"error": f"launch falhou pós-registro: {exc}",
                     "task_id": task_id}, 500)
        return

    _emit(cid, "canvas_launched", {"task_id": task_id, "session_id": session.session_id})
    from api import canvas_sala
    canvas_sala.register_launch(session.session_id, cid, task_id)

    _j(handler, {
        "session_id": session.session_id,
        "task_id": task_id,
        "brief": brief,
        "attachments": attachments,
    })


def handle_canvas_post(handler, path: str, body: dict) -> bool:
    if path.startswith("/api/canvas/curador/"):   # MOD-013 (F2): forward ao Curador
        from api.canvas_curador import handle_curador_post
        return handle_curador_post(handler, path, body)
    if path.startswith("/api/canvas/sala/"):     # MOD-014 (F3): forward à Sala viva
        from api.canvas_sala import handle_sala_post
        return handle_sala_post(handler, path, body)
    if path == "/api/canvas/patch":
        _handle_patch(handler, body)
        return True
    if path == "/api/canvas/launch":
        _handle_launch(handler, body)
        return True
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
    if parsed.path.startswith("/api/canvas/curador/"):   # MOD-013 (F2): forward ao Curador
        from api.canvas_curador import handle_curador_get
        return handle_curador_get(handler, parsed)
    if parsed.path.startswith("/api/canvas/sala/"):   # MOD-014 (F3): forward à Sala viva
        from api.canvas_sala import handle_sala_get
        return handle_sala_get(handler, parsed)
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
    if parsed.path == "/api/canvas/brief":
        cid = (parse_qs(parsed.query).get("canvas_id") or [""])[0]
        try:
            doc = canvas_store.load_canvas(cid)
        except Exception:
            _j(handler, {"error": "canvas desconhecido"}, 404)
            return True
        try:
            texto = canvas_brief.compile_brief(doc)
        except ValueError as exc:
            _j(handler, {"error": str(exc)}, 400)
            return True
        _j(handler, {"brief": texto})
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
