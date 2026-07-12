# Acervo Studio (MOD-010) — Go-live checklist

> The Studio (Phases 0–5) is merged to `exocortex/stable` and pushed to the fork origin
> (`elderbernardi/hermes-webui`). The **running** instance is the provisioned
> `~/.hermes/hermes-webui/` copy on `127.0.0.1:8787`, which still serves **Phase 1** —
> it has NOT been reprovisioned this round. Every step below is **OWNER-GATED**: the
> agent will not run any of them without an explicit owner OK.

Until go-live, the Studio degrades calmly: navigate / read / edit / download / capture
all work; the agent- or Drive-dependent features (triage, promote, publish, assist, ask)
show a calm "offline / não configurado" state instead of failing.

---

## What already works with no provisioning
- Navigate (all scopes incl. `micro`/`inbox`), read, inline edit (OKF-preserving via
  `x/save`), move/status/tags, download (md/raw/artifact-zip), stage-to-chat.
- Intake **capture** (text/link/file → `_inbox/incoming/{id}/`) — agentless.
- The whole surface is session-gated and path-safe (`.quarantine`/traversal unreachable).

## Gate A — Semantic promote (Phase 2b) needs the acervo control plane
`promote` writes a page via the `acervoctl` control plane, which is **not** provisioned
into `~/.hermes`. The runnable copy is `~/.exocortex-installer/scripts/` (has
`acervoctl.py` + `acervo_semantic_core.py`).
- [ ] Set **`EXOCORTEX_SCRIPTS_DIR`** in the WebUI runtime env to a dir containing
  `acervoctl.py` + `acervo_semantic_core.py` (the module resolves `EXOCORTEX_SCRIPTS_DIR`
  → `~/.exocortex-installer/scripts` → `~/exocortex/scripts`).
- [ ] Verify: promote a fixture envelope → a page appears in `micro/{slug}/{nature}/` with
  a `_meta/log.md` CREATED entry + a receipt. (Never against the real acervo without OK.)

## Gate B — Publish outbound (Phase 3) needs the publish CLIs + Google Drive creds
`publish` shells to `global/tools/artifact_publish.py` + `harness/validate_artifact_manifest.py`.
- [ ] Ensure the acervo's `global/tools/` (with `artifact_publish.py` and
  `harness/validate_artifact_manifest.py`) is reachable in the runtime — the module
  prefers the served acervo's own `global/tools`, then `~/.hermes/acervo/global/tools`,
  then `~/exocortex/acervo/global/tools`.
- [ ] Provision **Google Drive credentials** — the `google_api.py` driver
  (skill `productivity/google-workspace`) + its auth — in the runtime. Without it,
  publish degrades to "Drive não configurado" (HTTP 200, calm).
- [ ] **Public sharing stays owner-gated:** `artifact_publish.py` hardcodes
  `visibility:"private"` and has no public flag; the Studio refuses `visibility:"public"`
  by design. Enabling public share is a separate, future, owner-approved change — do NOT
  work around it.
- [ ] Verify: prepare shows the real antislop gate; publish a fixture draft → a private
  Drive folder + a SHA-256 receipt in `receipts/`.

## Gate C — Assist + Ask (Phase 4) need provider credentials
`assist`/`ask` run a tool-less in-process Hermes turn.
- [ ] Ensure the runtime has a reachable LLM endpoint + provider creds for the active
  profile (the ecosystem LLM is DeepSeek `deepseek-v4-pro` via `DEEPSEEK_API_KEY`, or
  whatever the profile resolves). Without it, assist/ask degrade to "agente offline".
- [ ] Verify: assist summarize returns a proposal; ask returns a grounded answer whose
  sources are real acervo paths.

## Gate D — Reprovision the running instance (the actual go-live)
The changes are in the repo; the running `~/.hermes/hermes-webui/` copy must be updated.
- [ ] **OWNER DECISION:** push is already done (fork origin `exocortex/stable` @ the Phase-5
  merge). Reprovision `~/.hermes/hermes-webui` to that HEAD:
  `git -C ~/.hermes/hermes-webui fetch origin && git -C ~/.hermes/hermes-webui merge --ff-only origin/exocortex/stable`
  then `~/.hermes/hermes-webui/ctl.sh restart`.
- [ ] ⚠️ **Security note before exposing writes:** prod :8787 serves the REAL acervo with
  no auth. The Studio now carries capture + agent-mediated semantic write (promote) +
  publish + assist/ask. Confirm the owner accepts that surface on an unauthenticated local
  port (or add auth) BEFORE reprovisioning. The write boundary itself is defended
  (micro-scope only, `.quarantine`/traversal unreachable, propose-then-approve, Draft-First,
  proposal-only assist), but the endpoints are unauthenticated like the rest of :8787.
- [ ] Verify live: the served `acervo-studio.js` has the Phase-5 consolidation hook; the
  MOD-009 launcher is redirected; publish/assist/ask behave per Gates A–C.

## Other standing owner gates (unchanged, do NOT do without an OK)
- **Umbrella push is BLOCKED** by a pre-existing 836 MB backup tarball versioned in commit
  `d28175a` (GitHub rejects it). The umbrella governance commits (COLLAB records + IDENTITY)
  are committed **locally** on `master` but not pushed. Flag; do not fight it.
- **HW-1 upstream re-founding (Strategy C)** incl. the latent terminal-RCE fix — its own
  focused session; see `EXOCRTX_MODIFICATIONS.md` "HW-1".
- Any write test against the **real** `~/exocortex/acervo` — always fixture-only without an OK.
