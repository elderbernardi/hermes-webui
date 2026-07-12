# Acervo Studio — Phase 2b (Intake Triage + Promote) Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development
> or superpowers:executing-plans. Steps use `- [ ]`.
> **Status: DRAFT — GATED on Task 0 (promote-invocation spike) + owner sign-off on the
> propose-then-approve flow.** This is the first **agent-mediated semantic write** →
> COLLAB. Do not build Task 3 (promote) before Task 0 resolves how the server drives a
> tool-enabled agent turn.

**Goal:** Turn a captured `_inbox/incoming/{id}/` envelope into (a) a Hermes **triage
proposal** (where should this go?) rendered inline, and (b) on owner approval, an
**agent-mediated promotion** into semantic memory via `excrtx-memory-manager`, moving the
envelope to `_inbox/promoted/`.

**Architecture (from the resolved spike `SPIKE-hermes-invocation.md`):** sync in-process
invocation. New `api/acervo_studio_agent.py` mediates `USER → GUI → SERVER → HERMES`. The
GUI never writes semantic memory or calls cognition directly. Triage is a **read-only**
structured call (no tools). Promote is a **tool-enabled** agent turn that runs the
sanctioned `excrtx-memory-manager` write path. Both degrade gracefully when Hermes is
offline (calm "agente offline", capture/browse still work).

**Tech Stack:** Python 3 stdlib + `from run_agent import AIAgent` (in-process);
pytest with a **mocked agent** for hermetic tests; live E2E against a **THROWAWAY fixture
acervo** + a real Hermes runtime (never the real `~/exocortex/acervo`).

## Global Constraints

- **COLLAB / governance rails (non-negotiable):** GUI never writes semantic memory or calls
  cognition directly — Hermes does, **server-mediated, propose-then-approve**, via
  `excrtx-memory-manager` (the only sanctioned semantic-write path; enforces scope guard +
  OKF frontmatter + ADR-016 deprecate hook). Uploads/inbox stay operational (input ≠ memory).
  `.quarantine/` off-limits. Draft-First for any later publish. Every endpoint session-gated.
- **REBASE-SAFETY:** new file `api/acervo_studio_agent.py`; triage/promote routes delegate
  from `handle_studio_{get,post}`. **0 new `routes.py` / `index.html` lines.** New frontend
  in the existing `.axs-*` IIFE only.
- **NEVER test promote against the real acervo.** Hermetic = mocked agent + `tmp_path`;
  live E2E = fixture acervo + a disposable Hermes home.
- **Invocation primitive (spike-confirmed):** triage = `AIAgent(..., enabled_toolsets=[])`
  + `run_conversation(user_message, system_message, conversation_history=[], task_id=…)`
  → parse `final_response` as JSON (like `_llm_git_commit_message`, routes.py:15561-15577).

---

## Task 0 — SPIKE: how does the server drive a tool-enabled agent turn to run `excrtx-memory-manager`? (GATES Task 3)

The main spike resolved triage (read-only text→JSON). **Promote is unresolved:** it needs
the in-process agent to actually *execute a skill and write files* (tools enabled), against
the fixture acervo, and return a structured result. Open questions to answer by reading
`run_agent.py` / `api/streaming.py` (`_run_agent_streaming`) / `bootstrap.py` and the
`excrtx-memory-manager` skill:

- Can `run_conversation` run with **tools enabled** (non-empty `enabled_toolsets`) from a
  server route the way `_llm_git_commit_message` runs it tool-less? What `enabled_toolsets`
  / config makes the exocortex skills (`excrtx-memory-manager`) available?
- Does the agent turn need the acervo scope context (active microverso, `EXOCORTEX_HOME`,
  the scope guard `exocortex_runtime_guard.py`)? How is that passed for a fixture acervo?
- Is a single `run_conversation("promote intake X to micro/Y per excrtx-memory-manager…")`
  turn enough, or is `acervoctl.py prepare-write`/`commit-write` (if provisioned) a more
  deterministic path? (Spike found acervoctl is source-repo-only, not provisioned → default
  is the agent turn.)
- What's the smallest reliable structured contract for the promote result (created path,
  scope, nature, status) so the UI can confirm?

