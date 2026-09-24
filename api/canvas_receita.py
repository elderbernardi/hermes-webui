"""F4 Receita — canvas → receita clean-portable (núcleo puro) + HTTP endpoints.

Task 6 (pure core): clean_portable / recipe_body / prefill_from_recipe.
Task 7 (impure layer): _build_recipe_frontmatter, canonizar / list / iniciar
  endpoints via handle_receita_get / handle_receita_post; forward-dispatch
  entries in canvas_tarefas.py.
"""
import copy
import json
import tempfile
import time
from pathlib import Path

import yaml

from api import canvas_store

_STRUCTURE_KEYS = ("vetor", "shape", "intent_type", "done_criteria", "verification")


# ── Pure core (Task 6) ─────────────────────────────────────────────────────────

def clean_portable(doc: dict) -> dict:
    """Strip instance-specific fields, preserve structure."""
    cp: dict = {k: doc.get(k) for k in _STRUCTURE_KEYS if doc.get(k) is not None}
    cp["microversos"] = {"primary": None, "related": list(doc.get("microversos", {}).get("related", []))}
    cp["intake_questions"] = list(doc.get("gaps", []))          # gaps recorrentes viram perguntas de intake
    p = doc.get("personas", {})
    cp["personas"] = {"slots": list(p.get("suggested", [])) + list(p.get("evaluators", []))}
    cp["artifacts_expected"] = [{"title": a.get("title"), "type": a.get("type")}
                                for a in doc.get("artifacts", {}).get("expected", [])]
    # instância removida: canvas_id, focus (nomes próprios), authorization, promotion_candidates, scope, assumptions
    return cp


def recipe_body(doc: dict) -> str:
    """YAML representation of clean-portable structure (corpo da receita)."""
    return yaml.safe_dump(clean_portable(doc), allow_unicode=True, sort_keys=False)


def prefill_from_recipe(recipe: dict) -> dict:
    """Create a new canvas doc seeded from recipe structure."""
    cp = recipe["structure"]
    # Use deepcopy to avoid shared references in nested dicts
    doc = copy.deepcopy(canvas_store._MINIMAL)
    for k in _STRUCTURE_KEYS:
        if k in cp:
            doc[k] = cp[k]
    doc["gaps"] = list(cp.get("intake_questions", []))
    doc["microversos"] = {"primary": None, "related": list(cp.get("microversos", {}).get("related", []))}
    doc["personas"] = {"suggested": list(cp.get("personas", {}).get("slots", [])), "explicit": [], "evaluators": []}
    doc["focus"] = recipe.get("focus_template", "")
    return doc


# ── Impure layer (Task 7) ──────────────────────────────────────────────────────

# JSON response helper — same pattern as canvas_tarefas._j / canvas_colheita._j
def _j(handler, obj, status: int = 200) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _build_recipe_frontmatter(doc: dict, now: str | None = None, today: str | None = None) -> str:
    """Build OKF v0.2 YAML frontmatter block for a receita.

    focus_template preserves the full original focus text (client-name stripping
    deferred to F5 per spec §11). structure/body from recipe_body has NO focus —
    focus_template lives only in the frontmatter.
    """
    if now is None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    if today is None:
        today = time.strftime("%Y-%m-%d")

    focus = doc.get("focus") or ""
    vetor = doc.get("vetor") or ""
    nature = "workflow" if doc.get("shape") == "plano-primeiro" else "template"
    title = focus[:80] or "receita"
    description = focus[:160] or "receita"

    lines = [
        "---",
        "schema: acervo/v0.2",
        f"type: {nature}",
        f'title: {json.dumps(title, ensure_ascii=False)}',
        f"focus_template: {json.dumps(focus, ensure_ascii=False)}",
        f"vetor: {vetor}",
        f'description: {json.dumps(description, ensure_ascii=False)}',
        "tags:",
        "  - receita",
        "  - canvas-tarefas",
        f"created_at: {now}",
        "class: perene",
        "status: active",
        "epistemic: rule",
        "---",
    ]
    return "\n".join(lines) + "\n"


