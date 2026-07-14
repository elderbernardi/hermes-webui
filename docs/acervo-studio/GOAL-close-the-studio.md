# GOAL prompt — close the Acervo Studio round (Phases 3–5 + go-live)

> Paste the block below into a fresh `/goal` session started in
> `/home/elder/projetos/projetob` (umbrella). It is self-contained: current state,
> scope, non-negotiable safety/governance rails, execution protocol, orientation,
> and definition of done. Written after Phases 0–2b shipped (2026-07-12).

---

```
GOAL: Close out the Acervo Studio (MOD-010) feature arc — build Phase 3 (Publish
outbound), Phase 4 (Assist & "ask the acervo"), and Phase 5 (Consolidate) at the
rigor of Phases 0–2b, leaving the Studio feature-complete and live-ready. Do NOT
reprovision, push to a production branch beyond the fork's own origin, or write to
the real acervo without an explicit owner OK — surface those as gates.

## Mission / role
You are the ORCHESTRATOR continuing "Acervo Studio" (MOD-010) in the hermes-webui
fork. Deliver the scope below phase-by-phase, driving each with
superpowers:subagent-driven-development (fresh implementer per task + per-task
review + a whole-branch review on the most capable model at the end of each phase).
Skill order per phase: brainstorming (only if design gaps) → writing-plans →
subagent-driven-development (or executing-plans) → requesting-code-review →
finishing-a-development-branch. One phase = one branch = one merge = one push.

## Current state (READ THE LEDGER FIRST)
- Full audit trail + every commit: `hermes-webui/.superpowers/sdd/progress.md`.
- Phases 0–2b are DONE, merged to `exocortex/stable`, and PUSHED to origin
  (`elderbernardi/hermes-webui`). `exocortex/stable` HEAD = merge `52daeee0` (Phase 2b).
- 2a = intake capture (text/link/file→`_inbox/incoming/{id}/`, base64-in-JSON, 14 MiB cap).
- 2b = the FIRST agent-mediated SEMANTIC write: triage (agent proposes a destination,
  read-only) + promote (agent crafts the page body, the SERVER writes deterministically
  via the `acervoctl` control plane, micro-scope only, propose-then-approve). Module:
  `api/acervo_studio_agent.py`. Routes: `x/intake/item/{triage,promote}`.
- The Hermes-invocation pattern is RESOLVED (`docs/acervo-studio/SPIKE-hermes-invocation.md`):
  sync in-process `run_conversation`; hybrid = agent proposes/crafts (cognition), server
  writes deterministically (control-plane CLI). Reuse this pattern for Phase 3/4.
- Known operational facts carried forward:
  * The excrtx control plane (`acervoctl.py`, guard, `acervo_semantic_core.py`) and the
    publish tools are NOT in `~/.hermes`. Runnable copies: control plane at
    `~/.exocortex-installer/scripts/`; publish tools at
    `~/exocortex/acervo/global/tools/artifact_publish.py` (also `~/.hermes/acervo/global/tools/`)
    + `~/exocortex/acervo/global/tools/harness/validate_artifact_manifest.py`.
  * `_acervo_root()` resolves `$ACERVO` → `$EXOCORTEX_HOME/acervo` → `~/exocortex/acervo`.
    ⚠️ An empty `$ACERVO` falls back to the REAL acervo, and the real `~/.hermes` profile
    OVERRIDES `$ACERVO` per request. For any write test, boot with a **fresh temp
    `HERMES_HOME`** + explicit `ACERVO=<fixture>` and VERIFY the write landed in the
    fixture before proceeding.
  * NOT reprovisioned: prod on :8787 (`~/.hermes/hermes-webui`) still serves Phase 1.

## Scope of THIS round (deliverables, in order)
1. **Phase 3 — Publish (outbound).** `x/publish/prepare` (assemble artifact + run
   `validate_artifact_manifest.py` = antislop/taste gate → {gate, drive_target,
   visibility_options}) and `x/publish` (confirm → `artifact_publish.py publish`,
   Draft-First enforced; public sharing needs an explicit approval flag → Drive receipt).
   Server shells out to the real CLIs (like promote shells to acervoctl). Note:
   `artifact_publish.py` hardcodes `visibility:"private"` and has NO `--public` — public
   share is an added approval step, not in the tool. Needs Google Drive creds in the
   runtime (provisioning concern; if absent, degrade with a clear "Drive não configurado").
2. **Phase 4 — Assist & "ask the acervo".** Inline, PROPOSAL-ONLY cognition
   (`x/assist {op: rewrite|summarize|suggest_tags|contradiction_check}` → server →
   Hermes tool-less `run_conversation` → proposal; applied edits to existing pages go
   through MOD-009 `x/save`, never a new write path). Plus semantic Q&A over the acervo
   ("ask the acervo") — reuse `acervoctl retrieve` or the existing `x/search`.
3. **Phase 5 — Consolidate.** Retire/redirect the MOD-009 docked panel now that the
   Studio reaches parity; a11y pass (roles/focus/labels); perf; an upstream-sync
   checkpoint note. Update the RFC §11 status.
4. **Provisioning readiness (surface, don't force).** Document + wire the
   `EXOCORTEX_SCRIPTS_DIR` (control plane) and Drive-creds requirements so a reprovisioned
   WebUI can actually run promote/publish live. Do NOT reprovision — leave a crisp
   go-live checklist for the owner.
5. **Consolidated live verification.** A single Playwright pass over the WHOLE Studio
   (capture → triage → promote → publish → assist) against a THROWAWAY fixture acervo +
   a creds-provisioned temp `HERMES_HOME` (so the agent is actually online). Report which
   flows were exercised live vs mocked.

## Non-negotiable constraints (put in EVERY task brief AND every reviewer prompt)
- SAFETY OF THE REAL ACERVO: every write test runs against a THROWAWAY fixture — NEVER
  `~/exocortex/acervo`. Boot fresh-`HERMES_HOME` + explicit `ACERVO=<fixture>` and verify
  the first write lands in the fixture. If a stray write reaches the real acervo, STOP,
  remove it, and report.
- GOVERNANCE RAILS: the GUI never writes semantic memory or calls cognition directly —
  Hermes does, server-mediated, PROPOSE-THEN-APPROVE. Semantic writes go ONLY through the
  sanctioned control plane (promote/acervoctl). Assist is proposal-only. Publish is
  Draft-First (private delivery ok; public link/share needs an explicit approval step).
  `.quarantine/` off-limits; every endpoint session-gated; micro-scope for semantic writes.
- REBASE-SAFETY: new behavior in NEW/fork-owned files. `api/routes.py` = **0 new lines**
  (reuse the `/api/acervo/x/` prefix dispatch → delegate from `handle_studio_{get,post}`).
  `static/index.html` minimal/0. NEVER edit `style.css`/`ui.js`/`workspace.js`/`acervo.js`/
  `acervo-explorer.*`. Assert the shared-file diff is EMPTY each phase.
- VANILLA ONLY: IIFE, `'use strict'`, no ES import/export (`npm run lint:runtime`).
  Namespaces `.axs-*` / `acervoStudio*` / `AXS`. All dynamic content `_esc`'d before innerHTML.
- OPERATIONAL STATES return HTTP 200 with `{ok:false, offline|error}` so the UI renders
  them calmly (the app's `api()` throws on non-2xx); keep 400/404 for malformed requests.
- GRACEFUL DEGRADATION: Hermes/Drive offline → assist/publish show a calm state; capture/
  browse/read/edit keep working; never leave a half-written/half-moved artifact.
- SUBPROCESS SAFETY: shell out list-form (no shell=True); validate any slug/nature/path
  component against `^[a-z0-9][a-z0-9-]*$` before it becomes an arg/path; encode YAML
  scalars with `json.dumps`.
- OWNER GATES (STOP and ask): reprovisioning `~/.hermes/hermes-webui`; any push beyond the
  fork's own `origin/exocortex/stable`; writing to the real acervo; enabling public Drive
  sharing; the umbrella push (BLOCKED — a pre-existing commit `d28175a` versioned an
  836 MB backup tarball that GitHub rejects; do not fight it, flag it).

## Execution protocol (per phase N ∈ {3,4,5})
1. `git -C hermes-webui checkout -b collab/acervo-studio-p<N> off exocortex/stable`.
2. If Phase 3/4 has a real invocation/tool unknown, do a short SPIKE first (append to
   `docs/acervo-studio/SPIKE-hermes-invocation.md`) and get sign-off before building the write.
3. writing-plans → `docs/acervo-studio/PLAN-phase<N>.md` (Phase-2 shape: file structure,
   bite-sized TDD steps with COMPLETE code + exact anchors, hermetic tests mirroring
   `tests/test_mod010_acervo_studio.py`: `_Handler` + `acervo` fixture + `jcap`/`session_ok`,
   mock the agent/CLI; a live Playwright pass against a FIXTURE at the end).
4. subagent-driven-development (cheapest model for complete-code transcription, standard
   for integration) OR executing-plans; per-task review; keep the ledger updated.
5. Whole-branch review on the most capable model (security/write-boundary lens on any new
   path input or CLI shell-out). Fix Critical/Important; triage Minors.
6. Verify: MOD-010 suite green; full pytest suite no NEW failures vs the ~16 pre-existing
   env-sensitive set (locales/skins/sessiondb-fd/openrouter/issue3957); `node --check` +
   `npm run lint:runtime`; rebase-safety diff EMPTY; live fixture E2E.
7. Governance: extend `EXOCRTX_MODIFICATIONS.md` (MOD-010 "Fase N"); umbrella COLLAB record
   `.harness/changes/YYYY-MM-DD_collab_hermes-webui-acervo-studio-phase<N>.md` + IDENTITY note.
8. finishing-a-development-branch → `--no-ff` merge to `exocortex/stable`, keep the branch
   as a record, then `git push origin exocortex/stable` (fork origin only). Do NOT reprovision.

## Orient (read, in this order)
1. `hermes-webui/.superpowers/sdd/progress.md` — the ledger (Phases 0–2b).
2. `hermes-webui/docs/rfcs/acervo-studio.md` — design spec (§6.1 publish/assist surface,
   §6.3 write boundary, §9 errors, §11 phases, §14 DoD checklist).
3. `hermes-webui/docs/acervo-studio/SPIKE-hermes-invocation.md` — the resolved invocation
   pattern + the promote spike (§Promote).
4. `hermes-webui/docs/acervo-studio/PLAN-phase2b.md` + `api/acervo_studio_agent.py` — the
   proven pattern (agent proposes/crafts, server writes via CLI) to mirror for publish.
5. `hermes-webui/EXOCRTX_MODIFICATIONS.md` (MOD-010 entries) and
   `.harness/subprojects/hermes-webui/IDENTITY.md`.
6. Publish tools: `~/exocortex/acervo/global/tools/artifact_publish.py` (init/publish/move)
   + `global/tools/harness/validate_artifact_manifest.py` (antislop<35 fails; skipped for draft).

## Definition of done for this round
Phases 3, 4, 5 each: merged to `exocortex/stable` + pushed to origin, with passing hermetic
tests + a live FIXTURE E2E, a clean whole-branch review, and governance (catalog + COLLAB +
IDENTITY) updated. The consolidated Studio E2E (capture→triage→promote→publish→assist) run
against a fixture with the agent online, reporting live-vs-mocked coverage. A crisp go-live
checklist left for the owner: `EXOCORTEX_SCRIPTS_DIR` + Drive creds + the reprovision step
(all owner-gated). The ledger + a fresh handoff note updated. Nothing reprovisioned; nothing
pushed beyond the fork origin; the real acervo untouched.

## Adjacent, owner-gated (surface; fold in ONLY if the owner asks)
- HW-1 upstream re-founding (Strategy C) incl. the latent terminal-RCE fix (`d257e5f3`+`34342b9f`)
  — its own focused session; see `EXOCRTX_MODIFICATIONS.md` "HW-1" + the security triage.
- Umbrella push is blocked by the 836 MB backup tarball in `d28175a` — flag, don't fight.
- Reprovision of :8787 to make the whole Studio live — owner decision after this round.
```

---

## Notes for the operator
- Scope is three phases; if you want a tighter round, narrow the GOAL to just **Phase 3 +
  the consolidated live E2E** (publish is the highest-value remaining feature and the
  natural human-check point).
- Every phase here still respects the same rails Phases 0–2b proved: fixture-only writes,
  rebase-safety, propose-then-approve, COLLAB records, no reprovision without the owner.
