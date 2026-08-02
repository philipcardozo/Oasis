#!/usr/bin/env python3
"""Generate public-staging browser matrix and map-provider evidence reports."""
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

BROWSER_CHECKS = {
    "application_shell": "application shell",
    "registration_login": "registration and login",
    "session_persistence": "session persistence",
    "no_reusable_local_storage_token": "no reusable token in localStorage",
    "standard_basemap": "Standard basemap",
    "dark_basemap": "Dark basemap",
    "satellite_disabled_or_failure": "Satellite disabled/failure behavior",
    "geographic_features": "geographic features",
    "search": "search",
    "entity_selection": "entity selection",
    "drawer_rail": "drawer and rail interactions",
    "three_map_slots": "three Map Studio slots",
    "export_workflow": "export workflow",
    "password_reset": "password reset",
    "logout": "logout",
    "responsive_layout": "responsive layout",
    "keyboard_navigation": "keyboard navigation",
    "basic_accessibility": "basic accessibility",
    "no_console_errors": "no unexpected console errors",
}

REQUIRED_DESKTOP_BROWSERS = {"chrome", "firefox", "safari_macos"}
OPTIONAL_MOBILE_BROWSERS = {"mobile_safari", "chrome_android"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
RESERVED_PUBLIC_HOSTS = {"example.com", "example.net", "example.org"}
RESERVED_PUBLIC_SUFFIXES = (".example.com", ".example.net", ".example.org", ".invalid", ".test")
PLACEHOLDER_MARKERS = ("<", ">", "replace-", "record exact", "required when")

MAP_CHECKS = {
    "vendored_maplibre": "vendored MapLibre asset loaded",
    "no_unpkg": "no unpkg.com requests",
    "no_provider_credentials": "no provider credentials leaked",
    "attribution_displayed": "attribution displayed where required",
    "standard_available": "Standard basemap available",
    "disabled_providers_unused": "disabled providers remained unused",
    "preferred_basemap_preserved_after_failure": "preferred basemap preserved after failure",
    "style_requests_expected": "style requests came from expected domains",
    "tile_requests_expected": "tile requests came from expected domains",
    "terrain_requests_expected_or_disabled": "terrain requests expected or disabled",
    "csp_ok": "CSP allowed required map behavior",
    "cors_ok": "CORS allowed required map behavior",
}


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text())


def display_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() and path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    return value


def flow_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, flow in sorted((summary.get("flows") or {}).items()):
        rows.append({
            "name": name,
            "flow": flow.get("flow") or name,
            "requested_bulk": bool(flow.get("requestedUniverseBulk")),
            "requested_unpkg": bool(flow.get("requestedUnpkg")),
            "console_errors": len(flow.get("consoleErrors") or []),
            "failed_requests": int(flow.get("failedRequestCount") or 0),
            "external_hosts": flow.get("externalHosts") or [],
            "har_path": flow.get("harPath"),
        })
    return rows


