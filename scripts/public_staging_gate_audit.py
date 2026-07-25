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
        elif path.suffix == ".md" and not name.startswith("docs/"):
            text = path.read_text(errors="replace")
            verdict = ANY_VERDICT_RE.search(text)
            out["markdown_verdict"] = verdict.group(1).strip() if verdict else None
            out["markdown_verdict_pass"] = bool(PASS_VERDICT_RE.search(text))
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
