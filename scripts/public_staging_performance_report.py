#!/usr/bin/env python3
"""Build public-staging performance evidence from HAR/probe summaries."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PERF_EVIDENCE = ROOT / "docs" / "evidence" / "performance"
PUBLIC_EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def load_json(path: Path, *, required: bool = False) -> dict[str, Any] | None:
    if not path.exists():
        if required:
            raise SystemExit(f"missing required input: {path}")
        return None
    return json.loads(path.read_text())


def safe_url(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.scheme:
        return value
    return parsed._replace(query="<redacted>" if parsed.query else "").geturl()


def display_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() and path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    return value


def flow_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, flow in sorted((summary.get("flows") or {}).items()):
        nav = flow.get("navigation") or {}
        rows.append({
            "name": name,
            "flow": flow.get("flow") or name,
            "requests": flow.get("requestCount"),
            "transfer_kb": flow.get("resourceTransferKb"),
            "dom_content_loaded_ms": nav.get("domContentLoadedMs"),
            "load_event_ms": nav.get("loadEventMs"),
            "bulk": bool(flow.get("requestedUniverseBulk")),
            "unpkg": bool(flow.get("requestedUnpkg")),
            "console_errors": len(flow.get("consoleErrors") or []),
            "failed_requests": int(flow.get("failedRequestCount") or 0),
            "external_hosts": flow.get("externalHosts") or [],
            "har_path": flow.get("harPath"),
        })
    return rows


def first_paint(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        name = str(row["name"])
        flow = str(row["flow"])
        if "first-paint" in name or "first paint" in flow:
            return row
    return rows[0] if rows else None


def auth_rows(summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not summary:
        return []
    rows = []
    for item in summary.get("measurements", []):
        rows.append({
            "name": item.get("name"),
            "p50_ms": item.get("p50_ms"),
            "p95_ms": item.get("p95_ms"),
            "target_ms": item.get("target_ms"),
            "target_met": item.get("target_met"),
            "status_codes": item.get("status_codes"),
        })
    return rows


def route_rows(summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not summary:
        return []
    rows = []
    for item in summary.get("measurements", []):
        rows.append({
            "name": item.get("name"),
            "family": item.get("family"),
            "method": item.get("method"),
            "template": item.get("template") or item.get("path"),
            "p50_ms": item.get("p50_ms"),
            "p95_ms": item.get("p95_ms"),
            "status_codes": item.get("status_codes"),
            "ok": item.get("ok"),
        })
    return rows


def evaluate(
    browser_rows: list[dict[str, Any]],
    preflight: dict[str, Any] | None,
    auth: dict[str, Any] | None,
    route_probe: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []

    first = first_paint(browser_rows)
    if not first:
        failures.append("browser summary has no captured flows")
    elif first["bulk"]:
        failures.append("first paint requested /api/universe/bulk")

    if any(row["unpkg"] for row in browser_rows):
        failures.append("browser capture requested unpkg.com")
    if any(row["console_errors"] for row in browser_rows):
        failures.append("browser capture recorded console errors")

    if preflight is None:
        warnings.append("public preflight input missing; DNS/TLS timings are not summarized")
    elif preflight.get("verdict") != "pass":
        failures.append("public preflight verdict is not pass")

    if auth is None:
        warnings.append("auth/map-slot latency input missing; p95 targets are not summarized")
    else:
        for row in auth_rows(auth):
            if row["target_met"] is False:
                failures.append(f"auth/map-slot target missed: {row['name']}")

    if route_probe is None:
        warnings.append("public route-family probe input missing; route p95s are not summarized")
    elif route_probe.get("verdict") != "pass" or route_probe.get("failure_count"):
        failures.append("public route-family probe verdict is not pass")

    return failures, warnings


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    browser = load_json(Path(args.browser_summary), required=True) or {}
    direct = load_json(Path(args.direct_summary)) if args.direct_summary else None
    preflight = load_json(Path(args.preflight)) if args.preflight else None
    auth = load_json(Path(args.auth_map_slot)) if args.auth_map_slot else None
    route_probe = load_json(Path(args.route_probe)) if args.route_probe else None

    browser_rows = flow_rows(browser)
    failures, warnings = evaluate(browser_rows, preflight, auth, route_probe)

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "inputs": {
            "browser_summary": display_path(args.browser_summary),
            "direct_summary": args.direct_summary,
            "preflight": args.preflight,
            "auth_map_slot": args.auth_map_slot,
            "route_probe": args.route_probe,
        },
        "target": {
            "base_url": safe_url(browser.get("baseUrl")),
            "proxy_server": browser.get("proxyServer"),
            "direct_base_url": safe_url(direct.get("baseUrl")) if direct else None,
        },
        "browser": {
            "captured_at": browser.get("capturedAt"),
            "flows": browser_rows,
            "direct_comparison_present": bool(direct),
        },
        "preflight": {
            "verdict": preflight.get("verdict") if preflight else None,
            "dns_ms": (preflight.get("dns") or {}).get("duration_ms") if preflight else None,
            "tls_ms": (preflight.get("tls") or {}).get("duration_ms") if preflight else None,
        },
        "auth_map_slot": {
            "captured_at": auth.get("captured_at") if auth else None,
            "rows": auth_rows(auth),
        },
        "route_probe": {
            "captured_at": route_probe.get("captured_at") if route_probe else None,
            "verdict": route_probe.get("verdict") if route_probe else None,
            "rows": route_rows(route_probe),
        },
        "failures": failures,
        "warnings": warnings,
        "verdict": "pass" if not failures else "investigate",
    }


def md_bool(value: Any) -> str:
    return "yes" if value else "no"


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Performance Evidence",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Verdict: **{payload['verdict']}**",
        "",
        "## Target",
        "",
        f"- Base URL: `{payload['target']['base_url']}`",
        f"- Proxyman proxy: `{payload['target']['proxy_server'] or 'not recorded'}`",
        f"- Direct comparison present: `{md_bool(payload['browser']['direct_comparison_present'])}`",
        "",
        "## Browser Flows",
        "",
        "| Flow | Requests | Transfer KB | DOMContentLoaded ms | Load ms | Bulk | unpkg | Console errors | External hosts |",
        "|---|---:|---:|---:|---:|---|---|---:|---|",
    ]
    for row in payload["browser"]["flows"]:
        hosts = ", ".join(row["external_hosts"]) or "-"
        lines.append(
            f"| {row['name']} | {row['requests']} | {row['transfer_kb']} | "
            f"{row['dom_content_loaded_ms']} | {row['load_event_ms']} | "
            f"{md_bool(row['bulk'])} | {md_bool(row['unpkg'])} | "
            f"{row['console_errors']} | {hosts} |"
        )

    auth_rows_ = payload["auth_map_slot"]["rows"]
    if auth_rows_:
        lines.extend([
            "",
            "## Auth And Map-Slot Latency",
            "",
            "| Measurement | p50 ms | p95 ms | Target ms | Target met | Status codes |",
            "|---|---:|---:|---:|---|---|",
        ])
        for row in auth_rows_:
            lines.append(
                f"| {row['name']} | {row['p50_ms']} | {row['p95_ms']} | "
                f"{row['target_ms'] or '-'} | {md_bool(row['target_met']) if row['target_met'] is not None else '-'} | "
                f"{row['status_codes']} |"
            )

    route_rows_ = payload["route_probe"]["rows"]
    if route_rows_:
        lines.extend([
            "",
            "## Route Probe Latency",
            "",
            "| Route | Family | p50 ms | p95 ms | Status codes | OK |",
            "|---|---|---:|---:|---|---|",
        ])
        for row in route_rows_:
            route = f"{row['method']} {row['template']}"
            lines.append(
                f"| {route} | {row['family'] or '-'} | {row['p50_ms']} | "
                f"{row['p95_ms']} | {row['status_codes']} | {md_bool(row['ok'])} |"
            )

    lines.extend([
        "",
        "## DNS And TLS",
        "",
        f"- Preflight verdict: `{payload['preflight']['verdict'] or 'missing'}`",
        f"- DNS time: `{payload['preflight']['dns_ms'] if payload['preflight']['dns_ms'] is not None else 'missing'}` ms",
        f"- TLS time: `{payload['preflight']['tls_ms'] if payload['preflight']['tls_ms'] is not None else 'missing'}` ms",
    ])

    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in payload["failures"])
    if payload["warnings"]:
        lines.extend(["", "## Missing Optional Inputs", ""])
        lines.extend(f"- {item}" for item in payload["warnings"])

    lines.extend([
        "",
        "This generated report summarizes public-staging performance evidence only. Network-isolation, licensing, and browser-matrix gates still require their dedicated evidence files.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-summary", default=str(PERF_EVIDENCE / "26-public-staging-browser-har-summary.json"))
    parser.add_argument("--direct-summary", default="")
    parser.add_argument("--preflight", default=str(PUBLIC_EVIDENCE / "00-public-staging-preflight.json"))
    parser.add_argument("--auth-map-slot", default="")
    parser.add_argument("--route-probe", default=str(PERF_EVIDENCE / "25-public-route-family-probe.json"))
    parser.add_argument("--output", default=str(PUBLIC_EVIDENCE / "15-performance.md"))
    args = parser.parse_args()

    payload = build_payload(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(payload))
    print(f"Wrote public staging performance report to {output}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"], "warnings": payload["warnings"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
