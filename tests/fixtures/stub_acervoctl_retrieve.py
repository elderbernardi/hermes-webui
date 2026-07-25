#!/usr/bin/env python3
"""Stub determinístico de `acervoctl retrieve|posture`. Lê os args (SEM depender de
`--json` — o acervoctl real sempre imprime JSON) e imprime um JSON no formato de
acervo_retrieve.retrieve. CURADOR_ACERVOCTL_STUB_MODE=empty força abstenção
(found=false)."""
import json
import os
import sys

args = sys.argv[1:]
mode = os.environ.get("CURADOR_ACERVOCTL_STUB_MODE", "hit")
if mode == "empty":
    print(json.dumps({"query": "", "scope": "comercial", "found": False,
                      "items": [], "view": [], "citations": [], "total_tokens": 0,
                      "message": "nada encontrado"}))
else:
    print(json.dumps({
        "query": "renegociar", "route": "semantic", "scope": "comercial",
        "allow_scopes": [], "k": 5, "budget_tokens": 6000, "found": True,
        "view": [], "notes": [],
        "items": [{"role": "result", "header": "Renegociação de contratos",
                   "content": "Playbook de renegociação...", "score": 0.8,
                   "source": "catalog+fts", "stub": False, "tokens_est": 410}],
        "citations": ["Acervo: micro/comercial/knowledge/renegociacao.md"],
        "total_tokens": 410,
    }))
