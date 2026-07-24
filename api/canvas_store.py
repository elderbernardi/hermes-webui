"""EXCRTX MOD-011 (spike F0) — Canvas de Tarefas: store server-side em $ACERVO/_tasks/.

Fonte da verdade é o YAML em disco (harness v0.4). A UI recebe snapshot +
deltas (subset RFC 6902). Sem dependências novas (PyYAML já é requisito).
"""
from __future__ import annotations

import copy
import os
import re
import threading
import time
from pathlib import Path

import yaml

_LOCK = threading.Lock()
_TEMPLATE_REL = "global/templates/harness-v0.4/canvas.yaml"

_MINIMAL = {
    "canvas_id": "", "focus": "", "original_input_summary": "",
    "vector": "evolucao", "intent_type": "explorar",
    "user_intention": {"explicit": "", "inferred": "", "confidence": "medium"},
    "microversos": {"primary": None, "related": []},
    "gaps": [], "dependencies": [], "risks": [], "next_moves": [],
}


def acervo_root() -> Path:
    for cand in (os.environ.get("ACERVO"),
                 os.path.expanduser("~/exocortex/acervo"),
                 os.path.expanduser("~/.hermes/acervo")):
        if cand and Path(cand).is_dir():
            return Path(cand)
    raise RuntimeError(
        "ACERVO não encontrado ($ACERVO, ~/exocortex/acervo, ~/.hermes/acervo)")


def tasks_dir() -> Path:
    d = acervo_root() / "_tasks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_canvas_id(slug: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")[:40] or "tarefa"
    return f"canvas_{time.strftime('%Y%m%d_%H%M%S')}_{slug}"


def _canvas_path(canvas_id: str) -> Path:
    if not re.fullmatch(r"canvas_[0-9]{8}_[0-9]{6}_[a-z0-9-]+", canvas_id):
        raise ValueError(f"canvas_id inválido: {canvas_id!r}")
    d = tasks_dir() / canvas_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "canvas.yaml"


def create_draft(focus_text: str) -> tuple[str, dict]:
    tpl = acervo_root() / _TEMPLATE_REL
    if tpl.is_file():
        canvas = yaml.safe_load(tpl.read_text(encoding="utf-8"))
    else:
        canvas = copy.deepcopy(_MINIMAL)
    cid = new_canvas_id(focus_text)
    canvas["canvas_id"] = cid
    canvas["original_input_summary"] = focus_text.strip()
    save_canvas(cid, canvas)
    return cid, canvas


def save_canvas(canvas_id: str, canvas: dict) -> None:
    p = _canvas_path(canvas_id)
    with _LOCK:
        p.write_text(yaml.safe_dump(canvas, allow_unicode=True, sort_keys=False),
                     encoding="utf-8")


def load_canvas(canvas_id: str) -> dict:
    return yaml.safe_load(_canvas_path(canvas_id).read_text(encoding="utf-8"))


# --- subset RFC 6902: add / replace / remove --------------------------------

def _resolve(doc, pointer: str):
    if not pointer.startswith("/"):
        raise ValueError(f"pointer inválido: {pointer!r}")
    parts = [p.replace("~1", "/").replace("~0", "~")
             for p in pointer.split("/")[1:]]
    parent = doc
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    return parent, parts[-1]


def apply_patch(canvas: dict, ops: list[dict]) -> dict:
    for op in ops:
        parent, key = _resolve(canvas, op["path"])
        kind = op["op"]
        if isinstance(parent, list):
            idx = len(parent) if key == "-" else int(key)
            if kind == "add":
                parent.insert(idx, op["value"])
            elif kind == "replace":
                parent[idx] = op["value"]
            elif kind == "remove":
                parent.pop(idx)
            else:
                raise ValueError(f"op não suportada: {kind}")
        else:
            if kind in ("add", "replace"):
                parent[key] = op["value"]
            elif kind == "remove":
                parent.pop(key, None)
            else:
                raise ValueError(f"op não suportada: {kind}")
    return canvas


# --- mapeador núcleo (schema v0.4, chave `vetor`) → documento (template, `vector`)

_CORE_TO_DOC = {
    "focus": "/focus",
    "vetor": "/vector",
    "intent_type": "/intent_type",
    "microverso_primary": "/microversos/primary",
}


def core_to_patch(core: dict) -> list[dict]:
    ops: list[dict] = []
    for key, path in _CORE_TO_DOC.items():
        if core.get(key) is not None:
            ops.append({"op": "replace", "path": path, "value": core[key]})
    for gap in core.get("gaps") or []:
        ops.append({"op": "add", "path": "/gaps/-", "value": gap})
    return ops
