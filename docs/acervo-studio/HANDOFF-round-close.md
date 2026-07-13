# Acervo Studio (MOD-010) — round-close handoff (2026-07-12)

The Studio feature arc is **complete**. Phases 0–5 are built, reviewed, merged to
`exocortex/stable`, and **pushed to the fork origin** (`elderbernardi/hermes-webui`).
Nothing was reprovisioned; the real acervo was never written; the umbrella push stays
blocked. Below is what shipped this round and what remains (all owner-gated).

## What shipped this round (Phases 3–5)

| Phase | What | Merge on `exocortex/stable` |
|---|---|---|
| **3 — Publish outbound** | `x/publish/prepare` (quality gate) + `x/publish` (Draft-First → Drive SHA-256 receipt); deterministic shell-out to the real `artifact_publish.py` + `validate_artifact_manifest.py`; public share owner-gated. | `27596c43` |
| **4 — Assist + Ask** | `x/assist` (rewrite/summarize/suggest_tags/contradiction, proposal-only; apply via the existing editor + `x/save`) + `x/ask` ("ask the acervo": bounded in-process retrieval → grounded answer, sources subset-validated). | `2cb0de86` |
| **5 — Consolidate** | Retire/redirect the MOD-009 docked panel (from the fork-owned `acervo-studio.js`, MOD-009 byte-untouched); a11y pass (dialog role, Escape, focus, keyboard nav); perf check; docs. | `b2aed98f` |

Head of `exocortex/stable` (local == origin): **`b2aed98f`**.

## Quality bar met each phase
- Hermetic tests: `tests/test_mod010_acervo_studio.py` = **154 green** (Phase 3 added 39,
  Phase 4 added 33, Phase 5 = FE+docs unchanged).
- Whole-branch review (opus) each phase: Phase 3 closed 1 Important + 2 Minor; Phase 4
  closed 2 Important; Phase 5's agent hit the Anthropic session limit → self-reviewed
  (1 idempotency hardening). All the same "integration-only" bug class the earlier phases
  taught us to hunt.
- Rebase-safety EMPTY every phase (`routes.py`/`index.html`/`style.css`/`ui.js`/
  `workspace.js`/`acervo.js`/`acervo-explorer.*` byte-untouched). Vanilla lint clean.
- Live FIXTURE E2E each phase + a consolidated whole-Studio pass. Reports in
  `.superpowers/sdd/e2e-report-phase{3,4,5}.md` + `e2e-report-consolidated.md`.

## Governance recorded
- `EXOCRTX_MODIFICATIONS.md` MOD-010 "Fase 3/4/5" (hermes-webui, pushed).
- Umbrella COLLAB records `.harness/changes/2026-07-12_collab_hermes-webui-acervo-studio-phase{3,4,5}.md`
  + IDENTITY note — committed **locally on `master`**, **NOT pushed** (umbrella push is
  blocked by a pre-existing 836 MB backup tarball in commit `d28175a` that GitHub rejects).

## Remaining — all OWNER-GATED (see docs/acervo-studio/GO-LIVE-CHECKLIST.md)
1. **Go-live / reprovision.** The running `~/.hermes/hermes-webui/` on :8787 still serves
   **Phase 1**. To go live: `git -C ~/.hermes/hermes-webui merge --ff-only origin/exocortex/stable`
   + `ctl.sh restart`. ⚠️ :8787 serves the REAL acervo **unauthenticated** — confirm the
   owner accepts the write/agent surface there (or add auth) first.
2. **Gate A (promote):** set `EXOCORTEX_SCRIPTS_DIR` in the runtime → the `acervoctl`
   control plane. **Verified working** in the consolidated E2E (`~/.exocortex-installer/scripts`).
3. **Gate B (publish):** provision Google Drive creds (`google_api.py` + auth). Until then
   publish degrades to "Drive não configurado".
4. **Gate C (assist/ask/triage):** provider creds + a reachable LLM endpoint. The endpoint
   was intermittent during this round; features degrade calmly to "agente offline".
5. **Umbrella push** — blocked by the 836 MB tarball in `d28175a`. Flag, don't fight.
6. **HW-1 upstream re-founding (Strategy C)** incl. the latent terminal-RCE fix — its own
   focused session; see `EXOCRTX_MODIFICATIONS.md` "HW-1".

## If you pick this up next
- Read `.superpowers/sdd/progress.md` (the full ledger, Phases 0–5 + consolidated E2E).
- The RFC (`docs/rfcs/acervo-studio.md`) §11 is now marked DELIVERED.
- The invocation/write patterns are settled: agent proposes/crafts (cognition), server
  writes deterministically (acervoctl for promote, the publish CLIs for publish); assist/
  ask are proposal-only. Reuse `api/acervo_studio_agent._run_agent_text` for any new
  tool-less cognition; keep every new route delegated from `handle_studio_{get,post}`
  (0 `routes.py` lines) and the shared-file diff EMPTY.
