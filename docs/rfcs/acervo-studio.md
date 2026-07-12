# Acervo Studio — Design Spec

> **Proposed MOD-010** (successor surface to MOD-009 Acervo Explorer). A fresh,
> premium, AI-native full-screen surface inside `hermes-webui` for the whole
> Exocórtex acervo lifecycle: **navigate · edit · upload · publish · download**,
> with the Hermes agent woven in as the cognition engine.
>
> - **Status:** **DELIVERED (Phases 0–5, 2026-07-12)** — merged to `exocortex/stable` and
>   pushed to the fork origin. Not yet reprovisioned to the running :8787 instance
>   (owner-gated go-live; see `docs/acervo-studio/GO-LIVE-CHECKLIST.md`). Original design
>   brainstorm-approved 2026-07-02.
> - **Author:** Fable (Opus 4.8) with the operator.
> - **Change mode:** COLLAB (write-coupling to the Exocórtex-governed acervo).
> - **Builds on:** the MOD-009 `/api/acervo/x/` backend + the MOD-007/008 chat-context bridge.
> - **Supersedes (eventually):** the MOD-009 docked panel front-end, once Studio reaches parity.

---

## 1. Vision & problem

The acervo is the Exocórtex's **structured cognitive memory** — a four-layer wiki
(`macro` soul · `global` ops · `micro/<slug>` domains · `shared` bridge) plus
operational scopes (`_inbox` capture · `_artifacts` deliverables · `.quarantine`
deletion staging). Today the operator can browse/edit it through MOD-009's docked
panel, but there is **no first-class way to get raw material *in*, curate it into
memory, ship deliverables *out*, or do any of it with the agent's help.**

**Acervo Studio** turns the acervo into a curation *cockpit* where the human is the
**curator-approver** and Hermes is the **co-processor**. It maps the operator's five
verbs onto the acervo's own native pipeline rather than inventing new concepts:

| Verb | Native acervo flow | Reuse / new |
|---|---|---|
| **Navigate** | Unified browse across `macro/global/shared/micro/artifacts/_inbox` + semantic search | extend MOD-009 (`micro`+`inbox` become first-class tree scopes) |
| **Edit** | In-place body+frontmatter, tags, status, move — OKF-preserving | reuse MOD-009 write surface |
| **Upload** | Drop → `_inbox/incoming/` (raw material preserved; *"input is not memory"*) | **new** (intake) |
| **Publish ①** | **Inbox → page**: Hermes triages → operator confirms → agent writes via `excrtx-memory-manager` | **new** (agent-mediated) |
| **Publish ②** | **Artifact → Drive**: quality gate → Draft-First → SHA-256 receipt | **new** (wraps `artifact_publish.py`) |
| **Download** | Export page/artifact out (md / raw / zip) | extend `/raw` |

---

## 2. Goals & non-goals

**Goals**
- A premium, ergonomic, self-contained full-screen surface that feels *calm by
  default, cockpit on demand* and reads as authentically Exocórtex.
- **Two meaningful decisions per item, max** (approve · publish); everything else is
  automatic and logged. The system's real state machines run *underneath* the UI.
- Hermes present in curation (triage, draft, contradiction, rewrite, quality gate) —
  **server-mediated**, propose-then-approve, never GUI-direct cognition.
- **Rebase-safe coexistence** with the still-developing upstream (607 commits ahead;
  `routes.py`/`ui.js`/`style.css` are the hot conflict zones).

**Non-goals**
- No graph/map as the *primary* navigator (the acervo is a tiered wiki with hard
  microverso isolation, not a graph). A graph is a possible *secondary lens* later.
- No direct GUI writes that bypass governance: **no create-new semantic page** except
  through agent-mediated intake promotion; **no delete**; `.quarantine/` stays unreachable.
- No acervo-wide "sync". "Publish" is only artifact→Drive (Draft-First) and the
  inbound inbox→page promotion. Not git, not remote mirroring.
- Not a rewrite of the chat surface. Studio and chat stay decoupled (§7).

---

## 3. The simplified lifecycle model

The governance states (`draft→ready→approved→ask-publication→published`,
`volátil→perene`, `deprecate→quarantine→purge`, the OKF frontmatter machinery)
**exist in the data** but are rendered as *progress indicators the agent advances*,
not steps the human operates.

