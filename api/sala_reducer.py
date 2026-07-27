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

    # ── D3 bounds (mirror F2 Curador _bump_empty/_sig shape) ───────────────
    def _on_verify(self, f: dict) -> list[tuple[str, dict]]:
        subj = f.get("subject") or ""
        if f.get("ok"):
            self._verify_fails[subj] = 0            # success resets the streak
            return []
        n = self._verify_fails.get(subj, 0) + 1
        self._verify_fails[subj] = n
        if n < 3:
            return []
        hypothesis = f.get("hypothesis") or (
            f"'{subj}' falhou {n}x seguidas — provável causa a investigar")
        return [("sala_interrupt", {
            "canvas_id": self.cid, "klass": "verify_fail",
            "clarify_id": f.get("clarify_id"), "session_id": f.get("session_id"),
            "tried": f.get("tried"), "output": f.get("output"), "hypothesis": hypothesis,
            "ops": [{"op": "add", "path": "/gaps/-", "value": hypothesis}]})]

    def _on_search(self, f: dict) -> list[tuple[str, dict]]:
        sig = f.get("query_sig") or ""
        empty = bool(f.get("empty")) or (sig == self._last_sig) or (not self._has_baseline)
        self._last_sig = sig
        self._has_baseline = True
        if not empty:
            return []
        self._empty += 1
        if self._empty < 2:
            return []
        q = f.get("query") or sig or "busca"
        reason = f"Sala não encontrou informação nova para '{q}' após 2 buscas"
        return [("sala_gap", {"canvas_id": self.cid, "source": "empty_search",
                              "question": reason,
                              "ops": [{"op": "add", "path": "/gaps/-", "value": reason}]})]

    def _on_surprise(self, f: dict) -> list[tuple[str, dict]]:
        return [("sala_finding", {
            "canvas_id": self.cid, "subject": f.get("subject"),
            "code": f.get("code"), "check": f.get("check"), "spec": f.get("spec"),
            "authority": ["executivo", "spec", "tests", "codigo"],
            "resolution": f.get("resolution")})]

    # ── D1(ii) clarify -> gap (re-skin an ALREADY-blocked runtime clarify) ──
    def _on_clarify(self, f: dict) -> list[tuple[str, dict]]:
        if f.get("bound_interrupt"):
            hyp = f.get("hypothesis") or f.get("question") or "bound atingido"
            return [("sala_interrupt", {
                "canvas_id": self.cid, "klass": "verify_fail",
                "clarify_id": f.get("clarify_id"), "session_id": f.get("session_id"),
                "tried": f.get("tried"), "output": f.get("output"), "hypothesis": hyp,
                "ops": [{"op": "add", "path": "/gaps/-", "value": hyp}]})]
        q = f.get("question") or ""
        return [("sala_gap", {
            "canvas_id": self.cid, "source": "clarify",
            "clarify_id": f.get("clarify_id"), "session_id": f.get("session_id"),
            "question": q, "choices_offered": f.get("choices_offered") or [],
            "ops": [{"op": "add", "path": "/gaps/-", "value": q}]})]

    # ── D2(i) Draft-First: conduct {"t":"draft"} OR a runtime approval gate ──
    def _on_approval(self, f: dict) -> list[tuple[str, dict]]:
        return [("sala_draft", {
            "canvas_id": self.cid, "session_id": f.get("session_id"),
            "action": f.get("action"), "draft_text": f.get("draft_text"),
            "approval_id": f.get("approval_id"), "requires_auth": True})]
