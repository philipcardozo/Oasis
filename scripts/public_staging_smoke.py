#!/usr/bin/env python3
"""Run the first public-staging smoke checks after provider setup."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
LOCAL_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
RESERVED_PUBLIC_HOSTS = {"example.com", "example.net", "example.org"}
RESERVED_PUBLIC_SUFFIXES = (".example.com", ".example.net", ".example.org", ".invalid", ".test")

ACCESS_HEADERS = [
    "CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID",
    "CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET",
]


def run(cmd: list[str]) -> dict[str, Any]:
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "command": redact_command(cmd),
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }


def redact_command(cmd: list[str]) -> list[str]:
    return ["<redacted>" if "SECRET" in part or "TOKEN" in part else part for part in cmd]


def public_base_url_failures(url: str) -> list[str]:
    parsed = urlparse(url)
    failures: list[str] = []
    if parsed.scheme != "https":
        failures.append("base URL must use https")
    if not parsed.hostname:
        failures.append("base URL must include a hostname")
    hostname = (parsed.hostname or "").lower()
    if hostname in LOCAL_PUBLIC_HOSTS or hostname.endswith(".local"):
        failures.append("base URL must be a non-local public hostname")
    if hostname in RESERVED_PUBLIC_HOSTS or hostname.endswith(RESERVED_PUBLIC_SUFFIXES):
        failures.append("base URL must not be a reserved documentation hostname")
    return failures


def build_commands(*, base_url: str, proxy_server: str, expect_commit: str, samples: int) -> list[list[str]]:
    preflight = [
        "python3",
        "scripts/public_staging_preflight.py",
        f"--base-url={base_url}",
        *[f"--header={item}" for item in ACCESS_HEADERS],
    ]
    if expect_commit:
        preflight.append(f"--expect-commit={expect_commit}")

    route = [
        "python3",
        "scripts/compose_route_family_probe.py",
        f"--base-url={base_url}",
        f"--samples={samples}",
        "--output-file=25-public-route-family-probe.json",
        "--verify-tls",
        *[f"--header={item}" for item in ACCESS_HEADERS],
    ]
    if proxy_server:
        route.append(f"--proxy-server={proxy_server}")

    return [
        ["python3", "scripts/public_staging_readiness.py"],
        preflight,
        route,
        ["python3", "scripts/public_staging_gate_audit.py"],
    ]


def payload(*, commands: list[list[str]], results: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    failures = [item for item in results if item.get("returncode") not in {0, None}]
    return {
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "not_public_staging_proof": bool(dry_run),
        "dry_run": dry_run,
        "commands": [redact_command(command) for command in commands],
        "results": results,
        "verdict": "planned" if dry_run else ("pass" if not failures else "investigate"),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("STAGING_URL", ""))
    parser.add_argument("--proxy-server", default="")
    parser.add_argument("--expect-commit", default="")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=str(EVIDENCE / "public-staging-smoke-run.json"))
    args = parser.parse_args()

    if not args.base_url:
        raise SystemExit("provide --base-url or STAGING_URL")
    target_failures = public_base_url_failures(args.base_url.rstrip("/"))
    if target_failures:
        raise SystemExit("; ".join(target_failures))

    commands = build_commands(
        base_url=args.base_url.rstrip("/"),
        proxy_server=args.proxy_server,
        expect_commit=args.expect_commit,
        samples=max(1, args.samples),
    )
    results = [] if args.dry_run else [run(command) for command in commands]
    data = payload(commands=commands, results=results, dry_run=args.dry_run)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging smoke run to {output}")
    print(json.dumps({"verdict": data["verdict"], "dry_run": data["dry_run"], "failure_count": len(data["failures"])}, indent=2))
    return 0 if data["verdict"] in {"planned", "pass"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
