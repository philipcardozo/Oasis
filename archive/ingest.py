"""Config-driven ingestion for the business-relationship graph.

Reads config/sources.yaml, pulls each enabled source, and writes nodes and
edges as line-delimited JSON. Every edge carries `source` and `as_of_date`,
so re-running the job refreshes the graph without any code change.

Run:  python ingest.py
Deps: pip install requests pyyaml
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

import requests
import yaml

TODAY = date.today().isoformat()
ROOT = Path(__file__).parent


# --------------------------------------------------------------------------- #
# Graph writer
# --------------------------------------------------------------------------- #
class GraphWriter:
    """Collects nodes/edges, dedupes by id, and writes JSONL."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}

    def add_company(self, node_id: str, name: str, **props) -> None:
        if not node_id:
            return
        self.nodes[node_id] = {
            "id": node_id,
            "type": "Company",
            "name": name,
            **props,
        }

    def add_edge(self, src: str, rel: str, dst: str, source: str, **props) -> None:
        if not (src and dst):
            return
        key = f"{src}|{rel}|{dst}"
        self.edges[key] = {
            "from": src,
            "rel": rel,
            "to": dst,
            "source": source,
            "as_of_date": TODAY,
            **props,
        }

    def flush(self, nodes_path: Path, edges_path: Path) -> None:
        nodes_path.parent.mkdir(parents=True, exist_ok=True)
        with nodes_path.open("w") as f:
            for n in self.nodes.values():
                f.write(json.dumps(n) + "\n")
        with edges_path.open("w") as f:
            for e in self.edges.values():
                f.write(json.dumps(e) + "\n")
        print(f"  wrote {len(self.nodes)} nodes -> {nodes_path}")
        print(f"  wrote {len(self.edges)} edges -> {edges_path}")


# --------------------------------------------------------------------------- #
# Identifier resolution: turn a bare ticker into {ticker, name, cik, lei}.
# --------------------------------------------------------------------------- #
_SEC_TICKERS: dict | None = None


def resolve_seed(ticker: str, sec_cfg: dict, gleif_cfg: dict) -> dict:
    global _SEC_TICKERS
    ua = {"User-Agent": sec_cfg["user_agent"]}

    # SEC publishes a full ticker -> CIK + name map. Fetch once, cache.
    if _SEC_TICKERS is None:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         timeout=30, headers=ua)
        r.raise_for_status()
        _SEC_TICKERS = {v["ticker"]: v for v in r.json().values()}
        time.sleep(0.2)

    rec = _SEC_TICKERS.get(ticker.upper(), {})
    name = rec.get("title", ticker)
    cik = str(rec.get("cik_str", "")).zfill(10) if rec else None

    # Resolve the LEI by name search against GLEIF (free, no key).
    lei = None
    rr = requests.get(f"{gleif_cfg['base_url']}/lei-records",
                      params={"filter[entity.legalName]": name, "page[size]": 1},
                      timeout=30, headers={"Accept": "application/vnd.api+json"})
    time.sleep(60.0 / gleif_cfg.get("rate_limit_per_min", 55))
    if rr.status_code == 200:
        hits = rr.json().get("data", [])
        if hits:
            lei = hits[0]["id"]

    return {"ticker": ticker.upper(), "name": name, "cik": cik, "lei": lei}


# --------------------------------------------------------------------------- #
# GLEIF: free, no key. Gives the "who owns whom" ownership backbone.
# --------------------------------------------------------------------------- #
def ingest_gleif(seed: dict, cfg: dict, g: GraphWriter) -> None:
    lei = seed.get("lei")
    if not lei:
        return
    base = cfg["base_url"]
    pause = 60.0 / cfg.get("rate_limit_per_min", 55)

    def get(path: str) -> dict | None:
        r = requests.get(f"{base}{path}", timeout=30,
                         headers={"Accept": "application/vnd.api+json"})
        time.sleep(pause)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    # The seed entity itself.
    rec = get(f"/lei-records/{lei}")
    if rec:
        ent = rec["data"]["attributes"]["entity"]
        g.add_company(lei, ent["legalName"]["name"],
                      lei=lei,
                      country=ent.get("legalAddress", {}).get("country"),
                      status=ent.get("status"))

    # Parents -> OWNS -> seed.
    parents = get(f"/lei-records/{lei}/direct-parents")
    for p in (parents or {}).get("data", []):
        pa = p["attributes"]["entity"]
        plei = p["id"]
        g.add_company(plei, pa["legalName"]["name"], lei=plei)
        g.add_edge(plei, "OWNS", lei, source="gleif")

    # Seed -> OWNS -> children.
    children = get(f"/lei-records/{lei}/direct-children")
    for c in (children or {}).get("data", []):
        ca = c["attributes"]["entity"]
        clei = c["id"]
        g.add_company(clei, ca["legalName"]["name"], lei=clei)
        g.add_edge(lei, "OWNS", clei, source="gleif")


# --------------------------------------------------------------------------- #
# SEC EDGAR: free, no key. Needs a descriptive User-Agent w/ contact email.
# --------------------------------------------------------------------------- #
def ingest_sec(seed: dict, cfg: dict, g: GraphWriter) -> None:
    cik = seed.get("cik")
    if not cik:
        return
    cik10 = cik.zfill(10)
    url = f"{cfg['base_url']}/submissions/CIK{cik10}.json"
    r = requests.get(url, timeout=30, headers={"User-Agent": cfg["user_agent"]})
    time.sleep(1.0 / cfg.get("rate_limit_per_sec", 8))
    if r.status_code != 200:
        print(f"  SEC: {cik10} returned {r.status_code}, skipping")
        return
    data = r.json()

    node_id = seed.get("lei") or f"CIK{cik10}"
    g.add_company(node_id, data.get("name", seed["name"]),
                  cik=cik10,
                  tickers=data.get("tickers", []),
                  sic=data.get("sicDescription"))

    # Former names recorded by the SEC: useful for entity resolution later.
    for former in data.get("formerNames", []):
        g.nodes[node_id].setdefault("aliases", []).append(former.get("name"))


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def expand_env(value):
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())
    sources = cfg["sources"]
    g = GraphWriter()

    for ticker in cfg["seeds"]:
        seed = resolve_seed(ticker, sources["sec_edgar"], sources["gleif"])
        print(f"Seed: {seed['ticker']} -> {seed['name']} "
              f"(cik={seed['cik']}, lei={seed['lei']})")
        if sources.get("gleif", {}).get("enabled"):
            ingest_gleif(seed, sources["gleif"], g)
        if sources.get("sec_edgar", {}).get("enabled"):
            ingest_sec(seed, sources["sec_edgar"], g)

    out = cfg["output"]
    g.flush(ROOT / out["nodes_path"], ROOT / out["edges_path"])


if __name__ == "__main__":
    main()
