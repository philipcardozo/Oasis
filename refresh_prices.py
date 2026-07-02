"""Cache latest market prices for connected listed companies and securities.

Run after expand_us.py has built graph/data/universe.json:
    python3 refresh_prices.py
"""

from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path

ROOT = Path(__file__).parent
GRAPH = ROOT / "graph" / "data" / "universe.json"
OUT = ROOT / "graph" / "data" / "prices.json"
RATE = 0.2
SPARK_POINTS = 26
SIX_MONTH_DAYS = 126
EXCHANGE_SUFFIX = {
    "ALXL": ".LS",
    "BCSE": ".CS",
    "BME": ".MC",
    "ENXL": ".LS",
    "XLIS": ".LS",
    "XAMS": ".AS",
    "XBOM": ".BO",
    "XBRU": ".BR",
    "XETR": ".DE",
    "XHKG": ".HK",
    "XKRX": ".KS",
    "XLON": ".L",
    "XNSE": ".NS",
    "XOSL": ".OL",
    "XPAR": ".PA",
    "XSHG": ".SS",
    "XSHE": ".SZ",
    "XTPE": ".TW",
    "XSWX": ".SW",
    "XTSX": ".TO",
    "XTKS": ".T",
    "XTSE": ".TO",
    "XWBO": ".VI",
}


def pct(new: float, old: float) -> float | None:
    return None if old == 0 else round((new - old) / old * 100, 2)


def downsample(values: list[float], size: int = SPARK_POINTS) -> list[float]:
    vals = [float(v) for v in values]
    if len(vals) <= size:
        return [round(v, 2) for v in vals]
    step = (len(vals) - 1) / (size - 1)
    return [round(vals[round(i * step)], 2) for i in range(size)]


def price_record(rows: list[tuple[str, float]]) -> dict:
    clean = [(d, float(v)) for d, v in sorted(rows) if v is not None]
    if len(clean) < 2:
        raise ValueError("need at least two closes")
    as_of, last = clean[-1]
    prior = clean[-2][1]
    base = clean[-(SIX_MONTH_DAYS + 1)][1] if len(clean) > SIX_MONTH_DAYS else clean[0][1]
    closes = [v for _, v in clean[-SIX_MONTH_DAYS:]]
    return {
        "as_of": as_of,
        "price": round(last, 2),
        "day_change_abs": round(last - prior, 2),
        "day_change_pct": pct(last, prior),
        "chg_6m_pct": pct(last, base),
        "spark": downsample(closes),
    }


def fetch_yfinance(ticker: str) -> list[tuple[str, float]]:
    import yfinance as yf

    df = yf.download(ticker, period="6mo", interval="1d", auto_adjust=True, progress=False, threads=False)
    if df is None or df.empty:
        raise ValueError("empty yfinance response")
    close = df["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    out = []
    for idx, value in close.dropna().items():
        day = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        out.append((day, float(value)))
    return out


def fetch_stooq(ticker: str) -> list[tuple[str, float]]:
    from urllib.request import Request, urlopen

    import ssl

    symbols = [ticker.lower(), ticker.lower().replace("-", ".")]
    last_error = None
    for symbol in dict.fromkeys(symbols):
        url = f"https://stooq.com/q/d/l/?s={symbol}.us&i=d"
        req = Request(url, headers={"User-Agent": "BusinessGraph/0.1"})
        try:
            try:
                text = urlopen(req, timeout=30).read().decode("utf-8")
            except Exception as exc:
                if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
                    raise
                import certifi

                ctx = ssl.create_default_context(cafile=certifi.where())
                text = urlopen(req, timeout=30, context=ctx).read().decode("utf-8")
            rows = [
                (r["Date"], float(r["Close"]))
                for r in csv.DictReader(io.StringIO(text))
                if r.get("Date") and r.get("Close")
            ]
            if rows:
                return rows[-160:]
            last_error = "empty CSV"
        except Exception as exc:
            last_error = exc
    raise ValueError(f"stooq failed: {last_error}")


def fetch_closes(ticker: str) -> tuple[list[tuple[str, float]], str]:
    try:
        return fetch_yfinance(ticker), "yfinance"
    except Exception as yf_exc:
        try:
            return fetch_stooq(ticker), "stooq"
        except Exception as stooq_exc:
            raise RuntimeError(f"yfinance: {yf_exc}; stooq: {stooq_exc}") from stooq_exc


def market_symbol(node: dict) -> str:
    if node.get("quote_symbol"):
        return str(node["quote_symbol"]).strip()
    raw_id = str(node.get("id") or "")
    ticker = str(node.get("t") or raw_id).strip()
    if ":" not in raw_id:
        return ticker.replace(".", "-")
    exchange, raw_ticker = raw_id.split(":", 1)
    suffix = EXCHANGE_SUFFIX.get(exchange.upper(), "")
    if exchange.upper() == "XHKG":
        try:
            return f"{int(raw_ticker):04d}.HK"
        except ValueError:
            return f"{raw_ticker}.HK"
    return f"{raw_ticker}{suffix}" if suffix else raw_ticker.replace(".", "-")


def connected_public_nodes() -> list[dict]:
    graph = json.load(GRAPH.open())
    return sorted(
        (n for n in graph["nodes"] if n.get("kind") in {"public", "security"} and n.get("deg", 0) > 0),
        key=lambda n: n["id"],
    )


def main() -> None:
    nodes = connected_public_nodes()
    prices = {}
    for i, node in enumerate(nodes, 1):
        ticker = market_symbol(node)
        try:
            rows, source = fetch_closes(ticker)
            prices[node["id"]] = price_record(rows)
            prices[node["id"]]["source"] = source
            prices[node["id"]]["symbol"] = ticker
            print(f"  {i}/{len(nodes)} {node['id']} ({ticker}): {prices[node['id']]['price']} as of {prices[node['id']]['as_of']}")
        except Exception as exc:
            print(f"  failed {node['id']} ({ticker}): {exc}")
            prices[node["id"]] = {"error": str(exc), "symbol": ticker}
        time.sleep(RATE)
    OUT.write_text(json.dumps(prices, indent=2) + "\n")
    print(f"Wrote prices for {len(prices)} companies -> {OUT}")


if __name__ == "__main__":
    main()
