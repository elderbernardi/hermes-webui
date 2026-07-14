# HW-1 Strategy C Re-founding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-found the fork's customization layer (MOD-001..010) onto current
`upstream/master` (`exp-v0.52.26`), producing `exocortex/stable-v2` that replaces the
published `exocortex/stable` — closing the 2850-commit gap and shrinking the future
sync surface (acervo backend extracted from `routes.py` into `api/acervo_tab.py`).

**Architecture:** Work in a git worktree on a new branch off `upstream/master`. The
re-apply payload for each shared file is the fork's three-dot diff
(`git diff upstream/master...exocortex/stable -- <file>` = merge-base→fork, fork-side
additions only), classified hunk-by-hunk: **MOD-layer → re-apply (adapting anchors);
2026-06-23 cherry-picked upstream fix → drop if already in v0.52.** The 9 fork-owned
files copy byte-identical. The MOD-007/008 block (`routes.py` 12061–12661) moves
verbatim into `api/acervo_tab.py`; `routes.py` re-exports the moved names so the
fork-owned modules' `routes.<name>` references keep working unchanged.

**Tech Stack:** git worktree, Python 3 stdlib server, pytest, eslint (`lint:runtime`),
Playwright fixture smoke (temp `HERMES_HOME` + `ACERVO=fixture`).

## Global Constraints

- **Spec:** `docs/hw1/DESIGN.md` (owner decisions locked 2026-07-13: full plan incl.
  cutover; extract MOD-007/008; automatic execution with verification gates; fixture smoke).
- **Fork-owned files stay byte-identical** (MOD-009/010 + `static/acervo.js`):
  `api/acervo_explorer.py`, `api/acervo_studio.py`, `api/acervo_studio_agent.py`,
  `api/acervo_studio_publish.py`, `static/acervo-explorer.{js,css}`,
  `static/acervo-studio.{js,css}`, `static/acervo.js` — copied with
  `git checkout exocortex/stable -- <path>`, never edited.
- **Endpoint contract unchanged:** every `/api/acervo/*` and `/api/artifact/*` route
  keeps its path, request shape, and response shape. Oracle = MOD-010 suite (154 tests)
  + MOD-007/008 endpoint smoke.
- **Real acervo never touched:** all live smoke uses temp `HERMES_HOME` + explicit
  `ACERVO=<fixture>`; verify isolation (`x/tree` shows fixture files) BEFORE any write.
- **Classification rule (every shared-file hunk):** if the hunk's distinctive symbol
  already exists in `upstream/master` → cherry-picked fix now upstream → **drop**;
  else it is MOD-layer → **re-apply**. Record each decision in the phase commit message.
- **Baseline-relative testing:** upstream v0.52 may have its own failing tests. P0
  records the baseline; later phases must show **zero NEW failures vs that baseline**.
- Worktree lives at `.worktrees/hw1-v2` inside hermes-webui (add `.worktrees/` to
  `.gitignore` if absent). Branch name: `exocortex/stable-v2`.
- Commits on `exocortex/stable-v2` per task; no pushes until P5 cutover (owner checkpoint
  before force-update).

## Reference — classification facts already verified (2026-07-13)

- Terminal-RCE gate (`d257e5f3`+`34342b9f`): **already in upstream/master** → free, no action.
- `_load_yaml_config_file_raw`: present in both fork and upstream → the config caching
  cherry-picks largely converged; classify per hunk anyway.
