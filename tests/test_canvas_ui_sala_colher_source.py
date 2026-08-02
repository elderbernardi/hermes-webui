# tests/test_canvas_ui_sala_colher_source.py
# F4 final review (I3): source-lock that the Sala island wires a "Colher" action
# on colhível cards (artifact/finding/next_move) that dispatches to the Colheita
# bandeja via window.CanvasColheita.colherFromSala (→ POST /api/canvas/colheita/adotar).
# Keyless, no browser — reads the JS island and asserts required strings.
from pathlib import Path

SALA = Path(__file__).resolve().parents[1] / "static" / "canvas-sala.js"


def _strip_banner(src):
    s = src.lstrip()
    if s.startswith("/*"):
        return s[s.index("*/") + 2:]
    return src


def test_sala_wires_colher_action():
    js = SALA.read_text(encoding="utf-8")
    # renders a Colher button (PT-BR) and delegates its click
    assert ">Colher<" in js, "Sala must render a PT-BR 'Colher' button"
    assert "cvt-sala-colher" in js, "Sala colher button class missing"
    # dispatches into the Colheita island (or POSTs /adotar directly)
    assert "colherFromSala" in js or "/api/canvas/colheita/adotar" in js, (
        "Sala colher must call CanvasColheita.colherFromSala or POST /adotar"
    )
    assert "window.CanvasColheita" in js, "Sala must reference the Colheita island surface"


def test_sala_colher_only_on_harvestable_kinds():
    js = SALA.read_text(encoding="utf-8")
    # colher gated to knowledge-bearing card kinds
    for kind in ("artifact", "finding", "next_move"):
        assert kind in js, f"colher gating must reference kind '{kind}'"


def test_sala_colher_passes_source_event_data():
    """The colher handler must forward the sala card's identifying data (raw)
    as the source_event — not a bare artifact_id (which the backend does not accept)."""
    js = SALA.read_text(encoding="utf-8")
    assert "artifact_id" not in js, (
        "Sala colher must not pass artifact_id; /adotar expects source_event."
    )
    # raw card data captured for artifact/next_move/finding events
    assert "raw:" in js, "sala cards must carry raw {title/path/text/subject} for colher"


def test_sala_colher_does_not_touch_hot_zone():
    body = _strip_banner(SALA.read_text(encoding="utf-8"))
    for hot in ("ui.js", "messages.js", "sessions.js", "panels.js", "boot.js",
                "style.css", "index.html"):
        assert hot not in body
