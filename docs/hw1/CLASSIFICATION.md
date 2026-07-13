# HW-1 — Shared-file hunk classification (REAPPLY vs DROP)

> P1.1 output, 2026-07-13. Payload = `git diff upstream/master...exocortex/stable -- <file>`
> (fork-side additions since merge-base v0.51.448). Verdict rule: distinctive added
> symbol already in `upstream/master` (now `exp-v0.52.61`, tip `d486394f`) → DROP
> (cherry-picked fix that upstream absorbed); absent → REAPPLY (MOD layer).

| File | Payload | Verdict | Evidence |
|---|---|---|---|
| `api/profiles.py` | +351 | **DROP (entire)** | #3961/#4544 credential-scrub family — `_BLOCKED_RUNTIME_ENV_KEYS`, `filter_runtime_env_for_gateway_parity`, `_profile_secret_env_names`, `profile_env_for_active_request_readonly` all present upstream |
| `server.py` | +34 | **DROP (entire)** | #4727 TLS accept-loop fix — `def get_request` + `do_handshake_on_connect` present upstream |
| `api/config.py` | +286 | **DROP caching hunks; REAPPLY MOD-001** | `_yaml_file_cache_lock`/`_load_yaml_config_file_raw` (#4650/#4662) present upstream; only the 2 `excrtx` skin-registry lines are fork-layer |
| `static/i18n.js` | +268 | **REAPPLY (all)** | MOD-002/005/006 — `excrtx` absent upstream; hunks = skins list (top), `cmd_theme` per-locale string, PT-BR block |
| `static/style.css` | +203 | **REAPPLY (all)** | MOD-004 skin block (@652, 87 lines) + MOD-007/008 `.workspace-acervo`/`.workspace-artifact-*` blocks — absent upstream |
| `static/index.html` | +63/−42 | **REAPPLY (all, split by phase)** | MOD-003 shell/rebrand (P1.3) + MOD-007/008 tab ruler (P2.3) + MOD-009/010 includes/mounts (P3.1) — `EXCRTX`/`acervoStudioRoot` absent upstream |
| `static/ui.js` | +222 | **REAPPLY (all)** | MOD-008 — `renderStagedContextChips`, `_refreshInboxBadge`/`_isInboxPath`/`_promptInboxMove`, `_aColors`, `S.pendingContextAttachments` — absent upstream |
| `static/workspace.js` | +126 | **REAPPLY (all)** | MOD-007/008 acervo tab wiring (`workspaceAcervoTab`, `workspaceAcervo` panel, `renderAcervo` calls) — absent upstream |
| `static/sessions.js` | +3 | **REAPPLY (all)** | MOD-008 `_refreshActiveWorkspaceTab` hook — absent upstream |
| `api/routes.py` | +850 | **→ P2 extraction** | ~620-line MOD-007/008 block (12061–12661) + dispatch lines → `api/acervo_tab.py`; residual hunks (e.g. ~9-line credential wrapper) re-classified during P2 with the same rule |

Security triage notes (P4 inputs):
- Terminal-RCE gate (`d257e5f3`+`34342b9f`): **present upstream** → nothing to do (verify only).
- CORS `do_OPTIONS` `*`: check the new upstream; adapt to the fork CSRF model only if still `*`.
- Upstream `package.json` already has `lint:runtime` + eslint guard config → not fork-only anymore; compare configs in P3.
