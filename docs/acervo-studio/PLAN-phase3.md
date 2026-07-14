# Acervo Studio — Phase 3 (Publish Outbound) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the owner publish an artifact package (`_artifacts/items/<id>/`) to
Google Drive from the Studio — quality gate (`validate_artifact_manifest.py`,
antislop/taste) → Draft-First confirm → `artifact_publish.py publish` → SHA-256
receipt rendered in the UI — with calm degradation when the publish tools or the
Drive driver are absent from the runtime.

**Architecture:** Deterministic, server-side, **no cognition** — the mirror image of
promote: where promote had the agent craft content and the server write via
`acervoctl`, publish has NO content to craft, so the server shells straight to the
two real CLIs (list-form `subprocess.run`, no `shell=True`), exactly like
`acervo_studio_agent._acervoctl` does. New self-contained module
`api/acervo_studio_publish.py`; two new POST routes delegated from the existing
`handle_studio_post` (MOD-009 prefix dispatch → **0 new `api/routes.py` lines**).
Frontend extends the artifact card in the existing `.axs-*` IIFE.

**Tech Stack:** Python 3 stdlib (`subprocess`, `json`); pytest (hermetic: fake CLIs
written into the fixture acervo's `global/tools/` so the real subprocess plumbing is
exercised without touching `~/exocortex`); vanilla IIFE JS + `npm run lint:runtime`;
Playwright for the live fixture E2E.

## Global Constraints

- **GOVERNANCE / Draft-First:** private delivery to the owner's Drive is allowed;
  **public link/share is OWNER-GATED** — `artifact_publish.py` hardcodes
  `visibility: "private"` and has **no** `--public` flag, so `visibility: "public"`
  is refused calmly (never executed, never 500). The quality gate re-runs at publish
  time (a stale prepare cannot slip a failing artifact through).
- **SAFETY OF THE REAL ACERVO:** hermetic tests run against the `acervo` tmp fixture
  (with fake CLIs inside it); the live E2E runs against a THROWAWAY fixture acervo +
  fresh temp `HERMES_HOME` + explicit `ACERVO=<fixture>`. NEVER `~/exocortex/acervo`.
  Publish subprocesses get `ACERVO=<served root>` in their env.
- **REBASE-SAFETY:** new module `api/acervo_studio_publish.py`; routes delegate from
  `handle_studio_post` (`api/acervo_studio.py`, fork-owned). **0 new `routes.py` /
  `index.html` lines.** NEVER edit `style.css`/`ui.js`/`workspace.js`/`acervo.js`/
  `acervo-explorer.*`. Assert the shared-file diff is EMPTY at the end.
- **VANILLA ONLY:** IIFE, `'use strict'`, no ES `import`/`export`
  (`npm run lint:runtime`). Namespaces `.axs-*` / `acervoStudio*` / `AXS`. All
  dynamic content `_esc`'d before `innerHTML`; external links only when `https://`.
- **OPERATIONAL STATES = HTTP 200 + `{ok:false, …}` flags** (`drive_unconfigured`,
  `tools_missing`, `gate_failed`, `public_gated`, `error`) so the UI renders them
  calmly (`api()` throws on non-2xx). Malformed requests keep 400/404.
- **SUBPROCESS SAFETY:** list-form only; `artifact_id` validated (no `/`, `\`,
  leading `.`, ≤128 chars) **before** it becomes a path; resolved path re-checked
  against dot-prefixed components (`.quarantine` unreachable — same posture as
  `x/download`).
- **SESSION-GATED:** both endpoints require a valid `session_id`
  (`routes._resolve_session_workspace`), 400/404 on miss.
- Tests mirror `tests/test_mod010_acervo_studio.py` idioms: `acervo` fixture,
  `_Handler`, `session_ok`, `jcap`, monkeypatched module seams.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `api/acervo_studio_publish.py` | create | id/path safety, tools-dir resolution, validator + publish CLI runners, `prepare()`, `publish()` |
| `api/acervo_studio.py` | modify (append) | `handle_publish_prepare` / `handle_publish` routes + 2 dispatch lines in `handle_studio_post` |
| `static/acervo-studio.js` | modify | publish button on the artifact card; `.axs-pub` panel: gate → confirm → receipt |
| `static/acervo-studio.css` | modify (append) | `.axs-pub*` styles |
| `tests/test_mod010_acervo_studio.py` | modify (append) | Phase 3 sections (module + routes) |

---

### Task 1 — `api/acervo_studio_publish.py`: safety + tools resolution

**Files:**
- Create: `api/acervo_studio_publish.py`
- Test: `tests/test_mod010_acervo_studio.py` (append)

**Interfaces:**
- Produces: `_valid_artifact_id(art_id) -> bool`; `_artifact_dir(root, art_id) -> Path|None`;
  `_resolve_tools_dir(root) -> str|None`; exceptions `PublishError`, `DriveNotConfigured`.

- [ ] **Step 1: Write the failing tests** (append at end of `tests/test_mod010_acervo_studio.py`)

```python
# ── Phase 3 Task 1: publish module — safety + tools resolution ──────────────

import api.acervo_studio_publish as studio_pub


def _mk_artifact(acervo, art_id="art_20260712_relatorio", status="draft",
                 title="Relatório"):
    d = acervo / "_artifacts" / "items" / art_id
    (d / "source").mkdir(parents=True)
    (d / "exports").mkdir()
    (d / "source" / "source.md").write_text("# rel\n\nconteudo\n", encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({
        "artifact_id": art_id, "title": title, "status": status,
        "artifact_type": "document", "source_type": "markdown",
        "source_path": "source/source.md",
        "provenance": {"created_at": "2026-07-12T00:00:00Z"},
        "drive_target": {"provider": "google_drive",
                         "folder_path": "exocortex/inbox",
                         "visibility": "private"},
    }, ensure_ascii=False), encoding="utf-8")
    return d


@pytest.mark.parametrize("bad", ["", "../evil", "a/b", "a\\b", ".hidden", "x" * 129])
def test_pub_valid_artifact_id_rejects(bad):
    assert studio_pub._valid_artifact_id(bad) is False


def test_pub_valid_artifact_id_accepts():
    assert studio_pub._valid_artifact_id("art_20260712_relatorio") is True


def test_pub_artifact_dir_resolves(acervo):
    d = _mk_artifact(acervo)
    assert studio_pub._artifact_dir(acervo, "art_20260712_relatorio") == d


def test_pub_artifact_dir_missing_none(acervo):
    assert studio_pub._artifact_dir(acervo, "art_20990101_nope") is None


def test_pub_artifact_dir_blocks_symlink_into_quarantine(acervo):
    (acervo / ".quarantine" / "evil").mkdir(parents=True)
    (acervo / "_artifacts" / "items").mkdir(parents=True, exist_ok=True)
    (acervo / "_artifacts" / "items" / "linked").symlink_to(
        acervo / ".quarantine" / "evil", target_is_directory=True)
    assert studio_pub._artifact_dir(acervo, "linked") is None


def test_pub_resolve_tools_dir_prefers_root_copy(acervo, monkeypatch):
    tools = acervo / "global" / "tools"
    (tools / "harness").mkdir(parents=True)
    (tools / "artifact_publish.py").write_text("# stub\n", encoding="utf-8")
    (tools / "harness" / "validate_artifact_manifest.py").write_text(
        "# stub\n", encoding="utf-8")
    assert studio_pub._resolve_tools_dir(acervo) == str(tools)


def test_pub_resolve_tools_dir_none_when_absent(acervo, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "nohermes"))
    monkeypatch.setenv("EXOCORTEX_HOME", str(tmp_path / "noexo"))
    assert studio_pub._resolve_tools_dir(acervo) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k pub_ -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.acervo_studio_publish'`

