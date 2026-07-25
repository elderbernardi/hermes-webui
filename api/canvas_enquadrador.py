"""EXCRTX MOD-011 (spike F0 -> F1) — enquadrador: 1 frase do executivo → núcleo do canvas.

ADR-CT-04: por default o LLM entra IN-PROCESS (um turno síncrono, tool-less, via
agent.auxiliary_client.call_llm sob o profile env ativo — precedente:
api.streaming's title_generation + api.acervo_studio_agent._run_agent_text). O
seam externo original do spike (env CANVAS_LLM_CMD: lê prompt no stdin, imprime
resposta) permanece como override — usado hoje pelos testes hermeticos deste
módulo e por quem quiser plugar um LLM externo em dev.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess

from api.canvas_store import acervo_root
from api.canvas_validate import validate_core

logger = logging.getLogger("canvas_enquadrador")

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


def _call_llm_seam(prompt: str) -> str:
    """Subprocess seam (env CANVAS_LLM_CMD) — override explícito p/ testes/dev.
    Comportamento e mensagens inalterados desde o spike F0."""
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


def _call_llm_inprocess(prompt: str) -> str:
    """Turno único in-process (ADR-CT-04). Precedente: api.streaming's
    title_generation (agent.auxiliary_client.call_llm) + api.acervo_studio_agent
    ._run_agent_text (profile env + runtime resolve). Diverge do rascunho da
    brief em dois símbolos (ver task-3-report.md para o recon completo):
    `profiles.get_active_profile_name()` (não existe `get_active_profile()`) e
    `profile_env_for_background_worker(profile, purpose, logger_override=...)`
    (tem `purpose` posicional além do profile/session)."""
    from api import profiles as profiles_api
    from api.acervo_studio_agent import _resolve_main_runtime

    active_profile = profiles_api.get_active_profile_name() or "default"
    with profiles_api.profile_env_for_background_worker(
            active_profile, "canvas enquadrador", logger_override=logger):
        runtime = _resolve_main_runtime(None)
        from agent.auxiliary_client import call_llm
        resp = call_llm(provider=runtime["provider"], model=runtime["model"],
                        base_url=runtime.get("base_url"),
                        api_key=runtime.get("api_key"),
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0)
        return resp.choices[0].message.content or ""


def _call_llm(prompt: str) -> str:
    """Router (ADR-CT-04): CANVAS_LLM_CMD setado -> seam (teste/dev override);
    senão -> in-process (default de produção)."""
    if os.environ.get("CANVAS_LLM_CMD"):
        return _call_llm_seam(prompt)
    return _call_llm_inprocess(prompt)


def _parse_json(text: str) -> dict:
    """Extrai o primeiro objeto JSON da resposta, tolerando cercas ```/```json
    (estilo api.acervo_studio_agent._extract_json — mais robusto que o
    find-braces cru do spike F0 quando o modelo devolve markdown)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else None
    if raw is None:
        start, end = text.find("{"), text.rfind("}")
        raw = text[start:end + 1] if (start >= 0 and end > start) else None
    if raw is None:
        raise ValueError("resposta sem JSON")
    return json.loads(raw)


def enquadrar(texto: str, session=None) -> tuple[dict, list[str]]:
    prompt = _PROMPT.format(
        microversos=", ".join(_microversos()) or "(nenhum)", texto=texto.strip())
    seam = bool(os.environ.get("CANVAS_LLM_CMD"))
    try:
        core = _parse_json(_call_llm(prompt))
        ok, errors = validate_core(core)
    except Exception as exc:
        # Estado calmo (nunca crash). O ramo seam mantém a mensagem "falhou" dos
        # testes F0; só o ramo in-process (indisponibilidade do agente/runtime)
        # usa "indisponível", por ADR-CT-04.
        prefix = "enquadrador falhou" if seam else "enquadrador indisponível"
        return {}, [f"{prefix}: {exc}"]
    if ok:
        return core, []
    retry = (prompt + "\n\nSeu JSON anterior foi rejeitado: " + "; ".join(errors)
             + "\nResponda novamente SOMENTE com o JSON corrigido.")
    try:
        core2 = _parse_json(_call_llm(retry))
        ok2, errors2 = validate_core(core2)
        return (core2, []) if ok2 else (core2, errors2)
    except Exception as exc:
        prefix = "retry falhou" if seam else "retry indisponível"
        return core, errors + [f"{prefix}: {exc}"]
