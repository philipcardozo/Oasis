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


REQUIREMENTS = [
    ("public_dns", "Public DNS", ["00-public-staging-preflight.json"], ["dns"]),
    ("public_tls", "Public TLS", ["00-public-staging-preflight.json"], ["tls"]),
    ("secret_management", "Secure secret management", ["04-render-services.md"], []),
    ("managed_postgres", "Managed PostgreSQL", ["04-render-services.md", "05-migration-version.md"], []),
    ("persistent_storage", "Persistent object and database storage", ["04-render-services.md", "12-backup-restore.md"], []),
    ("reverse_proxy", "Public reverse-proxy behavior", ["00-public-staging-preflight.json", "02-dns-tls-edge.md"], []),
    ("email_delivery", "Authentication email delivery", ["06-auth-email.md"], []),
    ("api_worker_separation", "API and worker separation", ["02-render-deploy.json", "10-worker-jobs.md"], []),
    ("attack_surface", "External attack-surface controls", ["03-cloudflare-access.md", "09-route-security.md"], []),
    ("browser_compatibility", "Remote browser compatibility", ["07-browser-matrix.md"], []),
    ("deployment_automation", "Deployment automation", ["01-image-manifest.json", "02-render-deploy.json"], []),
    ("rollback", "Rollback", ["13-failure-rollback.md"], []),
    ("backup_restore", "Backup and restore", ["12-backup-restore.md"], []),
    ("monitoring_alerting", "Monitoring and alerting", ["14-observability-alerts.md"], []),
    ("private_beta_access", "Private-beta access control", ["03-cloudflare-access.md", "06-auth-email.md"], []),
    ("performance", "Public performance measurements", ["15-performance.md"], []),
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
    ("auth_email", "Email verification and password reset work", ["06-auth-email.md"]),
    ("secure_cookies", "Session cookies are secure", ["06-auth-email.md", "00-public-staging-preflight.json"]),
    ("csrf", "CSRF works", ["09-route-security.md"]),
    ("route_classification", "Every route has explicit security classification", ["09-route-security.md"]),
    ("cross_user_denied", "Cross-user access is denied", ["09-route-security.md"]),
    ("three_slots", "Exactly three map slots persist across devices", ["07-browser-matrix.md"]),
    ("browser_map", "Real browser map rendering works", ["07-browser-matrix.md", "08-map-provider-capture.md"]),
    ("no_bulk_first_paint", "/api/universe/bulk is absent from initial paint", ["15-performance.md"]),
    ("zero_api_acquisition", "API user requests perform zero external acquisition", ["11-network-isolation.md"]),
    ("worker_recovery", "Worker jobs are bounded and recoverable", ["10-worker-jobs.md"]),
    ("private_storage", "Object storage remains private", ["12-backup-restore.md"]),
    ("headers_cors_hosts", "Security headers, CORS, and trusted hosts are correct", ["00-public-staging-preflight.json", "09-route-security.md"]),
    ("rate_limit_proxy", "Rate limiting works through public proxy", ["09-route-security.md"]),
    ("restore_success", "Backup and restore succeed", ["12-backup-restore.md"]),
    ("rollback_success", "Deployment rollback succeeds", ["13-failure-rollback.md"]),
    ("alerts", "Alerts detect key failures", ["14-observability-alerts.md"]),
    ("providers_disabled", "Unlicensed providers remain disabled", ["08-map-provider-capture.md"]),
    ("test_suites_pass", "Test suites pass", ["01-image-manifest.json"]),
    ("cicd_safe", "CI/CD deploys immutable images safely", ["01-image-manifest.json", "02-render-deploy.json"]),
    ("docs_current", "Documentation is current", ["docs/PHASE-1-75-PUBLIC-STAGING.md", "docs/PUBLIC-STAGING-RUNBOOK.md"]),
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


JSON_VALIDATORS = {
    "00-public-staging-preflight.json": preflight_weaknesses,
    "01-image-manifest.json": image_manifest_weaknesses,
    "02-render-deploy.json": render_deploy_weaknesses,
}


def file_status(name: str) -> dict[str, Any]:
    path = ROOT / name if name.startswith("docs/") else EVIDENCE / name
    out: dict[str, Any] = {"path": str(path.relative_to(ROOT)), "exists": path.exists()}
    if path.exists():
        out["bytes"] = path.stat().st_size
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
