"""Build graph/data/universe.json: every US public company (SEC ticker list) as
a node, S&P 500 members carrying exact GICS sectors and the rest classified by
SIC code (approximate) from the crawl cache. Curated nodes and links come from
JSON files and are validated against the node set.

Run after crawl_sic.py has populated (fully or partially) the SIC cache:
    python expand_us.py
Deps: pip install numpy (optional; layout falls back without it)
"""

from __future__ import annotations

import csv
import json
import math
import re
import ssl
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from build_map_geojson import write_map_geojson

ROOT = Path(__file__).parent
TICKERS = Path("/tmp/sec_tickers.json")
SP500_CSV = Path("/tmp/sp500.csv")
CACHE = ROOT / "graph" / "data" / "sic_cache.json"
OUT = ROOT / "graph" / "data" / "universe.json"
OUT_CORE = ROOT / "graph" / "data" / "universe_core.json"
OUT_BULK = ROOT / "graph" / "data" / "universe_bulk.json"
GOV_CONTRACTS = ROOT / "graph" / "data" / "gov_contracts.json"
GOV_CONTRACT_QUERIES = ROOT / "graph" / "data" / "gov_contract_queries.json"
FILINGS = ROOT / "graph" / "data" / "filings.json"
PRICES = ROOT / "graph" / "data" / "prices.json"
EDGE_CANDIDATES = ROOT / "graph" / "data" / "edge_candidates.json"
REJECTED_EDGES = ROOT / "graph" / "data" / "rejected_edges.json"
CURATED_NODES = ROOT / "graph" / "data" / "curated_nodes.json"
CURATED_LINKS = ROOT / "graph" / "data" / "curated_links.json"
SOURCES = ROOT / "graph" / "data" / "sources"
ALIASES = ROOT / "graph" / "data" / "aliases.json"
USASPENDING_API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_category/recipient/"
ALIASES_MAP = json.load(ALIASES.open()) if ALIASES.exists() else {}
SOURCE_REQUIRED = ("canonical_id", "name", "country", "exchange", "sector_or_sic")
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
UA = "BusinessGraph/0.1 (veratori@veratori.com)"
EXCHANGE_HQ_STUBS = {"NYSE", "Nasdaq", "OTC", "CBOE"}


def short_key(sector: str) -> str:
    return sector.lower().replace(" ", "_")


