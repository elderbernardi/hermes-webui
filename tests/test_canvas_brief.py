import pytest

from api import canvas_brief

DOC = {"focus": "Renegociar contrato Alfa", "vetor": "execucao",
       "intent_type": "produzir", "shape": "tarefa",
       "done_criteria": "oficio aprovado", "verification": "manifest+receipt",
       "microversos": {"primary": "comercial", "related": ["juridico"]},
       "gaps": ["Teto de desconto?"], "scope": [], "assumptions": [],
       "artifacts": {"existing": [], "expected": ["oficio.docx"]},
       "next_moves": []}


def test_brief_contem_blocos_essenciais():
    b = canvas_brief.compile_brief(dict(DOC))
    for trecho in ("Renegociar contrato Alfa", "oficio aprovado",
                   "manifest+receipt", "comercial", "juridico",
                   "Premissa (gap aberto): Teto de desconto?", "oficio.docx"):
        assert trecho in b, trecho


def test_brief_rejeita_ambiguo():
    with pytest.raises(ValueError):
        canvas_brief.compile_brief(dict(DOC, vetor="ambiguo"))


def test_brief_e_deterministico():
    assert canvas_brief.compile_brief(dict(DOC)) == canvas_brief.compile_brief(dict(DOC))
