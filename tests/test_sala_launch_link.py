import yaml
from pathlib import Path
from api import canvas_sala


def test_register_and_resolve(monkeypatch, tmp_path):
    monkeypatch.setenv("ACERVO", str(tmp_path))
    (tmp_path / "_tasks" / "canvas_20260725_120000_x_00100").mkdir(parents=True)
    canvas_sala._LAUNCHED.clear()
    canvas_sala.register_launch("sess-1", "canvas_20260725_120000_x_00100", "task_abc")
    assert canvas_sala.resolve("sess-1") == {"canvas_id": "canvas_20260725_120000_x_00100", "task_id": "task_abc"}
    assert canvas_sala.resolve("nope") is None
    # durable sidecar written under the canvas dir
    lp = tmp_path / "_tasks" / "canvas_20260725_120000_x_00100" / "launch.yaml"
    assert yaml.safe_load(lp.read_text())["session_id"] == "sess-1"


def test_rebuild_after_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("ACERVO", str(tmp_path))
    d = tmp_path / "_tasks" / "canvas_20260725_120000_y_00200"
    d.mkdir(parents=True)
    (d / "launch.yaml").write_text(yaml.safe_dump(
        {"session_id": "sess-2", "task_id": "task_y", "launched_at": "t"}))
    canvas_sala._LAUNCHED.clear()            # simulate server restart (memory lost)
    canvas_sala._rebuild_launched()
    assert canvas_sala.resolve("sess-2") == {"canvas_id": "canvas_20260725_120000_y_00200", "task_id": "task_y"}


def test_handle_launch_registers_link(monkeypatch, tmp_path):
    monkeypatch.setenv("ACERVO", str(tmp_path))
    from api import canvas_tarefas as ct, canvas_store, canvas_sala
    cid, _ = canvas_store.create_draft("preparar ofício")
    # minimal valid doc so compile_brief passes (vetor != ambiguo)
    doc = canvas_store.load_canvas(cid); doc["vetor"] = "execucao"; doc["focus"] = "preparar ofício de renegociação"
    canvas_store.save_canvas(cid, doc)
    monkeypatch.setattr(ct, "_register_task", lambda *a, **k: "task_L")
    monkeypatch.setattr(ct, "_new_session", lambda: type("S", (), {"session_id": "sess-L"})())
    monkeypatch.setattr(ct, "_stage_file", lambda sid, p: {"name": p.name, "path": str(p), "size": 1, "mime": "text/markdown", "is_image": False})
    canvas_sala._LAUNCHED.clear()
    captured = {}
    class H:  # fake handler capturing the JSON body
        def send_response(self, *a): pass
        def send_header(self, *a): pass
        def end_headers(self): pass
        class wfile:
            @staticmethod
            def write(b): captured["body"] = b
    ct._handle_launch(H(), {"canvas_id": cid})
    assert canvas_sala.resolve("sess-L") == {"canvas_id": cid, "task_id": "task_L"}
