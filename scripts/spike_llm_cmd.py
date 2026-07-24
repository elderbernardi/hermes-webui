#!/usr/bin/env python3
"""Seam de LLM do spike F0 (CANVAS_LLM_CMD): lê prompt no stdin, imprime resposta.
Endpoint OpenAI-compatível; usa DEEPSEEK_API_KEY ou EXOCORTEX_DEFAULT_API_KEY."""
import json
import os
import sys
import urllib.request

prompt = sys.stdin.read()
key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("EXOCORTEX_DEFAULT_API_KEY") or ""
base = os.environ.get("CANVAS_LLM_BASE", "https://api.deepseek.com/v1")
model = os.environ.get("CANVAS_LLM_MODEL", "deepseek-chat")
req = urllib.request.Request(
    base.rstrip("/") + "/chat/completions",
    data=json.dumps({"model": model, "temperature": 0,
                     "messages": [{"role": "user", "content": prompt}]}).encode(),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
with urllib.request.urlopen(req, timeout=110) as resp:
    print(json.load(resp)["choices"][0]["message"]["content"])
