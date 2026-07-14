"""Acervo Studio agent mediation — MOD-010 Phase 2b.

USER -> GUI -> SERVER -> HERMES. The GUI never calls cognition or writes semantic
memory directly; this module runs the in-process Hermes agent (sync, per the
resolved invocation spike docs/acervo-studio/SPIKE-hermes-invocation.md) and
returns a *structured proposal*. Two operations:

  * propose_triage()  — READ-ONLY. A tool-less run_conversation asks Hermes where
    a captured _inbox envelope should be promoted to; returns a parsed proposal.
  * promote()         — the sanctioned semantic WRITE (Task 3), agent-mediated via
    excrtx-memory-manager; propose-then-approve (the caller passes the approved
    routing). Built per the Task-0 spike.

Everything is self-contained in this fork-owned module (rebase-safe): the agent is
invoked through the stable `run_agent.AIAgent` + `api.config`/`api.profiles` API,
not by editing any upstream file. Degrades gracefully when Hermes is unavailable
(raises AgentUnavailable, which the routes translate to a calm "agente offline").
"""

import datetime
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import uuid

logger = logging.getLogger("acervo_studio_agent")

# Bound how much of an envelope's original content we feed the model for triage.
_TRIAGE_CONTENT_CHARS = 6000
_VALID_SCOPES = ("macro", "global", "shared", "micro")


class AgentUnavailable(Exception):
    """Hermes runtime not importable/usable — callers surface a calm offline state."""


def _resolve_main_runtime(session=None):
    """Resolve {provider, model, base_url, api_key} for the active profile/session,
    mirroring api.routes._llm_git_commit_message so cognition uses the same model
    the user configured. Kept here (not imported) to stay rebase-safe."""
    from api.config import (
        get_effective_default_model,
        model_with_provider_context,
        resolve_custom_provider_connection,
        resolve_model_provider,
    )

    session_model = str(getattr(session, "model", "") or "").strip()
    session_provider = str(getattr(session, "model_provider", "") or "").strip() or None
    model_for_resolution = (
        model_with_provider_context(session_model, session_provider)
        if session_model
        else get_effective_default_model()
    )
    model, provider, base_url = resolve_model_provider(model_for_resolution)
    api_key = None
    try:
        from api.oauth import resolve_runtime_provider_with_anthropic_env_lock
        from hermes_cli.runtime_provider import resolve_runtime_provider

        rt = resolve_runtime_provider_with_anthropic_env_lock(
            resolve_runtime_provider, requested=provider)
        api_key = rt.get("api_key")
        if not provider:
            provider = rt.get("provider")
        if not base_url:
            base_url = rt.get("base_url")
    except Exception as e:  # resolution is best-effort; agent ctor still gets what we have
        logger.debug("acervo studio runtime provider resolution failed: %s", e)
    if isinstance(provider, str) and provider.startswith("custom:"):
        cp_key, cp_base = resolve_custom_provider_connection(provider)
        if not api_key and cp_key:
            api_key = cp_key
        if not base_url and cp_base:
            base_url = cp_base
    return {"provider": provider, "model": model, "base_url": base_url, "api_key": api_key}


def _run_agent_text(system_prompt, user_prompt, *, session=None, enabled_toolsets=()):
    """Run one blocking in-process agent turn, return final_response text.
    enabled_toolsets=() => tool-less (triage/assist). A non-empty toolset lets the
    turn execute tools (promote). Raises AgentUnavailable for ANY runtime problem
    (missing agent, provider/profile resolution failure, turn error) so callers can
    surface a calm offline state instead of a 500."""
    try:
        from api import profiles as profiles_api

        active_profile = profiles_api.get_active_profile_name() or "default"
        with profiles_api.profile_env_for_background_worker(
                active_profile, "acervo studio agent", logger_override=logger):
            rt = _resolve_main_runtime(session)
            from run_agent import AIAgent
            if AIAgent is None:
                raise AgentUnavailable("AIAgent unavailable")
            sid = "acervo-studio-%s" % uuid.uuid4().hex[:8]
            agent = AIAgent(
                model=rt["model"], provider=rt["provider"], base_url=rt["base_url"],
                api_key=rt["api_key"], platform="webui", quiet_mode=True,
                enabled_toolsets=list(enabled_toolsets), session_id=sid)
            result = agent.run_conversation(
                user_message=user_prompt, system_message=system_prompt,
                conversation_history=[], task_id=sid)
            return str((result or {}).get("final_response") or "").strip()
    except AgentUnavailable:
        raise
    except Exception as e:
        raise AgentUnavailable(str(e))


