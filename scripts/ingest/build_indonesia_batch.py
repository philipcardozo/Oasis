from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "graph" / "data" / "browser_exports" / "idx_profiles_2026_07.ndjson"
OUT = ROOT / "graph" / "data" / "sources" / "indonesia_batch_2026_07.jsonl"
CURATED_LINKS = ROOT / "graph" / "data" / "curated_links.json"
UNIVERSE = ROOT / "graph" / "data" / "universe.json"

GENERIC_OWNERS = {
    "afiliasi",
    "garibaldi thohir",
    "masyarakat non warkat",
    "masyarakat warkat",
    "saham treasury",
    "public",
    "public non scripless",
    "public scripless",
}

INDONESIA_CITIES = [
    "Jakarta Selatan", "Jakarta Barat", "Jakarta Timur", "Jakarta Utara", "Jakarta Pusat",
    "Jakarta", "Bandung", "Surabaya", "Semarang", "Medan", "Makassar", "Balikpapan",
    "Palembang", "Batam", "Bogor", "Depok", "Bekasi", "Tangerang Selatan", "Tangerang",
    "Cikarang", "Karawang", "Sidoarjo", "Gresik", "Samarinda", "Denpasar", "Yogyakarta",
    "Solo", "Surakarta", "Pekanbaru", "Padang", "Banjarmasin", "Manado", "Malang",
]


def clean(text: str | None) -> str:
    return " ".join(str(text or "").replace("\n", " ").split()).strip()


def ensure_url(value: str | None) -> str:
    text = clean(value)
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        return text
    return "https://" + text.lstrip("/")


def city_from_address(address: str) -> str:
    text = clean(address)
    lower = text.lower()
    for city in INDONESIA_CITIES:
        if city.lower() in lower:
            return f"{city}, Indonesia"
    match = re.search(r"([A-Za-z .'-]+)\s+\d{5}(?:\s*-\s*Indonesia)?$", text, re.I)
    if match:
        city = clean(match.group(1)).strip(",.- ")
        return f"{city.title()}, Indonesia"
    parts = [part.strip() for part in re.split(r",|-", text) if part.strip()]
    if parts:
        tail = re.sub(r"\b\d{5}\b", "", parts[-1]).strip(" .,-")
        if tail and tail.lower() != "indonesia":
            return f"{tail.title()}, Indonesia"
    return "Indonesia"


def normalize_name(name: str) -> str:
    text = clean(name)
    text = re.sub(r"\(.*?sebelumnya.*?\)", "", text, flags=re.I)
    text = re.sub(r"\(.*?formerly.*?\)", "", text, flags=re.I)
    text = text.replace("&", " and ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(
        r"\b(pt|tbk|persero|bk|limited|ltd|corp|corporation|co|holdings|holding|group|inc|the)\b",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return " ".join(text.split())


def alias_variants(name: str) -> set[str]:
    values = {normalize_name(name)}
    for inner in re.findall(r"\((.*?)\)", name):
        if any(token in inner.lower() for token in ("sebelumnya", "formerly", "bernama")):
            values.add(normalize_name(inner))
    return {value for value in values if value}


def load_raw() -> list[dict]:
    rows = [json.loads(line) for line in RAW.read_text().splitlines() if line.strip()]
    return [row for row in rows if clean(row.get("code")) and clean(row.get("name"))]


def build_company_map(rows: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        node_id = f"IDX:{row['code']}"
        for alias in alias_variants(row["name"]) | alias_variants(row.get("directoryName", "")):
            mapping.setdefault(alias, node_id)
    if UNIVERSE.exists():
        universe = json.loads(UNIVERSE.read_text())
        for node in universe.get("nodes", []):
            node_id = str(node.get("id") or "")
            for alias in alias_variants(str(node.get("n") or "")):
                mapping.setdefault(alias, node_id)
    return mapping


def source_record(row: dict) -> dict:
    return {
        "canonical_id": f"IDX:{row['code']}",
        "name": clean(row["name"]),
        "country": "Indonesia",
        "exchange": "IDX",
        "sector_or_sic": clean(row.get("sector") or "Other"),
        "ticker": clean(row["code"]),
        "sub": clean(row.get("subIndustry") or row.get("subsector") or row.get("industry") or row.get("primarySector")),
        "hq": city_from_address(row.get("officeAddress", "")),
        "quote_symbol": f"{row['code']}.JK",
        "website": ensure_url(row.get("website")),
        "f": clean(row.get("listingDate"))[:4],
        "research": {
            "exchange_profile": f"https://www.idx.co.id/en/listed-companies/company-profiles/{row['code']}",
            "raw_address": clean(row.get("officeAddress")),
            "listing_board": clean(row.get("listingBoard")),
            "primary_sector": clean(row.get("primarySector")),
        },
    }


def build_links(rows: list[dict], company_map: dict[str, str]) -> list[dict]:
    links: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        target = f"IDX:{row['code']}"
        profile_url = f"https://www.idx.co.id/en/listed-companies/company-profiles/{row['code']}"
        for holder in row.get("shareholders", []):
            owner_name = clean(holder.get("name"))
            owner_key = normalize_name(owner_name)
            owner = company_map.get(owner_key)
            pct = clean(holder.get("percentage"))
            if not owner or owner == target or owner_key in GENERIC_OWNERS or pct in {"", "0%", "0.0%", "0.00%"}:
                continue
            key = (owner, "owns", target, profile_url)
            if key in seen:
                continue
            seen.add(key)
            links.append(
                {
                    "from": owner,
                    "to": target,
                    "rel": "owns",
                    "src": "IDX company profile",
                    "source_url": profile_url,
                    "val": 0.0,
                    "detail": f"Major shareholder disclosed on IDX profile ({pct})",
                    "confidence": 0.92,
                    "as_of": "2026-06-30",
                }
            )
        for sub in row.get("subsidiaries", []):
            child_name = clean(sub.get("name"))
            child = company_map.get(normalize_name(child_name))
            pct = clean(sub.get("percentage"))
            if not child or child == target:
                continue
            key = (target, "owns", child, profile_url)
            if key in seen:
                continue
            seen.add(key)
            links.append(
                {
                    "from": target,
                    "to": child,
                    "rel": "owns",
                    "src": "IDX company profile",
                    "source_url": profile_url,
                    "val": 0.0,
                    "detail": f"Subsidiary disclosed on IDX profile ({pct or 'ownership pct not stated'})",
                    "confidence": 0.9,
                    "as_of": "2026-06-30",
                }
            )
    return links


def merge_curated_links(new_links: list[dict]) -> None:
    existing = json.loads(CURATED_LINKS.read_text()) if CURATED_LINKS.exists() else []
    by_key = {(row.get("from"), row.get("rel"), row.get("to"), row.get("source_url")): row for row in existing}
    for row in new_links:
        by_key[(row["from"], row["rel"], row["to"], row["source_url"])] = row
    CURATED_LINKS.write_text(json.dumps(list(by_key.values()), ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    rows = load_raw()
    records = [source_record(row) for row in rows]
    records.sort(key=lambda row: row["ticker"])
    OUT.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n")
    company_map = build_company_map(rows)
    links = build_links(rows, company_map)
    merge_curated_links(links)
    print(f"wrote {len(records)} Indonesia companies -> {OUT}")
    print(f"merged {len(links)} Indonesia ownership links -> {CURATED_LINKS}")


if __name__ == "__main__":
    main()
