# Acervo Studio — Phase 4 (Assist & Ask-the-Acervo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inline, PROPOSAL-ONLY cognition on an existing page
(`x/assist {op: rewrite|summarize|suggest_tags|contradiction_check}`) plus semantic
Q&A over the acervo (`x/ask` — "ask the acervo": a retrieval-grounded answer with
cited sources) — both rendered inline, both degrading calmly when Hermes is offline,
and NEITHER writing anything.

**Architecture:** Reuses the proven Phase-2b mediation seam
(`api/acervo_studio_agent._run_agent_text`, tool-less, sync in-process): assist runs
one tool-less turn and returns a validated JSON proposal; applying a rewrite/tags
proposal happens by prefilling the EXISTING MOD-009 editor — `x/save` stays the ONLY
write path, so no new write is introduced. "Ask" grounding is an in-process bounded
walk over the acervo (term-overlap scoring over frontmatter + a bounded body read,
top-k excerpts) — chosen over `acervoctl retrieve` because retrieve needs a prebuilt
`catalog.sqlite` (`reindex`) and its factual route returned `found:false` even on
direct term hits in probing; the CLI stays a future enhancement. Both routes delegate
from `handle_studio_post` → **0 new `routes.py` lines**.

**Tech Stack:** Python 3 stdlib; pytest (hermetic, `_run_agent_text` monkeypatched);
vanilla IIFE JS + `npm run lint:runtime`; Playwright for the live fixture E2E.

## Global Constraints

