# HW-1 Re-founding — verification report

Branch `exocortex/stable-v2` off `upstream/master` (exp-v0.52.61). Fork base was v0.51.448.

## Test gates (baseline-relative)
- **P0 baseline** (pristine upstream): 12,823 pass; **2 env failures** persist on pristine
  upstream too (`test_tls_aware_probe.py` self-signed/insecure-optin — TLS-probe env, not code).
- **P1 gate** (skin/i18n): green after re-anchoring the 16 MOD-007/008 en keys into ALL
  locales (v0.52 added per-locale coverage tests) + keeping upstream's `_workspacePanelActiveTab`
  literal-marker line for the 4582 escape-nav tests.
- **P2+P3 gate**: **12,982 passed**, 94 skipped; only the same **2 env TLS-probe fails**
  remain serially (zero NEW vs baseline). `lint:runtime` clean.
- **MOD-010 acervo suite: 154/154** on the re-founded base.

## Extraction (P2)
- MOD-007/008 backend moved verbatim into `api/acervo_tab.py` (751 lines): 14 acervo/artifact
  handlers + `_handle_inbox_status`/`_handle_inbox_move`, core helpers rewritten to `routes.<name>`.
- routes.py acervo surface ≈ 30 lines: 2 dispatch delegations + bottom re-export block.
  (Fork had ~627 inline lines — the durable HW-1 win: future upstream sync no longer conflicts
  in routes.py for the acervo tab.)
- Import cycle safe both directions (`import api.acervo_tab` and `import api.routes` — verified).

## Live smoke (disposable fixture + temp HERMES_HOME + fixture ACERVO; real acervo UNTOUCHED)
- **Isolation verified BEFORE any write**: `x/tree` returns fixture pages only, no real-acervo leak.
- **EXCRTX shell renders**: title "EXCRTX.IA", `data-skin=excrtx`, excrtx logo, Acervo tab,
  Studio launcher; boot theme default `dark`. **0 console errors** (after copying the missed
  fork-only `static/friendly.js` — found by the smoke's 404).
- **MOD-007/008 endpoints** all 200 via `acervo_tab.py`: microverses (count 1),
  artifacts, knowledge, titles, inbox/status.
- **MOD-009 Explorer + MOD-010 Studio full chain LIVE** (deepseek provider):
  - capture → envelope written to fixture `_inbox` ✓
  - triage → real proposal `micro/cliente-x/contracts` "Preço cotado…" ✓
  - assist summarize → "O preço tabelado do produto X é R$ 10." ✓
  - ask → grounded "O desconto máximo padrão permitido é de 10 por cento." citing
    `global/decisions/politica-preco.md` ✓
  - publish/prepare → real antislop gate `gate.ok`, `can_publish` ✓; publish degrades
    calmly to `drive_unconfigured` (no Drive creds) ✓
  - promote control plane resolves + runs via `EXOCORTEX_SCRIPTS_DIR` (Gate A) ✓
  - Studio dialog opens (role=dialog, 6 keyboard-operable scopes — Phase-5 a11y intact) ✓
- Note: the agent was first offline because the isolated profile resolved provider
  `openai-codex` (no key); forcing `deepseek` (which has a key in ~/.hermes/.env) made all
  cognition live. **Not a re-founding regression** — every agent-seam symbol resolves on
  v0.52 (`api.config`/`api.oauth`/`run_agent`/`api.profiles` all present); graceful offline
  (HTTP 200, never 500) held identically to the fork.

## Security triage (P4.1) — zero changes needed
- Terminal-RCE gate (`d257e5f3`+`34342b9f`): **already in v0.52** — `_handle_terminal_start`
  calls `_embedded_terminal_gate_allows` → 403; `tests/test_cvd3_terminal_local_origin_gate.py` present.
- CORS: v0.52 `do_OPTIONS`/preflight echoes Origin only via `_check_same_origin_browser_request`,
  `Vary: Origin`, never `*`.

## Fork-owned byte-identity
- The 10 fork-owned files + the MOD-010 suite: `git diff exocortex/stable exocortex/stable-v2`
  EMPTY (byte-identical).
