"""EXCRTX MOD-013 (F2) — wrapper SÓ-LEITURA do acervo para o Curador.

Roda `acervoctl retrieve/posture --json` como subprocess (padrão _acervoctl de
api/acervo_studio_agent.py). Read-only ESTRUTURAL: nenhum verbo de escrita é
importado ou invocado. Abstenção (found=false) não é erro."""
from __future__ import annotations

import json
import os
import subprocess
import sys

_TIMEOUT = 60


def _resolve_acervoctl_dir() -> str | None:
    """Localiza um dir de control-plane runnable (tem acervoctl.py). O cache do
    installer é a cópia canônica runnable (não provisionada em ~/.hermes)."""
    candidates = []
    env_dir = os.environ.get("EXOCORTEX_SCRIPTS_DIR")
    if env_dir:
        candidates.append(env_dir)
    home = os.path.expanduser("~")
    candidates += [
        os.path.join(home, ".exocortex-installer", "scripts"),
        os.path.join(home, "exocortex", "scripts"),
    ]
    for d in candidates:
        if d and os.path.isfile(os.path.join(d, "acervoctl.py")):
            return d
    return None


def _acervoctl(scripts_dir: str, args: list[str]) -> subprocess.CompletedProcess:
    """Roda um subcomando acervoctl (list form, sem shell). Seam de teste:
    CURADOR_ACERVOCTL_CMD substitui o binário (stub determinístico)."""
    override = os.environ.get("CURADOR_ACERVOCTL_CMD")
    if override:
        return subprocess.run(override.split() + args, capture_output=True,
                              text=True, timeout=_TIMEOUT)
    env = dict(os.environ)
    env["PYTHONPATH"] = scripts_dir + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable or "python3", os.path.join(scripts_dir, "acervoctl.py")] + args,
        cwd=scripts_dir, env=env, capture_output=True, text=True, timeout=_TIMEOUT)


def _run(subcmd: str, extra: list[str]) -> dict:
    # NB: NÃO anexar `--json`. Verificado no acervoctl real: `posture` NÃO tem o
    # flag `--json` (o parser rejeita → exit 2) e `retrieve` só o aceita "por
    # compatibilidade"; `main()` SEMPRE faz print_json(payload). Anexar `--json`
    # quebraria `posture` (→ sugerir_itens sem candidatos em prod).
    scripts_dir = os.environ.get("CURADOR_ACERVOCTL_CMD") and "." or _resolve_acervoctl_dir()
    if not os.environ.get("CURADOR_ACERVOCTL_CMD") and scripts_dir is None:
        return {"found": False, "items": [], "citations": [], "total_tokens": 0,
                "message": "acervo control plane não encontrado"}
    proc = _acervoctl(scripts_dir or ".", [subcmd] + extra)
    if proc.returncode != 0:
        return {"found": False, "items": [], "citations": [], "total_tokens": 0,
                "message": f"acervoctl {subcmd} exit {proc.returncode}: "
                           f"{(proc.stderr or '')[-200:]}"}
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return {"found": False, "items": [], "citations": [], "total_tokens": 0,
                "message": "acervoctl não retornou JSON válido"}


def curador_retrieve(query: str, scope: str, *, budget: int = 6000, k: int = 5,
                     allow_scopes=()) -> dict:
    extra = ["--query", query, "--scope", scope, "--budget", str(budget), "--k", str(k)]
    for s in allow_scopes:
        extra += ["--allow-scope", s]
    return _run("retrieve", extra)


def curador_posture(query: str, scope: str, *, mode: str = "decision",
                    budget: int = 12000, k: int = 8, allow_scopes=()) -> dict:
    extra = ["--mode", mode, "--query", query, "--scope", scope,
             "--budget", str(budget), "--k", str(k)]
    for s in allow_scopes:
        extra += ["--allow-scope", s]
    return _run("posture", extra)
