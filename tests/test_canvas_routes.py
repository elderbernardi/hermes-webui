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
    """A garantia de fato (mata o double-connect): num job JÁ CONCLUÍDO, dois
    leitores conectando com cursores diferentes recebem, cada um, seu próprio
    replay completo a partir do cursor pedido — sem consumir nem interferir
    no outro. Aciona `handle_canvas_get` de verdade (não só inspeciona o dict
    interno)."""
    monkeypatch.setattr(canvas_tarefas, "enquadrar",
                        lambda t, session=None: ({"focus": "F", "vetor": "execucao",
                                                  "intent_type": "produzir"}, []))
    h = FakeHandler()
    canvas_tarefas.handle_canvas_post(h, "/api/canvas/draft", {"text": "x"})
    cid = json.loads(h.wfile.getvalue())["canvas_id"]
    job = canvas_tarefas.CANVAS_JOBS[cid]
    with job["cond"]:
        job["cond"].wait_for(lambda: job["status"] == "done", timeout=5)

    from urllib.parse import urlparse

    # Leitor A: since=1 pula o snapshot (evento 0) mas ainda replaya
    # delta+done, encerrando sozinho (predicado satisfeito + canvas_done
    # visto -> break) sem precisar de outro thread/timeout.
    h1 = FakeHandler()
    canvas_tarefas.handle_canvas_get(
        h1, urlparse(f"/api/canvas/stream?canvas_id={cid}&since=1"))
    body1 = h1.wfile.getvalue().decode()
    assert "event: canvas_snapshot" not in body1
    assert "event: canvas_delta" in body1
    assert "event: canvas_done" in body1
    assert "id: " in body1

    # Leitor B: reconecta do zero no MESMO job já concluído — replay
    # independente e completo, incluindo o snapshot que o leitor A pulou.
    h2 = FakeHandler()
    canvas_tarefas.handle_canvas_get(
        h2, urlparse(f"/api/canvas/stream?canvas_id={cid}&since=0"))
    body2 = h2.wfile.getvalue().decode()
    assert "event: canvas_snapshot" in body2
    assert "event: canvas_delta" in body2
    assert "event: canvas_done" in body2


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


def test_list_ordenado_mais_recentes_primeiro(acervo):
    """`/api/canvas/list` ordena por nome de diretório decrescente (o id
    embute o timestamp) — slugs escolhidos para que a ordem seja garantida
    por comparação lexicográfica mesmo se os dois drafts caírem no mesmo
    segundo (sem depender de sleep/timing)."""
    from api import canvas_store
    from urllib.parse import urlparse
    cid1, _ = canvas_store.create_draft("aaa primeiro")
    cid2, _ = canvas_store.create_draft("zzz segundo")
    h = FakeHandler()
    canvas_tarefas.handle_canvas_get(h, urlparse("/api/canvas/list"))
    lista = json.loads(h.wfile.getvalue())
    ids = [item["canvas_id"] for item in lista]
    assert ids.index(cid2) < ids.index(cid1)


def test_patch_valido_persiste_e_emite(acervo):
    from api import canvas_store
    cid, _ = canvas_store.create_draft("editar")
    canvas_tarefas.CANVAS_JOBS[cid] = canvas_tarefas._new_job()
    h = FakeHandler()
    assert canvas_tarefas.handle_canvas_post(h, "/api/canvas/patch", {
        "canvas_id": cid,
        "ops": [{"op": "replace", "path": "/focus", "value": "Foco editado"},
                 {"op": "replace", "path": "/vetor", "value": "execucao"},
                 {"op": "replace", "path": "/intent_type", "value": "produzir"}]})
    assert json.loads(h.wfile.getvalue())["valid"] is True
    assert canvas_store.load_canvas(cid)["focus"] == "Foco editado"


def test_patch_path_fora_da_whitelist_400(acervo):
    from api import canvas_store
    cid, _ = canvas_store.create_draft("editar")
    h = FakeHandler()
    canvas_tarefas.handle_canvas_post(h, "/api/canvas/patch", {
        "canvas_id": cid, "ops": [{"op": "replace", "path": "/canvas_id", "value": "hack"}]})
    assert h.status == 400


def test_patch_op_com_alvo_invalido_em_runtime_400_sem_persistir(acervo):
    """Path na whitelist mas op inaplicável em runtime (remove fora do range
    de um `gaps` vazio) não deve propagar exceção nem persistir nada — 400
    limpo, doc no disco idêntico ao snapshot anterior."""
    from api import canvas_store
    cid, _ = canvas_store.create_draft("editar")
    antes = canvas_store.load_canvas(cid)
    h = FakeHandler()
    canvas_tarefas.handle_canvas_post(h, "/api/canvas/patch", {
        "canvas_id": cid, "ops": [{"op": "remove", "path": "/gaps/5"}]})
    assert h.status == 400
    assert canvas_store.load_canvas(cid) == antes


def test_patch_path_com_newline_injetado_rejeitado(acervo):
    """`re.match` deixaria "/focus\\n" passar (o "$" casa antes do "\\n"
    final); com `fullmatch` isso é rejeitado como path fora da whitelist."""
    from api import canvas_store
    cid, _ = canvas_store.create_draft("editar")
    h = FakeHandler()
    canvas_tarefas.handle_canvas_post(h, "/api/canvas/patch", {
        "canvas_id": cid,
        "ops": [{"op": "replace", "path": "/focus\n", "value": "hack"}]})
    assert h.status == 400
    assert json.loads(h.wfile.getvalue())["error"] == "path não editável"


def test_launch_cria_task_sessao_e_attachments(acervo, monkeypatch, tmp_path):
    from api import canvas_store
    cid, doc = canvas_store.create_draft("Renegociar Alfa")
    doc.update({"focus": "Renegociar Alfa", "vetor": "execucao",
                "intent_type": "produzir"})
    canvas_store.save_canvas(cid, doc)
    canvas_tarefas.CANVAS_JOBS[cid] = canvas_tarefas._new_job()

    class FakeSession:
        session_id = "sess123"

    monkeypatch.setattr(canvas_tarefas, "_new_session", lambda: FakeSession())
    monkeypatch.setattr(canvas_tarefas, "_stage_file",
                        lambda sid, p: {"name": p.name, "path": str(p),
                                        "size": p.stat().st_size,
                                        "mime": "text/plain", "is_image": False})
    reg = {"called": False}

    def fake_register(canvas_path, title):
        reg["called"] = True
        return "task_20260724_renegociar-alfa_120000"

    monkeypatch.setattr(canvas_tarefas, "_register_task", fake_register)
    h = FakeHandler()
    assert canvas_tarefas.handle_canvas_post(h, "/api/canvas/launch",
                                             {"canvas_id": cid})
    body = json.loads(h.wfile.getvalue())
    assert body["session_id"] == "sess123" and reg["called"]
    assert len(body["attachments"]) == 2 and "Renegociar Alfa" in body["brief"]


def test_launch_ambiguo_400(acervo):
    from api import canvas_store
    cid, doc = canvas_store.create_draft("x")
    doc["vetor"] = "ambiguo"; canvas_store.save_canvas(cid, doc)
    h = FakeHandler()
    canvas_tarefas.handle_canvas_post(h, "/api/canvas/launch", {"canvas_id": cid})
    assert h.status == 400
