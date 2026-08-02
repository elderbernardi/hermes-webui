import pytest
from api import canvas_receita as R

CANVAS = {
    "canvas_id": "canvas_20260801_abc", "focus": "Renegociar com Cliente Alfa",
    "vetor": "execucao", "shape": "tarefa", "intent_type": "produzir",
    "done_criteria": "ofício aprovado", "verification": "manifest + SHA-256",
    "microversos": {"primary": "cliente-alfa", "related": ["juridico"]},
    "gaps": ["Teto de desconto?", "Prazo de vigência?"],
    "personas": {"suggested": ["redator-institucional"], "explicit": [], "evaluators": ["critico"]},
    "artifacts": {"expected": [{"title": "oficio.docx", "path": "x/oficio.docx", "type": "docx"}]},
    "authorization": [{"action": "enviar email", "words": "pode enviar", "at": "..."}],
    "promotion_candidates": {"knowledge": ["algo instanciado"]},
}

def test_clean_portable_strips_instance_keeps_structure():
    cp = R.clean_portable(CANVAS)
    assert "canvas_id" not in cp
    assert cp["microversos"]["primary"] is None          # vínculo de instância removido
    assert cp.get("authorization", []) == []             # palavras de AUTH removidas
    assert "promotion_candidates" not in cp              # instâncias removidas
    assert cp["vetor"] == "execucao" and cp["shape"] == "tarefa"     # estrutura preservada
    assert cp["verification"] == "manifest + SHA-256"
    assert cp["intake_questions"] == ["Teto de desconto?", "Prazo de vigência?"]  # gaps → intake
    assert cp["personas"]["slots"] == ["redator-institucional", "critico"]

def test_recipe_body_is_yaml_without_secrets():
    body = R.recipe_body(CANVAS)
    assert "canvas_20260801_abc" not in body and "pode enviar" not in body
    assert "vetor: execucao" in body

def test_prefill_from_recipe_seeds_new_canvas():
    cp = R.clean_portable(CANVAS)
    doc = R.prefill_from_recipe({"structure": cp, "focus_template": "Renegociar com <cliente>"})
    assert doc["vetor"] == "execucao" and doc["shape"] == "tarefa"
    assert doc["done_criteria"] == "ofício aprovado"
    assert doc["gaps"] == ["Teto de desconto?", "Prazo de vigência?"]
    assert doc["microversos"]["primary"] is None
