# Acervo Studio — Next-Phases Handoff (multi-agent execution prompt)

> Paste the block below into a **fresh** Claude Code session (or pass `goal` as
> `args.goal` to a Workflow). Fill in `GOAL`. The session orchestrates the work
> multi-agent (subagent-driven), at the same rigor Phase 0 was built.

---

```
GOAL: <<< fill me >>>
# Examples:
#   "Complete Phase 1 (edit + download + chat-bridge)"
#   "Complete Phases 1–2 (edit/download, then intake→triage→promote)"
#   "Complete all remaining phases 1–5"
#   "Do only the Phase-2 Hermes-invocation spike and report"

## Mission
You are the ORCHESTRATOR continuing the "Acervo Studio" (MOD-010) inside the
hermes-webui project. Deliver exactly the scope named in GOAL, at the rigor of
Phase 0. Do NOT hand-write it all yourself — drive it with
superpowers:subagent-driven-development (fresh implementer subagent per task +
per-task spec/quality review + a whole-branch review at the end). Skill order:
brainstorming (only if design gaps) → writing-plans → subagent-driven-development
→ requesting-code-review → finishing-a-development-branch.

## Orient first (read, in this order)
1. hermes-webui/docs/rfcs/acervo-studio.md — the design spec / north star.
   Phases §11, backend surface §6, AI mediation §6.2, write boundary §6.3,
   error handling §9, coexistence/rebase-safety §8, identity/themes §5.2.
2. hermes-webui/docs/acervo-studio/PLAN-phase0.md — COPY this plan's shape/rigor
   (bite-sized TDD tasks, complete code, exact anchors, self-review).
3. hermes-webui/.superpowers/sdd/progress.md — the Phase 0 SDD ledger: what's
   done, and 8 Minor findings deferred to Phase 1 (fix them opportunistically).
4. hermes-webui/EXOCRTX_MODIFICATIONS.md — MOD-009 + MOD-010 entries (the fork's
   coexistence catalog + rebase guidance).
5. Code you extend: hermes-webui/api/acervo_explorer.py,
   hermes-webui/static/acervo-studio.{js,css}, hermes-webui/static/index.html.
6. Acervo philosophy (for Phases 2–4): ~/exocortex/acervo (scopes, 11 natures,
   OKF frontmatter, _inbox/{incoming,processing,promoted}, _artifacts) and
   exocortex.saas skills excrtx-memory-{manager,intake}, excrtx-produce-artifacts,
   plus ~/exocortex/acervo/global/tools/{artifact_publish.py,validate_artifact_manifest.py}.

## Current state (Phase 0 — DONE, merged to exocortex/stable, NOT pushed)
Read-only full-screen Studio: unified navigator (Soul/Global/Shared/Microversos/
Artefatos/Inbox), reader (frontmatter chips + renderMd + sandboxed non-md preview),
command-bar search, Chat⇄Acervo toggle, Graphite-dark + current-web-ui-light themes.
Backend: `scope=micro`/`scope=inbox` added to `handle_tree` in acervo_explorer.py
(0 routes.py lines). Frontend: static/acervo-studio.{js,css} (IIFE, `.axs-*` /
`AXS` / `acervoStudio*` namespaces), 3 index.html lines. E2E-verified; micro-slug
path-traversal fixed via `_safe_acervo_path`.

## Remaining phases (RFC §11) — implement the slice in GOAL
- Phase 1 — Edit & download & bridge: wire the EXISTING MOD-009 write endpoints
  (`/api/acervo/x/{save,tags,status,move}`) into a Studio editor; download
  (md/raw/zip); stage-to-chat via the session pending-context bridge
  (`/api/acervo/x/stage`). NO agent dependency.
- Phase 2 — Intake (AI-native inbound): upload/text/link → `_inbox/incoming`;
  Hermes triage proposal; agent-mediated promote via excrtx-memory-manager.
  ⚠️ GATED by the Hermes-invocation spike below.
- Phase 3 — Publish (outbound): prepare → quality gate (antislop/taste via
  validate_artifact_manifest.py) → Draft-First → artifact_publish.py → Drive receipt.
- Phase 4 — Assist & "ask the acervo": inline rewrite/summarize/suggest-tags/
  contradiction-check (server→Hermes, proposal-only); semantic Q&A.
- Phase 5 — Consolidate: retire/redirect the MOD-009 docked panel; a11y; perf;
  upstream cherry-pick checkpoint.

## Non-negotiable constraints (put in EVERY task brief and EVERY reviewer prompt)
- REBASE-SAFETY: new behavior in NEW files. `api/routes.py` = 0 new lines
  (reuse the existing `/api/acervo/x/` prefix dispatch; new endpoints delegate
  from acervo_explorer's dispatcher, or add `api/acervo_studio.py` +
  `api/acervo_studio_agent.py` per RFC §6). `static/index.html` minimal. NEVER
  edit style.css / ui.js / workspace.js / acervo-explorer.*.
- VANILLA ONLY: IIFE, 'use strict', no ES import/export (`npm run lint:runtime`
  enforces). Namespaces `.axs-*` / `acervoStudio*` / `AXS` (never collide with
  MOD-009's `.ax-*` / `AX` / `acervoExplorer*`). (Framework-island reassessed at
  Phase 2 only — see RFC §5.2/§8; default stays vanilla.)
- GOVERNANCE RAILS (Phases 2+): the GUI NEVER writes semantic memory directly or
  calls cognition directly — Hermes does, SERVER-MEDIATED, PROPOSE-THEN-APPROVE,
  via excrtx-memory-manager. Uploads land in `_inbox` (input is not memory).
  `.quarantine/` off-limits. OKF preservation (merge existing frontmatter, bump
  only present timestamps). Draft-First for publish (private=delivery; public
  sharing needs explicit approval). Path safety via `_safe_acervo_path`. Every
  endpoint session-gated. Read-only edit boundary of MOD-009 unchanged (no
  delete, no direct create — new pages only via agent-mediated intake promote).
- GRACEFUL DEGRADATION: with Hermes offline, nav/read/edit/download must still
  work; triage/assist/promote show a calm "agente offline", never block.
- TESTS: hermetic pytest (mirror tests/test_mod010_acervo_studio.py — monkeypatch
  `api.routes._acervo_root` onto a tmp_path acervo). Vanilla JS: node --check +
  `npm run lint:runtime` + a live Playwright E2E pass per phase. Full suite: no
  NEW failures vs the pre-existing env-sensitive set (~30 local: live-server/
  locale/skin/git — not caused by our diff).

## Phase-2 prerequisite SPIKE (do FIRST if GOAL includes Phase 2)
Resolve RFC §6.2 risk #1 — the Hermes invocation mechanism: can the SERVER run a
structured agent turn and get a structured proposal synchronously, or is it
async (job + poll)? Evaluate api/agent_sessions.py, mcp_server.py, bootstrap.py,
and how excrtx-memory-intake's IntakeEnvelope contract (POST /v1/intake/*) is
meant to be driven. Write a short spike note to docs/acervo-studio/SPIKE-hermes-
invocation.md and get owner sign-off on the pattern BEFORE building Phase-2 UI.
The whole Phase-2/3/4 UX (inline vs progress) depends on this answer.

## Execution protocol
1. Branch per phase: `git -C hermes-webui checkout -b collab/acervo-studio-p<N>`
   off `exocortex/stable`.
2. writing-plans → docs/acervo-studio/PLAN-phase<N>.md (same shape as Phase 0:
   file structure, bite-sized TDD steps with COMPLETE code, exact anchors, no
   placeholders, self-review). Backend-first (pytest) then frontend (E2E).
3. subagent-driven-development: fresh implementer per task (pick model by task
   complexity — cheapest for complete-code transcription, standard for
   integration), per-task review (spec + quality), fix loops, ledger updates in
   .superpowers/sdd/progress.md. Defer browser E2E to a consolidated Playwright
   pass you run after each phase's UI lands.
4. Whole-branch review on the most capable model. Fix Critical/Important; triage
   Minors. (Note: Phase-0's whole-branch review caught a real path-traversal the
   per-task reviews missed — keep a security lens on any new user-supplied path
   input.)
5. Governance: extend EXOCRTX_MODIFICATIONS.md; update .harness/subprojects/
   hermes-webui/IDENTITY.md; write a fresh COLLAB change record in
   .harness/changes/ (Phases 2+ are WRITE-coupling → definitely COLLAB).
6. finishing-a-development-branch → merge to exocortex/stable locally (--no-ff),
   like Phase 0. Do NOT push and do NOT reprovision unless the owner asks.
7. End with an updated ledger + a one-page handoff note for the next phase.

## Local test instance
From hermes-webui (production 8787 may be down):
`HERMES_HOME="$(mktemp -d)" ACERVO="$HOME/exocortex/acervo" HERMES_WEBUI_PORT=8799 .venv/bin/python server.py --port 8799`
The session store is shared: pick a real conversation in the sidebar to bind
`S.session`, then click the bottom-right `▤ Acervo` launcher. `POST
/api/session/new` returns `{"session":{"session_id":...}}`. Studio is read-only
so it can't corrupt acervo data.

## Definition of done for this run
`collab/acervo-studio-p<N>` merged to exocortex/stable implementing GOAL, with
passing hermetic tests + a live E2E pass, a clean whole-branch review, governance
docs updated, and the ledger + next-phase handoff note written.
```

---

## Notes for the operator
- **Scope `GOAL` to one phase per run** for tightest review loops; Phase 2 is the
  natural stopping point to check the AI-mediation UX with a human.
- Phase 2+ introduce the **first WRITE-coupling** of this surface — treat each as
  a COLLAB change with its own record, and keep the propose-then-approve gate
  visible in the UI.
- The 8 deferred Phase-0 Minors (in the ledger) are cheap to fold into Phase 1:
  shared microverse-title helper, a `handle_tree` HTTP-dispatch test, `_root()`
  null-guards on the 3 window-exposed fns, iframe `title`, `.axs-sub` styling.
