"""F4 Colheita — bandeja de candidatos + fable-judge mecânico (núcleo puro).
Store: $ACERVO/_tasks/<canvas_id>/colheita.jsonl (append-only, último estado por id vence).

Task 4 adds: acervoctl subprocess wrapper, OKF frontmatter builder,
HTTP endpoints (list/stream/adotar/preparar/checkout), SSE room
(cloned from canvas_sala pattern), and forward-dispatch hooks."""
import json, re, hashlib, os, shlex, subprocess, sys, tempfile, threading, time
from pathlib import Path
from urllib.parse import parse_qs
from api import canvas_store

_DRAFT_FIRST_NATURES = {"persona", "decision"}          # + class perene (abaixo)
_INSTANCE_PATTERNS = [re.compile(r"canvas_\w"), re.compile(r"\bsession[_-]?id\b", re.I),
                      re.compile(r"\btask_\w"), re.compile(r"(?i)api[_-]?key|secret|token")]

def _store(canvas_id: str) -> Path:
    return canvas_store.tasks_dir() / canvas_id / "colheita.jsonl"

def compute_gate(nature: str, cls: str, source_trust: str) -> str:
    if source_trust == "untrusted":
        return "forced-draft"
    if cls == "perene" or nature in _DRAFT_FIRST_NATURES:
        return "draft-first"
    return "auto"

def _new_id(cand: dict) -> str:
    seed = f"{cand.get('title','')}|{cand.get('ref') or cand.get('body','')}"
    return "h_" + hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]

def ingest_candidate(canvas_id: str, cand: dict) -> dict:
    cls = cand.get("class", "volátil")
    st = cand.get("source_trust", "agent")
    card = {
        "id": cand.get("id") or _new_id(cand),
        "nature": cand["nature"], "scope": cand.get("scope", ""),
        "title": cand.get("title", ""), "porque": cand.get("porque", ""),
        "ref": cand.get("ref"), "body": cand.get("body"),
        "class": cls, "source_trust": st,
        "gate": compute_gate(cand["nature"], cls, st),
        "status": "pending", "origin": cand.get("origin", "agent"),
    }
    p = _store(canvas_id); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(card, ensure_ascii=False) + "\n")
    return card

def set_status(canvas_id: str, card_id: str, status: str, **extra) -> dict:
    rec = {"id": card_id, "status": status, **extra}
    _store(canvas_id).parent.mkdir(parents=True, exist_ok=True)
    with _store(canvas_id).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec

def list_cards(canvas_id: str) -> list[dict]:
    p = _store(canvas_id)
    if not p.exists():
        return []
    merged: dict[str, dict] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        cur = merged.get(rec["id"], {})
        cur.update(rec)
        merged[rec["id"]] = cur
    return list(merged.values())

def _body_after_frontmatter(text: str) -> str:
    """Return the document body, excluding a leading YAML --- frontmatter block.

    Spec §4.B: clean_portable scans the CORPO only, not metadata.
    A legitimate ref: canvas_... in the frontmatter is provenance, not an instance leak.
    """
    if text.startswith("---"):
        # Find the closing '---' fence on its own line
        idx = text.find("\n---", 3)
        if idx != -1:
            nl = text.find("\n", idx + 1)
            return text[nl + 1:] if nl != -1 else ""
    return text


def judge_committed(target_path: str, log_path: str, _validate=None) -> dict:
    """fable-judge mecânico: verifica por execução/diff, nunca lendo relatório."""
    tp, lp = Path(target_path), Path(log_path)
    checks = {"exists": tp.exists(), "frontmatter": False, "clean_portable": False, "logged": False}
    reasons: list[str] = []
    if not checks["exists"]:
        reasons.append(f"arquivo ausente: {target_path}")
        return {"ok": False, "checks": checks, "reasons": reasons}
    full_text = tp.read_text(encoding="utf-8")
    validate = _validate or _default_validate
    checks["frontmatter"] = bool(validate(str(tp)))
    if not checks["frontmatter"]:
        reasons.append("frontmatter OKF inválido")
    # Scan body only (after frontmatter) for instance leaks
    body_text = _body_after_frontmatter(full_text)
    leaks = [pat.pattern for pat in _INSTANCE_PATTERNS if pat.search(body_text)]
    checks["clean_portable"] = not leaks
    if leaks:
        reasons.append(f"clean-portable: possível vazamento de instância/segredo ({leaks})")
    checks["logged"] = lp.exists() and tp.name in lp.read_text(encoding="utf-8")
    if not checks["logged"]:
        reasons.append("sem entrada no _meta/log.md")
    return {"ok": all(checks.values()), "checks": checks, "reasons": reasons}

