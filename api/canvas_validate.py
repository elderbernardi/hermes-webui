"""EXCRTX MOD-011 (spike F0) — validação do NÚCLEO do canvas (schema v0.4 oficial).

Valida manualmente (obrigatórios, enums, campos extras) e, se `jsonschema`
estiver instalado E o schema oficial existir no acervo, valida também contra
ele. Nunca exige dependência nova.
"""
from __future__ import annotations

import importlib.util

from api.canvas_store import acervo_root

_REQUIRED = ("focus", "vetor", "intent_type")
_ENUMS = {
    "vetor": {"execucao", "evolucao", "manutencao", "ambiguo"},
    "intent_type": {"explorar", "decidir", "produzir", "revisar", "manter"},
    "macroverso_status": {"resolved", "partial", "placeholder", "missing"},
    "urgency": {"alta", "media", "baixa"},
}
_ALLOWED = set(_ENUMS) | {"focus", "microverso_primary", "gaps"}


def load_schema() -> dict | None:
    path = acervo_root() / "global/tools/harness/canvas_schema.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("excrtx_canvas_schema", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "CANVAS_SCHEMA", None)


def validate_core(core) -> tuple[bool, list[str]]:
    if not isinstance(core, dict):
        return False, ["núcleo não é objeto JSON"]
    errors = [f"campo obrigatório ausente/vazio: {k}"
              for k in _REQUIRED if not core.get(k)]
    errors += [f"campo desconhecido: {k}" for k in core if k not in _ALLOWED]
    for field, allowed in _ENUMS.items():
        v = core.get(field)
        if v is not None and v not in allowed:
            errors.append(f"{field} fora do enum: {v!r}")
    mp = core.get("microverso_primary")
    if mp is not None and not isinstance(mp, str):
        errors.append("microverso_primary deve ser string ou null")
    if core.get("gaps") is not None and (
            not isinstance(core["gaps"], list)
            or any(not isinstance(g, str) for g in core["gaps"])):
        errors.append("gaps deve ser lista de strings")
    schema = load_schema()
    if schema is not None:
        try:
            import jsonschema
            jsonschema.validate(core, schema)
        except ImportError:
            pass  # sem dependência nova; validação manual acima cobre o essencial
        except Exception as exc:
            msg = str(exc).splitlines()[0]
            if msg not in errors:
                errors.append(f"schema: {msg}")
    return (not errors, errors)