- [ ] **Step 3: Create the module with the safety + resolution layer**

Create `api/acervo_studio_publish.py`:

```python
"""Acervo Studio publish (outbound) — MOD-010 Phase 3.

Wraps the two canonical acervo publish CLIs, deterministically (NO cognition):

  * ``global/tools/harness/validate_artifact_manifest.py`` — the quality gate
    (manifest schema + antislop/taste; draft artifacts get warnings, not errors).
  * ``global/tools/artifact_publish.py publish`` — deterministic Google Drive
    upload with SHA-256 receipts. Draft-First: the tool hardcodes
    ``visibility: "private"`` and has NO public/share flag.

The server shells out list-form (no shell=True), exactly like promote shells
out to acervoctl (api/acervo_studio_agent.py). Public sharing is an
OWNER-GATED approval step the tool does not support — requests for it are
refused calmly. When the Drive driver (google_api.py) is not provisioned the
tool exits with a clear message, mapped here to DriveNotConfigured so the
route can answer "Drive não configurado" (HTTP 200 operational state).
"""

import json
import logging
import os
import subprocess
import sys

logger = logging.getLogger("acervo_studio_publish")

_VALIDATOR_TIMEOUT = 60
_PUBLISH_TIMEOUT = 300          # a Drive upload can be slow
_ART_ID_MAX = 128
_DRIVE_MISSING_MARKER = "google_api.py"
_VISIBILITIES = ("private", "public")

_PUBLIC_GATE_MESSAGE = (
    "compartilhamento público é owner-gated (Draft-First) e o publicador só "
    "grava entregas privadas — publique privado ou peça ao owner")


class PublishError(Exception):
    """A deterministic publish step failed (tool missing/rejected/unparseable)."""


class DriveNotConfigured(Exception):
    """The publish tool could not find the google_api.py Drive driver."""


def _valid_artifact_id(art_id):
    s = str(art_id or "")
    if not s or len(s) > _ART_ID_MAX:
        return False
    if "/" in s or "\\" in s or s.startswith("."):
        return False
    return True


def _artifact_dir(root, art_id):
    """Resolve _artifacts/items/<id> under the served acervo root, refusing
    traversal / symlink escape into dot-prefixed areas (same posture as
    x/download). Returns a Path or None (unsafe id / missing / escapes)."""
    from api.acervo_explorer import _safe_acervo_path
    if not _valid_artifact_id(art_id):
        return None
    try:
        target = _safe_acervo_path("_artifacts/items/" + str(art_id))
    except ValueError:
        return None
    if not target.is_dir():
        return None
    try:
        parts = target.resolve().relative_to(root.resolve()).parts
    except (OSError, ValueError):
        return None
    if any(p.startswith(".") for p in parts):
        return None
    return target


def _resolve_tools_dir(root):
    """Locate a runnable publish-tools dir (artifact_publish.py +
    harness/validate_artifact_manifest.py). Preference: the served acervo's
    own global/tools, then the provisioned (~/.hermes) and live (~/exocortex)
    acervo copies — tool code is code, not data; it always operates on the
    EXPLICIT --artifact-dir under the served root."""
    home = os.path.expanduser("~")
    hermes_home = os.path.expanduser(
        os.environ.get("HERMES_HOME", "") or os.path.join(home, ".hermes"))
    exo_home = os.path.expanduser(
        os.environ.get("EXOCORTEX_HOME", "") or os.path.join(home, "exocortex"))
    candidates = [
        os.path.join(str(root), "global", "tools"),
        os.path.join(hermes_home, "acervo", "global", "tools"),
        os.path.join(exo_home, "acervo", "global", "tools"),
    ]
    for d in candidates:
        if os.path.isfile(os.path.join(d, "artifact_publish.py")) and \
           os.path.isfile(os.path.join(d, "harness",
                                       "validate_artifact_manifest.py")):
            return d
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k pub_ -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add api/acervo_studio_publish.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): publish module — artifact id/path safety + tools resolution (Phase 3 T1)"
```

---

### Task 2 — CLI runners: `_run_validator` + `_run_publish` (fake-CLI hermetic tests)

**Files:**
- Modify: `api/acervo_studio_publish.py` (append)
- Test: `tests/test_mod010_acervo_studio.py` (append)

**Interfaces:**
- Consumes: `_resolve_tools_dir` (Task 1).
- Produces: `_run_validator(tools_dir, root, artifact_dir) -> {ok, errors, warnings}`
  (raises `PublishError`); `_run_publish(tools_dir, root, artifact_dir) -> receipt dict`
  (raises `DriveNotConfigured` | `PublishError`).

- [ ] **Step 1: Write the failing tests.** The fake CLIs are REAL python scripts
  dropped into the fixture's `global/tools/`, so args/env/JSON plumbing is
  exercised hermetically. The fake publisher writes a `ran.flag` sentinel — later
  tasks assert publish is NOT executed when the gate fails.

