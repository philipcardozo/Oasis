#!/usr/bin/env python3
"""Audit Phase 1.75 public-staging evidence.

This is a strict completion audit, not a smoke test. Missing evidence remains
missing; the script does not infer approval from scaffolding, docs, or intent.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
JSON_OUT = EVIDENCE / "99-public-staging-gate-audit.json"
MD_OUT = EVIDENCE / "99-public-staging-gate-audit.md"
PASS_VERDICT_RE = re.compile(r"^Verdict:\s*(?:\*\*)?pass(?:\*\*)?\s*$", re.IGNORECASE | re.MULTILINE)
ANY_VERDICT_RE = re.compile(r"^Verdict:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
GENERATED_REPORT_RE = re.compile(r"\bThis generated report\b", re.IGNORECASE)
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
PUBLIC_HASH_RE = re.compile(r"(?:sha256:)?[0-9a-f]{7,128}", re.IGNORECASE)
ARTIFACT_REFERENCE_RE = re.compile(
    r"(?=.*(?:^|[._/-])(?:public-staging|compose|local)(?:[._/-]|$))^[A-Za-z0-9][A-Za-z0-9._/-]*$"
)
URL_WITH_CREDENTIALS_RE = re.compile(r"://[^/\s:@]+:[^/\s:@]+@")
TOKEN_QUERY_RE = re.compile(r"(?i)(?:[?&](?:token|code|secret|password|key)=)(?!<redacted>|redacted)[^&\s`'\">]{8,}")
AUTH_HEADER_RE = re.compile(r"(?i)\bauthorization\s*[:=]\s*(?!<redacted>|redacted)(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
SECRET_PREFIX_RE = re.compile(r"^(?:sk_|pk_|ghp_|ghs_|xoxb-|xoxp-)[A-Za-z0-9._~+/=-]{8,}")
JWT_RE = re.compile(r"^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$")
LONG_SECRET_RE = re.compile(r"(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9_\-+/=]{32,}")
SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|token|cookie|authorization|secret|api[_-]?key|private[_-]?key|credential|database[_-]?url)",
    re.IGNORECASE,
)

GENERATED_MARKDOWN = {
    "02-dns-tls-edge.md",
    "03-cloudflare-access.md",
    "04-render-services.md",
    "05-migration-version.md",
    "06-auth-email.md",
    "07-browser-matrix.md",
    "08-map-provider-capture.md",
    "09-route-security.md",
    "10-worker-jobs.md",
    "11-network-isolation.md",
    "12-backup-restore.md",
    "13-failure-rollback.md",
    "14-observability-alerts.md",
    "15-performance.md",
}

MARKDOWN_REQUIRED_TEXT = {
    "02-dns-tls-edge.md": [
        "# Public Staging DNS TLS And Edge Evidence",
        "## Checks",
        "preflight verdict",
        "HSTS max-age present",
    ],
    "03-cloudflare-access.md": [
        "# Public Staging Cloudflare Access Evidence",
        "## Checks",
        "service-token status",
        "OASIS auth status",
    ],
    "04-render-services.md": [
        "# Public Staging Render Services Evidence",
        "## Checks",
        "image manifest verdict",
        "Render deploy roles",
    ],
    "05-migration-version.md": [
        "# Public Staging Migration Version Evidence",
        "## Checks",
        "expected revision",
        "current revision",
    ],
    "06-auth-email.md": [
        "# Public Staging Authentication And Email Evidence",
        "## Checks",
        "session cookie secure",
        "csrf rejection status",
    ],
    "07-browser-matrix.md": [
        "# Public Staging Browser Matrix Evidence",
        "## Browser Matrix",
        "## Captured Network Flows",
    ],
    "08-map-provider-capture.md": [
        "# Public Staging Map Provider Evidence",
        "## Provider Checks",
        "Approved hosts",
    ],
    "09-route-security.md": [
        "# Public Staging Route Security Evidence",
        "## Route Probe",
        "### Unauthenticated Rejections",
        "## Auth And Authorization Checks",
    ],
    "10-worker-jobs.md": [
        "# Public Staging Worker Job Evidence",
        "## Checks",
        "controlled noop job was created",
    ],
    "11-network-isolation.md": [
        "# Public Staging Network Isolation Evidence",
        "## Checks",
        "API made no SEC requests",
    ],
    "12-backup-restore.md": [
        "# Public Staging Backup Restore Evidence",
        "## Checks",
        "on-demand backup was created",
    ],
    "13-failure-rollback.md": [
        "# Public Staging Failure And Rollback Evidence",
        "## Checks",
        "API rollback was exercised",
    ],
    "14-observability-alerts.md": [
        "# Public Staging Observability And Alerts Evidence",
        "## Checks",
        "API readiness failure",
    ],
    "15-performance.md": [
        "# Public Staging Performance Evidence",
        "## Browser Flows",
        "## DNS And TLS",
    ],
}

REQUIRED_DOCS = [
    "docs/PHASE-1-75-PUBLIC-STAGING.md",
    "docs/PUBLIC-STAGING-ARCHITECTURE.md",
    "docs/PUBLIC-STAGING-RUNBOOK.md",
    "docs/PRIVATE-BETA-OPERATIONS.md",
    "docs/DEPLOYMENT-ROLLBACK.md",
    "docs/STAGING-OBSERVABILITY.md",
    "docs/STAGING-BACKUP-RESTORE.md",
    "docs/LICENSING-GATES.md",
    "docs/adr/0008-public-staging-provider.md",
    "docs/adr/0009-edge-access-control.md",
    "docs/adr/0010-managed-postgresql.md",
    "docs/adr/0011-container-registry.md",
    "docs/adr/0012-object-storage.md",
    "docs/adr/0013-email-provider.md",
    "docs/adr/0014-deployment-automation.md",
]


REQUIREMENTS = [
    ("public_dns", "Public DNS", ["00-public-staging-preflight.json"], ["dns"]),
    ("public_tls", "Public TLS", ["00-public-staging-preflight.json"], ["tls"]),
    ("secret_management", "Secure secret management", ["04-render-services.md"], []),
    ("managed_postgres", "Managed PostgreSQL", ["04-render-services.md", "05-migration-version.md"], []),
    ("persistent_storage", "Persistent object and database storage", ["04-render-services.md", "12-backup-restore.md"], []),
    ("reverse_proxy", "Public reverse-proxy behavior", ["00-public-staging-preflight.json", "02-dns-tls-edge.md"], []),
    ("email_delivery", "Authentication email delivery", ["06-auth-email.md", "auth-email-summary.json"], []),
    ("api_worker_separation", "API and worker separation", ["02-render-deploy.json", "10-worker-jobs.md"], []),
    ("attack_surface", "External attack-surface controls", ["03-cloudflare-access.md", "09-route-security.md", "route-security-summary.json"], []),
    ("browser_compatibility", "Remote browser compatibility", ["07-browser-matrix.md"], []),
    ("deployment_automation", "Deployment automation", ["01-image-manifest.json", "02-render-deploy.json"], []),
    ("rollback", "Rollback", ["13-failure-rollback.md"], []),
    ("backup_restore", "Backup and restore", ["12-backup-restore.md"], []),
    ("monitoring_alerting", "Monitoring and alerting", ["14-observability-alerts.md"], []),
    ("private_beta_access", "Private-beta access control", ["03-cloudflare-access.md", "06-auth-email.md", "auth-email-summary.json"], []),
    ("performance", "Public performance measurements", ["15-performance.md", "performance-evidence-summary.json"], []),
    ("licensing", "Licensing gates", ["15-performance.md", "08-map-provider-capture.md"], []),
]


ACCEPTANCE = [
    ("https_reachable", "Public staging is reachable through HTTPS", ["00-public-staging-preflight.json"]),
    ("outer_access", "Outer staging access control is enabled", ["03-cloudflare-access.md"]),
    ("dns_cert_valid", "DNS and certificates are valid", ["00-public-staging-preflight.json", "02-dns-tls-edge.md"]),
    ("tested_commit_image", "Deployed image matches a tested commit", ["01-image-manifest.json", "02-render-deploy.json"]),
    ("postgres_backed_up", "PostgreSQL is persistent and backed up", ["12-backup-restore.md"]),
    ("explicit_migrations", "Migrations complete explicitly", ["05-migration-version.md"]),
    ("api_worker_separate", "API and worker are separate", ["02-render-deploy.json", "10-worker-jobs.md"]),
    ("auth_email", "Email verification and password reset work", ["06-auth-email.md", "auth-email-summary.json"]),
    ("secure_cookies", "Session cookies are secure", ["06-auth-email.md", "auth-email-summary.json", "00-public-staging-preflight.json"]),
    ("csrf", "CSRF works", ["09-route-security.md", "route-security-summary.json"]),
    ("route_classification", "Every route has explicit security classification", ["09-route-security.md", "route-security-summary.json"]),
    ("cross_user_denied", "Cross-user access is denied", ["09-route-security.md", "route-security-summary.json"]),
    ("three_slots", "Exactly three map slots persist across devices", ["07-browser-matrix.md"]),
    ("browser_map", "Real browser map rendering works", ["07-browser-matrix.md", "08-map-provider-capture.md"]),
    ("no_bulk_first_paint", "/api/universe/bulk is absent from initial paint", ["15-performance.md", "performance-evidence-summary.json"]),
    ("zero_api_acquisition", "API user requests perform zero external acquisition", ["11-network-isolation.md"]),
    ("worker_recovery", "Worker jobs are bounded and recoverable", ["10-worker-jobs.md"]),
    ("private_storage", "Object storage remains private", ["12-backup-restore.md"]),
    ("headers_cors_hosts", "Security headers, CORS, and trusted hosts are correct", ["00-public-staging-preflight.json", "09-route-security.md", "route-security-summary.json"]),
    ("rate_limit_proxy", "Rate limiting works through public proxy", ["09-route-security.md", "route-security-summary.json"]),
    ("restore_success", "Backup and restore succeed", ["12-backup-restore.md"]),
    ("rollback_success", "Deployment rollback succeeds", ["13-failure-rollback.md"]),
    ("alerts", "Alerts detect key failures", ["14-observability-alerts.md"]),
    ("providers_disabled", "Unlicensed providers remain disabled", ["08-map-provider-capture.md"]),
    ("test_suites_pass", "Test suites pass", ["01-image-manifest.json"]),
    ("cicd_safe", "CI/CD deploys immutable images safely", ["01-image-manifest.json", "02-render-deploy.json"]),
    ("docs_current", "Documentation is current", REQUIRED_DOCS),
]


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {"_parse_error": str(exc)}


def status_ok(value: Any) -> bool:
    return str(value or "").lower() in {"pass", "passed", "ok", "success", "succeeded", "true", "present"}


def safe_secret_value(value: str, *, names_only: bool = False) -> bool:
    lowered = value.lower()
    if value in {"", "<redacted>", "redacted", "***", "present", "configured", "missing"}:
        return True
    if lowered.startswith("replace-with-"):
        return True
    if names_only or ENV_NAME_RE.fullmatch(value):
        return True
    if PUBLIC_HASH_RE.fullmatch(value):
        return True
    return False


def secretish_string(value: str) -> bool:
    if safe_secret_value(value):
        return False
    if URL_WITH_CREDENTIALS_RE.search(value):
        return True
    if TOKEN_QUERY_RE.search(value):
        return True
    if AUTH_HEADER_RE.search(value):
        return True
    if SECRET_PREFIX_RE.match(value):
        return True
    if JWT_RE.match(value):
        return True
    if ARTIFACT_REFERENCE_RE.fullmatch(value):
        return False
    return bool(LONG_SECRET_RE.fullmatch(value)) and not ENV_NAME_RE.fullmatch(value)


def json_secret_paths(value: Any, path: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child = f"{path}.{key_text}" if path else key_text
            lowered = key_text.lower()
            names_only = any(marker in lowered for marker in ("env", "header_names", "secret_names", "credential_names"))
            if SENSITIVE_KEY_RE.search(key_text) and isinstance(item, str) and not safe_secret_value(item, names_only=names_only):
                findings.append(child)
            findings.extend(json_secret_paths(item, child))
    elif isinstance(value, list):
        names_only = any(marker in path.lower() for marker in ("env", "header_names", "secret_names", "credential_names"))
        for idx, item in enumerate(value):
            child = f"{path}[{idx}]"
            if isinstance(item, str) and not safe_secret_value(item, names_only=names_only) and secretish_string(item):
                findings.append(child)
            findings.extend(json_secret_paths(item, child))
    elif isinstance(value, str) and secretish_string(value):
        findings.append(path or "<root>")
    return sorted(set(findings))


def text_secret_findings(text: str) -> list[str]:
    findings: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if URL_WITH_CREDENTIALS_RE.search(line):
            findings.append(f"line {lineno}: URL contains credentials")
        if TOKEN_QUERY_RE.search(line):
            findings.append(f"line {lineno}: URL contains token-like query value")
        if AUTH_HEADER_RE.search(line):
            findings.append(f"line {lineno}: authorization header value is present")
        for value in re.findall(r"(?<![A-Za-z0-9_])(?:sk_|pk_|ghp_|ghs_|xoxb-|xoxp-)[A-Za-z0-9._~+/=-]{8,}", line):
            if secretish_string(value):
                findings.append(f"line {lineno}: token-like value is present")
    return findings


def markdown_shape_weaknesses(name: str, text: str) -> list[str]:
    required = MARKDOWN_REQUIRED_TEXT.get(name, [])
    return [f"missing generated report content: {item}" for item in required if item not in text]


def endpoint_ok(data: dict[str, Any], path: str) -> bool:
    result = (data.get("endpoints") or {}).get(path) or {}
    return result.get("ok") is True and 200 <= int(result.get("status") or 0) < 400


def endpoint_text(data: dict[str, Any], path: str) -> str:
    result = (data.get("endpoints") or {}).get(path) or {}
    if isinstance(result.get("body_json"), dict):
        return json.dumps(result["body_json"], sort_keys=True)
    return str(result.get("body_text") or "")


def preflight_weaknesses(data: dict[str, Any]) -> list[str]:
    weak: list[str] = []
    if data.get("verdict") != "pass":
        weak.append("preflight verdict is not pass")
    if (data.get("url") or {}).get("scheme") != "https":
        weak.append("preflight base URL is not HTTPS")
    if (data.get("dns") or {}).get("ok") is not True:
        weak.append("preflight DNS is not ok")
    if (data.get("tls") or {}).get("ok") is not True:
        weak.append("preflight TLS is not ok")
    if (data.get("http_to_https_redirect") or {}).get("status") not in {301, 302, 307, 308}:
        weak.append("preflight HTTP-to-HTTPS redirect is missing")
    for path in ("/index.html", "/healthz", "/readyz", "/version"):
        if not endpoint_ok(data, path):
            weak.append(f"preflight {path} is not successful")
    headers = (((data.get("endpoints") or {}).get("/index.html") or {}).get("headers") or {})
    required_headers = {
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin",
        "content-security-policy": "default-src 'self'",
    }
    for key, expected in required_headers.items():
        if expected not in str(headers.get(key) or ""):
            weak.append(f"preflight /index.html missing {key}: {expected}")
    hsts = str(headers.get("strict-transport-security") or "").lower()
    if "max-age=" not in hsts:
        weak.append("preflight /index.html missing HSTS max-age")
    if "includesubdomains" in hsts:
        weak.append("preflight HSTS includeSubDomains is not allowed")
    if "preload" in hsts:
        weak.append("preflight HSTS preload is not allowed")

    manifest = load_json(EVIDENCE / "01-image-manifest.json") or {}
    manifest_commit = str(manifest.get("commit") or "") if not manifest.get("_parse_error") else ""
    if manifest_commit and manifest_commit not in endpoint_text(data, "/version"):
        weak.append("preflight /version does not include image manifest commit")
    return weak


def image_manifest_weaknesses(data: dict[str, Any]) -> list[str]:
    weak: list[str] = []
    image = str(data.get("image") or "")
    digest = str(data.get("digest") or "")
    image_name = str(data.get("image_name") or "")
    checks = data.get("checks") or {}
    if data.get("verdict") != "pass":
        weak.append("image manifest verdict is not pass")
    if not str(data.get("commit") or "") or len(str(data.get("commit") or "")) < 7:
        weak.append("image manifest commit is missing or too short")
    if "@" not in image:
        weak.append("image manifest image is not digest pinned")
    if ":latest" in image or image.endswith(":latest"):
        weak.append("image manifest image uses latest")
    if not IMAGE_DIGEST_RE.match(digest):
        weak.append("image manifest digest is not sha256")
    if image and digest and not image.endswith(f"@{digest}"):
        weak.append("image manifest digest does not match image")
    if data.get("registry") != "ghcr.io":
        weak.append("image manifest registry is not ghcr.io")
    if image_name and not image_name.startswith("ghcr.io/"):
        weak.append("image manifest image_name is not GHCR")
    if data.get("architecture") != "linux/amd64":
        weak.append("image manifest architecture is not linux/amd64")
    for name in ("migration_validation", "python_tests", "playwright_tests", "image_scan", "sbom", "provenance"):
        if not status_ok(checks.get(name)):
            weak.append(f"image manifest {name} is not passing/present")
    return weak


def render_deploy_weaknesses(data: dict[str, Any]) -> list[str]:
    weak: list[str] = []
    image_url = str(data.get("image_url") or "")
    digest = image_url.rsplit("@", 1)[1] if "@" in image_url else ""
    deployments = list(data.get("deployments") or [])
    roles = sorted(item.get("role") for item in deployments)
    if data.get("verdict") != "pass":
        weak.append("Render deploy verdict is not pass")
    if "@" not in image_url:
        weak.append("Render deploy image is not digest pinned")
    if ":latest" in image_url or image_url.endswith(":latest"):
        weak.append("Render deploy image uses latest")
    if not IMAGE_DIGEST_RE.match(digest):
        weak.append("Render deploy digest is missing or not sha256")
    if roles != ["api", "worker"]:
        weak.append(f"Render deploy roles must be exactly api and worker, got {roles}")
    sequence_text = "\n".join(str(item) for item in (data.get("sequence") or [])).lower()
    for required in ("alembic upgrade head", "server.migration_check", "before worker"):
        if required not in sequence_text:
            weak.append(f"Render deploy sequence missing {required}")
    for item in deployments:
        role = item.get("role") or "unknown"
        if item.get("ok") is not True:
            weak.append(f"Render {role} deploy is not ok")
        if item.get("terminal") is not True:
            weak.append(f"Render {role} deploy is not terminal")
        if item.get("timed_out") is True:
            weak.append(f"Render {role} deploy timed out")
        if not item.get("deploy_id"):
            weak.append(f"Render {role} deploy id is missing")
        if not item.get("service_id_sha256_16"):
            weak.append(f"Render {role} service hash is missing")

    manifest = load_json(EVIDENCE / "01-image-manifest.json") or {}
    if manifest and not manifest.get("_parse_error"):
        if manifest.get("image") != image_url:
            weak.append("Render deploy image does not match image manifest")
        if digest and manifest.get("digest") != digest:
            weak.append("Render deploy digest does not match image manifest")
    return weak


def performance_summary_weaknesses(data: dict[str, Any]) -> list[str]:
    weak: list[str] = []
    if data.get("verdict") != "pass":
        weak.append("performance summary verdict is not pass")
    if data.get("failures"):
        weak.append("performance summary has failures")
    if data.get("warnings"):
        weak.append("performance summary has unresolved missing inputs")

    target = data.get("target") or {}
    parsed = urlparse(str(target.get("base_url") or ""))
    if parsed.scheme != "https":
        weak.append("performance summary base URL is not HTTPS")
    if not target.get("proxy_server"):
        weak.append("performance summary Proxyman proxy is not recorded")

    browser = data.get("browser") or {}
    flows = list(browser.get("flows") or [])
    if not flows:
        weak.append("performance summary has no browser flows")
    if not browser.get("direct_comparison_present"):
        weak.append("performance summary direct network comparison is missing")
    first_flow = next((item for item in flows if "first-paint" in str(item.get("name") or "")), flows[0] if flows else {})
    if first_flow.get("bulk") is True:
        weak.append("performance summary first paint requested /api/universe/bulk")
    for row in flows:
        name = row.get("name") or "unknown flow"
        if row.get("unpkg") is True:
            weak.append(f"performance summary {name} requested unpkg.com")
        if int(row.get("console_errors") or 0):
            weak.append(f"performance summary {name} recorded console errors")
        if int(row.get("failed_requests") or 0):
            weak.append(f"performance summary {name} recorded failed requests")

    preflight = data.get("preflight") or {}
    if preflight.get("verdict") != "pass":
        weak.append("performance summary preflight verdict is not pass")
    if preflight.get("dns_ms") is None:
        weak.append("performance summary DNS timing is missing")
    if preflight.get("tls_ms") is None:
        weak.append("performance summary TLS timing is missing")

    auth_rows = list((data.get("auth_map_slot") or {}).get("rows") or [])
    required_auth = {
        "session validation": "session validation",
        "map-slot read": "map-slot read",
        "map-slot write": "map-slot write",
    }
    for label, needle in required_auth.items():
        row = next((item for item in auth_rows if needle in str(item.get("name") or "").lower()), None)
        if not row:
            weak.append(f"performance summary missing {label} app-layer latency")
        elif row.get("target_met") is not True:
            weak.append(f"performance summary {label} app-layer target is not met")
        elif row.get("p95_ms") is None:
            weak.append(f"performance summary {label} p95 is missing")

    route_probe = data.get("route_probe") or {}
    route_rows = list(route_probe.get("rows") or [])
    if route_probe.get("verdict") != "pass":
        weak.append("performance summary route probe verdict is not pass")
    if not route_rows:
        weak.append("performance summary route probe rows are missing")
    for row in route_rows:
        route = f"{row.get('method') or ''} {row.get('template') or row.get('name') or 'unknown route'}".strip()
        if row.get("ok") is not True:
            weak.append(f"performance summary route probe failed: {route}")
        if row.get("p95_ms") is None:
            weak.append(f"performance summary route probe p95 is missing: {route}")
    return weak


def route_security_summary_weaknesses(data: dict[str, Any]) -> list[str]:
    weak: list[str] = []
    if data.get("verdict") != "pass":
        weak.append("route-security summary verdict is not pass")
    if data.get("failures"):
        weak.append("route-security summary has failures")
    if data.get("warnings"):
        weak.append("route-security summary has warnings")

    route_probe = data.get("route_probe") or {}
    if route_probe.get("verdict") != "pass":
        weak.append("route-security route probe verdict is not pass")
    if route_probe.get("failure_count") != 0:
        weak.append("route-security route probe failure count is not zero")
    summary = route_probe.get("summary") or {}
    if int(summary.get("count") or 0) < 4:
        weak.append("route-security route probe measurement count is too small")
    expected_unauth = {
        "map slots unauthenticated",
        "auth me unauthenticated",
        "auth sessions unauthenticated",
    }
    unauth = list(summary.get("unauthenticated") or [])
    seen_unauth = {item.get("name") for item in unauth}
    for missing in sorted(expected_unauth - seen_unauth):
        weak.append(f"route-security missing unauthenticated probe: {missing}")
    for item in unauth:
        name = item.get("name") or "unknown unauthenticated probe"
        if item.get("ok") is not True:
            weak.append(f"route-security unauthenticated probe failed: {name}")
        statuses = set(item.get("status_codes") or [])
        if not statuses or not statuses.issubset({401, 403}):
            weak.append(f"route-security unauthenticated probe did not reject with 401/403: {name}")

    preflight = data.get("preflight") or {}
    if preflight.get("verdict") != "pass":
        weak.append("route-security preflight verdict is not pass")
    headers = set(preflight.get("index_headers") or [])
    required_headers = {
        "content-security-policy",
        "strict-transport-security",
        "x-content-type-options",
        "referrer-policy",
        "permissions-policy",
    }
    for header in sorted(required_headers - headers):
        weak.append(f"route-security missing header evidence: {header}")

    inventory = data.get("inventory") or {}
    if inventory.get("unique_method_paths") != 92:
        weak.append("route-security inventory does not have 92 public method/path entries")
    class_summary = inventory.get("class_summary") or {}
    if class_summary.get("public-write-auth-flow-rate-limited") != 5:
        weak.append("route-security rate-limited public auth-flow class count is not 5")
    if not class_summary:
        weak.append("route-security class summary is missing")

    auth = data.get("auth_security") or {}
    if auth.get("verdict") != "pass":
        weak.append("route-security auth evidence verdict is not pass")
    if auth.get("csrf_rejection_status") != 403:
        weak.append("route-security CSRF rejection status is not 403")
    if auth.get("cross_user_status") not in {403, 404}:
        weak.append("route-security cross-user denial status is not 403/404")
    if auth.get("stale_conflict_status") != 409:
        weak.append("route-security stale-version conflict status is not 409")
    if auth.get("default_map_slot_count") != 3 or auth.get("default_map_slot_numbers") != [1, 2, 3]:
        weak.append("route-security exactly-three map-slot evidence is missing")
    return weak


def auth_email_summary_weaknesses(data: dict[str, Any]) -> list[str]:
    weak: list[str] = []
    if data.get("verdict") != "pass":
        weak.append("auth-email summary verdict is not pass")
    if data.get("failures"):
        weak.append("auth-email summary has failures")

    rows = data.get("rows") or {}
    for user in ("user_a", "user_b"):
        registration = rows.get(f"{user}_registration_status")
        if registration not in {200, 201, 202}:
            weak.append(f"auth-email {user} registration status is not generic success")
        if rows.get(f"{user}_verification_token_supplied") is not True:
            weak.append(f"auth-email {user} verification token was not supplied")
        if rows.get(f"{user}_verification_status") != 200:
            weak.append(f"auth-email {user} verification status is not 200")
        if rows.get(f"{user}_login_status") != 200:
            weak.append(f"auth-email {user} login status is not 200")

    required_rows = {
        "password_reset_request_status": 200,
        "password_reset_token_supplied": True,
        "password_reset_complete_status": 200,
        "post_reset_login_status": 200,
        "session_cookie_secure": True,
        "session_cookie_httponly": True,
        "csrf_cookie_secure": True,
        "csrf_rejection_status": 403,
    }
    for key, expected in required_rows.items():
        if rows.get(key) != expected:
            weak.append(f"auth-email {key} is not {expected}")

    base_url = str(data.get("auth_base_url") or "")
    if base_url and urlparse(base_url).scheme != "https":
        weak.append("auth-email base URL is not HTTPS")
    if not data.get("auth_captured_at"):
        weak.append("auth-email captured timestamp is missing")
    return weak


JSON_VALIDATORS = {
    "00-public-staging-preflight.json": preflight_weaknesses,
    "01-image-manifest.json": image_manifest_weaknesses,
    "02-render-deploy.json": render_deploy_weaknesses,
    "auth-email-summary.json": auth_email_summary_weaknesses,
    "performance-evidence-summary.json": performance_summary_weaknesses,
    "route-security-summary.json": route_security_summary_weaknesses,
}


def file_status(name: str) -> dict[str, Any]:
    path = ROOT / name if name.startswith("docs/") else EVIDENCE / name
    out: dict[str, Any] = {"path": str(path.relative_to(ROOT)), "exists": path.exists()}
    if path.exists():
        out["bytes"] = path.stat().st_size
        if name in REQUIRED_DOCS and out["bytes"] < 40:
            out["doc_weak"] = "required documentation appears to be a placeholder"
        if path.suffix == ".json":
            data = load_json(path)
            out["json_verdict"] = data.get("verdict") if isinstance(data, dict) else None
            out["json_failures"] = data.get("failures") if isinstance(data, dict) else None
            out["parse_error"] = data.get("_parse_error") if isinstance(data, dict) else None
            if isinstance(data, dict) and not data.get("_parse_error"):
                out["secret_weak"] = [f"secret-like value at {item}" for item in json_secret_paths(data)]
            if isinstance(data, dict) and not data.get("_parse_error") and path.name in JSON_VALIDATORS:
                out["json_schema_weak"] = JSON_VALIDATORS[path.name](data)
        elif path.suffix == ".md" and not name.startswith("docs/"):
            text = path.read_text(errors="replace")
            verdict = ANY_VERDICT_RE.search(text)
            out["markdown_verdict"] = verdict.group(1).strip() if verdict else None
            out["markdown_verdict_pass"] = bool(PASS_VERDICT_RE.search(text))
            out["secret_weak"] = text_secret_findings(text)
            if path.name in GENERATED_MARKDOWN:
                out["generated_report_marker"] = bool(GENERATED_REPORT_RE.search(text))
                out["markdown_schema_weak"] = markdown_shape_weaknesses(path.name, text)
    return out


def evaluate(key: str, label: str, files: list[str], json_checks: list[str] | None = None) -> dict[str, Any]:
    statuses = [file_status(name) for name in files]
    missing = [item["path"] for item in statuses if not item["exists"]]
    weak = []
    for item in statuses:
        verdict = item.get("json_verdict")
        if verdict and verdict != "pass":
            weak.append(f"{item['path']} verdict={verdict}")
        if item.get("parse_error"):
            weak.append(f"{item['path']} parse_error={item['parse_error']}")
        if item.get("doc_weak"):
            weak.append(f"{item['path']} {item['doc_weak']}")
        weak.extend(f"{item['path']} {message}" for message in item.get("secret_weak", []))
        weak.extend(f"{item['path']} {message}" for message in item.get("json_schema_weak", []))
        if "markdown_verdict_pass" in item and not item["markdown_verdict_pass"]:
            verdict = item.get("markdown_verdict")
            if verdict:
                weak.append(f"{item['path']} markdown verdict={verdict}")
            else:
                weak.append(f"{item['path']} missing Markdown pass verdict")
        if item.get("generated_report_marker") is False:
            weak.append(f"{item['path']} missing generated report marker")
        weak.extend(f"{item['path']} {message}" for message in item.get("markdown_schema_weak", []))

    for check in json_checks or []:
        data = load_json(EVIDENCE / "00-public-staging-preflight.json") or {}
        section = data.get(check, {})
        if isinstance(section, dict) and not section.get("ok"):
            weak.append(f"preflight {check} not ok")

    status = "proven" if not missing and not weak else "missing" if missing else "weak"
    return {
        "key": key,
        "label": label,
        "status": status,
        "files": statuses,
        "missing": missing,
        "weak": weak,
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Gate Audit",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Verdict: **{payload['verdict']}**",
        "",
        "## Requirements",
        "",
        "| Status | Requirement | Missing/Weak Evidence |",
        "|---|---|---|",
    ]
    for item in payload["requirements"]:
        evidence = ", ".join(item["missing"] + item["weak"]) or "-"
        lines.append(f"| {item['status']} | {item['label']} | {evidence} |")
    lines.extend(["", "## Acceptance Criteria", "", "| Status | Criterion | Missing/Weak Evidence |", "|---|---|---|"])
    for item in payload["acceptance"]:
        evidence = ", ".join(item["missing"] + item["weak"]) or "-"
        lines.append(f"| {item['status']} | {item['label']} | {evidence} |")
    lines.append("")
    lines.append("This audit is strict: scaffolding does not count as public-staging proof.")
    return "\n".join(lines) + "\n"


def main() -> int:
    requirements = [evaluate(*item) for item in REQUIREMENTS]
    acceptance = [evaluate(key, label, files) for key, label, files in ACCEPTANCE]
    all_items = requirements + acceptance
    approved = all(item["status"] == "proven" for item in all_items)
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "requirements": requirements,
        "acceptance": acceptance,
        "verdict": "APPROVED FOR CONTROLLED PRIVATE BETA" if approved else "NOT APPROVED",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    MD_OUT.write_text(markdown(payload))
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    print(payload["verdict"])
    return 0 if approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
