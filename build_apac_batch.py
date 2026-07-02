from __future__ import annotations

import csv
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()

ROOT = Path(__file__).parent
SOURCES = ROOT / "graph" / "data" / "sources"
ASX_OUT = SOURCES / "australia_batch_2026_07.jsonl"
NZX_OUT = SOURCES / "new_zealand_batch_2026_07.jsonl"
UA = {"User-Agent": "Mozilla/5.0"}
NZ_LOCALITY_ALIASES = [
    ("auckland airport manukau", "Auckland"),
    ("shortland street auckland", "Auckland"),
    ("wellesley street auckland", "Auckland"),
    ("victoria street west auckland", "Auckland"),
    ("south auckland auckland", "Auckland"),
    ("panmure auckland", "Auckland"),
    ("parnell auckland", "Auckland"),
    ("newmarket auckland", "Auckland"),
    ("te aro wellington", "Wellington"),
    ("the terrace wellington", "Wellington"),
    ("wellington central", "Wellington"),
    ("te puke", "Te Puke"),
    ("lower hutt", "Lower Hutt"),
    ("christchurch", "Christchurch"),
    ("invercargill", "Invercargill"),
    ("new plymouth", "New Plymouth"),
    ("wellington", "Wellington"),
    ("auckland", "Auckland"),
    ("dunedin", "Dunedin"),
    ("tauranga", "Tauranga"),
    ("hamilton", "Hamilton"),
    ("whangarei", "Whangarei"),
    ("marlborough", "Marlborough"),
    ("takapuna", "Auckland"),
    ("bluff", "Bluff"),
    ("ruatoria", "Ruatoria"),
    ("rakaia", "Rakaia"),
    ("napier", "Napier"),
    ("nelson", "Nelson"),
]


def fetch_json(url: str, *, verify: bool = True) -> dict | list:
    response = requests.get(url, headers=UA, timeout=30, verify=verify)
    response.raise_for_status()
    return response.json()


def fetch_text(url: str, *, verify: bool = True) -> str:
    response = requests.get(url, headers=UA, timeout=30, verify=verify)
    response.raise_for_status()
    return response.text


def clean(text: str | None) -> str:
    return " ".join(str(text or "").replace("\n", " ").replace("\xa0", " ").split()).strip()


def ensure_url(value: str | None) -> str:
    text = clean(value)
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        return text
    return "https://" + text.lstrip("/")


def broad_sector(text: str) -> str:
    lower = clean(text).lower()
    if any(token in lower for token in ("bank", "financial", "insurance", "capital markets", "diversified financials")):
        return "Financials"
    if any(token in lower for token in ("pharma", "biotech", "health", "medical", "life sciences", "biotechnology")):
        return "Health Care"
    if any(token in lower for token in ("software", "technology", "semiconductor", "electronic", "it services", "communications equipment")):
        return "Information Technology"
    if any(token in lower for token in ("media", "telecommunication", "entertainment", "interactive")):
        return "Communication Services"
    if any(token in lower for token in ("oil", "gas", "energy", "coal", "uranium")):
        return "Energy"
    if any(token in lower for token in ("utility", "utilities", "water", "electric")):
        return "Utilities"
    if any(token in lower for token in ("real estate", "reit", "property")):
        return "Real Estate"
    if any(token in lower for token in ("food", "beverage", "staples", "grocery", "agric", "tobacco")):
        return "Consumer Staples"
    if any(token in lower for token in ("retail", "apparel", "consumer services", "automobile", "leisure", "travel", "hospitality", "media")):
        return "Consumer Discretionary"
    if any(token in lower for token in ("material", "mining", "metals", "chemical", "paper", "forest", "construction materials")):
        return "Materials"
    if any(token in lower for token in ("capital goods", "transportation", "commercial", "professional services", "industrial", "engineering")):
        return "Industrials"
    return "Other"


def australia_city(address: str) -> tuple[str, str]:
    raw = clean(address)
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    country = "Australia"
    if not parts:
        return country, country
    upper_parts = [part.upper() for part in parts]
    if "AUSTRALIA" in upper_parts:
        country = "Australia"
    else:
        for part in reversed(parts):
            alpha = re.sub(r"[^A-Za-z ]+", "", part).strip()
            if alpha:
                country = alpha.title()
                break
    candidates = parts[:-1] if parts else []
    for part in reversed(candidates):
        upper = part.upper()
        if upper == "AUSTRALIA":
            continue
        token = re.sub(r"\b\d{3,5}\b", "", part).strip(" -")
        if not token:
            continue
        if upper in {"NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"}:
            continue
        city = token.title()
        return f"{city}, {country}", country
    return country, country


def nz_city(address: str) -> tuple[str, str]:
    raw = clean(address.replace(",", ", "))
    lower = raw.lower()
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    upper = raw.upper()
    if any(token in upper for token in (" NSW ", " VIC ", " QLD ", " WA ", " TAS ", " ACT ", " SA ", "MELBOURNE", "SYDNEY", "BRISBANE", "PERTH", "ADELAIDE")):
        country = "Australia"
    else:
        country = "New Zealand"
    if not parts:
        return country, country
    for needle, city in NZ_LOCALITY_ALIASES:
        if needle in lower:
            return f"{city}, {country}", country
    for part in reversed(parts):
        token = re.sub(r"\b\d{3,5}\b", "", part).strip(" -")
        if token and token.lower() not in {"new zealand", "nz", "po box", "australia"}:
            return f"{token.title()}, {country}", country
    return country, country


