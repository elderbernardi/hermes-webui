import io
import json
from urllib.parse import urlparse

from api import canvas_tarefas, canvas_store


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


def test_microversos_lista_slugs_ordenados(tmp_path, monkeypatch):
    micro = tmp_path / "micro"
    for slug in ("gabinete", "comercial", "sales-ai"):
        (micro / slug).mkdir(parents=True)
    monkeypatch.setenv("ACERVO", str(tmp_path))
    h = FakeHandler()
    assert canvas_tarefas.handle_canvas_get(h, urlparse("/api/canvas/microversos"))
    body = json.loads(h.wfile.getvalue())
    assert body == ["comercial", "gabinete", "sales-ai"]  # ordenado
    assert h.status == 200


def test_microversos_ignora_underscore_ocultos_e_arquivos(tmp_path, monkeypatch):
    micro = tmp_path / "micro"
    for name in ("comercial", "_tasks", ".git"):
        (micro / name).mkdir(parents=True)
    (micro / "leiame.txt").write_text("x", encoding="utf-8")
    monkeypatch.setenv("ACERVO", str(tmp_path))
    h = FakeHandler()
    canvas_tarefas.handle_canvas_get(h, urlparse("/api/canvas/microversos"))
    assert json.loads(h.wfile.getvalue()) == ["comercial"]


def test_microversos_sem_acervo_retorna_200_lista_vazia(monkeypatch):
    def _boom():
        raise RuntimeError("ACERVO não encontrado")
    monkeypatch.setattr(canvas_store, "acervo_root", _boom)
    h = FakeHandler()
    assert canvas_tarefas.handle_canvas_get(h, urlparse("/api/canvas/microversos"))
    assert json.loads(h.wfile.getvalue()) == []
    assert h.status == 200
