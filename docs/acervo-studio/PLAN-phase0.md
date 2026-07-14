# Acervo Studio — Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a complete, read-only **Acervo Studio** — a self-contained full-screen surface inside the hermes-webui SPA that unifies navigation across all acervo scopes (Soul/Global/Shared/Microversos/Artefatos/Inbox), renders pages in a calm reader, and follows the app's theme (Graphite dark + current EXCRTX light).

**Architecture:** New isolated files only (`api/acervo_studio.py` deferred to Phase 1; Phase 0 extends the MOD-009 `api/acervo_explorer.py` tree endpoint + adds `static/acervo-studio.{js,css}`). The backend gains two new tree scopes (`micro`, `inbox`) factored as **pure helper functions** so they unit-test exactly like the MOD-009 suite. The frontend is a vanilla-JS IIFE mounted full-screen and reparented to `<body>`, toggling with Chat, reusing the MOD-009 read endpoints (`/api/acervo/x/{tree,page,search,raw}`) and the app globals (`S`, `api`, `renderMd`, `esc`, `showToast`, `humanizeFilename`). Zero new `routes.py` lines (the `/api/acervo/x/` prefix dispatch already exists); three lines added to `index.html`.

**Tech Stack:** Python 3 stdlib HTTP server (no framework), PyYAML; vanilla ES (`sourceType:"script"`, IIFE, no build/bundler); pytest (hermetic tmp acervo); ESLint runtime-guard.

## Global Constraints

- **Vanilla JS only** — new JS is IIFE-scoped, `'use strict'`, **no ES `import`/`export`** (enforced by `npm run lint:runtime`). No framework, no bundler, no build step.
- **Rebase-safe / self-contained** — all new behavior in **new files**. Upstream-owned files get the **minimum**: `static/index.html` gains exactly 3 lines (CSS link, mount div, script include). `api/routes.py` gains **0 lines** (the `startswith("/api/acervo/x/")` dispatch from MOD-009 already routes to `handle_acervo_x_get/post`). Never edit `static/style.css`, `static/ui.js`, `static/workspace.js`, `static/acervo.js`, `static/acervo-explorer.*`.
- **CSS namespace `.axs-*`** and **JS global prefix `acervoStudio*` / `AXS`** — must not collide with MOD-009's `.ax-*` / `acervoExplorer*` / `AX`.
- **Read-only in Phase 0** — no writes to the acervo. All endpoints are GET. `.quarantine/` stays unreachable (`_safe_acervo_path` already rejects any `.`-prefixed component).
- **Path root is always `_acervo_root()`** — never the session workspace. Every endpoint is session-gated (reuse the MOD-009 session-check idiom).
- **Reused routes.py helpers (late `import api.routes as routes` inside functions):** `_acervo_root`, `_resolve_session_workspace`, `_ACERVO_NATURES`, `_read_frontmatter_meta`, `_read_frontmatter_title`, `_humanize_slug`, `j`, `bad`.
- **Reused frontend globals (do not redeclare):** `S`, `api(url[,opts])` (returns parsed JSON; `await api(url)` for GET), `esc`, `showToast`, `renderMd(raw)→html`, `humanizeFilename(rel)→str`. Session id via `S.session.session_id`.
- **Cache-bust token** — asset URLs in `index.html` use the existing `?v=__WEBUI_VERSION__` pattern.
- **Test baseline** — full suite baseline is documented as 9070 pass / 17 pre-existing fails; Phase 0 must add **zero new failures**.

---

### Task 1: Backend — `scope=micro` in the unified tree

**Files:**
- Modify: `api/acervo_explorer.py` (add `_micro_nodes` helper; extend `handle_tree` scope allowlist + branch)
- Test: `tests/test_mod010_acervo_studio.py` (new)

**Interfaces:**
- Produces: `_micro_nodes(routes, root, slug, depth) -> list[dict]` — when `slug` is empty, a list of `{"type":"microverse","slug","title","rel_path","count"}` (one per `micro/<slug>/` dir, `count` = total `.md` pages across its natures); when `slug` is set, the same nature+page node shape `handle_tree` already emits for global/shared (`{"type":"nature",...}` and, at `depth>=2`, `_node_for_page(...)`).
- Consumes: `routes._acervo_root`, `routes._ACERVO_NATURES`, `_node_for_page`, `_rel_to_root`, `_safe_acervo_path`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_mod010_acervo_studio.py`:

```python
"""MOD-010 Acervo Studio — hermetic backend unit tests (Phase 0).

Tests the pure tree helpers added to api/acervo_explorer.py for the new
`micro` and `inbox` scopes, mirroring the MOD-009 hermetic style:
api.routes._acervo_root is monkeypatched onto a tmp_path acervo.
"""
import pytest

import api.acervo_explorer as ax
import api.routes as routes


@pytest.fixture
def acervo(tmp_path, monkeypatch):
    root = tmp_path / "acervo"
    (root / "micro" / "comercial" / "knowledge").mkdir(parents=True)
    (root / "micro" / "comercial" / "decisions").mkdir(parents=True)
    (root / "micro" / "_template" / "knowledge").mkdir(parents=True)  # underscore -> skipped
    (root / "_inbox" / "incoming").mkdir(parents=True)
    monkeypatch.setattr(routes, "_acervo_root", lambda: root)
    return root