def _extract_json(text):
    """Pull the first JSON object out of an LLM response (handles ```json fences
    and surrounding prose). Returns a dict or None."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else None
    if raw is None:
        start = text.find("{")
        end = text.rfind("}")
        raw = text[start:end + 1] if (start >= 0 and end > start) else None
    if raw is None:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except ValueError:
        return None


def _slug_ok(s):
    return bool(re.match(r"^[a-z0-9][a-z0-9-]*$", str(s or "")))


def _normalize_proposal(obj):
    """Validate + clamp a raw triage proposal into a safe, known shape.
    Returns None if unusable."""
    if not isinstance(obj, dict):
        return None
    scope = str(obj.get("scope", "") or "").strip().lower()
    if scope not in _VALID_SCOPES:
        return None
    slug = str(obj.get("slug", "") or "").strip().lower()
    nature = str(obj.get("nature", "") or "").strip().lower()
    title = str(obj.get("title", "") or "").strip()[:200]
    rationale = str(obj.get("rationale", "") or "").strip()[:500]
    keep = bool(obj.get("keep_in_inbox", False))
    # micro needs a valid slug; nature (when present) must be a plain word.
    if scope == "micro" and not _slug_ok(slug):
        return None
    if nature and not _slug_ok(nature):
        nature = ""
    return {"scope": scope, "slug": slug if scope == "micro" else "",
            "nature": nature, "title": title, "rationale": rationale,
            "keep_in_inbox": keep}


_TRIAGE_SYSTEM = (
    "You are the Exocortex acervo triage assistant. Given a captured inbox item, "
    "decide where it should live in the semantic acervo. Reply with ONE JSON object "
    "and nothing else, with keys: scope (one of macro|global|shared|micro), slug "
    "(microverse slug, lowercase-kebab, only when scope=micro), nature (e.g. "
    "knowledge|context|decisions|contracts|workflows|reflections), title (a concise "
    "human title), rationale (one short sentence), keep_in_inbox (true if it is raw "
    "material that should NOT become a semantic page yet). Do not invent facts."
)


def propose_triage(root, iid, *, session=None):
    """Read the envelope + its captured content and ask Hermes for a routing
    proposal. Returns {ok: True, proposal: {...}} | {ok: False, offline: True}
    | {ok: False, error: "..."}. Never writes semantic memory (read-only)."""
    import api.acervo_studio as studio

    env = studio._read_envelope(root, iid)
    if env is None:
        return {"ok": False, "error": "envelope not found"}
    content = ""
    files = env.get("files") or []
    if files:
        try:
            fp = studio._safe_acervo_path(
                "_inbox/incoming/" + iid + "/" + files[0])
            if fp.is_file():
                content = fp.read_text(encoding="utf-8", errors="replace")[:_TRIAGE_CONTENT_CHARS]
        except (ValueError, OSError):
            content = ""
    user_prompt = (
        "Inbox item to triage.\n"
        "content_type: %s\ncaption: %s\noriginal_filename: %s\n\n---\n%s\n---\n"
        % (env.get("content_type", ""), env.get("user_caption", ""),
           env.get("original_filename", ""), content))
    try:
        text = _run_agent_text(_TRIAGE_SYSTEM, user_prompt, session=session)
    except AgentUnavailable:
        return {"ok": False, "offline": True}
    proposal = _normalize_proposal(_extract_json(text))
    if proposal is None:
        return {"ok": False, "error": "could not parse a valid proposal"}
    return {"ok": True, "proposal": proposal}


# ── Promote: agent crafts the page body (cognition), server writes it via the
#    acervoctl control plane (deterministic; the scope guard runs inside
#    commit-write). Per the Task-0 spike. Micro-scope only. ────────────────────

_ACERVOCTL_TIMEOUT = 60


class PromoteError(Exception):
    """A deterministic promote step failed (control plane missing / write rejected)."""


_PROMOTE_SYSTEM = (
    "You are the Exocortex acervo scribe. Turn the raw inbox item into a clean, "
    "self-contained semantic page body in Markdown (NO YAML frontmatter — that is "
    "added separately). Preserve facts; structure and summarize, never invent. Reply "
    "with ONE JSON object and nothing else: body_markdown (the page content), class "
    "(\"perene\" for durable truth, \"volátil\" for transient state), description (one "
    "short sentence), tags (a short list of lowercase keyword strings)."
)


def _envelope_content(root, iid, env):
    import api.acervo_studio as studio
    files = env.get("files") or []
    if not files:
        return ""
    try:
        fp = studio._safe_acervo_path("_inbox/incoming/" + iid + "/" + files[0])
        if fp.is_file():
            return fp.read_text(encoding="utf-8", errors="replace")[:_TRIAGE_CONTENT_CHARS]
    except (ValueError, OSError):
        pass
    return ""


def _resolve_acervoctl_dir():
    """Locate a runnable acervoctl control-plane dir (has acervoctl.py +
    acervo_semantic_core.py). Not provisioned in ~/.hermes — the installer cache is
    the canonical runnable copy. Returns a str path or None."""
    candidates = []
    env_dir = os.environ.get("EXOCORTEX_SCRIPTS_DIR")
    if env_dir:
        candidates.append(env_dir)
    home = os.path.expanduser("~")
    candidates += [
        os.path.join(home, ".exocortex-installer", "scripts"),
        os.path.join(home, "exocortex", "scripts"),
    ]
    for d in candidates:
        if d and os.path.isfile(os.path.join(d, "acervoctl.py")) \
           and os.path.isfile(os.path.join(d, "acervo_semantic_core.py")):
            return d
    return None


def _scaffold_microverso(root, slug):
    """Ensure micro/{slug}/_meta/{index,log}.md exist (acervoctl prepare-write
    requires them). Idempotent; creates a new microverso skeleton when absent."""
    meta = root / "micro" / slug / "_meta"
    meta.mkdir(parents=True, exist_ok=True)
    idx = meta / "index.md"
    if not idx.is_file():
        idx.write_text("# Index — %s\n" % slug, encoding="utf-8")
    log = meta / "log.md"
    if not log.is_file():
        log.write_text("# Log — %s\n" % slug, encoding="utf-8")


# nature dir -> OKF/v0.2 `type` (validator V2-020 requires dir↔type consistency).
_NATURE_TO_TYPE = {
    "knowledge": "knowledge", "context": "context", "decisions": "decision",
    "workflows": "workflow", "contracts": "contract", "reflections": "reflection",
    "persona": "persona", "prompts": "prompt", "templates": "template",
    "tools": "tool", "skills": "skill",
}


def _build_okf_page(nature, title, description, tags, class_name, body, now=None):
    """Compose a schema-v0.2 page (frontmatter + body) that acervoctl commit-write
    will accept (it validates but does NOT synthesize frontmatter). Format mirrors
    acervo_semantic_core.new_object's proven fm_lines."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    type_ = _NATURE_TO_TYPE.get(nature, "knowledge")
    tag_list = ", ".join(json.dumps(str(t), ensure_ascii=False) for t in (tags or []))
    fm = "\n".join([
        "---",
        "schema: acervo/v0.2",
        "type: %s" % type_,
        "title: %s" % json.dumps(str(title or ""), ensure_ascii=False),
        "description: %s" % json.dumps(str(description or title or ""), ensure_ascii=False),
        "tags: [%s]" % tag_list,
        "created_at: %s" % now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "class: %s" % ("perene" if class_name == "perene" else "volátil"),
        "status: draft",
        "epistemic: fact",
        "confidence: high",
        'sources: [{type: agent-inference, ref: "acervoctl://acervo-studio-promote"}]',
        "observed_at: %s" % now.strftime("%Y-%m-%d"),
        "extraction: agent",
        "---",
    ])
    return fm + "\n\n" + (body or "").strip() + "\n"


