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

LOCATION_REQUIRED = {
    "dns_ms": "DNS time",
    "tcp_ms": "TCP connection time",
    "tls_ms": "TLS time",
    "ttfb_ms": "TTFB",
    "initial_transfer_kb": "initial transferred KB",
    "initial_request_count": "initial request count",
    "map_initialization_ms": "map initialization time",
}

APP_LAYER_REQUIRED = {
    "search": "search p50/p95",
    "comps": "comps p50/p95",
    "export_job_creation": "export-job creation p50/p95",
}

RUNTIME_REQUIRED = {
    "api_cpu_percent": "API CPU percent",
    "api_memory_mb": "API memory MB",
    "worker_cpu_percent": "worker CPU percent",
    "worker_memory_mb": "worker memory MB",
    "database_connections": "database connections",
    "queue_depth": "queue depth",
    "error_rate": "error rate",
}

WEB_VITAL_REQUIRED = {
    "lcp_ms": ("LCP", 2500),
    "inp_ms": ("INP", 200),
    "cls": ("CLS", 0.1),
    "fcp_ms": ("FCP", 1800),
    "ttfb_ms": ("TTFB", 800),
    "tbt_ms": ("TBT", 200),
}
POSITIVE_WEB_VITALS = {"lcp_ms", "inp_ms", "fcp_ms", "ttfb_ms"}


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


def flow_failures(rows: list[dict[str, Any]], label: str) -> list[str]:
    failures: list[str] = []
    first = first_paint(rows)
    if not first:
        failures.append(f"{label} summary has no captured flows")
    elif first["bulk"]:
        failures.append(f"{label} first paint requested /api/universe/bulk")

    if any(row["unpkg"] for row in rows):
        failures.append(f"{label} capture requested unpkg.com")
    if any(row["console_errors"] for row in rows):
        failures.append(f"{label} capture recorded console errors")
    if any(row["failed_requests"] for row in rows):
        failures.append(f"{label} capture recorded failed requests")
    return failures


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


def supplemental_template() -> dict[str, Any]:
    return {
        "input_captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": "https://staging.example.com",
        "secret_free_evidence": True,
        "external_locations": [
            {
                "name": "replace-with-location-1",
                "region": "replace-with-region-1",
                "dns_ms": 0,
                "tcp_ms": 0,
                "tls_ms": 0,
                "ttfb_ms": 0,
                "initial_transfer_kb": 0,
                "initial_request_count": 0,
                "map_initialization_ms": 0,
            },
            {
                "name": "replace-with-location-2",
                "region": "replace-with-region-2",
                "dns_ms": 0,
                "tcp_ms": 0,
                "tls_ms": 0,
                "ttfb_ms": 0,
                "initial_transfer_kb": 0,
                "initial_request_count": 0,
                "map_initialization_ms": 0,
            },
        ],
        "app_layer": {
            "search": {"p50_ms": 0, "p95_ms": 0, "target_ms": None, "target_met": True},
            "comps": {"p50_ms": 0, "p95_ms": 0, "target_ms": 500, "target_met": True},
            "export_job_creation": {"p50_ms": 0, "p95_ms": 0, "target_ms": None, "target_met": True},
        },
        "runtime_resources": {
            "api_cpu_percent": 0,
            "api_memory_mb": 0,
            "worker_cpu_percent": 0,
            "worker_memory_mb": 0,
            "database_connections": 0,
            "queue_depth": 0,
            "error_rate": 0,
        },
        "web_vitals": {
            "lcp_ms": 0,
            "inp_ms": 0,
            "cls": 0,
            "fcp_ms": 0,
            "ttfb_ms": 0,
            "tbt_ms": 0,
        },
    }


