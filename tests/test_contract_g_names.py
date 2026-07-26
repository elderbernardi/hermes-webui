import os, pathlib, pytest


def _contract_path():
    root = os.environ.get("UMBRELLA_ROOT")
    if not root:
        pytest.skip("UMBRELLA_ROOT not set (umbrella worktree path); run from the F3 harness")
    p = pathlib.Path(root) / ".harness" / "contracts" / "exocortex-hermes-webui.md"
    if not p.is_file():
        pytest.skip(f"contract not found at {p}")
    return p


SALA_EVENTS = ["sala_phase", "sala_artifact", "sala_gap", "sala_kanban", "sala_next_move",
               "sala_trace", "sala_draft", "sala_auth", "sala_interrupt", "sala_finding"]


def test_contract_declares_every_sala_event():
    text = _contract_path().read_text(encoding="utf-8")
    assert "### (g)" in text, "contract must define section (g)"
    missing = [e for e in SALA_EVENTS if e not in text]
    assert not missing, f"contract §(g) missing events: {missing}"
    # M8 / C-D: assert distinctive reconciliation markers written by THIS branch,
    # not substrings ('AG-UI', 'não') that already exist in the pre-(g) contract.
    assert "E9" in text and "AGUI_GATEWAY" in text, "contract §(g) must reconcile 'E9' vs the AGUI_GATEWAY surface"
