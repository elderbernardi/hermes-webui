import json
from pathlib import Path

import pytest

from api import canvas_receita as R
from api import canvas_colheita, canvas_store
from tests.test_canvas_routes import FakeHandler

CANVAS = {
    "canvas_id": "canvas_20260801_abc", "focus": "Renegociar com Cliente Alfa",
    "vetor": "execucao", "shape": "tarefa", "intent_type": "produzir",
    "done_criteria": "ofício aprovado", "verification": "manifest + SHA-256",
    "microversos": {"primary": "cliente-alfa", "related": ["juridico"]},
    "gaps": ["Teto de desconto?", "Prazo de vigência?"],
    "personas": {"suggested": ["redator-institucional"], "explicit": [], "evaluators": ["critico"]},
    "artifacts": {"expected": [{"title": "oficio.docx", "path": "x/oficio.docx", "type": "docx"}]},
    "authorization": [{"action": "enviar email", "words": "pode enviar", "at": "..."}],
    "promotion_candidates": {"knowledge": ["algo instanciado"]},
}

def test_clean_portable_strips_instance_keeps_structure():
    cp = R.clean_portable(CANVAS)
    assert "canvas_id" not in cp
    assert cp["microversos"]["primary"] is None          # vínculo de instância removido
    assert cp.get("authorization", []) == []             # palavras de AUTH removidas
    assert "promotion_candidates" not in cp              # instâncias removidas
    assert cp["vetor"] == "execucao" and cp["shape"] == "tarefa"     # estrutura preservada
    assert cp["verification"] == "manifest + SHA-256"
    assert cp["intake_questions"] == ["Teto de desconto?", "Prazo de vigência?"]  # gaps → intake
    assert cp["personas"]["slots"] == ["redator-institucional", "critico"]

def test_recipe_body_is_yaml_without_secrets():
    body = R.recipe_body(CANVAS)
    assert "canvas_20260801_abc" not in body and "pode enviar" not in body
    assert "vetor: execucao" in body

def test_prefill_from_recipe_seeds_new_canvas():
    cp = R.clean_portable(CANVAS)
    doc = R.prefill_from_recipe({"structure": cp, "focus_template": "Renegociar com <cliente>"})
    assert doc["vetor"] == "execucao" and doc["shape"] == "tarefa"
    assert doc["done_criteria"] == "ofício aprovado"
    assert doc["gaps"] == ["Teto de desconto?", "Prazo de vigência?"]
    assert doc["microversos"]["primary"] is None


# ── Task 7: endpoint tests ────────────────────────────────────────────────────

def test_canonizar_writes_recipe(tmp_path, monkeypatch):
    """canonizar: writes recipe file with vetor in frontmatter and body, focus_template in frontmatter.
    No instance id (canvas_20260801_abc) must appear in the body."""
    monkeypatch.setattr(canvas_store, "load_canvas", lambda cid: CANVAS)

    def fake_acervoctl(args, input_file=None):
        if args[0] == "prepare-write":
            tgt = tmp_path / "receitas" / "templates" / "r.md"
            return (0,
                    json.dumps({
                        "target_path": str(tgt),
                        "log_path": str(tmp_path / "receitas" / "_meta" / "log.md"),
                        "relative_output": "templates/r.md",
                    }),
                    "")
        if args[0] == "commit-write":
            cf = args[args.index("--content-file") + 1]
            tgt = tmp_path / "receitas" / "templates" / "r.md"
            tgt.parent.mkdir(parents=True, exist_ok=True)
            tgt.write_text(Path(cf).read_text(encoding="utf-8"), encoding="utf-8")
            return 0, json.dumps({"target_path": str(tgt)}), ""
        return 0, "{}", ""

    monkeypatch.setattr(canvas_colheita, "acervoctl", fake_acervoctl)
    h = FakeHandler()
    result = R.handle_receita_post(h, "/api/canvas/receita/canonizar", {"canvas_id": "canvas_x"})
    assert result
    assert h.status == 200
    written = (tmp_path / "receitas" / "templates" / "r.md").read_text(encoding="utf-8")
    # Body must contain vetor but NOT the instance canvas_id
    assert "vetor: execucao" in written
    assert "canvas_20260801_abc" not in written
    # Frontmatter must have both focus_template and vetor (proves canonizar emits vetor)
    assert "focus_template:" in written
    # Split frontmatter from body to verify vetor is in the frontmatter, not just the body
    fm, _ = R._split_frontmatter(written)
    assert "vetor: execucao" in fm, "vetor must be emitted in frontmatter by _build_recipe_frontmatter"