- **PROPOSAL-ONLY:** `x/assist` and `x/ask` NEVER write (no page, no envelope, no
  routing.json, no manifest mutation). Applying an assist proposal flows through the
  existing editor + `x/save` (the owner's click). The answer/proposal renders inline.
- **REBASE-SAFETY:** changes only in `api/acervo_studio_agent.py` (append),
  `api/acervo_studio.py` (append + 2 dispatch lines), `static/acervo-studio.{js,css}`,
  `tests/test_mod010_acervo_studio.py`. **0 new `routes.py` / `index.html` lines.**
  NEVER edit `style.css`/`ui.js`/`workspace.js`/`acervo.js`/`acervo-explorer.*`.
  Shared-file diff EMPTY at the end.
- **VANILLA ONLY:** IIFE, `'use strict'`, no ES import/export (`npm run lint:runtime`).
  Namespaces `.axs-*` / `acervoStudio*` / `AXS`. All dynamic content `_esc`'d.
- **OPERATIONAL STATES = HTTP 200 + `{ok:false, offline|no_context|error}`** so the UI
  renders them calmly (`api()` throws on non-2xx). Malformed = 400 (unknown op, empty
  question), missing page/session = 400/404.
- **PATH SAFETY:** assist reads the target page via `_safe_acervo_path` + a
  resolved-dot guard (`.quarantine` unreachable); `.md` only; body bounded to 12k chars.
- **GROUNDING:** ask's `sources` are server-validated to be a subset of the paths that
  were actually in the retrieved context (a model citing a foreign path gets it dropped).
- Hermetic tests mirror `tests/test_mod010_acervo_studio.py` idioms (`acervo` fixture,
  `_Handler`, `session_ok`, `jcap`); the agent is ALWAYS mocked in pytest; the live E2E
  runs against a THROWAWAY fixture + temp `HERMES_HOME` (agent offline ⇒ calm states)
  plus network-stubbed render checks. Agent-ONLINE assist/ask is exercised in the
  consolidated Studio E2E after Phase 5.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `api/acervo_studio_agent.py` | modify (append) | `_ASSIST_OPS`, `_ASSIST_SYSTEMS`, `_page_content_for_assist`, `_clean_tags`, `_normalize_assist`, `propose_assist`; `_ASK_SYSTEM`, `_ask_context`, `ask_acervo` |
| `api/acervo_studio.py` | modify (append) | `handle_assist` + `handle_ask` + 2 dispatch lines |
| `static/acervo-studio.js` | modify | ✦ Assistir action + `.axs-ai` strip (4 ops, apply-to-editor); ✦ Perguntar ao acervo in search |
| `static/acervo-studio.css` | modify (append) | `.axs-ai*` styles |
| `tests/test_mod010_acervo_studio.py` | modify (append) | Phase 4 sections |

---

### Task 1 — `propose_assist()` (agent module) + tests

**Files:**
- Modify: `api/acervo_studio_agent.py` (append at end)
- Test: `tests/test_mod010_acervo_studio.py` (append)

**Interfaces:**
- Consumes: `_run_agent_text`, `_extract_json`, `AgentUnavailable`, `re` (all present).
- Produces: `_ASSIST_OPS`; `propose_assist(root, rel_path, op, *, session=None) -> dict`.
  Shapes — ok: `{ok:True, op, proposal}` where proposal is per-op:
  rewrite → `{"body_markdown": str}`; summarize → `{"summary": str}`;
  suggest_tags → `{"tags": [str]}`; contradiction_check →
  `{"consistent": bool, "findings": [{"claim","conflict"}]}`.
  Fail: `{ok:False, offline:True}` | `{ok:False, error}`.

- [ ] **Step 1: Write the failing tests**

```python
# ── Phase 4 Task 1: propose_assist (proposal-only cognition) ─────────────────

def _mk_page(acervo, rel="global/knowledge/nota.md",
             body="---\ntitle: Nota\nstatus: draft\n---\n\nO preço do X é 10.\n"):
    p = acervo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return rel


def test_assist_rewrite_proposal(acervo, monkeypatch):
    rel = _mk_page(acervo)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"body_markdown":"# Nota\\n\\nO preço do X é 10."}')
    out = studio_agent.propose_assist(acervo, rel, "rewrite")
    assert out["ok"] is True and out["op"] == "rewrite"
    assert out["proposal"]["body_markdown"].startswith("# Nota")


def test_assist_summarize_proposal(acervo, monkeypatch):
    rel = _mk_page(acervo)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: 'Sure:\n```json\n{"summary":"Nota sobre preço."}\n```')
    out = studio_agent.propose_assist(acervo, rel, "summarize")
    assert out["ok"] is True and out["proposal"]["summary"] == "Nota sobre preço."


def test_assist_suggest_tags_cleans(acervo, monkeypatch):
    rel = _mk_page(acervo)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"tags":["Preço!!","  X  ","preço","a b c","","z"]}')
    out = studio_agent.propose_assist(acervo, rel, "suggest_tags")
    assert out["ok"] is True
    assert out["proposal"]["tags"] == ["preco", "x", "preco", "a-b-c", "z"]


def test_assist_contradiction_findings_clamped(acervo, monkeypatch):
    rel = _mk_page(acervo)
    finds = ",".join(['{"claim":"c%d","conflict":"k%d"}' % (i, i) for i in range(8)])
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"consistent":false,"findings":[' + finds + ']}')
    out = studio_agent.propose_assist(acervo, rel, "contradiction_check")
    assert out["ok"] is True and out["proposal"]["consistent"] is False
    assert len(out["proposal"]["findings"]) == 5   # clamped to 5
    assert out["proposal"]["findings"][0] == {"claim": "c0", "conflict": "k0"}


def test_assist_offline(acervo, monkeypatch):
    rel = _mk_page(acervo)
    def _boom(sp, up, **k):
        raise studio_agent.AgentUnavailable("no runtime")
    monkeypatch.setattr(studio_agent, "_run_agent_text", _boom)
    out = studio_agent.propose_assist(acervo, rel, "rewrite")
    assert out == {"ok": False, "offline": True}


def test_assist_unknown_op(acervo):
    rel = _mk_page(acervo)
    out = studio_agent.propose_assist(acervo, rel, "translate")
    assert out["ok"] is False and "unknown" in out["error"]


def test_assist_non_md_rejected(acervo, monkeypatch):
    (acervo / "global" / "knowledge").mkdir(parents=True, exist_ok=True)
    (acervo / "global" / "knowledge" / "a.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: (_ for _ in ()).throw(AssertionError("read a non-md")))
    out = studio_agent.propose_assist(acervo, "global/knowledge/a.pdf", "summarize")
    assert out["ok"] is False and "not found or not assistable" in out["error"]


def test_assist_quarantine_symlink_blocked(acervo, monkeypatch):
    (acervo / ".quarantine").mkdir(exist_ok=True)
    (acervo / ".quarantine" / "secret.md").write_text("segredo", encoding="utf-8")
    (acervo / "global" / "knowledge").mkdir(parents=True, exist_ok=True)
    (acervo / "global" / "knowledge" / "link.md").symlink_to(
        acervo / ".quarantine" / "secret.md")
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: (_ for _ in ()).throw(AssertionError("read quarantine")))
    out = studio_agent.propose_assist(acervo, "global/knowledge/link.md", "summarize")
    assert out["ok"] is False


def test_assist_unparseable(acervo, monkeypatch):
    rel = _mk_page(acervo)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: "no json here")
    out = studio_agent.propose_assist(acervo, rel, "rewrite")
    assert out["ok"] is False and "error" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k assist_ -x -q`
Expected: FAIL — `AttributeError: ... has no attribute 'propose_assist'`

- [ ] **Step 3: Append to `api/acervo_studio_agent.py`**

```python
# ── Phase 4: assist (proposal-only cognition) + ask-the-acervo ───────────────

_ASSIST_OPS = ("rewrite", "summarize", "suggest_tags", "contradiction_check")
_ASSIST_CONTENT_CHARS = 12000

_ASSIST_SYSTEMS = {
    "rewrite": (
        "You are the Exocortex acervo editor. Rewrite the page body for clarity "
        "and directness, preserving ALL facts and the original language. No YAML "
        "frontmatter. Reply with ONE JSON object and nothing else: "
        "{\"body_markdown\": \"...\"}."),
    "summarize": (
        "You are the Exocortex acervo summarizer. Summarize the page in its own "
        "language, 3-5 sentences, facts only. Reply with ONE JSON object and "
        "nothing else: {\"summary\": \"...\"}."),
    "suggest_tags": (
        "You are the Exocortex acervo tagger. Suggest up to 8 lowercase keyword "
        "tags for the page. Reply with ONE JSON object and nothing else: "
        "{\"tags\": [\"...\"]}."),
    "contradiction_check": (
        "You are the Exocortex acervo consistency checker. Find internal "
        "contradictions in the page (claims that conflict with each other). "
        "Reply with ONE JSON object and nothing else: {\"consistent\": true|false, "
        "\"findings\": [{\"claim\": \"...\", \"conflict\": \"...\"}]}."),
}


def _page_content_for_assist(root, rel_path):
    """Safe bounded read of an .md page for cognition. Returns text or None
    (bad path / not md / unreadable / resolves into a dot-prefixed area, which
    keeps .quarantine unreachable — the x/download posture)."""
    from api.acervo_explorer import _safe_acervo_path
    rel = str(rel_path or "").strip()
    if not rel.lower().endswith(".md"):
        return None
    try:
        fp = _safe_acervo_path(rel)
    except ValueError:
        return None
    try:
        parts = fp.resolve().relative_to(root.resolve()).parts
    except (OSError, ValueError):
        return None
    if any(p.startswith(".") for p in parts):
        return None
    if not fp.is_file():
        return None
    try:
        return fp.read_text(encoding="utf-8", errors="replace")[:_ASSIST_CONTENT_CHARS]
    except OSError:
        return None


def _clean_tags(raw):
    tags = [re.sub(r"[^a-z0-9-]+", "-", str(t).strip().lower()).strip("-")
            for t in (raw if isinstance(raw, list) else [])][:8]
    return [t for t in tags if t]


def _normalize_assist(op, obj):
    """Clamp the model's JSON into the per-op proposal shape; None if unusable."""
    if not isinstance(obj, dict):
        return None
    if op == "rewrite":
        body = str(obj.get("body_markdown", "") or "").strip()
        return {"body_markdown": body} if body else None
    if op == "summarize":
        s = str(obj.get("summary", "") or "").strip()
        return {"summary": s[:2000]} if s else None
    if op == "suggest_tags":
        tags = _clean_tags(obj.get("tags"))
        return {"tags": tags} if tags else None
    if op == "contradiction_check":
        finds = []
        for f in (obj.get("findings") or [])[:5]:
            if isinstance(f, dict):
                claim = str(f.get("claim", "") or "").strip()[:300]
                conflict = str(f.get("conflict", "") or "").strip()[:300]
                if claim:
                    finds.append({"claim": claim, "conflict": conflict})
        return {"consistent": bool(obj.get("consistent", not finds)),
                "findings": finds}
    return None


def propose_assist(root, rel_path, op, *, session=None):
    """PROPOSAL-ONLY cognition on one existing page. Never writes. Returns
    {ok, op, proposal} | {ok:False, offline} | {ok:False, error}."""
    op = str(op or "").strip().lower()
    if op not in _ASSIST_OPS:
        return {"ok": False, "error": "unknown assist op"}
    content = _page_content_for_assist(root, rel_path)
    if content is None:
        return {"ok": False, "error": "page not found or not assistable"}
    user_prompt = "Page path: %s\n\n---\n%s\n---\n" % (rel_path, content)
    try:
        text = _run_agent_text(_ASSIST_SYSTEMS[op], user_prompt, session=session)
    except AgentUnavailable:
        return {"ok": False, "offline": True}
    proposal = _normalize_assist(op, _extract_json(text))
    if proposal is None:
        return {"ok": False, "error": "could not parse a valid proposal"}
    return {"ok": True, "op": op, "proposal": proposal}
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k assist_ -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add api/acervo_studio_agent.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): propose_assist — proposal-only cognition on a page (Phase 4 T1)"
```

---

### Task 2 — `_ask_context()` + `ask_acervo()` + tests

**Files:**
- Modify: `api/acervo_studio_agent.py` (append)
- Test: `tests/test_mod010_acervo_studio.py` (append)

**Interfaces:**
- Consumes: `_run_agent_text`, `_extract_json`, `AgentUnavailable`; `routes._ACERVO_NATURES`,
  `routes._read_frontmatter_meta` (via `import api.routes`).
- Produces: `_ask_context(root, question, k=5) -> [{"path","title","excerpt"}]`;
  `ask_acervo(root, question, *, session=None) -> {ok, answer, sources}` |
  `{ok:False, no_context:True}` | `{ok:False, offline:True}` | `{ok:False, error}`.

- [ ] **Step 1: Write the failing tests**

```python
# ── Phase 4 Task 2: ask-the-acervo (retrieval-grounded) ──────────────────────

def test_ask_context_scores_and_returns_hit(acervo):
    _mk_page(acervo, "global/knowledge/preco.md",
             "---\ntitle: Tabela de preço\ntags: [preco]\n---\n\nO preço do produto X é R$ 10.\n")
    _mk_page(acervo, "global/knowledge/outro.md",
             "---\ntitle: Reunião\n---\n\nAta da reunião de segunda.\n")
    ctx = studio_agent._ask_context(acervo, "qual o preço do produto X?", k=3)
    assert ctx and ctx[0]["path"] == "global/knowledge/preco.md"
    assert "excerpt" in ctx[0] and ctx[0]["excerpt"]


def test_ask_context_skips_meta_and_dot(acervo):
    _mk_page(acervo, "micro/demo/_meta/index.md",
             "---\ntitle: Index\n---\n\npreço preço preço\n")
    _mk_page(acervo, "micro/demo/knowledge/p.md",
             "---\ntitle: Preço demo\n---\n\nO preço é 5.\n")
    ctx = studio_agent._ask_context(acervo, "preço", k=5)
    paths = [c["path"] for c in ctx]
    assert "micro/demo/knowledge/p.md" in paths
    assert not any("/_meta/" in p for p in paths)


def test_ask_context_k_cap(acervo):
    for i in range(6):
        _mk_page(acervo, "global/knowledge/p%d.md" % i,
                 "---\ntitle: Preço %d\n---\n\npreço tabelado item.\n" % i)
    ctx = studio_agent._ask_context(acervo, "preço tabelado", k=3)
    assert len(ctx) == 3


def test_ask_acervo_happy_subset_sources(acervo, monkeypatch):
    _mk_page(acervo, "global/knowledge/preco.md",
             "---\ntitle: Preço\n---\n\nO preço do X é 10.\n")
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"answer":"O preço do X é 10.",'
                                            '"sources":["global/knowledge/preco.md","micro/fake/x.md"]}')
    out = studio_agent.ask_acervo(acervo, "qual o preço do X?")
    assert out["ok"] is True and "10" in out["answer"]
    # a source not in the retrieved context is dropped (grounding)
    assert out["sources"] == ["global/knowledge/preco.md"]


def test_ask_acervo_no_context(acervo, monkeypatch):
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: (_ for _ in ()).throw(AssertionError("agent called with no context")))
    out = studio_agent.ask_acervo(acervo, "algo que não existe zzz")
    assert out["ok"] is False and out["no_context"] is True


def test_ask_acervo_offline(acervo, monkeypatch):
    _mk_page(acervo, "global/knowledge/preco.md",
             "---\ntitle: Preço\n---\n\nO preço do X é 10.\n")
    def _boom(sp, up, **k):
        raise studio_agent.AgentUnavailable("no runtime")
    monkeypatch.setattr(studio_agent, "_run_agent_text", _boom)
    out = studio_agent.ask_acervo(acervo, "qual o preço do X?")
    assert out == {"ok": False, "offline": True}


def test_ask_acervo_empty_question(acervo):
    out = studio_agent.ask_acervo(acervo, "   ")
    assert out["ok"] is False and "error" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k ask_ -x -q`
Expected: FAIL — `AttributeError: ... has no attribute '_ask_context'`

- [ ] **Step 3: Append to `api/acervo_studio_agent.py`**

```python
_ASK_SYSTEM = (
    "You are the Exocortex acervo answerer. Answer the question USING ONLY the "
    "provided acervo excerpts, in the question's language, concisely. If the "
    "excerpts do not contain the answer, say you don't know. Reply with ONE JSON "
    "object and nothing else: {\"answer\": \"...\", \"sources\": [\"<path>\"]} where "
    "sources lists only the excerpt paths you actually used.")

_ASK_SCAN_MAX = 2000
_ASK_BODY_CHARS = 4000
_ASK_EXCERPT_PAD = 160
_ASK_STOPWORDS = {"o", "a", "os", "as", "de", "do", "da", "e", "que", "qual",
                  "the", "of", "is", "to", "in", "a", "an"}


def _ask_terms(question):
    return [t for t in re.findall(r"[a-z0-9]+", str(question or "").lower())
            if len(t) > 1 and t not in _ASK_STOPWORDS]


def _ask_excerpt(body, terms):
    low = body.lower()
    for t in terms:
        i = low.find(t)
        if i >= 0:
            a = max(0, i - _ASK_EXCERPT_PAD)
            b = min(len(body), i + _ASK_EXCERPT_PAD)
            return ("…" if a > 0 else "") + body[a:b].strip() + ("…" if b < len(body) else "")
    return body[:_ASK_EXCERPT_PAD].strip()


def _ask_context(root, question, k=5):
    """Bounded in-process retrieval over global/shared/micro × the 11 natures.
    Scores term overlap (title×3, tags×2, description×2, body×1); returns the
    top-k {path, title, excerpt}. Skips `_`/`.`-prefixed dirs (so `_meta`,
    `.quarantine` never contribute)."""
    import api.routes as routes
    terms = _ask_terms(question)
    if not terms:
        return []
    bases = [root / "global", root / "shared"]
    micro = root / "micro"
    if micro.is_dir():
        try:
            for d in sorted(micro.iterdir(), key=lambda p: p.name):
                if d.is_dir() and not d.name.startswith(("_", ".")):
                    bases.append(d)
        except OSError:
            pass
    scored = []
    scanned = 0
    for base in bases:
        if not base.is_dir():
            continue
        for nat in routes._ACERVO_NATURES:
            nd = base / nat
            if not nd.is_dir():
                continue
            try:
                entries = sorted(nd.iterdir(), key=lambda p: p.name)
            except OSError:
                continue
            for f in entries:
                if scanned >= _ASK_SCAN_MAX:
                    break
                if not f.is_file() or f.suffix.lower() != ".md" \
                   or f.name.startswith(("_", ".")):
                    continue
                scanned += 1
                meta = routes._read_frontmatter_meta(
                    f, ["title", "description", "tags"])
                title = meta.get("title", f.stem)
                try:
                    body = f.read_text(encoding="utf-8", errors="replace")[:_ASK_BODY_CHARS]
                except OSError:
                    continue
                tl, dl, gl, bl = (title.lower(), meta.get("description", "").lower(),
                                  meta.get("tags", "").lower(), body.lower())
                score = 0
                for t in terms:
                    score += 3 * tl.count(t) + 2 * dl.count(t) + 2 * gl.count(t) + bl.count(t)
                if score > 0:
                    try:
                        rel = str(f.resolve().relative_to(root.resolve()))
                    except (OSError, ValueError):
                        continue
                    scored.append((score, rel, title, _ask_excerpt(body, terms)))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"path": p, "title": t, "excerpt": e}
            for (_s, p, t, e) in scored[:max(1, int(k))]]


def ask_acervo(root, question, *, session=None):
    """Semantic Q&A over the acervo: retrieve bounded context, ask Hermes to
    answer USING ONLY that context, validate the cited sources are a subset of
    the retrieved paths. PROPOSAL-ONLY (never writes). Returns
    {ok, answer, sources} | {ok:False, no_context} | offline | error."""
    q = str(question or "").strip()
    if not q:
        return {"ok": False, "error": "question is required"}
    ctx = _ask_context(root, q, k=5)
    if not ctx:
        return {"ok": False, "no_context": True}
    allowed = {c["path"] for c in ctx}
    blocks = "\n\n".join("[%s] %s\n%s" % (c["path"], c["title"], c["excerpt"])
                         for c in ctx)
    user_prompt = "Question: %s\n\nAcervo excerpts:\n%s\n" % (q, blocks)
    try:
        text = _run_agent_text(_ASK_SYSTEM, user_prompt, session=session)
    except AgentUnavailable:
        return {"ok": False, "offline": True}
    obj = _extract_json(text) or {}
    answer = str(obj.get("answer", "") or "").strip()
    if not answer:
        return {"ok": False, "error": "could not parse an answer"}
    raw_sources = obj.get("sources") if isinstance(obj.get("sources"), list) else []
    sources = [str(s) for s in raw_sources if str(s) in allowed]
    return {"ok": True, "answer": answer[:4000], "sources": sources}
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k "assist_ or ask_" -q`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add api/acervo_studio_agent.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): ask-the-acervo — bounded retrieval + grounded answer (Phase 4 T2)"
```

---

### Task 3 — Routes `POST x/assist` + `POST x/ask` + dispatch + tests

**Files:**
- Modify: `api/acervo_studio.py` — append handlers before `# region: dispatchers`
  (currently line ~509 pre-Phase-3; after Phase 3 it is after `handle_publish`),
  and 2 dispatch lines in `handle_studio_post` after the publish pair.