def _w(root, rel, text="---\ntitle: T\n---\n\nbody\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_micro_nodes_lists_microverses_with_counts(acervo):
    _w(acervo, "micro/comercial/knowledge/precificacao.md")
    _w(acervo, "micro/comercial/decisions/alcada.md")
    nodes = ax._micro_nodes(routes, acervo, "", 1)
    slugs = {n["slug"]: n for n in nodes if n["type"] == "microverse"}
    assert "comercial" in slugs
    assert "_template" not in slugs          # underscore dirs skipped
    assert slugs["comercial"]["count"] == 2  # 2 pages across natures


def test_micro_nodes_lists_pages_for_a_slug(acervo):
    _w(acervo, "micro/comercial/knowledge/precificacao.md",
       "---\ntitle: Precificação\nstatus: ready\n---\n\nx\n")
    nodes = ax._micro_nodes(routes, acervo, "comercial", 2)
    natures = [n for n in nodes if n["type"] == "nature"]
    pages = [n for n in nodes if n["type"] == "page"]
    assert any(n["name"] == "knowledge" for n in natures)
    assert any(p["title"] == "Precificação" and p["status"] == "ready" for p in pages)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/elder/projetos/projetob/hermes-webui && python -m pytest tests/test_mod010_acervo_studio.py -q`
Expected: FAIL with `AttributeError: module 'api.acervo_explorer' has no attribute '_micro_nodes'`.

- [ ] **Step 3: Add the `_micro_nodes` helper**

In `api/acervo_explorer.py`, immediately **after** `_node_for_page(...)` (ends ~line 224), insert:

```python
def _micro_nodes(routes, root, slug, depth):
    """Tree nodes for the `micro` scope.

    No slug -> one node per `micro/<slug>/` directory (skipping `_`/`.`-prefixed),
    with a friendly title (from `_meta/index.md` if present, else humanized slug)
    and a page count across its natures. With slug -> nature nodes + (depth>=2) page
    nodes, exactly like the global/shared branch of handle_tree.
    """
    nodes = []
    micro_dir = root / "micro"
    if not slug:
        if not micro_dir.is_dir():
            return nodes
        try:
            dirs = sorted([d for d in micro_dir.iterdir()
                           if d.is_dir() and not d.name.startswith(("_", "."))],
                          key=lambda p: p.name)
        except OSError:
            return nodes
        for d in dirs:
            count = 0
            for nat in routes._ACERVO_NATURES:
                nd = d / nat
                if not nd.is_dir():
                    continue
                try:
                    count += sum(1 for f in nd.iterdir()
                                 if f.is_file() and f.suffix.lower() == ".md"
                                 and not f.name.startswith(("_", ".")))
                except OSError:
                    pass
            title = (routes._read_frontmatter_title(d / "_meta" / "index.md")
                     or routes._humanize_slug(d.name))
            nodes.append({
                "type": "microverse",
                "slug": d.name,
                "title": title,
                "rel_path": _rel_to_root(d, root),
                "count": count,
            })
        return nodes

    base = micro_dir / slug
    if not base.is_dir():
        return nodes
    for nat in routes._ACERVO_NATURES:
        nd = base / nat
        if not nd.is_dir():
            continue
        try:
            files = [f for f in nd.iterdir()
                     if f.is_file() and f.suffix.lower() == ".md"
                     and not f.name.startswith(("_", "."))]
        except OSError:
            files = []
        nodes.append({"type": "nature", "name": nat,
                      "rel_path": _rel_to_root(nd, root), "count": len(files)})
        if depth >= 2:
            for f in sorted(files, key=lambda p: p.name):
                nodes.append(_node_for_page(routes, f, root, nature=nat, scope="micro"))
    return nodes
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_mod010_acervo_studio.py -q`
Expected: 2 passed.

- [ ] **Step 5: Wire `scope=micro` into `handle_tree`**

In `api/acervo_explorer.py`, in `handle_tree`, change the scope allowlist line:

```python
    if scope not in ("global", "shared", "macro", "artifacts"):
        return routes.bad(handler, "scope must be one of: global, shared, macro, artifacts")
```

to:

```python
    if scope not in ("global", "shared", "macro", "artifacts", "micro", "inbox"):
        return routes.bad(handler, "scope must be one of: global, shared, macro, artifacts, micro, inbox")
```

Then, immediately **before** the `if scope == "macro":` line, insert the micro branch:

```python
    if scope == "micro":
        nodes = _micro_nodes(routes, root, slug, depth)
        return routes.j(handler, {"scope": scope,
                                  "root": "micro" + ("/" + slug if slug else ""),
                                  "nodes": nodes, "count": len(nodes)})
```

- [ ] **Step 6: Run the full new test file + lint the touched module**

Run: `python -m pytest tests/test_mod010_acervo_studio.py -q && python -c "import ast,sys; ast.parse(open('api/acervo_explorer.py').read())"`
Expected: 2 passed; no syntax error.

- [ ] **Step 7: Commit**

```bash
git add api/acervo_explorer.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): micro scope in unified tree (MOD-010 Phase 0)"
```

---

### Task 2: Backend — `scope=inbox` in the unified tree

**Files:**
- Modify: `api/acervo_explorer.py` (add `_inbox_nodes` helper; add `handle_tree` branch)
- Test: `tests/test_mod010_acervo_studio.py` (extend)

**Interfaces:**
- Produces: `_inbox_nodes(routes, root) -> list[dict]` — one node per `_inbox/incoming/<envelope>/` dir: `{"type":"intake","id","title","status","rel_path"}`. `status` comes from `<envelope>/manifest.json` (`status` field) when present, else `"received"`; `title` from manifest `title`/`friendly_name` when present, else humanized dir name. Read-only.
- Consumes: `routes._humanize_slug`, `_rel_to_root`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mod010_acervo_studio.py`:

```python
import json


def test_inbox_nodes_lists_incoming_envelopes(acervo):
    env = acervo / "_inbox" / "incoming" / "int_20260616_open-notebook"
    (env / "original").mkdir(parents=True)
    (env / "manifest.json").write_text(
        json.dumps({"title": "Open Notebook", "status": "received"}),
        encoding="utf-8")
    (acervo / "_inbox" / "incoming" / "int_20260701_bare").mkdir(parents=True)

    nodes = ax._inbox_nodes(routes, acervo)
    by_id = {n["id"]: n for n in nodes}
    assert by_id["int_20260616_open-notebook"]["title"] == "Open Notebook"
    assert by_id["int_20260616_open-notebook"]["status"] == "received"
    # Bare envelope with no manifest still lists, with a defaulted status.
    assert by_id["int_20260701_bare"]["status"] == "received"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_mod010_acervo_studio.py::test_inbox_nodes_lists_incoming_envelopes -q`
Expected: FAIL with `AttributeError: ... has no attribute '_inbox_nodes'`.

- [ ] **Step 3: Add the `_inbox_nodes` helper**

In `api/acervo_explorer.py`, immediately **after** `_micro_nodes(...)`, insert:

```python
def _inbox_nodes(routes, root):
    """Tree nodes for the `inbox` scope — one per `_inbox/incoming/<envelope>/`.

    Read-only. Title/status come from the envelope's manifest.json when present
    (Phase 0 does not extract or promote — that is Phase 2).
    """
    import json
    nodes = []
    inc = root / "_inbox" / "incoming"
    if not inc.is_dir():
        return nodes
    try:
        dirs = sorted([d for d in inc.iterdir()
                       if d.is_dir() and not d.name.startswith(".")],
                      key=lambda p: p.name, reverse=True)
    except OSError:
        return nodes
    for d in dirs:
        title = routes._humanize_slug(d.name)
        status = "received"
        mf = d / "manifest.json"
        if mf.is_file():
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    title = data.get("title") or data.get("friendly_name") or title
                    status = data.get("status") or status
            except (OSError, ValueError):
                pass
        nodes.append({"type": "intake", "id": d.name, "title": title,
                      "status": status, "rel_path": _rel_to_root(d, root)})
    return nodes
```

- [ ] **Step 4: Wire `scope=inbox` into `handle_tree`**

In `handle_tree`, immediately **after** the `if scope == "micro":` block you added in Task 1, insert:

```python
    if scope == "inbox":
        nodes = _inbox_nodes(routes, root)
        return routes.j(handler, {"scope": scope, "root": "_inbox/incoming",
                                  "nodes": nodes, "count": len(nodes)})
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_mod010_acervo_studio.py -q`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add api/acervo_explorer.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): inbox scope in unified tree (MOD-010 Phase 0)"
```

---

### Task 3: Frontend — shell scaffold, mount, toggle

**Files:**
- Create: `static/acervo-studio.js`
- Create: `static/acervo-studio.css`
- Modify: `static/index.html` (3 lines: CSS link after l.72, mount div after l.1454, script after l.1525)

**Interfaces:**
- Produces: global `window.acervoStudioToggle()` (opens/closes the Studio); module state `AXS`; a self-injected launcher `#axsLauncher`. Later tasks add render functions inside the same IIFE.
- Consumes: `S`, `esc`, `showToast`.

- [ ] **Step 1: Create the CSS with the theme tokens**

Create `static/acervo-studio.css`:

```css
/* MOD-010 Acervo Studio — self-contained, .axs-* namespace. Read-only Phase 0.
   Theme follows the app: default vars = current EXCRTX light; :root.dark = Graphite. */
#acervoStudioRoot[hidden]{display:none !important;}
.axs-root{
  --axs-bg:#f4f5f8;--axs-sb:#e8ecf2;--axs-surf:#ffffff;--axs-surf2:#f0f2f6;
  --axs-bd:#d2d6e3;--axs-bd2:#bcc1ce;--axs-ink:#03123f;--axs-strong:#010a28;
  --axs-mut:#8f8a91;--axs-em:#1a3c86;--axs-acc:#1376ed;--axs-acct:#0e5fd6;
  --axs-accbg:rgba(19,118,237,.08);--axs-accbd:rgba(19,118,237,.32);
  --axs-ok:#38A169;--axs-line:#e4e8ef;
  --axs-serif:Georgia,'Times New Roman',serif;
  --axs-sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,system-ui,sans-serif;
  --axs-mono:'SF Mono',ui-monospace,monospace;
  position:fixed;inset:0;z-index:1200;background:var(--axs-bg);color:var(--axs-ink);
  font-family:var(--axs-sans);display:flex;flex-direction:column;
}
:root.dark .axs-root{
  --axs-bg:#1b1d21;--axs-sb:#202226;--axs-surf:#26292e;--axs-surf2:#212327;
  --axs-bd:#32353b;--axs-bd2:#3d414a;--axs-ink:#d7d8db;--axs-strong:#f0f1f3;
  --axs-mut:#888b93;--axs-em:#a9adb5;--axs-acc:#3b8af0;--axs-acct:#6baaf6;
  --axs-accbg:rgba(59,138,240,.12);--axs-accbd:rgba(59,138,240,.4);
  --axs-ok:#7EC98C;--axs-line:#2b2e34;
}
.axs-top{height:46px;display:flex;align-items:center;gap:12px;padding:0 12px;
  background:var(--axs-sb);border-bottom:1px solid var(--axs-bd);flex:none;}
.axs-mode{display:flex;background:var(--axs-bg);border:1px solid var(--axs-bd2);
  border-radius:8px;padding:2px;font:600 11.5px/1 var(--axs-sans);}
.axs-mode button{padding:5px 11px;border-radius:6px;color:var(--axs-mut);
  background:none;border:none;cursor:pointer;font:inherit;}
.axs-mode button.on{background:var(--axs-surf);color:var(--axs-strong);}
.axs-cmd{flex:1;max-width:520px;margin:0 auto;height:30px;background:var(--axs-bg);
  border:1px solid var(--axs-bd2);border-radius:9px;display:flex;align-items:center;
  padding:0 11px;}
.axs-cmd input{flex:1;background:none;border:none;outline:none;color:var(--axs-ink);
  font:400 12.5px/1 var(--axs-sans);}
.axs-body{flex:1;display:flex;min-height:0;}
.axs-nav{width:250px;flex:none;background:var(--axs-sb);
  border-right:1px solid var(--axs-bd);overflow:auto;padding:10px 8px;}
.axs-reader{flex:1;min-width:0;display:flex;flex-direction:column;background:var(--axs-bg);}
.axs-launcher{position:fixed;right:14px;bottom:14px;z-index:1100;display:flex;
  align-items:center;gap:7px;background:var(--axs-acc,#1376ed);color:#fff;border:none;
  border-radius:10px;padding:10px 13px;cursor:pointer;font:600 12px/1 system-ui;
  box-shadow:0 6px 18px -6px rgba(0,0,0,.5);}
```

