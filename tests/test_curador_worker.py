import threading
import time
import pytest

from api import canvas_curador, curador_a2a as a2a


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
