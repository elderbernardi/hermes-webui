from api.sala_reducer import SalaState, PHASE_TO_COLUMN

def _st(): return SalaState("canvas_x", "task_x")

def test_phase_frame_emits_phase_and_kanban():
    out = _st().ingest({"kind": "phase", "phase": "act", "seq": 4})
    names = [n for n, _ in out]
    assert names == ["sala_phase", "sala_kanban"]
    phase_p = out[0][1]; kanban_p = out[1][1]
    assert phase_p == {"canvas_id": "canvas_x", "phase": "act", "seq": 4}
    assert kanban_p == {"canvas_id": "canvas_x", "task_id": "task_x", "column": PHASE_TO_COLUMN["act"]}

def test_artifact_frame_emits_sala_artifact_with_ops():
    out = _st().ingest({"kind": "artifact", "title": "Ofício v1", "atype": "markdown",
                        "path": "/x/oficio.md", "tool": "write_file"})
    assert len(out) == 1 and out[0][0] == "sala_artifact"
    p = out[0][1]
    assert p["ops"] == [{"op": "add", "path": "/artifacts/expected/-",
                         "value": {"title": "Ofício v1", "path": "/x/oficio.md", "type": "markdown"}}]

def test_next_move_frame():
    out = _st().ingest({"kind": "next_move", "text": "validar com o jurídico"})
    assert out == [("sala_next_move", {"canvas_id": "canvas_x", "text": "validar com o jurídico",
                    "ops": [{"op": "add", "path": "/next_moves/-", "value": "validar com o jurídico"}]})]

def test_trace_frame_intent():
    out = _st().ingest({"kind": "trace", "trace_kind": "intent", "title": "Renegociar prazo",
                        "evidence": {"event_id": "run1:3"}})
    assert out[0][0] == "sala_trace"
    p = out[0][1]
    assert p["kind"] == "intent" and p["verifiable"] is True and p["evidence"] == {"event_id": "run1:3"}
    assert p["ops"] == [{"op": "add", "path": "/assumptions/-", "value": "Renegociar prazo"}]

def test_unknown_frame_is_ignored():
    assert _st().ingest({"kind": "wat"}) == []

def test_verify_fail_interrupts_on_third_consecutive():
    st = _st()
    assert st.ingest({"kind": "verify", "subject": "test_a", "ok": False}) == []
    assert st.ingest({"kind": "verify", "subject": "test_a", "ok": False}) == []
    out = st.ingest({"kind": "verify", "subject": "test_a", "ok": False})
    assert out[0][0] == "sala_interrupt"
    p = out[0][1]
    assert p["klass"] == "verify_fail" and p["ops"] == [{"op": "add", "path": "/gaps/-", "value": p["hypothesis"]}]

def test_verify_success_resets_counter():
    st = _st()
    st.ingest({"kind": "verify", "subject": "test_a", "ok": False})
    st.ingest({"kind": "verify", "subject": "test_a", "ok": True})   # reset
    st.ingest({"kind": "verify", "subject": "test_a", "ok": False})
    out = st.ingest({"kind": "verify", "subject": "test_a", "ok": False})
    assert out == []   # only 2 fails since reset

def test_verify_fail_per_subject_isolated():
    st = _st()
    for _ in range(2): st.ingest({"kind": "verify", "subject": "a", "ok": False})
    assert st.ingest({"kind": "verify", "subject": "b", "ok": False}) == []  # b independent

def test_empty_search_gap_on_second():
    st = _st()
    assert st.ingest({"kind": "search", "query_sig": "sig1", "empty": True}) == []
    out = st.ingest({"kind": "search", "query_sig": "sig2", "empty": True})
    assert out[0][0] == "sala_gap" and out[0][1]["source"] == "empty_search"