- [ ] **Step 2: Create the JS scaffold**

Create `static/acervo-studio.js`:

```javascript
/* MOD-010 Acervo Studio — self-contained full-screen surface. Read-only Phase 0.
   No ES import/export (sourceType:"script"); reuses app globals S/api/esc/showToast/
   renderMd/humanizeFilename. Prefix: acervoStudio* / AXS / .axs-*. */
'use strict';
(function () {
  var AXS = { built: false, open: false, scope: 'micro', slug: '', selectedPath: '' };

  function _sid() { return (typeof S !== 'undefined' && S && S.session) ? S.session.session_id : ''; }
  function _esc(s) { return (typeof esc === 'function') ? esc(s) : String(s == null ? '' : s); }
  function _toast(m, t) { if (typeof showToast === 'function') showToast(m, t); }
  function _root() { return document.getElementById('acervoStudioRoot'); }

  function _build() {
    if (AXS.built) return;
    var root = _root();
    if (!root) return;
    // Reparent to <body>: aside.rightpanel carries a CSS transform that traps
    // position:fixed (the MOD-009 lesson).
    if (root.parentElement !== document.body) document.body.appendChild(root);
    root.className = 'axs-root';
    root.innerHTML =
      '<div class="axs-top">' +
      '  <div class="axs-mode">' +
      '    <button type="button" data-axs="chat">Chat</button>' +
      '    <button type="button" class="on" data-axs="acervo">Acervo</button>' +
      '  </div>' +
      '  <div class="axs-cmd"><input type="search" data-axs="q" ' +
      '     placeholder="Perguntar ou buscar no acervo…" aria-label="Buscar"></div>' +
      '</div>' +
      '<div class="axs-body">' +
      '  <nav class="axs-nav" data-axs="nav" aria-label="Acervo"></nav>' +
      '  <section class="axs-reader" data-axs="reader"></section>' +
      '</div>';
    root.querySelector('[data-axs="chat"]').addEventListener('click', _close);
    AXS.built = true;
  }

  function _open() {
    _build();
    var root = _root();
    root.hidden = false;
    AXS.open = true;
    _showLauncher(false);
    if (typeof acervoStudioRenderNav === 'function') acervoStudioRenderNav();
  }
  function _close() {
    var root = _root();
    if (root) root.hidden = true;
    AXS.open = false;
    _showLauncher(true);
  }

  function _ensureLauncher() {
    if (document.getElementById('axsLauncher')) return;
    var b = document.createElement('button');
    b.id = 'axsLauncher';
    b.className = 'axs-launcher';
    b.type = 'button';
    b.title = 'Abrir o Acervo';
    b.innerHTML = '<span>▤</span><span>Acervo</span>';
    b.addEventListener('click', acervoStudioToggle);
    document.body.appendChild(b);
  }
  function _showLauncher(show) {
    var b = document.getElementById('axsLauncher');
    if (b) b.style.display = show ? '' : 'none';
  }

  function acervoStudioToggle() { if (AXS.open) _close(); else _open(); }
  window.acervoStudioToggle = acervoStudioToggle;

  // Expose module internals to later-task render functions in this IIFE.
  window.__AXS = { state: AXS, sid: _sid, esc: _esc, toast: _toast, root: _root };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _ensureLauncher);
  } else {
    _ensureLauncher();
  }
})();
```

- [ ] **Step 3: Add the 3 lines to `index.html`**

After the `acervo-explorer.css` link (l.72):

```html
<link rel="stylesheet" href="static/acervo-studio.css?v=__WEBUI_VERSION__">
```

After `<div id="acervoExplorerRoot" hidden></div>` (l.1454):

```html
    <div id="acervoStudioRoot" hidden></div>
```

After the `acervo-explorer.js` script (l.1525):

```html
<script src="static/acervo-studio.js?v=__WEBUI_VERSION__" defer></script>
```

- [ ] **Step 4: Lint + syntax-check + grep the insertions**

Run:
```bash
node --check static/acervo-studio.js && \
npm run lint:runtime && \
grep -c 'acervo-studio.css' static/index.html && \
grep -c 'acervoStudioRoot' static/index.html && \
grep -c 'acervo-studio.js' static/index.html
```
Expected: no errors; each grep prints `1`.

- [ ] **Step 5: Manual E2E — launcher + toggle**

Run an isolated server and drive it:
```bash
HERMES_HOME="$(mktemp -d)" ACERVO="$HOME/exocortex/acervo" HERMES_WEBUI_PORT=8799 python server.py --port 8799
```
In a browser at `http://localhost:8799`: confirm a floating **▤ Acervo** launcher appears; click it → the Studio opens full-screen with a top bar (Chat | Acervo toggle + search box) and an empty nav + reader; click **Chat** → it closes and the launcher returns.
Expected: toggle works; no console errors from `acervo-studio.js`.