def first_paint(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if "first-paint" in row["name"] or "first paint" in row["flow"]:
            return row
    return rows[0] if rows else None


def browser_key(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def normalized_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/")


def has_placeholder(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return any(marker in text for marker in PLACEHOLDER_MARKERS)


def public_https_url_failures(value: Any, label: str) -> list[str]:
    url = normalized_url(value)
    if not url:
        return [f"{label} base URL is missing"]
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return [f"{label} base URL is not HTTPS"]
    hostname = (parsed.hostname or "").lower()
    if hostname in LOCAL_HOSTS or hostname.endswith(".local"):
        return [f"{label} base URL is not public"]
    if hostname in RESERVED_PUBLIC_HOSTS or hostname.endswith(RESERVED_PUBLIC_SUFFIXES):
        return [f"{label} base URL is a reserved documentation hostname"]
    return []


def evaluate_target(matrix: dict[str, Any], browser_summary: dict[str, Any]) -> list[str]:
    failures = []
    matrix_url = normalized_url(matrix.get("base_url"))
    summary_url = normalized_url(browser_summary.get("baseUrl"))
    if matrix.get("not_public_staging_proof") is True:
        failures.append("browser matrix is still marked not public-staging proof")
    if matrix.get("verdict") == "operator_input_required":
        failures.append("browser matrix still requires operator input")
    failures.extend(public_https_url_failures(matrix_url, "browser matrix"))
    failures.extend(public_https_url_failures(summary_url, "browser HAR summary"))
    if matrix_url and summary_url and matrix_url != summary_url:
        failures.append("browser matrix and HAR summary base URLs do not match")
    return failures


def evaluate_browser_matrix(matrix: dict[str, Any], browser_summary: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    failures: list[str] = []
    browser_rows: list[dict[str, Any]] = []
    network_rows = flow_rows(browser_summary)
    entries = matrix.get("browsers") or []
    by_key = {browser_key(item.get("name", "")): item for item in entries}

    for key in sorted(REQUIRED_DESKTOP_BROWSERS):
        if key not in by_key:
            failures.append(f"required browser is missing: {key}")

    for key in sorted(OPTIONAL_MOBILE_BROWSERS):
        item = by_key.get(key)
        if not item:
            failures.append(f"mobile browser availability was not recorded: {key}")
        elif item.get("available") is False and not item.get("unavailable_reason"):
            failures.append(f"{key} is unavailable without a reason")

    for item in entries:
        key = browser_key(item.get("name", ""))
        checks = item.get("checks") or {}
        available = item.get("available", True)
        row = {
            "key": key,
            "name": item.get("name"),
            "browser_version": item.get("browser_version"),
            "os": item.get("os"),
            "os_version": item.get("os_version"),
            "available": available,
            "unavailable_reason": item.get("unavailable_reason"),
            "failed_checks": [],
        }
        if available is not False:
            for field in ("browser_version", "os", "os_version"):
                if has_placeholder(item.get(field)):
                    failures.append(f"{key} has placeholder browser field: {field}")
            for check_key in BROWSER_CHECKS:
                if checks.get(check_key) is not True:
                    row["failed_checks"].append(check_key)
                    failures.append(f"{key} failed browser check: {check_key}")
        elif item.get("unavailable_reason") and has_placeholder(item.get("unavailable_reason")):
            failures.append(f"{key} unavailable reason is still a placeholder")
        browser_rows.append(row)

    first = first_paint(network_rows)
    if not network_rows:
        failures.append("public browser HAR summary has no flows")
    if first and first["requested_bulk"]:
        failures.append("first paint requested /api/universe/bulk")
    if any(row["requested_unpkg"] for row in network_rows):
        failures.append("browser capture requested unpkg.com")
    if any(row["console_errors"] for row in network_rows):
        failures.append("browser capture recorded console errors")
    if any(row["failed_requests"] for row in network_rows):
        failures.append("browser capture recorded failed requests")
    for row in network_rows:
        name = row.get("name") or "unknown flow"
        har_path = str(row.get("har_path") or "")
        if (
            not har_path.startswith("docs/evidence/performance/")
            or not har_path.endswith(".har")
            or not (ROOT / har_path).is_file()
        ):
            failures.append(f"browser capture HAR path is missing or invalid: {name}")

    return failures, browser_rows, network_rows


def evaluate_map_provider(matrix: dict[str, Any], browser_summary: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    failures: list[str] = []
    rows: list[dict[str, Any]] = []
    map_provider = matrix.get("map_provider") or {}
    checks = map_provider.get("checks") or {}
    for key, label in MAP_CHECKS.items():
        value = checks.get(key)
        rows.append({"key": key, "label": label, "value": value})
        if value is not True:
            failures.append(f"map provider check is not true: {key}")

    approved_hosts = sorted(map_provider.get("approved_hosts") or [])
    if not approved_hosts:
        failures.append("approved map provider hosts are missing")
    for host in approved_hosts:
        if has_placeholder(host):
            failures.append(f"approved map provider host is still a placeholder: {host}")

    observed = sorted({host for row in flow_rows(browser_summary) for host in row["external_hosts"]})
    unexpected = [host for host in observed if host not in approved_hosts]
    if unexpected:
        failures.append(f"browser capture used unexpected external hosts: {', '.join(unexpected)}")
    return failures, rows, observed


def build_payload(matrix: dict[str, Any], browser_summary: dict[str, Any], matrix_path: str, summary_path: str) -> dict[str, Any]:
    target_failures = evaluate_target(matrix, browser_summary)
    browser_failures, browser_rows, network_rows = evaluate_browser_matrix(matrix, browser_summary)
    browser_failures = [*target_failures, *browser_failures]
    map_failures, map_rows, observed_hosts = evaluate_map_provider(matrix, browser_summary)
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "inputs": {
            "browser_matrix": display_path(matrix_path),
            "browser_summary": display_path(summary_path),
        },
        "target": {
            "matrix_base_url": matrix.get("base_url"),
            "summary_base_url": browser_summary.get("baseUrl"),
            "matrix_not_public_staging_proof": matrix.get("not_public_staging_proof"),
            "matrix_verdict": matrix.get("verdict"),
        },
        "browser": {
            "source_captured_at": matrix.get("captured_at"),
            "summary_captured_at": browser_summary.get("capturedAt"),
            "rows": browser_rows,
            "network_rows": network_rows,
            "failures": browser_failures,
            "verdict": "pass" if not browser_failures else "investigate",
        },
        "map_provider": {
            "rows": map_rows,
            "approved_hosts": sorted((matrix.get("map_provider") or {}).get("approved_hosts") or []),
            "observed_external_hosts": observed_hosts,
            "failures": map_failures,
            "verdict": "pass" if not map_failures else "investigate",
        },
    }


def browser_markdown(payload: dict[str, Any]) -> str:
    browser = payload["browser"]
    lines = [
        "# Public Staging Browser Matrix Evidence",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Base URL: `{payload['target']['matrix_base_url'] or payload['target']['summary_base_url']}`",
        f"Verdict: **{browser['verdict']}**",
        "",
        "## Browser Matrix",
        "",
        "| Browser | Version | OS | Available | Failed checks |",
        "|---|---|---|---|---|",
    ]
    for row in browser["rows"]:
        failed = ", ".join(row["failed_checks"]) or "-"
        os_value = " ".join(str(part) for part in (row.get("os"), row.get("os_version")) if part)
        lines.append(f"| {row['name']} | {row['browser_version']} | {os_value} | {row['available']} | {failed} |")
    lines.extend([
        "",
        "## Captured Network Flows",
        "",
        "| Flow | Bulk | unpkg | Console errors | Failed requests | HAR | External hosts |",
        "|---|---|---|---|---|---|---|",
    ])
    for row in browser["network_rows"]:
        lines.append(
            f"| {row['flow']} | `{row['requested_bulk']}` | `{row['requested_unpkg']}` | "
            f"`{row['console_errors']}` | `{row['failed_requests']}` | `{row.get('har_path') or '-'}` | "
            f"`{', '.join(row['external_hosts']) or '-'}` |"
        )
    if browser["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in browser["failures"])
    lines.append("")
    lines.append("This generated report contains browser/OS versions and sanitized network summary only.")
    return "\n".join(lines) + "\n"


def map_markdown(payload: dict[str, Any]) -> str:
    provider = payload["map_provider"]
    lines = [
        "# Public Staging Map Provider Evidence",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Base URL: `{payload['target']['matrix_base_url'] or payload['target']['summary_base_url']}`",
        f"Verdict: **{provider['verdict']}**",
        "",
        "## Provider Checks",
        "",
        "| Check | Value |",
        "|---|---|",
    ]
    for row in provider["rows"]:
        lines.append(f"| {row['label']} | `{row['value']}` |")
    lines.extend([
        "",
        f"- Approved hosts: `{', '.join(provider['approved_hosts']) or 'missing'}`",
        f"- Observed external hosts: `{', '.join(provider['observed_external_hosts']) or 'none'}`",
    ])
    if provider["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in provider["failures"])
    lines.append("")
    lines.append("This generated report contains no map-provider credentials or private access tokens.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-matrix", default=str(PUBLIC_EVIDENCE / "browser-matrix.json"))
    parser.add_argument("--browser-summary", default=str(PERF_EVIDENCE / "26-public-staging-browser-har-summary.json"))
    parser.add_argument("--browser-output", default=str(PUBLIC_EVIDENCE / "07-browser-matrix.md"))
    parser.add_argument("--map-output", default=str(PUBLIC_EVIDENCE / "08-map-provider-capture.md"))
    parser.add_argument("--summary-output", default=str(PUBLIC_EVIDENCE / "browser-map-summary.json"))
    args = parser.parse_args()

    matrix = load_json(Path(args.browser_matrix))
    summary = load_json(Path(args.browser_summary))
    payload = build_payload(matrix, summary, args.browser_matrix, args.browser_summary)
    browser_output = Path(args.browser_output)
    map_output = Path(args.map_output)
    browser_output.parent.mkdir(parents=True, exist_ok=True)
    map_output.parent.mkdir(parents=True, exist_ok=True)
    browser_output.write_text(browser_markdown(payload))
    map_output.write_text(map_markdown(payload))
    summary_output = Path(args.summary_output)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    failures = {
        key: payload[key]["failures"]
        for key in ("browser", "map_provider")
        if payload[key]["verdict"] != "pass"
    }
    print(f"Wrote public browser matrix report to {browser_output}")
    print(f"Wrote public map provider report to {map_output}")
    print(json.dumps({"verdict": "pass" if not failures else "investigate", "failures": failures}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
