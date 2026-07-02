"""Refresh recent company-news snippets for the graph UI.

Uses Google News RSS because it works without an API key. The output is a small
optional cache consumed by graph/index.html; missing news never blocks the graph.

Run:   python3 refresh_news.py [max_entities]
Deps:  pip install requests
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

ROOT = Path(__file__).parent
GRAPH = ROOT / "graph" / "data" / "universe.json"
OUT = ROOT / "graph" / "data" / "news.json"
RSS_URL = "https://news.google.com/rss/search"
UA = "BusinessGraph/0.1 (veratori@veratori.com)"


def rss_url(node: dict) -> str:
    ticker = "" if node.get("t") in {"private", "agency", "legacy"} else node.get("t", "")
    query = f'"{node["n"]}" {ticker} when:14d'.strip()
    params = {
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }
    return RSS_URL + "?" + urllib.parse.urlencode(params)


def fetch_items(node: dict, limit: int = 5) -> list[dict]:
    response = requests.get(rss_url(node), timeout=30, headers={"User-Agent": UA})
    response.raise_for_status()
    raw = response.content
    root = ET.fromstring(raw)
    items = []
    for item in root.findall("./channel/item")[:limit]:
        published = item.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(published).date().isoformat()
        except (TypeError, ValueError):
            pass
        items.append({
            "title": item.findtext("title") or "",
            "url": item.findtext("link") or "",
            "source": item.findtext("source") or "Google News",
            "published": published,
        })
    return items


def main() -> None:
    max_entities = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    data = json.load(GRAPH.open())
    nodes = [n for n in data["nodes"] if n.get("deg", 0) > 0 and n.get("kind") in {"public", "security"}]
    nodes.sort(key=lambda n: (n.get("kind") not in {"public", "security"}, -n.get("deg", 0), n["n"]))
    nodes = nodes[:max_entities]

    by_node = {}
    for i, node in enumerate(nodes, 1):
        try:
            items = fetch_items(node)
        except Exception as exc:
            print(f"  failed {node['id']} {node['n']}: {exc}")
            items = []
        if items:
            by_node[node["id"]] = items
        print(f"  {i}/{len(nodes)} {node['id']}: {len(items)} items")
        time.sleep(0.25)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": date.today().isoformat(),
        "source": RSS_URL,
        "items_by_node": by_node,
    }, indent=2))
    print(f"Wrote news for {len(by_node)} companies -> {OUT}")


if __name__ == "__main__":
    main()
