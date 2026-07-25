import io, json, pytest
from api import canvas_tarefas, canvas_store


class FakeHandler:
    def __init__(self): self.wfile = io.BytesIO(); self.status = None
    def send_response(self, c): self.status = c
    def send_header(self, *a): pass
    def end_headers(self): pass


@pytest.fixture()
def acervo(tmp_path, monkeypatch):
    (tmp_path / "_tasks").mkdir()
    monkeypatch.setenv("ACERVO", str(tmp_path))
    return tmp_path


def _draft(acervo):
    # create_draft deixa focus="" (via _MINIMAL); validate_core exige focus não-vazio
    # (minLength 3) -> setar antes do accept, senão `assert valid is True` falha.
    cid, canvas = canvas_store.create_draft("renegociar contrato")
    canvas["focus"] = "renegociar contrato Alfa"
    canvas["vetor"] = "execucao"
    canvas["intent_type"] = "produzir"
    canvas_store.save_canvas(cid, canvas)
    return cid


def test_minimal_tem_zonas_do_curador():
    assert "personas" in canvas_store._MINIMAL
    assert canvas_store._MINIMAL["personas"]["suggested"] == []
    assert canvas_store._MINIMAL["acervo_aplicado"] == []


def test_whitelist_aceita_personas_e_acervo_aplicado():
    assert canvas_tarefas._path_editavel("/personas/suggested/-")
    assert canvas_tarefas._path_editavel("/acervo_aplicado/-")
    assert canvas_tarefas._path_editavel("/acervo_aplicado/0")


def test_aceitar_persona_pousa_e_valida(acervo):
    cid = _draft(acervo)
    h = FakeHandler()
    canvas_tarefas._handle_patch(h, {"canvas_id": cid, "ops": [
        {"op": "add", "path": "/personas/suggested/-", "value": "negociador"}]})
    body = json.loads(h.wfile.getvalue())
    assert body["ok"] is True and body["valid"] is True
    doc = canvas_store.load_canvas(cid)
    assert doc["personas"]["suggested"] == ["negociador"]


def test_aceitar_acervo_aplicado_objeto(acervo):
    cid = _draft(acervo)
    h = FakeHandler()
    canvas_tarefas._handle_patch(h, {"canvas_id": cid, "ops": [
        {"op": "add", "path": "/acervo_aplicado/-",
         "value": {"path": "micro/comercial/templates/oficio.md",
                   "nature": "template", "porque": "modelo pronto"}}]})
    assert json.loads(h.wfile.getvalue())["ok"] is True
    doc = canvas_store.load_canvas(cid)
    assert doc["acervo_aplicado"][0]["nature"] == "template"


def test_path_nao_whitelisted_400(acervo):
    cid = _draft(acervo)
    h = FakeHandler()
    canvas_tarefas._handle_patch(h, {"canvas_id": cid, "ops": [
        {"op": "add", "path": "/personas/explicit/-", "value": "x"}]})
    assert h.status == 400          # só /personas/suggested/* é whitelisted p/ o Curador
