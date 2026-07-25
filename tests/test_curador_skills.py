import json
import pytest
from api import canvas_curador as cc, curador_a2a as a2a


@pytest.fixture()
def skills_env(tmp_path, monkeypatch):
    (tmp_path / "micro/comercial/knowledge").mkdir(parents=True)
    (tmp_path / "micro/comercial/knowledge/renegociacao.md").write_text("x", encoding="utf-8")
    monkeypatch.setenv("ACERVO", str(tmp_path))
    monkeypatch.setattr(cc.canvas_store, "load_canvas", lambda cid: {
        "canvas_id": cid, "microversos": {"primary": "comercial", "related": ["gabinete"]}})
    return tmp_path


def _task(skill="buscar_acervo", **args):
    t = a2a.new_task(contextId="c", skill=skill, budget_tokens=6000)
    t["metadata"]["args"] = {"query": args.get("query"), "escopo": args.get("escopo"),
                             "tema": args.get("tema"),
                             "allow_scopes": args.get("allow_scopes", [])}
    return t


def test_buscar_acervo_artefato_citado(skills_env, monkeypatch):
    monkeypatch.setattr(cc, "curador_retrieve", lambda q, s, **k: {
        "found": True, "total_tokens": 410,
        "items": [{"header": "Renegociação", "content": "playbook", "tokens_est": 410}],
        "citations": ["Acervo: micro/comercial/knowledge/renegociacao.md"]})
    # LLM destila, mas NÃO reescreve a citação (verbatim do retrieve)
    monkeypatch.setattr(cc, "_call_llm_curator", lambda p: json.dumps(
        {"porque": "playbook de renegociação do microverso"}))
    art, gap = cc._skill_buscar_acervo(_task(query="renegociar", escopo="comercial"))
    assert gap is None
    data = art["parts"][0]["data"]
    assert data["citations"] == ["Acervo: micro/comercial/knowledge/renegociacao.md"]
    assert data["path"] == "micro/comercial/knowledge/renegociacao.md"
    assert cc._tokens_est(art) <= cc.ARTIFACT_BUDGET_N


def test_buscar_acervo_bound1_dispara_apos_2_buscas(skills_env, monkeypatch):
    calls = {"n": 0}
    def empty(q, s, **k):
        calls["n"] += 1
        return {"found": False, "items": [], "citations": [], "total_tokens": 0}
    monkeypatch.setattr(cc, "curador_retrieve", empty)
    t = _task(query="inexistente", escopo="comercial")
    art, gap = cc._skill_buscar_acervo(t)
    assert art is None and gap                      # gap honesto, sem Artifact
    assert calls["n"] == 2                          # itera 2x, não 3 (Bound 1 corta antes da 3ª)
    assert cc._empty_exhausted(t)


def test_buscar_acervo_ops_pousam_em_next_moves(skills_env, monkeypatch):
    monkeypatch.setattr(cc, "curador_retrieve", lambda q, s, **k: {
        "found": True, "total_tokens": 100,
        "items": [{"header": "H", "content": "c", "tokens_est": 100}],
        "citations": ["Acervo: micro/comercial/knowledge/renegociacao.md"]})
    monkeypatch.setattr(cc, "_call_llm_curator", lambda p: json.dumps(
        {"porque": "p", "next_move": "revisar cláusula 5"}))
    art, _ = cc._skill_buscar_acervo(_task(query="q", escopo="comercial"))
    ops = art["metadata"]["ops"]
    assert any(o["path"] == "/next_moves/-" for o in ops)
