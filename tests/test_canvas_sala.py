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


# ── T8: observer daemon ──────────────────────────────────────────────────────
import queue as _queue


def _ctx(sid, cq, aq):
    return {"sid": sid, "clarify_q": cq, "approval_q": aq, "conduct_off": 0}


def test_poll_once_translates_conduct_frames(monkeypatch):
    canvas_sala.SALA_ROOMS.clear()
    from api.sala_reducer import SalaState
    st = SalaState("cidP", "taskP")
    conduct = [{"t": "phase", "phase": "act", "seq": 1},
               {"t": "artifact", "title": "Ofício", "atype": "markdown", "path": "/o.md", "tool": "write_file"}]
    canvas_sala._INJECTED["conduct"] = lambda task_id, off: (conduct[off:], len(conduct))
    ctx = _ctx("sidP", _queue.Queue(), _queue.Queue())
    n = canvas_sala._poll_once(st, ctx)
    names = [nm for nm, _ in canvas_sala._room("cidP")["events"]]
    assert names == ["sala_phase", "sala_kanban", "sala_artifact"] and n == 3
    canvas_sala._INJECTED.clear()


def test_poll_once_drains_clarify_queue(monkeypatch):
    canvas_sala.SALA_ROOMS.clear()
    from api.sala_reducer import SalaState
    st = SalaState("cidC", "taskC")
    canvas_sala._INJECTED["conduct"] = lambda t, o: ([], o)
    cq = _queue.Queue()
    cq.put({"pending": {"clarify_id": "cl1", "question": "qual prazo?", "choices_offered": ["30d", "60d"]}, "pending_count": 1})
    canvas_sala._poll_once(st, _ctx("sidC", cq, _queue.Queue()))
    # _on_clarify lands in T9; here just assert the frame reached the reducer without error
    canvas_sala._INJECTED.clear()


def test_conduct_off_advances_no_reprocess(monkeypatch):
    canvas_sala.SALA_ROOMS.clear()
    from api.sala_reducer import SalaState
    st = SalaState("cidO", "taskO")
    lines = [{"t": "next_move", "text": "a"}]
    canvas_sala._INJECTED["conduct"] = lambda t, off: (lines[off:], len(lines))
    ctx = _ctx("sidO", _queue.Queue(), _queue.Queue())
    assert canvas_sala._poll_once(st, ctx) == 1
    assert canvas_sala._poll_once(st, ctx) == 0   # offset advanced -> no reprocessing
    canvas_sala._INJECTED.clear()


def test_start_observer_noop_without_flag(monkeypatch):
    monkeypatch.delenv("SALA_ENABLE", raising=False)
    canvas_sala._OBSERVERS.clear()
    canvas_sala.start_observer("sidZ")
    assert "sidZ" not in canvas_sala._OBSERVERS


def test_observer_never_mints_a_blocking_primitive(monkeypatch):
    calls = []
    from api import clarify as _cl
    monkeypatch.setattr(_cl, "register_gateway_notify", lambda *a, **k: calls.append("notify"))
    monkeypatch.setattr(_cl, "submit_pending", lambda *a, **k: calls.append("submit"))
    from api.sala_reducer import SalaState
    canvas_sala._INJECTED["conduct"] = lambda t, o: ([], o)
    import queue as q
    canvas_sala._poll_once(SalaState("c", "t"), {"sid": "s", "clarify_q": q.Queue(),
                            "approval_q": q.Queue(), "conduct_off": 0})
    assert calls == []   # F3 mints nothing
    canvas_sala._INJECTED.clear()


# ── fix-wave #1: restart recovery is REACHABLE (lazy rebuild on a miss) ───────
def test_link_for_canvas_rebuilds_after_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("ACERVO", str(tmp_path))
    import yaml as _yaml
    d = tmp_path / "_tasks" / "canvas_20260727_120000_z_00300"
    d.mkdir(parents=True)
    (d / "launch.yaml").write_text(_yaml.safe_dump(
        {"session_id": "sess-R", "task_id": "task_R", "launched_at": "t"}))
    canvas_sala._LAUNCHED.clear()
    canvas_sala._PRIMED = False                      # simulate a fresh process (memory lost)
    # the sidecar exists on disk but _LAUNCHED is empty -> _link_for_canvas must rebuild
    assert canvas_sala._link_for_canvas("canvas_20260727_120000_z_00300") == "sess-R"


# ── fix-wave #2: observer winds down when no stream is watching ───────────────
def test_observer_stops_when_no_subscribers(monkeypatch, tmp_path):
    import time as _t
    monkeypatch.setenv("ACERVO", str(tmp_path))
    monkeypatch.setenv("SALA_ENABLE", "1")
    monkeypatch.setenv("SALA_OBS_IDLE_STOP", "2")
    monkeypatch.setenv("SALA_POLL_INTERVAL", "0.01")
    (tmp_path / "_tasks" / "canvas_20260727_120000_s_00400").mkdir(parents=True)
    canvas_sala._LAUNCHED.clear(); canvas_sala._OBSERVERS.clear(); canvas_sala.SALA_ROOMS.clear()
    canvas_sala.register_launch("sess-S", "canvas_20260727_120000_s_00400", "task_S")
    canvas_sala.start_observer("sess-S")
    for _ in range(300):                             # no stream opened -> subs stays 0 -> stops
        if "sess-S" not in canvas_sala._OBSERVERS:
            break
        _t.sleep(0.01)
    assert "sess-S" not in canvas_sala._OBSERVERS    # thread wound down + cleanup ran (no leak)
