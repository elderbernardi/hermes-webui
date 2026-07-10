# SPIKE — Hermes invocation mechanism (Acervo Studio Phase-2 gate)

> **Status:** RESOLVED — awaiting owner sign-off on the recommended pattern.
> **Gates:** RFC `docs/rfcs/acervo-studio.md` §6.2 risk #1 / §13 #1. No Phase-2 UI
> is built until the owner signs off on the invocation pattern below.
> **Date:** 2026-07-10 · **Method:** two read-only code investigations across
> `hermes-webui/` (server → Hermes path) and `exocortex.saas/` + the live
> `~/exocortex/acervo` (intake/memory/publish contracts). Every load-bearing
> claim is cited `file:line` and was spot-verified.

---

## 0. The question (verbatim from the RFC)

> §6.2: *"the exact Hermes invocation mechanism — synchronous structured turn vs.
> async job+poll. This determines whether triage/assist render inline or
> async-with-progress. Resolve before Phase 2."*

Plus the second-order question that the investigation forced open: **is the
`POST /v1/intake/*` "IntakeEnvelope HTTP contract" the RFC aligns to (§6.1, §13 #2)
actually real?**

---

## 1. TL;DR — the decision

**Use a synchronous, in-process, structured call. Render triage/assist inline. Do
NOT build an async job+poll runner.**

The Hermes agent already runs **in the same OS process** as the WebUI server
(imported as `from run_agent import AIAgent`). The server **already** makes
blocking, server-driven agent calls and parses their results for non-chat features
(git commit-message generation, chat-summary). That same primitive is exactly what
Phase-2 triage/assist need. The async job+poll machinery exists only as a
**default-off, undeployed seam** — using it now would be over-engineering.

Second finding, equally important: **the `POST /v1/intake/*` HTTP contract does not
exist.** It is aspirational prose in three markdown files. So Phase 2 does **not**
"drive an intake service" — it owns the envelope filesystem work directly (which is
allowed: *input is not memory*) and delegates only *cognition* and *semantic
writes* to Hermes.

---

## 2. How the server reaches Hermes (runtime coupling)

The WebUI server and the Hermes agent are **one process, one interpreter, one venv**.
The agent is a **library, not a service**.

- `bootstrap.py:101-208` — `discover_agent_dir()` locates the hermes-agent install
  (`HERMES_WEBUI_AGENT_DIR` → `$HERMES_HOME/hermes-agent` → siblings → `hermes` CLI
  shebang), prepends it to `PYTHONPATH`, and validates `from run_agent import AIAgent`
  before launch. It prefers the agent's own venv so both import sets coexist.
- Coupling is env-only: `HERMES_HOME` (default `~/.hermes`), a profile-scoped
  `state.db`, and per-turn env (`TERMINAL_CWD`, `HERMES_SESSION_KEY`, `HERMES_EXEC_ASK`).
- **What must be running for an agent call:** nothing extra — no sidecar, socket, or
  URL. Just (a) hermes-agent importable on `sys.path`, (b) provider creds resolvable,
  (c) a reachable LLM endpoint.

This is the crux: because the agent is in-process, a **blocking function call** is
the natural, already-proven invocation path. There is no network hop to make async.

---

## 3. The invocation channels that exist today

| Channel | Class | Evidence | Usable for Phase-2 cognition? |
|---|---|---|---|
| `AIAgent.run_conversation(...)` from a route | **SYNC-structured**, blocking, returns `{final_response, messages, …}` (tools available) | `routes.py:15571` (git-commit), `:9971` (summary), `:15069` (`/api/chat` sync fallback) | **Yes — recommended for triage/promote** |
| `agent.auxiliary_client` → `chat.completions.create(...)` | **SYNC-structured**, plain LLM completion, no tools/loop | `routes.py:9951`, `:15551` | **Yes — recommended for lightweight assist** |
| `POST /api/chat/start` + `/api/chat/stream` (live chat) | **ASYNC handle + SSE streaming-only** (NL `token.delta`) | `routes.py:14203-14355` spawns a daemon thread + `StreamChannel`; browser attaches SSE at `:7527` | No (streaming NL, not structured) |
| RuntimeAdapter `runner-local` / `HttpRunnerClient` | **ASYNC job+poll** over HTTP to an *external* runner | `runtime_adapter.py:105-143` (default `legacy-direct` = None), `runner_client.py:53` (`from_env` raises when `HERMES_WEBUI_RUNNER_BASE_URL` unset → route returns **501**) | No — default-off, runner not deployed |
| WebUI-hosted MCP (`mcp_server.py`) | Project/session **CRUD**, direction **Hermes → WebUI** | `mcp_server.py:454-533` exposes only list/create/rename/move/delete | No — wrong direction, no agent-run tool |

**"Structured" caveat (applies to both sync primitives):** neither returns typed
JSON natively. "Structured" today = **prompt-for-JSON + server-side parse** — exactly
what `_handle_git_commit_message` already does (`routes.py:15580-15598`: run the
agent, take `final_response` text, post-process into `{"ok": true, "message": …}`).
That is sufficient for triage/assist proposals; the JSON contract is enforced by
prompt + parser (+ a schema validator we add), not by the runtime.

---

## 4. The intake / memory / publish contracts — what is real

The RFC's §6.1 endpoint list implies an intake HTTP service and canonical tools.
On disk, most of that is **aspirational**. This changes the Phase-2 architecture.

| Surface | Reality on disk | Can the server drive it directly? |
|---|---|---|
| **Intake** (`POST /v1/intake/*`, envelope create/extract) | **Does not exist as code.** `/v1/intake/*` is prose in `excrtx-memory-intake/SKILL.md:144-160` + `references/intake-control-plane-seed.md`; even the "canonical tool" `intake_ingest.py` is **absent everywhere** (verified `find` → nothing). Today the agent hand-builds `_inbox/incoming/{id}/` per the skill. | **No service to call** — but the envelope is *just files*, so the server can write them itself (see §5). |
| **`_inbox` lifecycle** | Pure filesystem convention, **no daemon**. Envelope = a **directory** `_inbox/incoming/{intake_id}/` with `original/`, `derived/`, `manifest.json` (status: `received`→`extracted`→promoted), `routing.json`. Live sample: `_inbox/incoming/int_20260616_open-notebook/`. | Yes — server owns this dir with `_safe_acervo_path` (input ≠ memory). |
| **Semantic write** (`excrtx-memory-manager`) | Authority is an **agent-run skill** (`SKILL.md`, v2.2.0), **but** a real CLI exists: `exocortex.saas/scripts/acervoctl.py` with two-phase **`prepare-write`** (line 112) → **`commit-write`** (line 122) = machine-runnable *propose-then-approve*. **Caveat:** acervoctl lives in the **source repo only**, not provisioned into `~/.hermes`. Scope guard + OKF frontmatter + deprecate-hook (ADR-016) enforcement live in the skill's WRITE op. | **Not yet** — CLI not on the runtime path; default path stays **agent-mediated** via `run_conversation`. |
| **Publish** (`artifact_publish.py` + `harness/validate_artifact_manifest.py`) | **Real Python CLIs**, `artifact_publish.py` **is** provisioned (`~/.hermes/acervo/global/tools/`). `publish` uploads to Google Drive (SHA-256 receipts). Validator gates on antislop ≥ 35/50 + taste, skipped for `draft`. **Draft-First is hardcoded** `"visibility":"private"` (lines 282/313/362); **no `--public`/`--share` flag exists.** | **Yes** — server can shell out to both (needs Drive creds; public-share = a *future* approval step, not in the tool). |

---

## 5. Resulting Phase-2 architecture (the pattern to sign off on)

The governance rail is **"the GUI never writes semantic memory or calls cognition
directly — Hermes does, server-mediated, propose-then-approve"** and **"uploads land
in `_inbox` (input is not memory)."** Combined with §2–§4, that resolves each step to
a concrete, minimal-risk mechanism:

```
① CAPTURE   upload / paste / link
            → SERVER writes _inbox/incoming/{id}/ envelope directly (files, not memory)
            → works with Hermes OFFLINE. No agent. Reuses _safe_acervo_path + fm helpers.

② TRIAGE    "classify + propose routing"
            → SERVER → Hermes  SYNC in-process  (acervo_studio_agent.run_conversation)
            → JSON proposal (destination scope/nature/title) → parsed + schema-validated
            → rendered INLINE in the assistant panel. Hermes offline ⇒ "agente offline".

③ PROMOTE   owner confirms routing
            → SERVER → Hermes  SYNC in-process, agent runs excrtx-memory-manager WRITE
              (the sanctioned semantic-write path: scope guard, OKF, ADR-016 deprecate)
            → envelope moves _inbox/incoming → _inbox/promoted.
            (Future optimization: shell out to acervoctl prepare-write/commit-write
             ONCE it is provisioned into the runtime — do NOT depend on it in Phase 2.)

④ PUBLISH   (Phase 3, not this spike)
            → SERVER shells out to artifact_publish.py + validate_artifact_manifest.py
              directly. Draft-First/private only until a public-share approval step is added.
```

Key consequence: **triage and assist are inline** (sync). No progress bars, no
polling, no SSE, no job queue. The only long-ish call is `run_conversation`, run in
the request thread exactly like the existing git-commit handler.

---

## 6. What Phase 2 must BUILD (glue, not plumbing)

The transport already exists, so this is wiring:

1. **`api/acervo_studio_agent.py`** (new file — confirmed **does not exist yet**): a
   thin mediation layer that wraps a blocking `run_conversation` (or `auxiliary_client`)
   call with (a) a JSON-proposal prompt, (b) a parser, (c) a schema validator, and
   (d) the graceful-offline guard. This is the RFC §6.2 module.
2. **`x/intake/{upload,text,link,triage,promote}`** POST routes, delegated from the
   existing MOD-009 `/api/acervo/x/` prefix dispatcher into `handle_studio_post`
   (currently a stub, `acervo_studio.py:179-180`). **Zero new `routes.py` lines.**
3. Envelope read/write helpers for `_inbox/incoming/{id}/` (manifest + routing +
   original + derived), reusing `_safe_acervo_path`.
4. Frontend `intake` unit in `static/acervo-studio.js` (`.axs-*` namespace): capture
   form, inline triage proposal card, promote confirm.

**Nothing to build:** no new invocation transport, no runner backend, no async queue,
no `/v1/intake` HTTP service, no `intake_ingest.py`.

---

## 7. Graceful degradation (already supported)

- Import guard: `try: from run_agent import AIAgent except ImportError: AIAgent = None`
  (`streaming.py:368-371`); `_get_ai_agent()` retries at call time.
- Worker fail-fast with a rich diagnostic when the agent is unavailable
  (`streaming.py:6172-6174` + `1209-1253`); health probes in `api/agent_health.py`.
- Pattern for the mediation layer: catch the import/availability failure and return a
  structured `{ offline: true }` so the UI shows *"agente offline — tente novamente"*
  while **capture, read, edit, download, stage-to-chat keep working** (RFC §9).

---

## 8. Open decisions for owner sign-off

1. **Invocation pattern — sync inline (recommended) vs async job+poll.**
   Recommendation: **sync inline.** Async would require provisioning an external
   runner that does not exist and buys nothing while the agent is in-process.
2. **Intake HTTP contract — adopt `/v1/intake/*` (doesn't exist) vs server-owns-envelope
   (recommended).** Recommendation: **server owns the `_inbox` envelope filesystem work
   directly**; treat the `/v1/intake/*` prose as a *future* external-channel control
   plane, not a Phase-2 dependency. (RFC §13 #2 already frames it as "proposed".)
3. **Promote write path — agent-mediated `run_conversation` (recommended now) vs shell
   out to `acervoctl.py`.** Recommendation: **agent-mediated now**; revisit acervoctl
   once it is provisioned into `~/.hermes`. Either way, `excrtx-memory-manager` remains
   the only sanctioned semantic-write authority.
4. **Promote visibility (RFC §13 #3): background structured call vs visible chat turn.**
   Recommendation matches the RFC: **background by default**, with an "abrir no chat"
   escape hatch for complex cases.

**A "yes" on #1 + #2 is the minimum needed to unblock the Phase-2 plan.**

---

## Appendix — evidence index

**hermes-webui (server → Hermes)**
- In-process agent import + PYTHONPATH: `bootstrap.py:101-208`
- Sync structured calls in use: `api/routes.py:15571` (git-commit), `:9971` (summary),
  `:15069`/`:15136` (`/api/chat` sync fallback); aux client `:9951`, `:15551`
- Live chat = async handle + SSE: `api/routes.py:14203-14355`, `:7527`;
  worker `api/streaming.py:5128`, `:6172-6174`
- Async seam (default-off): `api/runtime_adapter.py:105-143`, `api/runner_client.py:53`,
  501 at `api/routes.py:10717-10721`; contract `docs/rfcs/hermes-run-adapter-contract.md`
- MCP (CRUD, Hermes→WebUI): `mcp_server.py:454-533`, `:560-567`
- Phase-2 stubs: `api/acervo_studio.py:179-180`; `api/acervo_studio_agent.py` **absent**
- Note: `api/agent_sessions.py` (an RFC-named suspect) is only a `state.db` read helper —
  no turn-execution code.

**exocortex.saas + live acervo (contracts)**
- Intake skill (agent-run, no service): `skills/excrtx-memory-intake/SKILL.md`
  (envelope shape `:109-128`, lifecycle `:87-98`/`:201-262`, `/v1/intake` "seed" `:144-160`)
- `intake_ingest.py` **absent** (verified `find` across `~/exocortex`, `~/.hermes`,
  `exocortex.saas`); `/v1/intake` string only in SKILL.md + references + dogfood baselines
- Memory-manager skill: `skills/excrtx-memory-manager/SKILL.md` (surfaces `:106-119`,
  WRITE op `:204-303`); real CLI `scripts/acervoctl.py` (`prepare-write:112`,
  `commit-write:122`) — **source-repo only, not provisioned**
- `_inbox` sample envelope: `~/exocortex/acervo/_inbox/incoming/int_20260616_open-notebook/`
- Publish CLIs: `~/exocortex/acervo/global/tools/artifact_publish.py` (private hardcode
  `:282/:313/:362`, no `--public`) + `global/tools/harness/validate_artifact_manifest.py`
  (antislop < 35 fails)
