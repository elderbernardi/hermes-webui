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
