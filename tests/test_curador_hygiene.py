# tests/test_curador_hygiene.py  (fork)
import io, json, time, pytest
from api import canvas_curador as cc, curador_a2a as a2a, canvas_store, canvas_brief


class FakeHandler:
    def __init__(self): self.wfile = io.BytesIO(); self.status = None
    def send_response(self, c): self.status = c
    def send_header(self, *a): pass
    def end_headers(self): pass


@pytest.fixture()
def room(tmp_path, monkeypatch):
    (tmp_path / "_tasks").mkdir()
    (tmp_path / "micro/comercial/knowledge").mkdir(parents=True)
    monkeypatch.setenv("ACERVO", str(tmp_path))
    cc.CURADOR_ROOMS.clear(); cc._STORE = a2a.TaskStore(); cc._QUEUE.clear()
    if cc._CURADOR_BUSY.locked(): cc._CURADOR_BUSY.release()
    return tmp_path


def _est(obj):
    return len(json.dumps(obj, ensure_ascii=False)) // 4


def _wait(tid, st, timeout=5):
    dl = time.time() + timeout
    while time.time() < dl:
        t = cc._STORE.get(tid)
        if t and t["status"]["state"] == st: return t
        time.sleep(0.01)
    raise AssertionError("timeout")


def test_hygiene_invariante_boundary(room, monkeypatch):
    # (a) complemento: payload pequeno vs grande -> o que cruza fica <= N
    monkeypatch.setattr(cc, "_call_llm_curator", lambda p: json.dumps(
        {"tipo": "buscar_acervo", "path": "p", "porque": "curto"}))
    small = a2a.new_artifact(name="n", description="d",
                             data={"tipo": "buscar_acervo", "path": "p", "porque": "curto"})
    big = a2a.new_artifact(name="n", description="d",
                           data={"tipo": "buscar_acervo", "path": "p", "porque": "x" * 8000})
    assert _est(cc._budget_guard(small)) <= cc.ARTIFACT_BUDGET_N
    assert _est(cc._budget_guard(big)) <= cc.ARTIFACT_BUDGET_N


def test_hygiene_real_room(room, monkeypatch):
    # (b) real-room: pipeline real; mede o CONTEXTO DO EXECUTOR (brief compilado)
    cid, canvas = canvas_store.create_draft("renegociar contrato Alfa")
    canvas["focus"] = "renegociar contrato Alfa"
    canvas["vetor"] = "execucao"; canvas["intent_type"] = "produzir"
    canvas_store.save_canvas(cid, canvas)
    brief_antes = canvas_brief.compile_brief(canvas_store.load_canvas(cid))
    exec_tokens_antes = _est(brief_antes)

    tabela = []
    for rotulo, internal in (("pequena", 400), ("enorme", 40000)):
        # retrieve stub com volume INTERNO controlado (total_tokens), mas destilado curto
        monkeypatch.setattr(cc, "curador_retrieve", lambda q, s, _tt=internal, **k: {
            "found": True, "total_tokens": _tt,
            "items": [{"header": "H", "content": "c" * (_tt), "tokens_est": _tt}],
            "citations": ["Acervo: micro/comercial/knowledge/renegociacao.md"]})
        monkeypatch.setattr(cc, "_call_llm_curator",
                            lambda p: json.dumps({"porque": "playbook"}))
        tid = cc.delegar(cid, "buscar_acervo", query="renegociar")
        _wait(tid, "completed")
        h = cc._STORE.get(tid)["metadata"]["hygiene"]
        # o brief do executor NÃO muda com a delegação (nada auto-injeta)
        exec_tokens_depois = _est(canvas_brief.compile_brief(canvas_store.load_canvas(cid)))
        tabela.append((rotulo, h["curador_internal_tokens"], exec_tokens_depois))
        assert exec_tokens_depois == exec_tokens_antes    # contexto do executor CONSTANTE

    # internal cresce ~100x entre pequena e enorme; executor constante
    assert tabela[1][1] > tabela[0][1] * 10
    assert tabela[0][2] == tabela[1][2] == exec_tokens_antes

    # aceitar UM card sobe o executor em Δ REAL (>0) e <= N (nunca pelo volume interno).
    # IMPORTANTE (achado #4): compile_brief renderiza next_moves/scope/assumptions/gaps,
    # mas NÃO personas.suggested nem acervo_aplicado (ver api/canvas_brief.py) — então o
    # accept do gate usa /next_moves/- (campo renderizado) para produzir Δ mensurável.
    art_ops = [{"op": "add", "path": "/next_moves/-",
                "value": "revisar cláusula 5 com base no playbook de renegociação"}]
    fh = FakeHandler()
    from api import canvas_tarefas
    canvas_tarefas._handle_patch(fh, {"canvas_id": cid, "ops": art_ops})
    exec_apos_accept = _est(canvas_brief.compile_brief(canvas_store.load_canvas(cid)))
    delta = exec_apos_accept - exec_tokens_antes
    assert 0 < delta <= cc.ARTIFACT_BUDGET_N

    # grava a tabela p/ anexar ao gate
    import pathlib
    out = pathlib.Path(cc.__file__).resolve().parent.parent / "docs/curador/HYGIENE-PROOF.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Prova de higiene de contexto (P11) — F2 Curador\n",
             "| Delegação | curador_internal_tokens | executor_tokens (contexto da Sala) |",
             "|---|---|---|"]
    for rot, intern, ex in tabela:
        lines.append(f"| {rot} | {intern} | {ex} |")
    lines.append(f"\nexecutor constante = {exec_tokens_antes}; "
                 f"após aceitar 1 card = {exec_apos_accept} (Δ ≤ N={cc.ARTIFACT_BUDGET_N}).")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert out.is_file()