def group_key(group: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", group.lower()).strip("_")


SECTOR_COLORS = {
    "Information Technology": "#4d9fff",
    "Communication Services": "#6c7bff",
    "Health Care": "#2dc4a0",
    "Financials": "#3fb56b",
    "Industrials": "#9aa7b4",
    "Materials": "#b07d4e",
    "Energy": "#e0703a",
    "Utilities": "#d8b13a",
    "Consumer Discretionary": "#ff6f91",
    "Consumer Staples": "#c98ad6",
    "Real Estate": "#e0566f",
}

COLORS = dict(SECTOR_COLORS)
COLORS["Other"] = "#6b7682"
COLORS["Government"] = "#58c7f3"
COLORS["Historical / Defunct"] = "#b6a178"

REL_DEFS = {
    "supplies": {"name": "Supplies", "color": "#2dc4a0", "verb": ["supplies", "supplied by"]},
    "funds": {"name": "Funds", "color": "#e0a33a", "verb": ["funds", "funded by"]},
    "partners": {"name": "Partners", "color": "#9b8cff", "verb": ["partner", "partner"]},
    "same_issuer": {"name": "Same issuer / listing", "color": "#7fb3ff", "verb": ["mirrors listing", "mirrors listing"]},
    "contracts": {
        "name": "Government contracts",
        "color": "#58c7f3",
        "verb": ["contracts with", "contractor to"],
    },
    "acquired": {
        "name": "Acquired / absorbed",
        "color": "#c6a15b",
        "verb": ["acquired", "acquired by"],
    },
    "owns": {"name": "Owns", "color": "#d0a7ff", "verb": ["owns", "owned by"]},
    "government_action": {
        "name": "Government action",
        "color": "#ff7f6e",
        "verb": ["acted on", "subject to action by"],
    },
}


SECURITY_TYPE_GROUPS = {
    "adr": "Depositary receipts",
    "etf": "ETFs & index products",
    "fund": "Funds & trusts",
    "spac": "SPACs & blank checks",
    "warrant": "Warrants, rights & units",
    "right": "Warrants, rights & units",
    "unit": "Warrants, rights & units",
    "preferred": "Preferred securities",
    "debt": "Debt & asset-backed securities",
    "trust": "Funds & trusts",
    "security": "Listed securities",
}


def news_url(name: str, ticker: str | None = None) -> str:
    query = f"{name} {ticker or ''}".strip()
    return "https://news.google.com/search?q=" + quote_plus(query)


def usaspending_url(name: str) -> str:
    return "https://www.usaspending.gov/search/?search_term=" + quote_plus(name)


def resolve_id(value: str) -> str:
    raw = str(value).strip()
    dotless = raw.replace(".", "-")
    return ALIASES_MAP.get(raw) or ALIASES_MAP.get(dotless) or dotless


def sec_research(cik: str, ticker: str, name: str) -> dict:
    cik_int = str(int(cik)) if cik and cik.isdigit() else cik
    return {
        "sec_filings": f"https://www.sec.gov/edgar/browse/?CIK={cik_int}",
        "sec_10k": "https://www.sec.gov/edgar/search/#/dateRange=all&forms=10-K%2C10-Q&entityName="
                   + quote_plus(ticker or name),
        "companyfacts": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
        "usaspending": usaspending_url(name),
        "news": news_url(name, ticker),
    }


def generic_research(name: str, ticker: str | None = None) -> dict:
    return {"usaspending": usaspending_url(name), "news": news_url(name, ticker)}


def normalized_issuer_key(name: str) -> str:
    text = re.sub(r"&", " and ", unicodedata.normalize("NFKD", name.lower()))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(
        r"\b(s\.?a\.?|sa|inc|corp|corporation|company|co|holding|holdings|plc|nv|limited|ltd|adr|ads|class|preferred|pref|ord|pn|on)\b",
        " ",
        text,
    )
    tokens = [
        tok
        for tok in re.sub(r"[^a-z0-9]+", " ", text).split()
        if tok and tok not in {"da", "de", "del", "do", "the", "y"}
    ]
    return " ".join(sorted(dict.fromkeys(tokens)))


def looks_like_exchange_hq(value: str | None) -> bool:
    return str(value or "").strip() in EXCHANGE_HQ_STUBS


def security_profile(node: dict) -> tuple[str, str] | None:
    name = str(node.get("n", "")).strip()
    sub = str(node.get("sub", "")).strip()
    sector = str(node.get("sector", "")).strip()
    text = " ".join(part for part in (name, sub, sector, str(node.get("t", ""))) if part).lower()

    if not name:
        return None
    if "real estate investment trust" in text or "reit" in text:
        return None
    if "blank checks" in text or re.search(r"\bacquisition corp\b", name, re.I) or re.search(r"\bspac\b", text):
        return "spac", SECURITY_TYPE_GROUPS["spac"]
    if "american depositary receipts" in text or re.search(r"/adr\b", name, re.I) or re.search(r"\badr\b", text):
        return "adr", SECURITY_TYPE_GROUPS["adr"]
    if re.search(r"\betf\b", text):
        return "etf", SECURITY_TYPE_GROUPS["etf"]
    if any(
        re.search(pattern, name, re.I)
        for pattern in (
            r"\bwarrant(s)?\b",
            r"\bright(s)?\b",
            r"\bunit(s)?\b",
            r"\bpreferred securities\b",
            r"\bpreferred income\b",
        )
    ):
        if re.search(r"\brightmove\b", name, re.I):
            return None
        if re.search(r"\bright(s)\b", name, re.I):
            return "right", SECURITY_TYPE_GROUPS["right"]
        if re.search(r"\bunit(s)?\b", name, re.I):
            return "unit", SECURITY_TYPE_GROUPS["unit"]
        if re.search(r"\bwarrant(s)?\b", name, re.I):
            return "warrant", SECURITY_TYPE_GROUPS["warrant"]
        return "preferred", SECURITY_TYPE_GROUPS["preferred"]
    if re.search(r"\bfund\b", name, re.I) or (
        "trust" in text
        and not any(marker in text for marker in ("real estate investment trust", "reit", "bank", "insurance"))
    ) or any(marker in text for marker in (
        "closed-end fund",
        "preferred & income",
        "tax-managed",
        "tax-advantaged",
        "buy-write",
        "dynamic income",
        "high income",
        "municipal income",
        "municipal credit",
        "convertible & income",
        "strategic opportunities",
        "enhanced equity",
        "floating rate income",
        "energy infrastructure fund",
        "real assets income",
        "infrastructure income",
        "science & technology trust",
        "health sciences term trust",
        "capital allocation term trust",
        "premium dividend",
        "dividend income",
        "yield opportunities",
        "income strategy",
        "multi-sector income",
        "bond fund",
        "bond trust",
        "municipal bond trust",
        "royalty trust",
        "physical gold trust",
        "physical silver trust",
        "physical platinum trust",
        "physical palladium trust",
    )):
        return "fund", SECURITY_TYPE_GROUPS["fund"]
    if any(marker in text for marker in ("asset-backed securities", "depository receipts")):
        return "debt", SECURITY_TYPE_GROUPS["debt"]
    if "trust" in text and any(marker in text for marker in ("physical", "royalty", "income", "dividend", "municipal", "preferred", "bond", "term", "opportunities", "strategy", "capital allocation")):
        return "trust", SECURITY_TYPE_GROUPS["trust"]
    return None


def listing_security_profile(anchor: dict, listing: dict, exchange: str) -> tuple[str, str]:
    profile = security_profile(listing)
    if profile:
        return profile
    ticker = str(listing.get("t") or listing.get("id") or "").upper()
    if anchor.get("country") != "United States" and (exchange in {"NYSE", "Nasdaq", "CBOE"} or ticker.endswith("Y")):
        return "adr", SECURITY_TYPE_GROUPS["adr"]
    return "security", SECURITY_TYPE_GROUPS["security"]


def sic_to_sector(sic) -> str:
    if not sic:
        return "Other"
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return "Other"
    if 4900 <= s <= 4999: return "Utilities"
    if 6500 <= s <= 6599: return "Real Estate"
    if 6000 <= s <= 6499 or 6700 <= s <= 6799: return "Financials"
    if s in (2834, 2835, 2836) or 3840 <= s <= 3851 or 8000 <= s <= 8099 or s == 8731:
        return "Health Care"
    if 3570 <= s <= 3579 or 3670 <= s <= 3679 or 7370 <= s <= 7379 or 3661 <= s <= 3669 or 3820 <= s <= 3827:
        return "Information Technology"
    if 4800 <= s <= 4899 or 2700 <= s <= 2799 or 7800 <= s <= 7899 or 4830 <= s <= 4841:
        return "Communication Services"
    if 1200 <= s <= 1399 or 2900 <= s <= 2999:
        return "Energy"
    if 1000 <= s <= 1099 or 1400 <= s <= 1499 or 2600 <= s <= 2699 or 2800 <= s <= 2824 or 2840 <= s <= 2899 or 3300 <= s <= 3399 or 2400 <= s <= 2499 or 1040 <= s <= 1049:
        return "Materials"
    if 2000 <= s <= 2199 or 5400 <= s <= 5499 or s == 5912:
        return "Consumer Staples"
    if 3700 <= s <= 3799 or 2300 <= s <= 2399 or 5000 <= s <= 5199 or 5200 <= s <= 5399 or 5600 <= s <= 5999 or 7000 <= s <= 7099 or s == 5812 or 3630 <= s <= 3652:
        return "Consumer Discretionary"
    if 1500 <= s <= 1799 or 3400 <= s <= 3569 or 3580 <= s <= 3599 or 3710 <= s <= 3729 or 4000 <= s <= 4799 or 7300 <= s <= 7369 or 3600 <= s <= 3629:
        return "Industrials"
    return "Other"


def load_sp500() -> dict:
    m = {}
    if SP500_CSV.exists():
        for row in csv.DictReader(SP500_CSV.open()):
            m[row["Symbol"].strip().replace(".", "-")] = {
                "sector": row["GICS Sector"].strip(),
                "sub": row["GICS Sub-Industry"].strip(),
                "hq": row["Headquarters Location"].strip(),
                "f": row["Founded"].strip(),
            }
    elif OUT.exists():
        for n in json.load(OUT.open()).get("nodes", []):
            if n.get("id") and n.get("f"):
                m[n["id"]] = {"sector": n["sector"], "sub": n["sub"], "hq": n["hq"], "f": n["f"]}
    return m


def load_tickers() -> dict:
    if TICKERS.exists():
        return json.load(TICKERS.open())
    try:
        req = Request(SEC_TICKERS_URL, headers={"User-Agent": UA})
        try:
            text = urlopen(req, timeout=30).read().decode("utf-8")
        except Exception as exc:
            if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
                raise
            import certifi

            ctx = ssl.create_default_context(cafile=certifi.where())
            text = urlopen(req, timeout=30, context=ctx).read().decode("utf-8")
        data = json.loads(text)
        TICKERS.write_text(json.dumps(data))
        return data
    except Exception as exc:
        if OUT.exists():
            print(f"  using existing universe ticker fallback: {exc}")
            rows = {}
            for i, n in enumerate(json.load(OUT.open()).get("nodes", [])):
                cik = str(n.get("cik") or "")
                if n.get("kind") in {"public", "security"} and cik.isdigit():
                    rows[str(i)] = {"ticker": n["id"], "cik_str": int(cik), "title": n["n"]}
            return rows
        raise


def source_sector(value) -> str:
    raw = str(value or "").strip()
    return sic_to_sector(raw) if raw.isdigit() else raw


def lookup_record(mapping: dict, *keys: str) -> dict | None:
    for key in keys:
        if key and key in mapping:
            return mapping[key]
    return None


def has_any(text: str, *needles: str) -> bool:
    return any(n in text for n in needles)


def company_group(node: dict) -> str:
    sector = node.get("sector", "")
    text = " ".join(str(node.get(k, "")) for k in ("n", "t", "sector", "sub")).lower()
    ticker = str(node.get("t", "")).upper()

    if node.get("kind") == "security":
        return node.get("security_type_group") or SECURITY_TYPE_GROUPS.get(str(node.get("security_type") or ""), "Listed securities")
    if node.get("kind") == "government":
        return "Government agencies"
    if node.get("kind") == "legacy":
        return "Historical / defunct entities"
    if ticker in {"NVDA", "AMD", "AVGO", "INTC", "QCOM", "ARM", "TSM", "ASML", "MU", "AMAT", "LRCX", "ADI", "TXN", "MRVL", "ON", "SMCI", "PLTR", "AI"} or has_any(text, "semiconductor", "memory", "dram", "nand", "flash", "artificial intelligence", "machine learning"):
        return "AI & semiconductors"
    if ticker in {"MSFT", "ORCL", "CRM", "NOW", "SNOW", "DDOG", "MDB", "NET", "IBM"} or has_any(text, "prepackaged software", "application software", "systems software", "cloud", "data processing", "computer programming"):
        return "Cloud & software"
    if has_any(text, "computer integrated systems", "it consulting", "information technology services", "computer processing"):
        return "IT services & consulting"
    if has_any(text, "computer peripheral", "communications equipment", "electronic components", "electronic computers", "hardware"):
        return "Hardware & communications equipment"

    if sector == "Financials":
        if has_any(text, "blank checks"):
            return "SPACs & holding companies"
        if has_any(text, "real estate investment trust", "reit"):
            return "REITs & real estate finance"
        if has_any(text, "insurance", "casualty", "life", "fire", "marine"):
            return "Insurance"
        if has_any(text, "asset management", "investment advice", "finance services", "custody", "investment"):
            return "Asset management & advisory"
        if has_any(text, "bank", "credit", "savings", "loan", "mortgage"):
            return "Banks & credit"
        if has_any(text, "payment", "exchange", "broker", "dealer", "commodity contracts", "securities"):
            return "Exchanges, brokers & payments"
        return "Financial services"

    if sector == "Health Care":
        if has_any(text, "pharmaceutical", "biological", "biotech", "diagnostic substances"):
            return "Pharma & biotech"
        if has_any(text, "surgical", "medical instruments", "apparatus", "analytical instruments"):
            return "Medical devices & tools"
        return "Health providers & services"
    if sector == "Communication Services":
        if has_any(text, "telephone", "telecom", "radiotelephone", "cable", "satellite"):
            return "Telecom & connectivity"
        if has_any(text, "interactive", "internet", "platform"):
            return "Internet & digital platforms"
        return "Media & entertainment"
    if sector == "Industrials":
        if has_any(text, "aerospace", "defense"):
            return "Aerospace & defense"
        if has_any(text, "transportation", "freight", "cargo", "trucking", "air transportation", "water transportation"):
            return "Transport & logistics"
        if has_any(text, "construction", "contractors", "engineering"):
            return "Construction & engineering"
        if has_any(text, "machinery", "equipment", "turbines", "industrial"):
            return "Industrial machinery & equipment"
        return "Industrial services"
    if sector == "Energy":
        if has_any(text, "pipeline", "field machinery", "equipment"):
            return "Energy equipment & pipelines"
        return "Energy producers"
    if sector == "Materials":
        return "Metals, mining & chemicals"
    if sector == "Utilities":
        return "Utilities"
    if sector == "Real Estate":
        return "Real estate operators"
    if sector == "Consumer Staples":
        return "Food, beverage & staples"
    if sector == "Consumer Discretionary":
        if has_any(text, "auto", "motor", "vehicle"):
            return "Autos & mobility"
        if has_any(text, "restaurant", "hotel", "travel", "leisure", "entertainment"):
            return "Restaurants, travel & leisure"
        if has_any(text, "retail", "e-commerce", "catalog", "stores"):
            return "Consumer retail & ecommerce"
        return "Consumer products & apparel"
    if has_any(text, "management consulting", "business services", "advertising", "help supply"):
        return "Consulting & professional services"
    if has_any(text, "educational services"):
        return "Education & other services"
    return "Other"


def canonical_node_type(node: dict) -> str:
    kind = node.get("kind") or "public"
    if kind == "security":
        sec_type = node.get("security_type") or "security"
        if sec_type in {"etf", "fund", "trust"}:
            return "fund"
        if sec_type in {"warrant", "right", "unit"}:
            return "warrant"
        return "security"
    if kind == "government":
        return "counterparty"
    return "company"


def node_source_confidence(node: dict) -> float:
    score = 0.52
    cik = str(node.get("cik") or "")
    research = node.get("research") or {}
    if cik and cik != "—":
        score += 0.2
    if research.get("sec_filings") or research.get("website"):
        score += 0.12
    if node.get("exchange"):
        score += 0.05
    if node.get("country"):
        score += 0.05
    if node.get("kind") == "security" and node.get("security_type"):
        score += 0.05
    return round(min(0.98, max(0.35, score)), 2)


def node_location_confidence(node: dict) -> float:
    hq = str(node.get("hq") or "").strip()
    country = str(node.get("country") or "").strip()
    if looks_like_exchange_hq(hq) or hq in {"", "—", "-", "N/A"}:
        return 0.2 if country else 0.1
    if country and hq and hq.lower() != country.lower():
        return 0.68
    return 0.45 if country else 0.25


def apply_canonical_entity_model(node: dict) -> None:
    node_type = canonical_node_type(node)
    source_conf = node_source_confidence(node)
    loc_conf = node_location_confidence(node)
    node["node_type"] = node_type
    node["source_confidence"] = source_conf
    node["location_confidence"] = loc_conf
    node["entity_model"] = {
        "schema_version": 1,
        "canonical_id": node.get("canonical_id") or node.get("id"),
        "entity_type": node_type,
        "security_type": node.get("security_type") if node.get("kind") == "security" else "",
        "issuer_id": node.get("issuer_id", ""),
        "location": {
            "raw": node.get("hq", ""),
            "country": node.get("country", ""),
            "confidence": loc_conf,
        },
        "source_confidence": source_conf,
    }


def source_node(rec: dict) -> dict:
    missing = [k for k in SOURCE_REQUIRED if not str(rec.get(k, "")).strip()]
    if missing:
        raise ValueError("missing " + ", ".join(missing))
    canonical_id = resolve_id(rec["canonical_id"])
    name = str(rec["name"]).strip()
    sector = source_sector(rec["sector_or_sic"])
    ticker = str(rec.get("ticker") or canonical_id.split(":")[-1]).strip()
    kind = str(rec.get("kind") or "public").strip()
    node = {"id": canonical_id, "canonical_id": canonical_id, "n": name, "t": ticker,
            "sec": short_key(sector), "sector": sector, "sub": rec.get("sub") or str(rec["sector_or_sic"]),
            "hq": rec.get("hq") or rec["country"], "cik": str(rec.get("cik") or "—"),
            "f": str(rec.get("f") or ""), "kind": kind, "status": rec.get("status", "active"),
            "country": rec["country"], "exchange": rec["exchange"],
            "research": generic_research(name, ticker)}
    if rec.get("website"):
        node["research"]["website"] = str(rec["website"]).strip()
    if isinstance(rec.get("research"), dict):
        node["research"].update({k: v for k, v in rec["research"].items() if v not in (None, "", "—")})
    if isinstance(rec.get("price"), dict) and rec["price"].get("price") is not None:
        node["price"] = rec["price"]
    if rec.get("quote_symbol"):
        node["quote_symbol"] = str(rec["quote_symbol"]).strip()
    if kind == "public":
        sec_profile = security_profile(node)
        if sec_profile:
            kind = node["kind"] = "security"
            node["security_type"], node["security_type_group"] = sec_profile
    if kind == "private" or rec.get("private"):
        node["private"] = True
    if rec.get("lei"):
        node["lei"] = str(rec["lei"]).strip()
    if rec.get("hq_force"):
        node["_hq_force"] = True
    if rec.get("f_force"):
        node["_f_force"] = True
    if rec.get("sub_force"):
        node["_sub_force"] = True
    if rec.get("sector_force"):
        node["_sector_force"] = True
    return node


def load_source_nodes(source_dir: Path = SOURCES) -> list[dict]:
    nodes = []
    if not source_dir.exists():
        return nodes
    for path in sorted(source_dir.glob("*.jsonl")):
        for lineno, raw in enumerate(path.read_text().splitlines(), 1):
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            try:
                nodes.append(source_node(json.loads(raw)))
            except (json.JSONDecodeError, ValueError) as exc:
                print(f"  skipped {path.name}:{lineno}: {exc}")
    return nodes


def merge_source_nodes(nodes: list[dict], source_dir: Path = SOURCES) -> list[dict]:
    by_canon = {n["canonical_id"]: n for n in nodes}
    prices = json.load(PRICES.open()) if PRICES.exists() else {}
    for node in load_source_nodes(source_dir):
        if "price" not in node:
            price_record = lookup_record(prices, node["id"], node["canonical_id"], node.get("quote_symbol", ""), node.get("t", ""))
            if price_record and price_record.get("price") is not None:
                node["price"] = price_record
        force_hq = bool(node.pop("_hq_force", False))
        force_f = bool(node.pop("_f_force", False))
        force_sub = bool(node.pop("_sub_force", False))
        force_sector = bool(node.pop("_sector_force", False))
        existing = by_canon.get(node["canonical_id"])
        if existing:
            if existing["n"] != node["n"]:
                print(f"  source collision {node['canonical_id']}: {existing['n']} vs {node['n']}")
            for k, v in node.items():
                if k == "research" and isinstance(v, dict):
                    existing.setdefault("research", {})
                    existing["research"].update({rk: rv for rk, rv in v.items() if rv not in (None, "", "—")})
                    continue
                if k == "price" and isinstance(v, dict) and v.get("price") is not None:
                    existing[k] = v
                    continue
                if k == "kind" and existing.get(k) == "public" and v != "public":
                    existing[k] = v
                elif k == "private" and v:
                    existing[k] = v
                elif k == "hq" and force_hq and v not in (None, "", "—"):
                    existing[k] = v
                elif k == "f" and force_f and v not in (None, "", "—"):
                    existing[k] = v
                elif k == "sub" and force_sub and v not in (None, "", "—"):
                    existing[k] = v
                elif k in ("sec", "sector") and force_sector and v not in (None, "", "—"):
                    existing[k] = v
                elif k == "hq" and existing.get(k) in ("Nasdaq", "NYSE", "OTC", "—") and v not in (None, "", "—"):
                    existing[k] = v
                elif k == "sub" and existing.get(k) in ("Semiconductors", "Semiconductors & Related Devices", "Services-Computer Programming, Data Processing, Etc.", "—") and v not in (None, "", "—"):
                    existing[k] = v
                elif existing.get(k) in (None, "", "—") and v not in (None, "", "—"):
                    existing[k] = v
            continue
        nodes.append(node)
        by_canon[node["canonical_id"]] = node
    return nodes


def build_nodes() -> list[dict]:
    tickers = load_tickers()
    cache = json.load(CACHE.open()) if CACHE.exists() else {}
    filings = json.load(FILINGS.open()) if FILINGS.exists() else {}
    prices = json.load(PRICES.open()) if PRICES.exists() else {}
    sp = load_sp500()
    nodes = []
    for row in tickers.values():
        t = row["ticker"].strip()
        cik = str(row["cik_str"]).zfill(10)
        info = cache.get(cik, {})
        if t in sp:
            sector = sp[t]["sector"]; sub = sp[t]["sub"]; hq = sp[t]["hq"]; f = sp[t]["f"]
        else:
            sector = sic_to_sector(info.get("sic"))
            sub = info.get("sicDescription") or "—"; hq = info.get("exchange") or "—"; f = ""
        name = row["title"].strip()
        node = {"id": t, "canonical_id": t, "n": name, "t": t, "sec": short_key(sector),
                "sector": sector, "sub": sub, "hq": hq, "cik": cik, "f": f,
                "kind": "public", "status": "active",
                "research": sec_research(cik, t, name)}
        sec_profile = security_profile(node)
        if sec_profile:
            node["kind"] = "security"
            node["security_type"], node["security_type_group"] = sec_profile
        if filings.get(t):
            node["filings"] = filings[t]
        price_record = lookup_record(prices, t, node["id"], node["canonical_id"])
        if price_record and price_record.get("price") is not None:
            node["price"] = price_record
        nodes.append(node)
    for p in json.load(CURATED_NODES.open()):
        node = {"id": p["id"], "canonical_id": p["id"], "n": p["n"], "t": p["t"], "sec": short_key(p["sector"]),
                "sector": p["sector"], "sub": p["sub"], "hq": p["hq"], "cik": "—",
                "f": p["f"], "kind": p["kind"], "status": p.get("status", "active"),
                "research": generic_research(p["n"])}
        if p.get("private"):
            node["private"] = True
        if p.get("end_date"):
            node["end_date"] = p["end_date"]
        nodes.append(node)
    return merge_source_nodes(nodes)


def normalize_link(raw) -> dict:
    if isinstance(raw, dict):
        rec = dict(raw)
    else:
        a, b, rel, src, val, detail = raw
        rec = {"from": a, "to": b, "rel": rel, "src": src, "val": val, "detail": detail}
    rec["from"] = resolve_id(rec["from"])
    rec["to"] = resolve_id(rec["to"])
    rec.setdefault("val", 0.0)
    rec.setdefault("confidence", 0.75 if rec["val"] else 0.65)
    rec.setdefault("as_of", date.today().isoformat())
    return rec


def edge_key(rec: dict) -> str:
    return "|".join(str(rec.get(k, "")).strip() for k in ("from", "rel", "to", "source_url"))


def has_edge_evidence(rec: dict) -> bool:
    return all(rec.get(k) not in (None, "", "—") for k in ("source_url", "src", "detail", "confidence")) and bool(rec.get("as_of") or rec.get("start"))


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.load(path.open())
    except json.JSONDecodeError:
        print(f"  ignored invalid JSON: {path}")
        return fallback


def confirmed_candidate_links() -> list[dict]:
    rejected = {edge_key(r) for r in load_json(REJECTED_EDGES, [])}
    out = []
    for raw in load_json(EDGE_CANDIDATES, []):
        if raw.get("status") != "confirmed" or edge_key(raw) in rejected:
            continue
        if not has_edge_evidence(raw):
            print(f"  skipped confirmed edge without evidence: {raw.get('from')}->{raw.get('to')}")
            continue
        out.append(raw)
    return out


def listing_bridge_links(nodes: list[dict]) -> list[dict]:
    local_by_key: dict[str, list[dict]] = {}
    external_by_key: dict[str, list[dict]] = {}
    for node in nodes:
        key = normalized_issuer_key(node.get("n", ""))
        if not key:
            continue
        if node.get("country") and node.get("exchange") and not looks_like_exchange_hq(node.get("hq")):
            local_by_key.setdefault(key, []).append(node)
        elif not node.get("country") and looks_like_exchange_hq(node.get("hq")):
            external_by_key.setdefault(key, []).append(node)

    links = []
    seen = set()
    for key, externals in external_by_key.items():
        locals_ = local_by_key.get(key)
        if not locals_:
            continue
        locals_.sort(
            key=lambda n: (
                n.get("kind") != "public",
                not n.get("research", {}).get("website"),
                n.get("exchange", ""),
                n.get("id", ""),
            )
        )
        anchor = locals_[0]
        anchor_url = anchor.get("research", {}).get("website") or anchor.get("research", {}).get("quote") or ""
        for ext in externals:
            stub_exchange = ext.get("exchange") or (ext.get("hq") if looks_like_exchange_hq(ext.get("hq")) else "")
            if not ext.get("country") and anchor.get("country"):
                ext["country"] = anchor["country"]
            if ext.get("hq") in (None, "", "—") or looks_like_exchange_hq(ext.get("hq")):
                ext["hq"] = anchor.get("hq") or ext.get("hq")
            if not ext.get("exchange") and stub_exchange:
                ext["exchange"] = stub_exchange
            ext["kind"] = "security"
            ext["security_type"], ext["security_type_group"] = listing_security_profile(anchor, ext, stub_exchange)
            ext["issuer_id"] = anchor["id"]
            if anchor.get("research", {}).get("website"):
                ext.setdefault("research", {})
                ext["research"].setdefault("website", anchor["research"]["website"])
            edge_id = (anchor["id"], ext["id"])
            if edge_id in seen or anchor["id"] == ext["id"]:
                continue
            seen.add(edge_id)
            links.append(
                {
                    "from": anchor["id"],
                    "to": ext["id"],
                    "rel": "same_issuer",
                    "src": "Generated issuer bridge",
                    "source_url": anchor_url,
                    "val": 0.0,
                    "detail": f"Same issuer across {anchor.get('exchange', 'local')} and {stub_exchange or 'foreign'} listings",
                    "confidence": 0.93,
                    "as_of": date.today().isoformat(),
                }
            )
    return links


def generated_contract_links() -> list[dict]:
    if not GOV_CONTRACTS.exists():
        return []
    try:
        data = json.load(GOV_CONTRACTS.open())
    except json.JSONDecodeError:
        print(f"  ignored invalid generated contracts file: {GOV_CONTRACTS}")
        return []
    return data.get("links", [])


def fallback_contract_links() -> list[dict]:
    if not GOV_CONTRACT_QUERIES.exists():
        return []
    return [{
        "from": q["agency_id"],
        "to": q["recipient_id"],
        "rel": "contracts",
        "src": "USAspending API; run refresh_gov_contracts.py",
        "source_url": USASPENDING_API_URL,
        "val": 0.0,
        "detail": q.get("detail", "Government contract exposure; refresh for current federal FY obligations"),
        "start": q.get("start"),
        "confidence": q.get("confidence", 0.9),
    } for q in json.load(GOV_CONTRACT_QUERIES.open())]


def curated_links() -> list[dict]:
    by_key = {}
    for raw in json.load(CURATED_LINKS.open()):
        rec = normalize_link(raw)
        by_key[(rec["from"], rec["rel"], rec["to"])] = rec
    for raw in fallback_contract_links():
        rec = normalize_link(raw)
        by_key[(rec["from"], rec["rel"], rec["to"])] = rec
    for raw in generated_contract_links():
        rec = normalize_link(raw)
        by_key[(rec["from"], rec["rel"], rec["to"])] = rec
    for raw in confirmed_candidate_links():
        rec = normalize_link(raw)
        by_key[(rec["from"], rec["rel"], rec["to"])] = rec
    return list(by_key.values())


def validate(node_ids: set, extra_links: list[dict] | None = None) -> list[dict]:
    kept = []
    for rec in curated_links() + list(extra_links or []):
        a, b = rec["from"], rec["to"]
        if a in node_ids and b in node_ids:
            kept.append(rec)
        else:
            print(f"  DROPPED {a}->{b}: not in node set")
    return kept


def prices_as_of() -> str | None:
    if not PRICES.exists():
        return None
    try:
        prices = json.load(PRICES.open())
    except json.JSONDecodeError:
        return None
    dates = [v.get("as_of") for v in prices.values() if isinstance(v, dict) and v.get("as_of")]
    return max(dates) if dates else None


def _strip_payload(node: dict) -> dict:
    """Remove derivable research URLs and empty entity_model fields from payload nodes."""
    n = dict(node)
    # research URLs are derivable client-side from CIK/ticker
    n.pop("research", None)
    # strip empty-string values from entity_model
    em = n.get("entity_model")
    if isinstance(em, dict):
        cleaned = {}
        for k, v in em.items():
            if isinstance(v, dict):
                sub = {sk: sv for sk, sv in v.items() if sv not in ("", None)}
                if sub:
                    cleaned[k] = sub
            elif v not in ("", None):
                cleaned[k] = v
        n["entity_model"] = cleaned
    return n


def split_graph(graph: dict) -> tuple[dict, dict]:
    core_nodes = [n for n in graph["nodes"] if n.get("deg", 0) > 0]
    bulk_nodes = [_strip_payload(n) for n in graph["nodes"] if n.get("deg", 0) == 0]
    core = dict(graph)
    core["meta"] = dict(graph["meta"], core_companies=len(core_nodes), bulk_companies=len(bulk_nodes))
    core["nodes"] = core_nodes
    bulk = {"meta": {"companies": len(bulk_nodes), "built_at": graph["meta"]["built_at"]}, "nodes": bulk_nodes}
    return core, bulk



def layout(nodes: list[dict]) -> None:
    by_sector = {}
    for n in nodes:
        by_sector.setdefault(n["sector"], []).append(n)
    sectors = sorted(by_sector)
    cluster_r = {s: 13 * math.sqrt(len(by_sector[s])) + 30 for s in sectors}
    ring = max(1500.0, max(cluster_r.values()) * 2.4)
    cx, cy = ring + 200, ring + 200
    GA = math.pi * (3 - math.sqrt(5))
    for i, s in enumerate(sectors):
        a = (i / len(sectors)) * 2 * math.pi
        scx, scy = cx + math.cos(a) * ring, cy + math.sin(a) * ring
        members = by_sector[s]
        n = len(members)
        cr = cluster_r[s]
        for j, node in enumerate(members):
            rr = cr * math.sqrt((j + 0.5) / n)
            th = j * GA
            node["x"] = round(scx + rr * math.cos(th), 1)
            node["y"] = round(scy + rr * math.sin(th), 1)


def main() -> None:
    nodes = build_nodes()
    bridge_links = listing_bridge_links(nodes)
    ids = {n["id"] for n in nodes}
    links = validate(ids, bridge_links)

    deg = {n["id"]: 0 for n in nodes}
    for l in links:
        deg[l["from"]] += 1; deg[l["to"]] += 1
    for n in nodes:
        n["deg"] = deg[n["id"]]
        n["group"] = company_group(n)
        n["grp"] = group_key(n["group"])
        apply_canonical_entity_model(n)

    layout(nodes)

    sectors = {}
    groups = {}
    for n in nodes:
        sectors.setdefault(n["sec"], {"name": n["sector"], "color": COLORS.get(n["sector"], "#6b7682")})
        groups.setdefault(n["grp"], {"name": n["group"], "color": COLORS.get(n["sector"], "#6b7682")})

    classified = sum(1 for n in nodes if n["sector"] != "Other")
    kinds = {}
    for n in nodes:
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
    contracts_as_of = None
    if GOV_CONTRACTS.exists():
        try:
            contracts_as_of = json.load(GOV_CONTRACTS.open()).get("generated_at")
        except json.JSONDecodeError:
            pass
    graph = {
        "meta": {"companies": len(nodes), "links": len(links), "classified": classified,
                 "kinds": kinds,
                 "built_at": date.today().isoformat(),
                 "contracts_as_of": contracts_as_of,
                 "prices_as_of": prices_as_of(),
                 "generated_contracts_loaded": GOV_CONTRACTS.exists(),
                 "source": "SEC US public companies; S&P 500 = GICS, others = SIC-derived (approx); curated cited relationships and generated overlays"},
        "sectors": sectors, "groups": groups, "rels": REL_DEFS, "nodes": nodes, "links": links,
    }
    core, bulk = split_graph(graph)
    OUT.write_text(json.dumps(graph))
    OUT_CORE.write_text(json.dumps(core))
    OUT_BULK.write_text(json.dumps(bulk))
    write_map_geojson(graph)
    print(f"Wrote {len(nodes)} companies ({classified} sector-classified), {len(links)} links -> {OUT}")
    print(f"Wrote {len(core['nodes'])} core nodes -> {OUT_CORE}")
    print(f"Wrote {len(bulk['nodes'])} bulk nodes -> {OUT_BULK}")


if __name__ == "__main__":
    main()
