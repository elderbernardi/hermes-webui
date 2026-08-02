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


# ── Regression locks for review fixes (F4 I1/I2/I3) ──────────────────────────

def test_i1_no_receipt_get_endpoint():
    """I1: endpoint /api/canvas/colheita/receipt (GET) does not exist — must never be fetched."""
    js = JS.read_text(encoding="utf-8")
    assert "colheita/receipt" not in js, (
        "Broken /receipt fallback was re-introduced; remove the fetch entirely."
    )


def test_i2_item_a_item_is_functional():
    """I2: item-a-item mode renders per-card Aprovar/Rejeitar and calls checkout with decisions."""
    js = JS.read_text(encoding="utf-8")
    # per-card buttons present in markup
    assert "cvt-colheita-aprovar-item" in js, "Per-card Aprovar button class missing"
    assert "cvt-colheita-rejeitar-item" in js, "Per-card Rejeitar button class missing"
    # single-decision checkout call wired up (unquoted JS object key)
    assert "decisions:" in js or '"decisions"' in js or "'decisions'" in js, "decisions array missing from checkout call"
    assert "item_a_item" in js, "mode:item_a_item missing from checkout payload"
    # PT-BR labels on per-card buttons
    assert ">Aprovar<" in js, "PT-BR 'Aprovar' label missing on per-card button"
    assert ">Rejeitar<" in js, "PT-BR 'Rejeitar' label missing on per-card button"


def test_i3_oncockpitopen_is_idempotent():
    """I3: onCockpitOpen returns early when cid matches and stream exists."""
    js = JS.read_text(encoding="utf-8")
    # guard pattern: cid unchanged AND stream active → early return
    assert "state.cid === cid && state.es" in js, (
        "Idempotency guard missing from onCockpitOpen"
    )
