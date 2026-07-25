"""EXCRTX MOD-011 (spike F0) — enquadrador: 1 frase do executivo → núcleo do canvas.

O LLM entra por um seam externo (env CANVAS_LLM_CMD: lê prompt no stdin,
imprime resposta). A escolha definitiva de invocação (runtime in-process,
síncrono vs job+poll) é a ADR-CT-04 — decidida com as medições da T6.
"""
from __future__ import annotations

import json
import os
import subprocess

from api.canvas_store import acervo_root
from api.canvas_validate import validate_core

_PROMPT = """Você é o enquadrador do Exocórtex (EX-05/EX-06). Analise o pedido do executivo
e responda SOMENTE com um objeto JSON válido, sem markdown, com exatamente estes campos:
{{"focus": string, "vetor": "execucao"|"evolucao"|"manutencao"|"ambiguo",
 "intent_type": "explorar"|"decidir"|"produzir"|"revisar"|"manter",
 "macroverso_status": "resolved"|"partial"|"placeholder"|"missing",
 "microverso_primary": string|null, "gaps": [string], "urgency": "alta"|"media"|"baixa"}}

Regras: microverso_primary deve ser um dos microversos existentes (ou null se nenhum casa);
gaps são perguntas cuja resposta só o executivo tem (nunca invente); use vetor "ambiguo"
quando não dá para saber se é para executar, explorar ou manter.

Microversos existentes: {microversos}

Pedido do executivo: {texto}
"""


def _microversos() -> list[str]:
    micro = acervo_root() / "micro"
    if not micro.is_dir():
        return []
    return sorted(p.name for p in micro.iterdir()
                  if p.is_dir() and not p.name.startswith(("_", ".")))


def _call_llm(prompt: str) -> str:
    cmd = os.environ.get("CANVAS_LLM_CMD")
    if not cmd:
        raise RuntimeError("CANVAS_LLM_CMD não definido (seam do spike F0)")
    proc = subprocess.run(cmd, shell=True, input=prompt.encode("utf-8"),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(
            f"CANVAS_LLM_CMD exit {proc.returncode}: "
            f"{proc.stderr.decode('utf-8', 'replace')[-200:]}")
    return proc.stdout.decode("utf-8", "replace")


def _parse_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("resposta sem JSON")
    return json.loads(text[start:end + 1])


def enquadrar(texto: str) -> tuple[dict, list[str]]:
    prompt = _PROMPT.format(
        microversos=", ".join(_microversos()) or "(nenhum)", texto=texto.strip())
    try:
        core = _parse_json(_call_llm(prompt))
        ok, errors = validate_core(core)
    except Exception as exc:
        return {}, [f"enquadrador falhou: {exc}"]
    if ok:
        return core, []
    retry = (prompt + "\n\nSeu JSON anterior foi rejeitado: " + "; ".join(errors)
             + "\nResponda novamente SOMENTE com o JSON corrigido.")
    try:
        core2 = _parse_json(_call_llm(retry))
        ok2, errors2 = validate_core(core2)
        return (core2, []) if ok2 else (core2, errors2)
    except Exception as exc:
        return core, errors + [f"retry falhou: {exc}"]
