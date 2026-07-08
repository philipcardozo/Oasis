"""Prompt 15: event gates + briefing generation."""
import json
from pathlib import Path

import duckdb
import pytest

import gates

ROOT = Path(__file__).resolve().parent
EVENTS = ROOT / "data" / "store" / "events.parquet"


def test_materiality_per_type() -> None:
    assert gates.materiality_gate("filing", {"form": "8-K"})["pass"]
    assert not gates.materiality_gate("filing", {"form": "424B5"})["pass"]
    assert gates.materiality_gate("contract", {"obligations_usd": 20e6})["pass"]
    assert not gates.materiality_gate("contract", {"obligations_usd": 1e6})["pass"]
    assert gates.materiality_gate("price", {"sigma": 2.5})["pass"]
    assert not gates.materiality_gate("price", {"sigma": 1.0})["pass"]
    assert gates.materiality_gate("trade", {"amount_low_usd": 50_000})["pass"]


def test_dedupe_and_hash() -> None:
    seen = {"abc"}
    assert not gates.dedupe_gate("abc", seen)["pass"]
    assert gates.dedupe_gate("xyz", seen)["pass"]
    h = gates.content_hash
    assert h("NVDA", "filing", "acc1") == h("NVDA", "filing", "acc1")   # stable
    assert h("NVDA", "filing", "acc1") != h("NVDA", "filing", "acc2")   # key-sensitive


def test_priority_rules() -> None:
    assert gates.priority_gate(True, False, 9)["priority"] == "P1"   # material + high degree
    assert gates.priority_gate(True, True, 0)["priority"] == "P1"    # material + watchlisted
    assert gates.priority_gate(True, False, 2)["priority"] == "P2"   # material only
    assert gates.priority_gate(False, True, 9)["priority"] == "P3"   # not material


def test_events_have_gate_stamps() -> None:
    if not EVENTS.exists():
        pytest.skip("events not built")
    for (g,) in duckdb.execute(f"select gates_json from '{EVENTS.as_posix()}' limit 100").fetchall():
        assert len(json.loads(g)) >= 3  # entity, dedupe, materiality, priority


def test_briefing_from_store() -> None:
    if not EVENTS.exists():
        pytest.skip("events not built")
    import build_briefing
    out = build_briefing.build("2099-01-01")  # fixture day
    txt = Path(out).read_text()
    assert "# OASIS briefing" in txt and "## P1" in txt
    assert "[source](http" in txt  # P1/P2 lines carry working source links
    Path(out).unlink()


if __name__ == "__main__":
    test_materiality_per_type()
    test_dedupe_and_hash()
    test_priority_rules()
    test_events_have_gate_stamps()
    test_briefing_from_store()
    print("events ok")
