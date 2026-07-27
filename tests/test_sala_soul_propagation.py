import os, subprocess, pathlib, pytest

# M7: resolve everything from env; skip cleanly when the harness/venv isn't present
# (no committed machine-specific literals, no invalid <placeholder> Python).
HERMES_AGENT = os.environ.get("HERMES_AGENT_HOME", os.path.expanduser("~/.hermes/hermes-agent"))
HERMES_AGENT_PY = os.path.join(HERMES_AGENT, "venv", "bin", "python")
SOUL_SEED = pathlib.Path(os.environ.get("SOUL_SEED_PATH", ""))

# The launched session loads SOUL via load_soul_md(context_length) — the model's
# resolved context window — NOT no-arg (agent/system_prompt.py:189 -> _ctx_len;
# agent/prompt_builder.py:2071). A no-arg call hits the 20K floor
# (_dynamic_context_file_max_chars), whose 0.7/0.2 head/tail truncation drops the
# mid-file "## Conduct Bounds"/"## Conduct Loop" block — a state the real launch
# never reaches. So mirror the launch: pass the model window. Default = DeepSeek's
# documented window (the launched Sala model; the runtime's own fallback #9 is even
# larger at 256K). Override to pin the exact deployed model's window. This is not a
# machine-specific literal — it is the model's context window, same kind of constant
# as prompt_builder.CONTEXT_FILE_MAX_CHARS.
LAUNCHED_CONTEXT_LENGTH = int(os.environ.get("SALA_MODEL_CONTEXT_LENGTH", "128000"))

def test_loaded_soul_contains_conduct_rules(tmp_path):
    if not SOUL_SEED.is_file():
        pytest.skip("SOUL_SEED_PATH not set to the compiled SOUL_SEED.md")
    if not os.path.exists(HERMES_AGENT_PY):
        pytest.skip(f"hermes-agent venv not found at {HERMES_AGENT_PY}")
    home = tmp_path / "hermes-home"; home.mkdir()
    (home / "SOUL.md").write_text(SOUL_SEED.read_text(encoding="utf-8"), encoding="utf-8")
    # call the EXACT runtime loader the launched session uses (pure file read, no key),
    # WITH the context window the launch passes it (load_soul_md(context_length)).
    code = ("import os,sys; os.environ['HERMES_HOME']=sys.argv[1];"
            "sys.path.insert(0, sys.argv[2]);"
            "from run_agent import load_soul_md; s=load_soul_md(int(sys.argv[3])) or '';"
            "print('LOOP' if '## Conduct Loop' in s else 'NO-LOOP');"
            "print('BOUNDS' if '## Conduct Bounds' in s else 'NO-BOUNDS');"
            # C-S1: the TAIL of the block-scalar rule must survive compile, not just the header
            "print('TAIL' if 'NEVER narrate' in s else 'NO-TAIL')")
    out = subprocess.run(
        [HERMES_AGENT_PY, "-c", code, str(home), HERMES_AGENT, str(LAUNCHED_CONTEXT_LENGTH)],
        capture_output=True, text=True)
    # line-anchored: bare 'in' would let 'NO-LOOP'/'NO-BOUNDS'/'NO-TAIL' false-green
    # via substring — anchoring on the leading newline pins the exact positive token.
    lines = "\n" + out.stdout
    assert "\nLOOP" in lines and "\nBOUNDS" in lines, out.stderr[-400:]
    assert "\nTAIL" in lines, "conduct-loop compiled_rules truncated (not a block scalar?) — C-S1"
