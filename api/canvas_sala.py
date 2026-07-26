"""EXCRTX MOD-014 (F3) — Sala viva: observe-and-translate layer.

Camada in-process que reflete a sessão lançada no canvas. NUNCA cunha
primitiva bloqueante (só observa clarify/approval multi-subscriber);
NUNCA escreve no runtime da sessão. Gate SALA_ENABLE (default off).
Este arquivo cresce por tarefa: T3=linkagem, T6=sala+stream, T8=observador."""
from __future__ import annotations

import threading
import time
import yaml

from api import canvas_store

_LAUNCHED: dict[str, dict] = {}          # session_id -> {"canvas_id","task_id"}
_LAUNCHED_LOCK = threading.Lock()


def register_launch(session_id: str, canvas_id: str, task_id: str) -> None:
    """Grava a linkagem em memória E num sidecar durável canvas-keyed
    (_tasks/<canvas_id>/launch.yaml), para sobreviver a restart do servidor."""
    with _LAUNCHED_LOCK:
        _LAUNCHED[session_id] = {"canvas_id": canvas_id, "task_id": task_id}
    d = canvas_store.tasks_dir() / canvas_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "launch.yaml").write_text(
        yaml.safe_dump({"session_id": session_id, "task_id": task_id,
                        "launched_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                       allow_unicode=True, sort_keys=False),
        encoding="utf-8")


def resolve(session_id: str) -> dict | None:
    with _LAUNCHED_LOCK:
        v = _LAUNCHED.get(session_id)
        return dict(v) if v else None


def _rebuild_launched() -> None:
    """Cold-start: reconstrói _LAUNCHED varrendo os sidecars em disco
    (mesmo padrão de _list_canvases)."""
    for p in canvas_store.tasks_dir().glob("canvas_*/launch.yaml"):
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        sid = doc.get("session_id")
        if sid:
            with _LAUNCHED_LOCK:
                _LAUNCHED[sid] = {"canvas_id": p.parent.name, "task_id": doc.get("task_id")}
