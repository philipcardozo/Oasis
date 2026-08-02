#!/usr/bin/env python3
"""Build public-staging route-security evidence from probe summaries."""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PERF_EVIDENCE = ROOT / "docs" / "evidence" / "performance"
PUBLIC_EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
AUTH_INVENTORY = ROOT / "docs" / "evidence" / "phase-1-5" / "route-authorization-inventory.json"
LOCAL_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
RESERVED_PUBLIC_HOSTS = {"example.com", "example.net", "example.org"}
RESERVED_PUBLIC_SUFFIXES = (".example.com", ".example.net", ".example.org", ".invalid", ".test")


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


def display_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() and path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    return value


def normalized_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/")


def public_https_url_failures(value: Any, label: str) -> list[str]:
    url = normalized_url(value)
    if not url:
        return [f"{label} base URL is missing"]
    parsed = urlparse(url)
    failures: list[str] = []
    if parsed.scheme != "https":
        failures.append(f"{label} base URL is not HTTPS")
    hostname = (parsed.hostname or "").lower()
    if hostname in LOCAL_PUBLIC_HOSTS or hostname.endswith(".local"):
        failures.append(f"{label} base URL is not public")
    if hostname in RESERVED_PUBLIC_HOSTS or hostname.endswith(RESERVED_PUBLIC_SUFFIXES):
        failures.append(f"{label} base URL is a reserved documentation hostname")
    return failures


def same_base_url(left: Any, right: Any) -> bool:
    return normalized_url(left) == normalized_url(right)


def status_subset(item: dict[str, Any], allowed: set[int]) -> bool:
    return set(item.get("status_codes") or []).issubset(allowed)


