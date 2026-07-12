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

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
    turn execute tools (promote). Raises AgentUnavailable if the runtime is absent."""
    from api import profiles as profiles_api

    active_profile = profiles_api.get_active_profile_name() or "default"
    with profiles_api.profile_env_for_background_worker(
            active_profile, "acervo studio agent", logger_override=logger):
        rt = _resolve_main_runtime(session)
        try:
            from run_agent import AIAgent
        except ImportError as e:
            raise AgentUnavailable(str(e))
        if AIAgent is None:
            raise AgentUnavailable("AIAgent unavailable")
        sid = "acervo-studio-%s" % uuid.uuid4().hex[:8]
        try:
            agent = AIAgent(
                model=rt["model"], provider=rt["provider"], base_url=rt["base_url"],
                api_key=rt["api_key"], platform="webui", quiet_mode=True,
                enabled_toolsets=list(enabled_toolsets), session_id=sid)
            result = agent.run_conversation(
                user_message=user_prompt, system_message=system_prompt,
                conversation_history=[], task_id=sid)
        except AgentUnavailable:
            raise
        except Exception as e:
            raise AgentUnavailable(str(e))
        return str((result or {}).get("final_response") or "").strip()


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
    "short sentence)."
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


def _acervoctl(scripts_dir, root, args):
    """Run one acervoctl subcommand (list form, no shell). Returns CompletedProcess."""
    env = dict(os.environ)
    env["PYTHONPATH"] = scripts_dir + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable or "python3", os.path.join(scripts_dir, "acervoctl.py")] + args,
        cwd=scripts_dir, env=env, capture_output=True, text=True,
        timeout=_ACERVOCTL_TIMEOUT)


def _commit_via_acervoctl(root, slug, nature, title, body_md, class_name, description):
    """prepare-write -> commit-write against `root` (the fixture/real acervo). The
    scope guard runs inside commit-write. Returns the parsed receipt dict. Raises
    PromoteError on any failure (surfaced to the user as a failed promote)."""
    scripts_dir = _resolve_acervoctl_dir()
    if scripts_dir is None:
        raise PromoteError("acervo control plane not found")
    root_s = str(root)
    with tempfile.TemporaryDirectory() as tmp:
        receipt_path = os.path.join(tmp, "r.json")
        body_path = os.path.join(tmp, "body.md")
        with open(body_path, "w", encoding="utf-8") as fh:
            fh.write(body_md)
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
    description = str(crafted.get("description", "") or "").strip()[:200] or title
    try:
        _scaffold_microverso(root, slug)
        receipt = _commit_via_acervoctl(root, slug, nature, title, body_md,
                                        class_name, description)
    except PromoteError as e:
        return {"ok": False, "error": str(e)}
    _move_to_promoted(root, iid)
    return {"ok": True,
            "created_path": receipt.get("relative_output") or receipt.get("target_path"),
            "receipt": receipt}
