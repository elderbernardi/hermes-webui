import threading
import time
import pytest

from api import canvas_curador, curador_a2a as a2a
import io
import json as _json
from urllib.parse import urlparse


@pytest.fixture()
def curador_env(tmp_path, monkeypatch):
    (tmp_path / "micro/comercial").mkdir(parents=True)
    (tmp_path / "_tasks").mkdir()
    monkeypatch.setenv("ACERVO", str(tmp_path))
    # canvas mínimo em disco p/ handle_curador_post validar load_canvas (T4)
    monkeypatch.setattr(canvas_curador.canvas_store, "load_canvas",
                        lambda cid: {"canvas_id": cid, "microversos": {"primary": "comercial"}})
    # estado de módulo limpo entre testes
    canvas_curador.CURADOR_ROOMS.clear()
    canvas_curador._STORE = a2a.TaskStore()
    canvas_curador._QUEUE.clear()
    if canvas_curador._CURADOR_BUSY.locked():
        canvas_curador._CURADOR_BUSY.release()
    return tmp_path


def _wait_state(task_id, state, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = canvas_curador._STORE.get(task_id)
        if t and t["status"]["state"] == state:
            return t
        time.sleep(0.01)
    raise AssertionError(f"{task_id} não chegou a {state}")


def _ok_skill(task):
    return (a2a.new_artifact(name="n", description="d",
            data={"tipo": task["metadata"]["skill"], "path": "micro/comercial/knowledge/k.md",
                  "query": task["metadata"]["args"].get("query")}), None)


def test_fifo_ordem_a_b_c(curador_env, monkeypatch):
    ordem = []
    gate = threading.Event()

    def slow_skill(task):
        gate.wait(timeout=2)               # segura o 1º worker até liberarmos
        ordem.append(task["metadata"]["args"]["query"])
        return _ok_skill(task)

    monkeypatch.setattr(canvas_curador, "_run_skill", slow_skill)
    ids = [canvas_curador.delegar("canvas_x", "buscar_acervo", query=q)
           for q in ("A", "B", "C")]
    # A já está em working (segurado no gate); B e C esperam na fila
    _wait_state(ids[0], "working")
    assert canvas_curador._STORE.get(ids[1])["status"]["state"] == "submitted"
    assert canvas_curador._STORE.get(ids[2])["status"]["state"] == "submitted"
    gate.set()
    for tid in ids:
        _wait_state(tid, "completed")
    assert ordem == ["A", "B", "C"]        # FIFO real


def test_um_worker_por_vez(curador_env, monkeypatch):
    concorrentes = {"max": 0, "cur": 0}
    lk = threading.Lock()
    rel = threading.Event()

    def counting_skill(task):
        with lk:
            concorrentes["cur"] += 1
            concorrentes["max"] = max(concorrentes["max"], concorrentes["cur"])
        rel.wait(timeout=2)
        with lk:
            concorrentes["cur"] -= 1
        return _ok_skill(task)

    monkeypatch.setattr(canvas_curador, "_run_skill", counting_skill)
    ids = [canvas_curador.delegar("c", "buscar_acervo", query=str(i)) for i in range(3)]
    _wait_state(ids[0], "working")
    rel.set()
    for tid in ids:
        _wait_state(tid, "completed")
    assert concorrentes["max"] == 1


def test_lock_liberado_em_excecao(curador_env, monkeypatch):
    monkeypatch.setattr(canvas_curador, "_run_skill",
                        lambda task: (_ for _ in ()).throw(RuntimeError("boom")))
    tid = canvas_curador.delegar("c", "buscar_acervo", query="q")
    _wait_state(tid, "failed")
    assert not canvas_curador._CURADOR_BUSY.locked()


def test_sugestao_emitida_e_completed(curador_env, monkeypatch):
    monkeypatch.setattr(canvas_curador, "_run_skill", _ok_skill)
    tid = canvas_curador.delegar("c", "buscar_acervo", query="renegociar")
    _wait_state(tid, "completed")
    nomes = [n for n, _ in canvas_curador.CURADOR_ROOMS["c"]["events"]]
    assert "curador_sugestao" in nomes


def test_gap_emitido_e_failed(curador_env, monkeypatch):
    monkeypatch.setattr(canvas_curador, "_run_skill",
                        lambda task: (None, "não encontrei após 2 buscas"))
    tid = canvas_curador.delegar("c", "buscar_acervo", query="x")
    _wait_state(tid, "failed")
    eventos = dict(canvas_curador.CURADOR_ROOMS["c"]["events"])
    assert "curador_gap" in [n for n, _ in canvas_curador.CURADOR_ROOMS["c"]["events"]]
    gap = eventos["curador_gap"]
    assert gap["ops"][0]["path"] == "/gaps/-"


def test_call_llm_curator_usa_seam(curador_env, monkeypatch):
    monkeypatch.setenv("CURADOR_LLM_CMD", "printf 'resposta-do-stub'")
    assert canvas_curador._call_llm_curator("prompt qualquer") == "resposta-do-stub"


class _OneShotStream:
    """Handler fake p/ SSE: captura frames e aborta o loop após o 1º batch
    (BrokenPipeError no flush quando já há um frame 'event:' escrito)."""
    def __init__(self):
        self._buf = bytearray()
        self.status = None
        self.frames = b""
        outer = self

        class _W:
            def write(self, b):
                outer._buf.extend(b)
            def flush(self):
                outer.frames = bytes(outer._buf)
                if b"event:" in outer.frames:
                    raise BrokenPipeError
        self.wfile = _W()

    def send_response(self, c): self.status = c
    def send_header(self, *a): pass
    def end_headers(self): pass


class FakeHandler:
    def __init__(self):
        self.wfile = io.BytesIO()
        self.status = None
    def send_response(self, c): self.status = c
    def send_header(self, *a): pass
    def end_headers(self): pass


def test_delegar_endpoint_retorna_id(curador_env, monkeypatch):
    monkeypatch.setattr(canvas_curador, "_run_skill",
                        lambda task: (a2a.new_artifact(name="n", description="d",
                                      data={"tipo": "buscar_acervo", "path": "p"}), None))
    h = FakeHandler()
    assert canvas_curador.handle_curador_post(
        h, "/api/canvas/curador/delegar",
        {"canvas_id": "c", "kind": "buscar_acervo", "query": "q"}) is True
    did = _json.loads(h.wfile.getvalue())["delegacao_id"]
    assert did.startswith("curador_task_")


def test_delegar_kind_invalido_400(curador_env):
    h = FakeHandler()
    canvas_curador.handle_curador_post(h, "/api/canvas/curador/delegar",
                                       {"canvas_id": "c", "kind": "nope"})
    assert h.status == 400


def test_pesquisar_desabilitado_por_default_400(curador_env, monkeypatch):
    monkeypatch.delenv("CURADOR_ENABLE_PESQUISAR", raising=False)
    h = FakeHandler()
    canvas_curador.handle_curador_post(h, "/api/canvas/curador/delegar",
                                       {"canvas_id": "c", "kind": "pesquisar", "tema": "x"})
    assert h.status == 400


def test_allow_scopes_validado_server_side(curador_env):
    # 'comercial' existe (fixture criou micro/comercial); 'fantasma' não
    assert canvas_curador._valid_allow_scopes(["comercial"]) is True
    assert canvas_curador._valid_allow_scopes(["fantasma"]) is False
    assert canvas_curador._valid_allow_scopes("comercial") is False
    h = FakeHandler()
    canvas_curador.handle_curador_post(
        h, "/api/canvas/curador/delegar",
        {"canvas_id": "c", "kind": "buscar_acervo", "query": "q",
         "allow_scopes": ["fantasma"]})
    assert h.status == 400


def test_path_desconhecido_retorna_false(curador_env):
    assert canvas_curador.handle_curador_post(FakeHandler(), "/api/outro", {}) is False
    assert canvas_curador.handle_curador_get(
        FakeHandler(), urlparse("/api/outro")) is False


def test_stream_replay_por_cursor(curador_env):
    canvas_curador._emit("c", "curador_status", {"estado": "working"})
    canvas_curador._emit("c", "curador_sugestao", {"path": "p"})
    h = _OneShotStream()
    canvas_curador._stream_events(h, canvas_curador._room("c"), 0)
    assert b"event: curador_status" in h.frames
    assert b"event: curador_sugestao" in h.frames
    assert b"id: 1" in h.frames and b"id: 2" in h.frames


def test_job_endpoint_reporta_estado(curador_env, monkeypatch):
    monkeypatch.setattr(canvas_curador, "_run_skill",
                        lambda task: (a2a.new_artifact(name="n", description="d",
                                      data={"tipo": "buscar_acervo", "path": "p"}), None))
    tid = canvas_curador.delegar("c", "buscar_acervo", query="q")
    _wait_state(tid, "completed")
    h = FakeHandler()
    canvas_curador.handle_curador_get(h, urlparse(f"/api/canvas/curador/job?delegacao_id={tid}"))
    body = _json.loads(h.wfile.getvalue())
    assert body["state"] == "completed" and "hygiene" in body


def test_forward_via_canvas_tarefas(curador_env, monkeypatch):
    # achado #2: /api/canvas/curador/* é despachado pelo forward em canvas_tarefas.py
    # (routes.py intocado). O forward chega ao MESMO módulo canvas_curador.
    from api import canvas_tarefas
    monkeypatch.setattr(canvas_curador, "_run_skill",
                        lambda task: (a2a.new_artifact(name="n", description="d",
                                      data={"tipo": "buscar_acervo", "path": "p"}), None))
    h = FakeHandler()
    assert canvas_tarefas.handle_canvas_post(
        h, "/api/canvas/curador/delegar",
        {"canvas_id": "c", "kind": "buscar_acervo", "query": "q"}) is True
    assert _json.loads(h.wfile.getvalue())["delegacao_id"].startswith("curador_task_")
    # path não-curador ainda cai no handler nativo do canvas (não é forwardado)
    assert canvas_tarefas.handle_canvas_post(FakeHandler(), "/api/outro", {}) is False
