# HW-1 — Fork re-founding onto current upstream (Strategy C) — Design

**Date:** 2026-07-13 · **Repo:** hermes-webui (fork `elderbernardi/hermes-webui`, branch `exocortex/stable`) · **Status:** design approved, pending spec review → plan.

## 1. Goal

Re-found the Exocórtex customization layer of `hermes-webui` on top of the **current** `upstream/master`, closing the divergence gap and shrinking the fork's future upstream-sync surface — without losing any customization (MOD-001..010, including the Acervo Studio Phases 0–5 that just landed).

**Divergence now:** base merge-base still `v0.51.448`; upstream HEAD `exp-v0.52.26`; fork is **~2850 behind / 124 ahead**. Incremental cherry-pick has not closed the gap (607 → 2850 in ~1 month); upstream crossed a minor (`v0.51 → v0.52`). Per the 2026-07-10 reaudit (`EXOCRTX_MODIFICATIONS.md` §"HW-1"), the fork's entire conflict surface is **additive and acervo-centric** — no fork commit rewrites upstream logic — which makes a clean re-founding viable and the best fit for the owner's goal ("aderir melhor ao upstream, acervo o mais independente possível").

## 2. Owner decisions (locked 2026-07-13)

1. **End-state:** full plan **including cutover**. The system is **not in production** — risks are acceptable. The re-founded lineage replaces the published `exocortex/stable`; reprovisioning `:8787` is fine but stays a trivial follow-up, not a risk gate.
2. **MOD-007/008:** **extract** the inline `routes.py` block into a new `api/acervo_tab.py` (zero acervo surface in `routes.py`).
3. **Execution rhythm:** **automatic with verification gates** — execute phase-by-phase in an isolated worktree; only stop for real checkpoints (the cutover).
4. **Live smoke:** against a **disposable fixture** (temp `HERMES_HOME` + `ACERVO=fixture` — the pattern proven in the Studio arc); the real acervo is never touched.

## 3. Strategy — clean re-founding (C)

Branch `exocortex/stable-v2` off the current `upstream/master`; re-apply **only** the fork layer; verify; then cutover (`exocortex/stable-v2` becomes `exocortex/stable`, old tip tagged `pre-refound-2026-07-13` as a safety ref, force-update origin). Rejected alternatives: **A** (incremental cherry-pick — never closes the gap) and **B** (in-place `merge upstream/master` — a huge, diffuse, hard-to-review conflict concentrated in an 18.9k-line `routes.py`, with a known interleaving failure mode).

Container: an isolated git worktree so the re-founding never disturbs the current working tree / `exocortex/stable`.

## 4. The fork layer to re-apply (inventory)

Authoritative source for each: `EXOCRTX_MODIFICATIONS.md` MOD-001..010 (each with its "Reaplicar se" + "Conflito provável"). Re-apply **by intent** (from the catalog), not by replaying old diffs — the upstream files moved substantially.

| Layer | MODs | Nature | Re-apply approach |
|---|---|---|---|
| **Skin / rebrand / i18n** | 001 skin registry (`config.py`), 002 frontend skins list (`i18n.js`), 003 EXCRTX.IA shell (`index.html` titlebar/empty-state/theme-boot), 004 skin stylesheet (`style.css`), 005 skin in `cmd_theme` locales, 006 full PT-BR (~125 keys) | Additive edits to **upstream files** (the churn-prone set) | Re-apply each edit against the new upstream file locations, guided by the catalog's anchors. |
| **Acervo tab** | 007 artifact catalog + Drive export, 008 session-oriented workspace + microverse browser + context enrichment | ~620-line inline block in `routes.py` (`_normalize_artifact`, `_handle_acervo_*`, `_handle_artifact_*`, `_acervo_root`, `_read_frontmatter_meta`, `_acervo_tool_path`) + frontend (`acervo.js`, `workspace.js` tab, `ui.js` chips, `sessions.js`) | **EXTRACT** → `api/acervo_tab.py` (see §5) |
| **Acervo Explorer** | 009 | Fork-owned files (upstream-absent) + `/api/acervo/x/` prefix dispatch | Copy clean; wire the prefix dispatch (now via `acervo_tab.py`). |
| **Acervo Studio (Phases 0–5)** | 010 | Fork-owned files (upstream-absent), 0 `routes.py` lines | Copy clean: `api/acervo_studio{,_agent,_publish}.py`, `static/acervo-studio.{js,css}`, `tests/test_mod010_acervo_studio.py`, `docs/acervo-studio/*`, `docs/rfcs/acervo-studio.md`. |

**Fork-owned files (confirmed upstream-absent → copy clean):** `api/acervo_explorer.py`, `api/acervo_studio.py`, `api/acervo_studio_agent.py`, `api/acervo_studio_publish.py`, `static/acervo-explorer.{js,css}`, `static/acervo-studio.{js,css}`.

## 5. The extraction — `api/acervo_tab.py` (the core new work)

Today the MOD-007/008 backend is ~620 lines inlined into `routes.py` (12061–12680) plus exact-match dispatch entries (`/api/acervo/titles`, `/api/acervo/stage-context`, `/api/acervo/microverses`, `/api/acervo/artifacts`, `/api/acervo/status`, `/api/acervo/knowledge`, artifact zip/publish/receipt). The Explorer (MOD-009) already added a **prefix dispatch** `/api/acervo/x/` and the Studio (MOD-010) rides it with 0 `routes.py` lines.

