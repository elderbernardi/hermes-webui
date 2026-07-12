# Acervo Studio — Phase 5 (Consolidate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> or superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** Bring the Studio to steady state now that it reaches parity: retire/redirect
the MOD-009 docked-panel entry points, an accessibility pass (dialog semantics, focus,
keyboard nav), a focused perf check, an upstream-sync checkpoint note, and the RFC §11
status update.

**Architecture:** All behavior changes live in the fork-owned `static/acervo-studio.js`
(+ small CSS). The MOD-009 retire/redirect is done WITHOUT editing `acervo-explorer.*`
(rebase-safety): a consolidation hook hides the MOD-009 body launcher (`#axLauncher`)
and redirects the global `window.acervoExplorerToggle` to open the Studio, preserving
the original on a namespaced global. No backend changes → the pytest suite is unchanged;
frontend behavior is verified via Playwright E2E + `node --check` + `lint:runtime`.

**Tech Stack:** vanilla IIFE JS, Playwright, docs.

## Global Constraints

- **REBASE-SAFETY:** changes ONLY in `static/acervo-studio.{js,css}` and docs
  (`docs/rfcs/acervo-studio.md`, new `docs/acervo-studio/UPSTREAM-SYNC.md`). **0 lines**
  in `routes.py`/`index.html`; NEVER edit `acervo-explorer.*`/`ui.js`/`workspace.js`/
  `acervo.js`/`style.css`. Shared-file diff EMPTY at the end.
- **VANILLA ONLY:** IIFE, no import/export (`npm run lint:runtime`); `.axs-*` namespace;
  all dynamic content `_esc`'d.
- **NON-DESTRUCTIVE CONSOLIDATION:** the MOD-009 code stays byte-untouched; only its
  *entry points* are redirected. The original toggle stays reachable via
  `window.__acervoExplorerToggleLegacy` (escape hatch). No behavior removed, only funneled.
- **NO REGRESSION:** the full pytest suite shows no NEW failures vs the ~16 env baseline.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `static/acervo-studio.js` | modify | consolidation hook (retire/redirect MOD-009) + a11y (dialog role, Escape, focus, keyboard nav) |
| `static/acervo-studio.css` | modify (append) | `:focus-visible` ring for nav items |
| `docs/acervo-studio/UPSTREAM-SYNC.md` | create | upstream-sync checkpoint note |
| `docs/rfcs/acervo-studio.md` | modify | §11 status update (Phases 0–5 delivered) |

---

### Task 1 — Consolidation hook: retire/redirect the MOD-009 docked panel

**Files:** `static/acervo-studio.js`.

The MOD-009 panel exposes `window.acervoExplorerToggle` (set at its script eval, which
loads before acervo-studio.js) and injects a body-level `#axLauncher` on DOMContentLoaded.
Redirect the global to the Studio and hide the duplicate launcher — all from this file.