def supplemental_location_rows(supplemental: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not supplemental:
        return []
    rows = []
    for item in supplemental.get("external_locations") or []:
        row = {
            "name": item.get("name"),
            "region": item.get("region"),
        }
        row.update({key: item.get(key) for key in LOCATION_REQUIRED})
        rows.append(row)
    return rows


def supplemental_app_rows(supplemental: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not supplemental:
        return []
    rows = []
    app = supplemental.get("app_layer") or {}
    for key, label in APP_LAYER_REQUIRED.items():
        item = app.get(key) or {}
        rows.append({
            "key": key,
            "label": label,
            "p50_ms": item.get("p50_ms"),
            "p95_ms": item.get("p95_ms"),
            "target_ms": item.get("target_ms"),
            "target_met": item.get("target_met"),
        })
    return rows


def supplemental_runtime_rows(supplemental: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not supplemental:
        return []
    resources = supplemental.get("runtime_resources") or {}
    return [
        {"key": key, "label": label, "value": resources.get(key)}
        for key, label in RUNTIME_REQUIRED.items()
    ]


def supplemental_vital_rows(supplemental: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not supplemental:
        return []
    vitals = supplemental.get("web_vitals") or {}
    return [
        {
            "key": key,
            "label": label,
            "value": vitals.get(key),
            "good_threshold": threshold,
        }
        for key, (label, threshold) in WEB_VITAL_REQUIRED.items()
    ]


def non_negative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and value >= 0


def evaluate(
    browser_rows: list[dict[str, Any]],
    direct_rows: list[dict[str, Any]] | None,
    browser_base_url: str,
    direct_base_url: str,
    direct_proxy_server: Any,
    preflight: dict[str, Any] | None,
    auth: dict[str, Any] | None,
    route_probe: dict[str, Any] | None,
    supplemental: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []

    failures.extend(flow_failures(browser_rows, "browser"))

    if direct_rows is None:
        failures.append("direct browser comparison input is missing")
    else:
        if safe_url(browser_base_url) != safe_url(direct_base_url):
            failures.append("direct browser comparison base URL does not match proxied capture")
        if direct_proxy_server:
            failures.append("direct browser comparison unexpectedly records a proxy server")
        failures.extend(flow_failures(direct_rows, "direct browser"))

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

    if supplemental is None:
        warnings.append("supplemental public performance evidence missing; external-location and runtime-resource metrics are not summarized")
    else:
        if not supplemental.get("input_captured_at"):
            failures.append("supplemental performance input captured timestamp is missing")
        if urlparse(str(supplemental.get("base_url") or "")).scheme != "https":
            failures.append("supplemental performance base URL is not HTTPS")
        if supplemental.get("secret_free_evidence") is not True:
            failures.append("supplemental performance evidence is not marked secret-free")

        location_rows = supplemental_location_rows(supplemental)
        if len(location_rows) < 2:
            failures.append("fewer than two external performance locations are recorded")
        for row in location_rows:
            name = row.get("name") or "unknown location"
            if not row.get("name") or not row.get("region"):
                failures.append(f"external performance location identity is incomplete: {name}")
            for key in LOCATION_REQUIRED:
                value = row.get(key)
                if not non_negative_number(value):
                    failures.append(f"external performance location {name} missing non-negative {key}")
            if not isinstance(row.get("initial_request_count"), int) or int(row.get("initial_request_count") or 0) <= 0:
                failures.append(f"external performance location {name} initial_request_count is not positive")
            if not non_negative_number(row.get("initial_transfer_kb")) or float(row.get("initial_transfer_kb") or 0) <= 0:
                failures.append(f"external performance location {name} initial_transfer_kb is not positive")

        for row in supplemental_app_rows(supplemental):
            key = row["key"]
            if not non_negative_number(row.get("p50_ms")):
                failures.append(f"supplemental app-layer {key} p50_ms is missing")
            if not non_negative_number(row.get("p95_ms")):
                failures.append(f"supplemental app-layer {key} p95_ms is missing")
            if row.get("target_met") is not True:
                failures.append(f"supplemental app-layer {key} target is not met")

        for row in supplemental_runtime_rows(supplemental):
            if not non_negative_number(row.get("value")):
                failures.append(f"runtime resource metric is missing: {row['key']}")

        for row in supplemental_vital_rows(supplemental):
            key = row["key"]
            value = row.get("value")
            if not non_negative_number(value):
                failures.append(f"web vital metric is missing: {key}")
            elif key in POSITIVE_WEB_VITALS and float(value) <= 0:
                failures.append(f"web vital metric is not positive: {key}")
            elif float(value) > float(row["good_threshold"]):
                failures.append(f"web vital metric exceeds good threshold: {key}")

    return failures, warnings


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    browser = load_json(Path(args.browser_summary), required=True) or {}
    direct = load_json(Path(args.direct_summary)) if args.direct_summary else None
    preflight = load_json(Path(args.preflight)) if args.preflight else None
    auth = load_json(Path(args.auth_map_slot)) if args.auth_map_slot else None
    route_probe = load_json(Path(args.route_probe)) if args.route_probe else None
    supplemental = load_json(Path(args.supplemental)) if args.supplemental else None

    browser_rows = flow_rows(browser)
    direct_rows = flow_rows(direct) if direct else None
    failures, warnings = evaluate(
        browser_rows,
        direct_rows,
        str(browser.get("baseUrl") or ""),
        str(direct.get("baseUrl") or "") if direct else "",
        direct.get("proxyServer") if direct else None,
        preflight,
        auth,
        route_probe,
        supplemental,
    )

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "inputs": {
            "browser_summary": display_path(args.browser_summary),
            "direct_summary": display_path(args.direct_summary) if args.direct_summary else "",
            "preflight": display_path(args.preflight) if args.preflight else "",
            "auth_map_slot": display_path(args.auth_map_slot) if args.auth_map_slot else "",
            "route_probe": display_path(args.route_probe) if args.route_probe else "",
            "supplemental": display_path(args.supplemental) if args.supplemental else "",
        },
        "target": {
            "base_url": safe_url(browser.get("baseUrl")),
            "proxy_server": browser.get("proxyServer"),
            "direct_base_url": safe_url(direct.get("baseUrl")) if direct else None,
            "direct_proxy_server": direct.get("proxyServer") if direct else None,
        },
        "browser": {
            "captured_at": browser.get("capturedAt"),
            "flows": browser_rows,
            "direct_comparison_present": bool(direct),
            "direct_flows": direct_rows or [],
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
        "supplemental": {
            "input_captured_at": supplemental.get("input_captured_at") if supplemental else None,
            "base_url": safe_url(supplemental.get("base_url")) if supplemental else None,
            "external_locations": supplemental_location_rows(supplemental),
            "app_layer": supplemental_app_rows(supplemental),
            "runtime_resources": supplemental_runtime_rows(supplemental),
            "web_vitals": supplemental_vital_rows(supplemental),
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
        f"- Direct base URL: `{payload['target']['direct_base_url'] or 'not recorded'}`",
        f"- Direct proxy: `{payload['target']['direct_proxy_server'] or 'not recorded'}`",
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

    if payload["browser"]["direct_flows"]:
        lines.extend([
            "",
            "## Direct Browser Flows",
            "",
            "| Flow | Requests | Transfer KB | DOMContentLoaded ms | Load ms | Bulk | unpkg | Console errors | External hosts |",
            "|---|---:|---:|---:|---:|---|---|---:|---|",
        ])
        for row in payload["browser"]["direct_flows"]:
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

    supplemental = payload["supplemental"]
    if supplemental["external_locations"]:
        lines.extend([
            "",
            "## External Locations",
            "",
            "| Location | Region | DNS ms | TCP ms | TLS ms | TTFB ms | Initial KB | Initial requests | Map init ms |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for row in supplemental["external_locations"]:
            lines.append(
                f"| {row['name']} | {row['region']} | {row['dns_ms']} | {row['tcp_ms']} | "
                f"{row['tls_ms']} | {row['ttfb_ms']} | {row['initial_transfer_kb']} | "
                f"{row['initial_request_count']} | {row['map_initialization_ms']} |"
            )

    if supplemental["app_layer"]:
        lines.extend([
            "",
            "## Supplemental App-Layer Latency",
            "",
            "| Measurement | p50 ms | p95 ms | Target ms | Target met |",
            "|---|---:|---:|---:|---|",
        ])
        for row in supplemental["app_layer"]:
            lines.append(
                f"| {row['label']} | {row['p50_ms']} | {row['p95_ms']} | "
                f"{row['target_ms'] if row['target_ms'] is not None else '-'} | {md_bool(row['target_met'])} |"
            )

    if supplemental["runtime_resources"]:
        lines.extend([
            "",
            "## Runtime Resources",
            "",
            "| Metric | Value |",
            "|---|---:|",
        ])
        for row in supplemental["runtime_resources"]:
            lines.append(f"| {row['label']} | {row['value']} |")

    if supplemental["web_vitals"]:
        lines.extend([
            "",
            "## Web Vitals",
            "",
            "| Metric | Value | Good threshold |",
            "|---|---:|---:|",
        ])
        for row in supplemental["web_vitals"]:
            lines.append(f"| {row['label']} | {row['value']} | {row['good_threshold']} |")

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
    parser.add_argument("--print-supplemental-template", action="store_true", help="print a non-secret supplemental performance evidence template and exit")
    parser.add_argument("--browser-summary", default=str(PERF_EVIDENCE / "26-public-staging-browser-har-summary.json"))
    parser.add_argument("--direct-summary", default="")
    parser.add_argument("--preflight", default=str(PUBLIC_EVIDENCE / "00-public-staging-preflight.json"))
    parser.add_argument("--auth-map-slot", default="")
    parser.add_argument("--route-probe", default=str(PERF_EVIDENCE / "25-public-route-family-probe.json"))
    parser.add_argument("--supplemental", default=str(PUBLIC_EVIDENCE / "performance-supplemental.json"))
    parser.add_argument("--output", default=str(PUBLIC_EVIDENCE / "15-performance.md"))
    parser.add_argument("--summary-output", default=str(PUBLIC_EVIDENCE / "performance-evidence-summary.json"))
    args = parser.parse_args()

    if args.print_supplemental_template:
        print(json.dumps(supplemental_template(), indent=2, sort_keys=True))
        return 0

    payload = build_payload(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(payload))
    summary_output = Path(args.summary_output)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging performance report to {output}")
    print(f"Wrote public staging performance summary to {summary_output}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"], "warnings": payload["warnings"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