- [ ] **Step 6: Commit**

```bash
git add static/acervo-studio.js static/acervo-studio.css static/index.html
git commit -m "feat(acervo-studio): shell scaffold + mount + toggle (MOD-010 Phase 0)"
```

---

### Task 4: Frontend — unified navigator

**Files:**
- Modify: `static/acervo-studio.js` (add `acervoStudioRenderNav` + scope loaders)
- Modify: `static/acervo-studio.css` (nav item styles)

**Interfaces:**
- Consumes: `window.__AXS` (state/sid/esc/toast/root), `api`, `humanizeFilename`.
- Produces: `window.acervoStudioRenderNav()` — populates `[data-axs="nav"]`; clicking a page calls `acervoStudioOpenPage(relPath)` (defined in Task 5); global `acervoStudioSelectScope(scope, slug)`.

- [ ] **Step 1: Add nav CSS**

Append to `static/acervo-studio.css`:

```css
.axs-sec{font:600 9.5px/1 var(--axs-sans);letter-spacing:.08em;text-transform:uppercase;
  color:var(--axs-mut);margin:12px 8px 6px;}
.axs-ni{display:flex;align-items:center;gap:9px;padding:6px 8px;border-radius:7px;
  font:500 12.5px/1 var(--axs-sans);color:var(--axs-ink);cursor:pointer;}
.axs-ni:hover{background:var(--axs-surf2);}
.axs-ni.on{background:var(--axs-surf);}
.axs-ni .ico{width:15px;text-align:center;}
.axs-ni.on .ico{color:var(--axs-acc);}
.axs-ni .ct{margin-left:auto;font:600 9.5px/1 var(--axs-mono);color:#fff;
  background:var(--axs-acc);border-radius:999px;padding:2px 6px;}
.axs-pi{display:flex;align-items:center;gap:7px;padding:4px 8px 4px 26px;border-radius:6px;
  font:400 11.5px/1.3 var(--axs-sans);color:var(--axs-mut);cursor:pointer;}
.axs-pi:hover{background:var(--axs-surf2);color:var(--axs-ink);}
.axs-pi.on{color:var(--axs-strong);background:var(--axs-surf);}
.axs-pi .st{width:6px;height:6px;border-radius:50%;flex:none;background:var(--axs-mut);}
.axs-pi .st.ready{background:var(--axs-ok);}
.axs-empty{color:var(--axs-mut);font:400 11px/1.5 var(--axs-sans);padding:10px 8px;}
```

- [ ] **Step 2: Add the navigator renderer**

In `static/acervo-studio.js`, **inside the IIFE**, before the `acervoStudioToggle` definition, add:

```javascript
  var SCOPES = [
    { key: 'macro', ico: '🧠', label: 'Soul', tree: true },
    { key: 'global', ico: '🌐', label: 'Global', tree: true },
    { key: 'shared', ico: '🔗', label: 'Shared', tree: true },
    { key: 'micro', ico: '🪐', label: 'Microversos', tree: true },
    { key: 'artifacts', ico: '📦', label: 'Artefatos', tree: true },
    { key: 'inbox', ico: '📥', label: 'Inbox', tree: true }
  ];

  async function _tree(scope, slug) {
    var url = '/api/acervo/x/tree?session_id=' + encodeURIComponent(_sid()) +
      '&scope=' + encodeURIComponent(scope) + '&depth=2' +
      (slug ? '&slug=' + encodeURIComponent(slug) : '');
    return await api(url);
  }

  function _human(rel) {
    return (typeof humanizeFilename === 'function') ? humanizeFilename(rel) : String(rel || '');
  }

  async function acervoStudioRenderNav() {
    var nav = _root() && _root().querySelector('[data-axs="nav"]');
    if (!nav) return;
    if (!_sid()) { nav.innerHTML = '<div class="axs-empty">Sem sessão ativa.</div>'; return; }
    var html = '<div class="axs-sec">Acervo</div>';
    // Inbox count badge (best-effort).
    var inboxCount = 0;
    try { inboxCount = (await _tree('inbox', '')).count || 0; } catch (e) {}
    SCOPES.forEach(function (s) {
      var on = AXS.scope === s.key ? ' on' : '';
      var badge = (s.key === 'inbox' && inboxCount) ?
        '<span class="ct">' + inboxCount + '</span>' : '';
      html += '<div class="axs-ni' + on + '" data-scope="' + s.key + '">' +
        '<span class="ico">' + s.ico + '</span>' + _esc(s.label) + badge + '</div>' +
        '<div class="axs-sub" data-sub="' + s.key + '"></div>';
    });
    nav.innerHTML = html;
    nav.querySelectorAll('.axs-ni').forEach(function (el) {
      el.addEventListener('click', function () {
        acervoStudioSelectScope(el.getAttribute('data-scope'), '');
      });
    });
    if (AXS.scope) acervoStudioSelectScope(AXS.scope, AXS.slug);
  }

  async function acervoStudioSelectScope(scope, slug) {
    AXS.scope = scope; AXS.slug = slug || '';
    var nav = _root().querySelector('[data-axs="nav"]');
    nav.querySelectorAll('.axs-ni').forEach(function (el) {
      el.classList.toggle('on', el.getAttribute('data-scope') === scope);
    });
    var sub = nav.querySelector('[data-sub="' + scope + '"]');
    nav.querySelectorAll('.axs-sub').forEach(function (s) { if (s !== sub) s.innerHTML = ''; });
    if (!sub) return;
    sub.innerHTML = '<div class="axs-empty">Carregando…</div>';
    var data;
    try { data = await _tree(scope, slug); }
    catch (e) { sub.innerHTML = '<div class="axs-empty">Erro ao carregar.</div>'; return; }
    var nodes = data.nodes || [];
    if (!nodes.length) { sub.innerHTML = '<div class="axs-empty">Vazio.</div>'; return; }
    var out = '';
    nodes.forEach(function (n) {
      if (n.type === 'microverse') {
        out += '<div class="axs-pi" data-mv="' + _esc(n.slug) + '">🪐 ' +
          _esc(n.title) + (n.count ? ' (' + n.count + ')' : '') + '</div>';
      } else if (n.type === 'page') {
        var st = n.status === 'ready' ? ' ready' : '';
        out += '<div class="axs-pi" data-path="' + _esc(n.rel_path) + '">' +
          '<span class="st' + st + '"></span>' + _esc(n.title || _human(n.rel_path)) + '</div>';
      } else if (n.type === 'nature') {
        out += '<div class="axs-sec" style="margin-left:18px">' + _esc(n.name) +
          ' (' + (n.count || 0) + ')</div>';
      } else if (n.type === 'intake') {
        out += '<div class="axs-pi"><span class="st"></span>' + _esc(n.title) +
          ' · ' + _esc(n.status) + '</div>';
      } else if (n.type === 'artifact') {
        out += '<div class="axs-pi">📦 ' + _esc(n.title || n.name) + '</div>';
      }
    });
    sub.innerHTML = out;
    sub.querySelectorAll('[data-mv]').forEach(function (el) {
      el.addEventListener('click', function () {
        acervoStudioSelectScope('micro', el.getAttribute('data-mv'));
      });
    });
    sub.querySelectorAll('[data-path]').forEach(function (el) {
      el.addEventListener('click', function () {
        if (typeof acervoStudioOpenPage === 'function')
          acervoStudioOpenPage(el.getAttribute('data-path'));
      });
    });
  }
  window.acervoStudioRenderNav = acervoStudioRenderNav;
  window.acervoStudioSelectScope = acervoStudioSelectScope;
```

