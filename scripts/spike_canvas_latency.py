#!/usr/bin/env python3
"""Spike F0/T6 — mede t_first_delta e t_done do enquadramento p/ 3 frases reais."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8787"
FRASES = [
    "Preparar ofício de renegociação do contrato com o cliente Alfa até sexta",
    "Estou pensando em como estruturar o lançamento do curso de extensão",
    "Revise as pendências do microverso exocortex-ops",
]


def post(texto):
    req = urllib.request.Request(
        BASE + "/api/canvas/draft",
        data=json.dumps({"text": texto}).encode(),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))["canvas_id"]


for texto in FRASES:
    cid = post(texto)
    t0, t_delta, t_done, valido = time.time(), None, None, None
    with urllib.request.urlopen(BASE + "/api/canvas/stream?canvas_id=" + cid) as s:
        for raw in s:
            line = raw.decode().strip()
            if line == "event: canvas_delta" and t_delta is None:
                t_delta = time.time() - t0
            if line == "event: canvas_done":
                t_done = time.time() - t0
            if line.startswith("data:") and t_done is not None:
                valido = json.loads(line[5:]).get("valid")
                break
    print(f"{texto[:44]!r:48} first_delta={t_delta and round(t_delta, 1)}s "
          f"done={t_done and round(t_done, 1)}s valido={valido}")
