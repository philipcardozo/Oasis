#!/usr/bin/env python3
"""Generate strict public-staging infrastructure evidence reports.

The input is sanitized structured evidence from provider dashboards, public
preflight probes, and deployment logs. This script does not prove staging by
itself; it prevents hand-written Markdown from claiming pass without the
required non-secret proof.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
EXPECTED_MIGRATION = "29995ef61d8e"

REPORTS = {
    "dns_tls_edge": "02-dns-tls-edge.md",
    "cloudflare_access": "03-cloudflare-access.md",
    "render_services": "04-render-services.md",
    "migration_version": "05-migration-version.md",
}

SECRET_KEY_RE = re.compile(
    r"(password|passwd|token|cookie|authorization|secret|api[_-]?key|private[_-]?key|credential|database[_-]?url)",
    re.IGNORECASE,
)
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
PUBLIC_HASH_RE = re.compile(r"(?:sha256:)?[0-9a-f]{7,128}", re.IGNORECASE)
URL_WITH_CREDENTIALS_RE = re.compile(r"://[^/\s:@]+:[^/\s:@]+@")
LONG_SECRET_RE = re.compile(r"(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9_\-+/=]{32,}")

DNS_TLS_REQUIRED_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin",
    "content-security-policy": "default-src 'self'",
}

ACCESS_REQUIRED = {
    "enabled": "Cloudflare Access is enabled",
    "policy_allowlist": "tester allowlist policy is configured",
    "unauthenticated_denied": "unauthenticated public access is denied or challenged",
    "service_token_probe": "service-token probe reaches OASIS through Access",
    "oasis_auth_inside_boundary": "OASIS auth works inside the edge boundary",
    "registration_allowlist": "OASIS registration is invitation or allowlist bounded",
    "hidden_url_not_only_control": "hidden URL is not the only access control",
    "access_logs_reviewed": "Access audit logs were reviewed",
    "waf_or_rate_rules": "Cloudflare WAF or rate rules are enabled for staging",
}

RENDER_REQUIRED = {
    "api_service": "Render API web service exists",
    "worker_service": "Render worker service exists",
    "managed_postgres": "Render managed PostgreSQL exists",
    "private_database_connectivity": "database connectivity is private/provider scoped",
    "postgres_tls": "PostgreSQL TLS is required or provider enforced",
    "postgres_backups": "managed PostgreSQL backups are enabled",
    "secrets_provider_managed": "secrets are stored in provider secret management",
    "secret_values_redacted": "evidence contains only secret names/status, not values",
    "required_env_present": "required staging environment names are present",
    "smtp_configured": "SMTP email settings are configured",
    "s3_storage_configured": "S3/R2 storage settings are configured",
    "object_storage_private": "object storage bucket remains private",
    "api_worker_separate_commands": "API and worker use separate process commands",
    "api_worker_same_image": "API and worker use the same immutable image",
    "api_worker_same_commit": "API and worker use the same tested commit",
    "health_checks_configured": "Render health checks are configured",
    "rollback_available": "previous successful deploy remains available for rollback",
    "logs_available": "provider logs are available for API and worker",
    "no_sqlite_fallback": "staging cannot fall back to SQLite",
}

MIGRATION_REQUIRED = {
    "predeploy_ran": "Render API predeploy ran before traffic",
    "alembic_upgrade_head": "alembic upgrade head ran",
    "migration_check_ok": "server.migration_check returned ok",
    "predeploy_before_worker": "migration verification completed before worker deploy",
    "database_engine_postgresql": "deployed database engine is PostgreSQL",
    "no_sqlite_fallback": "deployed environment did not fall back to SQLite",
    "deployed_version_checked": "deployed /version or migration evidence was checked",
    "failure_stops_release": "migration failure stops the release",
}


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def load_json(path: Path, *, required: bool = True) -> dict[str, Any] | None:
    if not path.exists():
        if required:
            raise SystemExit(f"missing input: {path}")
        return None
    return json.loads(path.read_text())


def secret_like_paths(value: Any, path: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            lowered = str(key).lower()
            names_only = any(marker in lowered for marker in ("env_names", "header_names", "secret_names", "credential_names"))
            if SECRET_KEY_RE.search(str(key)) and isinstance(item, str) and not safe_secret_name_value(item, names_only):
                findings.append(child)
            findings.extend(secret_like_paths(item, child))
    elif isinstance(value, list):
        names_only = any(marker in path.lower() for marker in ("env_names", "header_names", "secret_names", "credential_names"))
        for idx, item in enumerate(value):
            child = f"{path}[{idx}]"
            if isinstance(item, str) and not names_only and secretish_string(item):
                findings.append(child)
            findings.extend(secret_like_paths(item, child))
    elif isinstance(value, str) and secretish_string(value):
        findings.append(path or "<root>")
    return sorted(set(findings))


def safe_secret_name_value(value: str, names_only: bool = False) -> bool:
    if value in {"", "<redacted>", "redacted", "***", "present", "configured"}:
        return True
    if names_only or ENV_NAME_RE.match(value):
        return True
    return False


def secretish_string(value: str) -> bool:
    if PUBLIC_HASH_RE.fullmatch(value):
        return False
    if URL_WITH_CREDENTIALS_RE.search(value):
        return True
    if value.startswith(("sk_", "pk_", "ghp_", "ghs_", "xoxb-", "xoxp-")):
        return True
    return bool(LONG_SECRET_RE.fullmatch(value)) and not ENV_NAME_RE.fullmatch(value)


def check_bool(section: dict[str, Any], required: dict[str, str]) -> tuple[list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    rows: list[dict[str, Any]] = []
    checks = section.get("checks") or {}
    for key, label in required.items():
        value = checks.get(key)
        rows.append({"label": label, "value": value})
        if value is not True:
            failures.append(f"{key} is not true")
    return failures, rows


def endpoint_ok(preflight: dict[str, Any], path: str) -> bool:
    result = (preflight.get("endpoints") or {}).get(path) or {}
    return result.get("ok") is True and int(result.get("status") or 0) < 400


def endpoint_headers(preflight: dict[str, Any], path: str) -> dict[str, Any]:
    return ((preflight.get("endpoints") or {}).get(path) or {}).get("headers") or {}


def evaluate_dns_tls(preflight: dict[str, Any] | None, infra: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    rows: list[dict[str, Any]] = []
    if not preflight:
        return result("dns_tls_edge", ["public preflight evidence is missing"], rows)

    rows.extend(
        [
            {"label": "preflight verdict", "value": preflight.get("verdict")},
            {"label": "base URL", "value": preflight.get("base_url")},
            {"label": "URL scheme", "value": (preflight.get("url") or {}).get("scheme")},
            {"label": "DNS ok", "value": (preflight.get("dns") or {}).get("ok")},
            {"label": "TLS ok", "value": (preflight.get("tls") or {}).get("ok")},
            {"label": "HTTP redirect status", "value": (preflight.get("http_to_https_redirect") or {}).get("status")},
        ]
    )
    if preflight.get("verdict") != "pass":
        failures.append("public preflight verdict is not pass")
    if (preflight.get("url") or {}).get("scheme") != "https":
        failures.append("base URL is not HTTPS")
    if (preflight.get("dns") or {}).get("ok") is not True:
        failures.append("DNS lookup is not ok")
    if (preflight.get("tls") or {}).get("ok") is not True:
        failures.append("TLS probe is not ok")
    if (preflight.get("http_to_https_redirect") or {}).get("status") not in {301, 302, 307, 308}:
        failures.append("HTTP endpoint does not redirect to HTTPS")

    for path in ("/index.html", "/healthz", "/readyz", "/version"):
        ok = endpoint_ok(preflight, path)
        rows.append({"label": f"{path} successful", "value": ok})
        if not ok:
            failures.append(f"{path} did not return a successful response")

    headers = endpoint_headers(preflight, "/index.html")
    for key, expected in DNS_TLS_REQUIRED_HEADERS.items():
        value = str(headers.get(key) or "")
        ok = expected in value
        rows.append({"label": f"/index.html {key}", "value": ok})
        if not ok:
            failures.append(f"/index.html missing expected {key}: {expected}")

    hsts = str(headers.get("strict-transport-security") or "")
    hsts_lower = hsts.lower()
    allow_hsts_subdomains = bool((infra.get("dns_tls_edge") or {}).get("allow_hsts_subdomains"))
    rows.append({"label": "HSTS max-age present", "value": "max-age=" in hsts_lower})
    rows.append({"label": "HSTS includeSubDomains", "value": "includesubdomains" in hsts_lower})
    rows.append({"label": "HSTS preload", "value": "preload" in hsts_lower})
    if "max-age=" not in hsts_lower:
        failures.append("/index.html missing HSTS max-age")
    if not allow_hsts_subdomains and "includesubdomains" in hsts_lower:
        failures.append("HSTS includeSubDomains is not allowed for this staging gate")
    if not allow_hsts_subdomains and "preload" in hsts_lower:
        failures.append("HSTS preload is not allowed for this staging gate")

    return result("dns_tls_edge", failures, rows)


def evaluate_cloudflare_access(infra: dict[str, Any]) -> dict[str, Any]:
    section = infra.get("cloudflare_access") or {}
    if not section:
        return result("cloudflare_access", ["cloudflare_access evidence section is missing"], [])
    failures, rows = check_bool(section, ACCESS_REQUIRED)
    provider = str(section.get("provider") or "")
    rows.insert(0, {"label": "provider", "value": provider or "missing"})
    if "cloudflare" not in provider.lower():
        failures.append("provider is not Cloudflare Access")
    unauthenticated = section.get("unauthenticated_status")
    service_token = section.get("service_token_status")
    oasis_auth = section.get("oasis_auth_status")
    rows.extend(
        [
            {"label": "unauthenticated status", "value": unauthenticated},
            {"label": "service-token status", "value": service_token},
            {"label": "OASIS auth status", "value": oasis_auth},
            {"label": "header names only", "value": section.get("header_names_only")},
        ]
    )
    if unauthenticated not in {302, 401, 403}:
        failures.append("unauthenticated access was not denied or challenged")
    if service_token != 200:
        failures.append("service-token probe did not return 200")
    if oasis_auth != 200:
        failures.append("OASIS auth inside Access did not return 200")
    if section.get("header_names_only") is not True:
        failures.append("Cloudflare evidence must contain header names only")
    return result("cloudflare_access", failures, rows)


def split_digest(image_url: str) -> str:
    return image_url.rsplit("@", 1)[1] if "@" in image_url else ""


def deploy_roles(render_deploy: dict[str, Any] | None) -> list[str]:
    return sorted(item.get("role") for item in (render_deploy or {}).get("deployments") or [])


def evaluate_render_services(
    infra: dict[str, Any],
    render_deploy: dict[str, Any] | None,
    image_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    section = infra.get("render_services") or {}
    if not section:
        return result("render_services", ["render_services evidence section is missing"], [])
    failures, rows = check_bool(section, RENDER_REQUIRED)
    rows.extend(
        [
            {"label": "image manifest verdict", "value": (image_manifest or {}).get("verdict")},
            {"label": "Render deploy verdict", "value": (render_deploy or {}).get("verdict")},
            {"label": "Render deploy roles", "value": ", ".join(deploy_roles(render_deploy))},
        ]
    )
    if (image_manifest or {}).get("verdict") != "pass":
        failures.append("image manifest verdict is not pass")
    if (render_deploy or {}).get("verdict") != "pass":
        failures.append("Render deploy verdict is not pass")
    if deploy_roles(render_deploy) != ["api", "worker"]:
        failures.append("Render deploy evidence does not contain exactly api and worker")
    image_url = str((render_deploy or {}).get("image_url") or "")
    manifest_image = str((image_manifest or {}).get("image") or "")
    digest = split_digest(image_url)
    rows.append({"label": "deploy image matches manifest", "value": bool(image_url and image_url == manifest_image)})
    if not image_url or image_url != manifest_image:
        failures.append("Render deployed image does not match image manifest")
    if digest and digest != (image_manifest or {}).get("digest"):
        failures.append("Render deployed digest does not match image manifest digest")
    if "@sha256:" not in image_url:
        failures.append("Render deployed image is not digest pinned")
    return result("render_services", failures, rows)


def current_revisions(section: dict[str, Any]) -> list[str]:
    value = section.get("current_revision")
    if value is None:
        value = section.get("current")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def evaluate_migration_version(
    infra: dict[str, Any],
    render_deploy: dict[str, Any] | None,
    image_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    section = infra.get("migration") or {}
    if not section:
        return result("migration_version", ["migration evidence section is missing"], [])
    failures, rows = check_bool(section, MIGRATION_REQUIRED)
    expected = str(section.get("expected_revision") or EXPECTED_MIGRATION)
    current = current_revisions(section)
    rows.extend(
        [
            {"label": "expected revision", "value": expected},
            {"label": "current revision", "value": ", ".join(current) or "missing"},
            {"label": "image manifest migration check", "value": (image_manifest or {}).get("migration_check")},
            {"label": "Render deploy verdict", "value": (render_deploy or {}).get("verdict")},
        ]
    )
    if expected != EXPECTED_MIGRATION:
        failures.append(f"expected revision is {expected}, expected {EXPECTED_MIGRATION}")
    if current != [EXPECTED_MIGRATION]:
        failures.append(f"current revision is {current}, expected [{EXPECTED_MIGRATION!r}]")
    if (image_manifest or {}).get("migration_check") != "pass":
        failures.append("image manifest migration_check is not pass")
    if (render_deploy or {}).get("verdict") != "pass":
        failures.append("Render deploy verdict is not pass")
    if section.get("database_url_redacted") is not True:
        failures.append("migration evidence must confirm DATABASE_URL is redacted")
    rows.append({"label": "DATABASE_URL redacted", "value": section.get("database_url_redacted")})
    return result("migration_version", failures, rows)


def result(kind: str, failures: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": kind,
        "verdict": "pass" if not failures else "investigate",
        "failures": failures,
        "rows": rows,
    }


def append_secret_failures(results: dict[str, dict[str, Any]], inputs: dict[str, Any]) -> None:
    for name, data in inputs.items():
        paths = secret_like_paths(data)
        if not paths:
            continue
        message = f"{name} contains secret-like values at: {', '.join(paths)}"
        for output in results.values():
            output["failures"].append(message)
            output["verdict"] = "investigate"


def safe_display(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if secretish_string(text) or URL_WITH_CREDENTIALS_RE.search(text):
        return "<redacted>"
    return text.replace("|", "\\|")


def markdown(kind: str, section: dict[str, Any] | None, output: dict[str, Any], payload: dict[str, Any]) -> str:
    title = {
        "dns_tls_edge": "Public Staging DNS TLS And Edge Evidence",
        "cloudflare_access": "Public Staging Cloudflare Access Evidence",
        "render_services": "Public Staging Render Services Evidence",
        "migration_version": "Public Staging Migration Version Evidence",
    }[kind]
    lines = [
        f"# {title}",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Source captured: `{(section or {}).get('captured_at', payload.get('input_captured_at') or 'missing')}`",
        f"Evidence source: `{safe_display((section or {}).get('source', 'missing'))}`",
        f"Verdict: **{output['verdict']}**",
        "",
        "## Checks",
        "",
        "| Check | Evidence value |",
        "|---|---|",
    ]
    for row in output["rows"]:
        lines.append(f"| {safe_display(row['label'])} | `{safe_display(row['value'])}` |")
    if output["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {safe_display(item)}" for item in output["failures"])
    lines.append("")
    lines.append("This generated report contains no secret values, cookies, private token URLs, raw authorization headers, database URLs, SMTP credentials, or storage credentials.")
    return "\n".join(lines) + "\n"


def build_payload(
    infra: dict[str, Any],
    preflight: dict[str, Any] | None,
    render_deploy: dict[str, Any] | None,
    image_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    results = {
        "dns_tls_edge": evaluate_dns_tls(preflight, infra),
        "cloudflare_access": evaluate_cloudflare_access(infra),
        "render_services": evaluate_render_services(infra, render_deploy, image_manifest),
        "migration_version": evaluate_migration_version(infra, render_deploy, image_manifest),
    }
    append_secret_failures(
        results,
        {
            "infra evidence": infra,
            "preflight evidence": preflight or {},
            "Render deploy evidence": render_deploy or {},
            "image manifest evidence": image_manifest or {},
        },
    )
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "input_captured_at": infra.get("captured_at"),
        "results": results,
    }


def write_reports(infra: dict[str, Any], payload: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for kind, filename in REPORTS.items():
        section = infra.get(kind) or infra.get("migration" if kind == "migration_version" else kind)
        output = payload["results"][kind]
        (output_dir / filename).write_text(markdown(kind, section, output, payload))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(EVIDENCE / "infra-evidence.json"))
    parser.add_argument("--preflight", default=str(EVIDENCE / "00-public-staging-preflight.json"))
    parser.add_argument("--render-deploy", default=str(EVIDENCE / "02-render-deploy.json"))
    parser.add_argument("--image-manifest", default=str(EVIDENCE / "01-image-manifest.json"))
    parser.add_argument("--output-dir", default=str(EVIDENCE))
    parser.add_argument("--summary-output", default=str(EVIDENCE / "infra-evidence-summary.json"))
    args = parser.parse_args()

    infra = load_json(Path(args.input)) or {}
    preflight = load_json(Path(args.preflight))
    render_deploy = load_json(Path(args.render_deploy))
    image_manifest = load_json(Path(args.image_manifest))
    payload = build_payload(infra, preflight, render_deploy, image_manifest)
    output_dir = Path(args.output_dir)
    write_reports(infra, payload, output_dir)
    summary = Path(args.summary_output)
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    failures = {
        kind: output["failures"]
        for kind, output in payload["results"].items()
        if output["verdict"] != "pass"
    }
    print(f"Wrote public staging infra reports to {output_dir}")
    print(json.dumps({"verdict": "pass" if not failures else "investigate", "failures": failures}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
