import pytest
from api import canvas_curador as cc, curador_a2a as a2a


def _task():
    return a2a.new_task(contextId="c", skill="buscar_acervo", budget_tokens=6000)


def test_tokens_est_heuristica():
    assert cc._tokens_est({"a": "x" * 400}) >= 100   # ~chars/4


def test_budget_guard_pequeno_passa(monkeypatch):
    monkeypatch.setattr(cc, "_call_llm_curator", lambda p: "não deveria ser chamado")
    art = a2a.new_artifact(name="n", description="d",
                           data={"tipo": "buscar_acervo", "path": "p", "porque": "curto"})
    out = cc._budget_guard(art)
    assert cc._tokens_est(out) <= cc.ARTIFACT_BUDGET_N


def test_budget_guard_grande_comprime_uma_vez(monkeypatch):
    chamou = {"n": 0}
    def fake(prompt):
        chamou["n"] += 1
        return '{"tipo": "buscar_acervo", "path": "p", "porque": "resumo curto"}'
    monkeypatch.setattr(cc, "_call_llm_curator", fake)
    big = a2a.new_artifact(name="n", description="d",
                           data={"tipo": "buscar_acervo", "path": "p", "porque": "x" * 5000})
    out = cc._budget_guard(big)
    assert chamou["n"] == 1
    assert cc._tokens_est(out) <= cc.ARTIFACT_BUDGET_N


def test_budget_guard_ainda_grande_trunca(monkeypatch):
    monkeypatch.setattr(cc, "_call_llm_curator", lambda p: "y" * 6000)  # comprime falha
    big = a2a.new_artifact(name="n", description="d",
                           data={"tipo": "buscar_acervo", "path": "p", "porque": "x" * 6000})
    out = cc._budget_guard(big)
    assert cc._tokens_est(out) <= cc.ARTIFACT_BUDGET_N
    assert "[destilado truncado" in out["parts"][0]["data"]["porque"]


def test_budget_guard_citations_grande_capa(monkeypatch):
    # porque pequeno, compressão no-op; citations sozinho estoura N -> o guard
    # tem de capar a lista para a fronteira nunca deixar passar > N.
    monkeypatch.setattr(cc, "_call_llm_curator", lambda p: "não é json")  # compress falha
    big_cites = [f"Acervo: micro/comercial/knowledge/doc-{i}.md" for i in range(400)]
    big = a2a.new_artifact(name="n", description="d",
                           data={"tipo": "buscar_acervo",
                                 "path": "micro/comercial/knowledge/doc-0.md",
                                 "citations": big_cites, "porque": "curto"})
    assert cc._tokens_est(big) > cc.ARTIFACT_BUDGET_N     # pré-condição: estoura só por citations
    out = cc._budget_guard(big)
    data = out["parts"][0]["data"]
    assert cc._tokens_est(out) <= cc.ARTIFACT_BUDGET_N
    assert cc._TRUNC_MARK in data["citations"]            # marcador de corte
    assert data["path"] == "micro/comercial/knowledge/doc-0.md"  # citação primária preservada
    assert cc._fit_ok(data) is True                       # fit gate segue satisfeito


def test_fit_gate_exige_citacao():
    assert cc._fit_ok({"path": "micro/x/k.md"}) is True
    assert cc._fit_ok({"fontes": ["https://ex.com"]}) is True
    assert cc._fit_ok({"fonte": "acervoctl retrieve"}) is True
    assert cc._fit_ok({"porque": "boa ideia sem citação"}) is False


def test_bound1_empty_lookups():
    t = _task()
    cc._bump_empty(t, "sig-A")            # 0 citáveis
    assert not cc._empty_exhausted(t)
    cc._bump_empty(t, "sig-A")            # assinatura duplicada
    assert cc._empty_exhausted(t)         # 2 -> pare


def test_bound2_attempts():
    t = _task()
    for _ in range(2):
        cc._bump_attempt(t)
    assert not cc._attempts_exhausted(t)
    cc._bump_attempt(t)
    assert cc._attempts_exhausted(t)      # 3 -> pare


def test_ledger_separa_internal_de_executor():
    t = _task()
    cc._ledger_retrieve(t, {"total_tokens": 5000})
    cc._ledger_retrieve(t, {"total_tokens": 5000})
    cc._ledger_emit(t, {"path": "p", "porque": "curto"})
    h = t["metadata"]["hygiene"]
    assert h["curador_internal_tokens"] == 10000     # trilha interna cresce
    assert h["n_retrieves"] == 2
    assert h["executor_tokens"] <= cc.ARTIFACT_BUDGET_N  # o que a Sala paga fica ≤ N
