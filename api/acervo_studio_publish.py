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
# Match the publish tool's SPECIFIC "driver not found" message, not the bare
# filename — a genuine Drive failure (quota/auth) raises an Exception whose
# traceback frames also mention google_api.py, which must NOT be misread as
# "Drive não configurado".
_DRIVE_MISSING_MARKER = "google_api.py não encontrado"
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
    Raises DriveNotConfigured when the Drive driver is missing (that path
    raises SystemExit inside the tool BEFORE any upload, so no failure receipt
    is written for it), PublishError on any other failure (those do write the
    tool's receipts/receipt.google_drive.failed.json)."""
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
    dt = manifest.get("drive_target")
    folder = dt.get("folder_path") if isinstance(dt, dict) else None
    return {
        "ok": True,
        "artifact": {
            "id": str(art_id),
            "title": str(manifest.get("title", "") or art_id),
            "status": str(manifest.get("status", "") or "draft"),
            "drive_target": str(folder or "exocortex/inbox"),
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