def parse_nzx_page(code: str) -> dict:
    html = fetch_text(f"https://www.nzx.com/companies/{code}")
    soup = BeautifulSoup(html, "html.parser")
    payload = soup.find("script", id="__NEXT_DATA__")
    if not payload or not payload.string:
        raise ValueError(f"missing __NEXT_DATA__ for {code}")
    page_props = json.loads(payload.string)["props"]["pageProps"]
    instruments = page_props.get("companyInstruments") or []
    listed = next((row for row in instruments if row.get("marketType") == "NZSX"), instruments[0] if instruments else {})
    snapshot_rows = page_props.get("companyInstrumentsSnapshotData") or []
    snapshot = next((row for row in snapshot_rows if row.get("code") == code), snapshot_rows[0] if snapshot_rows else {})
    contact = page_props.get("companyContact") or {}
    summary = page_props.get("companySummaryData") or {}
    registered_name = clean(page_props.get("companyName") or listed.get("name") or page_props.get("companyId"))
    hq, country = nz_city(contact.get("rawAddress", ""))
    price_amount = clean(snapshot.get("priceAmount"))
    price = None
    if price_amount and re.fullmatch(r"-?\d+(?:\.\d+)?", price_amount):
        price = {
            "as_of": "2026-06-30",
            "price": float(price_amount),
            "source": "NZX",
            "symbol": code,
        }
    record = {
        "canonical_id": f"NZX:{code}",
        "name": registered_name,
        "country": country,
        "exchange": "NZX",
        "sector_or_sic": broad_sector(" ".join(filter(None, [registered_name, listed.get("name"), clean(contact.get("websiteURL"))]))),
        "ticker": code,
        "sub": clean(listed.get("name") or registered_name),
        "hq": hq,
        "quote_symbol": f"{code}.NZ",
        "research": {
            "exchange_profile": f"https://www.nzx.com/companies/{code}",
            "website": ensure_url(contact.get("websiteURL")),
            "raw_address": clean(contact.get("rawAddress")),
        },
        "website": ensure_url(contact.get("websiteURL")),
        "f": clean(summary.get("firstListedDate", ""))[:4],
    }
    if price:
        record["price"] = price
    return record


def build_new_zealand() -> list[dict]:
    listed = fetch_json("https://api.nzx.com/public/companies/listed/all.json")
    equity_codes = [row["code"] for row in listed if row.get("code")]
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(parse_nzx_page, code): code for code in equity_codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                rec = future.result()
            except Exception as exc:  # pragma: no cover - network variability
                print("skip nzx", code, exc)
                continue
            if rec["country"] == "New Zealand" and clean(rec.get("name")):
                rows.append(rec)
    rows.sort(key=lambda row: row["ticker"])
    return rows


def normalize_asx_rows(csv_text: str) -> list[tuple[str, str, str]]:
    rows = []
    reader = csv.reader(io.StringIO(csv_text))
    next(reader, None)
    for row in reader:
        if len(row) < 3:
            continue
        name, code, industry_group = (clean(row[0]), clean(row[1]), clean(row[2]))
        if not code or not name:
            continue
        rows.append((name, code, industry_group))
    return rows


def parse_asx(code: str, name: str, industry_group: str) -> dict | None:
    try:
        header = fetch_json(f"https://asx.api.markitdigital.com/asx-research/1.0/companies/{code}/header")
        about = fetch_json(f"https://cdn-api.markitdigital.com/apiman-gateway/ASX/asx-research/1.0/companies/{code}/about?v=undefined")
    except requests.RequestException as exc:  # pragma: no cover - network variability
        print("skip asx", code, exc)
        return None
    header_data = header.get("data") or {}
    about_data = about.get("data") or {}
    address = clean((about_data.get("addressContact") or {}).get("address"))
    hq, country = australia_city(address)
    if country != "Australia":
        return None
    price_last = header_data.get("priceLast")
    price = None
    if isinstance(price_last, (int, float)):
        price = {
            "as_of": "2026-06-30",
            "price": round(float(price_last), 6),
            "source": "ASX",
            "symbol": code,
        }
    record = {
        "canonical_id": f"ASX:{code}",
        "name": clean(header_data.get("displayName") or name),
        "country": country,
        "exchange": "ASX",
        "sector_or_sic": broad_sector(header_data.get("industryGroup") or industry_group),
        "ticker": code,
        "sub": clean(header_data.get("industryGroup") or industry_group),
        "hq": hq,
        "quote_symbol": f"{code}.AX",
        "research": {
            "exchange_profile": f"https://www.asx.com.au/markets/company/{code}",
            "website": ensure_url(about_data.get("websiteUrl")),
            "hq_address": address,
            "description": clean(about_data.get("description")),
        },
        "website": ensure_url(about_data.get("websiteUrl")),
        "f": clean(header_data.get("dateListed", ""))[:4],
    }
    if price:
        record["price"] = price
    return record


def build_australia() -> list[dict]:
    csv_text = fetch_text("https://www.asx.com.au/asx/research/ASXListedCompanies.csv")
    listed = normalize_asx_rows(csv_text)
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {
            pool.submit(parse_asx, code, name, industry_group): code
            for name, code, industry_group in listed
        }
        for future in as_completed(futures):
            rec = future.result()
            if rec:
                rows.append(rec)
            time.sleep(0.05)
    rows.sort(key=lambda row: row["ticker"])
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    australia = build_australia()
    new_zealand = build_new_zealand()
    write_jsonl(ASX_OUT, australia)
    write_jsonl(NZX_OUT, new_zealand)
    print(f"wrote {len(australia)} Australia companies -> {ASX_OUT}")
    print(f"wrote {len(new_zealand)} New Zealand companies -> {NZX_OUT}")


if __name__ == "__main__":
    main()