- `server.py` +34 = TLS accept-loop fix (#4727, cherry-picked 2026-06-23) → classify.
- Upstream anchors alive: `_SETTINGS_SKIN_VALUES` (api/config.py), `cmd_theme`
  (static/i18n.js). MOD catalog's `_SKINS` symbol is stale — work from diff hunks, not
  catalog symbol names.
- `_read_frontmatter_meta`/`_acervo_root`/`_ACERVO_NATURES` have **zero consumers** in
  `routes.py` outside the 12061–12661 block → clean move.
- `routes.<name>` attributes consumed by fork-owned modules (20): acervo-specific
  (candidates to move+re-export): `_ACERVO_NATURES`, `_ACERVO_UI_STATUSES`,
  `_acervo_root`, `_read_frontmatter_meta`, `_read_frontmatter_title`, `_humanize_slug`,
  `_handle_acervo_status`, `_handle_acervo_stage_context`. Core-routes (stay in
  routes.py): `j`, `bad`, `require`, `get_session`, `get_session_for_file_ops`,
  `_resolve_session_workspace`, `_llm_git_commit_message`, `open_anchored_fd`,
  `_content_disposition_value`, `_folder_download_collect`, `_folder_zip_max_bytes`,
  `_folder_zip_max_files`. Task P2.1 verifies each name's true home before moving.

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `.worktrees/hw1-v2/` | create (worktree) | isolated re-founding workspace |
| `api/acervo_tab.py` | **create** | MOD-007/008 backend moved verbatim + acervo-shared helpers; `handle_acervo_get/post` dispatchers |
| `api/routes.py` | modify (minimal) | remove old block; add 1 re-export import + 2 dispatch delegations |
| `api/config.py`, `static/{i18n.js,index.html,style.css,ui.js,workspace.js,sessions.js}`, `server.py`, `api/profiles.py` | modify | re-apply classified MOD hunks |
| 9 fork-owned files (list in Global Constraints) | copy byte-identical | MOD-009/010 + acervo.js |
| `tests/test_mod010_acervo_studio.py` | copy byte-identical | acervo oracle (154 tests) |
| `EXOCRTX_MODIFICATIONS.md`, `docs/**` (rfcs, acervo-studio, hw1, architecture, ui-ux) | copy + update | catalog gets new base + extraction note |

---

## Phase P0 — Worktree & baseline

### Task P0.1: Worktree, branch, safety tag, baseline record

**Files:**
- Create: `.worktrees/hw1-v2/` (worktree), branch `exocortex/stable-v2`
- Modify: `.gitignore` (only if `.worktrees/` not ignored)

**Interfaces:**
- Produces: worktree at `.worktrees/hw1-v2` on `exocortex/stable-v2` = `upstream/master`;
  tag `pre-refound-2026-07-13` on old stable; baseline file `/tmp/hw1-baseline.txt`.

- [ ] **Step 1: Tag the old tip and create the worktree**

```bash
cd /home/elder/projetos/projetob/hermes-webui
git tag -f pre-refound-2026-07-13 exocortex/stable
grep -qx '.worktrees/' .gitignore || { echo '.worktrees/' >> .gitignore; git add .gitignore; git commit -m "chore: ignore .worktrees/"; }
git worktree add .worktrees/hw1-v2 -b exocortex/stable-v2 upstream/master
cd .worktrees/hw1-v2 && git log --oneline -1   # expect upstream exp-v0.52.26 tip (157714a1)
```

- [ ] **Step 2: Record the upstream test/lint baseline**

```bash
cd .worktrees/hw1-v2
python3 -m pytest tests/ -q 2>&1 | tail -3 | tee /tmp/hw1-baseline.txt
npm install --no-audit --no-fund >/dev/null 2>&1 || true
npm run lint:runtime 2>&1 | tail -2 | tee -a /tmp/hw1-baseline.txt || echo "lint:runtime script absent upstream — note it" | tee -a /tmp/hw1-baseline.txt
```
Expected: some pass/fail counts — whatever they are, they ARE the baseline. If
`lint:runtime` doesn't exist upstream, note it (the fork adds it; re-applied in P1 if
it lives in `package.json`, else in P3 with the fork files).

- [ ] **Step 3: Boot smoke of pristine upstream**

```bash
cd .worktrees/hw1-v2
HERMES_WEBUI_PORT=8795 timeout 20 python3 server.py & sleep 4
curl -s -o /dev/null -w "upstream boot: %{http_code}\n" http://127.0.0.1:8795/   # expect 200
kill %1 2>/dev/null
```

- [ ] **Step 4: Commit nothing (worktree is at upstream tip); record baseline in the ledger**

Append the baseline numbers to `docs/hw1/PLAN.md` execution notes (main checkout) or a
`.superpowers/sdd/hw1-progress.md` ledger entry. No code commit.

---

## Phase P1 — Skin / rebrand / i18n (MOD-001..006) + shared-file classification

### Task P1.1: Generate and classify the per-file payloads

**Files:**
- Create: `/tmp/hw1-payload/<file>.diff` (one per shared file, working material)