```
 ① CAPTURE  ───────────▶  ② CURATE  ───────────▶  ③ PUBLISH (out)
 (automatic)              (one approve)            (one confirm)

 upload / paste / link /  Hermes proposes:          "Publish to Drive" →
 "save from chat"         "knowledge · comercial,    quality gate + Draft-First
   → _inbox/incoming       here's the draft" →       run underneath →
   → Hermes extracts +     Approve (or tweak         one confirm → receipt
     drafts a triage       routing/body) → agent
     hypothesis            writes via
   NO decision yet         excrtx-memory-manager
```

- Editing an existing page rides the **Curate** surface: edit → save (OKF-preserved).
  Marking **perene** or **ready** is one inline toggle, not a pipeline.
- The full "I edited this → it's in Drive" path is **edit → Publish → one confirm**.
- Cognition (extract, triage, draft, contradiction-check, rewrite) is always Hermes,
  server-mediated, **propose-then-approve**. Nothing writes to memory without one click.
- Escape hatch honored: *"input is not memory"* — every intake can resolve to
  keep-in-inbox / become-a-task / become-an-artifact instead of a page.

---

## 4. Information architecture

**One unified navigator** (fixes today's split where `micro/` lives on the older
`/api/acervo/microverses`+`/knowledge` endpoints, separate from the `x/tree` scopes):

```
ACERVO
├─ 🧠 Soul        macro/         identity · values · tone   (perene, rarely touched)
├─ 🌐 Global      global/        universal ops · 11 natures
├─ 🔗 Shared      shared/        cross-refs · glossary · groups
├─ 🪐 Microversos micro/<slug>/  comercial · sales-ai · excrtx … (per-domain worlds)
├─ 📦 Artefatos   _artifacts/    deliverables (by status / microverso / type / task)
└─ 📥 Inbox       _inbox/        capture queue (incoming → curated)   ← NEW
   (.quarantine/ never shown — off-limits by design)
```

- **Natures** (11, from `_ACERVO_NATURES`): context, knowledge, contracts, workflows,
  decisions, templates, tools, skills, persona, prompts, reflections. (`raw/`,
  `_archive/`, `_meta/` are shown as structural, not editable natures.)
- A page's `nature` must equal its directory — enforced on any agent write.
- Hard microverso isolation is respected: no cross-microverso wikilink UI; cross-domain
  references route through `shared/`.

---

## 5. Surface & interaction design

### 5.1 Shape — Library & Reader + pinnable assistant
A self-contained **full-screen view inside the existing SPA** (not a separate
document), toggling with Chat. Two-pane by default:

- **Left navigator** — the unified scope tree; a selected scope/nature expands its page
  list inline (Notion/Linear-style). Inbox carries a needs-triage count badge.
- **Reader/Editor** — the focused document: breadcrumb, OKF frontmatter chips
  (`nature`, `🔒 perene`, `status`, tags), serif body for reading, inline editor for
  writing. Quiet toolbar: **Editar · Enviar ao chat · Baixar · ⋯**.
- **Assistant (`✦ Hermes`)** — *not a permanent column.* Calm by default (a quiet edge
  tab). It **self-summons** when there's cognition to surface (a fresh inbox item, a
  contradiction on save, a publish gate) and can be **📌 pinned** into a persistent
  right rail for a curation session, then recedes.
- **Command bar** (`⌘K`) — "Perguntar ou buscar no acervo…": semantic search +
  command palette + "ask the acervo".

### 5.2 Visual identity — Exocórtex, ergonomic
- **Palette: "Graphite Neutral"** — a near-neutral dark graphite field (`#1b1d21` bg,
  `#202226` rails, `#26292e` surfaces, `#32353b` borders), neutral-cool ink (`#d7d8db`,
  strong `#f0f1f3`, muted `#888b93`). Chosen over the stock EXCRTX deep-navy (`#181f30`)
  because a saturated navy field with steel text + saturated blue accent is fatiguing
  over long sessions. **The identity lives in the accent, not the field.**
- **Accent: EXCRTX blue `#3b8af0`**, reserved strictly for *decisions and the agent*
  (primary action, triage proposal, Aprovar, needs-triage badge, active nav). `perene`
  reads as a calm blue `🔒`; `ready` is the only green (`#7EC98C`); metadata stays
  steel-muted. **One accent at a time** (Calm Console law).
