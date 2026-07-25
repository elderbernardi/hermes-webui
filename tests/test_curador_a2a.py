import pytest
from api import curador_a2a as a2a


def test_new_task_shape_e_estado_inicial():
    t = a2a.new_task(contextId="canvas_x", skill="buscar_acervo", budget_tokens=6000)
    assert t["id"].startswith("curador_task_")
    assert t["contextId"] == "canvas_x"
    assert t["status"]["state"] == "submitted"
    assert t["status"]["timestamp"] and t["status"]["message"] is None
    assert t["history"] == [] and t["artifacts"] == []
    assert t["metadata"]["skill"] == "buscar_acervo"
    assert t["metadata"]["budget_tokens"] == 6000
    assert t["metadata"]["attempts"] == 0 and t["metadata"]["empty_lookups"] == 0
    assert t["metadata"]["hygiene"] == {
        "executor_tokens": 0, "curador_internal_tokens": 0, "n_retrieves": 0}


def test_transicao_feliz_submitted_working_completed():
    t = a2a.new_task(contextId="c", skill="buscar_acervo", budget_tokens=6000)
    a2a.transition(t, "working")
    assert t["status"]["state"] == "working"
    a2a.transition(t, "completed")
    assert t["status"]["state"] == "completed" and a2a.is_terminal(t)


def test_transicao_ilegal_levanta():
    t = a2a.new_task(contextId="c", skill="buscar_acervo", budget_tokens=6000)
    with pytest.raises(a2a.CuradorProtocolError):
        a2a.transition(t, "completed")  # submitted -> completed é ilegal


def test_transicao_a_partir_de_terminal_levanta():
    t = a2a.new_task(contextId="c", skill="buscar_acervo", budget_tokens=6000)
    a2a.transition(t, "working")
    a2a.transition(t, "failed", message=a2a.new_message(
        role="agent", skill="buscar_acervo", task_id=t["id"], text="sem hit"))
    assert t["status"]["message"]["parts"][0]["text"] == "sem hit"
    with pytest.raises(a2a.CuradorProtocolError):
        a2a.transition(t, "working")


def test_artifact_e_message_shapes():
    m = a2a.new_message(role="user", skill="buscar_acervo", task_id="tid",
                        metadata={"query": "renegociar"}, text="buscar_acervo")
    assert m["role"] == "user" and m["taskId"] == "tid"
    assert m["parts"][0]["kind"] == "text" and m["parts"][0]["text"] == "buscar_acervo"
    assert m["metadata"]["skill"] == "buscar_acervo" and m["metadata"]["query"] == "renegociar"
    art = a2a.new_artifact(name="sugestao", description="d",
                           data={"tipo": "buscar_acervo", "path": "micro/x/k.md"},
                           ops=[{"op": "add", "path": "/next_moves/-", "value": "v"}])
    assert art["parts"][0]["kind"] == "data"
    assert art["parts"][0]["data"]["path"] == "micro/x/k.md"
    assert art["metadata"]["ops"][0]["path"] == "/next_moves/-"


def test_taskstore_keyed_por_context():
    store = a2a.TaskStore()
    a = store.add(a2a.new_task(contextId="c1", skill="buscar_acervo", budget_tokens=1))
    b = store.add(a2a.new_task(contextId="c1", skill="sugerir_itens", budget_tokens=1))
    store.add(a2a.new_task(contextId="c2", skill="pesquisar", budget_tokens=1))
    assert store.get(a["id"]) is a
    ids = {t["id"] for t in store.for_context("c1")}
    assert ids == {a["id"], b["id"]}


def test_leitores_alias_tolerantes():
    assert a2a.part_kind({"type": "data"}) == "data"       # alias
    assert a2a.part_kind({"kind": "text"}) == "text"       # canônico
    assert a2a.context_id({"sessionId": "s"}) == "s"       # alias
    assert a2a.context_id({"contextId": "c"}) == "c"       # canônico
