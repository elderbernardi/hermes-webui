from api.sala_reducer import SalaState, PHASE_TO_COLUMN

def _st(): return SalaState("canvas_x", "task_x")

def test_phase_frame_emits_phase_and_kanban():
    out = _st().ingest({"kind": "phase", "phase": "act", "seq": 4})
    names = [n for n, _ in out]
    assert names == ["sala_phase", "sala_kanban"]
    phase_p = out[0][1]; kanban_p = out[1][1]
    assert phase_p == {"canvas_id": "canvas_x", "phase": "act", "seq": 4}
    assert kanban_p == {"canvas_id": "canvas_x", "task_id": "task_x", "column": PHASE_TO_COLUMN["act"]}

def test_artifact_frame_emits_sala_artifact_with_ops():
    out = _st().ingest({"kind": "artifact", "title": "Ofício v1", "atype": "markdown",
                        "path": "/x/oficio.md", "tool": "write_file"})
    assert len(out) == 1 and out[0][0] == "sala_artifact"
    p = out[0][1]
    assert p["ops"] == [{"op": "add", "path": "/artifacts/expected/-",
                         "value": {"title": "Ofício v1", "path": "/x/oficio.md", "type": "markdown"}}]

def test_next_move_frame():
    out = _st().ingest({"kind": "next_move", "text": "validar com o jurídico"})
    assert out == [("sala_next_move", {"canvas_id": "canvas_x", "text": "validar com o jurídico",
                    "ops": [{"op": "add", "path": "/next_moves/-", "value": "validar com o jurídico"}]})]

def test_trace_frame_intent():
    out = _st().ingest({"kind": "trace", "trace_kind": "intent", "title": "Renegociar prazo",
                        "evidence": {"event_id": "run1:3"}})
    assert out[0][0] == "sala_trace"
    p = out[0][1]
    assert p["kind"] == "intent" and p["verifiable"] is True and p["evidence"] == {"event_id": "run1:3"}
    assert p["ops"] == [{"op": "add", "path": "/assumptions/-", "value": "Renegociar prazo"}]

def test_unknown_frame_is_ignored():
    assert _st().ingest({"kind": "wat"}) == []
