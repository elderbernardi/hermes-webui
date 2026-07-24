import pytest

from api import canvas_store


@pytest.fixture()
def acervo(tmp_path, monkeypatch):
    (tmp_path / "_tasks").mkdir()
    (tmp_path / "global/templates/harness-v0.4").mkdir(parents=True)
    monkeypatch.setenv("ACERVO", str(tmp_path))
    return tmp_path


def test_create_draft_persiste_yaml(acervo):
    cid, canvas = canvas_store.create_draft("Renegociar contrato Alfa")
    assert (acervo / "_tasks" / cid / "canvas.yaml").is_file()
    assert canvas["original_input_summary"] == "Renegociar contrato Alfa"
    assert canvas_store.load_canvas(cid)["canvas_id"] == cid


def test_drafts_nao_compartilham_estado(acervo):
    _, c1 = canvas_store.create_draft("a")
    canvas_store.apply_patch(c1, [{"op": "add", "path": "/gaps/-", "value": "g"}])
    _, c2 = canvas_store.create_draft("b")
    assert c2["gaps"] == []


def test_apply_patch_add_replace_remove(acervo):
    cid, canvas = canvas_store.create_draft("x")
    canvas = canvas_store.apply_patch(canvas, [
        {"op": "replace", "path": "/focus", "value": "Foco novo"},
        {"op": "add", "path": "/gaps/-", "value": "Teto de desconto?"},
    ])
    assert canvas["focus"] == "Foco novo"
    assert canvas["gaps"] == ["Teto de desconto?"]
    canvas = canvas_store.apply_patch(canvas, [{"op": "remove", "path": "/gaps/0"}])
    assert canvas["gaps"] == []


def test_core_to_patch_mapeia_nucleo_para_documento(acervo):
    ops = canvas_store.core_to_patch({
        "focus": "F", "vetor": "execucao", "intent_type": "produzir",
        "microverso_primary": "comercial", "gaps": ["g1", "g2"],
    })
    assert {"op": "replace", "path": "/vector", "value": "execucao"} in ops
    assert {"op": "replace", "path": "/microversos/primary", "value": "comercial"} in ops
    assert {"op": "add", "path": "/gaps/-", "value": "g2"} in ops


def test_canvas_id_invalido_rejeitado(acervo):
    with pytest.raises(ValueError):
        canvas_store.load_canvas("../../etc/passwd")
