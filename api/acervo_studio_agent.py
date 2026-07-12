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
import re
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