**Design:** move the entire MOD-007/008 block into `api/acervo_tab.py`, exposing `handle_acervo_get(handler, parsed)` / `handle_acervo_post(handler, body)` dispatchers, and re-plug **all** acervo routes (007/008 exact-match + the 009/010 `x/` prefix) through a single `/api/acervo/` prefix dispatch in `routes.py`. Net `routes.py` acervo surface → **~3 lines** (GET dispatch, POST dispatch, and the existing prefix hook).

**Shared-helper home.** `_acervo_root`, `_safe_acervo_path` (currently in `acervo_explorer.py`), `_read_frontmatter_meta`, `_ACERVO_NATURES`, and the session-workspace resolver are imported by the Explorer and Studio modules. Consolidate the acervo-shared helpers into `acervo_tab.py` as the single home; `routes.py`, `acervo_explorer.py`, `acervo_studio*.py` import them from there. This removes the last acervo helpers from `routes.py` and gives the acervo subsystem one clear dependency root. (Where a helper genuinely belongs to core routes — e.g. session resolution — keep it in `routes.py` and import it; the module boundary is "acervo-specific logic → `acervo_tab.py`".)

**Interface contract (unchanged behavior):** every existing acervo endpoint keeps its path, request shape, and response shape. The extraction is a pure move + re-wire; the MOD-009/010 test suite (154 tests) and the MOD-007/008 endpoints are the regression oracle.

## 6. Security triage disposition (from the 2026-07-10 sweep)

- 🔴 **Terminal-RCE gate** (`d257e5f3`+`34342b9f`) — **already in current upstream/master (confirmed)** → comes free with the re-founding. No interim cherry-pick.
- **Credential-scrub #3961 & other Fase-1 items** — check each against v0.52; the fork already back-ported the follow-ups. Drop if present upstream, else re-apply. The ~9-line credential wrapper in `routes.py` is re-applied only if still needed.
- 🟠 **CORS `*` on `do_OPTIONS`** — re-apply the fork's CSRF-model adaptation (echo Origin only if allowed, `Vary: Origin`, never `*`) if the new upstream still emits `*`.
- **Moot items** (TTS SSRF, OIDC SSO, skin-picker XSS, etc.) — not portable / absent in fork; skip.

## 7. Verification (prove it, take risks)

Per phase and at the end:
- **`pytest`** full suite on the new base (the fork's acervo suite ports clean; upstream's suite runs against v0.52). MOD-010 = 154 tests is the primary acervo oracle.
- **`npm run lint:runtime`** (vanilla-JS guard) clean.
- **Live smoke** on a disposable fixture (temp `HERMES_HOME` + `ACERVO=fixture` + provider keys from `~/.hermes/.env` + `EXOCORTEX_SCRIPTS_DIR` + real publish CLIs): boot server, verify skin/rebrand renders, drive the **Acervo tab** (MOD-007/008), the **Explorer** (MOD-009), and the full **Studio** chain capture→triage→promote→publish→assist (MOD-010). Isolation verified (fixture, not real acervo) before any write.
- **Whole-branch review** (opus) on the re-founded branch, focused on the extraction (behavior parity) and the skin/i18n re-application.

## 8. Phasing (the plan will detail; each phase → verify → merge into `exocortex/stable-v2`)

1. **P0 — Worktree & baseline.** Worktree off `upstream/master`; branch `exocortex/stable-v2`; confirm upstream suite + lint baseline green; tag `pre-refound-2026-07-13` on the old tip.
2. **P1 — Skin/rebrand/i18n (MOD-001..006).** Re-apply; smoke the shell (EXCRTX.IA renders, skin, PT-BR).
3. **P2 — Acervo tab extraction (MOD-007/008 → `acervo_tab.py`).** The core work; behavior parity via the MOD-007/008 endpoints.
4. **P3 — Explorer + Studio (MOD-009/010).** Copy fork-owned files; wire the prefix dispatch through `acervo_tab.py`; MOD-010 suite 154 green.
5. **P4 — Security triage + full verification.** Re-apply any still-needed Fase-1 items + CORS adaptation; full pytest + lint + consolidated live smoke + review.
6. **P5 — Cutover.** Tag safety ref; `exocortex/stable-v2` → `exocortex/stable`; force-update origin; update `EXOCRTX_MODIFICATIONS.md` (new base, extraction note) + umbrella COLLAB/IDENTITY. **(Checkpoint with owner before the force-update.)**

## 9. Risks & mitigations

- **Skin/i18n re-application misses an upstream-moved anchor** → guided by the MOD catalog's "Reaplicar se"; live shell smoke catches visual regressions.
- **Extraction changes behavior** → pure move + re-wire; 154-test MOD-010 suite + MOD-007/008 endpoint smoke are the oracle; whole-branch review targets it.
- **v0.52 upstream changed an API the fork depends on** (e.g. `run_agent.AIAgent`, session resolver, `_safe_acervo_path` peers) → caught at import/boot and by the agent-seam smoke; adapt the one call site (documented in `UPSTREAM-SYNC.md` seams).
- **Cutover rewrites published history** → safety tag + owner checkpoint before force-update; both repos already in sync so the coordinated push is clean.

## 10. Out of scope

Reprovisioning `:8787` (trivial follow-up), new features, unrelated upstream features (Kanban, Wiki-LLM, etc. — evaluate later per the catalog's Fase-3 list), and the umbrella governance push (routine, done at cutover).
