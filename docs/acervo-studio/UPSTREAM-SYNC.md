# Acervo Studio (MOD-010) — Upstream-sync checkpoint

> Written at the close of Phase 5 (2026-07-12). The Studio is feature-complete
> (Phases 0–5) and merged to `exocortex/stable`. This note captures how the Studio
> stays rebase-safe against the still-developing upstream and what to re-check on the
> next `upstream/master` cherry-pick.

## Policy: cherry-pick, never full-rebase

The fork's upstream policy is unchanged: pull **selected** upstream commits by
cherry-pick; **never** blindly merge/reset to `upstream/master` (it would clobber the
Exocórtex customization layer). `EXOCRTX_MODIFICATIONS.md` is the authoritative catalog
of every customization (`[MOD-NNN]`); consult it before any upstream sync. See
`.harness/subprojects/hermes-webui/IDENTITY.md`.

## Why the Studio is rebase-safe by construction

Rebase-safety is governed by **shared-file conflict surface**, not by language or size.
The Studio was built to touch almost none of it:

- **All new behavior lives in new, fork-owned files:** `api/acervo_studio.py`,
  `api/acervo_studio_agent.py`, `api/acervo_studio_publish.py`,
  `static/acervo-studio.{js,css}`, `tests/test_mod010_acervo_studio.py`,
  `docs/acervo-studio/*`, `docs/rfcs/acervo-studio.md`.
- **`api/routes.py` — 0 net-new lines across all six phases.** The Studio reuses the
  `/api/acervo/x/` prefix dispatch that MOD-009 already installed; every Studio route
  is delegated from `acervo_studio.handle_studio_{get,post}`.
- **`static/index.html` — no new lines since Phase 0** (the Phase-0 include/mount lines
  cover every later phase; the CSS `<link>` + JS `<script defer>` + `#acervoStudioRoot`).
- **The MOD-009 files are byte-untouched.** Phase 5's consolidation (retire/redirect the
  MOD-009 docked panel) is done entirely from `acervo-studio.js`: it hides the MOD-009
  body launcher `#axLauncher` and redirects the global `window.acervoExplorerToggle` to
  open the Studio, preserving the original on `window.__acervoExplorerToggleLegacy`.
  `acervo-explorer.{js,css}` were never edited.

Each phase asserts the invariant explicitly:

```bash
git diff exocortex/stable --stat -- \
  api/routes.py static/index.html static/style.css static/ui.js \
  static/workspace.js static/acervo.js static/acervo-explorer.js static/acervo-explorer.css
# expected: EMPTY
```

## Re-check these on the next upstream cherry-pick

The Studio only depends on a few upstream/MOD-009 seams. If a cherry-pick restructures
any of them, re-verify (and, if needed, re-point the fork-owned glue — never the reverse):

1. **The `/api/acervo/x/` prefix dispatcher** in `api/routes.py` (fork-owned via MOD-009;
   low risk) — the Studio's zero-`routes.py`-lines property depends on it delegating
   unknown `x/*` sub-paths to `acervo_explorer.handle_acervo_x_{get,post}`, which fall
   through to `acervo_studio.handle_studio_{get,post}`.
2. **The right-panel include/mount area** in `static/index.html` (the CSS `<link>`, the
   JS `<script defer>` order — `acervo-explorer.js` must load before `acervo-studio.js`
   so the consolidation hook can redirect `acervoExplorerToggle`; and `#acervoStudioRoot`).
3. **The two globals the consolidation hook touches:** `window.acervoExplorerToggle` and
   the `#axLauncher` element (both from `acervo-explorer.js`). The hook is defensive
   (typeof/existence guards, try/catch) — if upstream renames/removes them, the hook
   silently no-ops rather than breaking; the Studio's own `#axsLauncher` still works.
4. **The in-process agent seam** `run_agent.AIAgent` + `api.config`/`api.profiles`
   (used by `acervo_studio_agent.py` for triage/promote/assist/ask). If the agent's
   constructor or `run_conversation` signature changes upstream, update the one call site
   in `_run_agent_text`.
5. **The MOD-009 read/write helpers** `_safe_acervo_path`, frontmatter helpers,
   `_read_frontmatter_meta`, `_ACERVO_NATURES` (imported by the Studio modules).

## Runtime / go-live note (owner-gated)

The running instance is the provisioned `~/.hermes/hermes-webui/` copy (still serving
Phase 1 on :8787 — **not reprovisioned** this round). Making the full Studio live requires
the owner-gated go-live steps in `docs/acervo-studio/GO-LIVE-CHECKLIST.md`
(`EXOCORTEX_SCRIPTS_DIR` for promote, Drive creds for publish, provider creds for
assist/ask, then reprovision). Until then the Studio degrades calmly (agent-dependent
features show a calm offline state; browse/read/edit/capture keep working).
