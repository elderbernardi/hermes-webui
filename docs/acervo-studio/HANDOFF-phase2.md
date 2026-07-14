# Acervo Studio — Handoff for the next session (post–Phase 1)

> Paste the block below into a **fresh** Claude Code session started in
> `/home/elder/projetos/projetob` (umbrella). Fill in `GOAL`. Phase 1 + 1.1 are
> DONE and merged locally to `exocortex/stable` (not pushed). The session should
> continue at the same rigor (subagent-driven-development → per-task review →
> whole-branch review → finishing-a-development-branch).

---

```
GOAL: <<< fill me — pick ONE >>>
# Examples:
#   "Ship Phase 1 live" (push exocortex/stable + reprovision the WebUI)
#   "Do the Phase-2 Hermes-invocation SPIKE and get owner sign-off, then stop"
#   "Complete Phase 2 (intake → triage → agent-mediated promote) after the spike"
#   "Fold the deferred Phase-1 Minors (M1/M2/M4) and the umbrella Phase-1.1 note"

## Mission
You are the ORCHESTRATOR continuing "Acervo Studio" (MOD-010) in the hermes-webui
fork. Deliver exactly the scope in GOAL at the rigor of Phases 0–1. Drive it with
superpowers:subagent-driven-development (fresh implementer per task + per-task
spec/quality review + a whole-branch review on the most capable model at the end).
Skill order: brainstorming (only if design gaps) → writing-plans →
subagent-driven-development → requesting-code-review → finishing-a-development-branch.

## Current state (2026-07-04) — READ THE LEDGER FIRST
- Full audit trail + every commit sha: `hermes-webui/.superpowers/sdd/progress.md`.
- Phase 1 COMPLETE & MERGED LOCAL: `collab/acervo-studio-p1` → `--no-ff` merge
  `d7d7245e` on `exocortex/stable`. 8 tasks: `GET /api/acervo/x/download`
  (read-only, symlink-hardened), inline OKF-preserving editor, kebab move/status,
  stage-to-chat, download, `_micro_title` harmonization, artifact-tree `kind`,
  and the 8 deferred Phase-0 minors.
- Phase 1.1 (post-merge UX) MERGED LOCAL: session auto-bind (`_ensureSession` in
  `static/acervo-studio.js`) → merge `7ad6010c`. The Studio no longer needs an
  open chat — it creates+binds a session on open (backend session-gate unchanged).
- The final whole-branch review (opus) caught + fixed two blockers the per-task
  reviews missed: editor silently downgraded out-of-set page `status` (`ae955af5`),
  and `x/raw` leaked `.quarantine`/`.git` via a clean-path symlink (`7001bc51`).
  Both live-verified.
- Verification at merge: `tests/test_mod010_acervo_studio.py` 32 green; full suite
  9142 pass / 16 fail (all pre-existing env-sensitive: turkish/zh_hant/verdigris/
  sessiondb-fd — none in acervo/MOD-010); `node --check` + `npm run lint:runtime`
  clean; 10/10 live browser E2E flows (fixture acervo); rebase-safety EMPTY
  (`api/routes.py` 0 new lines, `static/index.html` 0 new lines, all upstream/
  MOD-009 files byte-untouched).
- `exocortex/stable` is **14 commits ahead of `origin/exocortex/stable` — NOT
  pushed**, and the provisioned instance `~/.hermes/hermes-webui/` is **NOT
  reprovisioned** (still Phase 0). Branches `collab/acervo-studio-p1` and
  `fix/acervo-studio-session-autobind` are kept as records.
- Umbrella governance (separate repo, branch `collab/matriz-cnpj-consolidation`,
  also NOT pushed): COLLAB record
  `.harness/changes/2026-07-03_collab_hermes-webui-acervo-studio-phase1.md` +
  IDENTITY updated (`cf714188`).

## Open loose ends (address per GOAL)
1. **Ship Phase 1 live** (ops): `git -C hermes-webui push origin exocortex/stable`
   then reprovision via `exocortex.saas/setup/step-10b-hermes-webui.sh` /
   `exocortex.saas/provision/hermes-webui`, and verify on the live instance.
   This puts the fork's FIRST write-capable acervo surface live — treat as a
   deliberate, owner-approved step. Get explicit go-ahead before pushing.
2. **Deferred Phase-1 Minors** (all Low, triaged to a later phase — see ledger):
   M1 `_download_artifact_zip` zip-loop `except…pass` has no `logger.warning`;
   M2 the artifact-zip response omits `X-Content-Type-Options: nosniff`;
   M4 `_toggleMenu` leaks one self-healing `document` click-listener when the
   menu is dismissed by selecting an item.
3. **Umbrella COLLAB record** does not yet mention Phase 1.1 (session auto-bind).
   Add a one-line note if you want a complete audit trail.

## Phase 2 (Intake — AI-native inbound) — GATED: do the SPIKE FIRST
Phase 2 is the first phase that needs the agent. BEFORE any Phase-2 UI, resolve
RFC §6.2 risk #1 — the **Hermes invocation mechanism**: can the SERVER run a
structured agent turn and get a structured proposal synchronously, or is it async
(job + poll)? Evaluate `api/agent_sessions.py`, `mcp_server.py`, `bootstrap.py`,
and how excrtx-memory-intake's IntakeEnvelope contract (`POST /v1/intake/*`) is
meant to be driven. Write `docs/acervo-studio/SPIKE-hermes-invocation.md` and get
owner sign-off on the pattern before building Phase-2 UI — the whole Phase-2/3/4
UX (inline vs progress) depends on this answer. Phase 2 flow (post-spike):
upload/text/link → `_inbox/incoming`; Hermes triage proposal; agent-mediated
promote via excrtx-memory-manager (propose-then-approve; the GUI NEVER writes
semantic memory or calls cognition directly — Hermes does, server-mediated).

## Orient (read, in this order)
1. `hermes-webui/docs/acervo-studio/HANDOFF-NEXT-PHASES.md` — the full phases §11
   map + non-negotiable constraints + execution protocol (still current for
   Phases 2–5; this file only updates the "state" to post–Phase 1).
2. `hermes-webui/docs/rfcs/acervo-studio.md` — design spec (§6 backend, §6.2 AI
   mediation, §6.3 write boundary, §9 errors, §8 coexistence, §11 phases).
3. `hermes-webui/docs/acervo-studio/PLAN-phase1.md` — copy this plan's shape/rigor.
4. `hermes-webui/.superpowers/sdd/progress.md` — the SDD ledger (Phase 0 + 1 + 1.1).
5. `hermes-webui/EXOCRTX_MODIFICATIONS.md` (MOD-009 + MOD-010 entries) and
   `.harness/subprojects/hermes-webui/IDENTITY.md`.

## Non-negotiable constraints (put in EVERY task brief AND every reviewer prompt)
- REBASE-SAFETY: new behavior in NEW files. `api/routes.py` = 0 new lines
  (reuse the `/api/acervo/x/` prefix dispatch; new endpoints delegate from
  `acervo_explorer`'s dispatcher into `api/acervo_studio.py` / a new
  `api/acervo_studio_agent.py` per RFC §6). `static/index.html` minimal. NEVER
  edit `style.css` / `ui.js` / `workspace.js` / `acervo.js` / `acervo-explorer.*`.
  (`api/acervo_explorer.py` is fork-owned → small additive edits only.)
- VANILLA ONLY: IIFE, `'use strict'`, no ES import/export (`npm run lint:runtime`
  enforces). Namespaces `.axs-*` / `acervoStudio*` / `AXS` (never MOD-009's
  `.ax-*` / `AX` / `acervoExplorer*`).
- GOVERNANCE RAILS (Phase 2+, WRITE-coupling → COLLAB): server-mediated,
  propose-then-approve, via excrtx-memory-manager; uploads land in `_inbox`;
  `.quarantine/` off-limits; OKF preservation; Draft-First for publish; path
  safety via `_safe_acervo_path` + a resolved-dot guard for any NEW read/serve
  path (see the x/raw fix `7001bc51`); every endpoint session-gated.
- GRACEFUL DEGRADATION: with Hermes offline, nav/read/edit/download must still
  work; triage/assist/promote show a calm "agente offline", never block.
- TESTS: hermetic pytest (mirror `tests/test_mod010_acervo_studio.py`) + a live
  Playwright E2E pass per phase against a THROWAWAY fixture acervo (Phase 2+
  writes — NEVER the real `~/exocortex/acervo`). Whole-branch review with a
  security lens on any new user-supplied path input.

## Execution protocol
1. Branch per phase: `git -C hermes-webui checkout -b collab/acervo-studio-p<N>`
   off `exocortex/stable`.
2. writing-plans → `docs/acervo-studio/PLAN-phase<N>.md` (Phase-0/1 shape: file
   structure, bite-sized TDD steps with COMPLETE code + exact anchors, self-review).
3. subagent-driven-development: cheapest model for complete-code transcription,
   standard for integration; per-task spec+quality review; fix loops; keep the
   ledger `.superpowers/sdd/progress.md` updated.
4. Whole-branch review on the most capable model. Fix Critical/Important; triage
   Minors into the ledger for the final review.
5. Governance: extend `EXOCRTX_MODIFICATIONS.md`; update the umbrella
   `.harness/subprojects/hermes-webui/IDENTITY.md`; new COLLAB change record in
   `.harness/changes/` (Phase 2+ are WRITE-coupling → definitely COLLAB).
6. finishing-a-development-branch → merge `--no-ff` to `exocortex/stable` locally.
   Do NOT push and do NOT reprovision unless the owner asks.
7. End with an updated ledger + a fresh handoff note for the next phase.

## Local test instance (nothing is running now)
From `hermes-webui` (prod 8787 is down):
```
# SAFE (writes hit a fixture) — build a throwaway acervo first (see PLAN-phase1 Task 7 Step 1), then:
HERMES_HOME="$(mktemp -d)" ACERVO="$FIXTURE" HERMES_WEBUI_PORT=8799 .venv/bin/python server.py --port 8799
# REAL content (⚠️ Editar/Salvar/Mover/Status WRITE to real files):
HERMES_HOME="$(mktemp -d)" ACERVO="$HOME/exocortex/acervo" HERMES_WEBUI_PORT=8799 .venv/bin/python server.py --port 8799
```
Open http://localhost:8799 → bottom-right **▤ Acervo** (auto-binds a session now,
so it loads without opening a chat). `_acervo_root()` resolves `$ACERVO` →
`$EXOCORTEX_HOME/acervo` → `~/exocortex/acervo`; the Studio path root is ALWAYS
`_acervo_root()`, never the chat session's workspace.

## Definition of done for this run
The scope in GOAL delivered at Phase-0/1 rigor: passing hermetic tests + a live
E2E pass, a clean whole-branch review, governance docs updated, and the ledger +
next handoff note written. For a "ship" GOAL: pushed + reprovisioned + verified
live, with explicit owner go-ahead recorded.
```

---

## Notes for the operator
- **Scope `GOAL` to one thing per run.** "Ship Phase 1" and "Build Phase 2" are
  different sessions; the spike is its own natural stopping point for a human check.
- Phase 2 is the **first write-coupling of the intake surface** — treat as COLLAB
  with its own change record, and keep the propose-then-approve gate visible.
- If you only want to exercise Phase-1 writes safely against real-looking data,
  run the server against an `rsync` snapshot of `~/exocortex/acervo`, not the live one.
