# tests/test_sala_island.py  (fork)
# F3 T12 — source-lint of the Sala viva island, mirroring test_curador_ui_source.py.
# Live-server-free: the Playwright/screenshot leg of Step 5 defers to the T16 gate;
# this guarantees the island surface + hot-zone isolation without a running server.
import pathlib


def _static(name):
    return (pathlib.Path(__file__).resolve().parent.parent / "static" / name).read_text(
        encoding="utf-8")


def _strip_banner(src):
    # Drop the leading /* … */ header. That banner names the hot files by string
    # precisely to state the island does NOT touch them; the hot-zone assertion
    # below must inspect the executable body, not the descriptive docstring.
    s = src.lstrip()
    if s.startswith("/*"):
        return s[s.index("*/") + 2:]
    return src


def test_canvas_tarefas_faz_handoff_da_sala():
    src = _static("canvas-tarefas.js")
    # one guarded line beside the existing Curador handoff (M3)
    assert "window.CanvasSala" in src and "onCockpitOpen" in src
    assert "window.CanvasSala.onCockpitOpen" in src


def test_ilha_sala_tem_superficie_minima():
    src = _static("canvas-sala.js")
    assert "/api/canvas/sala/stream" in src        # T6/T8 SSE consumed by the island
    assert "EventSource" in src                     # own stream, not the chat transport
    assert "cvt-sala-zone" in src                   # container próprio, sobrevive a renderCockpit
    assert "MutationObserver" in src                # espelha o hidden do Cockpit (fora dele, some)
    assert "cvt-sala-chip" in src                   # fase = chip discreto, nunca bolha de chat
    assert "window.CVT.acceptOps" in src            # Aceitar roteia ops pela fonte única do canvas
    assert "/api/clarify/respond" in src            # HITL: responder a gap/interrupt
    assert "/api/approval/respond" in src           # HITL: gate de permissão de tool
    assert "/authorization/-" in src                # Draft-First grava as palavras exatas
    assert "window.CanvasSala" in src               # superfície pública da ilha


def test_canvas_dev_html_carrega_a_ilha_sala():
    # canvas-dev.html é o ÚNICO carregador do Cockpit (achado #3)
    html = _static("canvas-dev.html")
    assert "/static/canvas-sala.js" in html
    assert "/static/canvas-tarefas.css" in html


def test_css_tem_classes_da_sala():
    css = _static("canvas-tarefas.css")
    for cls in (".cvt-sala-zone", ".cvt-sala-chip", ".cvt-sala-card"):
        assert cls in css


def test_ilha_sala_nao_toca_zonas_quentes():
    body = _strip_banner(_static("canvas-sala.js"))
    for hot in ("ui.js", "messages.js", "sessions.js", "panels.js", "boot.js",
                "style.css", "index.html"):
        assert hot not in body