- Test: `tests/test_mod010_acervo_studio.py` (append)

**Interfaces:**
- Consumes: `agent.propose_assist` / `agent.ask_acervo` (Task 1/2); `_intake_session`.
- Produces: `POST /api/acervo/x/assist {session_id, path, op}`;
  `POST /api/acervo/x/ask {session_id, question}`.

- [ ] **Step 1: Write the failing tests**

```python
# ── Phase 4 Task 3: assist + ask routes ──────────────────────────────────────

def test_assist_route_happy(acervo, session_ok, jcap, monkeypatch):
    rel = _mk_page(acervo)
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"summary":"resumo curto."}')
    h = _Handler("/api/acervo/x/assist")
    studio.handle_studio_post(h, {"session_id": "sid1", "path": rel, "op": "summarize"})
    assert jcap["status"] == 200 and jcap["obj"]["ok"] is True
    assert jcap["obj"]["proposal"]["summary"] == "resumo curto."


def test_assist_route_unknown_op_400(acervo, session_ok, jcap):
    rel = _mk_page(acervo)
    h = _Handler("/api/acervo/x/assist")
    studio.handle_studio_post(h, {"session_id": "sid1", "path": rel, "op": "translate"})
    assert jcap["status"] == 400


def test_assist_route_offline_calm(acervo, session_ok, jcap, monkeypatch):
    rel = _mk_page(acervo)
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    def _boom(sp, up, **k):
        raise studio_agent.AgentUnavailable("x")
    monkeypatch.setattr(studio_agent, "_run_agent_text", _boom)
    h = _Handler("/api/acervo/x/assist")
    studio.handle_studio_post(h, {"session_id": "sid1", "path": rel, "op": "rewrite"})
    assert jcap["status"] == 200 and jcap["obj"]["offline"] is True


def test_assist_route_missing_page(acervo, session_ok, jcap, monkeypatch):
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    monkeypatch.setattr(studio_agent, "_run_agent_text", lambda sp, up, **k: "{}")
    h = _Handler("/api/acervo/x/assist")
    studio.handle_studio_post(h, {"session_id": "sid1",
                                  "path": "global/knowledge/nope.md", "op": "rewrite"})
    assert jcap["status"] == 200 and jcap["obj"]["ok"] is False


def test_assist_route_requires_session(acervo, jcap, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: None)
    h = _Handler("/api/acervo/x/assist")
    studio.handle_studio_post(h, {"session_id": "ghost", "path": "x.md", "op": "rewrite"})
    assert jcap["status"] in (400, 404)


def test_ask_route_happy(acervo, session_ok, jcap, monkeypatch):
    _mk_page(acervo, "global/knowledge/preco.md",
             "---\ntitle: Preço\n---\n\nO preço do X é 10.\n")
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"answer":"É 10.","sources":["global/knowledge/preco.md"]}')
    h = _Handler("/api/acervo/x/ask")
    studio.handle_studio_post(h, {"session_id": "sid1", "question": "preço do X?"})
    assert jcap["status"] == 200 and jcap["obj"]["ok"] is True
    assert jcap["obj"]["sources"] == ["global/knowledge/preco.md"]


def test_ask_route_no_context_calm(acervo, session_ok, jcap, monkeypatch):
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    h = _Handler("/api/acervo/x/ask")
    studio.handle_studio_post(h, {"session_id": "sid1", "question": "zzz inexistente"})
    assert jcap["status"] == 200 and jcap["obj"]["no_context"] is True


def test_ask_route_empty_question_400(acervo, session_ok, jcap):
    h = _Handler("/api/acervo/x/ask")
    studio.handle_studio_post(h, {"session_id": "sid1", "question": "  "})
    assert jcap["status"] == 400


def test_ask_route_requires_session(acervo, jcap, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: None)
    h = _Handler("/api/acervo/x/ask")
    studio.handle_studio_post(h, {"session_id": "ghost", "question": "x"})
    assert jcap["status"] in (400, 404)


def test_post_dispatcher_delegates_assist_and_ask(acervo, session_ok, jcap, monkeypatch):
    rel = _mk_page(acervo)
    monkeypatch.setattr(routes, "get_session", lambda sid: None, raising=False)
    monkeypatch.setattr(studio_agent, "_run_agent_text",
                        lambda sp, up, **k: '{"summary":"s."}')
    h = _Handler("/api/acervo/x/assist")
    ax.handle_acervo_x_post(h, {"session_id": "sid1", "path": rel, "op": "summarize"})
    assert jcap["status"] == 200 and jcap["obj"]["ok"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k "assist_route or ask_route or delegates_assist" -q`
