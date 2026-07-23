"""Explicit, bounded acquisition of SEC companyfacts.

This is the ONLY place OASIS downloads companyfacts. Request paths and normal
startup are local-only (dcf_export.load_facts defaults to allow_network=False).

    python3 refresh_financial_facts.py --dry-run
    python3 refresh_financial_facts.py --max-entities 50
    python3 refresh_financial_facts.py --entities NVDA,GM --force

Safe to interrupt (Ctrl-C): finishes the current file, prints a summary, exits 130.
Resumes automatically — anything already cached is skipped unless --force.
"""
from __future__ import annotations

import argparse
import json
import random
import signal
import ssl
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cache_companyfacts import cik10
from dcf_export import FACTS
from store import by_id as store_by_id

UA = "OasisGraph/0.1 (companyfacts refresh; contact veratori@veratori.com)"
SEC_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

DEFAULTS = {
    "rate_limit": 6.0,        # requests/sec — SEC fair-use ceiling is 10/s
    "timeout": 20.0,          # seconds per request
    "max_retries": 3,
    "max_entities": 100,      # never the full 14k universe by default
    "max_file_mb": 25.0,      # skip absurdly large payloads
    "quota_gb": 2.0,          # total companyfacts cache ceiling
}

_interrupted = False


def _on_sigint(_sig, _frame):
    global _interrupted
    _interrupted = True
    print("\ninterrupt received — finishing current file, then stopping...", file=sys.stderr)


def dir_size_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.glob("*.json") if p.is_file())


def backoff_delay(attempt: int) -> float:
    """Exponential backoff with full jitter."""
    return random.uniform(0, min(30.0, 2.0**attempt))


def fetch_one(cik: str, *, timeout: float, max_retries: int, max_file_mb: float) -> tuple[bytes | None, str]:
    url = SEC_URL.format(cik=cik)
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()

    for attempt in range(max_retries + 1):
        try:
            with urlopen(req, timeout=timeout, context=ctx) as res:
                payload = res.read()
            size_mb = len(payload) / 1_048_576
            if size_mb > max_file_mb:
                return None, f"too large ({size_mb:.1f} MB > {max_file_mb} MB)"
            json.loads(payload)  # validate before writing
            return payload, "ok"
        except HTTPError as e:
            if e.code == 404:
                return None, "404 not found"
            if e.code in (429, 503) and attempt < max_retries:
                time.sleep(backoff_delay(attempt))
                continue
            return None, f"HTTP {e.code}"
        except (URLError, TimeoutError, OSError) as e:
            if attempt < max_retries:
                time.sleep(backoff_delay(attempt))
                continue
            return None, f"network: {type(e).__name__}"
        except json.JSONDecodeError:
            return None, "invalid JSON"
    return None, "retries exhausted"


def select_targets(entities: str | None, max_entities: int, force: bool) -> list[tuple[str, str]]:
    """Return [(entity_id, cik10)] — highest-degree entities first, uncached only."""
    nodes = store_by_id()
    if entities:
        wanted = {e.strip().upper() for e in entities.split(",") if e.strip()}
        chosen = [n for n in nodes.values()
                  if str(n.get("id", "")).upper() in wanted or str(n.get("t", "")).upper() in wanted]
    else:
        chosen = sorted(
            (n for n in nodes.values() if str(n.get("cik") or "").strip().isdigit()),
            key=lambda n: -int(n.get("deg") or 0),
        )
    out = []
    for n in chosen:
        raw = str(n.get("cik") or "").strip()
        if not raw.isdigit():
            continue
        try:
            cik = cik10(raw)
        except ValueError:
            continue
        if not force and (FACTS / f"CIK{cik}.json").exists():
            continue
        out.append((n.get("id", cik), cik))
        if len(out) >= max_entities:
            break
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--entities", help="comma-separated ids/tickers (default: highest-degree uncached)")
    p.add_argument("--max-entities", type=int, default=DEFAULTS["max_entities"])
    p.add_argument("--rate-limit", type=float, default=DEFAULTS["rate_limit"], help="requests per second")
    p.add_argument("--timeout", type=float, default=DEFAULTS["timeout"])
    p.add_argument("--max-retries", type=int, default=DEFAULTS["max_retries"])
    p.add_argument("--max-file-mb", type=float, default=DEFAULTS["max_file_mb"])
    p.add_argument("--quota-gb", type=float, default=DEFAULTS["quota_gb"], help="companyfacts cache ceiling")
    p.add_argument("--force", action="store_true", help="re-download even if cached")
    p.add_argument("--dry-run", action="store_true", help="list what would be fetched, download nothing")
    args = p.parse_args()

    signal.signal(signal.SIGINT, _on_sigint)
    FACTS.mkdir(parents=True, exist_ok=True)

    quota_bytes = int(args.quota_gb * 1_073_741_824)
    used = dir_size_bytes(FACTS)
    targets = select_targets(args.entities, args.max_entities, args.force)

    print(f"cache: {used / 1_073_741_824:.2f} GB / {args.quota_gb} GB quota  ({len(list(FACTS.glob('*.json')))} files)")
    print(f"targets: {len(targets)}  rate: {args.rate_limit}/s  timeout: {args.timeout}s  retries: {args.max_retries}")

    if args.dry_run:
        for eid, cik in targets:
            print(f"  would fetch {eid} (CIK{cik})")
        print(f"dry run — nothing downloaded ({len(targets)} planned)")
        return 0

    if used >= quota_bytes:
        print(f"quota reached ({used / 1_073_741_824:.2f} GB) — nothing fetched. Raise --quota-gb or clear the cache.")
        return 1

    ok = failed = skipped = 0
    interval = 1.0 / args.rate_limit if args.rate_limit > 0 else 0.0
    for i, (eid, cik) in enumerate(targets, 1):
        if _interrupted:
            break
        if used >= quota_bytes:
            print(f"quota reached at {used / 1_073_741_824:.2f} GB — stopping")
            break
        started = time.monotonic()
        payload, status = fetch_one(cik, timeout=args.timeout, max_retries=args.max_retries,
                                    max_file_mb=args.max_file_mb)
        if payload is None:
            failed += 1
            print(f"[{i}/{len(targets)}] {eid} CIK{cik} — FAILED: {status}")
        else:
            (FACTS / f"CIK{cik}.json").write_bytes(payload)
            used += len(payload)
            ok += 1
            print(f"[{i}/{len(targets)}] {eid} CIK{cik} — {len(payload) / 1_048_576:.1f} MB")
        elapsed = time.monotonic() - started
        if interval > elapsed and i < len(targets):
            time.sleep(interval - elapsed)

    print(f"\nsummary: {ok} fetched, {failed} failed, {skipped} skipped, "
          f"cache now {used / 1_073_741_824:.2f} GB / {args.quota_gb} GB")
    if _interrupted:
        print("stopped early (interrupt) — rerun to resume")
        return 130
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
