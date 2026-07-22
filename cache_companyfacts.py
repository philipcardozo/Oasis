from __future__ import annotations

import json
import ssl
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
UNIVERSE = ROOT / "graph" / "data" / "universe.json"
from oasis_paths import facts_dir

OUT_DIR = facts_dir()  # must match dcf_export.FACTS
UA = "OasisGraph/0.1 (companyfacts cache; local research use)"


def cik10(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        raise ValueError("missing CIK")
    return digits.zfill(10)


def resolve_cik(token: str, nodes: list[dict]) -> str:
    raw = token.strip()
    if raw.isdigit():
        return cik10(raw)
    q = raw.upper()
    for node in nodes:
        if q in {str(node.get("id", "")).upper(), str(node.get("t", "")).upper()}:
            return cik10(node.get("cik", ""))
    raise ValueError(f"no CIK found for {token!r}")


def cache_one(cik: str) -> Path:
    cik = cik10(cik)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
    with urlopen(req, timeout=30, context=ctx) as res:
        payload = json.loads(res.read().decode("utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"CIK{cik}.json"
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    return path


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python3 cache_companyfacts.py TICKER_OR_CIK [...]")
    nodes = json.load(UNIVERSE.open())["nodes"]
    for token in sys.argv[1:]:
        path = cache_one(resolve_cik(token, nodes))
        print(f"cached {path}")


if __name__ == "__main__":
    main()
