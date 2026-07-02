"""Report likely duplicate entities without changing the graph."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re

ROOT = Path(__file__).parent
UNIVERSE = ROOT / "graph" / "data" / "universe.json"
OUT = ROOT / "graph" / "data" / "dupes_report.json"
SUFFIXES = {"inc", "corp", "co", "ltd", "plc", "sa", "ag", "nv", "group", "holdings", "the"}


def normalize_name(name: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", str(name).lower()).split()
    return " ".join(w for w in words if w not in SUFFIXES)


def usable_key(value) -> bool:
    return bool(re.search(r"[A-Za-z0-9]", str(value or "")))


def member(node: dict) -> dict:
    return {
        "id": node.get("id"),
        "canonical_id": node.get("canonical_id", node.get("id")),
        "name": node.get("n"),
        "kind": node.get("kind"),
        "cik": node.get("cik"),
        "lei": node.get("lei"),
    }


def collision_groups(nodes: list[dict], field: str | None = None) -> list[dict]:
    groups = defaultdict(list)
    for node in nodes:
        key = normalize_name(node.get("n", "")) if field is None else node.get(field)
        if key and usable_key(key):
            groups[str(key)].append(member(node))
    return [
        {"key": key, "members": sorted(items, key=lambda x: x["id"] or "")}
        for key, items in sorted(groups.items())
        if len(items) > 1
    ]


def build_report(nodes: list[dict]) -> dict:
    by_cik = collision_groups(nodes, "cik")
    by_lei = collision_groups(nodes, "lei")
    by_name = collision_groups(nodes)
    candidates = {
        item["id"]
        for group in by_cik + by_lei + by_name
        for item in group["members"]
        if item.get("id")
    }
    return {
        "totals": {
            "groups_by_name": len(by_name),
            "groups_by_cik": len(by_cik),
            "groups_by_lei": len(by_lei),
            "total_dup_candidates": len(candidates),
        },
        "by_cik": by_cik,
        "by_lei": by_lei,
        "by_name": by_name,
    }


def main() -> None:
    nodes = json.load(UNIVERSE.open())["nodes"]
    report = build_report(nodes)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    t = report["totals"]
    print(
        f"duplicate candidates: {t['total_dup_candidates']} "
        f"(name groups {t['groups_by_name']}, cik groups {t['groups_by_cik']}, lei groups {t['groups_by_lei']})"
    )


if __name__ == "__main__":
    main()
