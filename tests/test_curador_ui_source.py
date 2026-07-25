# tests/test_curador_ui_source.py  (fork)
import pathlib


def _static(name):
    return (pathlib.Path(__file__).resolve().parent.parent / "static" / name).read_text(
        encoding="utf-8")


def test_canvas_tarefas_expoe_surface_do_curador():
    src = _static("canvas-tarefas.js")
    assert "acceptOps: submitOps" in src
    assert "getCanvas:" in src and "currentCid:" in src
    assert "window.CanvasCurador" in src and "onCockpitOpen" in src


def test_ilha_curador_tem_superficie_minima():
    src = _static("canvas-curador.js")
    assert "/api/canvas/curador/stream" in src
    assert "/api/canvas/curador/delegar" in src
    assert "EventSource" in src
    assert "window.CVT.acceptOps" in src
    assert "cvt-curador-zone" in src             # container próprio, sobrevive a renderCockpit
    assert "Pedir sugestões" in src              # gatilho manual canônico (PT-BR)
    assert "MutationObserver" in src             # esconde a zona fora do Cockpit
    assert "window.CanvasCurador" in src


def test_canvas_dev_html_carrega_a_ilha():
    # achado #3: canvas-dev.html é o ÚNICO carregador do Cockpit
    html = _static("canvas-dev.html")
    assert "/static/canvas-curador.js" in html
    assert "/static/canvas-tarefas.css" in html   # já existia (link da ilha reusa)


def test_css_tem_classes_da_ilha():
    css = _static("canvas-tarefas.css")
    for cls in (".cvt-curador-zone", ".cvt-sug"):
        assert cls in css


def test_ilha_nao_toca_zonas_quentes():
    src = _static("canvas-curador.js")
    for hot in ("ui.js", "messages.js", "sessions.js", "panels.js", "boot.js",
                "style.css", "index.html"):
        assert hot not in src