- **Theme is user-selectable and honors the app's existing Theme control**
  (`System / Dark / Light`) + Skin — the Studio reads the same global theme/skin the
  operator already sets in Settings, so switching there flips the Studio too. Default
  **follows the OS**.
  - **Light mode follows the *current* web-ui palette (EXCRTX light) verbatim** —
    off-white field `#f4f5f8`, white surfaces `#ffffff`, navy ink `#03123f`, muted
    `#8f8a91`, blue accent `#1376ed` (`accent-text #0e5fd6`), success `#38A169`. The
    Studio's light theme *is* the app's light theme, not a bespoke palette.
  - **Dark mode is the ergonomic "Graphite Neutral"** variant above — our tuned
    replacement for the fatiguing stock EXCRTX deep-navy, keeping the blue as accent only.
  - Implementation: the `.axs-*` shell resolves its tokens from the app's
    `:root[data-skin]` / `.dark` state (light → current EXCRTX light vars; dark →
    Graphite overrides), so a Settings theme/skin change reflows the Studio with no
    separate control. Dim-dark + light, OS-followed, is the most ergonomic answer.
- **Type** — sans (`system-ui`) for UI; serif (Georgia) for document titles/body
  reading. Mono for paths/receipts/metadata.
- **CSS namespace `.axs-*`**, own shell — never touches upstream's chat CSS.

### 5.3 Flow ① — upload → triage → approve (detail)
1. **Capturar** *(automatic)* — drop a file / paste text / drop a link / "salvar do
   chat" → an intake envelope `int_YYYYMMDD_HHMMSS_slug/` under `_inbox/incoming/` with
   `original/` preserved. Hermes runs extraction (audio→transcript, pdf→md/ocr,
   image→ocr+desc, zip→inventory, link→snapshot) → `derived/`.
2. **Triar — Hermes propõe** *(the one gate)* — a structured proposal: hypothesis,
   **editable routing** (`microverso ▾ · nature ▾ · class ▾`), a drafted-page preview,
   suggested tags → **Aprovar / Ajustar**, plus the *"não é memória?"* branch
   (keep-in-inbox / task / artifact).
3. **Salvo** *(automatic)* — on approve, **the agent writes the page via
   `excrtx-memory-manager`** (ontology + scope validation, contradiction-deprecation,
   `index.md`/`log.md` update, Hindsight index). The GUI never writes the new page itself.

### 5.4 Flow ② — edit → publish → Drive (detail)
1. **Editar & publicar** — edit the deliverable → **⇪ Publicar no Drive**. Hermes
   assembles the artifact package (`source/` + `exports/`, manifest).
2. **Verificar & confirmar** *(the one gate)* — the **quality gate** (`check_antislop`
   ≥35/50, `check_taste`) and **Draft-First** target are shown; visibility choice
   **🔒 Privado** (= delivery, allowed) vs **🌐 Compartilhar** (requires explicit
   approval) → one **⇪ Publicar**. On gate failure (non-draft): block + surface issues +
   "Revisar".
3. **Publicado** *(automatic)* — `artifact_publish.py` uploads to Drive, computes
   SHA-256, writes `receipts/receipt.google_drive.json`, sets `manifest.status =
   published`, records the `publication.drive` block. UI shows the receipt + open/copy-link.

---

## 6. Backend architecture

All new endpoints live under the existing **`/api/acervo/x/`** prefix, which
`routes.py` already dispatches to `acervo_explorer.handle_acervo_x_{get,post}`
(MOD-009). **Net-new `routes.py` lines for MOD-010: zero.**

### 6.1 New module `api/acervo_studio.py`
Keeps MOD-009's `acervo_explorer.py` focused; the MOD-009 dispatcher delegates the new
sub-paths to it (a small edit to a fork-owned file, zero upstream risk). Reuses all
MOD-009 helpers (`_safe_acervo_path`, frontmatter split/merge/dump, `_acervo_root`,
`_ACERVO_NATURES`, `_ACERVO_UI_STATUSES`, response helpers).

**Navigate (extend)**
- `GET x/tree` — add `scope=micro` (unify with `/microverses`+`/knowledge`) and
  `scope=inbox`. `micro` becomes a first-class tree scope.

**Intake (new)** — aligns with the `excrtx-memory-intake` `IntakeEnvelope` HTTP contract:
- `POST x/intake/upload` (multipart) · `POST x/intake/text` · `POST x/intake/link`
  → create envelope in `_inbox/incoming/`, preserve original, kick off extraction.