```python
# ── Phase 3 Task 2: CLI runners against fake tools in the fixture ────────────

def _mk_tools(acervo, *, validator_json=None, publish_json=None, publish_rc=0,
              publish_stderr=""):
    """Fake artifact_publish.py + validate_artifact_manifest.py inside the
    fixture acervo. The publisher touches ran.flag so tests can assert
    whether it was executed."""
    tools = acervo / "global" / "tools"
    (tools / "harness").mkdir(parents=True, exist_ok=True)
    vj = validator_json if validator_json is not None else [
        {"artifact": "x", "ok": True, "errors": [], "warnings": []}]
    (tools / "harness" / "validate_artifact_manifest.py").write_text(
        "import json, sys\n"
        "print(json.dumps(%r))\n"
        "sys.exit(0 if %r else 1)\n" % (vj, bool(vj[0].get("ok"))),
        encoding="utf-8")
    pj = publish_json if publish_json is not None else {
        "status": "published", "folder_path": "exocortex/inbox",
        "folder_id": "f1", "folder_link": "https://drive.example/f1",
        "files": [{"name": "source.md", "drive_file_id": "d1",
                   "webViewLink": "https://drive.example/d1",
                   "sha256": "aa" * 32, "size": 12}]}
    (tools / "artifact_publish.py").write_text(
        "import json, os, sys\n"
        "open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ran.flag'), 'w').close()\n"
        "sys.stderr.write(%r)\n"
        "print(json.dumps(%r, ensure_ascii=False))\n"
        "sys.exit(%d)\n" % (publish_stderr, pj, publish_rc),
        encoding="utf-8")
    return tools


def test_pub_run_validator_parses_ok(acervo):
    d = _mk_artifact(acervo)
    tools = _mk_tools(acervo)
    gate = studio_pub._run_validator(str(tools), acervo, d)
    assert gate == {"ok": True, "errors": [], "warnings": []}


def test_pub_run_validator_reports_errors(acervo):
    d = _mk_artifact(acervo)
    tools = _mk_tools(acervo, validator_json=[
        {"artifact": "x", "ok": False,
         "errors": ["Missing required field: title"],
         "warnings": ["No owner.id — artifact is orphaned"]}])
    gate = studio_pub._run_validator(str(tools), acervo, d)
    assert gate["ok"] is False
    assert gate["errors"] == ["Missing required field: title"]
    assert gate["warnings"] == ["No owner.id — artifact is orphaned"]


def test_pub_run_validator_unparseable_raises(acervo):
    d = _mk_artifact(acervo)
    tools = acervo / "global" / "tools"
    (tools / "harness").mkdir(parents=True, exist_ok=True)
    (tools / "harness" / "validate_artifact_manifest.py").write_text(
        "print('not json')\n", encoding="utf-8")
    (tools / "artifact_publish.py").write_text("", encoding="utf-8")
    with pytest.raises(studio_pub.PublishError):
        studio_pub._run_validator(str(tools), acervo, d)


def test_pub_run_publish_parses_receipt(acervo):
    d = _mk_artifact(acervo)
    tools = _mk_tools(acervo)
    receipt = studio_pub._run_publish(str(tools), acervo, d)
    assert receipt["status"] == "published"
    assert receipt["files"][0]["sha256"] == "aa" * 32
    assert (tools / "ran.flag").is_file()


def test_pub_run_publish_drive_unconfigured(acervo):
    d = _mk_artifact(acervo)
    tools = _mk_tools(acervo, publish_rc=1, publish_stderr=
                      "google_api.py não encontrado. Verifique a skill "
                      "productivity/google-workspace no runtime Hermes.\n")
    with pytest.raises(studio_pub.DriveNotConfigured):
        studio_pub._run_publish(str(tools), acervo, d)


def test_pub_run_publish_other_failure_raises(acervo):
    d = _mk_artifact(acervo)
    tools = _mk_tools(acervo, publish_rc=1, publish_stderr="boom: quota\n",
                      publish_json={"status": "error"})
    with pytest.raises(studio_pub.PublishError):
        studio_pub._run_publish(str(tools), acervo, d)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k pub_run -q`
Expected: FAIL — `AttributeError: ... has no attribute '_run_validator'`

- [ ] **Step 3: Append the runners to `api/acervo_studio_publish.py`**

```python
def _run_tool(args, *, root, timeout, cwd):
    """One publish-CLI subprocess: list form, no shell, ACERVO pinned to the
    served root so the tool never falls back to a different acervo."""
    env = dict(os.environ)
    env["ACERVO"] = str(root)
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=timeout)


def _run_validator(tools_dir, root, artifact_dir):
    """Run validate_artifact_manifest.py --json on one artifact dir. Returns
    {ok, errors, warnings}. Exit code 1 just means "has errors" — still a
    valid gate result; raises PublishError only when the tool cannot run or
    prints unparseable output."""
    script = os.path.join(tools_dir, "harness", "validate_artifact_manifest.py")
    try:
        p = _run_tool([sys.executable or "python3", script,
                       str(artifact_dir), "--json"],
                      root=root, timeout=_VALIDATOR_TIMEOUT, cwd=tools_dir)
    except (subprocess.TimeoutExpired, OSError) as e:
        raise PublishError("validator failed: %s" % e)
    try:
        arr = json.loads((p.stdout or "").strip() or "[]")
    except ValueError:
        raise PublishError("validator output unparseable: %s"
                           % (p.stderr or p.stdout or "").strip()[:300])
    if not isinstance(arr, list) or not arr or not isinstance(arr[0], dict):
        raise PublishError("validator returned no result: %s"
                           % (p.stderr or "").strip()[:300])
    r = arr[0]
    return {"ok": bool(r.get("ok")),
            "errors": [str(x) for x in (r.get("errors") or [])],
            "warnings": [str(x) for x in (r.get("warnings") or [])]}


def _run_publish(tools_dir, root, artifact_dir):
    """artifact_publish.py publish --artifact-dir … → parsed receipt dict.
    Raises DriveNotConfigured when the Drive driver is missing (the tool's
    own failure receipt receipts/receipt.google_drive.failed.json still gets
    written by the tool), PublishError on any other failure."""
    script = os.path.join(tools_dir, "artifact_publish.py")
    try:
        p = _run_tool([sys.executable or "python3", script, "publish",
                       "--artifact-dir", str(artifact_dir)],
                      root=root, timeout=_PUBLISH_TIMEOUT, cwd=tools_dir)
    except (subprocess.TimeoutExpired, OSError) as e:
        raise PublishError("publish failed: %s" % e)
    blob = (p.stderr or "") + "\n" + (p.stdout or "")
    if p.returncode != 0:
        if _DRIVE_MISSING_MARKER in blob:
            raise DriveNotConfigured(blob.strip()[:300])
        raise PublishError("publish rejected: %s" % blob.strip()[:300])
    out = (p.stdout or "").strip()
    try:
        receipt = json.loads(out) if out else None
    except ValueError:
        receipt = None
    if not isinstance(receipt, dict) or receipt.get("status") != "published":
        raise PublishError("publish output unparseable: %s" % out[:300])
    return receipt
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k pub_ -q`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add api/acervo_studio_publish.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): validator + publish CLI runners, fake-CLI hermetic tests (Phase 3 T2)"
```

---

### Task 3 — `prepare()` + `publish()` (gate, Draft-First, public owner-gate)

**Files:**
- Modify: `api/acervo_studio_publish.py` (append)
- Test: `tests/test_mod010_acervo_studio.py` (append)

**Interfaces:**
- Consumes: Task 1 + Task 2 internals.
- Produces: `prepare(root, art_id) -> dict`; `publish(root, art_id, *, visibility="private",
  approve_public=False) -> dict`. Shapes: prepare ok →
  `{ok, artifact:{id,title,status,drive_target,exports_count}, gate:{ok,errors,warnings},
  can_publish, visibility_options:[{value,label,enabled,gate?}], drive_probe}`;
  publish ok → `{ok: True, receipt}`; failures →
  `{ok: False, tools_missing|gate_failed(+gate)|public_gated(+message)|drive_unconfigured|error}`.

- [ ] **Step 1: Write the failing tests**

```python
# ── Phase 3 Task 3: prepare + publish policies ───────────────────────────────

