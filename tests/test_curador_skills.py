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


def test_sugerir_itens_persona_e_acervo(skills_env, monkeypatch):
    monkeypatch.setattr(cc, "load_capability_card", lambda slug: {
        "name": "comercial", "skills": [
            {"id": "comercial/persona", "name": "persona", "count": 1,
             "examples": ["persona/negociador.md"], "porque": "negociação dura"}]})
    monkeypatch.setattr(cc, "curador_posture", lambda q, s, **k: {
        "found": True, "total_tokens": 300,
        "items": [{"header": "template de ofício", "content": "...",
                   "path": "micro/comercial/templates/oficio.md", "tokens_est": 120}],
        "citations": ["Acervo: micro/comercial/templates/oficio.md"]})
    monkeypatch.setattr(cc, "_call_llm_curator", lambda p: json.dumps({"itens": [
        {"nature": "persona", "titulo": "negociador",
         "path": "micro/comercial/persona/negociador.md", "porque": "negociação dura"},
        {"nature": "template", "titulo": "ofício",
         "path": "micro/comercial/templates/oficio.md", "porque": "modelo pronto"}]}))
    art, gap = cc._skill_sugerir_itens(_task(skill="sugerir_itens"))
    assert gap is None
    data = art["parts"][0]["data"]
    assert data["nature"] == "persona"
    assert art["metadata"]["ops"][0]["path"] == "/personas/suggested/-"


def test_sugerir_itens_fit_gate_descarta_sem_path(skills_env, monkeypatch):
    monkeypatch.setattr(cc, "load_capability_card", lambda slug: None)
    monkeypatch.setattr(cc, "curador_posture", lambda q, s, **k: {
        "found": True, "total_tokens": 10, "items": [], "citations": []})
    monkeypatch.setattr(cc, "_call_llm_curator", lambda p: json.dumps({"itens": [
        {"nature": "skill", "titulo": "boa ideia", "porque": "sem path"}]}))
    art, gap = cc._skill_sugerir_itens(_task(skill="sugerir_itens"))
    assert art is None and gap                      # nenhum item citável -> gap


def test_pesquisar_sintese_com_fontes(skills_env, monkeypatch):
    monkeypatch.setenv("CURADOR_ENABLE_PESQUISAR", "1")
    monkeypatch.setattr(cc, "_web_search", lambda q: [
        {"title": "Preços 2026", "url": "https://ex.example.com/a", "snippet": "..."}])
    monkeypatch.setattr(cc, "_call_llm_curator", lambda p: json.dumps(
        {"sintese": "mercado subiu 3%", "suficiente": True}))
    art, gap = cc._skill_pesquisar(_task(skill="pesquisar", tema="preços de mercado"))
    assert gap is None
    data = art["parts"][0]["data"]
    assert data["trust"] == "untrusted"
    assert data["fontes"] == ["https://ex.example.com/a"]
    # ops de pesquisar só podem tocar /gaps/-
    for op in art["metadata"]["ops"]:
        assert op["path"] == "/gaps/-"


def test_pesquisar_bound1_duas_buscas_vazias_vira_gap(skills_env, monkeypatch):
    monkeypatch.setenv("CURADOR_ENABLE_PESQUISAR", "1")
    calls = {"n": 0}
    monkeypatch.setattr(cc, "_web_search",
                        lambda q: (calls.__setitem__("n", calls["n"] + 1), [])[1])
    monkeypatch.setattr(cc, "_call_llm_curator", lambda p: json.dumps(
        {"sintese": "", "suficiente": False, "refinar": "outra query"}))
    t = _task(skill="pesquisar", tema="tema obscuro")
    art, gap = cc._skill_pesquisar(t)
    assert art is None and gap
    assert calls["n"] == 2 and cc._empty_exhausted(t)


def test_pesquisar_mascara_segredos_em_fontes(skills_env, monkeypatch):
    monkeypatch.setenv("CURADOR_ENABLE_PESQUISAR", "1")
    monkeypatch.setattr(cc, "_web_search", lambda q: [
        {"title": "t", "url": "https://ex.example.com/x?api_key=SEGREDO123&z=1",
         "snippet": "s"}])
    monkeypatch.setattr(cc, "_call_llm_curator", lambda p: json.dumps(
        {"sintese": "ok", "suficiente": True}))
    art, _ = cc._skill_pesquisar(_task(skill="pesquisar", tema="x"))
    assert "SEGREDO123" not in json.dumps(art)
    assert "api_key=***" in art["parts"][0]["data"]["fontes"][0]