def test_canonizar_workflow_shape(tmp_path, monkeypatch):
    """shape=plano-primeiro should produce nature=workflow."""
    workflow_canvas = {**CANVAS, "shape": "plano-primeiro"}
    monkeypatch.setattr(canvas_store, "load_canvas", lambda cid: workflow_canvas)

    captured = {}

    def fake_acervoctl(args, input_file=None):
        if args[0] == "prepare-write":
            captured["nature"] = args[args.index("--nature") + 1]
            return (0, json.dumps({"target_path": str(tmp_path / "r.md"),
                                   "log_path": str(tmp_path / "log.md"),
                                   "relative_output": "templates/r.md"}), "")
        if args[0] == "commit-write":
            # write something so the handler can read the response
            cf = args[args.index("--content-file") + 1]
            out = tmp_path / "r.md"
            out.write_text(Path(cf).read_text(encoding="utf-8"), encoding="utf-8")
            return 0, json.dumps({"target_path": str(out)}), ""
        return 0, "{}", ""

    monkeypatch.setattr(canvas_colheita, "acervoctl", fake_acervoctl)
    h = FakeHandler()
    R.handle_receita_post(h, "/api/canvas/receita/canonizar", {"canvas_id": "x"})
    assert captured.get("nature") == "workflow"


def test_list_returns_empty_when_dir_absent(tmp_path, monkeypatch):
    """list: returns 200 [] when receitas dir doesn't exist (never 500)."""
    monkeypatch.setattr(canvas_store, "acervo_root", lambda: tmp_path)
    h = FakeHandler()
    result = R.handle_receita_get(h, _parsed("/api/canvas/receita/list"))
    assert result
    assert h.status == 200
    assert json.loads(h.wfile.getvalue()) == []


def test_list_returns_entries_when_present(tmp_path, monkeypatch):
    """list: returns recipe entries with focus_template and vetor from frontmatter."""
    monkeypatch.setattr(canvas_store, "acervo_root", lambda: tmp_path)
    # Create a fake recipe file under micro/receitas/templates/
    tpl_dir = tmp_path / "micro" / "receitas" / "templates"
    tpl_dir.mkdir(parents=True)
    recipe_content = (
        "---\n"
        "schema: acervo/v0.2\n"
        "type: template\n"
        'title: "Renegociar"\n'
        'focus_template: "Renegociar com <cliente>"\n'
        "vetor: execucao\n"
        "---\n"
        "vetor: execucao\n"
    )
    (tpl_dir / "minha-receita.md").write_text(recipe_content, encoding="utf-8")
    h = FakeHandler()
    result = R.handle_receita_get(h, _parsed("/api/canvas/receita/list"))
    assert result
    assert h.status == 200
    items = json.loads(h.wfile.getvalue())
    assert len(items) == 1
    assert items[0]["recipe_id"] == "minha-receita"
    assert items[0]["focus_template"] == "Renegociar com <cliente>"
    assert items[0]["vetor"] == "execucao"


def test_iniciar_creates_prefilled_canvas(tmp_path, monkeypatch):
    """iniciar: creates a prefilled canvas via create_draft + save_canvas with correct signatures."""
    monkeypatch.setattr(R, "_load_recipe", lambda rid: {
        "structure": R.clean_portable(CANVAS),
        "focus_template": "Renegociar com <cliente>",
    })

    # create_draft returns tuple (canvas_id, canvas) per real signature
    fake_canvas = {"canvas_id": "canvas_new_001", "vetor": "evolucao", "gaps": []}
    monkeypatch.setattr(canvas_store, "create_draft",
                        lambda focus_text="": ("canvas_new_001", fake_canvas))

    saved = {}
    monkeypatch.setattr(canvas_store, "save_canvas",
                        lambda canvas_id, canvas: saved.update({"canvas_id": canvas_id, **canvas}))

    h = FakeHandler()
    result = R.handle_receita_post(h, "/api/canvas/receita/iniciar", {"recipe_id": "r1"})
    assert result
    assert h.status == 200
    body = json.loads(h.wfile.getvalue())
    assert body["canvas_id"] == "canvas_new_001"
    # The saved doc must have structure fields from the recipe
    assert saved["vetor"] == "execucao"
    assert saved["gaps"][0] == "Teto de desconto?"


def test_forward_dispatch_post(monkeypatch):
    """handle_canvas_post must forward /api/canvas/receita/* to handle_receita_post."""
    from api import canvas_tarefas
    called = {}

    def fake_post(handler, path, body):
        called["path"] = path
        return True

    monkeypatch.setattr("api.canvas_receita.handle_receita_post", fake_post)
    h = FakeHandler()
    result = canvas_tarefas.handle_canvas_post(h, "/api/canvas/receita/canonizar", {})
    assert result
    assert called.get("path") == "/api/canvas/receita/canonizar"


def test_forward_dispatch_get(monkeypatch):
    """handle_canvas_get must forward /api/canvas/receita/* to handle_receita_get."""
    from api import canvas_tarefas
    called = {}

    def fake_get(handler, parsed):
        called["path"] = parsed.path
        return True

    monkeypatch.setattr("api.canvas_receita.handle_receita_get", fake_get)
    h = FakeHandler()
    result = canvas_tarefas.handle_canvas_get(h, _parsed("/api/canvas/receita/list"))
    assert result
    assert called.get("path") == "/api/canvas/receita/list"


# ── helpers ───────────────────────────────────────────────────────────────────

class _Parsed:
    """Minimal fake of urllib.parse.ParseResult for tests."""
    def __init__(self, path: str, query: str = ""):
        self.path = path
        self.query = query


def _parsed(path: str, query: str = "") -> _Parsed:
    return _Parsed(path, query)
