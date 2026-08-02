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


# ── F4 final review locks (C1/C2/I4) — align island to backend card contract ──

def test_c1_no_artifact_id_field():
    """C1: the backend never emits `artifact_id`; the island must not read it.

    Every SSE payload is a card dict keyed by `id` (h_<sha1>), never artifact_id.
    """
    js = JS.read_text(encoding="utf-8")
    assert "artifact_id" not in js, (
        "Island still references artifact_id — backend emits `id`/`card_id`, not artifact_id."
    )


def test_c1_reads_backend_card_id():
    """C1: SSE handlers read d.id and cards are keyed/decided by the real card id."""
    js = JS.read_text(encoding="utf-8")
    assert "d.id" in js, "SSE handlers must read the backend card `id` (d.id)."
    # checkout decisions carry card_id (the real h_<sha1> id)
    assert "card_id:" in js or '"card_id"' in js, "checkout decisions must send card_id."
    # per-card buttons carry the real id via data-id and _decidirItem sends it as card_id
    assert "_decidirItem" in js and "card_id: cardId" in js, (
        "per-card decision must forward the real card id as card_id."
    )


def test_c1_prepared_updates_existing_card_no_synthetic_key():
    """C1/I4: colheita_prepared UPDATES the existing card (by real id) to
    status 'prepared' + receipt — it must NOT create a synthetic prep-/cand- key,
    and must NOT wipe a `state.prepared` list."""
    js = JS.read_text(encoding="utf-8")
    # no synthetic keys derived from cursor
    assert '"cand-"' not in js and "'cand-'" not in js and '"cand-" +' not in js, "synthetic cand- key must be gone"
    assert '"prep-"' not in js and "'prep-'" not in js and '"prep-" +' not in js, "synthetic prep- key must be gone"
    assert '"prep-" + state.cursor' not in js and '"cand-" + (' not in js, "synthetic cursor keys must be gone"
    # I4: state.prepared no longer wiped from the event (no d.items assignment)
    assert "state.prepared = d.items" not in js, (
        "I4: colheita_prepared must not overwrite state.prepared with d.items (event has no items)."
    )
    # I4: no assignment to a state.prepared list anywhere (a lone comment ref is fine)
    assert "state.prepared =" not in js, (
        "I4: derive 'has prepared cards?' from card.status, not a state.prepared list."
    )
    assert "d.items" not in js, "I4: the prepared event carries no items[] array; do not read d.items."
    # prepared-ness derived from status
    assert 'status === "prepared"' in js or "status === 'prepared'" in js, (
        "prepared cards must be derived from status === 'prepared'."
    )


def test_c2_bulk_checkout_builds_decisions_array():
    """C2: bulk 'Aprovar tudo' / 'Rejeitar' BUILD a decisions array from all
    currently-prepared cards and always POST decisions (backend iterates it)."""
    js = JS.read_text(encoding="utf-8")
    # a helper that maps prepared cards to {card_id, action}
    assert "_bulkDecisions" in js, "bulk decisions builder missing"
    assert "card_id: c.id" in js, "bulk decisions must carry the real card id as card_id"
    # bulk handlers invoke the builder with the concrete actions
    assert '_bulkDecisions("aprovar")' in js, "bulk approve must build decisions with action 'aprovar'"
    assert '_bulkDecisions("rejeitar")' in js, "bulk reject must build decisions with action 'rejeitar'"
    # both bulk handlers must send decisions (not just mode)
    assert "decisions: decisions" in js, "bulk checkout must POST the built decisions array"
    # mode strings aligned to spec/backend (aprovar_tudo / item_a_item)
    assert "aprovar_tudo" in js, "bulk approve mode string missing"


def test_c1_adotar_sends_source_event_not_artifact_id():
    """C1: manual adopt (colher) POSTs /adotar with {canvas_id, source_event, nature?, scope?}."""
    js = JS.read_text(encoding="utf-8")
    assert "source_event:" in js or '"source_event"' in js, (
        "/adotar body must carry source_event, not artifact_id."
    )
    assert "colherFromSala" in js, "colherFromSala public API missing"