- [ ] **Step 1: Add the consolidation hook** near the bottom of the IIFE, before the
  final `_ensureLauncher()` bootstrap (search for `window.addEventListener('beforeunload'`
  — add this just above the module's DOM-ready bootstrap block):

```js
  // ── Phase 5: consolidate — retire/redirect the MOD-009 docked panel ──────
  // The Studio reaches parity, so its entry points funnel to the Studio. We do
  // NOT edit acervo-explorer.* (rebase-safety): we hide the MOD-009 body
  // launcher and redirect its global toggle, preserving the original as an
  // escape hatch. Idempotent; safe if MOD-009 is absent.
  function _consolidateMod009() {
    try {
      if (typeof window.acervoExplorerToggle === 'function' &&
          window.acervoExplorerToggle !== acervoStudioToggle) {
        window.__acervoExplorerToggleLegacy = window.acervoExplorerToggle;
        window.acervoExplorerToggle = function () { acervoStudioToggle(); };
      }
      var legacy = document.getElementById('axLauncher');
      if (legacy) legacy.style.display = 'none';
    } catch (e) { /* consolidation is best-effort */ }
  }
```

- [ ] **Step 2: Call it from the DOM-ready bootstrap.** Find the existing bootstrap at
  the end of the IIFE (the block that calls `_ensureLauncher`). Add `_consolidateMod009()`
  right after `_ensureLauncher()` in BOTH the `DOMContentLoaded` branch and the
  already-loaded branch. If the bootstrap is a single `_ensureLauncher()` call, wrap:

```js
  function _bootstrap() {
    _ensureLauncher();
    _consolidateMod009();
  }
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', _bootstrap, { once: true });
    } else {
      _bootstrap();
    }
  }
```

  (Replace the existing `_ensureLauncher`-only bootstrap with this. Keep whatever the
  current bootstrap's structure is — the point is both `_ensureLauncher` and
  `_consolidateMod009` run once on ready.)

- [ ] **Step 3: Verify** `node --check static/acervo-studio.js && npm run lint:runtime`.
- [ ] **Step 4: Commit** `feat(acervo-studio): retire/redirect MOD-009 docked panel (Phase 5 T1)`.

---

### Task 2 — Accessibility pass: dialog semantics, Escape, focus, keyboard nav

**Files:** `static/acervo-studio.js`, `static/acervo-studio.css`.

- [ ] **Step 1: Dialog semantics + keyboard on the shell.** In `_build`, after
  `root.className = 'axs-root';`, add:

```js
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-label', 'Acervo Studio');
```

  and after the search-input keydown wiring in `_build`, add an Escape-to-close handler
  (only when focus is NOT in a text field, so Escape still clears the search box natively)
  and a delegated Enter/Space handler that activates focused nav items:

```js
    root.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        var t = e.target;
        var tag = t && t.tagName ? t.tagName.toLowerCase() : '';
        var typing = tag === 'input' || tag === 'textarea' || tag === 'select';
        if (!typing) { e.preventDefault(); _close(); }
        return;
      }
      if ((e.key === 'Enter' || e.key === ' ') && e.target &&
          e.target.classList && (e.target.classList.contains('axs-ni') ||
          e.target.classList.contains('axs-pi'))) {
        e.preventDefault();
        e.target.click();
      }
    });
```

- [ ] **Step 2: Focus management on open/close.** In `_open`, remember the launcher and
  move focus into the Studio after it is shown:

```js
  function _open() {
    _build();
    var root = _root();
    root.hidden = false;
    AXS.open = true;
    AXS._returnFocus = document.getElementById('axsLauncher');
    _showLauncher(false);
    if (typeof acervoStudioRenderNav === 'function') acervoStudioRenderNav();
    var q = root.querySelector('[data-axs="q"]');
    if (q && typeof q.focus === 'function') q.focus();
  }
```

  and in `_close`, return focus to the launcher after it is re-shown (add right before
  the function returns, after `_showLauncher(true);`):

```js
    _showLauncher(true);
    var rf = AXS._returnFocus || document.getElementById('axsLauncher');
    if (rf && typeof rf.focus === 'function') rf.focus();
```

- [ ] **Step 3: Make nav items focusable.** Add `role="button"` + `tabindex="0"` to the
  scope items and the sub items where they are wired. In `acervoStudioRenderNav`, in the
  `.axs-ni` forEach loop (the one that adds the click listener), add before/after the
  `addEventListener`:

```js
      el.setAttribute('role', 'button');
      el.setAttribute('tabindex', '0');
```

  In `acervoStudioSelectScope`, add the same two `setAttribute` calls inside EACH of the
  four sub-item wire loops (`[data-mv]`, `[data-path]`, `[data-intake]`, `[data-art]`).

- [ ] **Step 4: Focus-visible ring (CSS).** Append to `static/acervo-studio.css`:

```css
/* Phase 5: a11y — visible keyboard focus for nav items */
.axs-ni:focus-visible, .axs-pi:focus-visible {
  outline: 2px solid var(--axs-acc); outline-offset: -2px; border-radius: 6px;
}
```

- [ ] **Step 5: Verify** `node --check` + `lint:runtime`.
- [ ] **Step 6: Commit** `feat(acervo-studio): a11y pass — dialog role, Escape, focus, keyboard nav (Phase 5 T2)`.

---

### Task 3 — Focused perf check (measure; apply only clear wins)

**Files:** `static/acervo-studio.js` (only if a clear win is found).

- [ ] **Step 1: Measure** in the live E2E (Task 5): time from `acervoStudioToggle()` to a
  fully rendered nav, and a scope switch. Record the numbers.
- [ ] **Step 2:** The known extra cost is the inbox-badge `_tree('inbox')` fetch on every
  `acervoStudioRenderNav`. It is best-effort and small; only cache it (per-open) if the
  measurement shows it dominates. Document the decision either way in the E2E report —
  no speculative optimization (YAGNI).
- [ ] **Step 3: Commit** only if a change was made.

---

### Task 4 — Docs: upstream-sync checkpoint + RFC §11 status

**Files:** create `docs/acervo-studio/UPSTREAM-SYNC.md`; modify `docs/rfcs/acervo-studio.md`.

- [ ] **Step 1:** Write `docs/acervo-studio/UPSTREAM-SYNC.md`: the current fork⇄upstream
  gap posture, the cherry-pick-not-rebase policy, why the Studio is rebase-safe by
  construction (new files + `/api/acervo/x/` prefix dispatch → 0 `routes.py` lines; the
  shared-file diff invariant asserted each phase), and the reapply-if triggers (the
  MOD-009 prefix dispatcher, the index.html include/mount area, the two globals the
  consolidation hook redirects). Point to `EXOCRTX_MODIFICATIONS.md` MOD-010 for touch points.
- [ ] **Step 2:** Update RFC `docs/rfcs/acervo-studio.md` §11: mark Phases 0–5 as
  **delivered** (with the merge/push state), and the §1 status line.
- [ ] **Step 3: Commit** `docs(acervo-studio): upstream-sync checkpoint + RFC §11 status (Phase 5 T4)`.

---

### Task 5 — Verification: live E2E + regression + rebase-safety

**Files:** none (verification only; `.superpowers/sdd/e2e-report-phase5.md`).

- [ ] **Step 1: Live E2E (Playwright)** against a fixture: (a) consolidation — the MOD-009
  `#axLauncher` is hidden and `window.acervoExplorerToggle` opens the Studio (not the
  docked `#acervoExplorerRoot`); the legacy fn is preserved on `__acervoExplorerToggleLegacy`.
  (b) a11y — `.axs-root` has `role=dialog`/`aria-modal`/`aria-label`; opening moves focus to
  the search box; Tab reaches a nav item; Enter/Space on a focused `.axs-ni` selects the
  scope; Escape closes and returns focus to the launcher. (c) perf timings recorded.
  Console clean.
- [ ] **Step 2:** Full pytest suite unchanged (154 MOD-010; no new failures vs baseline).
- [ ] **Step 3:** Rebase-safety diff EMPTY.
- [ ] **Step 4:** Record in `.superpowers/sdd/progress.md` + the E2E report.

---

### Task 6 — Governance: catalog + COLLAB + IDENTITY

- [ ] **Step 1:** `EXOCRTX_MODIFICATIONS.md` MOD-010 "Fase 5" bullet (consolidation +
  a11y + docs; 0 routes.py/index.html; acervo-explorer.* untouched).
- [ ] **Step 2:** umbrella COLLAB record
  `.harness/changes/2026-07-12_collab_hermes-webui-acervo-studio-phase5.md` + IDENTITY note.

---

## Self-review notes

- Spec coverage: brief Phase-5 scope — retire/redirect MOD-009 ✔ (redirect + hide, no
  acervo-explorer edit), a11y ✔ (dialog/Escape/focus/keyboard-nav), perf ✔ (measured
  check), upstream-sync note ✔, RFC §11 ✔.
- Rebase-safety preserved: MOD-009 is redirected, never edited.
- YAGNI: perf applies a change only if measurement warrants; consolidation is
  non-destructive (legacy escape hatch kept).
