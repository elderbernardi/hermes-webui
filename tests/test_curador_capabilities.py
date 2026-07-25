import json
import pytest
from api import curador_capabilities as cap


@pytest.fixture()
def acervo(tmp_path):
    idx = tmp_path / "micro/comercial/_meta"
    idx.mkdir(parents=True)
    (idx / "index.md").write_text(
        "# Index — comercial\n\n### Persona\n- persona/negociador.md — negociação dura\n"
        "### Templates\n- templates/oficio.md — modelo de ofício\n", encoding="utf-8")
    (tmp_path / "global/tools/state").mkdir(parents=True)
    return tmp_path


def test_build_agent_card_deriva_de_index(acervo):
    card = cap.build_agent_card("comercial", root=acervo)
    assert card["name"] == "comercial"
    assert card["version"]                              # digest presente
    natures = {s["name"] for s in card["skills"]}
    assert "persona" in natures


def test_build_agent_card_idempotente(acervo):
    a = cap.build_agent_card("comercial", root=acervo)
    b = cap.build_agent_card("comercial", root=acervo)
    assert a["version"] == b["version"]                 # mesma entrada -> mesmo digest


def test_refresh_escreve_cache_off_trail(acervo):
    p = cap.refresh_capability_cache(root=acervo)
    assert p == acervo / "global/tools/state/curador/capabilities.json"
    assert p.is_file()
    blob = json.loads(p.read_text(encoding="utf-8"))
    assert "comercial" in blob["microversos"]


def test_refresh_idempotente_nao_muda_digest(acervo):
    p = cap.refresh_capability_cache(root=acervo)
    d1 = json.loads(p.read_text(encoding="utf-8"))["digest"]
    p = cap.refresh_capability_cache(root=acervo)
    d2 = json.loads(p.read_text(encoding="utf-8"))["digest"]
    assert d1 == d2


def test_load_le_so_o_cache(acervo):
    assert cap.load_capability_card("comercial", root=acervo) is None   # sem cache ainda
    cap.refresh_capability_cache(root=acervo)
    card = cap.load_capability_card("comercial", root=acervo)
    assert card and card["name"] == "comercial"


def test_load_degrada_sem_cache(acervo):
    assert cap.load_capability_card("inexistente", root=acervo) is None


def test_modulo_leitor_do_curador_nao_importa_escritor():
    import api.canvas_curador as cc, pathlib
    src = pathlib.Path(cc.__file__).read_text(encoding="utf-8")
    assert "load_capability_card" in src
    assert "refresh_capability_cache" not in src        # worker nunca escreve o cache
