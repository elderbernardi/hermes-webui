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


# ── T7: forward wiring /api/canvas/sala/ ─────────────────────────────────────
from urllib.parse import urlparse
from api import canvas_tarefas as ct


class _StateHandler:
    def __init__(self): self.body = None; self.status = 200
    def send_response(self, s): self.status = s
    def send_header(self, *a): pass
    def end_headers(self): pass
    class _W:
        def __init__(self, o): self.o = o
        def write(self, b): self.o.body = b
    @property
    def wfile(self): return _StateHandler._W(self)


def test_forward_routes_sala_state():
    canvas_sala_cleared = __import__("api.canvas_sala", fromlist=["SALA_ROOMS"])
    canvas_sala_cleared.SALA_ROOMS.clear()
    h = _StateHandler()
    handled = ct.handle_canvas_get(h, urlparse("/api/canvas/sala/state?canvas_id=cidX"))
    assert handled is True and h.status == 200


def test_forward_unknown_sala_path_falls_through():
    h = _StateHandler()
    handled = ct.handle_canvas_get(h, urlparse("/api/canvas/sala/bogus"))
    assert handled is False   # handle_sala_get returns False -> caller returns False
