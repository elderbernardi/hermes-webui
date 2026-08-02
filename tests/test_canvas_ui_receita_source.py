# tests/test_canvas_ui_receita_source.py
# Source-assertion test for the Receita gallery UI (F4/Task-8b).
# Keyless, no browser — reads JS/CSS files and asserts required strings.
from pathlib import Path

TAR = Path(__file__).resolve().parents[1] / "static" / "canvas-tarefas.js"
CSS = Path(__file__).resolve().parents[1] / "static" / "canvas-tarefas.css"


def test_hangar_gallery_and_canonize_wired():
    js = TAR.read_text(encoding="utf-8")
    assert "/api/canvas/receita/list" in js
    assert "/api/canvas/receita/iniciar" in js
    assert "/api/canvas/receita/canonizar" in js
    assert "Receitas" in js and "Canonizar sala como receita" in js  # PT-BR


def test_receita_functions_present():
    js = TAR.read_text(encoding="utf-8")
    assert "iniciarDeReceita" in js
    assert "canonizarReceita" in js


def test_receita_card_html():
    js = TAR.read_text(encoding="utf-8")
    assert "cvt-receita-card" in js
    assert "focus_template" in js or "recipe_id" in js  # recipe fields rendered


def test_canonizar_button_in_cockpit():
    js = TAR.read_text(encoding="utf-8")
    assert "Canonizar sala como receita" in js
    # wired in cockpit click handler or renderCockpit
    assert "canonizarReceita" in js


def test_receita_css_classes_present():
    css = CSS.read_text(encoding="utf-8")
    assert "cvt-receita" in css