def _load_recipe(recipe_id: str) -> dict:
    """Load a recipe from the acervo micro/receitas/{templates,workflows}/ dirs.

    Returns {"structure": <parsed body YAML>, "focus_template": <from frontmatter>}.
    """
    root = canvas_store.acervo_root() / "micro" / "receitas"
    for sub in ("templates", "workflows"):
        candidate = root / sub / f"{recipe_id}.md"
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8")
            frontmatter, body = _split_frontmatter(text)
            fm = yaml.safe_load(frontmatter) or {}
            structure = yaml.safe_load(body) or {}
            return {
                "structure": structure,
                "focus_template": fm.get("focus_template", ""),
            }
    raise FileNotFoundError(f"recipe not found: {recipe_id!r}")


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split a '---\\n...\\n---\\n' frontmatter from body. Returns (fm_yaml, body)."""
    if text.startswith("---"):
        idx = text.find("\n---", 3)
        if idx != -1:
            nl = text.find("\n", idx + 1)
            fm = text[3:idx].strip()          # between the two ---
            body = text[nl + 1:] if nl != -1 else ""
            return fm, body
    return "", text


def _scan_recipes() -> list[dict]:
    """Scan acervo micro/receitas/{templates,workflows}/*.md, read frontmatter."""
    try:
        root = canvas_store.acervo_root() / "micro" / "receitas"
    except Exception:
        return []
    items: list[dict] = []
    for sub in ("templates", "workflows"):
        d = root / sub
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            try:
                text = md.read_text(encoding="utf-8")
                fm_yaml, _ = _split_frontmatter(text)
                fm = yaml.safe_load(fm_yaml) or {}
                items.append({
                    "recipe_id": md.stem,
                    "focus_template": fm.get("focus_template", ""),
                    "vetor": fm.get("vetor", ""),
                    "path": str(md),
                })
            except Exception:
                continue
    return items


# ── Endpoint handlers ──────────────────────────────────────────────────────────

def handle_receita_get(handler, parsed) -> bool:
    """Dispatch GET /api/canvas/receita/* paths."""
    path = parsed.path

    if path == "/api/canvas/receita/list":
        try:
            items = _scan_recipes()
        except Exception:
            items = []
        _j(handler, items)
        return True

    return False


def handle_receita_post(handler, path: str, body: dict) -> bool:
    """Dispatch POST /api/canvas/receita/* paths."""
    from api import canvas_colheita  # late import: keeps module boot cheap + allows monkeypatch

    # POST /api/canvas/receita/canonizar
    if path == "/api/canvas/receita/canonizar":
        cid = body.get("canvas_id") or ""
        try:
            doc = canvas_store.load_canvas(cid)
        except Exception:
            _j(handler, {"error": "canvas desconhecido"}, 404)
            return True

        nature = "workflows" if doc.get("shape") == "plano-primeiro" else "templates"
        focus = doc.get("focus") or ""
        title = focus[:80] or "receita"

        receipt_tmp = None
        content_tmp = None
        try:
            # Step 1: prepare-write → get target_path + receipt
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as tf:
                receipt_tmp = tf.name

            rc, stdout, stderr = canvas_colheita.acervoctl([
                "prepare-write",
                "--microverso", "receitas",
                "--nature", nature,
                "--title", title,
                "--receipt-out", receipt_tmp,
            ])
            if rc != 0:
                detail = stderr or stdout
                _j(handler, {"error": "prepare-write falhou", "detail": detail[:200]}, 500)
                return True

            # Parse receipt from stdout or receipt-out file
            try:
                receipt = json.loads(stdout)
            except (json.JSONDecodeError, ValueError):
                try:
                    receipt = json.loads(Path(receipt_tmp).read_text(encoding="utf-8"))
                except Exception:
                    receipt = {}

            # Step 2: build content = frontmatter + recipe_body
            frontmatter = _build_recipe_frontmatter(doc)
            body_yaml = recipe_body(doc)
            content = frontmatter + "\n" + body_yaml

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8"
            ) as cf:
                cf.write(content)
                content_tmp = cf.name

            # Persist receipt to file for commit-write --receipt
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as rf:
                json.dump(receipt, rf, ensure_ascii=False)
                receipt_file = rf.name

            try:
                rc2, stdout2, stderr2 = canvas_colheita.acervoctl([
                    "commit-write",
                    "--receipt", receipt_file,
                    "--content-file", content_tmp,
                    "--description", title,
                    "--class-name", "perene",
                ])
            finally:
                try:
                    Path(receipt_file).unlink(missing_ok=True)
                except Exception:
                    pass

            if rc2 != 0:
                detail2 = stderr2 or stdout2
                _j(handler, {"error": "commit-write falhou", "detail": detail2[:200]}, 500)
                return True

            try:
                commit_out = json.loads(stdout2)
            except (json.JSONDecodeError, ValueError):
                commit_out = {}

            target_path = commit_out.get("target_path") or receipt.get("target_path", "")
            recipe_id = Path(target_path).stem if target_path else ""
            _j(handler, {"recipe_id": recipe_id, "path": target_path})
            return True

        finally:
            for p in (receipt_tmp, content_tmp):
                if p:
                    try:
                        Path(p).unlink(missing_ok=True)
                    except Exception:
                        pass

    # POST /api/canvas/receita/iniciar
    if path == "/api/canvas/receita/iniciar":
        rid = body.get("recipe_id") or ""
        try:
            recipe = _load_recipe(rid)
        except FileNotFoundError:
            _j(handler, {"error": "recipe não encontrada"}, 404)
            return True
        except Exception as exc:
            _j(handler, {"error": f"erro ao carregar recipe: {exc}"}, 500)
            return True

        doc = prefill_from_recipe(recipe)
        focus_text = recipe.get("focus_template", "")
        cid, _ = canvas_store.create_draft(focus_text)
        doc["canvas_id"] = cid
        canvas_store.save_canvas(cid, doc)
        _j(handler, {"canvas_id": cid})
        return True

    return False