- [ ] **Step 3: Lint + syntax-check**

Run: `node --check static/acervo-studio.js && npm run lint:runtime`
Expected: clean.

- [ ] **Step 4: Manual E2E — navigate scopes**

With the isolated server (real acervo at `$HOME/exocortex/acervo`), open the Studio: click **Microversos** → the microverse list (comercial, sales-ai, …) appears; click a microverse → its natures + pages list; click **Inbox** → shows a count badge and any incoming envelopes; **Global/Shared/Soul** list their natures+pages.
Expected: all scopes load; no console errors.

- [ ] **Step 5: Commit**

```bash
git add static/acervo-studio.js static/acervo-studio.css
git commit -m "feat(acervo-studio): unified navigator across all scopes (MOD-010 Phase 0)"
```

---

### Task 5: Frontend — reader (page + non-md preview)

**Files:**
- Modify: `static/acervo-studio.js` (add `acervoStudioOpenPage`)
- Modify: `static/acervo-studio.css` (reader styles)

**Interfaces:**
- Consumes: `api`, `renderMd`, the `/api/acervo/x/{page,raw}` endpoints.
- Produces: `window.acervoStudioOpenPage(relPath)` — loads and renders a page (frontmatter chips + serif body) or a non-md raw preview into `[data-axs="reader"]`.

- [ ] **Step 1: Add reader CSS**

Append to `static/acervo-studio.css`:

```css
.axs-crumb{height:34px;display:flex;align-items:center;gap:7px;padding:0 20px;
  border-bottom:1px solid var(--axs-bd);font:400 11px/1 var(--axs-sans);color:var(--axs-mut);flex:none;}
.axs-crumb b{color:var(--axs-acct);font-weight:600;}
.axs-doc{flex:1;overflow:auto;padding:22px 26px;}
.axs-fm{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px;}
.axs-fm span{font:600 10px/1 var(--axs-sans);border-radius:6px;padding:5px 8px;
  border:1px solid var(--axs-bd2);color:var(--axs-em);background:var(--axs-surf2);}
.axs-fm .perene{color:var(--axs-acct);border-color:var(--axs-accbd);background:var(--axs-accbg);}
.axs-title{font:600 25px/1.25 var(--axs-serif);color:var(--axs-strong);margin:0 0 4px;}
.axs-md{font:400 15px/1.68 var(--axs-serif);color:var(--axs-ink);}
.axs-md h1,.axs-md h2,.axs-md h3{font-family:var(--axs-serif);color:var(--axs-strong);}
.axs-md a{color:var(--axs-acct);}
.axs-md code{font-family:var(--axs-mono);background:var(--axs-surf2);border-radius:4px;padding:1px 4px;}
.axs-md pre{background:var(--axs-surf2);border:1px solid var(--axs-bd);border-radius:8px;
  padding:12px;overflow:auto;}
.axs-raw{width:100%;height:70vh;border:1px solid var(--axs-bd);border-radius:8px;background:#fff;}
.axs-reader-empty{margin:auto;color:var(--axs-mut);font:400 13px/1.5 var(--axs-sans);
  text-align:center;padding:40px;}
```

- [ ] **Step 2: Add the reader**

In `static/acervo-studio.js`, inside the IIFE, add:

```javascript
  function _chip(label, cls) { return '<span class="' + (cls || '') + '">' + _esc(label) + '</span>'; }

  async function acervoStudioOpenPage(relPath) {
    AXS.selectedPath = relPath;
    var reader = _root().querySelector('[data-axs="reader"]');
    reader.innerHTML = '<div class="axs-reader-empty">Carregando…</div>';
    var p;
    try {
      p = await api('/api/acervo/x/page?session_id=' + encodeURIComponent(_sid()) +
        '&path=' + encodeURIComponent(relPath));
    } catch (e) {
      reader.innerHTML = '<div class="axs-reader-empty">Erro ao abrir a página.</div>';
      return;
    }
    var crumb = relPath.split('/').map(function (s, i, a) {
      return i === a.length - 1 ? _esc(s) : '<b>' + _esc(s) + '</b>';
    }).join(' › ');
    if (p && p.editable === false && p.raw_url) {
      var rawUrl = p.raw_url + '&session_id=' + encodeURIComponent(_sid());
      var isImg = (p.mime || '').indexOf('image/') === 0;
      var view = isImg
        ? '<img class="axs-raw" src="' + _esc(rawUrl) + '" alt="' + _esc(relPath) + '">'
        : '<iframe class="axs-raw" src="' + _esc(rawUrl) + '" sandbox></iframe>';
      reader.innerHTML = '<div class="axs-crumb">' + crumb + '</div><div class="axs-doc">' + view + '</div>';
      return;
    }
    var fm = (p && p.frontmatter) || {};
    var chips = '';
    if (fm.nature) chips += _chip(fm.nature);
    if (fm['class']) chips += _chip('🔒 ' + fm['class'],
      String(fm['class']).indexOf('peren') === 0 ? 'perene' : '');
    if (fm.status) chips += _chip('✓ ' + fm.status);
    (Array.isArray(fm.tags) ? fm.tags : []).forEach(function (t) { chips += _chip('#' + t); });
    var bodyHtml = (typeof renderMd === 'function') ? renderMd(p.body || '') : _esc(p.body || '');
    reader.innerHTML =
      '<div class="axs-crumb">' + crumb + '</div>' +
      '<div class="axs-doc">' +
      '  <div class="axs-fm">' + chips + '</div>' +
      '  <h1 class="axs-title">' + _esc(p.title || relPath) + '</h1>' +
      '  <div class="axs-md">' + bodyHtml + '</div>' +
      '</div>';
    // Mark the active page in the nav.
    var nav = _root().querySelector('[data-axs="nav"]');
    nav.querySelectorAll('.axs-pi').forEach(function (el) {
      el.classList.toggle('on', el.getAttribute('data-path') === relPath);
    });
  }
  window.acervoStudioOpenPage = acervoStudioOpenPage;
```

- [ ] **Step 3: Lint + syntax-check**

Run: `node --check static/acervo-studio.js && npm run lint:runtime`
Expected: clean.

- [ ] **Step 4: Manual E2E — open a page**

In the Studio, navigate Global ▸ knowledge (or a microverse) and click a page: the reader shows the breadcrumb, frontmatter chips (nature / perene / status / tags), the title in serif, and the markdown body rendered via `renderMd`. Open a non-md item (pdf/image) if present → it shows in a sandboxed frame / `<img>`.
Expected: renders correctly; the clicked page highlights in the nav; no console errors.

- [ ] **Step 5: Commit**

```bash
git add static/acervo-studio.js static/acervo-studio.css
git commit -m "feat(acervo-studio): reader with frontmatter chips + markdown/raw preview (MOD-010 Phase 0)"
```

---

### Task 6: Frontend — command bar search

**Files:**
- Modify: `static/acervo-studio.js` (wire the `[data-axs="q"]` input to `/search`)
- Modify: `static/acervo-studio.css` (results list)

**Interfaces:**
- Consumes: `api`, the `/api/acervo/x/search` endpoint, `acervoStudioOpenPage`.
- Produces: search-on-Enter that renders results into the reader; clicking a result opens it.

- [ ] **Step 1: Add results CSS**

Append to `static/acervo-studio.css`:

```css
.axs-results{padding:16px 20px;}
.axs-rescard{display:block;width:100%;text-align:left;background:var(--axs-surf);
  border:1px solid var(--axs-bd);border-radius:9px;padding:11px 13px;margin-bottom:8px;cursor:pointer;}
.axs-rescard:hover{border-color:var(--axs-acct);}
.axs-rescard .rt{font:600 13px/1.3 var(--axs-serif);color:var(--axs-strong);}
.axs-rescard .rm{font:400 11px/1.4 var(--axs-sans);color:var(--axs-mut);margin-top:3px;}
```

- [ ] **Step 2: Wire the search input**

In `static/acervo-studio.js`, inside `_build()`, after the `chat` button listener line, add:

```javascript
    var qi = root.querySelector('[data-axs="q"]');
    if (qi) qi.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') acervoStudioSearch(qi.value);
    });
```

Then, inside the IIFE, add the search function:

```javascript
  async function acervoStudioSearch(q) {
    q = (q || '').trim();
    var reader = _root().querySelector('[data-axs="reader"]');
    if (!q) { reader.innerHTML = '<div class="axs-reader-empty">Digite um termo.</div>'; return; }
    reader.innerHTML = '<div class="axs-reader-empty">Buscando…</div>';
    var d;
    try {
      d = await api('/api/acervo/x/search?session_id=' + encodeURIComponent(_sid()) +
        '&q=' + encodeURIComponent(q));
    } catch (e) { reader.innerHTML = '<div class="axs-reader-empty">Erro na busca.</div>'; return; }
    var res = (d && d.results) || [];
    if (!res.length) { reader.innerHTML = '<div class="axs-reader-empty">Nada encontrado.</div>'; return; }
    var html = '<div class="axs-results">';
    res.forEach(function (r) {
      html += '<button type="button" class="axs-rescard" data-path="' + _esc(r.rel_path) + '">' +
        '<div class="rt">' + _esc(r.title) + '</div>' +
        '<div class="rm">' + _esc(r.nature || '') + (r.status ? ' · ' + _esc(r.status) : '') +
        (r.snippet ? ' — ' + _esc(r.snippet) : '') + '</div></button>';
    });
    html += (d.truncated ? '<div class="axs-empty">Resultados truncados.</div>' : '') + '</div>';
    reader.innerHTML = html;
    reader.querySelectorAll('.axs-rescard').forEach(function (el) {
      el.addEventListener('click', function () { acervoStudioOpenPage(el.getAttribute('data-path')); });
    });
  }
  window.acervoStudioSearch = acervoStudioSearch;
```

