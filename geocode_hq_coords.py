from __future__ import annotations

import json
import os
import subprocess
import time
import unicodedata
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ROOT = Path(__file__).parent
UNIVERSE = ROOT / "graph" / "data" / "universe.json"
HQ_COORDS = ROOT / "graph" / "data" / "hq_coords.json"
UA = "OasisGraph/0.1 (hq-coords refresh)"
ARCGIS_API_KEY = os.environ.get("ARCGIS_LOCATION_API_KEY", "").strip()
ARCGIS_URL = "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
BAD = {"", "-", "—", "n/a", "na", "none", "null", "nyse", "nasdaq", "otc", "cboe"}
TARGET_COUNTRIES = {
    "Argentina", "Australia", "Benin", "Bolivia", "Brazil", "Burkina Faso", "Chile", "Colombia",
    "Cote d'Ivoire", "Ecuador", "Ghana", "Guyana", "Indonesia", "Kenya", "Mali", "Morocco",
    "New Zealand", "Niger", "Paraguay", "Peru", "Senegal", "South Africa", "Suriname", "Togo",
    "Uruguay", "Venezuela",
    "Germany", "Sweden", "France", "Finland", "Denmark", "Liechtenstein", "Italy", "Cyprus",
    "Luxembourg", "Iceland", "Ireland", "United Kingdom", "Netherlands", "Spain", "Portugal",
    "Ukraine", "Georgia"
}


def clean(text: str) -> str:
    return " ".join(str(text or "").replace("[", " ").replace("]", " ").split()).strip()


def key(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", clean(text).lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.replace(".", "").strip()


def lookup_key(hq: str, country: str) -> str:
    hq_key = key(hq)
    country_key = key(country)
    if country_key and hq_key.endswith(f", {country_key}"):
        return hq_key
    if country_key:
        return f"{hq_key}, {country_key}"
    return hq_key


def coord_record(lat, lon, label: str, region: str, country: str, source: str, confidence: float) -> list:
    return [round(float(lat), 6), round(float(lon), 6), clean(label), clean(region), clean(country), source, round(confidence, 2)]


def geocode_arcgis(query: str, country: str) -> list | None:
    if not ARCGIS_API_KEY:
        return None
    search = clean(query)
    if key(country) not in key(search).split(", "):
        search = f"{search}, {country}"
    params = urlencode({
        "f": "json",
        "singleLine": search,
        "maxLocations": 1,
        "outFields": "Match_addr,Addr_type,City,Region,Subregion,Country,Score",
        "forStorage": "true",
        "token": ARCGIS_API_KEY,
    })
    req = Request(f"{ARCGIS_URL}?{params}", headers={"User-Agent": UA})
    with urlopen(req, timeout=20) as res:
        payload = json.loads(res.read().decode("utf-8"))
    rows = payload.get("candidates") or []
    if not rows:
        return None
    row = rows[0]
    loc = row.get("location") or {}
    attrs = row.get("attributes") or {}
    if loc.get("y") is None or loc.get("x") is None:
        return None
    score = float(attrs.get("Score") or row.get("score") or 70)
    label = attrs.get("City") or clean(query.split(",")[0]).title()
    region = attrs.get("Region") or attrs.get("Subregion") or country
    resolved_country = attrs.get("Country") or country
    return coord_record(loc["y"], loc["x"], label, region, resolved_country, "arcgis", max(0.5, score / 100))


def geocode_nominatim(query: str, country: str) -> list | None:
    search = clean(query)
    if key(country) not in key(search).split(", "):
        search = f"{search}, {country}"
    params = urlencode({"q": search, "format": "jsonv2", "limit": 1})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    raw = subprocess.check_output(["curl", "-ksA", UA, "--max-time", "20", url], text=True)
    rows = json.loads(raw)
    if not rows:
        return None
    row = rows[0]
    display = [part.strip() for part in row.get("display_name", "").split(",") if part.strip()]
    label = clean(query.split(",")[0]).title()
    region = display[1] if len(display) > 1 else country
    return coord_record(row["lat"], row["lon"], label, region, country, "nominatim", 0.72)


def geocode(query: str, country: str) -> list | None:
    try:
        found = geocode_arcgis(query, country)
        if found:
            return found
    except Exception as exc:
        print("arcgis failed", lookup_key(query, country), exc)
    return geocode_nominatim(query, country)


def main() -> None:
    coords = json.loads(HQ_COORDS.read_text()) if HQ_COORDS.exists() else {}
    universe = json.loads(UNIVERSE.read_text())
    wanted: dict[str, tuple[str, str]] = {}
    for node in universe["nodes"]:
        country = clean(node.get("country", ""))
        hq = clean(node.get("hq", ""))
        if country not in TARGET_COUNTRIES or key(hq) in BAD or key(hq) == key(country):
            continue
        lookup = lookup_key(hq, country)
        if lookup not in coords:
            wanted[lookup] = (hq, country)

    added = 0
    for lookup, (hq, country) in sorted(wanted.items()):
        result = geocode(hq, country)
        time.sleep(1)
        if not result:
            print("skip", lookup)
            continue
        coords[lookup] = result
        added += 1
        print("added", lookup, "->", result[:2])

    HQ_COORDS.write_text(json.dumps(dict(sorted(coords.items())), ensure_ascii=False, indent=2) + "\n")
    print(f"added {added} coordinate rows; total {len(coords)}")


if __name__ == "__main__":
    main()