def _acervoctl(scripts_dir, root, args):
    """Run one acervoctl subcommand (list form, no shell). Returns CompletedProcess."""
    env = dict(os.environ)
    env["PYTHONPATH"] = scripts_dir + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable or "python3", os.path.join(scripts_dir, "acervoctl.py")] + args,
        cwd=scripts_dir, env=env, capture_output=True, text=True,
        timeout=_ACERVOCTL_TIMEOUT)


def _commit_via_acervoctl(root, slug, nature, title, body_md, class_name,
                          description, tags=None):
    """prepare-write -> commit-write against `root` (the fixture/real acervo). MY
    code builds the schema-v0.2 page (commit-write validates but won't synthesize
    frontmatter); the scope guard runs inside commit-write. Returns the parsed
    receipt dict. Raises PromoteError on any failure."""
    scripts_dir = _resolve_acervoctl_dir()
    if scripts_dir is None:
        raise PromoteError("acervo control plane not found")
    root_s = str(root)
    page = _build_okf_page(nature, title, description, tags, class_name, body_md)
    with tempfile.TemporaryDirectory() as tmp:
        receipt_path = os.path.join(tmp, "r.json")
        body_path = os.path.join(tmp, "body.md")
        with open(body_path, "w", encoding="utf-8") as fh:
            fh.write(page)
        try:
            p1 = _acervoctl(scripts_dir, root, [
                "prepare-write", "--acervo-root", root_s, "--microverso", slug,
                "--nature", nature, "--title", title, "--receipt-out", receipt_path])
        except (subprocess.TimeoutExpired, OSError) as e:
            raise PromoteError("prepare-write failed: %s" % e)
        if p1.returncode != 0 or not os.path.isfile(receipt_path):
            raise PromoteError("prepare-write rejected: %s" % (p1.stderr or p1.stdout or "").strip()[:300])
        try:
            p2 = _acervoctl(scripts_dir, root, [
                "commit-write", "--receipt", receipt_path, "--content-file", body_path,
                "--description", description, "--class-name", class_name])
        except (subprocess.TimeoutExpired, OSError) as e:
            raise PromoteError("commit-write failed: %s" % e)
        out = (p2.stdout or "").strip()
        receipt = None
        try:
            receipt = json.loads(out) if out else None
        except ValueError:
            receipt = _extract_json(out)
        if p2.returncode != 0 or not isinstance(receipt, dict) or receipt.get("status") != "committed":
            raise PromoteError("write rejected: %s"
                               % (p2.stderr or out or "").strip()[:300])
        return receipt


