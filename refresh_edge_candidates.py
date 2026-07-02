"""Create relationship candidates from cached news.

Candidates are review material only. `expand_us.py` includes them only after
`status` is changed to `confirmed` and the evidence fields are present.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from expand_us import edge_key, resolve_id

ROOT = Path(__file__).parent
GRAPH = ROOT / "graph" / "data" / "universe.json"
NEWS = ROOT / "graph" / "data" / "news.json"
OUT = ROOT / "graph" / "data" / "edge_candidates.json"
REJECTED = ROOT / "graph" / "data" / "rejected_edges.json"

KEYWORDS = {
    "acquired": ("acquire", "acquires", "acquired", "buyout", "takeover"),
    "partners": ("partner", "partners", "partnership", "alliance", "collaborat"),
    "supplies": ("supplier", "supplies", "supply", "customer", "vendor"),
    "contracts": ("contract", "award", "task order", "obligation"),
    "funds": ("invest", "investment", "stake", "backs", "funding"),
}


def load(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.load(path.open())
    except json.JSONDecodeError:
        return fallback


def infer_rel(text: str) -> str | None:
    low = text.lower()
    for rel, words in KEYWORDS.items():
        if any(w in low for w in words):
            return rel
    return None


def name_hit(text: str, node: dict) -> bool:
    low = text.lower()
    name = re.sub(r"\b(inc|corp|corporation|company|co|plc|ltd|llc|holdings|group)\b\.?", "", node["n"].lower())
    words = [w for w in re.split(r"[^a-z0-9]+", name) if len(w) > 3]
    ticker = "" if str(node.get("t", "")).lower() in {"private", "agency", "legacy"} else node.get("t", "")
    return (ticker and re.search(rf"\b{re.escape(ticker.lower())}\b", low)) or (words and " ".join(words[:2]) in low)


def make_candidates(graph: dict, news: dict, existing: list[dict], rejected: list[dict]) -> list[dict]:
    nodes = {n["id"]: n for n in graph["nodes"]}
    searchable = [n for n in graph["nodes"] if n.get("deg", 0) > 0]
    live = {(l["from"], l["rel"], l["to"]) for l in graph["links"]}
    seen = {edge_key(c) for c in existing} | {edge_key(r) for r in rejected}
    out = []

    for source_id, items in (news.get("items_by_node") or {}).items():
        source = nodes.get(resolve_id(source_id))
        if not source:
            continue
        for item in items:
            title = item.get("title", "")
            rel = infer_rel(title)
            if not rel:
                continue
            for target in searchable:
                if target["id"] == source["id"] or not name_hit(title, target):
                    continue
                rec = {
                    "from": source["id"],
                    "to": target["id"],
                    "rel": rel,
                    "status": "candidate",
                    "src": item.get("source") or "Google News",
                    "source_url": item.get("url") or "",
                    "as_of": item.get("published") or date.today().isoformat(),
                    "confidence": 0.35,
                    "val": 0.0,
                    "detail": title,
                }
                key = edge_key(rec)
                if (rec["from"], rec["rel"], rec["to"]) not in live and key not in seen:
                    seen.add(key)
                    out.append(rec)
    return out


def main() -> None:
    graph = load(GRAPH, {"nodes": [], "links": []})
    news = load(NEWS, {"items_by_node": {}})
    existing = load(OUT, [])
    rejected = load(REJECTED, [])
    kept = [c for c in existing if c.get("status") != "candidate"]
    candidates = kept + make_candidates(graph, news, kept, rejected)
    OUT.write_text(json.dumps(candidates, indent=2) + "\n")
    if not REJECTED.exists():
        REJECTED.write_text("[]\n")
    print(f"Wrote {len(candidates)} edge candidates -> {OUT}")


if __name__ == "__main__":
    main()
