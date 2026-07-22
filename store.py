"""Shared readers for the canonical DuckDB/Parquet graph store."""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STORE = ROOT / "data" / "store"
NODES = STORE / "nodes.parquet"
EDGES = STORE / "edges.parquet"
ALIASES = ROOT / "graph" / "data" / "aliases.json"


def _mtime(path: Path) -> float:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run python3 bootstrap.py")
    return path.stat().st_mtime


def _rows(path: Path) -> list[dict]:
    import duckdb

    con = duckdb.connect()
    cur = con.execute(f"select * from '{path.as_posix()}'")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    con.close()
    return rows


def _json(value, fallback):
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _scalar(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


@lru_cache(maxsize=2)
def _load_nodes(mtime: float) -> tuple[dict, ...]:
    out = []
    for row in _rows(NODES):
        node = {k: _scalar(v) for k, v in row.items() if v is not None}
        node["n"] = node.pop("name", "")
        node["t"] = node.pop("ticker", "")
        for key in ("research", "price", "entity_model"):
            node[key] = _json(node.pop(f"{key}_json", None), {})
        for key in ("entity_type", "security_type", "issuer_id"):
            if node.get(key) in (None, ""):
                node[key] = node["entity_model"].get(key, "")
        out.append(node)
    return tuple(out)


@lru_cache(maxsize=2)
def _load_edges(mtime: float) -> tuple[dict, ...]:
    out = []
    for row in _rows(EDGES):
        edge = {k: _scalar(v) for k, v in row.items() if v is not None}
        edge["from"] = edge.pop("from_id")
        edge["to"] = edge.pop("to_id")
        out.append(edge)
    return tuple(out)


def load_nodes() -> list[dict]:
    return list(_load_nodes(_mtime(NODES)))


def load_edges() -> list[dict]:
    return list(_load_edges(_mtime(EDGES)))


@lru_cache(maxsize=2)
def _by_id(mtime: float) -> dict[str, dict]:
    return {node["id"]: node for node in _load_nodes(mtime)}


def by_id() -> dict[str, dict]:
    return _by_id(_mtime(NODES))


@lru_cache(maxsize=2)
def _node_count(mtime: float) -> int:
    import duckdb

    con = duckdb.connect()
    count = con.execute(f"select count(*) from '{NODES.as_posix()}'").fetchone()[0]
    con.close()
    return int(count)


def node_count() -> int:
    return _node_count(_mtime(NODES))


@lru_cache(maxsize=2)
def _aliases(nodes_mtime: float, aliases_mtime: float) -> dict[str, str]:
    nodes = _load_nodes(nodes_mtime)
    out = {node["id"].upper(): node["id"] for node in nodes}
    for node in nodes:
        if node.get("t"):
            out.setdefault(str(node["t"]).upper(), node["id"])
        if str(node.get("id", "")).upper() == str(node.get("t", "")).upper():
            out[str(node["t"]).upper()] = node["id"]
    if ALIASES.exists():
        out.update({str(k).upper(): v for k, v in json.loads(ALIASES.read_text("utf-8")).items()})
    return out


def aliases() -> dict[str, str]:
    aliases_mtime = ALIASES.stat().st_mtime if ALIASES.exists() else 0
    return _aliases(_mtime(NODES), aliases_mtime)