def test_pub_prepare_happy(acervo):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    out = studio_pub.prepare(acervo, "art_20260712_relatorio")
    assert out["ok"] is True
    assert out["artifact"]["id"] == "art_20260712_relatorio"
    assert out["artifact"]["title"] == "Relatório"
    assert out["artifact"]["status"] == "draft"
    assert out["artifact"]["drive_target"] == "exocortex/inbox"
    assert out["gate"]["ok"] is True and out["can_publish"] is True
    vis = {v["value"]: v for v in out["visibility_options"]}
    assert vis["private"]["enabled"] is True
    assert vis["public"]["enabled"] is False and vis["public"]["gate"]


def test_pub_prepare_tools_missing(acervo, tmp_path, monkeypatch):
    _mk_artifact(acervo)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "nohermes"))
    monkeypatch.setenv("EXOCORTEX_HOME", str(tmp_path / "noexo"))
    out = studio_pub.prepare(acervo, "art_20260712_relatorio")
    assert out == {"ok": False, "tools_missing": True}


def test_pub_prepare_artifact_missing(acervo):
    _mk_tools(acervo)
    out = studio_pub.prepare(acervo, "art_20990101_nope")
    assert out["ok"] is False and out["error"] == "artifact not found"


def test_pub_prepare_bad_manifest(acervo):
    d = _mk_artifact(acervo)
    _mk_tools(acervo)
    (d / "manifest.json").write_text("{not json", encoding="utf-8")
    out = studio_pub.prepare(acervo, "art_20260712_relatorio")
    assert out["ok"] is False and "manifest" in out["error"]


def test_pub_publish_happy(acervo):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    out = studio_pub.publish(acervo, "art_20260712_relatorio")
    assert out["ok"] is True
    assert out["receipt"]["status"] == "published"


def test_pub_publish_gate_failed_blocks_and_skips_upload(acervo):
    _mk_artifact(acervo, status="ready")
    tools = _mk_tools(acervo, validator_json=[
        {"artifact": "x", "ok": False,
         "errors": ["Anti-slop quality check failed (score: 20/50...)"],
         "warnings": []}])
    out = studio_pub.publish(acervo, "art_20260712_relatorio")
    assert out["ok"] is False and out["gate_failed"] is True
    assert out["gate"]["errors"]
    assert not (tools / "ran.flag").exists()   # publish CLI never executed


def test_pub_publish_public_requires_flag(acervo):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    out = studio_pub.publish(acervo, "art_20260712_relatorio",
                             visibility="public")
    assert out["ok"] is False and "approve_public" in out["error"]


def test_pub_publish_public_gated_even_with_flag(acervo):
    _mk_artifact(acervo)
    tools = _mk_tools(acervo)
    out = studio_pub.publish(acervo, "art_20260712_relatorio",
                             visibility="public", approve_public=True)
    assert out["ok"] is False and out["public_gated"] is True
    assert not (tools / "ran.flag").exists()   # nothing uploaded


def test_pub_publish_invalid_visibility(acervo):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    out = studio_pub.publish(acervo, "art_20260712_relatorio",
                             visibility="unlisted")
    assert out["ok"] is False and "visibility" in out["error"]


