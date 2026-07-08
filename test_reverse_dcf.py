"""Prompt 11: reverse-DCF solver converges and reproduces market cap within 1%."""
from reverse_dcf import _pv, reverse_dcf


def test_reverse_dcf_nvda_converges() -> None:
    r = reverse_dcf("NVDA")
    assert r["available"], r
    assert -0.5 <= r["implied_growth"] <= 1.0  # -50%..+100% band
    assert len(r["sensitivity"]) == 5 and all(s["implied_growth"] is not None for s in r["sensitivity"])

    # PV of the implied-growth stream reproduces the target EV (== mcap + net debt) within 1%.
    pv = _pv(r["fcf0"], r["implied_growth"], r["discount"], r["terminal_growth"])
    assert abs(pv - r["target_ev"]) / r["target_ev"] < 0.01
    # Equity value implied by that PV reproduces market cap within 1%.
    assert abs((pv - r["net_debt"]) - r["market_cap"]) / r["market_cap"] < 0.01


def test_reverse_dcf_no_cik_degrades() -> None:
    r = reverse_dcf("PVT_OPENAI")
    assert r == {"available": False, "reason": "no SEC CIK"}


if __name__ == "__main__":
    test_reverse_dcf_nvda_converges()
    test_reverse_dcf_no_cik_degrades()
    print("reverse_dcf ok")
