import json
from pathlib import Path
import pytest
from api import canvas_colheita as C
from api import canvas_store

@pytest.fixture
def acervo(tmp_path, monkeypatch):
    (tmp_path / "_tasks" / "canvas_x").mkdir(parents=True)
    monkeypatch.setattr(canvas_store, "tasks_dir", lambda: tmp_path / "_tasks")
    return tmp_path

def test_compute_gate():
    assert C.compute_gate("knowledge", "perene", "agent") == "draft-first"
    assert C.compute_gate("persona", "volátil", "agent") == "draft-first"
    assert C.compute_gate("knowledge", "volátil", "untrusted") == "forced-draft"
    assert C.compute_gate("knowledge", "volátil", "agent") == "auto"

def test_ingest_and_list(acervo):
    card = C.ingest_candidate("canvas_x", {
        "nature": "knowledge", "scope": "cliente-alfa", "title": "Histórico",
        "porque": "reuso", "ref": "art/1.md", "class": "perene", "source_trust": "agent",
        "origin": "agent"})
    assert card["gate"] == "draft-first" and card["status"] == "pending" and card["id"]
    cards = C.list_cards("canvas_x")
    assert len(cards) == 1 and cards[0]["title"] == "Histórico"

def test_set_status_last_wins(acervo):
    c = C.ingest_candidate("canvas_x", {"nature": "knowledge", "scope": "s", "title": "t",
                                        "class": "volátil", "source_trust": "agent", "origin": "manual"})
    C.set_status("canvas_x", c["id"], "committed", receipt={"target_path": "x"})
    cards = C.list_cards("canvas_x")
    assert len(cards) == 1 and cards[0]["status"] == "committed"
    assert cards[0]["receipt"] == {"target_path": "x"}

def test_judge_committed_pass(tmp_path):
    f = tmp_path / "k.md"
    f.write_text("---\ntype: knowledge\ntitle: t\n---\ncorpo sem instancia\n", encoding="utf-8")
    log = tmp_path / "log.md"
    log.write_text("- CREATED k.md\n", encoding="utf-8")
    # stub the frontmatter validator to pass (real one lives in exocortex; see Task 4 seam)
    res = C.judge_committed(str(f), str(log), _validate=lambda p: True)
    assert res["ok"] and res["checks"]["clean_portable"] and res["checks"]["logged"]

def test_judge_committed_flags_instance_leak(tmp_path):
    f = tmp_path / "k.md"
    f.write_text("---\ntype: knowledge\n---\nvazou canvas_20260801_abc\n", encoding="utf-8")
    log = tmp_path / "log.md"; log.write_text("- CREATED k.md\n", encoding="utf-8")
    res = C.judge_committed(str(f), str(log), _validate=lambda p: True)
    assert res["ok"] is False and res["checks"]["clean_portable"] is False
