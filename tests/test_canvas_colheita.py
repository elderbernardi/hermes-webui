import json
from pathlib import Path
import pytest
from api import canvas_colheita as C
from api import canvas_store
# Use the REAL FakeHandler from test_canvas_routes (io.BytesIO wfile)
from tests.test_canvas_routes import FakeHandler

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


# ── Task 4 endpoint tests ──────────────────────────────────────────────────

def _fake_acervoctl_ok(monkeypatch, tmp_path):
    """Fake acervoctl: prepare-write returns receipt JSON; commit-write writes
    the content file to target and creates a log; validate-frontmatter passes."""
    def fake(args, input_file=None):
        sub = args[0] if args else ""
        if sub == "prepare-write":
            tgt = tmp_path / "receitas" / "knowledge" / "n.md"
            tgt.parent.mkdir(parents=True, exist_ok=True)
            return 0, json.dumps({
                "target_path": str(tgt),
                "log_path": str(tmp_path / "receitas" / "_meta" / "log.md"),
                "relative_output": "knowledge/n.md",
                "source_trust": "agent",
            }), ""
        if sub == "commit-write":
            # find --content-file arg, copy content to target
            try:
                cf = args[args.index("--content-file") + 1]
            except (ValueError, IndexError):
                cf = None
            tgt = tmp_path / "receitas" / "knowledge" / "n.md"
            tgt.parent.mkdir(parents=True, exist_ok=True)
            if cf:
                tgt.write_text(Path(cf).read_text(encoding="utf-8"), encoding="utf-8")
            lg = tmp_path / "receitas" / "_meta" / "log.md"
            lg.parent.mkdir(parents=True, exist_ok=True)
            lg.write_text("- CREATED knowledge/n.md\n", encoding="utf-8")
            return 0, json.dumps({"target_path": str(tgt), "log_path": str(lg)}), ""
        if sub == "validate-frontmatter":
            return 0, "{}", ""
        return 1, "", "unknown subcommand"
    monkeypatch.setattr(C, "acervoctl", fake)


def test_list_endpoint(acervo):
    C.ingest_candidate("canvas_x", {
        "nature": "knowledge", "scope": "s", "title": "t",
        "class": "volátil", "source_trust": "agent", "origin": "agent",
    })
    h = FakeHandler()
    from urllib.parse import urlparse
    assert C.handle_colheita_get(h, urlparse("/api/canvas/colheita/list?canvas_id=canvas_x"))
    assert h.status == 200
    result = json.loads(h.wfile.getvalue())
    assert result[0]["title"] == "t"


def test_adotar_creates_manual_card(acervo):
    h = FakeHandler()
    assert C.handle_colheita_post(h, "/api/canvas/colheita/adotar", {
        "canvas_id": "canvas_x",
        "source_event": {"title": "achado", "body": "x"},
        "nature": "decision",
        "scope": "cliente-alfa",
    })
    assert h.status == 200
    cards = C.list_cards("canvas_x")
    assert cards[0]["origin"] == "manual" and cards[0]["nature"] == "decision"


def test_preparar_then_checkout_commits_and_judges(acervo, tmp_path, monkeypatch):
    _fake_acervoctl_ok(monkeypatch, tmp_path)
    c = C.ingest_candidate("canvas_x", {
        "nature": "knowledge", "scope": "receitas", "title": "n",
        "body": "corpo limpo", "class": "volátil", "source_trust": "agent", "origin": "agent",
    })
    h1 = FakeHandler()
    assert C.handle_colheita_post(h1, "/api/canvas/colheita/preparar", {"canvas_id": "canvas_x"})
    assert C.list_cards("canvas_x")[0]["status"] == "prepared"

    h2 = FakeHandler()
    assert C.handle_colheita_post(h2, "/api/canvas/colheita/checkout", {
        "canvas_id": "canvas_x",
        "mode": "aprovar_tudo",
        "decisions": [{"card_id": c["id"], "action": "aprovar"}],
    })
    summary = json.loads(h2.wfile.getvalue())
    assert summary["committed"] == 1 and summary["items"][0]["judge"]["ok"] is True
    assert C.list_cards("canvas_x")[0]["status"] == "committed"
