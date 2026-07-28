"""EXCRTX MOD-011 (F1) — compilador determinístico do brief de lançamento.

SEM LLM: o texto é montado por um template PT-BR fixo a partir do documento
do canvas (schema v0.5). `vetor == "ambiguo"` bloqueia a compilação — o
vetor precisa estar resolvido antes de o canvas virar um brief de execução.
"""
from __future__ import annotations

_POSTURA = {
    "execucao": ("Postura: execução — o foco é entregar o resultado "
                 "combinado, sem reabrir escopo no meio do caminho."),
    "evolucao": ("Postura: evolução — há espaço para explorar alternativas "
                 "e ajustar a direção conforme o aprendizado."),
    "manutencao": ("Postura: manutenção — preservar o que já funciona, com "
                   "mudanças mínimas e reversíveis."),
}


def _bloco_lista(titulo: str, itens: list[str]) -> list[str]:
    if not itens:
        return []
    return [f"{titulo}:"] + [f"- {item}" for item in itens] + [""]


def _fmt_acervo_item(item) -> str:
    """Um item de `acervo_aplicado` é {path, nature, porque} (ver
    canvas.yaml/_MINIMAL); serializa em uma linha legível. Aceita string
    solta por robustez."""
    if not isinstance(item, dict):
        return str(item)
    path = item.get("path") or ""
    nature = item.get("nature") or ""
    porque = item.get("porque") or ""
    head = f"{path} ({nature})" if nature else path
    return f"{head} — {porque}" if porque else head


def compile_brief(doc: dict) -> str:
    vetor = doc.get("vetor")
    if vetor == "ambiguo":
        raise ValueError("resolva o vetor antes de lançar")

    linhas: list[str] = [f"Brief: {doc.get('focus', '')}", ""]

    linhas.append(_POSTURA.get(vetor, f"Postura: {vetor}"))
    linhas.append("")

    done = (doc.get("done_criteria") or "").strip()
    verif = (doc.get("verification") or "").strip()
    if done and verif:
        linhas.append(f"Pronto quando: {done} — Verificação: {verif}")
    else:
        linhas.append("DEFINIR PRONTO na sessão.")
    linhas.append("")

    microversos = doc.get("microversos") or {}
    primary = microversos.get("primary")
    related = microversos.get("related") or []
    if primary:
        linhas.append(f"Microverso âncora: {primary}")
    if related:
        linhas.append(f"Apoios: {', '.join(related)}")
    if primary or related:
        linhas.append("")

    gaps = doc.get("gaps") or []
    linhas.extend(_bloco_lista(
        "Premissas", [f"Premissa (gap aberto): {g}" for g in gaps]))

    linhas.extend(_bloco_lista("Escopo", doc.get("scope") or []))
    linhas.extend(_bloco_lista("Suposições", doc.get("assumptions") or []))
    linhas.extend(_bloco_lista(
        "Artefatos esperados", (doc.get("artifacts") or {}).get("expected") or []))

    # Sugestões do Curador (F2) aceitas no canvas — só entram no brief quando
    # populadas (fluxo F1b as deixa vazias → zero regressão). Personas são nomes/
    # paths (strings); acervo_aplicado são {path, nature, porque}.
    linhas.extend(_bloco_lista(
        "Personas sugeridas", (doc.get("personas") or {}).get("suggested") or []))
    linhas.extend(_bloco_lista(
        "Acervo aplicado",
        [_fmt_acervo_item(it) for it in (doc.get("acervo_aplicado") or [])]))

    linhas.extend(_bloco_lista("Próximos passos", doc.get("next_moves") or []))

    return "\n".join(linhas).rstrip("\n") + "\n"


def with_task_id(brief: str, task_id: str) -> str:
    """EXCRTX MOD-015 (C0) — append the launched task_id so the conducting
    agent targets $ACERVO/_tasks/<id>/conduct.jsonl without deriving it from
    $HERMES_SESSION_ID (fragile). The conduct skills read this exact marker.
    """
    return brief.rstrip("\n") + f"\n\nTask ID (para o conduct.jsonl): {task_id}\n"
