"""Reverse DCF (prompt 11): solve for the constant 10-year FCF growth that the
current market cap is pricing in. Reuses dcf_export's SEC-facts extraction — the
XBRL TAGS map is imported, never duplicated.
"""
from __future__ import annotations

from dcf_export import FactsUnavailable, TAGS, get_latest_filed_annual, load_facts, load_node

YEARS = 10


def _latest(series: dict) -> float | None:
    return series[max(series)] if series else None


def _pv(fcf0: float, growth: float, disc: float, term_growth: float) -> float:
    """Enterprise value = PV of a 10y growing FCF stream + Gordon terminal value."""
    pv = cf = 0.0
    for t in range(1, YEARS + 1):
        cf = fcf0 * (1 + growth) ** t
        pv += cf / (1 + disc) ** t
    tv = cf * (1 + term_growth) / (disc - term_growth)
    return pv + tv / (1 + disc) ** YEARS


def _solve_growth(fcf0: float, target_ev: float, disc: float, term_growth: float) -> float | None:
    """Bisection for growth in [-50%, +100%] with PV(growth) == target_ev."""
    lo, hi = -0.5, 1.0
    f = lambda g: _pv(fcf0, g, disc, term_growth) - target_ev
    flo, fhi = f(lo), f(hi)
    if (flo > 0) == (fhi > 0):
        return None  # priced-in growth is outside the plausible band
    for _ in range(100):
        mid = (lo + hi) / 2
        if (f(mid) > 0) == (flo > 0):
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def reverse_dcf(entity_id: str, discount: float = 0.09, terminal_growth: float = 0.025,
                method: str = "cash_flow") -> dict:
    try:
        node = load_node(entity_id)
    except ValueError as e:
        return {"available": False, "reason": str(e)}
    if not str(node.get("cik") or "").strip().isdigit():  # '—' placeholder / blank -> no facts
        return {"available": False, "reason": "no SEC CIK"}
    try:
        facts, _ = load_facts(node)  # local-only by default
    except FactsUnavailable as e:
        return {"available": False, "reason": str(e), "facts_cached": False,
                "hint": "run refresh_financial_facts.py to acquire SEC facts"}
    except Exception as e:  # parse / unexpected — degrade cleanly
        return {"available": False, "reason": f"facts unavailable: {e}"}

    shares = _latest(get_latest_filed_annual(facts, TAGS["shares"]))
    price = (node.get("price") or {}).get("price")
    if not shares or not price:
        return {"available": False, "reason": "missing price or shares"}
    if method == "dividend":
        fcf0 = _latest(get_latest_filed_annual(facts, TAGS["dividends"]))
    else:
        cfo = _latest(get_latest_filed_annual(facts, TAGS["cfo"]))
        capex = _latest(get_latest_filed_annual(facts, TAGS["capex"]))
        fcf0 = (cfo - capex) if (cfo is not None and capex is not None) else None
    if not fcf0 or fcf0 <= 0:
        return {"available": False, "reason": "non-positive free cash flow"}

    cash = _latest(get_latest_filed_annual(facts, TAGS["cash"])) or 0.0
    debt = _latest(get_latest_filed_annual(facts, TAGS["debt"])) or 0.0  # ponytail: single debt tag, understates multi-tranche debt
    market_cap = price * shares
    net_debt = debt - cash
    target_ev = market_cap + net_debt

    implied = _solve_growth(fcf0, target_ev, discount, terminal_growth)
    if implied is None:
        return {"available": False, "reason": "priced-in growth outside -50%..+100%"}
    sensitivity = [{"discount": d, "implied_growth": _solve_growth(fcf0, target_ev, d, terminal_growth)}
                   for d in (0.07, 0.08, 0.09, 0.10, 0.11)]
    return {
        "available": True, "entity_id": node["id"], "name": node.get("n"), "method": method,
        "discount": discount, "terminal_growth": terminal_growth,
        "fcf0": fcf0, "shares": shares, "price": price, "market_cap": market_cap,
        "net_debt": net_debt, "target_ev": target_ev,
        "implied_growth": implied, "sensitivity": sensitivity,
    }


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(reverse_dcf(sys.argv[1] if len(sys.argv) > 1 else "NVDA"), indent=2))
