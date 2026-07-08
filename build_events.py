"""Append-only event extraction (prompt 15). Diffs existing refresh outputs against
data/store/events.parquet and appends genuinely new, gated events. No new fetchers,
no queues, no daemons — just files + deterministic gates.

Event schema: {event_id, oasis_id, event_type, ts, title, payload_json, source_url,
retrieved_at, gates_json}. Unresolvable items go to data/store/events_quarantine.json.
"""
from __future__ import annotations

import json
import statistics
from datetime import date, datetime
from pathlib import Path

import duckdb

import gates
from build_store import write_parquet

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "graph" / "data"
STORE = ROOT / "data" / "store"
EVENTS = STORE / "events.parquet"
QUARANTINE = STORE / "events_quarantine.json"

# USAspending obligations in gov_contracts are expressed in $B.
BN = 1e9


def _load_json(name, default):
    p = DATA / name
    return json.loads(p.read_text("utf-8")) if p.exists() else default


def _universe():
    uni = _load_json("universe.json", {"nodes": [], "links": []})
    by_id = {n["id"]: n for n in uni["nodes"]}
    return by_id


def _watchlisted() -> set:
    wl = _load_json("watchlists.json", {"watchlists": []})
    return {eid for w in wl.get("watchlists", []) for eid in w.get("entity_ids", [])}


def _existing_ids() -> set:
    if not EVENTS.exists():
        return set()
    return {r[0] for r in duckdb.execute(f"select event_id from '{EVENTS.as_posix()}'").fetchall()}


def _candidates(by_id):
    """Yield (oasis_id, event_type, natural_key, ts, title, payload, source_url)."""
    # Filings: new accession per company.
    for tkr, rows in _load_json("filings.json", {}).items():
        for f in rows or []:
            yield (tkr, "filing", f.get("accessionNumber", ""), f.get("filingDate", ""),
                   f"{f.get('form', 'Filing')} filed", {"form": f.get("form")}, f.get("url"))
    # Prices: >= 2 sigma daily move vs trailing spark.
    for tkr, p in _load_json("prices.json", {}).items():
        spark = p.get("spark") or []
        if not isinstance(p, dict) or len(spark) < 8:
            continue
        rets = [(spark[i] - spark[i - 1]) / spark[i - 1] for i in range(1, len(spark)) if spark[i - 1]]
        sd = statistics.pstdev(rets) if len(rets) > 1 else 0
        move = (p.get("day_change_pct") or 0) / 100
        sigma = move / sd if sd else 0
        if abs(sigma) >= 2:
            yield (tkr, "price", p.get("as_of", ""), p.get("as_of", ""),
                   f"{p.get('day_change_pct'):+.1f}% move ({sigma:+.1f}σ)", {"sigma": sigma}, None)
    # News: new item per entity.
    for nid, items in _load_json("news.json", {}).get("items_by_node", {}).items():
        for it in items or []:
            yield (nid, "news", it.get("url", ""), _load_json("news.json", {}).get("generated_at", ""),
                   it.get("title", "News"), {}, it.get("url"))
    # Contracts: USAspending obligation per recipient.
    gc = _load_json("gov_contracts.json", {})
    for l in gc.get("links", []):
        usd = float(l.get("val") or 0) * BN
        yield (l.get("to"), "contract", f"{l.get('from')}:{l.get('val')}", str(gc.get("fiscal_year", "")),
               f"{l.get('detail') or 'Federal obligation'}", {"obligations_usd": usd}, l.get("source_url"))
    # Trades: politician PTR filings (prompt 13).
    if (STORE / "pol_trades.parquet").exists():
        for pid, name, dt, doc, url in duckdb.execute(
            f"select politician_id, filer_name, disclosure_date, doc_id, source_url "
            f"from '{(STORE / 'pol_trades.parquet').as_posix()}' where politician_id is not null").fetchall():
            yield (pid, "trade", doc, dt, f"{name} disclosed a periodic transaction report",
                   {"amount_low_usd": gates.TRADE_MATERIAL_USD}, url)


def build() -> dict:
    STORE.mkdir(parents=True, exist_ok=True)
    by_id = _universe()
    known = set(by_id) | {r[0] for r in (duckdb.execute(
        f"select id from '{(STORE / 'pol_members.parquet').as_posix()}'").fetchall()
        if (STORE / "pol_members.parquet").exists() else [])}
    watch = _watchlisted()
    seen = _existing_ids()
    now = datetime.now().isoformat(timespec="seconds")

    new_events, quarantine = [], []
    for oasis_id, etype, nkey, ts, title, payload, src in _candidates(by_id):
        eg = gates.entity_gate(oasis_id or "", known)
        if not eg["pass"]:
            quarantine.append({"oasis_id": oasis_id, "event_type": etype, "title": title, "reason": eg["reason"]})
            continue
        eid = gates.content_hash(oasis_id, etype, nkey)
        dg = gates.dedupe_gate(eid, seen)
        if not dg["pass"]:
            continue
        seen.add(eid)
        mg = gates.materiality_gate(etype, payload)
        deg = int(by_id.get(oasis_id, {}).get("deg") or 0)
        pg = gates.priority_gate(mg["pass"], oasis_id in watch, deg)
        new_events.append({
            "event_id": eid, "oasis_id": oasis_id, "event_type": etype, "ts": ts or "",
            "title": title, "payload_json": json.dumps(payload, ensure_ascii=False),
            "source_url": src or "", "retrieved_at": now,
            "gates_json": json.dumps([eg, dg, mg, pg], ensure_ascii=False), "priority": pg["priority"],
        })

    # Append: existing rows + new rows (read existing back as dicts, no pandas).
    existing = []
    if EVENTS.exists():
        cur = duckdb.execute(f"select * from '{EVENTS.as_posix()}'")
        cols = [d[0] for d in cur.description]
        existing = [dict(zip(cols, row)) for row in cur.fetchall()]
    write_parquet([*existing, *new_events], EVENTS)
    QUARANTINE.write_text(json.dumps(quarantine, ensure_ascii=False, indent=2), "utf-8")
    print(f"events: +{len(new_events)} new (total {len(existing) + len(new_events)}), "
          f"quarantined {len(quarantine)} -> {QUARANTINE.name}")
    return {"new": len(new_events), "total": len(existing) + len(new_events), "quarantined": len(quarantine)}


if __name__ == "__main__":
    build()
