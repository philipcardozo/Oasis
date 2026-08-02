#!/usr/bin/env python3
"""Generate a secret-free manual browser-matrix template for public staging."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.public_staging_browser_reports import BROWSER_CHECKS, MAP_CHECKS

PUBLIC_EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
DEFAULT_JSON = PUBLIC_EVIDENCE / "browser-matrix.template.json"
DEFAULT_MARKDOWN = PUBLIC_EVIDENCE / "browser-matrix-template.md"
LOCAL_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
RESERVED_PUBLIC_HOSTS = {"example.com", "example.net", "example.org"}
RESERVED_PUBLIC_SUFFIXES = (".example.com", ".example.net", ".example.org", ".invalid", ".test")

DESKTOP_BROWSERS = [
    ("chrome", "Google Chrome"),
    ("firefox", "Firefox"),
    ("safari_macos", "Safari on macOS"),
]
OPTIONAL_BROWSERS = [
    ("edge_or_brave", "Microsoft Edge or Brave"),
    ("mobile_safari", "Mobile Safari"),
    ("chrome_android", "Chrome on Android"),
]


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def blank_checks(checks: dict[str, str]) -> dict[str, None]:
    return {key: None for key in checks}


def public_base_url_failures(url: str, *, allow_placeholder: bool = False) -> list[str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if allow_placeholder and host == "staging.<approved-domain>":
        return []
    failures: list[str] = []
    if parsed.scheme != "https":
        failures.append("browser matrix base URL must use https")
    if not host or host in LOCAL_PUBLIC_HOSTS or host.endswith(".local"):
        failures.append("browser matrix base URL must be a non-local public hostname")
    if host in RESERVED_PUBLIC_HOSTS or host.endswith(RESERVED_PUBLIC_SUFFIXES):
        failures.append("browser matrix base URL must not be a reserved documentation hostname")
    return failures


def browser_row(name: str, label: str, *, optional: bool = False) -> dict[str, Any]:
    row = {
        "name": name,
        "label": label,
        "browser_version": "<record exact browser version>",
        "os": "<record OS>",
        "os_version": "<record OS version>",
        "available": None,
        "unavailable_reason": "" if not optional else "<required when available is false>",
        "checks": blank_checks(BROWSER_CHECKS),
        "notes": "",
    }
    if optional:
        row["optional"] = True
    return row


def build_payload(*, base_url: str, captured_at: str | None = None) -> dict[str, Any]:
    return {
        "captured_at": captured_at or utc_now(),
        "base_url": base_url,
        "branch": git_value("branch", "--show-current"),
        "commit": git_value("rev-parse", "HEAD"),
        "not_public_staging_proof": True,
        "verdict": "operator_input_required",
        "instructions": [
            "Copy this template to docs/evidence/public-staging/browser-matrix.json after the public URL is live.",
            "Replace every placeholder and set each passed check to true only after manual verification in that browser.",
            "Leave optional mobile browsers unavailable only with a concrete reason.",
            "Do not record cookies, tokens, Authorization headers, Cloudflare Access secrets, SMTP credentials, or provider credentials.",
            "Run scripts/public_staging_browser_reports.py after the filled matrix and public HAR summary are present.",
        ],
        "manual_flow_order": [
            "Open the public staging URL in Chrome, Firefox, and Safari.",
            "Verify registration, email verification, login, secure cookies, logout, and password reset.",
            "Verify Standard, Dark, and Satellite-disabled-or-failure map behavior.",
            "Verify exactly three map slots, persistence across reloads, stale-update 409, and cross-user denial.",
            "Restart the API service and verify session/data persistence.",
            "Review browser console and network panels for unexpected errors, failed requests, token leakage, /api/universe/bulk on first paint, and unpkg.com requests.",
        ],
        "check_labels": BROWSER_CHECKS,
        "browsers": [
            *(browser_row(name, label) for name, label in DESKTOP_BROWSERS),
            *(browser_row(name, label, optional=True) for name, label in OPTIONAL_BROWSERS),
        ],
        "map_provider": {
            "approved_hosts": ["<record approved public map tile/style host>"],
            "checks": blank_checks(MAP_CHECKS),
            "notes": "",
        },
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Browser Matrix Template",
        "",
        f"Captured: {payload['captured_at']}",
        f"Branch: `{payload['branch']}`",
        f"Commit: `{payload['commit']}`",
        f"Base URL: `{payload['base_url']}`",
        "Verdict: **operator_input_required**",
        "",
        "This generated file is operator guidance only. It is not public-staging proof.",
        "",
        "## Instructions",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["instructions"])
    lines.extend(["", "## Manual Flow Order", ""])
    lines.extend(f"- {item}" for item in payload["manual_flow_order"])
    lines.extend([
        "",
        "## Required Browser Checks",
        "",
        "| Key | Check |",
        "|---|---|",
    ])
    for key, label in payload["check_labels"].items():
        lines.append(f"| `{key}` | {label} |")
    lines.extend([
        "",
        "## Browser Rows",
        "",
        "| Browser key | Label | Optional |",
        "|---|---|---|",
    ])
    for row in payload["browsers"]:
        lines.append(f"| `{row['name']}` | {row['label']} | `{bool(row.get('optional'))}` |")
    lines.extend([
        "",
        "After filling `docs/evidence/public-staging/browser-matrix.json`, run:",
        "",
        "```bash",
        "python3 scripts/public_staging_browser_reports.py \\",
        "  --browser-matrix=docs/evidence/public-staging/browser-matrix.json \\",
        "  --browser-summary=docs/evidence/performance/26-public-staging-browser-har-summary.json \\",
        "  --browser-output=docs/evidence/public-staging/07-browser-matrix.md \\",
        "  --map-output=docs/evidence/public-staging/08-map-provider-capture.md \\",
        "  --summary-output=docs/evidence/public-staging/browser-map-summary.json",
        "```",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://staging.<approved-domain>")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON))
    parser.add_argument("--markdown-output", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    failures = public_base_url_failures(base_url, allow_placeholder=True)
    if failures:
        raise SystemExit("; ".join(failures))

    payload = build_payload(base_url=base_url)
    json_output = Path(args.json_output)
    markdown_output = Path(args.markdown_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown_output.write_text(markdown(payload))
    print(f"Wrote public staging browser matrix template JSON to {json_output}")
    print(f"Wrote public staging browser matrix template Markdown to {markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
