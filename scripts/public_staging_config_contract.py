#!/usr/bin/env python3
"""Validate public-staging Render and Compose configuration contracts."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
DEFAULT_OUTPUT = PUBLIC_EVIDENCE / "public-staging-config-contract.json"
DEPLOY_PROVIDERS = {"render", "gcp"}
GCP_REQUIRED_ENV = {
    "GCP_PROJECT_ID",
    "GCP_REGION",
    "GCP_ARTIFACT_REPOSITORY",
    "GCP_CLOUD_RUN_SERVICE",
    "GCP_CLOUD_RUN_WORKER_POOL",
    "GCP_CLOUD_SQL_INSTANCE",
    "GCP_STORAGE_BUCKET",
    "STAGING_URL",
}
LOCAL_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
RESERVED_PUBLIC_HOSTS = {"example.com", "example.net", "example.org"}
RESERVED_PUBLIC_SUFFIXES = (".example.com", ".example.net", ".example.org", ".invalid", ".test")

RENDER_SYNC_FALSE = {
    "OASIS_PUBLIC_BASE_URL",
    "OASIS_API_BASE_URL",
    "OASIS_ALLOWED_ORIGINS",
    "OASIS_TRUSTED_HOSTS",
    "OASIS_REGISTRATION_ALLOWED_EMAILS",
    "OASIS_EMAIL_FROM",
    "OASIS_SMTP_HOST",
    "OASIS_SMTP_USER",
    "OASIS_SMTP_PASSWORD",
    "OASIS_S3_BUCKET",
    "OASIS_S3_ENDPOINT",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
}

RENDER_LITERAL_VALUES = {
    "OASIS_MODE": "staging",
    "OASIS_ENV": "staging",
    "OASIS_COOKIE_SECURE": "true",
    "OASIS_COOKIE_SAMESITE": "lax",
    "OASIS_TRUST_PROXY": "true",
    "OASIS_EMAIL_BACKEND": "smtp",
    "OASIS_SMTP_PORT": "587",
    "OASIS_SMTP_STARTTLS": "true",
    "OASIS_STORAGE_BACKEND": "s3",
    "OASIS_S3_REGION": "auto",
    "OASIS_LOG_JSON": "true",
    "OASIS_FEATURE_SATELLITE": "false",
    "OASIS_FEATURE_PRICES": "false",
    "OASIS_FEATURE_LOGOS": "false",
}

COMPOSE_APP_ENV = {
    "OASIS_DATABASE_URL",
    "OASIS_SESSION_SECRET",
    "OASIS_ALLOWED_ORIGINS",
    "OASIS_TRUSTED_HOSTS",
    "OASIS_PUBLIC_BASE_URL",
    "OASIS_API_BASE_URL",
    "OASIS_EMAIL_BACKEND",
    "OASIS_EMAIL_FROM",
    "OASIS_SMTP_HOST",
    "OASIS_SMTP_PORT",
    "OASIS_SMTP_STARTTLS",
    "OASIS_SMTP_USER",
    "OASIS_SMTP_PASSWORD",
    "OASIS_STORAGE_BACKEND",
    "OASIS_S3_BUCKET",
    "OASIS_S3_REGION",
    "OASIS_S3_ENDPOINT",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
}

COMPOSE_ENV_WITHOUT_FALLBACK = {
    "OASIS_SESSION_SECRET",
    "OASIS_ALLOWED_ORIGINS",
    "OASIS_TRUSTED_HOSTS",
    "OASIS_PUBLIC_BASE_URL",
    "OASIS_API_BASE_URL",
    "OASIS_EMAIL_FROM",
    "OASIS_SMTP_HOST",
    "OASIS_SMTP_USER",
    "OASIS_SMTP_PASSWORD",
    "OASIS_STORAGE_BACKEND",
    "OASIS_S3_BUCKET",
    "OASIS_S3_ENDPOINT",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
}


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def render_env_group(render_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = render_config.get("envVarGroups") or []
    group = next((item for item in groups if item.get("name") == "oasis-staging-shared"), {})
    return {item.get("key"): item for item in group.get("envVars") or [] if item.get("key")}


def service_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item.get("name"): item for item in config.get("services") or [] if item.get("name")}


def env_map(service: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item.get("key"): item for item in service.get("envVars") or [] if item.get("key")}


def compose_env(service: dict[str, Any]) -> dict[str, Any]:
    value = service.get("environment") or {}
    return value if isinstance(value, dict) else {}


def row(key: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"key": key, "ok": bool(ok), "detail": detail}


def normalize_provider(value: str | None) -> str:
    provider = (value or "render").strip().lower()
    if provider not in DEPLOY_PROVIDERS:
        return provider
    return provider


def required_env_reference(value: Any, key: str) -> bool:
    return isinstance(value, str) and value.strip() == f"${{{key}}}"


def public_https_url(value: str | None) -> bool:
    parsed = urlparse(str(value or ""))
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname:
        return False
    if hostname in LOCAL_PUBLIC_HOSTS or hostname.endswith(".local"):
        return False
    if hostname in RESERVED_PUBLIC_HOSTS or hostname.endswith(RESERVED_PUBLIC_SUFFIXES):
        return False
    return True


def evaluate_gcp(env: Mapping[str, str | None]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for key in sorted(GCP_REQUIRED_ENV):
        rows.append(row(f"gcp_env_{key}", bool(env.get(key)), f"{key} is supplied outside Git"))
    rows.append(row("gcp_provider_selected", normalize_provider(env.get("OASIS_DEPLOY_PROVIDER")) == "gcp", "OASIS_DEPLOY_PROVIDER=gcp"))
    rows.append(row("gcp_region_us_east1", env.get("GCP_REGION") == "us-east1", "GCP_REGION=us-east1"))
    rows.append(row("gcp_staging_url_public_https", public_https_url(env.get("STAGING_URL")), "STAGING_URL is a real public HTTPS URL"))
    rows.append(row("gcp_artifact_repository_named", bool(env.get("GCP_ARTIFACT_REPOSITORY")), "Artifact Registry repository is named"))
    rows.append(row("gcp_cloud_storage_bucket_named", bool(env.get("GCP_STORAGE_BUCKET")), "Cloud Storage bucket is named"))
    rows.append(row("gcp_cloud_sql_instance_named", bool(env.get("GCP_CLOUD_SQL_INSTANCE")), "Cloud SQL PostgreSQL instance is named"))
    rows.append(row("gcp_cloud_run_api_named", bool(env.get("GCP_CLOUD_RUN_SERVICE")), "Cloud Run API service is named"))
    rows.append(row("gcp_cloud_run_worker_pool_named", bool(env.get("GCP_CLOUD_RUN_WORKER_POOL")), "Cloud Run worker pool is named"))

    for item in rows:
        if not item["ok"]:
            failures.append(item["key"])
    return rows, failures


def evaluate_render(render_config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    env = render_env_group(render_config)

    session = env.get("OASIS_SESSION_SECRET") or {}
    rows.append(row("render_session_secret_generated", session.get("generateValue") is True and "value" not in session, "OASIS_SESSION_SECRET uses generateValue and no committed value"))

    for key in sorted(RENDER_SYNC_FALSE):
        item = env.get(key) or {}
        ok = item.get("sync") is False and "value" not in item and "generateValue" not in item
        rows.append(row(f"render_sync_false_{key}", ok, f"{key} is sync:false outside Git"))

    for key, expected in sorted(RENDER_LITERAL_VALUES.items()):
        item = env.get(key) or {}
        rows.append(row(f"render_value_{key}", item.get("value") == expected, f"{key}={expected}"))

    services = service_map(render_config)
    api = services.get("oasis-api-staging") or {}
    worker = services.get("oasis-worker-staging") or {}
    dbs = {item.get("name"): item for item in render_config.get("databases") or [] if item.get("name")}
    database = dbs.get("oasis-postgres-staging") or {}
    rows.append(row("render_postgres_exists", bool(database), "oasis-postgres-staging database exists"))
    rows.append(row("render_postgres_ip_allowlist_empty", database.get("ipAllowList") == [], "managed Postgres has no public IP allow list"))
    rows.append(row("render_api_predeploy_migration_check", "server.migration_check" in str(api.get("preDeployCommand") or ""), "API predeploy runs migration check"))
    rows.append(row("render_worker_is_worker", worker.get("type") == "worker" and "server.worker" in str(worker.get("dockerCommand") or ""), "worker uses same image with worker command"))

    for service_name, service in (("api", api), ("worker", worker)):
        service_env = env_map(service)
        for key in ("OASIS_DATABASE_URL", "DATABASE_URL"):
            item = service_env.get(key) or {}
            ok = (item.get("fromDatabase") or {}).get("name") == "oasis-postgres-staging"
            rows.append(row(f"render_{service_name}_{key}_from_postgres", ok, f"{service_name} {key} comes from managed Postgres"))

    for item in rows:
        if not item["ok"]:
            failures.append(item["key"])
    return rows, failures


def evaluate_compose(compose_config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    services = compose_config.get("services") or {}
    for service_name in ("migrate", "api", "worker"):
        env = compose_env(services.get(service_name) or {})
        for key in sorted(COMPOSE_APP_ENV):
            rows.append(row(f"compose_{service_name}_env_{key}", key in env, f"{service_name} receives {key} from local env/defaults"))
        for key in sorted(COMPOSE_ENV_WITHOUT_FALLBACK):
            rows.append(row(
                f"compose_{service_name}_env_required_{key}",
                required_env_reference(env.get(key), key),
                f"{service_name} requires {key} from env with no local/default fallback",
            ))
    rows.append(row("compose_worker_not_http", "server.worker" in str((services.get("worker") or {}).get("command") or ""), "worker role does not serve HTTP"))
    rows.append(row("compose_db_persistent_volume", "pgdata" in str((services.get("db") or {}).get("volumes") or []), "Postgres uses pgdata volume"))

    for item in rows:
        if not item["ok"]:
            failures.append(item["key"])
    return rows, failures


def build_payload(
    *,
    render_path: Path = ROOT / "render.yaml",
    compose_path: Path = ROOT / "compose.yaml",
    env: Mapping[str, str | None] | None = None,
    provider: str | None = None,
    captured_at: str | None = None,
) -> dict[str, Any]:
    env = env or os.environ
    provider = normalize_provider(provider or env.get("OASIS_DEPLOY_PROVIDER"))
    render_rows: list[dict[str, Any]] = []
    render_failures: list[str] = []
    gcp_rows: list[dict[str, Any]] = []
    gcp_failures: list[str] = []
    if provider == "render":
        render_rows, render_failures = evaluate_render(load_yaml(render_path))
        gcp_verdict = "not_applicable"
    elif provider == "gcp":
        gcp_rows, gcp_failures = evaluate_gcp(env)
        gcp_verdict = "pass" if not gcp_failures else "investigate"
    else:
        gcp_failures = [f"unsupported_provider_{provider}"]
        gcp_verdict = "investigate"
    compose_rows, compose_failures = evaluate_compose(load_yaml(compose_path))
    failures = [*render_failures, *gcp_failures, *compose_failures]
    return {
        "captured_at": captured_at or utc_now(),
        "branch": git_value("branch", "--show-current"),
        "commit": git_value("rev-parse", "HEAD"),
        "deploy_provider": provider,
        "not_public_staging_proof": True,
        "inputs": {
            "render": str(render_path.relative_to(ROOT)) if render_path.is_relative_to(ROOT) else str(render_path),
            "compose": str(compose_path.relative_to(ROOT)) if compose_path.is_relative_to(ROOT) else str(compose_path),
        },
        "render": {
            "rows": render_rows,
            "failures": render_failures,
            "verdict": "pass" if provider == "render" and not render_failures else ("investigate" if provider == "render" else "not_applicable"),
        },
        "gcp": {"rows": gcp_rows, "failures": gcp_failures, "verdict": gcp_verdict},
        "compose": {"rows": compose_rows, "failures": compose_failures, "verdict": "pass" if not compose_failures else "investigate"},
        "failures": failures,
        "verdict": "pass" if not failures else "investigate",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render", default=str(ROOT / "render.yaml"))
    parser.add_argument("--compose", default=str(ROOT / "compose.yaml"))
    parser.add_argument("--provider", choices=sorted(DEPLOY_PROVIDERS), default=os.environ.get("OASIS_DEPLOY_PROVIDER", "render"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = build_payload(render_path=Path(args.render), compose_path=Path(args.compose), provider=args.provider)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging config contract to {output}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
