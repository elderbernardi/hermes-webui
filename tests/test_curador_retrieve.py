import json
import sys
import pytest

from api import canvas_curador_retrieve as ret


@pytest.fixture()
def stub_cmd(monkeypatch):
    monkeypatch.setenv("CURADOR_ACERVOCTL_CMD",
                       f"{sys.executable} tests/fixtures/stub_acervoctl_retrieve.py")


def test_retrieve_devolve_items_e_citacoes(stub_cmd):
    out = ret.curador_retrieve("renegociar", "comercial", budget=6000, k=5)
    assert out["found"] is True
    assert out["citations"] == ["Acervo: micro/comercial/knowledge/renegociacao.md"]
    assert out["items"][0]["header"]
    assert out["total_tokens"] == 410


def test_retrieve_abstencao_nao_e_erro(stub_cmd, monkeypatch):
    monkeypatch.setenv("CURADOR_ACERVOCTL_STUB_MODE", "empty")
    out = ret.curador_retrieve("inexistente", "comercial")
    assert out["found"] is False
    assert out["citations"] == []
    # não levanta — abstenção honesta


def test_posture_usa_mesmo_shape(stub_cmd):
    out = ret.curador_posture("decidir preço", "comercial", mode="decision")
    assert "items" in out and "total_tokens" in out


def test_read_only_estrutural_sem_verbos_de_escrita():
    src = __import__("pathlib").Path(ret.__file__).read_text(encoding="utf-8")
    for verbo in ("prepare-write", "commit-write", "new-object",
                  "prepare_write", "commit_write"):
        assert verbo not in src, f"módulo do Curador não pode referenciar {verbo}"


def test_nao_anexa_json_flag():
    # achado #1: posture rejeita --json; _run nunca deve anexá-lo
    src = __import__("pathlib").Path(ret.__file__).read_text(encoding="utf-8")
    assert '"--json"' not in src and "'--json'" not in src