def _default_validate(path: str) -> bool:
    """Seam real (substituído em Task 4 pela chamada acervoctl validate-frontmatter)."""
    return True


# ── Task 4: impure layer ──────────────────────────────────────────────────────

# ── SSE room (cloned from canvas_sala._room/_emit/_stream_events) ──────────

COLHEITA_ROOMS: dict[str, dict] = {}
_ROOMS_LOCK = threading.Lock()


def _room(cid: str) -> dict:
    with _ROOMS_LOCK:
        room = COLHEITA_ROOMS.get(cid)
        if room is None:
            room = {"events": [], "cond": threading.Condition(), "subs": 0}
            COLHEITA_ROOMS[cid] = room
        return room


def _emit(cid: str, name: str, payload) -> None:
    """Append-only + notify. Non-closing, cursor-replay (cloned from canvas_sala)."""
    room = _room(cid)
    with room["cond"]:
        room["events"].append((name, payload))
        room["cond"].notify_all()


def _stream_events(handler, room: dict, cursor: int) -> None:
    """SSE re-attachable stream (cloned from canvas_sala._stream_events)."""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    with room["cond"]:
        room["subs"] = room.get("subs", 0) + 1
    try:
        while True:
            with room["cond"]:
                room["cond"].wait_for(lambda: len(room["events"]) > cursor, timeout=30)
                pending = room["events"][cursor:]
            if not pending:
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
                continue
            frames = []
            for name, payload in pending:
                cursor += 1
                data = json.dumps(payload, ensure_ascii=False)
                frames.append(f"id: {cursor}\nevent: {name}\ndata: {data}\n\n")
            handler.wfile.write("".join(frames).encode("utf-8"))
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        with room["cond"]:
            room["subs"] = max(0, room.get("subs", 0) - 1)


# ── acervoctl subprocess wrapper ───────────────────────────────────────────

# Default: the acervoctl.py lives in the exocortex runtime — resolved via env
# ACERVOCTL_CMD (shlex.split). Fallback points to scripts/acervoctl.py in this
# repo for local dev. Tests inject a fake by monkeypatching this function.
_REPO = Path(__file__).resolve().parent.parent


def acervoctl(args: list[str], input_file=None) -> tuple[int, str, str]:
    """Run the acervoctl CLI. Returns (returncode, stdout, stderr).
    Resolves the command from env ACERVOCTL_CMD (shlex.split) or falls back to
    [sys.executable, <repo>/scripts/acervoctl.py]. Secrets are never logged."""
    env_cmd = os.environ.get("ACERVOCTL_CMD")
    if env_cmd:
        base_cmd = shlex.split(env_cmd)
    else:
        base_cmd = [sys.executable, str(_REPO / "scripts" / "acervoctl.py")]
    full_cmd = base_cmd + [str(a) for a in args]
    stdin_data = None
    if input_file is not None:
        stdin_data = Path(input_file).read_bytes()
    result = subprocess.run(
        full_cmd,
        input=stdin_data,
        capture_output=True,
        env={**os.environ},
    )
    return result.returncode, result.stdout.decode("utf-8", errors="replace"), \
           result.stderr.decode("utf-8", errors="replace")


# ── OKF v0.2 frontmatter builder ──────────────────────────────────────────

_NATURE_TYPE_MAP = {
    "knowledge": "knowledge",
    "decision": "decision",
    "reflection": "reflection",
    "template": "template",
    "workflow": "workflow",
}
_EPISTEMIC_NATURES = {"knowledge", "decision", "reflection"}


