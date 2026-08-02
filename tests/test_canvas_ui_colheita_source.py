# tests/test_canvas_ui_colheita_source.py
# Source-assertion test for the Colheita UI island (F4/Task-8a).
# Keyless, no browser — reads JS/HTML/CSS files and asserts required strings.
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "static" / "canvas-colheita.js"
TAR = Path(__file__).resolve().parents[1] / "static" / "canvas-tarefas.js"
DEV = Path(__file__).resolve().parents[1] / "static" / "canvas-dev.html"
CSS = Path(__file__).resolve().parents[1] / "static" / "canvas-tarefas.css"


def test_colheita_island_wires_stream_and_controls():
    js = JS.read_text(encoding="utf-8")
    assert "/api/canvas/colheita/stream" in js
    assert "/api/canvas/colheita/preparar" in js and "/api/canvas/colheita/checkout" in js
    for ev in ("colheita_candidate", "colheita_prepared", "colheita_committed", "colheita_rejected"):
        assert ev in js
    assert "Aprovar tudo" in js and "Item a item" in js and "Rejeitar" in js  # PT-BR
    assert "cvt-colheita-zone" in js


def test_cockpit_mounts_colheita_zone_and_dev_loads_island():
    assert "cvt-colheita-zone" in TAR.read_text(encoding="utf-8")
    assert "canvas-colheita.js" in DEV.read_text(encoding="utf-8")


def test_colheita_has_adotar_endpoint():
    js = JS.read_text(encoding="utf-8")
    assert "/api/canvas/colheita/adotar" in js


def test_colheita_has_gate_badge():
    js = JS.read_text(encoding="utf-8")
    # gate badges: draft-first, forced-draft, auto
    assert "draft-first" in js and "forced-draft" in js and "auto" in js
    assert "cvt-colheita-badge" in js


def test_colheita_css_classes_present():
    css = CSS.read_text(encoding="utf-8")
    assert "cvt-colheita-zone" in css
    assert "cvt-colheita-card" in css
    assert "cvt-colheita-badge" in css