- `GET  x/intake` — list inbox items + status (received/processing/proposed/promoted).
- `GET  x/intake/{id}` — envelope detail + the current Hermes triage proposal.
- `POST x/intake/{id}/triage` — (re)run triage (server → Hermes) → proposal.
- `POST x/intake/{id}/promote` — confirm routing → **agent writes** page/task/artifact
  via `excrtx-memory-manager`; envelope → `_inbox/promoted/`.

**Publish (new)** — wraps the canonical `global/tools/artifact_publish.py`:
- `POST x/publish/prepare` — assemble artifact + run `validate_artifact_manifest.py`
  (antislop/taste gate) → `{gate, drive_target, visibility_options}`.
- `POST x/publish` — confirm → `artifact_publish.py publish` (Draft-First enforced;
  public sharing requires an explicit approval flag) → receipt.

**Download (new/extend)**
- `GET x/download?path=…` (md/raw) · `?artifact_id=…` (zip via existing `/api/artifact/zip`).
  Same `_safe_acervo_path` gating + `nosniff`/sandbox CSP as MOD-009 `/raw`.

**Assist (new, read-only cognition)**
- `POST x/assist` — `{op: rewrite|summarize|suggest_tags|contradiction_check, ...}`
  → server → Hermes → **proposal only** (never writes). Applied edits to *existing*
  pages go through MOD-009 `x/save`; new pages go through intake promotion.

### 6.2 Hermes-in-the-loop mediation — `api/acervo_studio_agent.py`
A thin server-side mediation layer (`USER → GUI → SERVER → HERMES`). The GUI **never**
calls cognition or writes semantic memory directly. This module:
- Accepts a **structured task** (triage envelope / promote routing / assist op).
- Invokes the Hermes runtime and returns a **structured proposal**.
- For writes, routes through `excrtx-memory-manager` (ontology/scope/deprecation
  enforcement), which is the *only* sanctioned semantic-write path.
- Degrades gracefully when Hermes is unavailable (see §9).

