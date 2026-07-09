"""Self-check for the Parquet store (prompt 10): counts + a flattened field round-trip."""
from pathlib import Path

import duckdb
import pytest
from store import EDGES, NODES, load_edges, load_nodes

ROOT = Path(__file__).resolve().parent


def test_store_matches_universe() -> None:
    if not NODES.exists() or not EDGES.exists():
        pytest.skip("Parquet store unavailable; run python3 bootstrap.py")
    con = duckdb.connect()

    def count(name: str) -> int:
        return con.execute(f"select count(*) from '{ROOT}/data/store/{name}.parquet'").fetchone()[0]

    assert count("nodes") == len(load_nodes())
    assert count("edges") == len(load_edges())

    # entity_model got flattened into real columns, not left as an opaque blob.
    row = con.execute(
        f"select name, ticker, entity_type from '{ROOT}/data/store/nodes.parquet' where id = 'NVDA'"
    ).fetchone()
    assert row and row[0] and row[1] == "NVDA", row


if __name__ == "__main__":
    test_store_matches_universe()
    print("store self-check ok")
