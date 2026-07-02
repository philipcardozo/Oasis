"""Load the JSONL graph produced by ingest.py into Neo4j.

Idempotent: MERGE on company id so re-running updates instead of duplicating.
Reads connection details from env so the same script works locally and in CI.

Run:   python load_neo4j.py
Env:   NEO4J_URI (default bolt://localhost:7687)
       NEO4J_USER (default neo4j)
       NEO4J_PASSWORD (required)
Deps:  pip install neo4j

After loading, explore three hops around any company in the Neo4j Browser:

    MATCH p=(c:Company {name:'Tesla, Inc.'})-[*1..3]-(x)
    RETURN p
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from neo4j import GraphDatabase

ROOT = Path(__file__).parent


def read_jsonl(path: Path):
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load(tx, nodes, edges):
    for n in nodes:
        tx.run(
            "MERGE (c:Company {id:$id}) "
            "SET c.name=$name, c.cik=$cik, c.lei=$lei, c.sic=$sic",
            id=n["id"], name=n.get("name"),
            cik=n.get("cik"), lei=n.get("lei"), sic=n.get("sic"),
        )
    for e in edges:
        # Relationship type is data, so build the query string from it.
        # Values stay parameterized; only the validated rel label is inlined.
        rel = "".join(ch for ch in e["rel"] if ch.isalnum() or ch == "_")
        tx.run(
            f"MATCH (a:Company {{id:$from}}), (b:Company {{id:$to}}) "
            f"MERGE (a)-[r:{rel}]->(b) "
            f"SET r.source=$source, r.as_of_date=$as_of",
            **{"from": e["from"], "to": e["to"],
               "source": e.get("source"), "as_of": e.get("as_of_date")},
        )


def main() -> None:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD")
    if not pw:
        raise SystemExit("Set NEO4J_PASSWORD")

    nodes = list(read_jsonl(ROOT / "data" / "nodes.jsonl"))
    edges = list(read_jsonl(ROOT / "data" / "edges.jsonl"))

    driver = GraphDatabase.driver(uri, auth=(user, pw))
    with driver.session() as s:
        s.run("CREATE CONSTRAINT company_id IF NOT EXISTS "
              "FOR (c:Company) REQUIRE c.id IS UNIQUE")
        s.execute_write(load, nodes, edges)
    driver.close()
    print(f"Loaded {len(nodes)} companies and {len(edges)} relationships.")


if __name__ == "__main__":
    main()