Expected: FAIL — 404 "unknown acervo explorer endpoint"

- [ ] **Step 3: Append the handlers to `api/acervo_studio.py`** (before `# region: dispatchers`):

```python
# region: assist + ask (Phase 4 — proposal-only cognition; never writes)

def handle_assist(handler, body):
    """POST /api/acervo/x/assist {session_id, path, op} — proposal-only
    cognition on ONE existing page (rewrite|summarize|suggest_tags|
    contradiction_check). Never writes: applying an edit goes through x/save."""
    import api.routes as routes
    import api.acervo_studio_agent as agent
    body = body or {}
    sid = _intake_session(handler, routes, body)
    if sid is None:
        return True
    op = str(body.get("op", "") or "").strip().lower()
    if op not in agent._ASSIST_OPS:
        return routes.bad(handler, "unknown assist op")
    rel = str(body.get("path", "") or "").strip()
    if not rel:
        return routes.bad(handler, "path is required")
    root = routes._acervo_root()
    session = None
    try:
        session = routes.get_session(sid)
    except Exception:
        session = None
    result = agent.propose_assist(root, rel, op, session=session)
    if result.get("ok"):
        return routes.j(handler, {"ok": True, "op": result["op"],
                                  "proposal": result["proposal"]})
    if result.get("offline"):
        return routes.j(handler, {"ok": False, "offline": True,
                                  "message": "agente offline — tente novamente"})
    return routes.j(handler, {"ok": False,
                              "error": result.get("error", "assist failed")})


def handle_ask(handler, body):
    """POST /api/acervo/x/ask {session_id, question} — semantic Q&A grounded in
    retrieved acervo excerpts. Proposal-only (read-only); never writes."""
    import api.routes as routes
    import api.acervo_studio_agent as agent
    body = body or {}
    sid = _intake_session(handler, routes, body)
    if sid is None:
        return True
    question = str(body.get("question", "") or "").strip()
    if not question:
        return routes.bad(handler, "question is required")
    root = routes._acervo_root()
    session = None
    try:
        session = routes.get_session(sid)
    except Exception:
        session = None
    result = agent.ask_acervo(root, question, session=session)
    if result.get("ok"):
        return routes.j(handler, {"ok": True, "answer": result["answer"],
                                  "sources": result.get("sources", [])})
    if result.get("offline"):
        return routes.j(handler, {"ok": False, "offline": True,
                                  "message": "agente offline — tente novamente"})
    if result.get("no_context"):
        return routes.j(handler, {"ok": False, "no_context": True,
                                  "message": "nada relevante encontrado no acervo"})
    return routes.j(handler, {"ok": False,
                              "error": result.get("error", "ask failed")})
```