> **Implementation spike required (risk #1):** the exact Hermes invocation mechanism —
> synchronous structured turn vs. async job+poll. This determines whether triage/assist
> render inline or async-with-progress. Resolve before Phase 2. (`api/agent_sessions.py`,
> `mcp_server.py`, `bootstrap.py` are the entry points to evaluate.)

### 6.3 Sanctioned write boundary (unchanged governance)
- **Edit existing page** → GUI-direct, bounded, OKF-preserving (MOD-009 `x/save`). OK.
- **Create new page** → agent-mediated only (intake promote). Never GUI-direct.
- **Delete** → never (GUI). `.quarantine/` unreachable (`_safe_acervo_path` rejects any
  `.`-prefixed component + traversal/symlink-escape/absolute).
- **Publish** → Draft-First; validator can revert a bad manifest status change.

---

## 7. Chat bridge (Studio ↔ Chat) — a session contract, not a DOM coupling

The Studio and chat communicate **only** through the server session + fork-owned
MOD-007/008 pending-context plumbing — never shared components:

```
STUDIO  ──"Enviar ao chat"──▶  POST x/stage (copies page → session pending-context dir)
                                          │ session state
CHAT composer  ◀── reads S.pendingContextAttachments / #ctxTray chips ── rides next message
```

Because the bridge is a `session_id` + a fork-owned endpoint, upstream can rewrite the
entire chat DOM without breaking it. Reverse deep-links (chat cites a page → open in
Studio) and "save from chat → intake" reuse the same session channel.

---

## 8. Coexistence & rebase-safety

The defining constraint. Strategy = **isolation + near-zero upstream touch** (the proven
MOD-009 pattern, taken further):

| Surface | Touch | Risk |
|---|---|---|
| `api/acervo_studio.py`, `api/acervo_studio_agent.py` (new) | new files | none |
| `static/acervo-studio.{js,css}` (new, `.axs-*`, own shell) | new files | none |
| `api/acervo_explorer.py` (MOD-009, fork-owned) | small: delegate new `x/*` sub-paths | none (fork-owned) |
| `api/routes.py` (upstream-owned) | **0 new lines** (prefix dispatch already exists) | none |
| `static/index.html` (upstream-owned) | ~4 lines: nav/launch entry + 2 includes + `#acervoStudioRoot` mount | low |

- **Frontend tech — vanilla now, framework-island reassessed at Phase 2 (decided 2026-07-02).**
  Phase 0–1 are built as **vanilla IIFE** (`sourceType:"script"`, no build, lint via
  `npm run lint:runtime`) — consistent with the app, cheapest rebase-safety, no impact on
  the provisioned `~/.hermes/hermes-webui/` runtime. Rationale for not adopting a framework
  up front: the Studio is *not upstreamable regardless* (it is Exocórtex-domain-specific and
  the fork policy is already "no upstream PRs"), so the only thing protected by staying
  build-free is the fork's **own** operational simplicity — pull-rebase-ability is governed by
  *shared-file* conflict surface, not language, and the Studio lives in new files either way.
  The stateful flows that would actually justify a framework arrive in **Phases 2–4** (intake
  triage, publish gate, pinnable assistant); at Phase 2 we reassess adopting a **pre-bundled
  island** — a lightweight framework (e.g. Preact ~4KB) authored under `studio-src/` and built
  to a single **IIFE** `acervo-studio.bundle.{js,css}` in `static/`. Because the bundle output
  carries no ES `import`/`export`, it still passes the runtime guard and the server still
  serves one static file — so the island is a safe, isolated, reversible upgrade with zero
  effect on the rest of the app. Decision deferred (YAGNI) until the flows prove it necessary.
- Mount is **reparented to `<body>`** at runtime (rightpanel carries a `transform` that
  traps `position:fixed` — the MOD-009 lesson).
- Catalog as **MOD-010** in `EXOCRTX_MODIFICATIONS.md` (touch points + rebase guidance);
  COLLAB record in `.harness/changes/2026-07-02_collab_hermes-webui-acervo-studio.md`;
  update `.harness/subprojects/hermes-webui/IDENTITY.md`.
- Upstream sync stays **cherry-pick, not full rebase** (unchanged policy).

---

## 9. Error handling & edge cases

- **Hermes unavailable** — Studio degrades to a manual knowledge manager: navigate,
  edit, move, tags, status, download, stage-to-chat all still work; triage/assist/promote
  show a calm "agente offline — tente novamente" and never block manual work. *The AI is
  additive, never a hard dependency for core file ops.*
- **Quality gate fails** (non-draft artifact) — publish blocked; issues surfaced; "Revisar".
- **Draft-First** — private-to-owner = delivery (allowed); public link/share/email needs
  an explicit approval step.
- **Not memory** — intake resolves to keep-in-inbox / task / artifact.
- **Large uploads** — size caps + streaming; original always preserved before extraction.
- **Dirty editor** — `beforeunload`/nav guard (reuse MOD-009); perene edit warns.
- **Non-md** (pdf/image) — preview via `x/raw` (sandbox CSP), not the md editor.
- **Session required** — every endpoint session-gated (404 on miss), like MOD-009.
- **Concurrency** — atomic writes (temp + `os.replace`); agent writes serialize through
  `excrtx-memory-manager`.

---

## 10. Component breakdown (isolated, testable units)

**Backend**
- `acervo_studio.py` — HTTP handlers (intake/publish/download/assist + tree extensions).
  *Depends on:* `acervo_explorer` helpers, `acervo_studio_agent`, `artifact_publish`.
- `acervo_studio_agent.py` — Hermes mediation (task→proposal; write routing).
  *Depends on:* Hermes runtime, `excrtx-memory-manager`.
- (reuse) `acervo_explorer.py` — path safety, frontmatter, read/edit endpoints.

**Frontend (`static/acervo-studio.js`, one IIFE, module-local state `AXS`)**
- `shell` — full-screen mount, Chat↔Acervo toggle, theme (dim/light OS-follow), `⌘K`.
- `navigator` — unified scope tree + inline page lists + inbox badge.
- `reader` — preview (reuse `renderMd`/`renderKatexBlocks`) + frontmatter chips.
- `editor` — body+frontmatter, tags, status, move (→ MOD-009 endpoints), dirty guard.
- `assistant` — self-summon/pin; renders proposals (triage/assist/publish gate).
- `intake` — capture (upload/paste/link/from-chat) + triage proposal + promote.
- `publish` — prepare/gate/Draft-First/confirm + receipt.
- `bridge` — stage-to-chat + deep-links (reuse pending-context).

Each unit: single purpose, well-defined interface, independently testable.

---

## 11. Phased delivery — DELIVERED (Phases 0–5, 2026-07-12)

All phases are merged to `exocortex/stable` and pushed to the fork origin. Each shipped
with hermetic tests + a live FIXTURE E2E + a whole-branch review + governance (catalog +
COLLAB + IDENTITY). The running :8787 instance is **not yet reprovisioned** (owner-gated).

- **Phase 0 — Shell & navigate. ✅ DONE.** Full-screen view, Chat↔Acervo toggle,
  Graphite+light themes, `.axs-*`, unified navigator (`tree`+`micro`+`inbox`), reader.
- **Phase 1 — Edit & download & bridge. ✅ DONE.** Elevated editor (MOD-009 write surface),
  download (md/raw/zip), stage-to-chat. (+ Phase 1.1 session auto-bind.) *Shipped live.*
- **Phase 2 — Intake (AI-native inbound). ✅ DONE.** 2a: capture upload/text/link → `_inbox`
  (agentless). 2b: Hermes triage proposal + agent-mediated promote (the first semantic
  write; hybrid = agent crafts body, server writes via the `acervoctl` control plane).
- **Phase 3 — Publish (outbound). ✅ DONE.** `x/publish/prepare` (quality gate) +
  `x/publish` (Draft-First → Drive SHA-256 receipt); public share owner-gated. Deterministic
  shell-out to `artifact_publish.py` + `validate_artifact_manifest.py` (no cognition).
- **Phase 4 — Assist & ask. ✅ DONE.** `x/assist` (rewrite/summarize/suggest-tags/
  contradiction, proposal-only; apply via the existing editor + `x/save`) + `x/ask`
  ("ask the acervo": bounded in-process retrieval → grounded answer, sources subset-validated).
- **Phase 5 — Consolidate. ✅ DONE.** Retire/redirect the MOD-009 docked panel (from the
  fork-owned `acervo-studio.js`, MOD-009 byte-untouched); a11y pass (dialog role, Escape,
  focus management, keyboard-operable nav); perf check; upstream-sync checkpoint
  (`docs/acervo-studio/UPSTREAM-SYNC.md`).

Phases 0–1 shipped a premium manager with zero agent risk; 2–4 added the AI-native spine;
5 consolidated. Go-live (reprovision) is the remaining owner-gated step —
`docs/acervo-studio/GO-LIVE-CHECKLIST.md`.

---

## 12. Testing strategy

- **Unit (pytest, hermetic tmp acervo)** — path safety (reuse MOD-009 suite), intake
  envelope creation/preservation, promote routing, publish gate integration (mock
  `artifact_publish`), download safety, assist mediation (mock Hermes), tree
  micro/inbox scopes.
- **Governance tests** — OKF preservation on agent writes; `.quarantine`/create/delete
  rejected; Draft-First public-share requires approval; quality-gate revert.
- **Integration** — `acervo_studio_agent` contract against a stub Hermes (proposal shape,
  graceful offline).
- **E2E (headless Chromium + live API, like MOD-009 §9)** — both flows end-to-end;
  responsive; theme switch; a11y roles/focus; the chat bridge round-trip.
- **Rebase-safety** — assert upstream-owned touch counts (index.html grep counts;
  routes.py unchanged); `npm run lint:runtime`; full suite baseline (**no new failures**
  vs. the documented pre-existing set).

---

## 13. Open questions / risks

1. **Hermes invocation mechanism** (§6.2) — sync vs async; the #1 spike, gates Phase 2 UX.
2. **IntakeEnvelope contract** — adopt the `excrtx-memory-intake` proposed HTTP contract
   verbatim vs. a Studio-specific variant. *Recommend: adopt it.*
3. **Promote visibility** — background structured call (proposal in the assistant) vs.
   visible chat turn. *Recommend: background by default, "abrir no chat" for complex cases.*
4. **Google Drive credentials** — `artifact_publish.py` needs Drive auth in the
   provisioned runtime (provisioning concern, not UI).
5. **Deployment** — changes live in the repo; the running instance is the provisioned
   `~/.hermes/hermes-webui/` copy and must be reprovisioned to go live (MOD-009 note).

---

## 14. Verification checklist (definition of done, per phase)

- [ ] Upstream-owned files touched ≤ target (routes.py: 0; index.html: ~4).
- [ ] `npm run lint:runtime` clean; `node --check`; `py_compile` OK.
- [ ] Full pytest suite: no new failures vs. baseline.
- [ ] E2E: the phase's flow driven end-to-end in headless Chromium against a live server.
- [ ] Governance: `.quarantine`/create/delete rejected; OKF preserved; Draft-First honored.
- [ ] Graceful degradation with Hermes offline (Phases ≥2).
- [ ] MOD-010 catalog + COLLAB record + IDENTITY.md updated.
