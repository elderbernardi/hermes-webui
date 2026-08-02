"""F4 Receita — canvas → receita clean-portable (núcleo puro)."""
import copy
import yaml
from api import canvas_store

_STRUCTURE_KEYS = ("vetor", "shape", "intent_type", "done_criteria", "verification")


def clean_portable(doc: dict) -> dict:
    """Strip instance-specific fields, preserve structure."""
    cp: dict = {k: doc.get(k) for k in _STRUCTURE_KEYS if doc.get(k) is not None}
    cp["microversos"] = {"primary": None, "related": list(doc.get("microversos", {}).get("related", []))}
    cp["intake_questions"] = list(doc.get("gaps", []))          # gaps recorrentes viram perguntas de intake
    p = doc.get("personas", {})
    cp["personas"] = {"slots": list(p.get("suggested", [])) + list(p.get("evaluators", []))}
    cp["artifacts_expected"] = [{"title": a.get("title"), "type": a.get("type")}
                                for a in doc.get("artifacts", {}).get("expected", [])]
    # instância removida: canvas_id, focus (nomes próprios), authorization, promotion_candidates, scope, assumptions
    return cp


def recipe_body(doc: dict) -> str:
    """YAML representation of clean-portable structure (corpo da receita)."""
    return yaml.safe_dump(clean_portable(doc), allow_unicode=True, sort_keys=False)


def prefill_from_recipe(recipe: dict) -> dict:
    """Create a new canvas doc seeded from recipe structure."""
    cp = recipe["structure"]
    # Use deepcopy to avoid shared references in nested dicts
    doc = copy.deepcopy(canvas_store._MINIMAL)
    for k in _STRUCTURE_KEYS:
        if k in cp:
            doc[k] = cp[k]
    doc["gaps"] = list(cp.get("intake_questions", []))
    doc["microversos"] = {"primary": None, "related": list(cp.get("microversos", {}).get("related", []))}
    doc["personas"] = {"suggested": list(cp.get("personas", {}).get("slots", [])), "explicit": [], "evaluators": []}
    doc["focus"] = recipe.get("focus_template", "")
    return doc
