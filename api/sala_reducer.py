"""EXCRTX MOD-014 (F3) — Sala reducer: núcleo PURO (sem IO/threads/relógio).

Recebe UM frame normalizado (produzido pelo observador a partir do
conduct.jsonl e das filas HITL clarify/approval) e devolve a lista de (evento, payload) a emitir.
Determinístico: mesma sequência de frames -> mesma sequência de eventos.
É a costura de teste hermética do F3 (fakes entram, lista exata sai)."""
from __future__ import annotations

PHASE_TO_COLUMN = {
    "classify": "triage", "define_done": "todo", "evidence": "ready",
    "decide": "ready", "act": "running", "verify": "running", "report": "done",
}

TRACE_OP_PATH = {"intent": "/assumptions/-", "twins": "/scope/-", "pending": "/assumptions/-"}


class SalaState:
    def __init__(self, canvas_id: str, task_id: str) -> None:
        self.cid = canvas_id
        self.task_id = task_id
        # bound counters (T5)
        self._verify_fails: dict[str, int] = {}
        self._empty = 0
        self._last_sig: str | None = None
        self._has_baseline = False

    def ingest(self, frame: dict) -> list[tuple[str, dict]]:
        kind = frame.get("kind")
        handler = getattr(self, f"_on_{kind}", None)
        if handler is None:
            return []
        return handler(frame)

    # ── D4 / D1 ───────────────────────────────────────────────────────────
    def _on_phase(self, f: dict) -> list[tuple[str, dict]]:
        phase = f.get("phase")
        column = PHASE_TO_COLUMN.get(phase, "triage")
        return [
            ("sala_phase", {"canvas_id": self.cid, "phase": phase, "seq": f.get("seq")}),
            ("sala_kanban", {"canvas_id": self.cid, "task_id": self.task_id, "column": column}),
        ]

    def _on_artifact(self, f: dict) -> list[tuple[str, dict]]:
        value = {"title": f.get("title"), "path": f.get("path"), "type": f.get("atype")}
        return [("sala_artifact", {
            "canvas_id": self.cid, "title": f.get("title"), "type": f.get("atype"),
            "path": f.get("path"), "tool": f.get("tool"),
            "ops": [{"op": "add", "path": "/artifacts/expected/-", "value": value}]})]

    def _on_next_move(self, f: dict) -> list[tuple[str, dict]]:
        text = f.get("text")
        return [("sala_next_move", {
            "canvas_id": self.cid, "text": text,
            "ops": [{"op": "add", "path": "/next_moves/-", "value": text}]})]

    def _on_trace(self, f: dict) -> list[tuple[str, dict]]:
        tk = f.get("trace_kind")
        payload = {"canvas_id": self.cid, "kind": tk, "title": f.get("title"),
                   "evidence": f.get("evidence") or {}, "verifiable": True}
        path = TRACE_OP_PATH.get(tk)
        if path:
            payload["ops"] = [{"op": "add", "path": path, "value": f.get("title")}]
        return [("sala_trace", payload)]
