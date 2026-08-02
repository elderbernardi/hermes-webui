"""F4 Colheita — bandeja de candidatos + fable-judge mecânico (núcleo puro).
Store: $ACERVO/_tasks/<canvas_id>/colheita.jsonl (append-only, último estado por id vence)."""
import json, re, hashlib
from pathlib import Path
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

def judge_committed(target_path: str, log_path: str, _validate=None) -> dict:
    """fable-judge mecânico: verifica por execução/diff, nunca lendo relatório."""
    tp, lp = Path(target_path), Path(log_path)
    checks = {"exists": tp.exists(), "frontmatter": False, "clean_portable": False, "logged": False}
    reasons: list[str] = []
    if not checks["exists"]:
        reasons.append(f"arquivo ausente: {target_path}")
        return {"ok": False, "checks": checks, "reasons": reasons}
    body = tp.read_text(encoding="utf-8")
    validate = _validate or _default_validate
    checks["frontmatter"] = bool(validate(str(tp)))
    if not checks["frontmatter"]:
        reasons.append("frontmatter OKF inválido")
    leaks = [pat.pattern for pat in _INSTANCE_PATTERNS if pat.search(body)]
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
