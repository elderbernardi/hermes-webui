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


def test_ilha_curador_e_helper_sem_hack_de_zona_irma():
    src = _static("canvas-curador.js")   # _static() já prepende static/ (nome NU)
    assert "/api/canvas/curador/stream" in src
    assert "/api/canvas/curador/delegar" in src
    assert "EventSource" in src
    assert "window.CVT.acceptOps" in src
    assert "window.CanvasCurador" in src
    # C1: virou helper — sem zona-irmã, sem observer, sem o rótulo antigo
    assert "cvt-curador-zone" not in src
    assert "MutationObserver" not in src
    assert "Pedir sugestões" not in src
    # preenche containers reservados + expõe fill + botão "Atualizar"
    assert "getElementById" in src
    assert "fill" in src
    assert 'id="cvt-cur-pedir"' in src and "Atualizar" in src
    # Skills = nature SINGULAR
    assert '=== "skill"' in src


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