**Deliverable:** append findings to `SPIKE-hermes-invocation.md` (§Promote) + a recommended
promote-invocation pattern. **Get owner sign-off before Task 3.** If a tool-enabled server
turn is not cleanly feasible, fall back to "open in chat" (visible agent turn) for promote.

---

## Task 1 — `api/acervo_studio_agent.py`: the mediation layer + triage

**Files:** create `api/acervo_studio_agent.py`; test `tests/test_mod010_acervo_studio.py`.

- `propose_triage(root, iid, *, session) -> dict` — read the envelope
  (`acervo_studio._read_envelope`) + its `original/` content (bounded), build a
  JSON-proposal prompt (candidate scope ∈ macro/global/shared/micro, slug, nature, title,
  a one-line rationale, `keep_in_inbox` option), run a **tool-less** `run_conversation`,
  parse `final_response` as JSON, validate the shape, and return
  `{ok, proposal|None, offline?}`. Mirror `_llm_git_commit_message`'s provider/runtime
  resolution (profile env, `resolve_model_provider`, aux client fallback).
- Graceful offline: catch `ImportError`/agent-unavailable (`AIAgent is None`) →
  `{ok: False, offline: True}` (never raise into the route).
- **Hermetic test:** monkeypatch `acervo_studio_agent._run_agent_json` to return a canned
  proposal → assert `propose_triage` shape; monkeypatch it to raise → assert `offline`.
  Persist the proposal into the envelope as `routing.json` (so re-open shows the last proposal).

## Task 2 — Triage route: `POST x/intake/item/triage`

Delegate from `handle_studio_post`. Body `{session_id, id}`. Session-gated + `_valid_intake_id`.
Calls `acervo_studio_agent.propose_triage`, writes `routing.json`, returns
`{ok, proposal}` or `{ok:false, offline:true}`. Hermetic tests: happy path (mocked agent),
offline path (503-ish JSON, not a crash), bad id → 400.

## Task 3 — Promote route: `POST x/intake/item/promote` (GATED on Task 0)

Body `{session_id, id, routing}` (the approved scope/nature/title). Session-gated. Calls
`acervo_studio_agent.promote(root, iid, routing, session=…)` which runs the **tool-enabled**
agent turn per Task 0's pattern to write the page via `excrtx-memory-manager`, then moves
`_inbox/incoming/{id}` → `_inbox/promoted/{id}`. Returns `{ok, created_path}` or
`{ok:false, offline:true}`/error. **Propose-then-approve:** the route requires an explicit
`routing` payload the owner confirmed in the UI; the server never auto-promotes.
Hermetic tests (mocked agent write): envelope moves to `promoted/`, created_path returned;
offline → envelope stays in `incoming/`, calm error; `.quarantine`/dot targets rejected.

## Task 4 — Frontend: triage proposal card + promote confirm (assistant panel)

In the envelope detail view (`acervoStudioOpenEnvelope`): a "Triar" button → POST triage →
render the proposal inline (scope/nature/title + rationale) as an editable form; a
"Promover" button (disabled until a proposal exists) → POST promote with the (possibly
edited) routing → on success show the created page + link into it; on `offline` show the
calm "agente offline — tente novamente". Keep the propose-then-approve gate visible: nothing
is written until the owner clicks Promover. `.axs-*` namespace; all dynamic content `_esc`'d.

## Task 5 — Live E2E + governance

Fixture acervo + a disposable Hermes home with the exocortex skills. Drive: capture → triage
(proposal renders) → edit routing → promote (page appears in micro/…; envelope in promoted/).
Verify Hermes-offline degradation. Then: EXOCRTX_MODIFICATIONS MOD-010 "Fase 2b" row; umbrella
COLLAB record `.harness/changes/YYYY-MM-DD_collab_hermes-webui-acervo-studio-phase2b.md` +
IDENTITY note; rebase-safety EMPTY assertion; full-suite baseline.

---

## Open decisions for owner sign-off (before Task 3)

1. **Promote invocation** (Task 0 outcome): tool-enabled in-process `run_conversation` running
   `excrtx-memory-manager` (recommended if feasible) vs. "open in chat" visible turn (fallback).
2. **Promote visibility** (RFC §13 #3): background structured call by default, "abrir no chat"
   for complex cases (RFC + spike recommendation) — confirm.
3. **Scope of Phase 2b:** triage + promote only. Publish (Phase 3) and assist (Phase 4) remain separate.