def test_pub_publish_drive_unconfigured(acervo):
    _mk_artifact(acervo)
    _mk_tools(acervo, publish_rc=1, publish_stderr=
              "google_api.py não encontrado.\n")
    out = studio_pub.publish(acervo, "art_20260712_relatorio")
    assert out["ok"] is False and out["drive_unconfigured"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k pub_p -q`
Expected: FAIL — `AttributeError: ... no attribute 'prepare'`

- [ ] **Step 3: Append `prepare`/`publish` (+ `_drive_probe`) to the module**

```python
def _drive_probe():
    """Best-effort hint: does a google_api.py Drive driver look discoverable
    in the runtime? The publish tool does its own authoritative discovery —
    this only powers the UI's early "Drive não configurado" hint."""
    home = os.path.expanduser(os.environ.get("HERMES_HOME", "") or "~/.hermes")
    for rel in (os.path.join("skills", "productivity", "google-workspace",
                             "scripts", "google_api.py"),
                os.path.join("hermes-agent", "skills", "productivity",
                             "google-workspace", "scripts", "google_api.py")):
        if os.path.isfile(os.path.join(home, rel)):
            return True
    return False


def prepare(root, art_id):
    """Assemble the publish gate for one artifact: manifest summary + quality
    gate + Drive target + visibility options. Read-only (the validator does
    not mutate). Never raises for operational problems."""
    target = _artifact_dir(root, art_id)
    if target is None:
        return {"ok": False, "error": "artifact not found"}
    try:
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest is not an object")
    except (OSError, ValueError):
        return {"ok": False, "error": "manifest.json missing or invalid"}
    tools_dir = _resolve_tools_dir(root)
    if tools_dir is None:
        return {"ok": False, "tools_missing": True}
    try:
        gate = _run_validator(tools_dir, root, target)
    except PublishError as e:
        return {"ok": False, "error": str(e)}
    exports = manifest.get("exports") or []
    return {
        "ok": True,
        "artifact": {
            "id": str(art_id),
            "title": str(manifest.get("title", "") or art_id),
            "status": str(manifest.get("status", "") or "draft"),
            "drive_target": str(((manifest.get("drive_target") or {})
                                 .get("folder_path")) or "exocortex/inbox"),
            "exports_count": len(exports) if isinstance(exports, list) else 0,
        },
        "gate": gate,
        "can_publish": bool(gate["ok"]),
        "visibility_options": [
            {"value": "private", "label": "Privado (Draft-First)",
             "enabled": True},
            {"value": "public", "label": "Compartilhar (link público)",
             "enabled": False, "gate": "requer aprovação explícita do owner"},
        ],
        "drive_probe": _drive_probe(),
    }


def publish(root, art_id, *, visibility="private", approve_public=False):
    """The CONFIRMED publish (the owner clicked Publicar). Draft-First: only
    private delivery is executable; visibility="public" is refused calmly
    (owner-gated, and the tool has no public support). The quality gate
    re-runs right before publishing so a stale prepare cannot slip a failing
    artifact through."""
    visibility = str(visibility or "private").strip().lower()
    if visibility not in _VISIBILITIES:
        return {"ok": False, "error": "invalid visibility"}
    if visibility == "public":
        if not approve_public:
            return {"ok": False, "error": "compartilhamento público requer "
                                          "aprovação explícita (approve_public)"}
        return {"ok": False, "public_gated": True,
                "message": _PUBLIC_GATE_MESSAGE}
    target = _artifact_dir(root, art_id)
    if target is None:
        return {"ok": False, "error": "artifact not found"}
    tools_dir = _resolve_tools_dir(root)
    if tools_dir is None:
        return {"ok": False, "tools_missing": True}
    try:
        gate = _run_validator(tools_dir, root, target)
    except PublishError as e:
        return {"ok": False, "error": str(e)}
    if not gate["ok"]:
        return {"ok": False, "gate_failed": True, "gate": gate}
    try:
        receipt = _run_publish(tools_dir, root, target)
    except DriveNotConfigured:
        return {"ok": False, "drive_unconfigured": True}
    except PublishError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "receipt": receipt}
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k pub_ -q`
Expected: 28 passed

- [ ] **Step 5: Commit**

```bash
git add api/acervo_studio_publish.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): publish prepare/confirm policies — quality gate, Draft-First, public owner-gate (Phase 3 T3)"
```

---

### Task 4 — Routes: `POST x/publish/prepare` + `POST x/publish`

**Files:**
- Modify: `api/acervo_studio.py` — append handlers after `handle_intake_promote`
  (before the `# region: dispatchers` comment, currently line 509) and add 2
  dispatch lines inside `handle_studio_post` (after the
  `/api/acervo/x/intake/item/promote` line, currently line 536).
- Test: `tests/test_mod010_acervo_studio.py` (append)

**Interfaces:**
- Consumes: `studio_pub.prepare` / `studio_pub.publish` / `_valid_artifact_id` /
  `_artifact_dir` (Task 3); `_intake_session` (existing).
- Produces: HTTP surface `POST /api/acervo/x/publish/prepare {session_id, artifact_id}`;
  `POST /api/acervo/x/publish {session_id, artifact_id, visibility?, approve_public?}`.

- [ ] **Step 1: Write the failing tests**

```python
# ── Phase 3 Task 4: publish routes ───────────────────────────────────────────

def test_publish_prepare_route_happy(acervo, session_ok, jcap):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    h = _Handler("/api/acervo/x/publish/prepare")
    studio.handle_studio_post(h, {"session_id": "sid1",
                                  "artifact_id": "art_20260712_relatorio"})
    assert jcap["status"] == 200 and jcap["obj"]["ok"] is True
    assert jcap["obj"]["gate"]["ok"] is True
    assert jcap["obj"]["artifact"]["drive_target"] == "exocortex/inbox"


def test_publish_prepare_route_bad_id_400(acervo, session_ok, jcap):
    h = _Handler("/api/acervo/x/publish/prepare")
    studio.handle_studio_post(h, {"session_id": "sid1", "artifact_id": "../evil"})
    assert jcap["status"] == 400


def test_publish_prepare_route_missing_404(acervo, session_ok, jcap):
    _mk_tools(acervo)
    h = _Handler("/api/acervo/x/publish/prepare")
    studio.handle_studio_post(h, {"session_id": "sid1",
                                  "artifact_id": "art_20990101_nope"})
    assert jcap["status"] == 404


def test_publish_prepare_route_tools_missing_calm(acervo, session_ok, jcap,
                                                  tmp_path, monkeypatch):
    _mk_artifact(acervo)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "nohermes"))
    monkeypatch.setenv("EXOCORTEX_HOME", str(tmp_path / "noexo"))
    h = _Handler("/api/acervo/x/publish/prepare")
    studio.handle_studio_post(h, {"session_id": "sid1",
                                  "artifact_id": "art_20260712_relatorio"})
    assert jcap["status"] == 200
    assert jcap["obj"]["ok"] is False and jcap["obj"]["tools_missing"] is True
    assert jcap["obj"]["message"]


def test_publish_prepare_route_requires_session(acervo, jcap, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: None)
    h = _Handler("/api/acervo/x/publish/prepare")
    studio.handle_studio_post(h, {"session_id": "ghost",
                                  "artifact_id": "art_20260712_relatorio"})
    assert jcap["status"] in (400, 404)


def test_publish_route_happy(acervo, session_ok, jcap):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    h = _Handler("/api/acervo/x/publish")
    studio.handle_studio_post(h, {"session_id": "sid1",
                                  "artifact_id": "art_20260712_relatorio"})
    assert jcap["status"] == 200 and jcap["obj"]["ok"] is True
    assert jcap["obj"]["receipt"]["status"] == "published"


def test_publish_route_drive_unconfigured_calm(acervo, session_ok, jcap):
    _mk_artifact(acervo)
    _mk_tools(acervo, publish_rc=1,
              publish_stderr="google_api.py não encontrado.\n")
    h = _Handler("/api/acervo/x/publish")
    studio.handle_studio_post(h, {"session_id": "sid1",
                                  "artifact_id": "art_20260712_relatorio"})
    assert jcap["status"] == 200
    assert jcap["obj"]["ok"] is False and jcap["obj"]["drive_unconfigured"] is True
    assert "Drive" in jcap["obj"]["message"]


def test_publish_route_gate_failed_payload(acervo, session_ok, jcap):
    _mk_artifact(acervo, status="ready")
    _mk_tools(acervo, validator_json=[
        {"artifact": "x", "ok": False, "errors": ["bad prose"], "warnings": []}])
    h = _Handler("/api/acervo/x/publish")
    studio.handle_studio_post(h, {"session_id": "sid1",
                                  "artifact_id": "art_20260712_relatorio"})
    assert jcap["status"] == 200
    assert jcap["obj"]["ok"] is False and jcap["obj"]["gate_failed"] is True
    assert jcap["obj"]["gate"]["errors"] == ["bad prose"]


def test_publish_route_public_gated(acervo, session_ok, jcap):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    h = _Handler("/api/acervo/x/publish")
    studio.handle_studio_post(h, {"session_id": "sid1",
                                  "artifact_id": "art_20260712_relatorio",
                                  "visibility": "public",
                                  "approve_public": True})
    assert jcap["status"] == 200
    assert jcap["obj"]["ok"] is False and jcap["obj"]["public_gated"] is True


def test_publish_route_requires_session(acervo, jcap, monkeypatch):
    monkeypatch.setattr(routes, "_resolve_session_workspace", lambda sid: None)
    h = _Handler("/api/acervo/x/publish")
    studio.handle_studio_post(h, {"session_id": "ghost",
                                  "artifact_id": "art_20260712_relatorio"})
    assert jcap["status"] in (400, 404)


def test_post_dispatcher_delegates_publish(acervo, session_ok, jcap):
    _mk_artifact(acervo)
    _mk_tools(acervo)
    h = _Handler("/api/acervo/x/publish/prepare")
    ax.handle_acervo_x_post(h, {"session_id": "sid1",
                                "artifact_id": "art_20260712_relatorio"})
    assert jcap["status"] == 200 and jcap["obj"]["ok"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -k publish_ -q`
