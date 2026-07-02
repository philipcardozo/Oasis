from datetime import date, timedelta

from refresh_prices import market_symbol, price_record


def main() -> None:
    start = date(2026, 1, 1)
    rows = [((start + timedelta(days=i)).isoformat(), 100 + i) for i in range(127)]
    out = price_record(rows)

    assert out["price"] == 226
    assert out["day_change_abs"] == 1
    assert out["day_change_pct"] == round(1 / 225 * 100, 2)
    assert out["chg_6m_pct"] == 126
    assert len(out["spark"]) == 26
    assert market_symbol({"id": "XLIS:EDP", "t": "EDP"}) == "EDP.LS"
    assert market_symbol({"id": "BME:IBE", "t": "IBE"}) == "IBE.MC"
    assert market_symbol({"id": "BCSE:ATW", "t": "ATW"}) == "ATW.CS"


if __name__ == "__main__":
    main()
