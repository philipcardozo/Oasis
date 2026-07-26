#!/usr/bin/env python3
"""Build public-staging object-storage evidence.

The Phase 1.75 gate requires isolated private object storage for exports, logos,
future reports, and temporary private files. This report accepts only structured
non-secret evidence and cross-checks the broader infra/ops summaries.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"

CONFIGURATION_CHECKS = {
    "backend_s3": "S3-compatible backend is configured for staging",
    "provider_cloudflare_r2": "Cloudflare R2 or an approved S3-compatible provider is used",
    "staging_namespace_separate": "staging bucket or namespace is separate",
    "bucket_identifier_sanitized": "bucket identifier is sanitized in evidence",
    "server_side_encryption": "server-side encryption is enabled or provider enforced",
    "lifecycle_expiration": "lifecycle expiration is configured",
    "generated_exports_supported": "generated exports are stored in object storage",
    "approved_logos_supported": "approved logos can be stored in object storage",
    "future_report_artifacts_supported": "future report artifacts have a storage path",
    "temporary_private_files_supported": "temporary private files have a storage path",
}

ACCESS_CHECKS = {
    "private_by_default": "objects are private by default",
    "public_bucket_listing_disabled": "public bucket listing is disabled",
    "credentials_provider_managed": "credentials are provider-managed secrets",
    "least_privilege_credentials": "storage credentials are least privilege",
    "browser_credentials_absent": "browser receives no raw storage credentials",
    "signed_downloads_expire": "download authorization expires",
    "signed_operation_scope_limited": "signed operations are tightly scoped",
    "ownership_checks": "application ownership checks guard object access",
    "no_raw_object_url_authorization": "raw object URLs are not authorization",
}

VALIDATION_CHECKS = {
    "size_limit_enforced": "export/object size limit is enforced",
    "content_type_validation": "content type validation is enforced",
    "max_export_bytes_configured": "maximum export byte limit is configured",
    "allowed_content_types_recorded": "allowed content types are recorded",
}

FAILURE_CHECKS = {
    "storage_unavailable_probe_recorded": "storage unavailable behavior was probed",
    "export_status_accurate": "export status is accurate during storage failure",
    "partial_output_not_offered": "partial output is not offered",
    "retry_bounded": "retry behavior is bounded",
    "no_secret_leak_in_errors": "storage errors leak no secrets",
}


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def display_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() and path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    return value


def bool_row(key: str, label: str, value: bool, **extra: Any) -> dict[str, Any]:
    return {"key": key, "label": label, "value": bool(value), **extra}


def check_rows(data: dict[str, Any], section: str, required: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    checks = data.get(section) or {}
    rows = [bool_row(key, label, checks.get(key) is True) for key, label in required.items()]
    failures = [f"storage {section} check is not true: {row['key']}" for row in rows if row["value"] is not True]
    return rows, failures


def provider_ok(data: dict[str, Any]) -> bool:
    provider = str(data.get("provider") or "")
    return "cloudflare" in provider.lower() and "r2" in provider.lower()


def validation_rows(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    validation = data.get("validation_limits") or {}
    rows = [bool_row(key, label, validation.get(key) is True) for key, label in VALIDATION_CHECKS.items()]
    max_bytes = int(validation.get("max_export_bytes") or 0)
    rows.append(bool_row("max_export_bytes_positive", "maximum export bytes is positive", max_bytes > 0, max_export_bytes=max_bytes))
    allowed_content_types = validation.get("allowed_content_types") or []
    rows.append(
        bool_row(
            "allowed_content_type_count_positive",
            "at least one allowed content type is recorded",
            isinstance(allowed_content_types, list) and len(allowed_content_types) > 0,
            allowed_content_type_count=len(allowed_content_types) if isinstance(allowed_content_types, list) else 0,
        )
    )
    failures = [f"storage validation_limits check is not true: {row['key']}" for row in rows if row["value"] is not True]
    return rows, failures


def infra_storage_pass(infra: dict[str, Any] | None) -> bool:
    if not infra or not infra.get("input_captured_at"):
        return False
    result = ((infra.get("results") or {}).get("render_services") or {})
    if result.get("verdict") != "pass" or result.get("failures"):
        return False
    rows = {row.get("label"): row.get("value") for row in result.get("rows") or []}
    return rows.get("S3/R2 storage settings are configured") is True and rows.get("object storage bucket remains private") is True


def ops_storage_pass(ops: dict[str, Any] | None) -> bool:
    if not ops or not ops.get("input_captured_at"):
        return False
    results = ops.get("results") or {}
    backup_rows = {row.get("key"): row.get("value") for row in ((results.get("backup_restore") or {}).get("rows") or [])}
    obs_rows = {row.get("key"): row.get("value") for row in ((results.get("observability_alerts") or {}).get("rows") or [])}
    return (
        (results.get("backup_restore") or {}).get("verdict") == "pass"
        and backup_rows.get("object_storage_private") is True
        and (results.get("observability_alerts") or {}).get("verdict") == "pass"
        and obs_rows.get("signal.storage_usage") is True
        and obs_rows.get("alert.storage_quota_pressure") is True
        and obs_rows.get("redaction.storage_credentials") is True
    )


def cross_check_rows(infra: dict[str, Any] | None, ops: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
    rows = [
        bool_row("infra_storage_summary_pass", "infra summary proves S3/R2 private storage", infra_storage_pass(infra)),
        bool_row("ops_storage_summary_pass", "ops summary proves private storage and storage alerts", ops_storage_pass(ops)),
    ]
    failures = [f"storage cross-check is not true: {row['key']}" for row in rows if row["value"] is not True]
    return rows, failures


def build_payload(data: dict[str, Any], infra: dict[str, Any] | None, ops: dict[str, Any] | None, *, input_path: str, infra_path: str, ops_path: str) -> dict[str, Any]:
    failures: list[str] = []
    configuration, configuration_failures = check_rows(data, "storage_configuration", CONFIGURATION_CHECKS)
    access, access_failures = check_rows(data, "access_controls", ACCESS_CHECKS)
    validation, validation_failures = validation_rows(data)
    failure_behavior, failure_failures = check_rows(data, "failure_behavior", FAILURE_CHECKS)
    cross_checks, cross_failures = cross_check_rows(infra, ops)
    failures.extend(configuration_failures + access_failures + validation_failures + failure_failures + cross_failures)

    if not provider_ok(data):
        failures.append("storage provider is not Cloudflare R2")
    if not data.get("input_captured_at"):
        failures.append("storage input captured timestamp is missing")
    if urlparse(str(data.get("base_url") or "")).scheme != "https":
        failures.append("storage base URL is not HTTPS")
    if data.get("secret_free_evidence") is not True:
        failures.append("storage evidence is not marked secret-free")

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "input_captured_at": data.get("input_captured_at"),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "base_url": data.get("base_url"),
        "provider": data.get("provider"),
        "bucket_alias": data.get("bucket_alias"),
        "verdict": "pass" if not failures else "investigate",
        "failures": failures,
        "inputs": {
            "storage_evidence": display_path(input_path),
            "infra_summary": display_path(infra_path),
            "ops_summary": display_path(ops_path),
        },
        "storage_configuration": {"rows": configuration},
        "access_controls": {"rows": access},
        "validation_limits": {"rows": validation},
        "failure_behavior": {"rows": failure_behavior},
        "cross_checks": {"rows": cross_checks},
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Object Storage Evidence",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Base URL: `{payload['base_url']}`",
        f"Provider: `{payload['provider']}`",
        f"Bucket alias: `{payload['bucket_alias']}`",
        f"Verdict: **{payload['verdict']}**",
    ]
    for title, section in (
        ("Storage Configuration", "storage_configuration"),
        ("Access Controls", "access_controls"),
        ("Validation Limits", "validation_limits"),
        ("Export Failure Behavior", "failure_behavior"),
        ("Cross Checks", "cross_checks"),
    ):
        lines.extend(["", f"## {title}", "", "| Check | Result |", "|---|---|"])
        for row in payload[section]["rows"]:
            lines.append(f"| {row['label']} | `{row['value']}` |")
    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in payload["failures"])
    lines.append("")
    lines.append("This generated report contains sanitized object-storage evidence only.")
    return "\n".join(lines) + "\n"


def template() -> dict[str, Any]:
    return {
        "input_captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": "https://staging.example.com",
        "provider": "Cloudflare R2",
        "bucket_alias": "oasis-staging-objects",
        "secret_free_evidence": True,
        "storage_configuration": {key: True for key in CONFIGURATION_CHECKS},
        "access_controls": {key: True for key in ACCESS_CHECKS},
        "validation_limits": {
            **{key: True for key in VALIDATION_CHECKS},
            "max_export_bytes": 26214400,
            "allowed_content_types": ["application/json", "text/csv", "image/png"],
        },
        "failure_behavior": {key: True for key in FAILURE_CHECKS},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-template", action="store_true", help="print a non-secret object-storage evidence template and exit")
    parser.add_argument("--input", default=str(PUBLIC_EVIDENCE / "storage-evidence.json"))
    parser.add_argument("--infra-summary", default=str(PUBLIC_EVIDENCE / "infra-evidence-summary.json"))
    parser.add_argument("--ops-summary", default=str(PUBLIC_EVIDENCE / "ops-evidence-summary.json"))
    parser.add_argument("--output", default=str(PUBLIC_EVIDENCE / "19-object-storage.md"))
    parser.add_argument("--summary-output", default=str(PUBLIC_EVIDENCE / "storage-summary.json"))
    args = parser.parse_args()

    if args.print_template:
        print(json.dumps(template(), indent=2, sort_keys=True))
        return 0

    data = load_json(Path(args.input))
    if data is None:
        raise SystemExit(f"missing input: {args.input}")
    payload = build_payload(
        data,
        load_json(Path(args.infra_summary)),
        load_json(Path(args.ops_summary)),
        input_path=args.input,
        infra_path=args.infra_summary,
        ops_path=args.ops_summary,
    )
    output = Path(args.output)
    summary = Path(args.summary_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(payload))
    summary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging object-storage report to {output}")
    print(f"Wrote public staging object-storage summary to {summary}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