Expected: FAIL — 404 "unknown acervo explorer endpoint" (route not wired)

- [ ] **Step 3: Append the handlers to `api/acervo_studio.py`** (immediately before
  the `# region: dispatchers` comment):

```python
# region: publish (Phase 3 — outbound; deterministic, no cognition)

def handle_publish_prepare(handler, body):
    """POST /api/acervo/x/publish/prepare {session_id, artifact_id} — quality
    gate + Drive target + visibility options for one artifact package.
    Read-only; the confirmed upload is handle_publish (propose-then-approve)."""
    import api.routes as routes
    import api.acervo_studio_publish as pub
    body = body or {}
    sid = _intake_session(handler, routes, body)
    if sid is None:
        return True
    art_id = str(body.get("artifact_id", "") or "").strip().strip("/")
    if not pub._valid_artifact_id(art_id):
        return routes.bad(handler, "invalid artifact id")
    root = routes._acervo_root()
    if pub._artifact_dir(root, art_id) is None:
        return routes.j(handler, {"error": "artifact not found"}, status=404)
    result = pub.prepare(root, art_id)
    if result.get("ok"):
        return routes.j(handler, result)
    # Operational states return 200 with an ok flag so the frontend renders
    # them calmly (api() throws only on non-2xx). Malformed already 400/404'd.
    if result.get("tools_missing"):
        return routes.j(handler, {"ok": False, "tools_missing": True,
                                  "message": "publicador não encontrado — "
                                             "ferramentas do acervo ausentes no runtime"})
    return routes.j(handler, {"ok": False,
                              "error": result.get("error", "prepare failed")})


def handle_publish(handler, body):
    """POST /api/acervo/x/publish {session_id, artifact_id, visibility?,
    approve_public?} — the CONFIRMED Drive publish (Draft-First: private
    delivery only; public share is owner-gated and refused calmly)."""
    import api.routes as routes
    import api.acervo_studio_publish as pub
    body = body or {}
    sid = _intake_session(handler, routes, body)
    if sid is None:
        return True
    art_id = str(body.get("artifact_id", "") or "").strip().strip("/")
    if not pub._valid_artifact_id(art_id):
        return routes.bad(handler, "invalid artifact id")
    root = routes._acervo_root()
    if pub._artifact_dir(root, art_id) is None:
        return routes.j(handler, {"error": "artifact not found"}, status=404)
    result = pub.publish(root, art_id,
                         visibility=str(body.get("visibility", "private")
                                        or "private"),
                         approve_public=bool(body.get("approve_public", False)))
    if result.get("ok"):
        return routes.j(handler, {"ok": True, "receipt": result.get("receipt")})
    if result.get("drive_unconfigured"):
        return routes.j(handler, {"ok": False, "drive_unconfigured": True,
                                  "message": "Drive não configurado — provisione "
                                             "as credenciais do Google Drive no runtime"})
    if result.get("tools_missing"):
        return routes.j(handler, {"ok": False, "tools_missing": True,
                                  "message": "publicador não encontrado — "
                                             "ferramentas do acervo ausentes no runtime"})
    if result.get("gate_failed"):
        return routes.j(handler, {"ok": False, "gate_failed": True,
                                  "gate": result.get("gate"),
                                  "message": "gate de qualidade reprovou — "
                                             "revise o artefato"})
    if result.get("public_gated"):
        return routes.j(handler, {"ok": False, "public_gated": True,
                                  "message": result.get("message")})
    return routes.j(handler, {"ok": False,
                              "error": result.get("error", "publish failed")})
```

And add the 2 dispatch lines in `handle_studio_post`, after the promote line:

```python
    if path == "/api/acervo/x/publish/prepare":
        return handle_publish_prepare(handler, body)
    if path == "/api/acervo/x/publish":
        return handle_publish(handler, body)
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -q`
Expected: all pass (76 pre-existing + ~39 new)

- [ ] **Step 5: Commit**

```bash
git add api/acervo_studio.py tests/test_mod010_acervo_studio.py
git commit -m "feat(acervo-studio): publish routes — x/publish/prepare + x/publish (Phase 3 T4)"
```

---

### Task 5 — Frontend: publish panel on the artifact card (`.axs-pub*`)

**Files:**
- Modify: `static/acervo-studio.js` — extend `_openArtifact` (line ~335) and
  `_wireActs` (line ~271); add a Phase-3 section after `acervoStudioPromote`
  (after line ~807, before the `// ── Phase 2a: intake capture` comment).
- Modify: `static/acervo-studio.css` — append `.axs-pub*` styles.

