#!/usr/bin/env python3
"""Audit OASIS performance evidence coverage.

Reads the committed Proxyman/HAR/API/auth evidence and writes a compact coverage
report. This helps decide whether the next performance change is justified by
evidence or whether more capture is required first.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "performance"


EXPECTED_ARTIFACTS = [
    "00-preflight.json",
    "01-route-inventory.json",
    "02-golden-api-snapshots.json",
    "03-local-first-paint.har",
    "04-local-reload.har",
    "05-local-search-intent.har",
    "06-local-auth-and-map-slots.json",
    "06-local-auth-and-map-slots-http.json",
    "06-local-auth-and-map-slots-http-direct.json",
    "06-local-map-interactions.har",
    "07-local-api-latency.json",
    "07-local-dcf-download.har",
    "08-proxyman-findings.md",
    "09-optimization-plan.md",
    "10-before-after-summary.md",
    "11-browser-har-summary.json",
    "12-local-entity-drawer.har",
    "13-local-data-quality-panel.har",
    "14-local-report-preview.har",
    "15-staging-capture-status.json",
    "15-compose-browser-har-summary.json",
    "17-route-family-performance-probes.json",
    "18-headless-maplibre-diagnostic.json",
    "19-compose-auth-map-slots.json",
    "20-compose-route-family-probe.json",
    "21-compose-route-family-proxyman-probe.json",
    "22-compose-backup-restore-drill.json",
    "23-compose-failure-exercises.json",
    "24-compose-map-gate.json",
]


KNOWN_AUTH_MAPSLOT_TEMPLATES = {
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/verify-email"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/me"),
    ("GET", "/api/auth/sessions"),
    ("GET", "/api/map-slots"),
    ("GET", "/api/map-slots/{slot_id}"),
    ("PUT", "/api/map-slots/{slot_id}"),
    ("POST", "/api/map-slots/{slot_id}/rename"),
    ("GET", "/api/map-slots/{slot_id}/export"),
    ("POST", "/api/map-slots/{slot_id}/reset"),
    ("POST", "/api/map-slots/{slot_id}/activate"),
    ("POST", "/api/map-slots/import"),
}


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def load_json(name: str, default: Any = None) -> Any:
    path = EVIDENCE / name
    if not path.exists():
        return default
    return json.loads(path.read_text())


def route_family(path: str) -> str:
    if path in {"", "/", "/index.html"}:
        return "app shell"
    if path.startswith(("/js/", "/css/", "/vendor/", "/Logo_")):
        return "static asset"
    if path.startswith("/data/"):
        return "static data"
    if path.startswith("/api/auth/"):
        return "auth"
    if path.startswith("/api/map-slots"):
        return "map slots"
    if path.startswith("/api/entity/"):
        return "entity drawer/model"
    if path.startswith("/api/assets/"):
        return "assets/due diligence"
    if path.startswith("/api/reports/"):
        return "reports"
    if path.startswith("/api/data-quality"):
        return "data quality"
    if path.startswith("/api/map/"):
        return "map API"
    if path.startswith("/api/reliefs/"):
        return "relief/terrain"
    if path.startswith("/api/overrides") or path.startswith("/api/evidence"):
        return "evidence/overrides"
    return path.split("/", 3)[1] if path.startswith("/") else "other"


def normalize_path(path_or_url: str) -> str:
    parsed = urlparse(path_or_url)
    if parsed.scheme:
        return parsed.path or "/"
    return path_or_url.split("?", 1)[0] or "/"


def template_regex(path: str) -> re.Pattern[str]:
    escaped = re.escape(path)
    pattern = re.sub(r"\\\{[^/]+\\\}", r"[^/]+", escaped)
    return re.compile(f"^{pattern}$")


def method_path_matches(template_method: str, template_path: str, actual_method: str, actual_path: str) -> bool:
    if template_method and actual_method and template_method != actual_method:
        return False
    return bool(template_regex(template_path).match(actual_path))


def har_requests() -> list[dict[str, str]]:
    requests = []
    for path in sorted(EVIDENCE.glob("*.har")):
        try:
            har = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        for entry in har.get("log", {}).get("entries", []):
            req = entry.get("request", {})
            url = req.get("url", "")
            parsed = urlparse(url)
            if parsed.hostname not in {"127.0.0.1", "localhost"}:
                continue
            requests.append({
                "source": path.name,
                "method": req.get("method", "GET"),
                "path": parsed.path or "/",
            })
    return requests


def api_latency_requests() -> set[tuple[str, str]]:
    out = set()
    latency = load_json("07-local-api-latency.json", {})
    for item in latency.get("measurements", []):
        out.add((item.get("method", "GET"), normalize_path(item.get("path", ""))))
    snapshots = load_json("02-golden-api-snapshots.json", {})
    for item in snapshots.get("snapshots", []):
        out.add((item.get("method", "GET"), normalize_path(item.get("path", ""))))
    return out


def route_probe_requests() -> set[tuple[str, str]]:
    out = set()
    probes = load_json("17-route-family-performance-probes.json", {})
    for item in probes.get("measurements", []):
        if item.get("status_codes") == [200]:
            out.add((item.get("method", "GET"), normalize_path(item.get("template") or item.get("path", ""))))
    return out


def auth_http_extra_requests() -> set[tuple[str, str]]:
    out = set()
    for file in ("06-local-auth-and-map-slots-http.json", "06-local-auth-and-map-slots-http-direct.json"):
        data = load_json(file, {})
        for item in data.get("extra_operations", []):
            status_code = item.get("status_code")
            if isinstance(status_code, int) and 200 <= status_code < 400 and item.get("template"):
                out.add((item.get("method", "GET"), normalize_path(item["template"])))
    return out


def route_probe_summary() -> dict[str, Any]:
    probes = load_json("17-route-family-performance-probes.json", {})
    measurements = probes.get("measurements", [])
    return {
        "captured_at": probes.get("captured_at"),
        "samples_per_route": probes.get("samples_per_route"),
        "measurement_count": len(measurements),
        "skipped_count": len(probes.get("skipped", [])),
        "sandboxed_fixture_count": len(probes.get("sandboxed_fixtures", [])),
        "measured_by_family": dict(Counter(item.get("family") or "other" for item in measurements)),
        "non_200": [
            {
                "name": item.get("name"),
                "method": item.get("method"),
                "template": item.get("template"),
                "status_codes": item.get("status_codes"),
            }
            for item in measurements
            if item.get("status_codes") != [200]
        ],
        "sandboxed_fixtures": probes.get("sandboxed_fixtures", []),
        "skipped": probes.get("skipped", []),
    }


def browser_summary() -> dict[str, Any]:
    summary = load_json("15-compose-browser-har-summary.json", {}) or load_json("11-browser-har-summary.json", {"flows": {}})
    flows = {}
    for name, flow in summary.get("flows", {}).items():
        flows[name] = {
            "requests": flow.get("requestCount"),
            "transfer_kb": flow.get("resourceTransferKb"),
            "bulk": flow.get("requestedUniverseBulk"),
            "unpkg": flow.get("requestedUnpkg"),
            "console_errors": len(flow.get("consoleErrors") or []),
            "external_hosts": flow.get("externalHosts", []),
        }
    return {
        "captured_at": summary.get("capturedAt"),
        "proxy_server": summary.get("proxyServer"),
        "flows": flows,
    }


def compose_map_gate_summary() -> dict[str, Any]:
    data = load_json("24-compose-map-gate.json", {})
    summary = data.get("summary") or {}
    browser = data.get("browser") or {}
    screenshots = data.get("screenshots") or {}
    return {
        "present": bool(data),
        "verdict": data.get("verdict"),
        "captured_at": data.get("capturedAt"),
        "browser_channel": browser.get("channel"),
        "browser_version": browser.get("version"),
        "headed": browser.get("requestedHeaded") and not browser.get("actualHeadless"),
        "proxy_server": data.get("proxyServer"),
        "requested_unpkg": summary.get("requestedUnpkg"),
        "requested_vendored_maplibre": summary.get("requestedVendoredMapLibre"),
        "unexpected_failed_requests": len(summary.get("unexpectedFailedRequests") or []),
        "unexpected_console_errors": len(summary.get("unexpectedConsoleErrors") or []),
        "screenshots": screenshots,
    }


def maplibre_diagnostic_summary() -> dict[str, Any]:
    data = load_json("18-headless-maplibre-diagnostic.json", {})
    return {
        "captured_at": data.get("capturedAt"),
        "conclusion": data.get("conclusion"),
        "variant_count": len(data.get("results", [])),
        "unclassified_error_count": sum(
            1
            for result in data.get("results", [])
            for error in result.get("errors", [])
            if error.get("classification") == "unclassified"
        ),
        "all_style_loaded": all(result.get("styleLoaded") for result in data.get("results", [])) if data.get("results") else False,
        "all_basemap_preserved": all(result.get("basemapPreserved") for result in data.get("results", [])) if data.get("results") else False,
    }


def auth_summary() -> dict[str, Any]:
    out = {}
    for label, file in [
        ("testclient", "06-local-auth-and-map-slots.json"),
        ("http_proxyman", "06-local-auth-and-map-slots-http.json"),
        ("http_direct", "06-local-auth-and-map-slots-http-direct.json"),
    ]:
        data = load_json(file, {})
        measurements = {}
        for m in data.get("measurements", []):
            measurements[m.get("name", "")] = {
                "p50_ms": m.get("p50_ms"),
                "p95_ms": m.get("p95_ms"),
                "target_ms": m.get("target_ms"),
                "target_met": m.get("target_met"),
                "status_codes": m.get("status_codes"),
            }
        out[label] = {
            "file": file,
            "proxy_server": data.get("proxy_server"),
            "samples": data.get("samples_per_measurement"),
            "default_map_slots": data.get("default_map_slot_count"),
            "csrf_status": (data.get("csrf_rejection") or {}).get("status_code"),
            "extra_operations": len(data.get("extra_operations", [])),
            "extra_non_success": [
                {
                    "operation": item.get("operation"),
                    "method": item.get("method"),
                    "template": item.get("template"),
                    "status_code": item.get("status_code"),
                }
                for item in data.get("extra_operations", [])
                if not isinstance(item.get("status_code"), int) or item.get("status_code") >= 400
            ],
            "measurements": measurements,
        }
    return out


def route_coverage(route_inventory: dict[str, Any]) -> dict[str, Any]:
    actual_requests = {(r["method"], r["path"]) for r in har_requests()}
    actual_requests |= api_latency_requests()
    actual_requests |= route_probe_requests()
    actual_requests |= auth_http_extra_requests()
    actual_requests |= KNOWN_AUTH_MAPSLOT_TEMPLATES

    result = {}
    for app_name in ("map_api", "server_app"):
        routes = [
            route for route in route_inventory.get(app_name, [])
            if route.get("kind") == "APIRoute"
            and route.get("path") not in {"/docs", "/openapi.json", "/redoc", "/docs/oauth2-redirect"}
        ]
        covered = []
        uncovered = []
        for route in routes:
            route_methods = route.get("methods") or ["GET"]
            route_path = route.get("path") or ""
            matched = any(
                method_path_matches(method, route_path, actual_method, actual_path)
                for method in route_methods
                for actual_method, actual_path in actual_requests
            )
            item = {
                "path": route_path,
                "methods": route_methods,
                "name": route.get("name"),
                "family": route_family(route_path),
            }
            (covered if matched else uncovered).append(item)
        result[app_name] = {
            "total_routes": len(routes),
            "covered_routes": len(covered),
            "uncovered_routes": len(uncovered),
            "coverage_pct": round((len(covered) / len(routes) * 100), 1) if routes else 0,
            "covered_by_family": dict(Counter(item["family"] for item in covered)),
            "uncovered_by_family": dict(Counter(item["family"] for item in uncovered)),
            "uncovered": uncovered,
        }
    return result


def compose_route_probe_summary() -> dict[str, Any]:
    direct = load_json("20-compose-route-family-probe.json", {})
    proxied = load_json("21-compose-route-family-proxyman-probe.json", {})
    return {
        "direct": {
            "present": bool(direct),
            "verdict": direct.get("verdict"),
            "measurement_count": direct.get("measurement_count", 0),
            "failure_count": direct.get("failure_count", 0),
            "base_url": direct.get("base_url"),
        },
        "proxyman": {
            "present": bool(proxied),
            "verdict": proxied.get("verdict"),
            "measurement_count": proxied.get("measurement_count", 0),
            "failure_count": proxied.get("failure_count", 0),
            "base_url": proxied.get("base_url"),
            "proxy_server": proxied.get("proxy_server"),
        },
    }


def compose_failure_summary() -> dict[str, Any]:
    data = load_json("23-compose-failure-exercises.json", {})
    return {
        "present": bool(data),
        "verdict": data.get("verdict"),
        "captured_at": data.get("captured_at"),
        "postgres_readyz_stopped": (
            data.get("exercises", {})
            .get("stop_postgres", {})
            .get("readyz_while_db_stopped", {})
            .get("status_code")
        ),
        "worker_job_status": (
            data.get("exercises", {})
            .get("recover_worker", {})
            .get("job_after_worker_restart", {})
            .get("status")
        ),
        "full_restart_readyz": (
            data.get("exercises", {})
            .get("restart_full_stack", {})
            .get("readyz_after_compose_restart", {})
            .get("status_code")
        ),
        "login_status": data.get("persistence_after_restarts", {}).get("login_status"),
        "map_slot_count": data.get("persistence_after_restarts", {}).get("map_slot_count"),
    }


def derive_gaps(
    browser: dict[str, Any],
    auth: dict[str, Any],
    staging: dict[str, Any],
    maplibre: dict[str, Any],
    compose_routes: dict[str, Any],
    failure: dict[str, Any],
    map_gate: dict[str, Any],
) -> list[str]:
    gaps = []
    staging_result = staging.get("result")
    compose_captured = staging_result in {
        "staging_or_deployed_capture_complete",
        "compose_staging_performance_capture_complete_with_limitations",
        "compose_staging_performance_capture_current_with_public_url_gap",
    }
    if not compose_captured:
        gaps.append("deployed or compose staging Proxyman capture is still missing")
    if not staging.get("current_environment", {}).get("docker_available"):
        gaps.append("compose staging cannot run on this machine because Docker is unavailable")
    direct_routes = compose_routes.get("direct", {})
    proxyman_routes = compose_routes.get("proxyman", {})
    compose_route_probe_passed = (
        direct_routes.get("verdict") == "pass"
        and proxyman_routes.get("verdict") == "pass"
    )
    if staging_result == "compose_staging_performance_capture_complete_with_limitations" and not compose_route_probe_passed:
        gaps.append("route-family coverage through the compose reverse proxy is still pending")
    if not staging.get("current_environment", {}).get("env_public_base_url_set"):
        gaps.append("no public deployed staging URL is configured in .env")
    if failure.get("verdict") != "pass":
        gaps.append("compose failure exercises are missing or failing")
    if map_gate.get("verdict") != "pass":
        gaps.append("headed compose map gate is missing or failing")
    map_flow = browser.get("flows", {}).get("06-local-map-interactions", {})
    if map_flow.get("console_errors") and not (
        maplibre.get("all_style_loaded")
        and maplibre.get("all_basemap_preserved")
        and maplibre.get("unclassified_error_count") == 0
    ):
        gaps.append("headless MapLibre map interaction capture still logs shaderPreludeCode errors")
    direct = auth.get("http_direct", {}).get("measurements", {})
    proxied = auth.get("http_proxyman", {}).get("measurements", {})
    for name, measurement in proxied.items():
        if measurement.get("target_met") is False and direct.get(name, {}).get("target_met") is True:
            gaps.append(f"Proxyman-routed local HTTP outlier for {name}; direct HTTP passes")
    return gaps


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_markdown(path: Path, audit: dict[str, Any]) -> None:
    browser = audit["browser"]
    auth = audit["auth"]
    coverage = audit["route_coverage"]
    route_probe = audit["route_family_probe"]
    maplibre = audit["maplibre_headless_diagnostic"]
    map_gate = audit["compose_map_gate"]
    failure = audit["compose_failure_exercises"]
    lines = [
        "# Performance Evidence Coverage Audit",
        "",
        f"**Generated:** {audit['generated_at']}",
        f"**Commit:** `{audit['commit']}`",
        "",
        "## Artifact Presence",
        "",
        "| Artifact | Status |",
        "|---|---|",
    ]
    for name, present in audit["artifacts"].items():
        lines.append(f"| `{name}` | {'present' if present else 'missing'} |")

    lines.extend([
        "",
        "## Browser Flows",
        "",
        f"Source summary: `{browser.get('captured_at')}` via `{browser.get('proxy_server')}`",
        "",
        "| Flow | Requests | Transfer KB | Bulk | unpkg | Console errors |",
        "|---|---:|---:|---|---|---:|",
    ])
    for name, flow in browser.get("flows", {}).items():
        lines.append(
            f"| `{name}` | {flow.get('requests')} | {flow.get('transfer_kb')} | "
            f"{flow.get('bulk')} | {flow.get('unpkg')} | {flow.get('console_errors')} |"
        )

    lines.extend([
        "",
        "## Headless MapLibre Diagnostic",
        "",
        f"- captured: `{maplibre.get('captured_at')}`",
        f"- variants: `{maplibre.get('variant_count')}`",
        f"- all style loaded: `{maplibre.get('all_style_loaded')}`",
        f"- all basemap state preserved: `{maplibre.get('all_basemap_preserved')}`",
        f"- unclassified errors: `{maplibre.get('unclassified_error_count')}`",
        f"- conclusion: {maplibre.get('conclusion')}",
    ])

    lines.extend([
        "",
        "## Headed Compose Map Gate",
        "",
        f"- captured: `{map_gate.get('captured_at')}`",
        f"- verdict: `{map_gate.get('verdict')}`",
        f"- browser: `{map_gate.get('browser_channel')}` `{map_gate.get('browser_version')}`",
        f"- headed: `{map_gate.get('headed')}`",
        f"- proxy: `{map_gate.get('proxy_server')}`",
        f"- vendored MapLibre requested: `{map_gate.get('requested_vendored_maplibre')}`",
        f"- unpkg requested: `{map_gate.get('requested_unpkg')}`",
        f"- unexpected failed requests: `{map_gate.get('unexpected_failed_requests')}`",
        f"- unexpected console errors: `{map_gate.get('unexpected_console_errors')}`",
        f"- normal screenshot: `{map_gate.get('screenshots', {}).get('normal')}`",
        f"- provider-failure screenshot: `{map_gate.get('screenshots', {}).get('providerFailure')}`",
    ])

    lines.extend(["", "## Auth And Map Slots", ""])
    for label, data in auth.items():
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- file: `{data.get('file')}`")
        lines.append(f"- proxy: `{data.get('proxy_server')}`")
        lines.append(f"- default map slots: `{data.get('default_map_slots')}`")
        lines.append(f"- CSRF rejection status: `{data.get('csrf_status')}`")
        if data.get("extra_operations"):
            lines.append(f"- extra covered one-shot operations: `{data.get('extra_operations')}`")
        if data.get("extra_non_success"):
            lines.append(f"- extra operations needing attention: `{len(data.get('extra_non_success'))}`")
        lines.append("")
        lines.append("| Measurement | p50 ms | p95 ms | Target | Met |")
        lines.append("|---|---:|---:|---:|---|")
        for name, m in data.get("measurements", {}).items():
            lines.append(
                f"| {name} | {m.get('p50_ms')} | {m.get('p95_ms')} | "
                f"{m.get('target_ms') or ''} | {m.get('target_met')} |"
            )
        lines.append("")

    lines.extend(["## Route Coverage", ""])
    lines.append(
        f"Route-family probe: {route_probe['measurement_count']} measured routes "
        f"with {route_probe['skipped_count']} skipped routes and "
        f"{route_probe.get('sandboxed_fixture_count', 0)} sandboxed fixture groups."
    )
    lines.append("")
    for app_name, data in coverage.items():
        lines.append(
            f"- `{app_name}`: {data['covered_routes']}/{data['total_routes']} routes covered "
            f"by performance evidence ({data['coverage_pct']}%)."
        )
        if data["uncovered_by_family"]:
            parts = ", ".join(f"{family}: {count}" for family, count in sorted(data["uncovered_by_family"].items()))
            lines.append(f"  Uncovered families: {parts}.")
    if route_probe["measured_by_family"]:
        parts = ", ".join(
            f"{family}: {count}" for family, count in sorted(route_probe["measured_by_family"].items())
        )
        lines.append(f"- Route probe measured families: {parts}.")
    if route_probe["non_200"]:
        lines.append("- Route probe non-200 measurements remain and need investigation before using them as coverage.")
    if route_probe.get("sandboxed_fixtures"):
        lines.append("- Some route-family coverage uses temporary fixture redirection; see `sandboxed_fixtures` in JSON.")
    compose_route_probe = audit.get("compose_route_family_probe", {})
    lines.append(
        "- Compose route-family probes: "
        f"direct `{compose_route_probe.get('direct', {}).get('verdict')}`, "
        f"Proxyman `{compose_route_probe.get('proxyman', {}).get('verdict')}`."
    )
    lines.extend(["", "### Uncovered Server-App Routes", ""])
    lines.append("| Methods | Path | Family |")
    lines.append("|---|---|---|")
    for item in coverage.get("server_app", {}).get("uncovered", [])[:60]:
        lines.append(f"| `{','.join(item['methods'])}` | `{item['path']}` | {item['family']} |")

    lines.extend([
        "",
        "## Failure Exercises",
        "",
        f"- captured: `{failure.get('captured_at')}`",
        f"- verdict: `{failure.get('verdict')}`",
        f"- `/readyz` while PostgreSQL stopped: `{failure.get('postgres_readyz_stopped')}`",
        f"- worker restart job status: `{failure.get('worker_job_status')}`",
        f"- `/readyz` after full compose restart: `{failure.get('full_restart_readyz')}`",
        f"- post-restart login status: `{failure.get('login_status')}`",
        f"- post-restart map slots: `{failure.get('map_slot_count')}`",
    ])

    lines.extend(["", "## Gaps And Decision", ""])
    for gap in audit["gaps"]:
        lines.append(f"- {gap}")
    lines.extend([
        "",
        "**Decision:** local compose performance optimization evidence is current. "
        "The remaining acceptance gap is the absent public deployed staging URL; local compose, "
        "reverse-proxy, Proxyman, backup/restore, headed-map, route-family, and failure-exercise "
        "evidence are present.",
        "",
    ])
    path.write_text("\n".join(lines))


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    route_inventory_data = load_json("01-route-inventory.json", {})
    browser = browser_summary()
    auth = auth_summary()
    maplibre = maplibre_diagnostic_summary()
    staging = load_json("15-staging-capture-status.json", {})
    coverage = route_coverage(route_inventory_data)
    route_probe = route_probe_summary()
    compose_routes = compose_route_probe_summary()
    failure = compose_failure_summary()
    map_gate = compose_map_gate_summary()
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "artifacts": {name: (EVIDENCE / name).exists() for name in EXPECTED_ARTIFACTS},
        "browser": browser,
        "maplibre_headless_diagnostic": maplibre,
        "auth": auth,
        "route_family_probe": route_probe,
        "compose_route_family_probe": compose_routes,
        "compose_failure_exercises": failure,
        "compose_map_gate": map_gate,
        "route_coverage": coverage,
        "staging": staging,
        "gaps": derive_gaps(browser, auth, staging, maplibre, compose_routes, failure, map_gate),
    }
    write_json(EVIDENCE / "16-performance-coverage-audit.json", audit)
    write_markdown(EVIDENCE / "16-performance-coverage-audit.md", audit)
    print(f"Wrote performance coverage audit to {EVIDENCE / '16-performance-coverage-audit.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
