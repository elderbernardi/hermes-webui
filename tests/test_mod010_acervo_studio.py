"""MOD-010 Acervo Studio — hermetic backend unit tests (Phase 0).

Tests the pure tree helpers added to api/acervo_explorer.py for the new
`micro` and `inbox` scopes, mirroring the MOD-009 hermetic style:
api.routes._acervo_root is monkeypatched onto a tmp_path acervo.
"""
import pytest

import api.acervo_explorer as ax
import api.routes as routes


@pytest.fixture
def acervo(tmp_path, monkeypatch):
    root = tmp_path / "acervo"
    (root / "micro" / "comercial" / "knowledge").mkdir(parents=True)
    (root / "micro" / "comercial" / "decisions").mkdir(parents=True)
    (root / "micro" / "_template" / "knowledge").mkdir(parents=True)  # underscore -> skipped
    (root / "_inbox" / "incoming").mkdir(parents=True)
    monkeypatch.setattr(routes, "_acervo_root", lambda: root)
    return root


def _w(root, rel, text="---\ntitle: T\n---\n\nbody\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_micro_nodes_lists_microverses_with_counts(acervo):
    _w(acervo, "micro/comercial/knowledge/precificacao.md")
    _w(acervo, "micro/comercial/decisions/alcada.md")
    nodes = ax._micro_nodes(routes, acervo, "", 1)
    slugs = {n["slug"]: n for n in nodes if n["type"] == "microverse"}
    assert "comercial" in slugs
    assert "_template" not in slugs          # underscore dirs skipped
    assert slugs["comercial"]["count"] == 2  # 2 pages across natures


def test_micro_nodes_lists_pages_for_a_slug(acervo):
    _w(acervo, "micro/comercial/knowledge/precificacao.md",
       "---\ntitle: Precificação\nstatus: ready\n---\n\nx\n")
    nodes = ax._micro_nodes(routes, acervo, "comercial", 2)
    natures = [n for n in nodes if n["type"] == "nature"]
    pages = [n for n in nodes if n["type"] == "page"]
    assert any(n["name"] == "knowledge" for n in natures)
    assert any(p["title"] == "Precificação" and p["status"] == "ready" for p in pages)


import json


def test_inbox_nodes_lists_incoming_envelopes(acervo):
    env = acervo / "_inbox" / "incoming" / "int_20260616_open-notebook"
    (env / "original").mkdir(parents=True)
    (env / "manifest.json").write_text(
        json.dumps({"title": "Open Notebook", "status": "received"}),
        encoding="utf-8")
    (acervo / "_inbox" / "incoming" / "int_20260701_bare").mkdir(parents=True)

    nodes = ax._inbox_nodes(routes, acervo)
    by_id = {n["id"]: n for n in nodes}
    assert by_id["int_20260616_open-notebook"]["title"] == "Open Notebook"
    assert by_id["int_20260616_open-notebook"]["status"] == "received"
    # Bare envelope with no manifest still lists, with a defaulted status.
    assert by_id["int_20260701_bare"]["status"] == "received"


@pytest.mark.parametrize("evil", ["../../etc", "../global", "..", "../../"])
def test_micro_nodes_rejects_traversal_slug(acervo, evil):
    # A slug that tries to escape the acervo root must yield nothing (no leak, no raise).
    assert ax._micro_nodes(routes, acervo, evil, 2) == []
