"""Deterministic daily briefing (prompt 15): outputs/briefings/YYYY-MM-DD.md.
P1 events grouped by watchlist then entity; P2 as a compact digest. Plain Markdown,
no prose generation — every line is assembled from the events table + gate reasons.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
STORE = ROOT / "data" / "store"
DATA = ROOT / "graph" / "data"
OUT = ROOT / "outputs" / "briefings"


def _watchlist_map() -> dict:
    p = DATA / "watchlists.json"
    wl = json.loads(p.read_text("utf-8"))["watchlists"] if p.exists() else []
    return {eid: w["name"] for w in wl for eid in w.get("entity_ids", [])}


def _reason(gates_json: str) -> str:
    return next((g["reason"] for g in json.loads(gates_json) if g["gate"] == "priority"), "")


def build(day: str | None = None) -> Path:
    day = day or date.today().isoformat()
    events = STORE / "events.parquet"
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{day}.md"
    if not events.exists():
        path.write_text(f"# OASIS briefing — {day}\n\nNo events store yet.\n")
        return path

    wl_map = _watchlist_map()
    rows = duckdb.execute(
        f"select oasis_id, event_type, ts, title, source_url, gates_json, priority "
        f"from '{events.as_posix()}' order by ts desc").fetchall()
    p1 = [r for r in rows if r[6] == "P1"]
    p2 = [r for r in rows if r[6] == "P2"]

    out = [f"# OASIS briefing — {day}", "", f"**P1** {len(p1)} · **P2** {len(p2)} · total {len(rows)}", "",
           "## P1 — priority"]
    groups: dict = defaultdict(lambda: defaultdict(list))
    for r in p1:
        groups[wl_map.get(r[0], "Unwatchlisted")][r[0]].append(r)
    for wl in sorted(groups):
        out.append(f"\n### {wl}")
        for eid in sorted(groups[wl]):
            out.append(f"- **{eid}**")
            for r in groups[wl][eid]:
                src = f" · [source]({r[4]})" if r[4] else ""
                out.append(f"  - {r[3]} — {r[1]} · {r[2]}{src} — _{_reason(r[5])}_")

    out += ["", "## P2 — digest"]
    for r in p2[:60]:
        src = f" · [source]({r[4]})" if r[4] else ""
        out.append(f"- **{r[0]}** {r[3]} — {r[1]} · {r[2]}{src}")

    path.write_text("\n".join(out) + "\n", "utf-8")
    print(f"briefing -> {path} (P1 {len(p1)}, P2 {len(p2)})")
    return path


if __name__ == "__main__":
    build()
