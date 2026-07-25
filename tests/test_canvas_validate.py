import pytest

from api import canvas_validate

CORE_OK = {"focus": "Renegociar contrato Alfa", "vetor": "execucao",
           "intent_type": "produzir", "gaps": ["Teto de desconto?"]}


@pytest.fixture()
def acervo(tmp_path, monkeypatch):
    (tmp_path / "global/tools/harness").mkdir(parents=True)
    monkeypatch.setenv("ACERVO", str(tmp_path))
    return tmp_path


def test_core_valido_passa(acervo):
    ok, errors = canvas_validate.validate_core(dict(CORE_OK))
    assert ok, errors


def test_obrigatorio_ausente_falha(acervo):
    core = dict(CORE_OK); core.pop("vetor")
    ok, errors = canvas_validate.validate_core(core)
    assert not ok and any("vetor" in e for e in errors)


def test_enum_invalido_falha(acervo):
    core = dict(CORE_OK); core["vetor"] = "turbo"
    ok, errors = canvas_validate.validate_core(core)
    assert not ok


def test_campo_desconhecido_falha(acervo):
    core = dict(CORE_OK); core["surpresa"] = 1
    ok, errors = canvas_validate.validate_core(core)
    assert not ok and any("desconhecido" in e for e in errors)


def test_schema_oficial_usado_quando_presente(acervo):
    (acervo / "global/tools/harness/canvas_schema.py").write_text(
        "CANVAS_SCHEMA = {'type': 'object', 'required': ['focus']}\n")
    assert canvas_validate.load_schema() == {"type": "object", "required": ["focus"]}


def test_enum_nao_string_nao_lanca(acervo):
    core = dict(CORE_OK); core["vetor"] = ["execucao"]
    ok, errors = canvas_validate.validate_core(core)
    assert not ok and any("vetor" in e for e in errors)


def test_v05_intent_type_8_e_campos_metodo(acervo):
    core = dict(CORE_OK, intent_type="publicar", shape="tarefa",
                done_criteria="oficio aprovado", verification="manifest+receipt")
    ok, errors = canvas_validate.validate_core(core)
    assert ok, errors


def test_v05_shape_invalido_falha(acervo):
    core = dict(CORE_OK, shape="epico")
    ok, errors = canvas_validate.validate_core(core)
    assert not ok and any("shape" in e for e in errors)
