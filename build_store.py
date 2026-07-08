"""Build the canonical Parquet store from the built universe + caches (prompt 10).

DuckDB is the query engine; Parquet under data/store/ is the canonical store.
The JSON UI payloads are demoted to build artifacts. Flattens scalar node fields
and entity_model into columns; keeps genuinely ragged fields as JSON blobs.

Run standalone or via refresh_all.py. Regenerable, so data/store/ is gitignored.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "graph" / "data"
STORE = ROOT / "data" / "store"


def _j(v):
    return json.dumps(v, ensure_ascii=False) if v is not None else None


def download(url: str, path) -> Path:
    """Fetch url to path via curl (uses the system trust store — urllib's CA bundle
    is unreliable on this machine). Returns the path; raises on non-2xx."""
    import subprocess
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["curl", "-sL", "--fail", "--max-time", "90", "-o", str(path), url], check=True)
    return path


def write_parquet(rows: list[dict], path) -> int:
    """Write rows to a Parquet file via a JSONL -> DuckDB COPY. Reused by refresh_*."""
    from pathlib import Path as _P
    path = _P(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) or "{}")
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT * FROM read_json_auto('{tmp.as_posix()}', format='newline_delimited', "
        f"maximum_object_size=20000000)) TO '{path.as_posix()}' (FORMAT PARQUET)"
    )
    con.close()
    tmp.unlink()
    return len(rows)


def build() -> dict[str, int]:
    STORE.mkdir(parents=True, exist_ok=True)
    uni = json.loads((DATA / "universe.json").read_text("utf-8"))
    nodes, links = uni.get("nodes", []), uni.get("links", [])

    node_rows = []
    for n in nodes:
        em = n.get("entity_model") or {}
        loc = em.get("location") or {}
        node_rows.append({
            "id": n.get("id"), "canonical_id": n.get("canonical_id"), "name": n.get("n"),
            "ticker": n.get("t"), "kind": n.get("kind"), "node_type": n.get("node_type"),
            "sector": n.get("sector"), "sub": n.get("sub"), "group": n.get("group"),
            "country": n.get("country"), "hq": n.get("hq"), "cik": n.get("cik"),
            "lei": n.get("lei"), "exchange": n.get("exchange"), "deg": n.get("deg"),
            "source_confidence": n.get("source_confidence"), "location_confidence": n.get("location_confidence"),
            "entity_type": em.get("entity_type"), "security_type": em.get("security_type"),
            "issuer_id": em.get("issuer_id"), "loc_country": loc.get("country"),
            "loc_confidence": loc.get("confidence"), "x": n.get("x"), "y": n.get("y"),
            "research_json": _j(n.get("research")), "price_json": _j(n.get("price")),
            "entity_model_json": _j(em),
        })

    edge_rows = [{
        "from_id": l.get("from"), "to_id": l.get("to"), "rel": l.get("rel"), "src": l.get("src"),
        "val": l.get("val"), "detail": l.get("detail"), "source_url": l.get("source_url"),
        "as_of": l.get("as_of"), "confidence": l.get("confidence"),
    } for l in links]

    filing_rows = []
    for n in nodes:
        for f in (n.get("filings") or []):
            row = {"node_id": n.get("id"), "cik": n.get("cik")}
            row.update({k: (_j(v) if isinstance(v, (dict, list)) else v) for k, v in f.items()})
            filing_rows.append(row)

    price_rows = []
    pf = DATA / "prices.json"
    if pf.exists():
        for sym, p in json.loads(pf.read_text("utf-8")).items():
            if not isinstance(p, dict):
                continue
            price_rows.append({
                "symbol": p.get("symbol") or sym, "as_of": p.get("as_of"), "price": p.get("price"),
                "day_change_abs": p.get("day_change_abs"), "day_change_pct": p.get("day_change_pct"),
                "chg_6m_pct": p.get("chg_6m_pct"), "source": p.get("source"), "spark_json": _j(p.get("spark")),
            })

    counts = {}
    for rows, name in ((node_rows, "nodes"), (edge_rows, "edges"), (filing_rows, "filings"), (price_rows, "prices")):
        counts[name] = write_parquet(rows, STORE / f"{name}.parquet")
    print(f"store built: nodes={counts['nodes']} edges={counts['edges']} "
          f"filings={counts['filings']} prices={counts['prices']} -> {STORE}")
    return counts


if __name__ == "__main__":
    build()
