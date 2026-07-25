import sys

import pytest

from api import canvas_enquadrador


@pytest.fixture()
def acervo(tmp_path, monkeypatch):
    (tmp_path / "micro/comercial").mkdir(parents=True)
    (tmp_path / "micro/gabinete").mkdir(parents=True)
    monkeypatch.setenv("ACERVO", str(tmp_path))
    return tmp_path


def _use_stub(monkeypatch, name):
    monkeypatch.setenv("CANVAS_LLM_CMD",
                       f"{sys.executable} tests/fixtures/{name}")


def test_enquadrar_valido(acervo, monkeypatch):
    _use_stub(monkeypatch, "stub_llm_ok.py")
    core, errors = canvas_enquadrador.enquadrar("renegociar contrato")
    assert errors == []
    assert core["vetor"] == "execucao"


def test_enquadrar_resposta_ruim_nao_lanca(acervo, monkeypatch):
    _use_stub(monkeypatch, "stub_llm_ruim.py")
    core, errors = canvas_enquadrador.enquadrar("qualquer coisa")
    assert errors and isinstance(core, dict)


def test_prompt_lista_microversos(acervo, monkeypatch):
    seen = {}
    monkeypatch.setattr(canvas_enquadrador, "_call_llm",
                        lambda p: seen.setdefault("p", p) or "{}")
    canvas_enquadrador.enquadrar("x")
    assert "comercial" in seen["p"] and "gabinete" in seen["p"]


def test_retry_apos_json_schema_invalido(acervo, monkeypatch):
    calls = []
    respostas = ['{"focus": "F"}',
                 '{"focus": "F", "vetor": "execucao", "intent_type": "produzir"}']

    def fake(prompt):
        calls.append(prompt)
        return respostas[len(calls) - 1]

    monkeypatch.setattr(canvas_enquadrador, "_call_llm", fake)
    core, errors = canvas_enquadrador.enquadrar("x")
    assert errors == [] and core["vetor"] == "execucao"
    assert len(calls) == 2 and "rejeitado" in calls[1]


def test_retry_tambem_invalido_retorna_erros(acervo, monkeypatch):
    monkeypatch.setattr(canvas_enquadrador, "_call_llm",
                        lambda p: '{"focus": "F"}')
    core, errors = canvas_enquadrador.enquadrar("x")
    assert errors and core.get("focus") == "F"


def test_call_llm_falha_de_comando_erro_diagnostico(acervo, monkeypatch):
    monkeypatch.setenv("CANVAS_LLM_CMD", "false")  # exit 1, stdout vazio
    core, errors = canvas_enquadrador.enquadrar("x")
    assert errors and any("exit" in e or "código" in e for e in errors)


def test_inprocess_usado_quando_sem_seam(acervo, monkeypatch):
    monkeypatch.delenv("CANVAS_LLM_CMD", raising=False)
    chamado = {}

    def fake_inprocess(prompt):
        chamado["p"] = prompt
        return ('{"focus": "F", "vetor": "execucao", "intent_type": "produzir"}')

    monkeypatch.setattr(canvas_enquadrador, "_call_llm_inprocess", fake_inprocess)
    core, errors = canvas_enquadrador.enquadrar("fazer X")
    assert errors == [] and chamado


def test_inprocess_indisponivel_estado_calmo(acervo, monkeypatch):
    monkeypatch.delenv("CANVAS_LLM_CMD", raising=False)

    def boom(prompt):
        raise RuntimeError("agent runtime offline")

    monkeypatch.setattr(canvas_enquadrador, "_call_llm_inprocess", boom)
    core, errors = canvas_enquadrador.enquadrar("x")
    assert core == {} and any("indisponível" in e for e in errors)


def test_extract_json_com_cerca_markdown(acervo, monkeypatch):
    monkeypatch.setenv("CANVAS_LLM_CMD", "true")
    monkeypatch.setattr(
        canvas_enquadrador, "_call_llm",
        lambda p: '```json\n{"focus": "F", "vetor": "execucao", "intent_type": "produzir"}\n```')
    core, errors = canvas_enquadrador.enquadrar("x")
    assert errors == []