And add the 2 dispatch lines in `handle_studio_post`, after the publish pair:

```python
    if path == "/api/acervo/x/assist":
        return handle_assist(handler, body)
    if path == "/api/acervo/x/ask":
        return handle_ask(handler, body)
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -q`
Expected: all pass (121 pre-existing + ~26 new)

- [ ] **Step 5: Commit**

```bash
git add api/acervo_studio.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): assist + ask routes — x/assist + x/ask (Phase 4 T3)"
```

---

### Task 4 — Frontend: ✦ Assistir strip + ✦ Perguntar ao acervo

**Files:**
- Modify: `static/acervo-studio.js` — `_actionsBar` (md-only ✦ Assistir), `_wireActs`
  (assist branch); add `.axs-ai` container to the md page render in
  `acervoStudioOpenPage`; new Phase-4 section after `acervoStudioPublishConfirm`;
  ✦ Perguntar in `acervoStudioSearch`.
- Modify: `static/acervo-studio.css` — append `.axs-ai*`.

**Interfaces:**
- Consumes: `POST x/assist`, `POST x/ask`; existing `api`, `_esc`, `_sid`, `_toast`,
  `_detail`, `AXS`, `acervoStudioEdit`, `acervoStudioOpenPage`.
- Produces: globals `acervoStudioAssistOpen`, `acervoStudioAssist`, `acervoStudioAsk`.

