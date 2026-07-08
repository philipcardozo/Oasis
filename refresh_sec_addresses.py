"""Refresh SEC business addresses mapping.

Downloads SEC daily bulk submissions ZIP, extracts company business addresses,
and falls back to querying the SEC EDGAR API directly for any missing CIKs.
Saves the mapping to data/raw/sec/business_addresses.json.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_FILE = ROOT / "data" / "raw" / "sec" / "business_addresses.json"
ZIP_PATH = ROOT / "data" / "raw" / "sec" / "submissions.zip"
SEC_BULK_URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
UA = "BusinessGraph/0.1 (veratori@veratori.com)"
SSL_CTX = ssl._create_unverified_context()


def download_file(url: str, dest_path: Path) -> None:
    print(f"Downloading SEC bulk submissions from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    start_time = time.time()
    total_bytes = 0
    with urllib.request.urlopen(req, context=SSL_CTX) as response:
        with open(dest_path, "wb") as f:
            chunk_size = 4 * 1024 * 1024  # 4MB
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                total_bytes += len(chunk)
                elapsed = time.time() - start_time
                speed = (total_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                sys.stdout.write(f"\rDownloaded {total_bytes / (1024*1024):.1f} MB ({speed:.2f} MB/s)")
                sys.stdout.flush()
    print(f"\nFinished download in {time.time() - start_time:.1f} seconds.")


def extract_addresses() -> dict:
    print("Extracting business addresses from zip...")
    addresses = {}
    
    # Load SEC CIK list to find the CIKs we care about
    tickers_path = Path("/tmp/sec_tickers.json")
    if not tickers_path.exists():
        try:
            print("Downloading tickers list...")
            req = urllib.request.Request(SEC_TICKERS_URL, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, context=SSL_CTX) as r:
                tickers_path.write_bytes(r.read())
        except Exception as e:
            print(f"Error loading tickers list: {e}")
            return {}
            
    tickers_data = json.loads(tickers_path.read_text("utf-8"))
    ciks = set()
    for row in tickers_data.values():
        ciks.add(str(row["cik_str"]).zfill(10))
        
    # Read from zip file index directly
    if ZIP_PATH.exists():
        with zipfile.ZipFile(ZIP_PATH) as zf:
            print(f"Directly looking up {len(ciks)} CIK JSON files inside the ZIP...")
            
            count = 0
            for cik10 in sorted(ciks):
                count += 1
                if count % 2000 == 0:
                    print(f"Looked up {count}/{len(ciks)} CIKs inside Zip...")
                    
                name = f"CIK{cik10}.json"
                try:
                    with zf.open(name) as f:
                        data = json.loads(f.read().decode("utf-8"))
                        
                    cik_str = data.get("cik")
                    if not cik_str:
                        continue
                    cik_val = str(cik_str).zfill(10)
                    
                    addresses_data = data.get("addresses", {})
                    biz = addresses_data.get("business")
                    if biz:
                        city = biz.get("city", "").strip()
                        state_or_country = biz.get("stateOrCountry")
                        state_code = str(state_or_country).strip() if state_or_country else ""
                        state_or_country_desc = biz.get("stateOrCountryDescription") or biz.get("country")
                        desc = str(state_or_country_desc).strip() if state_or_country_desc else ""
                        
                        if city or state_code or desc:
                            addresses[cik_val] = {
                                "city": city,
                                "state_or_country": state_code,
                                "description": desc
                            }
                except KeyError:
                    # File not in ZIP index
                    continue
                except Exception as e:
                    continue
                    
    print(f"Extracted {len(addresses)} CIK business addresses from zip.")
    
    # Fallback to direct API fetch for missing CIKs
    missing_ciks = ciks - set(addresses.keys())
    if missing_ciks:
        print(f"Querying SEC submissions API directly for {len(missing_ciks)} missing CIKs...")
        for idx, cik10 in enumerate(sorted(missing_ciks)):
            if idx % 100 == 0:
                print(f"Queried {idx}/{len(missing_ciks)} missing CIKs...")
                
            url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, context=SSL_CTX) as r:
                    data = json.loads(r.read().decode("utf-8"))
                    
                addresses_data = data.get("addresses", {})
                biz = addresses_data.get("business")
                if biz:
                    city = biz.get("city", "").strip()
                    state_or_country = biz.get("stateOrCountry")
                    state_code = str(state_or_country).strip() if state_or_country else ""
                    state_or_country_desc = biz.get("stateOrCountryDescription") or biz.get("country")
                    desc = str(state_or_country_desc).strip() if state_or_country_desc else ""
                    
                    if city or state_code or desc:
                        addresses[cik10] = {
                            "city": city,
                            "state_or_country": state_code,
                            "description": desc
                        }
            except Exception as e:
                # 404 or rate-limited or other errors, skip
                pass
            time.sleep(0.15)  # Safe rate limit (approx 6.6 requests/second)
            
    print(f"Total resolved addresses: {len(addresses)}")
    return addresses


def run(force: bool = False) -> None:
    if OUT_FILE.exists() and not force:
        mtime = OUT_FILE.stat().st_mtime
        age_days = (time.time() - mtime) / (24 * 3600)
        if age_days < 30:
            print(f"SEC business addresses cache is {age_days:.1f} days old. Skipping refresh.")
            return

    try:
        download_file(SEC_BULK_URL, ZIP_PATH)
        addresses = extract_addresses()
        
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUT_FILE.write_text(json.dumps(addresses, indent=2) + "\n", encoding="utf-8")
        print(f"Successfully wrote SEC business addresses to {OUT_FILE}")
    finally:
        if ZIP_PATH.exists():
            print("Cleaning up ZIP file...")
            ZIP_PATH.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh SEC business addresses.")
    parser.add_argument("--force", action="store_true", help="Force refresh even if cache is fresh.")
    args = parser.parse_args()
    run(force=args.force)


if __name__ == "__main__":
    main()
