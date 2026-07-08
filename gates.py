"""Deterministic event gates (prompt 15). Each is a pure function returning a
{gate, pass, reason} stamp — inspectable, never silent. No I/O, no LLM.
"""
from __future__ import annotations

import hashlib

MATERIAL_FORMS = ("8-K", "10-K", "10-Q", "13D", "13G", "SC 13D", "SC 13G")
CONTRACT_MATERIAL_USD = 10e6
TRADE_MATERIAL_USD = 50_000


def content_hash(oasis_id: str, event_type: str, natural_key: str) -> str:
    return hashlib.sha1(f"{oasis_id}|{event_type}|{natural_key}".encode()).hexdigest()[:16]


def entity_gate(oasis_id: str, known_ids: set) -> dict:
    ok = bool(oasis_id) and oasis_id in known_ids
    return {"gate": "entity", "pass": ok, "reason": "resolved to node" if ok else "unresolved entity"}


def dedupe_gate(event_id: str, seen: set) -> dict:
    ok = event_id not in seen
    return {"gate": "dedupe", "pass": ok, "reason": "new" if ok else "duplicate within store"}


def materiality_gate(event_type: str, payload: dict) -> dict:
    if event_type == "filing":
        form = (payload.get("form") or "").upper()
        ok = form.startswith(MATERIAL_FORMS) and not form.startswith("424")
        return {"gate": "materiality", "pass": ok, "reason": f"{form or '?'} {'material' if ok else 'routine'}"}
    if event_type == "contract":
        usd = abs(float(payload.get("obligations_usd") or 0))
        ok = usd >= CONTRACT_MATERIAL_USD
        return {"gate": "materiality", "pass": ok, "reason": f"${usd/1e6:.0f}M {'>=' if ok else '<'} $10M"}
    if event_type == "price":
        sigma = abs(float(payload.get("sigma") or 0))
        ok = sigma >= 2
        return {"gate": "materiality", "pass": ok, "reason": f"{sigma:.1f}sigma move"}
    if event_type == "trade":
        usd = float(payload.get("amount_low_usd") or TRADE_MATERIAL_USD)
        ok = usd >= TRADE_MATERIAL_USD
        return {"gate": "materiality", "pass": ok, "reason": f"disclosed trade >= ${TRADE_MATERIAL_USD//1000}k"}
    if event_type == "news":
        return {"gate": "materiality", "pass": False, "reason": "news informational"}
    return {"gate": "materiality", "pass": False, "reason": "unknown type"}


def priority_gate(material: bool, watchlisted: bool, degree: int) -> dict:
    if material and (watchlisted or degree >= 5):
        pr, why = "P1", f"material + {'watchlisted' if watchlisted else f'degree {degree}'}"
    elif material:
        pr, why = "P2", "material"
    else:
        pr, why = "P3", "not material"
    return {"gate": "priority", "pass": True, "priority": pr, "reason": f"{pr}: {why}"}


if __name__ == "__main__":
    assert materiality_gate("filing", {"form": "8-K"})["pass"]
    assert not materiality_gate("filing", {"form": "424B5"})["pass"]
    assert materiality_gate("contract", {"obligations_usd": 20e6})["pass"]
    assert not materiality_gate("contract", {"obligations_usd": 1e6})["pass"]
    assert materiality_gate("price", {"sigma": 2.4})["pass"]
    assert priority_gate(True, False, 9)["priority"] == "P1"
    assert priority_gate(True, False, 1)["priority"] == "P2"
    assert priority_gate(False, True, 9)["priority"] == "P3"
    print("gates ok")