- [ ] **Step 1: Add ✦ Assistir to `_actionsBar`** — after the `edit` button line
  (inside `if (md)`), add a second md-only button:

```js
    if (md) acts += '<button type="button" class="axs-act" data-axs-act="assist">✦ Assistir</button>';
```

- [ ] **Step 2: Wire it in `_wireActs`** — add a branch before the `more` branch:

```js
        else if (act === 'assist') { if (typeof acervoStudioAssistOpen === 'function') acervoStudioAssistOpen(); }
```

- [ ] **Step 3: Add the assist strip container** — in `acervoStudioOpenPage`, in the
  md-page `reader.innerHTML` (the block with `<div class="axs-md">`), append a strip
  div right after the md div:

```js
      '  <div class="axs-md">' + bodyHtml + '</div>' +
      '  <div class="axs-ai" data-axs-ai></div>' +
```

- [ ] **Step 4: Add the Phase-4 section** (after
  `window.acervoStudioPublishConfirm = acervoStudioPublishConfirm;`):

```js
  // ── Phase 4: assist (proposal-only) + ask-the-acervo ─────────────────────
  var AXS_ASSIST_OPS = [
    { op: 'rewrite', label: 'Reescrever' },
    { op: 'summarize', label: 'Resumir' },
    { op: 'suggest_tags', label: 'Sugerir tags' },
    { op: 'contradiction_check', label: 'Verificar contradições' }
  ];

  function _aiBox() {
    var root = _root();
    return root && root.querySelector('[data-axs-ai]');
  }

  function acervoStudioAssistOpen() {
    var box = _aiBox();
    if (!box) return;
    var btns = AXS_ASSIST_OPS.map(function (o) {
      return '<button type="button" class="axs-ai-op" data-ai-op="' + o.op + '">✦ ' + _esc(o.label) + '</button>';
    }).join('');
    box.innerHTML = '<div class="axs-ai-bar">' + btns + '</div><div class="axs-ai-out" data-ai-out></div>';
    box.querySelectorAll('[data-ai-op]').forEach(function (b) {
      b.addEventListener('click', function () { acervoStudioAssist(b.getAttribute('data-ai-op')); });
    });
  }
  window.acervoStudioAssistOpen = acervoStudioAssistOpen;

  async function acervoStudioAssist(op) {
    var box = _aiBox();
    var out = box && box.querySelector('[data-ai-out]');
    if (!out || !AXS.selectedPath) return;
    out.innerHTML = '<div class="axs-env-note">Consultando o Hermes…</div>';
    box.querySelectorAll('[data-ai-op]').forEach(function (b) { b.disabled = true; });
    var r;
    try {
      r = await api('/api/acervo/x/assist', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), path: AXS.selectedPath, op: op }),
        timeoutMs: 120000
      });
    } catch (e) {
      out.innerHTML = '<div class="axs-env-note">' + _esc('Falha na assistência' + _detail(e)) + '</div>';
      return;
    } finally {
      box.querySelectorAll('[data-ai-op]').forEach(function (b) { b.disabled = false; });
    }
    if (r && r.offline) { out.innerHTML = '<div class="axs-env-note">Agente offline — tente novamente.</div>'; return; }
    if (!r || !r.ok || !r.proposal) { out.innerHTML = '<div class="axs-env-note">' + _esc((r && r.error) || 'Não foi possível gerar a proposta.') + '</div>'; return; }
    _renderAssist(out, op, r.proposal);
  }
  window.acervoStudioAssist = acervoStudioAssist;

  function _fillEditorBody(text) {
    // Open the existing editor (x/save is the only write path) and prefill the
    // body; the owner still clicks Salvar. Returns true if the editor is present.
    if (typeof acervoStudioEdit === 'function') acervoStudioEdit();
    var root = _root();
    var ta = root && root.querySelector('[data-axs-ed="body"]');
    if (!ta) return false;
    ta.value = text;
    AXS.dirty = true;
    return true;
  }

  function _fillEditorTags(tags) {
    if (typeof acervoStudioEdit === 'function') acervoStudioEdit();
    var root = _root();
    var inp = root && root.querySelector('[data-axs-fm="tags"]');
    if (!inp) return false;
    inp.value = tags.join(', ');
    AXS.dirty = true;
    return true;
  }

  function _renderAssist(out, op, p) {
    if (op === 'rewrite') {
      out.innerHTML = '<div class="axs-ai-card"><div class="axs-prop-head">Proposta de reescrita</div>' +
        '<pre class="axs-ai-pre">' + _esc(p.body_markdown || '') + '</pre>' +
        '<div class="axs-acts"><button type="button" class="axs-act axs-act-primary" data-ai-apply="body">Aplicar no editor</button></div>' +
        '<div class="axs-env-note">Proposta — nada é salvo até você editar e clicar em Salvar.</div></div>';
      out.querySelector('[data-ai-apply]').addEventListener('click', function () {
        if (_fillEditorBody(p.body_markdown || '')) _toast('Aplicado no editor — revise e salve', 'success');
      });
    } else if (op === 'summarize') {
      out.innerHTML = '<div class="axs-ai-card"><div class="axs-prop-head">Resumo</div>' +
        '<div class="axs-ai-text">' + _esc(p.summary || '') + '</div>' +
        '<div class="axs-env-note">Proposta somente-leitura.</div></div>';
    } else if (op === 'suggest_tags') {
      var chips = (p.tags || []).map(function (t) { return '<span class="axs-chip">#' + _esc(t) + '</span>'; }).join(' ');
      out.innerHTML = '<div class="axs-ai-card"><div class="axs-prop-head">Tags sugeridas</div>' +
        '<div class="axs-ai-tags">' + chips + '</div>' +
        '<div class="axs-acts"><button type="button" class="axs-act axs-act-primary" data-ai-apply="tags">Aplicar no editor</button></div></div>';
      out.querySelector('[data-ai-apply]').addEventListener('click', function () {
        if (_fillEditorTags(p.tags || [])) _toast('Tags aplicadas no editor — revise e salve', 'success');
      });
    } else if (op === 'contradiction_check') {
      if (p.consistent || !(p.findings || []).length) {
        out.innerHTML = '<div class="axs-ai-card"><div class="axs-prop-head">✓ Sem contradições encontradas</div></div>';
      } else {
        var items = p.findings.map(function (f) {
          return '<li><b>' + _esc(f.claim) + '</b>' + (f.conflict ? ' ⇄ ' + _esc(f.conflict) : '') + '</li>';
        }).join('');
        out.innerHTML = '<div class="axs-ai-card"><div class="axs-prop-head">Possíveis contradições</div>' +
          '<ul class="axs-ai-finds">' + items + '</ul>' +
          '<div class="axs-env-note">Proposta — revise você mesmo antes de editar.</div></div>';
      }
    }
  }

  async function acervoStudioAsk(q) {
    var root = _root();
    if (!root) return;
    q = (q || '').trim();
    if (!q) return;
    var reader = root.querySelector('[data-axs="reader"]');
    var host = reader.querySelector('[data-axs-ask]');
    if (!host) {
      host = document.createElement('div');
      host.setAttribute('data-axs-ask', '');
      reader.insertBefore(host, reader.firstChild);
    }
    host.innerHTML = '<div class="axs-env-note">Perguntando ao acervo…</div>';
    var r;
    try {
      r = await api('/api/acervo/x/ask', {
        method: 'POST', body: JSON.stringify({ session_id: _sid(), question: q }),
        timeoutMs: 120000
      });
    } catch (e) {
      host.innerHTML = '<div class="axs-env-note">' + _esc('Falha ao perguntar' + _detail(e)) + '</div>';
      return;
    }
    if (r && r.offline) { host.innerHTML = '<div class="axs-env-note">Agente offline — tente novamente.</div>'; return; }
    if (r && r.no_context) { host.innerHTML = '<div class="axs-env-note">Nada relevante encontrado no acervo.</div>'; return; }
    if (!r || !r.ok) { host.innerHTML = '<div class="axs-env-note">' + _esc((r && r.error) || 'Não foi possível responder.') + '</div>'; return; }
    var srcs = (r.sources || []).map(function (s) {
      return '<button type="button" class="axs-ask-src" data-ask-src="' + _esc(s) + '">' + _esc(s) + '</button>';
    }).join(' ');
    host.innerHTML = '<div class="axs-ai-card axs-ask-card"><div class="axs-prop-head">✦ Resposta do acervo</div>' +
      '<div class="axs-ai-text">' + _esc(r.answer || '') + '</div>' +
      (srcs ? '<div class="axs-ask-srcs">Fontes: ' + srcs + '</div>' : '') +
      '<div class="axs-env-note">Resposta ancorada nas fontes citadas — verifique antes de agir.</div></div>';
    host.querySelectorAll('[data-ask-src]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (typeof acervoStudioOpenPage === 'function') acervoStudioOpenPage(b.getAttribute('data-ask-src'));
      });
    });
  }
  window.acervoStudioAsk = acervoStudioAsk;
```