def _build_frontmatter(card: dict, canvas_id: str = "", now: str | None = None, today: str | None = None) -> str:
    """Build OKF v0.2 YAML frontmatter block for an acervo card.

    Args:
        card: The colheita card dict
        canvas_id: The originating canvas session id (for sources[].ref provenance)
        now: ISO timestamp (defaults to current time)
        today: ISO date (defaults to today)
    """
    if now is None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    if today is None:
        today = time.strftime("%Y-%m-%d")
    nature = card.get("nature", "knowledge")
    okf_type = _NATURE_TYPE_MAP.get(nature, nature)
    title = card.get("title", "")
    # Always emit description: use porque if present, else title, else fallback
    description = (card.get("porque") or title or "sem descrição")[:160]
    tags_raw = card.get("tags") or ["colheita"]
    cls = card.get("class", "volátil")

    lines = [
        "---",
        "schema: acervo/v0.2",
        f"type: {okf_type}",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"description: {json.dumps(description, ensure_ascii=False)}",
    ]
    lines.append("tags:")
    for tag in tags_raw:
        lines.append(f"  - {tag}")
    lines += [
        f"created_at: {now}",
        f"class: {cls}",
        "status: active",
    ]
    if nature in _EPISTEMIC_NATURES:
        lines += [
            "epistemic: observation",
            "confidence: likely",
            "sources:",
            "  - type: agent-inference",
            f"    ref: {canvas_id}",
            f"observed_at: {today}",
            "extraction: agent",
        ]
    lines.append("---")
    return "\n".join(lines) + "\n"


# ── JSON response helper (same pattern as canvas_tarefas._j) ───────────────

def _j(handler, obj, status: int = 200) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


# ── Endpoint handlers ──────────────────────────────────────────────────────

def handle_colheita_get(handler, parsed) -> bool:
    """Dispatch GET /api/canvas/colheita/* paths."""
    path = parsed.path
    qs = parse_qs(parsed.query)

    if path == "/api/canvas/colheita/list":
        cid = (qs.get("canvas_id") or [""])[0]
        _j(handler, list_cards(cid))
        return True

    if path == "/api/canvas/colheita/stream":
        cid = (qs.get("canvas_id") or [""])[0]
        try:
            cursor = int((qs.get("since") or ["0"])[0])
        except (TypeError, ValueError):
            cursor = 0
        if cursor < 0:
            cursor = 0
        _stream_events(handler, _room(cid), cursor)
        return True

    return False