def route_measurements(route_probe: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not route_probe:
        return []
    return list(route_probe.get("measurements") or [])


def find_measurement(measurements: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for item in measurements:
        if item.get("name") == name:
            return item
    return None


def staging_inventory(inventory: dict[str, Any] | None) -> dict[str, Any] | None:
    if not inventory:
        return None
    for item in inventory.get("inventories") or []:
        if item.get("label") == "staging-secure":
            return item
    return None


def auth_checks(auth_security: dict[str, Any] | None) -> dict[str, Any]:
    if not auth_security:
        return {}
    checks = dict(auth_security.get("checks") or {})
    csrf = auth_security.get("csrf_rejection") or checks.get("csrf_rejection")
    if csrf:
        checks["csrf_rejection_status"] = csrf.get("status_code")
    if "default_map_slot_count" not in checks and auth_security.get("default_map_slot_count") is not None:
        checks["default_map_slot_count"] = auth_security.get("default_map_slot_count")
    if "default_map_slot_numbers" not in checks and auth_security.get("default_map_slot_numbers") is not None:
        checks["default_map_slot_numbers"] = auth_security.get("default_map_slot_numbers")
    return checks


def evaluate(
    route_probe: dict[str, Any] | None,
    preflight: dict[str, Any] | None,
    inventory: dict[str, Any] | None,
    auth_security: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    measurements = route_measurements(route_probe)

    if route_probe is None:
        failures.append("public route probe is missing")
    elif route_probe.get("verdict") != "pass" or route_probe.get("failure_count"):
        failures.append("public route probe verdict is not pass")
    elif route_probe.get("base_url"):
        failures.extend(public_https_url_failures(route_probe.get("base_url"), "public route probe"))
    else:
        failures.append("public route probe base URL is missing")

    failed_routes = [item for item in measurements if item.get("ok") is False]
    if failed_routes:
        failures.append(f"{len(failed_routes)} public route probe measurements failed")

    expected_unauth = {
        "map slots unauthenticated",
        "auth me unauthenticated",
        "auth sessions unauthenticated",
    }
    seen_unauth = {item.get("name") for item in measurements if item.get("name") in expected_unauth}
    missing_unauth = sorted(expected_unauth - seen_unauth)
    if missing_unauth:
        failures.append(f"missing unauthenticated rejection probes: {', '.join(missing_unauth)}")
    for name in sorted(expected_unauth & seen_unauth):
        item = find_measurement(measurements, name) or {}
        if not status_subset(item, {401, 403}):
            failures.append(f"{name} did not reject with 401/403")

    if preflight is None:
        failures.append("public preflight is missing")
    elif preflight.get("verdict") != "pass":
        failures.append("public preflight verdict is not pass")
    else:
        failures.extend(public_https_url_failures(preflight.get("base_url"), "public preflight"))
        if route_probe and route_probe.get("base_url") and preflight.get("base_url") and not same_base_url(route_probe.get("base_url"), preflight.get("base_url")):
            failures.append("public preflight base URL does not match route probe")

    headers = ((preflight or {}).get("endpoints") or {}).get("/index.html", {}).get("headers", {})
    for header in ("content-security-policy", "strict-transport-security", "x-content-type-options", "referrer-policy", "permissions-policy"):
        if preflight is not None and not headers.get(header):
            failures.append(f"public preflight did not record {header}")

    secure_inventory = staging_inventory(inventory)
    if secure_inventory is None:
        failures.append("staging-secure route authorization inventory is missing")
    else:
        if secure_inventory.get("unique_method_paths") != 92:
            failures.append(f"staging-secure route inventory count changed: {secure_inventory.get('unique_method_paths')}")
        if secure_inventory.get("duplicate_method_paths"):
            failures.append("route authorization inventory has duplicate method/path entries")
        if secure_inventory.get("docs_paths_present"):
            failures.append("secure-mode documentation routes are present")

    checks = auth_checks(auth_security)
    if not auth_security:
        failures.append("auth/CSRF/cross-user security evidence is missing")
    else:
        failures.extend(public_https_url_failures(auth_security.get("base_url"), "auth/security"))
        if route_probe and route_probe.get("base_url") and auth_security.get("base_url") and not same_base_url(route_probe.get("base_url"), auth_security.get("base_url")):
            failures.append("auth/security base URL does not match route probe")
        if checks.get("csrf_rejection_status") != 403:
            failures.append("CSRF rejection status is not 403")
        if checks.get("cross_user_slot_read_denied", {}).get("status_code") not in {403, 404}:
            failures.append("cross-user map-slot denial is missing or not 403/404")
        if checks.get("stale_version_conflict", {}).get("status_code") != 409:
            warnings.append("map-slot conflict evidence is missing or not 409")
        if checks.get("default_map_slot_count") != 3 or checks.get("default_map_slot_numbers") != [1, 2, 3]:
            failures.append("exactly-three map-slot evidence is missing")
        if checks.get("fourth_slot_create_attempt", {}).get("status_code") not in {404, 405, 409, 422}:
            failures.append("fourth map-slot create attempt was not rejected")
        if checks.get("fourth_slot_import_attempt", {}).get("status_code") != 422:
            failures.append("fourth map-slot import attempt was not rejected with 422")

    return failures, warnings


def summarize_routes(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(measurements),
        "families": dict(Counter(item.get("family") or "unknown" for item in measurements)),
        "unauthenticated": [
            {
                "name": item.get("name"),
                "template": item.get("template"),
                "status_codes": item.get("status_codes"),
                "ok": item.get("ok"),
            }
            for item in measurements
            if item.get("name") in {"map slots unauthenticated", "auth me unauthenticated", "auth sessions unauthenticated"}
        ],
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    route_probe = load_json(Path(args.route_probe), required=True)
    preflight = load_json(Path(args.preflight), required=True)
    inventory = load_json(Path(args.inventory), required=True)
    auth_security = load_json(Path(args.auth_security)) if args.auth_security else None

    failures, warnings = evaluate(route_probe, preflight, inventory, auth_security)
    measurements = route_measurements(route_probe)
    secure_inventory = staging_inventory(inventory)
    checks = auth_checks(auth_security)
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "inputs": {
            "route_probe": display_path(args.route_probe),
            "preflight": display_path(args.preflight),
            "inventory": display_path(args.inventory),
            "auth_security": display_path(args.auth_security) if args.auth_security else "",
        },
        "route_probe": {
            "captured_at": route_probe.get("captured_at"),
            "base_url": route_probe.get("base_url"),
            "verdict": route_probe.get("verdict"),
            "failure_count": route_probe.get("failure_count"),
            "summary": summarize_routes(measurements),
        },
        "preflight": {
            "captured_at": preflight.get("captured_at"),
            "base_url": preflight.get("base_url"),
            "verdict": preflight.get("verdict"),
            "index_headers": sorted((((preflight.get("endpoints") or {}).get("/index.html") or {}).get("headers") or {}).keys()),
        },
        "inventory": {
            "generated_on": inventory.get("generated_on"),
            "unique_method_paths": secure_inventory.get("unique_method_paths") if secure_inventory else None,
            "class_summary": secure_inventory.get("class_summary") if secure_inventory else {},
        },
        "auth_security": {
            "captured_at": auth_security.get("captured_at") if auth_security else None,
            "base_url": auth_security.get("base_url") if auth_security else None,
            "verdict": auth_security.get("verdict") if auth_security else None,
            "csrf_rejection_status": checks.get("csrf_rejection_status"),
            "cross_user_status": checks.get("cross_user_slot_read_denied", {}).get("status_code"),
            "stale_conflict_status": checks.get("stale_version_conflict", {}).get("status_code"),
            "default_map_slot_count": checks.get("default_map_slot_count"),
            "default_map_slot_numbers": checks.get("default_map_slot_numbers"),
            "fourth_slot_create_status": checks.get("fourth_slot_create_attempt", {}).get("status_code"),
            "fourth_slot_import_status": checks.get("fourth_slot_import_attempt", {}).get("status_code"),
        },
        "failures": failures,
        "warnings": warnings,
        "verdict": "pass" if not failures else "investigate",
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Route Security Evidence",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Verdict: **{payload['verdict']}**",
        "",
        "## Route Probe",
        "",
        f"- Base URL: `{payload['route_probe']['base_url']}`",
        f"- Probe verdict: `{payload['route_probe']['verdict']}`",
        f"- Measurements: `{payload['route_probe']['summary']['count']}`",
        f"- Failure count: `{payload['route_probe']['failure_count']}`",
        "",
        "### Unauthenticated Rejections",
        "",
        "| Probe | Route | Status codes | OK |",
        "|---|---|---|---|",
    ]
    for item in payload["route_probe"]["summary"]["unauthenticated"]:
        lines.append(f"| {item['name']} | {item['template']} | {item['status_codes']} | {item['ok']} |")

    lines.extend([
        "",
        "## Security Headers And Inventory",
        "",
        f"- Preflight base URL: `{payload['preflight']['base_url']}`",
        f"- Preflight verdict: `{payload['preflight']['verdict']}`",
        f"- `/index.html` headers recorded: `{', '.join(payload['preflight']['index_headers'])}`",
        f"- Staging-secure route count: `{payload['inventory']['unique_method_paths']}`",
        "",
        "## Auth And Authorization Checks",
        "",
        f"- Auth evidence base URL: `{payload['auth_security']['base_url'] or 'missing'}`",
        f"- Auth evidence verdict: `{payload['auth_security']['verdict'] or 'missing'}`",
        f"- CSRF rejection status: `{payload['auth_security']['csrf_rejection_status']}`",
        f"- Cross-user slot denial status: `{payload['auth_security']['cross_user_status']}`",
        f"- Stale version conflict status: `{payload['auth_security']['stale_conflict_status']}`",
        f"- Default map slots: `{payload['auth_security']['default_map_slot_numbers']}`",
        f"- Fourth slot create attempt status: `{payload['auth_security']['fourth_slot_create_status']}`",
        f"- Fourth slot import attempt status: `{payload['auth_security']['fourth_slot_import_status']}`",
    ])
    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in payload["failures"])
    if payload["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in payload["warnings"])
    lines.append("")
    lines.append("This generated report contains no secrets, cookies, private URLs with tokens, or authorization header values.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route-probe", default=str(PERF_EVIDENCE / "25-public-route-family-probe.json"))
    parser.add_argument("--preflight", default=str(PUBLIC_EVIDENCE / "00-public-staging-preflight.json"))
    parser.add_argument("--inventory", default=str(AUTH_INVENTORY))
    parser.add_argument("--auth-security", default="")
    parser.add_argument("--output", default=str(PUBLIC_EVIDENCE / "09-route-security.md"))
    parser.add_argument("--summary-output", default=str(PUBLIC_EVIDENCE / "route-security-summary.json"))
    args = parser.parse_args()

    payload = build_payload(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(payload))
    summary_output = Path(args.summary_output)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging route-security report to {output}")
    print(f"Wrote public staging route-security summary to {summary_output}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"], "warnings": payload["warnings"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