def test_identical_signature_counts_as_empty():
    st = _st()
    st.ingest({"kind": "search", "query_sig": "same", "empty": False})   # baseline
    out = st.ingest({"kind": "search", "query_sig": "same", "empty": False})  # repeat -> empty#1... need 2
    # first repeat is empty#1 (dup of baseline), second repeat triggers gap
    out2 = st.ingest({"kind": "search", "query_sig": "same", "empty": False})
    assert out2[0][0] == "sala_gap"

def test_surprise_emits_finding_with_authority_order():
    out = _st().ingest({"kind": "surprise", "subject": "prazo", "code": "30d", "check": "45d", "spec": "60d"})
    assert out[0][0] == "sala_finding"
    assert out[0][1]["authority"] == ["executivo", "spec", "tests", "codigo"]

def test_clarify_frame_emits_gap():
    out = _st().ingest({"kind": "clarify", "clarify_id": "cl9", "session_id": "s9",
                        "question": "qual o prazo desejado?", "choices_offered": ["30d", "60d"]})
    assert out[0][0] == "sala_gap"
    p = out[0][1]
    assert p["source"] == "clarify" and p["clarify_id"] == "cl9" and p["session_id"] == "s9"
    assert p["choices_offered"] == ["30d", "60d"]
    assert p["ops"] == [{"op": "add", "path": "/gaps/-", "value": "qual o prazo desejado?"}]

def test_bound_interrupt_clarify_emits_interrupt_not_gap():
    out = _st().ingest({"kind": "clarify", "clarify_id": "b1", "session_id": "s1",
                        "question": "3 tentativas falharam", "bound_interrupt": True,
                        "hypothesis": "o schema mudou", "tried": "rodei o teste 3x", "output": "AssertionError"})
    assert out[0][0] == "sala_interrupt"
    p = out[0][1]
    assert p["klass"] == "verify_fail" and p["hypothesis"] == "o schema mudou"
    assert p["clarify_id"] == "b1" and p["ops"] == [{"op": "add", "path": "/gaps/-", "value": "o schema mudou"}]

def test_normal_clarify_still_emits_gap():
    out = _st().ingest({"kind": "clarify", "clarify_id": "n1", "question": "q?"})
    assert out[0][0] == "sala_gap"   # unchanged

def test_approval_frame_emits_draft():
    out = _st().ingest({"kind": "approval", "approval_id": "ap1", "session_id": "s1",
                        "action": "git push", "draft_text": "push da branch collab/x"})
    assert out[0][0] == "sala_draft"
    p = out[0][1]
    assert p["approval_id"] == "ap1" and p["action"] == "git push" and p["session_id"] == "s1"
    assert p["draft_text"] == "push da branch collab/x" and p["requires_auth"] is True

def test_conduct_declared_draft_has_no_approval_id():
    # the agent's own EX-08 declaration (via conduct {"t":"draft"}) carries no runtime approval_id
    out = _st().ingest({"kind": "approval", "approval_id": None, "session_id": "s2",
                        "action": "enviar e-mail", "draft_text": "para o diretor…"})
    assert out[0][0] == "sala_draft" and out[0][1]["approval_id"] is None


# ── fix-wave #5: HITL dedup by id (the SSE re-fires the head pending) ─────────
def test_clarify_deduped_by_id():
    st = _st()
    f = {"kind": "clarify", "clarify_id": "cl1", "question": "q?"}
    assert st.ingest(f)[0][0] == "sala_gap"    # first emits
    assert st.ingest(f) == []                  # re-fire of the same clarify_id -> no duplicate card


def test_approval_deduped_by_id_but_conduct_drafts_distinct():
    st = _st()
    a = {"kind": "approval", "approval_id": "ap1", "action": "x", "draft_text": "y"}
    assert st.ingest(a)[0][0] == "sala_draft"
    assert st.ingest(a) == []                  # same runtime approval_id -> no dup
    d = {"kind": "approval", "approval_id": None, "action": "z", "draft_text": "w"}
    assert st.ingest(d)[0][0] == "sala_draft"  # conduct-declared drafts (id=None) stay distinct
    assert st.ingest(d)[0][0] == "sala_draft"