def handle_colheita_post(handler, path: str, body: dict) -> bool:
    """Dispatch POST /api/canvas/colheita/* paths."""

    if path == "/api/canvas/colheita/adotar":
        cid = body.get("canvas_id") or ""
        source_event = body.get("source_event") or {}
        nature = body.get("nature") or source_event.get("nature", "knowledge")
        scope = body.get("scope") or source_event.get("scope", "")
        cand = {
            **source_event,
            "nature": nature,
            "scope": scope,
            "origin": "manual",
            "class": body.get("class") or source_event.get("class", "volátil"),
            "source_trust": body.get("source_trust") or source_event.get("source_trust", "agent"),
        }
        card = ingest_candidate(cid, cand)
        _emit(cid, "colheita_candidate", card)
        _j(handler, card)
        return True

    if path == "/api/canvas/colheita/preparar":
        cid = body.get("canvas_id") or ""
        cards = [c for c in list_cards(cid) if c.get("status") == "pending"]
        results = []
        for card in cards:
            scope = card.get("scope", "")
            nature = card.get("nature", "knowledge")
            title = card.get("title", "")
            trust = card.get("source_trust", "agent")
            # Write receipt to a temp file so acervoctl can populate it
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as tf:
                receipt_out = tf.name
            rc, stdout, _stderr = acervoctl([
                "prepare-write",
                "--microverso", scope,
                "--nature", nature,
                "--title", title,
                "--source-trust", trust,
                "--receipt-out", receipt_out,
            ])
            if rc == 0:
                try:
                    receipt = json.loads(stdout)
                except (json.JSONDecodeError, ValueError):
                    # Try reading the receipt-out file directly
                    try:
                        receipt = json.loads(Path(receipt_out).read_text(encoding="utf-8"))
                    except Exception:
                        receipt = {}
                set_status(cid, card["id"], "prepared", receipt=receipt)
                _emit(cid, "colheita_prepared", {**card, "status": "prepared", "receipt": receipt})
                results.append({"card_id": card["id"], "ok": True})
            else:
                results.append({"card_id": card["id"], "ok": False, "error": _stderr[:200]})
            # Clean up temp receipt-out file
            try:
                Path(receipt_out).unlink(missing_ok=True)
            except Exception:
                pass
        _j(handler, {"prepared": sum(1 for r in results if r.get("ok")), "items": results})
        return True

    if path == "/api/canvas/colheita/checkout":
        cid = body.get("canvas_id") or ""
        decisions = body.get("decisions") or []
        # Build a lookup of current card state
        cards_by_id = {c["id"]: c for c in list_cards(cid)}
        committed = 0
        unverified = 0
        rejected = 0
        items = []

        for dec in decisions:
            card_id = dec.get("card_id") or ""
            action = dec.get("action") or ""
            card = cards_by_id.get(card_id)
            if not card:
                items.append({"card_id": card_id, "ok": False, "error": "card não encontrado"})
                continue

            if action == "rejeitar":
                set_status(cid, card_id, "rejected")
                _emit(cid, "colheita_rejected", {**card, "status": "rejected"})
                rejected += 1
                items.append({"card_id": card_id, "judge": {"ok": False, "action": "rejected"}})
                continue

            if action == "aprovar":
                receipt = card.get("receipt") or {}
                target_path = receipt.get("target_path", "")
                log_path = receipt.get("log_path", "")
                trust = card.get("source_trust", "agent")
                cls = card.get("class", "volátil")
                porque = (card.get("porque") or card.get("title") or "sem descrição")[:160]

                # Build frontmatter + corpo
                frontmatter = _build_frontmatter(card, canvas_id=cid)
                ref = card.get("ref")
                if ref and Path(ref).is_file():
                    corpo = Path(ref).read_text(encoding="utf-8")
                else:
                    corpo = card.get("body") or ""

                content = frontmatter + "\n" + corpo

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".md", delete=False, encoding="utf-8"
                ) as tf:
                    tf.write(content)
                    content_file = tf.name

                # Persist receipt to a temp file for commit-write --receipt
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False, encoding="utf-8"
                ) as rf:
                    json.dump(receipt, rf, ensure_ascii=False)
                    receipt_file = rf.name

                try:
                    rc, stdout, _stderr = acervoctl([
                        "commit-write",
                        "--receipt", receipt_file,
                        "--content-file", content_file,
                        "--description", porque,
                        "--class-name", cls,
                        "--source-trust", trust,
                    ])
                    if rc == 0:
                        try:
                            commit_out = json.loads(stdout)
                        except (json.JSONDecodeError, ValueError):
                            commit_out = {}
                        # Use commit output paths if available, else fall back to receipt
                        tp = commit_out.get("target_path") or target_path
                        lp = commit_out.get("log_path") or log_path

                        judge = judge_committed(
                            tp, lp,
                            _validate=lambda p: acervoctl(["validate-frontmatter", "--path", p])[0] == 0,
                        )
                        final_status = "committed" if judge["ok"] else "committed_unverified"
                        set_status(cid, card_id, final_status, judge=judge)
                        _emit(cid, "colheita_committed", {**card, "status": final_status, "judge": judge})
                        committed += 1
                        items.append({"card_id": card_id, "judge": judge})
                    else:
                        try:
                            err_detail = json.loads(stdout).get("error", stdout)
                        except Exception:
                            err_detail = stdout or _stderr
                        judge = {"ok": False, "checks": {}, "reasons": [f"commit-write falhou: {err_detail[:200]}"]}
                        set_status(cid, card_id, "committed_unverified", judge=judge)
                        _emit(cid, "colheita_committed", {**card, "status": "committed_unverified", "judge": judge})
                        unverified += 1
                        items.append({"card_id": card_id, "judge": judge})
                finally:
                    try:
                        Path(content_file).unlink(missing_ok=True)
                        Path(receipt_file).unlink(missing_ok=True)
                    except Exception:
                        pass

        _j(handler, {
            "committed": committed,
            "unverified": unverified,
            "rejected": rejected,
            "items": items,
        })
        return True

    return False