- [ ] **Step 5: Add the ✦ Perguntar button in `acervoStudioSearch`** — replace the
  `var html = '<div class="axs-results">';` line with a version that prepends an ask
  button (query is in scope as `q`):

```js
    var html = '<div class="axs-ask-launch"><button type="button" class="axs-act axs-act-primary" data-ask-go>✦ Perguntar ao acervo</button></div><div class="axs-results">';
```

  and, right after `reader.innerHTML = html;`, wire it:

```js
    var askGo = reader.querySelector('[data-ask-go]');
    if (askGo) askGo.addEventListener('click', function () { acervoStudioAsk(q); });
```

- [ ] **Step 6: Append the CSS** (end of `static/acervo-studio.css`):

```css
/* Phase 4: assist + ask */
.axs-ai:empty { display: none; }
.axs-ai-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.axs-ai-op { padding: 5px 11px; border-radius: 7px; border: 1px solid var(--axs-bd2);
  background: var(--axs-surf); color: var(--axs-ink); cursor: pointer;
  font: 500 12px/1 var(--axs-sans); }
.axs-ai-op:hover { border-color: var(--axs-acc); color: var(--axs-strong); }
.axs-ai-op:disabled { opacity: .5; cursor: default; }
.axs-ai-card { margin-top: 12px; padding: 12px; border: 1px solid var(--axs-bd2);
  border-radius: 8px; background: var(--axs-surf2); }
.axs-ai-pre { white-space: pre-wrap; font-family: var(--axs-mono); font-size: 12px;
  line-height: 1.5; max-height: 40vh; overflow: auto; margin: 8px 0; }
.axs-ai-text { font-size: 13.5px; line-height: 1.6; margin: 6px 0; }
.axs-ai-tags { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.axs-ai-finds { margin: 8px 0 0; padding-left: 18px; font-size: 12.5px; line-height: 1.6; }
.axs-ask-launch { margin-bottom: 12px; }
.axs-ask-card { background: var(--axs-accbg); border-color: var(--axs-accbd); }
.axs-ask-srcs { margin-top: 8px; font-size: 12px; }
.axs-ask-src { background: none; border: none; color: var(--axs-acct); cursor: pointer;
  text-decoration: underline; font: 400 12px/1.4 var(--axs-mono); padding: 0 2px; }
```

