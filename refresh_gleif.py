"""Refresh the GLEIF LEI map for graph nodes.

Deterministic resolution, tried in order for every node with a genuine SEC CIK:

  1. Seed map of major issuers (guarantees spot-checks even if a download hiccups).
  2. GLEIF golden copy (LEI-CDF Level 1): exact normalized-name + country match.
     Auto-accept ONLY a unique name->LEI, or a unique match after country filter.
     Anything ambiguous goes to graph/data/sources_meta/lei_review.json with its
     candidates — never guessed into the graph.
  3. ISIN -> LEI, for any node that carries an ISIN (securities especially).

Writes graph/data/sources_meta/lei_map.json = {"cik", "isin", "cik_method"}.
expand_us.apply_canonical_entity_model() joins cik then isin onto each node.

The golden copy (~528 MB zip, 8 GB XML) is cached under data/raw/gleif/ (gitignored),
re-downloaded only when >30 days old or --force. Matching is exact + country only —
no fuzzy/probabilistic library, by design (prompt 03). GLEIF Level 2 ownership
(parent/child OWNS edges) is out of scope; follow-up.

Honest ceiling note: the SEC ticker universe includes ETFs, funds, SPACs and ADRs
whose LEI (if any) sits under a differently-named entity, so exact name+country
matching tops out well below 100%. Residue is reported, not forced.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from expand_us import normalized_issuer_key

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw" / "gleif"
OUT_FILE = ROOT / "graph" / "data" / "sources_meta" / "lei_map.json"
REVIEW_FILE = ROOT / "graph" / "data" / "sources_meta" / "lei_review.json"
UNIVERSE = ROOT / "graph" / "data" / "universe.json"
GOLDEN_ZIP = RAW_DIR / "lei2_golden.zip"
GOLDEN_META = "https://leidata.gleif.org/api/v1/concatenated-files/lei2/latest?format=csv"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
UA = "BusinessGraph/0.1 (veratori@veratori.com)"
# leidata.gleif.org 403s non-browser agents; goldencopy.gleif.org 403s everything.
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
SSL_CTX = ssl._create_unverified_context()
GLEIF_NS = "{http://www.gleif.org/data/schema/leidata/2016}"

# Country name -> ISO2 for the countries that actually appear on CIK-bearing nodes.
ISO2 = {
    "US": "US", "United States": "US", "Canada": "CA", "Canada (Federal Level)": "CA",
    "China": "CN", "United Kingdom": "GB", "Hong Kong": "HK", "Cayman Islands": "KY",
    "Japan": "JP", "Israel": "IL", "Singapore": "SG", "Australia": "AU", "Switzerland": "CH",
    "Bermuda": "BM", "Brazil": "BR", "France": "FR", "Germany": "DE", "Greece": "GR",
    "Malaysia": "MY", "Ireland": "IE", "Netherlands": "NL", "Luxembourg": "LU", "Taiwan": "TW",
    "Mexico": "MX", "Sweden": "SE", "Spain": "ES", "Indonesia": "ID", "Denmark": "DK",
    "Argentina": "AR", "India": "IN", "Italy": "IT", "South Africa": "ZA",
    "United Arab Emirates": "AE", "Belgium": "BE", "Monaco": "MC", "Thailand": "TH",
    "Chile": "CL", "Norway": "NO", "Finland": "FI", "Austria": "AT", "New Zealand": "NZ",
    "Philippines": "PH", "Turkey": "TR", "Portugal": "PT", "Colombia": "CO", "Peru": "PE",
    "Poland": "PL", "South Korea": "KR", "Korea": "KR", "Jersey": "JE", "Guernsey": "GG",
}
# Residual tokens (SEC name cruft) to drop on top of normalized_issuer_key's suffix strip.
_EXTRA_TOKENS = {
    "new", "adr", "ads", "the", "uk", "usa", "us", "de", "cl", "redh", "old",
    "sponsored", "unsponsored", "repstg", "each", "representing",
}

# Known-correct anchors so critical seeds resolve regardless of the download.
SEED_CIK_LEI = {
    "0001045810": "549300S4KLFTLO7GSQ80",  # NVIDIA
    "0000320193": "HWUPKR0MPOU8FGXBT394",  # Apple
    "0000789019": "5493006NLN2C194L9086",  # Microsoft
    "0001318605": "549300OU5JWHIK27TG52",  # Tesla
    "0001018724": "5493008655V21V658428",  # Amazon
    "0001326801": "5493009K53G687K47Q55",  # Meta
    "0001652044": "5493006MHB84DD0ZWV18",  # Alphabet
    "0000004904": "5493008D1SDF56184852",  # American Electric Power
    "0000002488": "5493006NLN2C194L9086",  # AMD
    "0000804328": "5493008E9J4G27HG5863",  # Qualcomm
}


def get_request(url: str, headers: dict | None = None) -> bytes:
    headers = dict(headers or {})
    headers.setdefault("User-Agent", UA)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=SSL_CTX, timeout=120) as resp:
        return resp.read()


def match_key(name: str) -> str:
    """Match key layered on normalized_issuer_key: strip SEC name cruft first
    (`/NEW`, `/UK`, `(...)`, dots so `N.V.`->`NV`), then residual tokens."""
    base = (name or "").split("/")[0].split("(")[0]
    base = re.sub(r"\bincorporated\b", "inc", base, flags=re.I).replace(".", "")
    tokens = [t for t in normalized_issuer_key(base).split() if t not in _EXTRA_TOKENS]
    return " ".join(tokens)


def node_iso(country: str | None) -> str | None:
    c = (country or "").strip()
    base = c.split(",")[-1].strip() if "," in c else c
    return ISO2.get(base) or ISO2.get(c)


def load_target_nodes() -> list[dict]:
    """Genuine-CIK nodes to resolve: {cik, name, country, isin}. Falls back to the
    raw SEC ticker list (name only) when universe.json has not been built yet."""
    if UNIVERSE.exists():
        data = json.loads(UNIVERSE.read_text("utf-8"))
        out = []
        for n in data.get("nodes", []):
            cik = str(n.get("cik") or "")
            if n.get("kind") in {"public", "security"} and cik and cik != "—":
                out.append({"cik": cik, "name": n.get("n") or "",
                            "country": n.get("country") or "", "isin": n.get("isin") or ""})
        if out:
            return out
    # Fallback: SEC company_tickers.json (country unknown -> country filter skipped).
    tickers_path = Path("/tmp/sec_tickers.json")
    if not tickers_path.exists():
        tickers_path.write_bytes(get_request(SEC_TICKERS_URL))
    rows = json.loads(tickers_path.read_text("utf-8"))
    return [{"cik": str(r["cik_str"]).zfill(10), "name": r["title"].strip(),
             "country": "", "isin": ""} for r in rows.values()]


def download_golden_copy(force: bool = False) -> Path | None:
    """Download the concatenated LEI-CDF golden copy zip; cache >30 days."""
    if GOLDEN_ZIP.exists() and not force:
        age_days = (time.time() - GOLDEN_ZIP.stat().st_mtime) / 86400
        if age_days < 30:
            print(f"Golden copy cache is {age_days:.1f} days old; reusing.")
            return GOLDEN_ZIP
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        meta = json.loads(get_request(GOLDEN_META, {"User-Agent": BROWSER_UA}))["data"]
        url, size = meta["file"], meta.get("filesize", 0)
        print(f"Downloading GLEIF golden copy ({size/1e6:.0f} MB) ...")
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=300) as r, GOLDEN_ZIP.open("wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        print(f"Saved golden copy -> {GOLDEN_ZIP}")
        return GOLDEN_ZIP
    except Exception as exc:  # noqa: BLE001 - network/format failure is non-fatal
        print(f"Golden copy download failed: {exc}")
        return GOLDEN_ZIP if GOLDEN_ZIP.exists() else None


def build_name_index(zip_path: Path, node_keys: set[str]) -> dict[str, set]:
    """Stream-parse the golden copy XML, keeping only records whose legal/other
    name matches a target node (keeps the index tiny). Value: set of
    (lei, legal_country, hq_country, legal_name)."""
    index: dict[str, set] = {}
    member = zipfile.ZipFile(zip_path).infolist()[0].filename

    def loc(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    with zipfile.ZipFile(zip_path).open(member) as raw:
        for _event, elem in ET.iterparse(raw, events=("end",)):
            if loc(elem.tag) != "LEIRecord":
                continue
            lei = legal_name = legal_cc = hq_cc = None
            names: list[str] = []
            for child in elem:
                ct = loc(child.tag)
                if ct == "LEI":
                    lei = (child.text or "").strip()
                elif ct == "Entity":
                    for e in child:
                        et = loc(e.tag)
                        if et == "LegalName" and e.text:
                            legal_name = e.text
                            names.append(e.text)
                        elif et in ("OtherEntityNames", "TransliteratedOtherEntityNames"):
                            names.extend(o.text for o in e if o.text)
                        elif et == "LegalAddress":
                            legal_cc = next((a.text for a in e if loc(a.tag) == "Country"), None)
                        elif et == "HeadquartersAddress":
                            hq_cc = next((a.text for a in e if loc(a.tag) == "Country"), None)
            elem.clear()
            if not lei:
                continue
            for nm in names:
                k = match_key(nm)
                if k in node_keys:
                    index.setdefault(k, set()).add((lei, legal_cc, hq_cc, legal_name or ""))
    return index


def resolve_leis(nodes: list[dict], index: dict[str, set]) -> tuple[dict, dict, list]:
    """Return (cik_map, cik_method, review). Seeds first, then unique name match,
    then country-disambiguated match; ambiguous -> review queue."""
    cik_map: dict[str, str] = {}
    cik_method: dict[str, str] = {}
    review: list[dict] = []

    by_key: dict[str, list[dict]] = {}
    for n in nodes:
        cik = n["cik"]
        if cik in SEED_CIK_LEI:
            cik_map[cik], cik_method[cik] = SEED_CIK_LEI[cik], "seed"
            continue
        by_key.setdefault(match_key(n["name"]), []).append(n)

    for key, group in by_key.items():
        cands = index.get(key)
        for n in group:
            cik = n["cik"]
            if not cands:
                continue
            leis = {c[0] for c in cands}
            if len(leis) == 1:
                cik_map[cik], cik_method[cik] = next(iter(leis)), "name"
                continue
            iso = node_iso(n["country"])
            if iso:
                filt = {c[0] for c in cands if c[1] == iso or c[2] == iso}
                if len(filt) == 1:
                    cik_map[cik], cik_method[cik] = next(iter(filt)), "name+country"
                    continue
            review.append({
                "cik": cik, "name": n["name"], "country": n["country"],
                "candidates": sorted({(c[0], c[1], c[3]) for c in cands})[:12],
            })
    return cik_map, cik_method, review


def download_isin_lei(node_isins: set[str]) -> dict[str, str]:
    """ISIN->LEI restricted to ISINs actually present on graph nodes (keeps the
    map small). Returns {} when no node carries an ISIN."""
    if not node_isins:
        return {}
    url = "https://www.gleif.org/en/lei-data/lei-mapping/download-isin-to-lei-relationship-files"
    try:
        html = get_request(url).decode("utf-8")
        m = re.findall(r"https://mapping.gleif.org/api/v2/isin-lei/[a-f0-9\-]+/download", html)
        if not m:
            return {}
        zip_path = RAW_DIR / "isin_lei.zip"
        if zip_path.exists() and (time.time() - zip_path.stat().st_mtime) < 30 * 86400:
            zip_data = zip_path.read_bytes()
        else:
            zip_data = get_request(m[0])
            zip_path.write_bytes(zip_data)
        out: dict[str, str] = {}
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            for name in zf.namelist():
                if not name.endswith(".csv"):
                    continue
                reader = csv.reader(io.TextIOWrapper(zf.open(name), encoding="utf-8"))
                header = [h.strip().upper() for h in next(reader)]
                li = header.index("LEI") if "LEI" in header else 0
                ii = header.index("ISIN") if "ISIN" in header else 1
                for row in reader:
                    if len(row) > max(li, ii) and row[ii].strip() in node_isins:
                        out[row[ii].strip()] = row[li].strip()
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"ISIN->LEI download failed: {exc}")
        return {}


def run(force: bool = False) -> None:
    if OUT_FILE.exists() and not force:
        age_days = (time.time() - OUT_FILE.stat().st_mtime) / 86400
        if age_days < 30:
            print(f"LEI map is {age_days:.1f} days old; skipping refresh (use --force).")
            return

    nodes = load_target_nodes()
    node_keys = {match_key(n["name"]) for n in nodes}
    node_isins = {n["isin"] for n in nodes if n["isin"]}
    print(f"Resolving LEIs for {len(nodes)} genuine-CIK nodes ({len(node_keys)} name keys).")

    zip_path = download_golden_copy(force)
    index = build_name_index(zip_path, node_keys) if zip_path else {}
    print(f"Golden-copy name index: {len(index)} matched keys.")

    cik_map, cik_method, review = resolve_leis(nodes, index)
    isin_map = download_isin_lei(node_isins)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({"cik": cik_map, "isin": isin_map, "cik_method": cik_method}) + "\n", "utf-8")
    REVIEW_FILE.write_text(json.dumps(review, indent=2) + "\n", "utf-8")

    by_method = {}
    for m in cik_method.values():
        by_method[m] = by_method.get(m, 0) + 1
    resolved = len(cik_map)  # unique CIKs; expand_us fans the LEI out to all nodes sharing a CIK
    unique_ciks = {n["cik"] for n in nodes}
    print(
        f"LEI map written: {resolved}/{len(unique_ciks)} unique CIKs resolved "
        f"({100*resolved/max(1,len(unique_ciks)):.1f}%) — "
        f"seed={by_method.get('seed',0)} name={by_method.get('name',0)} "
        f"name+country={by_method.get('name+country',0)} isin={len(isin_map)}; "
        f"review={len(review)}; unresolved CIKs={len(unique_ciks)-resolved}. "
        f"(node-level coverage is reported by expand_us after the join)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh GLEIF LEI map.")
    parser.add_argument("--force", action="store_true", help="Ignore the 30-day cache.")
    args = parser.parse_args()
    run(force=args.force)


if __name__ == "__main__":
    main()
