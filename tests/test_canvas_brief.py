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


def test_brief_sem_curador_nao_renderiza_blocos():
    # fluxo F1b: personas.suggested e acervo_aplicado vazios -> blocos ausentes
    b = canvas_brief.compile_brief(dict(DOC))
    assert "Personas sugeridas" not in b
    assert "Acervo aplicado" not in b


def test_brief_renderiza_personas_e_acervo_aceitos():
    doc = dict(DOC,
               personas={"suggested": ["negociador"], "explicit": [], "evaluators": []},
               acervo_aplicado=[{"path": "micro/comercial/templates/oficio.md",
                                 "nature": "template", "porque": "modelo pronto"}])
    b = canvas_brief.compile_brief(doc)
    assert "Personas sugeridas:" in b
    assert "- negociador" in b
    assert "Acervo aplicado:" in b
    assert "micro/comercial/templates/oficio.md (template) — modelo pronto" in b


def test_with_task_id_appends_marker_and_preserves_brief():
    from api.canvas_brief import with_task_id
    out = with_task_id("Brief: renegociar\n\nPostura: execução\n", "task_20260728_ab12cd")
    assert out.startswith("Brief: renegociar")            # original preserved
    assert "Task ID (para o conduct.jsonl): task_20260728_ab12cd" in out
    assert out.endswith("\n")                              # trailing newline kept
    # idempotent shape: exactly one marker line
    assert out.count("Task ID (para o conduct.jsonl):") == 1
