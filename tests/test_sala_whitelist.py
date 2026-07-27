from api import canvas_tarefas as ct


def test_authorization_pointer_is_editable():
    assert ct._path_editavel("/authorization/-") is True
    assert ct._path_editavel("/authorization/0") is True


def test_non_whitelisted_still_rejected():
    assert ct._path_editavel("/personas/evaluators/-") is False


import copy
from api import canvas_store


def test_patch_adds_authorization_item(tmp_path, monkeypatch):
    monkeypatch.setenv("ACERVO", str(tmp_path))
    (tmp_path / "_tasks").mkdir()
    cid, canvas = canvas_store.create_draft("autorizar envio de ofício")
    # a launched-session doc must carry an authorization list (harness template does;
    # _MINIMAL fallback does). Assert the add applies and re-validates.
    ops = [{"op": "add", "path": "/authorization/-",
            "value": {"action": "git push", "words": "pode dar push", "at": "2026-07-25T20:00:00Z"}}]
    canvas2 = canvas_store.apply_patch(copy.deepcopy(canvas), ops)
    assert canvas2["authorization"][-1]["words"] == "pode dar push"