- [ ] **Step 3: Lint + syntax-check**

Run: `node --check static/acervo-studio.js && npm run lint:runtime`
Expected: clean.

- [ ] **Step 4: Manual E2E — search**

In the Studio, type a known content term (e.g. `vendas`) in the top bar and press Enter → result cards render in the reader; click one → the page opens.
Expected: results appear; click opens the page; no console errors.

- [ ] **Step 5: Commit**

```bash
git add static/acervo-studio.js static/acervo-studio.css
git commit -m "feat(acervo-studio): command-bar search (MOD-010 Phase 0)"
```

---

### Task 7: Full-suite regression + governance docs

**Files:**
- Modify: `EXOCRTX_MODIFICATIONS.md` (append MOD-010 entry)
- Modify: `.harness/subprojects/hermes-webui/IDENTITY.md` (Studio line) — *in the umbrella repo*
- Create: `.harness/changes/2026-07-02_collab_hermes-webui-acervo-studio.md` — *in the umbrella repo*

**Interfaces:** none (docs + verification only).

- [ ] **Step 1: Run the full backend suite for regressions**

Run: `cd /home/elder/projetos/projetob/hermes-webui && python -m pytest -q 2>&1 | tail -5`
Expected: the documented baseline (≈9070 passed / 17 pre-existing fails) **+3** new passes from `test_mod010_acervo_studio.py`; **zero new failures**. If any *new* failure appears, stop and fix before continuing.

- [ ] **Step 2: Append the MOD-010 catalog entry**

In `EXOCRTX_MODIFICATIONS.md`, after the MOD-009 block, add a `### MOD-010: Acervo Studio (Phase 0 — read-only)` entry documenting: touch points (`api/acervo_explorer.py` tree extension; new `static/acervo-studio.{js,css}`; 3 `index.html` lines; **0** `routes.py` lines), the `.axs-*`/`acervoStudio*` namespaces, and the rebase-safety rationale (new files + prefix dispatch reuse).

- [ ] **Step 3: Write the COLLAB change record (umbrella repo)**

Create `/home/elder/projetos/projetob/.harness/changes/2026-07-02_collab_hermes-webui-acervo-studio.md` mirroring `2026-06-23_collab_hermes-webui-acervo-explorer.md`: why COLLAB (read-coupling in Phase 0, write-coupling arrives in Phase 2), the `/api/acervo/x/` surface additions (`tree` scopes `micro`/`inbox`), boundaries respected (read-only; `.quarantine`/create/delete out of reach), and additive-not-breaking classification.

- [ ] **Step 4: Update IDENTITY.md (umbrella repo)**

In `/home/elder/projetos/projetob/.harness/subprojects/hermes-webui/IDENTITY.md`, add an "Acervo Studio (MOD-010)" line under the customization-layers note, describing the read-only Phase 0 surface and pointing to `docs/rfcs/acervo-studio.md`.

- [ ] **Step 5: Commit (two repos)**

```bash
# hermes-webui
git -C /home/elder/projetos/projetob/hermes-webui add EXOCRTX_MODIFICATIONS.md
git -C /home/elder/projetos/projetob/hermes-webui commit -m "docs(acervo-studio): MOD-010 Phase 0 catalog entry"
# umbrella
git -C /home/elder/projetos/projetob add .harness/changes/2026-07-02_collab_hermes-webui-acervo-studio.md .harness/subprojects/hermes-webui/IDENTITY.md
git -C /home/elder/projetos/projetob commit -m "docs(harness): COLLAB record — acervo-studio MOD-010 Phase 0"
```

---

## Self-Review

**Spec coverage (Phase 0 slice of `docs/rfcs/acervo-studio.md`):**
- §4 unified IA (macro/global/shared/**micro**/artifacts/**inbox**) → Tasks 1–2 (backend scopes) + Task 4 (nav). ✓
- §5.1 shape (full-screen view, toggle, reader) → Tasks 3, 5. ✓
- §5.2 identity (Graphite dark + current-web-ui light, app-theme-following) → Task 3 CSS. ✓
- §6 backend (extend tree; 0 routes.py lines) → Tasks 1–2. ✓
- §8 coexistence (new files; ≤3 index.html lines; `.axs-*`) → Global Constraints + Task 3. ✓
- §11 Phase 0 (shell + navigate + reader, read-only, zero agent dependency) → all tasks. ✓
- §12 testing (pytest hermetic; E2E; no new failures) → Tasks 1–2 (pytest), 3–6 (E2E), 7 (regression). ✓
- Deferred to later plans (correctly out of Phase 0 scope): edit/download/bridge (Phase 1), intake/triage/promote (Phase 2), publish (Phase 3), assist (Phase 4).

**Placeholder scan:** none — every code step contains complete content; no "TBD"/"handle errors"/"similar to". ✓

**Type/name consistency:** `acervoStudioToggle`, `acervoStudioRenderNav`, `acervoStudioSelectScope`, `acervoStudioOpenPage`, `acervoStudioSearch`, state `AXS`, helpers `_micro_nodes`/`_inbox_nodes` — used identically across tasks; nav emits `data-path`/`data-mv`/`data-scope` consumed by the same tasks' listeners. Backend node shapes (`type: microverse|nature|page|intake|artifact`) match the nav renderer's branches. ✓
