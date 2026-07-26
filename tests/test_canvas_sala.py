from api import canvas_sala


def test_emit_appends_and_project_derives_phase_and_columns():
    canvas_sala.SALA_ROOMS.clear()
    canvas_sala._emit("cid1", "sala_phase", {"canvas_id": "cid1", "phase": "act", "seq": 1})
    canvas_sala._emit("cid1", "sala_kanban", {"canvas_id": "cid1", "task_id": "t1", "column": "running"})
    proj = canvas_sala._project(canvas_sala._room("cid1"))
    assert proj == {"phase": "act", "columns": {"t1": "running"}, "n_events": 2}


def test_emit_to_missing_room_creates_it():
    canvas_sala.SALA_ROOMS.clear()
    canvas_sala._emit("cid2", "sala_next_move", {"canvas_id": "cid2", "text": "x"})
    assert len(canvas_sala._room("cid2")["events"]) == 1
