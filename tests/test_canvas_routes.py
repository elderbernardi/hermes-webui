import io
import json

import pytest

from api import canvas_tarefas


class FakeHandler:
    def __init__(self):
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, code):
        self.status = code

    def send_header(self, *a):
        pass

    def end_headers(self):
        pass


@pytest.fixture()
def acervo(tmp_path, monkeypatch):
    (tmp_path / "_tasks").mkdir()
    (tmp_path / "global/templates/harness-v0.4").mkdir(parents=True)
    monkeypatch.setenv("ACERVO", str(tmp_path))
    return tmp_path


def test_draft_dispara_snapshot_delta_done(acervo, monkeypatch):
    monkeypatch.setattr(
        canvas_tarefas, "enquadrar",
        lambda t, session=None: ({"focus": "F", "vetor": "execucao",
                    "intent_type": "produzir", "gaps": ["g"]}, []))
    h = FakeHandler()
    assert canvas_tarefas.handle_canvas_post(
        h, "/api/canvas/draft", {"text": "renegociar Alfa"})
    cid = json.loads(h.wfile.getvalue())["canvas_id"]
    job = canvas_tarefas.CANVAS_JOBS[cid]
    with job["cond"]:
        job["cond"].wait_for(lambda: job["status"] == "done", timeout=5)
    eventos = [n for n, _ in job["events"]]
    assert eventos == ["canvas_snapshot", "canvas_delta", "canvas_done"]


def test_draft_sem_texto_400(acervo):
    h = FakeHandler()
    assert canvas_tarefas.handle_canvas_post(h, "/api/canvas/draft", {})
    assert h.status == 400


def test_path_desconhecido_retorna_false(acervo):
    assert not canvas_tarefas.handle_canvas_post(FakeHandler(), "/api/outro", {})


def test_core_invalido_nao_persiste_nem_emite_delta(acervo, monkeypatch):
    monkeypatch.setattr(
        canvas_tarefas, "enquadrar",
        lambda t, session=None: ({"focus": "F", "vetor": "turbo"}, ["vetor fora do enum"]))
    h = FakeHandler()
    canvas_tarefas.handle_canvas_post(h, "/api/canvas/draft", {"text": "x"})
    cid = json.loads(h.wfile.getvalue())["canvas_id"]
    job = canvas_tarefas.CANVAS_JOBS[cid]
    with job["cond"]:
        job["cond"].wait_for(lambda: job["status"] == "done", timeout=5)
    eventos = job["events"]
    assert [e[0] for e in eventos] == ["canvas_snapshot", "canvas_done"]
    assert eventos[1][1]["valid"] is False
    from api import canvas_store
    assert canvas_store.load_canvas(cid)["focus"] == ""


def test_excecao_no_enquadrador_emite_done_invalido(acervo, monkeypatch):
    def boom(t, session=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(canvas_tarefas, "enquadrar", boom)
    h = FakeHandler()
    canvas_tarefas.handle_canvas_post(h, "/api/canvas/draft", {"text": "x"})
    cid = json.loads(h.wfile.getvalue())["canvas_id"]
    job = canvas_tarefas.CANVAS_JOBS[cid]
    with job["cond"]:
        job["cond"].wait_for(lambda: job["status"] == "done", timeout=5)
    nomes = [n for n, _ in job["events"]]
    assert nomes == ["canvas_snapshot", "canvas_done"]


def test_get_inexistente_nao_vaza_caminho(acervo):
    h = FakeHandler()
    from urllib.parse import urlparse
    canvas_tarefas.handle_canvas_get(
        h, urlparse("/api/canvas/get?canvas_id=canvas_20260101_000000_x0"))
    assert h.status == 404
    body = h.wfile.getvalue().decode()
    assert "/home/" not in body and "_tasks" not in body


def test_registry_limpo_apos_delay_mesmo_sem_stream(acervo, monkeypatch):
    import time as _t
    monkeypatch.setattr(canvas_tarefas, "_CLEANUP_DELAY", 0.05)
    monkeypatch.setattr(
        canvas_tarefas, "enquadrar",
        lambda t, session=None: ({"focus": "F", "vetor": "execucao",
                    "intent_type": "produzir"}, []))
    h = FakeHandler()
    canvas_tarefas.handle_canvas_post(h, "/api/canvas/draft", {"text": "x"})
    cid = json.loads(h.wfile.getvalue())["canvas_id"]
    deadline = _t.time() + 2
    while cid in canvas_tarefas.CANVAS_JOBS and _t.time() < deadline:
        _t.sleep(0.02)
    assert cid not in canvas_tarefas.CANVAS_JOBS


def test_replay_por_cursor_dois_leitores(acervo, monkeypatch):
    monkeypatch.setattr(canvas_tarefas, "enquadrar",
                        lambda t, session=None: ({"focus": "F", "vetor": "execucao",
                                                  "intent_type": "produzir"}, []))
    h = FakeHandler()
    canvas_tarefas.handle_canvas_post(h, "/api/canvas/draft", {"text": "x"})
    cid = json.loads(h.wfile.getvalue())["canvas_id"]
    job = canvas_tarefas.CANVAS_JOBS[cid]
    with job["cond"]:
        job["cond"].wait_for(lambda: job["status"] == "done", timeout=5)
    nomes = [n for n, _ in job["events"]]
    assert nomes == ["canvas_snapshot", "canvas_delta", "canvas_done"]
    assert nomes == [n for n, _ in job["events"]]  # segunda leitura idêntica (replay)


def test_poll_endpoint(acervo, monkeypatch):
    monkeypatch.setattr(canvas_tarefas, "enquadrar",
                        lambda t, session=None: ({"focus": "F", "vetor": "execucao",
                                                  "intent_type": "produzir"}, []))
    h = FakeHandler()
    canvas_tarefas.handle_canvas_post(h, "/api/canvas/draft", {"text": "x"})
    cid = json.loads(h.wfile.getvalue())["canvas_id"]
    job = canvas_tarefas.CANVAS_JOBS[cid]
    with job["cond"]:
        job["cond"].wait_for(lambda: job["status"] == "done", timeout=5)
    h2 = FakeHandler()
    from urllib.parse import urlparse
    canvas_tarefas.handle_canvas_get(h2, urlparse(f"/api/canvas/job?canvas_id={cid}"))
    body = json.loads(h2.wfile.getvalue())
    assert body["status"] == "done" and body["valid"] is True and body["n_events"] == 3


def test_list_para_o_atrio(acervo, monkeypatch):
    from api import canvas_store
    cid, _ = canvas_store.create_draft("listar isto")
    h = FakeHandler()
    from urllib.parse import urlparse
    canvas_tarefas.handle_canvas_get(h, urlparse("/api/canvas/list"))
    lista = json.loads(h.wfile.getvalue())
    assert any(item["canvas_id"] == cid for item in lista)
