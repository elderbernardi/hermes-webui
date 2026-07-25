"""EXCRTX MOD-013 (F2) — contrato A2A puro do Curador (sem transporte, sem I/O).

Shapes wire-idênticos ao A2A para upgrade futuro a HTTP real (nota de honestidade):
estados compostos HIFENIZADOS ("input-required"), Part.kind (alias "type" tolerado
na leitura), contextId (alias sessionId tolerado na leitura), ids opacos e estáveis.
Antes de qualquer upgrade HTTP, revalidar contra o spec.json A2A então corrente
(o teste de conformance em tests/test_curador_a2a.py é o guarda anti-drift)."""
from __future__ import annotations

import datetime
import uuid


class CuradorProtocolError(Exception):
    """Transição de estado ilegal na Task do Curador."""


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Máquina de estados como CÓDIGO (não convenção). 3 exercitados em F2
# (submitted/working/completed|failed); input-required/canceled reservados
# (compat de schema + F3), nenhum código de F2 transiciona para eles.
_VALID = {
    "submitted": {"working"},
    "working": {"completed", "failed"},
    "input-required": {"working"},   # reservado (F3)
    "completed": set(),
    "failed": set(),
    "canceled": set(),
}
_TERMINAL = {"completed", "failed", "canceled"}


def new_task(*, contextId: str, skill: str, budget_tokens: int) -> dict:
    return {
        "id": "curador_task_" + uuid.uuid4().hex,
        "contextId": contextId,
        "status": {"state": "submitted", "timestamp": now_iso(), "message": None},
        "history": [],
        "artifacts": [],
        "metadata": {
            "skill": skill,
            "budget_tokens": budget_tokens,
            "attempts": 0,
            "empty_lookups": 0,
            "hygiene": {"executor_tokens": 0, "curador_internal_tokens": 0,
                        "n_retrieves": 0},
        },
    }


def new_part(kind: str, **fields) -> dict:
    part = {"kind": kind}
    part.update(fields)
    return part


def new_message(*, role: str, skill: str, task_id: str,
                metadata: dict | None = None, text: str | None = None) -> dict:
    return {
        "role": role,
        "parts": [new_part("text", text=text if text is not None else skill)],
        "messageId": uuid.uuid4().hex,
        "taskId": task_id,
        "metadata": {"skill": skill, **(metadata or {})},
    }


def new_artifact(*, name: str, description: str, data: dict,
                 ops: list | None = None) -> dict:
    return {
        "artifactId": uuid.uuid4().hex,
        "name": name,
        "description": description,
        "parts": [new_part("data", data=data)],
        "metadata": {"ops": list(ops or [])},
    }


def part_kind(part: dict) -> str:
    """kind canônico; tolera o alias 'type' de revisões A2A antigas."""
    return part.get("kind") or part.get("type") or ""


def context_id(task: dict) -> str:
    """contextId canônico; tolera o alias 'sessionId'."""
    return task.get("contextId") or task.get("sessionId") or ""


def is_terminal(task: dict) -> bool:
    return task["status"]["state"] in _TERMINAL


def transition(task: dict, to: str, *, message: dict | None = None) -> None:
    frm = task["status"]["state"]
    if to not in _VALID.get(frm, set()):
        raise CuradorProtocolError(f"transição inválida: {frm} → {to}")
    task["status"] = {"state": to, "timestamp": now_iso(), "message": message}


class TaskStore:
    """Store em memória, keyed por id; consultável por contextId=canvas_id."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict] = {}

    def add(self, task: dict) -> dict:
        self._tasks[task["id"]] = task
        return task

    def get(self, task_id: str) -> dict | None:
        return self._tasks.get(task_id)

    def for_context(self, context_id_val: str) -> list[dict]:
        return [t for t in self._tasks.values() if t["contextId"] == context_id_val]