def _move_to_promoted(root, iid):
    src = root / "_inbox" / "incoming" / iid
    dst_dir = root / "_inbox" / "promoted"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / iid
    if src.is_dir() and not dst.exists():
        shutil.move(str(src), str(dst))


def promote(root, iid, routing, *, session=None):
    """Agent-mediated semantic write. `routing` = the OWNER-APPROVED
    {scope, slug, nature, title}. The agent crafts the page body (cognition); the
    server writes it deterministically via acervoctl (scope guard enforced there).
    Micro-scope only. Returns {ok, created_path, receipt} | {ok:False, offline}
    | {ok:False, error}. Never runs unless the caller passed approved routing."""
    import api.acervo_studio as studio

    routing = routing or {}
    scope = str(routing.get("scope", "") or "").strip().lower()
    slug = str(routing.get("slug", "") or "").strip().lower()
    nature = str(routing.get("nature", "") or "").strip().lower() or "knowledge"
    title = str(routing.get("title", "") or "").strip()
    if scope != "micro":
        return {"ok": False, "error": "promote target must be a microverso (scope=micro)"}
    if not _slug_ok(slug):
        return {"ok": False, "error": "invalid microverso slug"}
    if not _slug_ok(nature):
        return {"ok": False, "error": "invalid nature"}
    if not title:
        return {"ok": False, "error": "title is required"}
    env = studio._read_envelope(root, iid)
    if env is None:
        return {"ok": False, "error": "envelope not found"}
    content = _envelope_content(root, iid, env)
    user_prompt = ("Raw inbox item to turn into a semantic page.\ntitle: %s\nnature: %s\n\n"
                   "---\n%s\n---\n" % (title, nature, content))
    try:
        text = _run_agent_text(_PROMOTE_SYSTEM, user_prompt, session=session)
    except AgentUnavailable:
        return {"ok": False, "offline": True}
    crafted = _extract_json(text) or {}
    body_md = str(crafted.get("body_markdown", "") or "").strip() or content or title
    class_name = str(crafted.get("class", "") or "").strip().lower()
    class_name = "perene" if class_name == "perene" else "volátil"
    description = str(crafted.get("description", "") or "").strip()[:160] or title
    raw_tags = crafted.get("tags") if isinstance(crafted.get("tags"), list) else []
    tags = [re.sub(r"[^a-z0-9-]+", "-", str(t).strip().lower()).strip("-")
            for t in raw_tags][:8]
    tags = [t for t in tags if t]
    micro_dir = root / "micro" / slug
    existed = micro_dir.exists()
    try:
        _scaffold_microverso(root, slug)
        receipt = _commit_via_acervoctl(root, slug, nature, title, body_md,
                                        class_name, description, tags)
    except (PromoteError, OSError) as e:
        # A failed promote must not leave a new, empty microverso skeleton behind.
        if not existed:
            try:
                shutil.rmtree(micro_dir)
            except OSError:
                pass
        return {"ok": False, "error": str(e)}
    # The page is committed — the write succeeded. Moving the envelope to
    # promoted/ is best-effort: a move failure must not 500 or discard the write.
    try:
        _move_to_promoted(root, iid)
    except OSError as e:
        logger.warning("promote: envelope move to promoted/ failed after commit: %s", e)
    return {"ok": True,
            "created_path": receipt.get("relative_output") or receipt.get("target_path"),
            "receipt": receipt}


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
    # NFKD-fold accents first (ç→c, ã→a) so a Portuguese tag becomes "preco",
    # not "pre-o" — mirrors acervo_studio._slugify's normalization.
    def _one(t):
        s = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9-]+", "-", s.strip().lower()).strip("-")
    tags = [_one(t) for t in (raw if isinstance(raw, list) else [])][:8]
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
        # The model output is untrusted: `findings` may arrive as a non-list
        # (a single object, a number) — guard before slicing (mirrors ask's
        # isinstance guard on `sources`) so a bad shape never 500s.
        raw_finds = obj.get("findings")
        raw_finds = raw_finds if isinstance(raw_finds, list) else []
        for f in raw_finds[:5]:
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
                  "the", "of", "is", "to", "in", "an"}


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
                # Resolve + guard BEFORE reading: a symlink whose NAME looks
                # clean but resolves into .quarantine/ or a `_`-prefixed area
                # (e.g. _meta) must not be read or cited. Mirrors the assist
                # guard in _page_content_for_assist; also drops out-of-root
                # symlinks so their bodies are never read.
                try:
                    parts = f.resolve().relative_to(root.resolve()).parts
                except (OSError, ValueError):
                    continue
                if any(p.startswith((".", "_")) for p in parts):
                    continue
                rel = "/".join(parts)
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