**Interfaces:**
- Consumes: `POST /api/acervo/x/publish/prepare` and `POST /api/acervo/x/publish`
  (Task 4 shapes); existing `api()`, `_esc`, `_sid`, `_toast`, `_detail`, `AXS`.
- Produces: globals `acervoStudioPublishPrepare()`, `acervoStudioPublishConfirm()`.

- [ ] **Step 1: Extend `_openArtifact`** — replace its `reader.innerHTML` block with:

```js
    reader.innerHTML =
      '<div class="axs-crumb"><b>_artifacts</b> › ' + _esc(id) +
      '  <div class="axs-acts"><button type="button" class="axs-act" data-axs-act="download">⬇ Baixar (zip)</button>' +
      '<button type="button" class="axs-act axs-act-primary" data-axs-act="publish">⇪ Publicar no Drive</button></div></div>' +
      '<div class="axs-doc">' +
      '  <h1 class="axs-title">📦 ' + _esc(title || id) + '</h1>' +
      '  <div class="axs-empty">Pacote de artefato — o download inclui manifest.json, source/ e exports/.</div>' +
      '  <div class="axs-pub" data-axs-pub></div>' +
      '</div>';
    _wireActs(reader);
```

- [ ] **Step 2: Wire the action in `_wireActs`** — add one branch before the
  `more` branch:

```js
        else if (act === 'publish') { if (typeof acervoStudioPublishPrepare === 'function') acervoStudioPublishPrepare(); }
```

- [ ] **Step 3: Add the Phase-3 section** (new code, after
  `window.acervoStudioPromote = acervoStudioPromote;`):

```js
  // ── Phase 3: publish (outbound) — gate → confirm → receipt ───────────────
  function _pubBox() {
    var root = _root();
    return root && root.querySelector('[data-axs-pub]');
  }

  function _safeHttp(u) {
    u = String(u || '');
    return /^https:\/\//i.test(u) ? u : '';
  }

  async function acervoStudioPublishPrepare() {
    var box = _pubBox();
    if (!box || !AXS.artifactId) return;
    box.innerHTML = '<div class="axs-env-note">Verificando o gate de qualidade…</div>';
    var r;
    try {
      r = await api('/api/acervo/x/publish/prepare', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), artifact_id: AXS.artifactId })
      });
    } catch (e) {
      box.innerHTML = '<div class="axs-env-note">' + _esc('Falha ao preparar publicação' + _detail(e)) + '</div>';
      return;
    }
    if (!r || !r.ok) {
      var msg = (r && (r.message || r.error)) || 'Não foi possível preparar a publicação.';
      box.innerHTML = '<div class="axs-env-note">' + _esc(msg) + '</div>';
      return;
    }
    _renderPublishGate(box, r);
  }
  window.acervoStudioPublishPrepare = acervoStudioPublishPrepare;

  function _renderPublishGate(box, r) {
    var gate = r.gate || { ok: false, errors: [], warnings: [] };
    var art = r.artifact || {};
    var items = '';
    (gate.errors || []).forEach(function (x) { items += '<li class="axs-pub-err">' + _esc(x) + '</li>'; });
    (gate.warnings || []).forEach(function (x) { items += '<li class="axs-pub-warn">' + _esc(x) + '</li>'; });
    var vis = (r.visibility_options || []).map(function (v) {
      return '<label class="axs-pub-vis' + (v.enabled ? '' : ' axs-pub-vis-off') + '"' +
        (v.enabled ? '' : ' title="' + _esc(v.gate || 'indisponível') + '"') + '>' +
        '<input type="radio" name="axsPubVis" value="' + _esc(v.value) + '"' +
        (v.value === 'private' ? ' checked' : '') + (v.enabled ? '' : ' disabled') + '> ' +
        _esc(v.label) + '</label>';
    }).join('');
    box.innerHTML =
      '<div class="axs-pub-card">' +
      '  <div class="axs-prop-head">Publicar no Drive — ' + _esc(art.title || art.id || '') +
      '  <span class="axs-pub-status">' + _esc(art.status || '') + '</span></div>' +
      '  <div class="axs-pub-target">Destino: <code>' + _esc(art.drive_target || '') + '</code>' +
      (r.drive_probe === false ? ' <span class="axs-pub-hint">· Drive não configurado neste runtime</span>' : '') +
      '  </div>' +
      '  <div class="axs-pub-gate ' + (gate.ok ? 'axs-pub-gate-ok' : 'axs-pub-gate-bad') + '">' +
      (gate.ok ? '✓ Gate de qualidade aprovado' : '✗ Gate de qualidade reprovou — revise o artefato') +
      (items ? '<ul class="axs-pub-issues">' + items + '</ul>' : '') + '</div>' +
      '  <div class="axs-pub-visrow">' + vis + '</div>' +
      '  <div class="axs-acts">' +
      '    <button type="button" class="axs-act axs-act-primary" data-pub-go' + (gate.ok ? '' : ' disabled') + '>⇪ Publicar</button>' +
      '  </div>' +
      '  <div class="axs-env-note" data-pub-note>Draft-First: a entrega é privada no seu Drive; compartilhar publicamente exige aprovação do owner.</div>' +
      '</div>';
    var go = box.querySelector('[data-pub-go]');
    if (go) go.addEventListener('click', function () { acervoStudioPublishConfirm(); });
  }

  function _renderPublishReceipt(box, receipt) {
    var flink = _safeHttp(receipt.folder_link);
    var files = (receipt.files || []).map(function (f) {
      var wl = _safeHttp(f.webViewLink);
      return '<li><code>' + _esc(f.name || '') + '</code>' +
        (f.sha256 ? ' <span class="axs-pub-sha">sha256:' + _esc(String(f.sha256).slice(0, 12)) + '…</span>' : '') +
        (wl ? ' — <a href="' + _esc(wl) + '" target="_blank" rel="noopener">abrir</a>' : '') +
        '</li>';
    }).join('');
    box.innerHTML =
      '<div class="axs-pub-card axs-pub-done">' +
      '  <div class="axs-prop-head">✓ Publicado no Drive</div>' +
      '  <div class="axs-pub-target">Pasta: <code>' + _esc(receipt.folder_path || '') + '</code>' +
      (flink ? ' — <a href="' + _esc(flink) + '" target="_blank" rel="noopener">abrir no Drive</a>' : '') + '</div>' +
      (files ? '<ul class="axs-pub-files">' + files + '</ul>' : '') +
      '  <div class="axs-env-note">Entrega privada (Draft-First) — recibo SHA-256 gravado em receipts/.</div>' +
      '</div>';
  }

  async function acervoStudioPublishConfirm() {
    var box = _pubBox();
    if (!box || !AXS.artifactId) return;
    var btn = box.querySelector('[data-pub-go]');
    if (btn) btn.disabled = true;
    var note = box.querySelector('[data-pub-note]');
    if (note) note.textContent = 'Publicando no Drive…';
    var r;
    try {
      r = await api('/api/acervo/x/publish', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), artifact_id: AXS.artifactId, visibility: 'private' }),
        timeoutMs: 300000  // a Drive upload can take a while
      });
    } catch (e) {
      if (btn) btn.disabled = false;
      if (note) note.textContent = 'Falha ao publicar' + _detail(e);
      return;
    }
    if (r && r.ok && r.receipt) {
      _renderPublishReceipt(box, r.receipt);
      _toast('Publicado no Drive', 'success');
      return;
    }
    if (btn) btn.disabled = false;
    var msg = (r && (r.message || r.error)) || 'Não foi possível publicar.';
    if (note) note.textContent = msg;
    _toast(msg, 'error');
  }
  window.acervoStudioPublishConfirm = acervoStudioPublishConfirm;
```