**Interfaces:**
- Produces: for each shared file, a classified hunk list: `REAPPLY` (MOD-layer) or
  `DROP` (already upstream). Used by P1.2–P1.4 and P2/P4.

- [ ] **Step 1: Generate the fork-side diffs**

```bash
cd /home/elder/projetos/projetob/hermes-webui
mkdir -p /tmp/hw1-payload
for f in api/config.py api/profiles.py server.py static/i18n.js static/index.html \
         static/style.css static/ui.js static/workspace.js static/sessions.js; do
  git diff upstream/master...exocortex/stable -- "$f" > "/tmp/hw1-payload/$(basename $f).diff"
done
wc -l /tmp/hw1-payload/*.diff
```

- [ ] **Step 2: Classify every hunk**

For each hunk: extract its most distinctive added symbol/string; check
`git grep -F "<symbol>" upstream/master -- <file>`. Present in upstream → `DROP`
(record which cherry-pick it was); absent → `REAPPLY`. Write the classification table
to `/tmp/hw1-payload/CLASSIFICATION.md` with columns: file · hunk anchor · symbol ·
verdict · reason. Known candidates to check: `api/profiles.py` (+351 — #3961
credential-scrub follow-ups), `server.py` (+34 — TLS accept fix #4727), `api/config.py`
(config caching #4662 vs MOD-001 skin registry), `static/ui.js` (#4346 footer jitter vs
MOD-008 chips).

- [ ] **Step 3: Commit the classification** (in the worktree, as documentation)

```bash
cd .worktrees/hw1-v2 && mkdir -p docs/hw1
cp /tmp/hw1-payload/CLASSIFICATION.md docs/hw1/CLASSIFICATION.md
git add docs/hw1/CLASSIFICATION.md && git commit -m "docs(hw1): shared-file hunk classification (REAPPLY vs DROP)"
```

### Task P1.2: Re-apply MOD-001 (skin registry) + MOD-004 (stylesheet) + MOD-005/006 (i18n)

**Files:**
- Modify (in worktree): `api/config.py`, `static/style.css`, `static/i18n.js`

**Interfaces:**
- Consumes: `REAPPLY` hunks from P1.1 for these files.
- Produces: `excrtx` skin registered backend+frontend; EXCRTX token block in
  `style.css`; PT-BR locale (~125 keys) + skin listed in `cmd_theme` locales.

- [ ] **Step 1: Apply the REAPPLY hunks**, adapting anchors: `api/config.py` →
  `_SETTINGS_SKIN_VALUES` (anchor verified alive); `static/style.css` → append the
  EXCRTX skin block at the end (additive); `static/i18n.js` → skins list + `cmd_theme`
  strings + the PT-BR block. Use `git apply --3way` per-file first; hand-adapt rejects.

- [ ] **Step 2: Verify**

```bash
cd .worktrees/hw1-v2
python3 -c "import api.config"            # imports clean
grep -c "excrtx" api/config.py static/i18n.js static/style.css   # each >= 1
node --check static/i18n.js
```

- [ ] **Step 3: Commit**

```bash
git add api/config.py static/style.css static/i18n.js
git commit -m "feat(hw1): re-apply MOD-001/004/005/006 — excrtx skin registry, stylesheet, locales"
```

### Task P1.3: Re-apply MOD-003 (EXCRTX.IA shell in index.html)

**Files:**
- Modify (in worktree): `static/index.html`

**Interfaces:**
- Consumes: `REAPPLY` hunks of `index.html.diff` **excluding** the MOD-007/008 tab
  ruler and MOD-009/010 include/mount lines (those land in P2.3/P3.1 with their code).
- Produces: EXCRTX.IA titlebar/rebrand/theme-boot on the new upstream shell.

- [ ] **Step 1: Apply the shell/rebrand hunks** (titlebar text, empty-state, theme/skin
  boot script). The upstream boot script moved (v0.52) — locate by searching
  `data-theme`/`skin` initialization in the new `index.html` and adapt.
- [ ] **Step 2: Verify** — boot the server (port 8795), `curl -s http://127.0.0.1:8795/ | grep -c EXCRTX` ≥ 1; open in Playwright, screenshot, confirm rebrand + skin renders (no unstyled shell).
- [ ] **Step 3: Commit** `feat(hw1): re-apply MOD-003 — EXCRTX.IA shell`

### Task P1.4: Phase gate P1

- [ ] Full pytest + lint vs baseline (zero NEW failures); boot smoke; commit any fixups.

---

## Phase P2 — Extract MOD-007/008 → `api/acervo_tab.py`

### Task P2.1: Verify the move list and create `api/acervo_tab.py`

**Files:**
- Create (in worktree): `api/acervo_tab.py`

**Interfaces:**
- Consumes: the block `routes.py:12061–12661` **from the fork checkout**
  (`git show exocortex/stable:api/routes.py`), which contains (verified):
  `_normalize_artifact`, `_handle_acervo_artifacts`, `_handle_acervo_status`,
  `_acervo_root`, `_read_frontmatter_meta`, `_ACERVO_NATURES`,
  `_handle_acervo_microverses`, `_handle_acervo_knowledge`, `_handle_acervo_titles`,
  `_handle_acervo_stage_context`, `_handle_artifact_zip`, `_acervo_tool_path`,
  `_handle_artifact_publish`, `_handle_artifact_receipt`.
- Produces: `api.acervo_tab` exposing all of the above **plus**
  `handle_acervo_get(handler, parsed) -> bool` and
  `handle_acervo_post(handler, path, body) -> bool` dispatchers; plus any of
  `_ACERVO_UI_STATUSES`, `_read_frontmatter_title`, `_humanize_slug` that P2.1
  verification shows are acervo-only.

- [ ] **Step 1: Verify the exact move list.** For each candidate name in the Reference
  section, confirm in the fork's `routes.py`: defined inside 12000–12700? consumers
  outside that range? (`grep -n "<name>" api/routes.py` on the fork checkout). Names
  defined in the block OR used only by acervo code → move. Names with non-acervo
  consumers (e.g. `_humanize_slug` if used by workspace code) → leave in `routes.py`,
  import into `acervo_tab.py` deferred.
- [ ] **Step 2: Create the module.** Extract lines 12061–12661 (adjusted per Step 1)
  verbatim from `git show exocortex/stable:api/routes.py`, prepend:

```python
"""Acervo tab backend — MOD-007/008 (HW-1 extraction from api/routes.py).

Every /api/acervo/* and /api/artifact/* endpoint of the Acervo tab lives here;
routes.py keeps only a re-export import and two dispatch delegations. Core-route
helpers (j, bad, sessions) are imported from api.routes at call time (deferred,
same pattern as api/acervo_explorer.py) to avoid import cycles.
"""
```

  and replace bare uses of core helpers (`j(...)`, `bad(...)`, `get_session(...)`,
  `_resolve_session_workspace(...)` …) with the deferred pattern used by
  `acervo_explorer.py`: `import api.routes as routes` at function top + `routes.j(...)`.
  Append the two dispatchers, mapping exactly the paths the fork dispatches today:

```python
def handle_acervo_get(handler, parsed):
    """GET dispatcher. Returns True if the path was handled."""
    p = parsed.path
    if p == "/api/artifact/zip":
        return _handle_artifact_zip(handler, parsed)
    if p == "/api/acervo/artifacts":
        return _handle_acervo_artifacts(handler, parsed)
    if p == "/api/acervo/microverses":
        return _handle_acervo_microverses(handler, parsed)
    if p == "/api/acervo/knowledge":
        return _handle_acervo_knowledge(handler, parsed)
    if p == "/api/acervo/titles":
        return _handle_acervo_titles(handler, parsed)
    if p == "/api/artifact/receipt":
        return _handle_artifact_receipt(handler, parsed)
    if p.startswith("/api/acervo/x/"):
        from api.acervo_explorer import handle_acervo_x_get
        return handle_acervo_x_get(handler, parsed)
    return False


def handle_acervo_post(handler, path, body):
    """POST dispatcher. Returns True if the path was handled."""
    if path == "/api/artifact/publish":
        return _handle_artifact_publish(handler, body)
    if path == "/api/acervo/status":
        return _handle_acervo_status(handler, body)
    if path == "/api/acervo/stage-context":
        return _handle_acervo_stage_context(handler, body)
    if path.startswith("/api/acervo/x/"):
        from api.acervo_explorer import handle_acervo_x_post
        return handle_acervo_x_post(handler, path, body)
    return False
```

  ⚠️ Adapt the exact signatures to what the fork's dispatch call-sites pass today
  (`routes.py:7548–7562` GET, `9179–9186` POST — read them and mirror; e.g. if the
  explorer POST fallback receives `(handler, body)` only, drop `path` accordingly).
- [ ] **Step 3: Syntax check** `python3 -m py_compile api/acervo_tab.py`.
- [ ] **Step 4: Commit** `feat(hw1): api/acervo_tab.py — MOD-007/008 backend extracted (module only, unwired)`

### Task P2.2: Wire routes.py (dispatch + re-export) — the ONLY routes.py edit

**Files:**
- Modify (in worktree): `api/routes.py`

**Interfaces:**
- Consumes: `api.acervo_tab.handle_acervo_get/post` + the moved names.
- Produces: `routes.<moved-name>` still resolves (re-export) so the 9 byte-identical
  fork-owned files work unchanged; all acervo routes dispatch through the module.

- [ ] **Step 1: Add the delegation + re-export.** In the new upstream `routes.py`,
  find the GET dispatcher (where upstream matches `parsed.path`) and add **one** block:

```python
    # EXCRTX MOD-007..010 — Acervo tab/explorer/studio (extracted: api/acervo_tab.py)
    from api.acervo_tab import handle_acervo_get as _acervo_get
    if _acervo_get(self, parsed):
        return
```

  and in the POST dispatcher:

```python
    # EXCRTX MOD-007..010 — Acervo (extracted: api/acervo_tab.py)
    from api.acervo_tab import handle_acervo_post as _acervo_post
    if _acervo_post(self, parsed.path, body):
        return
```

  At module level (bottom of routes.py, one line-block), the re-export for the
  fork-owned modules' `routes.<name>` references:

```python
# EXCRTX re-exports — fork-owned acervo modules reference these via api.routes
from api.acervo_tab import (  # noqa: E402,F401
    _ACERVO_NATURES, _ACERVO_UI_STATUSES, _acervo_root,
    _read_frontmatter_meta, _read_frontmatter_title, _humanize_slug,
    _handle_acervo_status, _handle_acervo_stage_context,
)
```

  (Trim this list to the P2.1-verified moved set. Guard against the import cycle: the
  re-export at file bottom runs after routes.py fully defines its own names;
  `acervo_tab` only imports `api.routes` inside functions — verified pattern.)
- [ ] **Step 2: Verify** `python3 -c "import api.routes"` clean; boot server; then
  endpoint smoke (fixture acervo + session): `GET /api/acervo/microverses`,
  `/api/acervo/artifacts`, `/api/acervo/knowledge?scope=global`, `/api/acervo/titles`,
  `POST /api/acervo/status` (invalid id → 400/404 calm) — each responds with the same
  shape as on the fork (compare against the same curl on a fork-checkout server).
- [ ] **Step 3: Commit** `feat(hw1): wire acervo_tab dispatch + re-exports — routes.py acervo surface ≈ 12 lines`

### Task P2.3: MOD-007/008 frontend (acervo.js, workspace/ui/sessions hooks, index.html tab)

**Files:**
- Copy (byte-identical): `static/acervo.js`
- Modify (in worktree): `static/workspace.js`, `static/ui.js`, `static/sessions.js`,
  `static/index.html` (tab ruler + `acervo.js` include)

**Interfaces:**
- Consumes: `REAPPLY` hunks from P1.1 for these files (MOD-007/008 hooks:
  `switchWorkspacePanelTab` acervo branch, `renderSessionArtifacts`,
  `renderStagedContextChips`, `_refreshActiveWorkspaceTab`).
- Produces: working Acervo tab UI on the new shell.

- [ ] **Step 1:** `git checkout exocortex/stable -- static/acervo.js`
- [ ] **Step 2:** Apply the classified hooks to `workspace.js`/`ui.js`/`sessions.js`
  (adapt anchors — these functions moved in v0.52; locate by function name) and the
  `index.html` tab-ruler + include lines.
- [ ] **Step 3: Verify** — boot; open Playwright; the right panel shows the Acervo tab;
  the tab lists fixture microverses/artifacts; staged-context chips render; console clean.
- [ ] **Step 4: Commit** `feat(hw1): re-apply MOD-007/008 frontend on v0.52 shell`

### Task P2.4: Phase gate P2

- [ ] Full pytest + lint vs baseline; endpoint-parity smoke (Step 2 of P2.2 rerun);
  commit fixups.

---

## Phase P3 — Explorer + Studio (MOD-009/010)

### Task P3.1: Copy fork-owned files + includes; port the MOD-010 suite

**Files:**
- Copy (byte-identical, in worktree): `api/acervo_explorer.py`, `api/acervo_studio.py`,
  `api/acervo_studio_agent.py`, `api/acervo_studio_publish.py`,
  `static/acervo-explorer.{js,css}`, `static/acervo-studio.{js,css}`,
  `tests/test_mod010_acervo_studio.py`
- Modify: `static/index.html` (the 5 include/mount lines: 2 CSS links, 2 script defers
  in order explorer-before-studio, `#acervoExplorerRoot` + `#acervoStudioRoot` mounts)
- Copy: `docs/rfcs/acervo-studio.md`, `docs/acervo-studio/**`, `eslint.runtime-guard.config.mjs`
  + the `lint:runtime` script entry in `package.json` (if P0 noted it absent upstream)

**Interfaces:**
- Consumes: `routes.<name>` re-exports (P2.2) + `/api/acervo/x/` prefix dispatch (P2.1).
- Produces: full Explorer + Studio running on the new base.

- [ ] **Step 1:**

```bash
cd .worktrees/hw1-v2
git checkout exocortex/stable -- api/acervo_explorer.py api/acervo_studio.py \
  api/acervo_studio_agent.py api/acervo_studio_publish.py \
  static/acervo-explorer.js static/acervo-explorer.css \
  static/acervo-studio.js static/acervo-studio.css \
  tests/test_mod010_acervo_studio.py docs/rfcs/acervo-studio.md docs/acervo-studio \
  eslint.runtime-guard.config.mjs
```

- [ ] **Step 2:** Add the include/mount lines to `index.html` (same 3-line pattern the
  catalog documents + the explorer's lines; explorer script before studio script).
  Add `lint:runtime` to `package.json` scripts if missing.
- [ ] **Step 3: Verify**

```bash
python3 -m pytest tests/test_mod010_acervo_studio.py -q   # expect 154 passed
npm run lint:runtime                                       # clean
```
  If any of the 154 fail: the cause is in the *seam* (a `routes.<name>` re-export
  missing, or an upstream API the agent module uses changed — e.g. `run_agent.AIAgent`
  ctor, `api.profiles.profile_env_for_background_worker`). Fix the seam in
  `acervo_tab.py`/re-export list — NEVER by editing the fork-owned files.
- [ ] **Step 4: Commit** `feat(hw1): MOD-009/010 Explorer+Studio on v0.52 — fork files byte-identical, 154 green`

### Task P3.2: Phase gate P3

- [ ] Full pytest vs baseline; `node --check` both fork JS files; boot + Playwright:
  Studio opens (launcher), nav renders scopes, consolidation hook hides the MOD-009
  launcher (P5-of-Studio behavior intact on new base).

---

## Phase P4 — Security triage + full verification

### Task P4.1: Apply still-needed security items

**Files:**
- Modify (in worktree): per P1.1 classification — likely `server.py` (`do_OPTIONS`
  CORS) and any `REAPPLY` remnants of `api/profiles.py`.

- [ ] **Step 1:** From `CLASSIFICATION.md`: every security hunk marked `REAPPLY`
  (i.e. NOT yet upstream) gets applied now — expected: the CORS `do_OPTIONS`
  adaptation (echo Origin only if allowed by the fork's `_allowed_public_origins`
  model, add `Vary: Origin`, never `*`) **if** the new upstream still emits `*`
  (check first: `grep -n "Access-Control-Allow-Origin" server.py api/*.py`).
  Terminal-RCE: verify the gate exists in the new base
  (`grep -n "_onboarding_request_is_local\|local.*gate" api/routes.py` near the
  terminal handlers) — confirmed upstream, so this is a check, not a change.
- [ ] **Step 2: Commit** `fix(hw1): security triage — CORS origin echo (+ any residual REAPPLY items)`

### Task P4.2: Consolidated fixture live-smoke + whole-branch review

- [ ] **Step 1: Fixture smoke** (the proven recipe): temp `HERMES_HOME` + copy ONLY
  `~/.hermes/config.yaml` + provider keys from `~/.hermes/.env` + explicit
  `ACERVO=<fixture>` + `EXOCORTEX_SCRIPTS_DIR=~/.exocortex-installer/scripts` + real
  publish CLIs in `<fixture>/global/tools/`. Verify isolation FIRST (`x/tree` = fixture
  files only). Then drive: skin/rebrand renders → Acervo tab (microverses, artifacts,
  stage-context) → Explorer → Studio chain capture→triage→promote→publish-gate→assist→ask.
  Agent-cognition steps may degrade offline (calm 200s) — deterministic halves must pass.
  0 console errors. Real acervo verified untouched after.
- [ ] **Step 2: Whole-branch review** (opus subagent): diff `upstream/master..exocortex/stable-v2`,
  lenses: extraction behavior-parity (old fork block vs `acervo_tab.py` — should be a
  pure move), re-export completeness, skin/i18n fidelity, no fork-owned file drift
  (`git diff exocortex/stable exocortex/stable-v2 -- <9 files> tests/test_mod010*` must
  be EMPTY), classification correctness (spot-check 3 DROPs actually exist upstream).
  Fix findings with regressions; re-run the suite.
- [ ] **Step 3: Commit fixes** + record smoke/review results in the ledger.

---

## Phase P5 — Docs + cutover (OWNER CHECKPOINT)

### Task P5.1: Update the catalog + docs on v2

**Files:**
- Modify (in worktree): `EXOCRTX_MODIFICATIONS.md`, `docs/acervo-studio/UPSTREAM-SYNC.md`

- [ ] **Step 1:** `EXOCRTX_MODIFICATIONS.md`: new base = `exp-v0.52.26` merge-base;
  HW-1 section gains "EXECUTADO 2026-07-13" outcome (Strategy C, extraction done,
  which hunks were DROPped as already-upstream — from CLASSIFICATION.md); MOD-007/008
  entries note the new home `api/acervo_tab.py`; routes.py conflict risk table updated
  (acervo surface now ≈ 12 lines). `UPSTREAM-SYNC.md`: base/seam updates.
- [ ] **Step 2: Commit** `docs(hw1): catalog + upstream-sync updated for the re-founded base`

### Task P5.2: 🛑 OWNER CHECKPOINT, then cutover

- [ ] **Step 1: STOP — present to owner:** v2 verification summary (suite vs baseline,
  154 acervo tests, smoke, review) and the exact cutover commands below. **Do not
  proceed without explicit OK.**
- [ ] **Step 2: Cutover (after OK):**

```bash
cd /home/elder/projetos/projetob/hermes-webui
git branch -f exocortex/stable exocortex/stable-v2
git push --force-with-lease origin exocortex/stable
git push origin pre-refound-2026-07-13            # safety tag preserved on origin
git worktree remove .worktrees/hw1-v2
```

- [ ] **Step 3: Umbrella governance:** COLLAB record
  `.harness/changes/2026-07-13_collab_hermes-webui-hw1-refounding.md` + IDENTITY update
  (new base, acervo_tab extraction, stable lineage rewritten w/ safety tag) — commit +
  push umbrella (push now unblocked).
- [ ] **Step 4:** Update memory ledger; surface follow-ups (reprovision `:8787` to the
  new stable = owner-gated Gate D; old branches `collab/acervo-studio-p*` remain valid
  history on the old lineage via the tag).

## Execution notes

- **Task-sizing caveat:** P1.2/P1.3/P2.3 are "re-apply by intent" — the exact final
  hunks depend on v0.52 anchors and cannot be pre-written here; the payload diffs +
  classification + per-step verification are the contract. Everything else is exact.
- **Failure policy:** any phase gate failing vs baseline blocks the next phase; fix
  forward inside the phase. If the extraction proves unexpectedly entangled (hidden
  consumers), fall back to *inline re-apply* for the entangled name only (leave it in
  routes.py, import from acervo_tab) — record in the catalog.
