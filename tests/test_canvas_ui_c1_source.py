import re
from pathlib import Path


def _js():
    return Path("static/canvas-tarefas.js").read_text(encoding="utf-8")


def _css():
    return Path("static/canvas-tarefas.css").read_text(encoding="utf-8")


def _strip_comments(js):
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)   # block comments
    js = re.sub(r"(?m)//.*$", "", js)               # line comments
    return js


def test_headline_edita_focus_nao_original_input():
    js = _js()
    assert "cvt-headline" in js
    assert 'editableSpanHtml("/focus"' in js
    assert "original_input_summary" in js          # display fallback (dot access)
    assert "/original_input_summary" not in js     # nunca é PATCH target


def test_chips_para_vetor_intent_shape():
    js = _js()
    assert "CHIP_GROUPS" in js
    assert "cvt-chip" in js
    assert "data-value" in js               # data-value é novo (chipHtml); data-field já existia
    assert 'closest(".cvt-chip")' in js
    assert "chip.dataset.field" in js and "chip.dataset.value" in js
    assert "cvt-ambig-btn" not in js               # card ambíguo antigo retirado


def test_microverso_dropdown_change_e_fallback():
    js, css = _js(), _css()
    assert "cvt-microverso-select" in js
    assert 'data-field="/microversos/primary"' in js
    assert "/api/canvas/microversos" in js         # fetch da lista
    assert 'addEventListener("change"' in js       # listener delegado
    assert "includes(cur)" in js                   # fallback fix-2 (valor fora dos slugs)
    assert "cvt-microverso-select" in css


def test_css_declutter_presente():
    css = _css()
    for cls in (".cvt-headline", ".cvt-chiprow", ".cvt-chip", ".cvt-chip.on"):
        assert cls in css


def test_detalhes_metodo_colapsado_via_state():
    js = _js()
    assert "cvt-collapse-toggle" in js
    assert "state.methodOpen" in js
    assert "methodCollapseHtml" in js
    # os campos de método moram DENTRO do colapso (via LIST_BY_PATH), não no fluxo
    for expr in ('LIST_BY_PATH["/scope"]', 'LIST_BY_PATH["/assumptions"]',
                 'LIST_BY_PATH["/next_moves"]', 'LIST_BY_PATH["/microversos/related"]'):
        assert expr in js
    # o grid plano antigo (todas as listas) foi desmontado
    assert "LIST_FIELDS.map(listZoneHtml)" not in js
    # fluxo principal = só lacunas + artefatos
    assert 'LIST_BY_PATH["/gaps"]' in js
    assert 'LIST_BY_PATH["/artifacts/expected"]' in js
