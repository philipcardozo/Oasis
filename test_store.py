"""Self-check for the Parquet store (prompt 10): counts + a flattened field round-trip."""
import json
from pathlib import Path

import duckdb

import build_store

ROOT = Path(__file__).resolve().parent


def test_store_matches_universe() -> None:
    build_store.build()
    uni = json.loads((ROOT / "graph/data/universe.json").read_text("utf-8"))
    con = duckdb.connect()

    def count(name: str) -> int:
        return con.execute(f"select count(*) from '{ROOT}/data/store/{name}.parquet'").fetchone()[0]

    # Node/edge counts must match the source universe exactly (the DuckDB acceptance one-liner).
    assert count("nodes") == len(uni["nodes"]), (count("nodes"), len(uni["nodes"]))
    assert count("edges") == len(uni.get("links", []))

    # entity_model got flattened into real columns, not left as an opaque blob.
    row = con.execute(
        f"select name, ticker, entity_type from '{ROOT}/data/store/nodes.parquet' where id = 'NVDA'"
    ).fetchone()
    assert row and row[0] and row[1] == "NVDA", row


if __name__ == "__main__":
    test_store_matches_universe()
    print("store self-check ok")