- [ ] **Step 7: Verify + commit**

Run: `node --check static/acervo-studio.js && npm run lint:runtime`
Expected: no errors

```bash
git add static/acervo-studio.js static/acervo-studio.css
git commit -m "feat(acervo-studio): assist strip + ask-the-acervo UI (Phase 4 T4)"
```

---

### Task 5 — Verification: live fixture E2E + regression + rebase-safety

**Files:** none (verification only; report to `.superpowers/sdd/e2e-report-phase4.md`).

- [ ] **Step 1:** MOD-010 suite green; full suite no NEW failures (serial re-run any
  contention noise) vs the ~16 env baseline.
- [ ] **Step 2: Live fixture E2E** — throwaway fixture (pages incl. a known fact + a
  self-contradicting page) + temp `HERMES_HOME` (agent OFFLINE): open a page → ✦ Assistir
  → each op returns the calm offline note; search → ✦ Perguntar → offline note. THEN
  network-stub `x/assist`/`x/ask` through the real handlers to verify every render path
  incl. apply-to-editor (rewrite → editor body prefilled + dirty; suggest_tags → tags
  input prefilled + dirty; the SAVE stays the owner's existing `x/save`), and ask sources
  are clickable → open the cited page. Console clean; kill server; remove fixture.
- [ ] **Step 3: Rebase-safety** — shared-file diff EMPTY.
- [ ] **Step 4: Record** results in `.superpowers/sdd/progress.md`.

---

### Task 6 — Governance: catalog + COLLAB record + IDENTITY

**Files:**
- Modify: `EXOCRTX_MODIFICATIONS.md` — MOD-010 "Fase 4" bullet.
- Create (umbrella): `.harness/changes/2026-07-12_collab_hermes-webui-acervo-studio-phase4.md`
- Modify (umbrella): `.harness/subprojects/hermes-webui/IDENTITY.md` — MOD-010 Phase 4 note.

- [ ] **Step 1:** Catalog entry (hermes-webui branch) — commit.
- [ ] **Step 2:** COLLAB record + IDENTITY note (umbrella, its own commit).

---

## Self-review notes

- Spec coverage: RFC §6.1 Assist (rewrite/summarize/suggest_tags/contradiction_check,
  proposal-only, applied edits via x/save) ✔; RFC §5.1 command-bar "ask the acervo" ✔;
  §9 degradation (offline/no_context calm) ✔; brief Phase-4 scope ✔.
- Grounding: ask sources server-validated as a subset of retrieved paths (test pinned).
- No placeholders; every code step is complete.
- Type consistency: `propose_assist`/`ask_acervo` shapes match the routes and the JS
  readers (`proposal.body_markdown|summary|tags|findings`; `answer`/`sources`).
- YAGNI: no acervoctl-retrieve dependency (needs a prebuilt catalog); no new write path
  (apply flows through the existing editor + x/save); assist is single-page only.