- [ ] **Step 4: Append the CSS** (end of `static/acervo-studio.css`):

```css
/* Phase 3: publish (outbound) */
.axs-pub:empty { display: none; }
.axs-pub-card { margin-top: 14px; padding: 12px; border: 1px solid var(--axs-bd, #3a3a3a); border-radius: 8px; }
.axs-pub-status { font: 600 10px/1 var(--axs-mono); color: var(--axs-mut); margin-left: 6px; text-transform: uppercase; }
.axs-pub-target { font-size: 12.5px; margin: 6px 0; }
.axs-pub-target code { font-family: var(--axs-mono); }
.axs-pub-hint { color: var(--axs-mut); font-size: 11.5px; }
.axs-pub-gate { margin: 8px 0; padding: 8px 10px; border-radius: 6px; font: 600 12px/1.4 var(--axs-sans); }
.axs-pub-gate-ok { background: rgba(126,201,140,.12); color: var(--axs-ok, #7EC98C); }
.axs-pub-gate-bad { background: rgba(220,120,120,.12); color: #d08080; }
.axs-pub-issues { margin: 6px 0 0; padding-left: 18px; font-weight: 400; }
.axs-pub-err { color: #d08080; }
.axs-pub-warn { color: var(--axs-mut); }
.axs-pub-visrow { display: flex; gap: 14px; margin: 8px 0; font-size: 12.5px; }
.axs-pub-vis-off { opacity: .55; cursor: not-allowed; }
.axs-pub-files { margin: 8px 0 0; padding-left: 18px; font-size: 12.5px; }
.axs-pub-sha { font: 400 10.5px/1 var(--axs-mono); color: var(--axs-mut); }
.axs-pub-done { border-color: var(--axs-accbd); }
```

- [ ] **Step 5: Verify syntax + lint**

Run: `node --check static/acervo-studio.js && npm run lint:runtime`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add static/acervo-studio.js static/acervo-studio.css
git commit -m "feat(acervo-studio): publish panel — gate, Draft-First confirm, Drive receipt (Phase 3 T5)"
```

---

### Task 6 — Verification: live fixture E2E + regression + rebase-safety

**Files:** none (verification only; report to the ledger).

- [ ] **Step 1: Focused + full suite**

Run: `python3 -m pytest tests/test_mod010_acervo_studio.py -q` → all green.
Run: `python3 -m pytest -x -q -p no:cacheprovider 2>&1 | tail -5` → no NEW failures
vs the ~16 pre-existing env-sensitive set (locales/skins/sessiondb-fd/openrouter).

- [ ] **Step 2: Live fixture E2E (Playwright)** — throwaway fixture acervo with a
  seeded draft artifact + a COPY of the REAL validator (so the real antislop gate
  runs live) + fresh temp `HERMES_HOME`, explicit `ACERVO=<fixture>`, spare port:
  - open Studio → Artefatos → click the artifact → card shows «⇪ Publicar no Drive»
  - prepare renders the REAL validator's gate result
  - confirm publish → with no Drive driver in the temp home → calm
    «Drive não configurado» (the live-exercised degradation path)
  - gate-failed artifact (seeded slop, status=ready) → publish blocked, issues listed
  - verify no write escaped the fixture; kill server; remove fixture.

- [ ] **Step 3: Rebase-safety assertion**

Run: `git diff exocortex/stable --stat -- api/routes.py static/index.html static/style.css static/ui.js static/workspace.js static/acervo.js static/acervo-explorer.js static/acervo-explorer.css`
Expected: EMPTY output.

- [ ] **Step 4: Record results in the ledger** (`.superpowers/sdd/progress.md`).

---

### Task 7 — Governance: catalog + COLLAB record + IDENTITY

**Files:**
- Modify: `EXOCRTX_MODIFICATIONS.md` — MOD-010 gets a "Fase 3" bullet (publish
  outbound: routes, module, Draft-First, public owner-gate, degradation paths,
  0 routes.py/index.html lines).
- Create (umbrella repo): `.harness/changes/2026-07-12_collab_hermes-webui-acervo-studio-phase3.md`
- Modify (umbrella repo): `.harness/subprojects/hermes-webui/IDENTITY.md` — MOD-010 note
  gains Phase 3.

- [ ] **Step 1: Write + commit the catalog entry (hermes-webui branch)**
- [ ] **Step 2: Write + commit the COLLAB record + IDENTITY note (umbrella repo, its own commit)**

---

## Self-review notes

- Spec coverage: RFC §6.1 Publish (prepare + confirm) ✔; §5.4 flow ✔ (gate,
  Draft-First, receipt, «Revisar» on failure); §9 degradation ✔ (tools missing,
  Drive unconfigured, gate failed — all HTTP 200 calm states); brief's Phase-3
  scope ✔ (validator = antislop/taste gate; publish tool private-hardcoded;
  public = added approval step, refused as owner-gated).
- No placeholders; every step carries complete code.
- Type consistency: `prepare`/`publish` shapes match the route mappings and the
  frontend readers (`gate.errors/warnings`, `receipt.files[].sha256/webViewLink`,
  `visibility_options[].enabled/gate`).
- YAGNI: no artifact CREATION (init) in the Studio; no Drive move; no public
  share implementation — refusal only, per the owner gate.
