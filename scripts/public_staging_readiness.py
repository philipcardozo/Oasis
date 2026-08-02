#!/usr/bin/env python3
"""Check whether public-staging deployment prerequisites are configured.

This is not public-staging proof. It records only presence/absence and provider
metadata needed before the real public deploy, without storing secret values.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.public_staging_config_contract import build_payload as build_config_contract

EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"

LOCAL_ENV_REQUIRED = [
    "STAGING_URL",
    "OASIS_CF_ACCESS_CLIENT_ID",
    "OASIS_CF_ACCESS_CLIENT_SECRET",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_ZONE_ID",
    "RENDER_API_KEY",
    "RENDER_API_SERVICE_ID",
    "RENDER_WORKER_SERVICE_ID",
    "OASIS_PUBLIC_TESTER_A_EMAIL",
    "OASIS_PUBLIC_TESTER_A_PASSWORD",
    "OASIS_PUBLIC_TESTER_A_RESET_PASSWORD",
    "OASIS_PUBLIC_TESTER_B_EMAIL",
    "OASIS_PUBLIC_TESTER_B_PASSWORD",
    "OASIS_PUBLIC_LIFECYCLE_EMAIL",
    "OASIS_PUBLIC_LIFECYCLE_PASSWORD",
    "OASIS_PUBLIC_LIFECYCLE_CHANGED_PASSWORD",
]

GITHUB_ACTIONS_ENV_REQUIRED = [
    "STAGING_URL",
    "RENDER_API_KEY",
    "RENDER_API_SERVICE_ID",
    "RENDER_WORKER_SERVICE_ID",
    "OASIS_CF_ACCESS_CLIENT_ID",
    "OASIS_CF_ACCESS_CLIENT_SECRET",
]

GITHUB_STAGING_SECRETS = [
    "RENDER_API_KEY",
    "RENDER_API_SERVICE_ID",
    "RENDER_WORKER_SERVICE_ID",
    "OASIS_CF_ACCESS_CLIENT_ID",
    "OASIS_CF_ACCESS_CLIENT_SECRET",
]

GITHUB_STAGING_VARIABLES = ["STAGING_URL"]
GITHUB_STAGING_BRANCH_POLICIES = ["main"]
LOCAL_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
RESERVED_PUBLIC_HOSTS = {"example.com", "example.net", "example.org"}
RESERVED_PUBLIC_SUFFIXES = (".example.com", ".example.net", ".example.org", ".invalid", ".test")

BROWSER_APPS = {
    "chrome": Path("/Applications/Google Chrome.app"),
    "firefox": Path("/Applications/Firefox.app"),
    "safari": Path("/Applications/Safari.app"),
}


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        return 127, str(exc)
    return result.returncode, (result.stdout + result.stderr).strip()


def list_names(output: str) -> list[str]:
    names: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("---"):
            continue
        names.append(line.split()[0])
    return names


def github_context() -> dict[str, Any]:
    auth_code, auth_output = run(["gh", "auth", "status"])
    env_code, env_output = run(["gh", "api", "repos/:owner/:repo/environments"])
    secret_code, secret_output = run(["gh", "secret", "list", "--env", "staging"])
    var_code, var_output = run(["gh", "variable", "list", "--env", "staging"])
    branch_policy_code, branch_policy_output = run([
        "gh",
        "api",
        "repos/:owner/:repo/environments/staging/deployment-branch-policies",
    ])

    staging: dict[str, Any] = {}
    if env_code == 0:
        try:
            envs = json.loads(env_output)
            staging = next((item for item in envs.get("environments", []) if item.get("name") == "staging"), {})
        except json.JSONDecodeError:
            staging = {}

    secrets = list_names(secret_output) if secret_code == 0 else []
    variables = list_names(var_output) if var_code == 0 else []
    branch_policies: list[str] = []
    if branch_policy_code == 0:
        try:
            branch_payload = json.loads(branch_policy_output)
            branch_policies = sorted(item.get("name", "") for item in branch_payload.get("branch_policies", []) if item.get("name"))
        except json.JSONDecodeError:
            branch_policies = []
    return {
        "gh_authenticated": auth_code == 0,
        "gh_auth_error": None if auth_code == 0 else auth_output[:500],
        "staging_environment_exists": bool(staging),
        "staging_environment_protection_rule_count": len(staging.get("protection_rules") or []),
        "staging_environment_can_admins_bypass": staging.get("can_admins_bypass"),
        "staging_environment_deployment_branch_policy": staging.get("deployment_branch_policy"),
        "staging_secret_names_configured": secrets,
        "staging_variable_names_configured": variables,
        "staging_branch_policies_configured": branch_policies,
        "required_staging_secrets_missing": [name for name in GITHUB_STAGING_SECRETS if name not in secrets],
        "required_staging_vars_missing": [name for name in GITHUB_STAGING_VARIABLES if name not in variables],
        "required_staging_branch_policies_missing": [name for name in GITHUB_STAGING_BRANCH_POLICIES if name not in branch_policies],
    }


def env_presence(env: Mapping[str, str | None], required: list[str]) -> dict[str, str]:
    return {name: "set" if env.get(name) else "missing" for name in required}


def staging_url_metadata(value: str | None) -> dict[str, Any]:
    parsed = urlparse(str(value or ""))
    hostname = (parsed.hostname or "").lower()
    is_local = hostname in LOCAL_PUBLIC_HOSTS or hostname.endswith(".local")
    is_reserved = hostname in RESERVED_PUBLIC_HOSTS or hostname.endswith(RESERVED_PUBLIC_SUFFIXES)
    return {
        "present": bool(value),
        "https": parsed.scheme == "https",
        "hostname_present": bool(hostname),
        "non_local_hostname": bool(hostname) and not is_local,
        "reserved_documentation_hostname": is_reserved,
        "public_https": bool(value) and parsed.scheme == "https" and bool(hostname) and not is_local and not is_reserved,
    }


def staging_url_blockers(metadata: Mapping[str, Any], env_label: str) -> list[str]:
    if not metadata.get("present"):
        return []
    blockers: list[str] = []
    if metadata.get("https") is not True:
        blockers.append(f"{env_label} STAGING_URL is not HTTPS")
    if metadata.get("hostname_present") is not True:
        blockers.append(f"{env_label} STAGING_URL hostname is missing")
    if metadata.get("non_local_hostname") is not True:
        blockers.append(f"{env_label} STAGING_URL is not a non-local public hostname")
    if metadata.get("reserved_documentation_hostname") is True:
        blockers.append(f"{env_label} STAGING_URL is a reserved documentation hostname")
    return blockers


def browser_presence(paths: Mapping[str, Path] = BROWSER_APPS) -> dict[str, bool]:
    return {name: path.exists() for name, path in paths.items()}


def build_payload(
    *,
    env: Mapping[str, str | None],
    github: Mapping[str, Any],
    browsers: Mapping[str, bool],
    branch: str,
    commit: str,
    captured_at: str | None = None,
    required_env_names: list[str] | None = None,
    require_github_provider_metadata: bool = True,
    require_browsers: bool = True,
    env_label: str = "local environment variables",
    config_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    local = env_presence(env, required_env_names or LOCAL_ENV_REQUIRED)
    staging_url = staging_url_metadata(env.get("STAGING_URL"))
    contract = dict(config_contract or {"verdict": "pass", "failures": []})
    blockers: list[str] = []

    missing_local = [name for name, state in local.items() if state == "missing"]
    if missing_local:
        blockers.append(f"{env_label} missing: " + ", ".join(missing_local))
    blockers.extend(staging_url_blockers(staging_url, env_label))
    if require_github_provider_metadata:
        if not github.get("gh_authenticated"):
            blockers.append("GitHub CLI is not authenticated")
        if not github.get("staging_environment_exists"):
            blockers.append("GitHub staging environment is missing")
        if int(github.get("staging_environment_protection_rule_count") or 0) < 1:
            blockers.append("GitHub staging environment has no protection rules")
        branch_policy = github.get("staging_environment_deployment_branch_policy") or {}
        if not branch_policy.get("custom_branch_policies"):
            blockers.append("GitHub staging environment does not require custom branch policies")
        missing_branch_policies = list(github.get("required_staging_branch_policies_missing") or [])
        if missing_branch_policies:
            blockers.append("GitHub staging branch policies missing: " + ", ".join(missing_branch_policies))
        missing_secrets = list(github.get("required_staging_secrets_missing") or [])
        if missing_secrets:
            blockers.append("GitHub staging secrets missing: " + ", ".join(missing_secrets))
        missing_vars = list(github.get("required_staging_vars_missing") or [])
        if missing_vars:
            blockers.append("GitHub staging variables missing: " + ", ".join(missing_vars))
    if require_browsers:
        missing_browsers = [name for name, present in browsers.items() if not present]
        if missing_browsers:
            blockers.append("manual browser matrix apps missing: " + ", ".join(sorted(missing_browsers)))
    if contract.get("verdict") != "pass":
        failures = ", ".join(str(item) for item in contract.get("failures") or []) or "unknown failure"
        blockers.append("public staging config contract failed: " + failures)

    return {
        "captured_at": captured_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "branch": branch,
        "commit": commit,
        "verdict": "ready" if not blockers else "not_ready",
        "not_public_staging_proof": True,
        "local_environment": local,
        "staging_url": staging_url,
        "github": dict(github),
        "public_staging_config_contract": contract,
        "local_browser_availability": dict(browsers),
        "blocking_external_inputs": blockers,
        "safe_next_commands_after_ready": [
            "python3 scripts/public_staging_config_contract.py",
            "gh workflow run Deploy --ref main -f target=staging",
            "python3 scripts/public_staging_preflight.py --base-url=\"$STAGING_URL\" --header CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID --header CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET",
            "python3 scripts/public_staging_gate_audit.py",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(EVIDENCE / "public-staging-readiness-status.json"))
    parser.add_argument("--allow-not-ready", action="store_true", help="write evidence and exit 0 even when prerequisites are missing")
    parser.add_argument(
        "--mode",
        choices=["local", "github-actions"],
        default="local",
        help="local checks operator/provider readiness; github-actions checks env injected into the deploy job",
    )
    args = parser.parse_args()
    github = github_context() if args.mode == "local" else {"context": "github-actions-env-only"}
    browsers = browser_presence() if args.mode == "local" else {}
    required_env = LOCAL_ENV_REQUIRED if args.mode == "local" else GITHUB_ACTIONS_ENV_REQUIRED
    contract = build_config_contract()

    payload = build_payload(
        env=os.environ,
        github=github,
        browsers=browsers,
        branch=git_value("branch", "--show-current"),
        commit=git_value("rev-parse", "HEAD"),
        required_env_names=required_env,
        require_github_provider_metadata=args.mode == "local",
        require_browsers=args.mode == "local",
        env_label="local environment variables" if args.mode == "local" else "GitHub Actions deployment environment variables",
        config_contract=contract,
    )
    payload["mode"] = args.mode

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging readiness to {output}")
    print(json.dumps({"verdict": payload["verdict"], "blocking_external_inputs": payload["blocking_external_inputs"]}, indent=2))
    return 0 if args.allow_not_ready or payload["verdict"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
