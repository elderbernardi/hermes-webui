"""EXCRTX MOD-013 (F2) — memória viva de capacidades por microverso (OFF-TRAIL).

build_agent_card = derivação PURA de _meta/index.md (+ catalog.sqlite se existir).
refresh_capability_cache = rotina ESCRITORA dedicada -> global/tools/state/curador/
capabilities.json (fora da árvore de conhecimento; disposable). load_capability_card
= leitor do Curador (só lê o cache). O Curador NUNCA escreve: importa só load_*.
_meta/capabilities.json canônico = graduação F4 (fora do escopo)."""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

_STATE_REL = "global/tools/state/curador"
_CACHE_NAME = "capabilities.json"


def _acervo_root(root=None) -> pathlib.Path:
    if root is not None:
        return pathlib.Path(root)
    from api.canvas_store import acervo_root
    return acervo_root()


def _parse_index(md: str) -> list[dict]:
    """Extrai (nature, [exemplos], porque) das seções '### Nature' + bullets do index.md."""
    skills: list[dict] = []
    cur = None
    for line in md.splitlines():
        h = re.match(r"^#{3,}\s+(.+?)\s*$", line)
        if h:
            cur = {"name": h.group(1).strip().lower(), "examples": [], "porque": ""}
            skills.append(cur)
            continue
        b = re.match(r"^\s*[-*]\s+(\S+)\s*(?:—|-)\s*(.+?)\s*$", line)
        if b and cur is not None:
            cur["examples"].append(b.group(1).strip())
            if not cur["porque"]:
                cur["porque"] = b.group(2).strip()
    return [s for s in skills if s["examples"]]


def build_agent_card(slug: str, *, root=None) -> dict:
    root = _acervo_root(root)
    idx = root / "micro" / slug / "_meta" / "index.md"
    md = idx.read_text(encoding="utf-8") if idx.is_file() else ""
    parsed = _parse_index(md)
    skills = []
    for s in parsed:
        entry = {"id": f"{slug}/{s['name']}", "name": s["name"],
                 "examples": s["examples"][:5], "porque": s["porque"]}
        # catalog.sqlite é opcional/disposable; contagem só se existir (degrada sem)
        cat = root / "global/tools/state/catalog.sqlite"
        if cat.is_file():
            entry["count"] = len(s["examples"])   # placeholder estrutural do count real
        skills.append(entry)
    digest = hashlib.sha256(json.dumps(skills, sort_keys=True, ensure_ascii=False)
                            .encode("utf-8")).hexdigest()[:16]
    return {"name": slug, "version": digest, "skills": skills}


def _microverso_slugs(root: pathlib.Path) -> list[str]:
    micro = root / "micro"
    if not micro.is_dir():
        return []
    return sorted(p.name for p in micro.iterdir()
                  if p.is_dir() and not p.name.startswith(("_", ".")))


def refresh_capability_cache(root=None) -> pathlib.Path:
    """ROTINA ESCRITORA (não o Curador). Idempotente: mesma entrada -> mesmo digest."""
    root = _acervo_root(root)
    cards = {slug: build_agent_card(slug, root=root) for slug in _microverso_slugs(root)}
    digest = hashlib.sha256(
        json.dumps({k: v["version"] for k, v in cards.items()}, sort_keys=True)
        .encode("utf-8")).hexdigest()[:16]
    out_dir = root / _STATE_REL
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / _CACHE_NAME
    payload = {"digest": digest, "microversos": cards}
    new_blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    if not (path.is_file() and path.read_text(encoding="utf-8") == new_blob):
        path.write_text(new_blob, encoding="utf-8")   # reescrita no-op se digest igual
    return path


def load_capability_card(slug: str, *, root=None) -> dict | None:
    """LEITOR DO CURADOR — só lê o cache off-trail; nunca deriva/escreve."""
    root = _acervo_root(root)
    path = root / _STATE_REL / _CACHE_NAME
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return (blob.get("microversos") or {}).get(slug)
