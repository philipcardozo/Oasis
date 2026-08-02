#!/usr/bin/env python3
"""Run or plan the full public-staging verification sequence."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
PERF_EVIDENCE = ROOT / "docs" / "evidence" / "performance"
DEFAULT_JSON = PUBLIC_EVIDENCE / "public-staging-full-verification-run.json"
DEFAULT_MD = PUBLIC_EVIDENCE / "public-staging-full-verification-plan.md"
LOCAL_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
RESERVED_PUBLIC_HOSTS = {"example.com", "example.net", "example.org"}
RESERVED_PUBLIC_SUFFIXES = (".example.com", ".example.net", ".example.org", ".invalid", ".test")

ACCESS_HEADERS = [
    "CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID",
    "CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET",
]


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    command: list[str]
    produces: list[str]
    requires: list[str]
    manual_input: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def header_args() -> list[str]:
    return [f"--header={item}" for item in ACCESS_HEADERS]


def public_base_url_failures(url: str, *, allow_placeholder: bool = False) -> list[str]:
    if allow_placeholder and "<approved-domain>" in url:
        return []
    parsed = urlparse(url)
    failures: list[str] = []
    if parsed.scheme != "https":
        failures.append("base URL must use https")
    if not parsed.hostname:
        failures.append("base URL must include a hostname")
    hostname = (parsed.hostname or "").lower()
    if hostname in LOCAL_PUBLIC_HOSTS or hostname.endswith(".local"):
        failures.append("base URL must be a non-local public hostname")
    if hostname in RESERVED_PUBLIC_HOSTS or hostname.endswith(RESERVED_PUBLIC_SUFFIXES):
        failures.append("base URL must not be a reserved documentation hostname")
    return failures


def command_line(command: list[str]) -> str:
    return shlex.join(command)


def redact_text(value: str) -> str:
    redacted = value
    for env_name in (
        "OASIS_CF_ACCESS_CLIENT_SECRET",
        "OASIS_PUBLIC_TESTER_A_PASSWORD",
        "OASIS_PUBLIC_TESTER_A_RESET_PASSWORD",
        "OASIS_PUBLIC_TESTER_B_PASSWORD",
        "OASIS_PUBLIC_LIFECYCLE_PASSWORD",
        "OASIS_PUBLIC_LIFECYCLE_CHANGED_PASSWORD",
    ):
        secret_value = os.environ.get(env_name)
        if secret_value:
            redacted = redacted.replace(secret_value, "<redacted>")
    return redacted


def build_steps(*, base_url: str, proxy_server: str, expect_commit: str, samples: int) -> list[Step]:
    preflight = [
        "python3",
        "scripts/public_staging_preflight.py",
        f"--base-url={base_url}",
        *header_args(),
    ]
    if expect_commit:
        preflight.append(f"--expect-commit={expect_commit}")

    route_probe = [
        "python3",
        "scripts/compose_route_family_probe.py",
        f"--base-url={base_url}",
        f"--samples={samples}",
        "--output-file=25-public-route-family-probe.json",
        "--verify-tls",
        *header_args(),
    ]
    if proxy_server:
        route_probe.append(f"--proxy-server={proxy_server}")

    auth_probe = [
        "python3",
        "scripts/public_staging_auth_map_slots_probe.py",
        f"--base-url={base_url}",
        f"--samples={samples}",
        "--enforce-app-targets",
        f"--output={PERF_EVIDENCE / '27-public-auth-map-slots.json'}",
        *header_args(),
    ]
    if proxy_server:
        auth_probe.append(f"--proxy-server={proxy_server}")

    proxyman_capture = [
        "node",
        "scripts/browser_performance_capture.js",
        f"--base-url={base_url}",
        "--no-start-server=true",
        f"--proxy-server={proxy_server}",
        "--flow-prefix=26-public-staging",
        "--summary-file=26-public-staging-browser-har-summary.json",
    ]

    direct_capture = [
        "node",
        "scripts/browser_performance_capture.js",
        f"--base-url={base_url}",
        "--no-start-server=true",
        "--flow-prefix=26-public-staging-direct",
        "--summary-file=26-public-staging-direct-browser-har-summary.json",
    ]

    return [
        Step(
            "setup_checklist",
            "Generate secret-free setup checklist",
            ["python3", "scripts/public_staging_setup_checklist.py"],
            [
                "docs/evidence/public-staging/public-staging-setup-checklist.md",
                "docs/evidence/public-staging/public-staging-setup-checklist.json",
            ],
            [],
        ),
        Step(
            "browser_matrix_template",
            "Generate manual browser matrix template",
            ["python3", "scripts/public_staging_browser_matrix_template.py", f"--base-url={base_url}"],
            [
                "docs/evidence/public-staging/browser-matrix.template.json",
                "docs/evidence/public-staging/browser-matrix-template.md",
            ],
            [],
            manual_input=True,
        ),
        Step(
            "config_contract",
            "Validate Render and Compose production-style staging value contract",
            ["python3", "scripts/public_staging_config_contract.py"],
            ["docs/evidence/public-staging/public-staging-config-contract.json"],
            ["render.yaml", "compose.yaml"],
        ),
        Step(
            "readiness",
            "Verify external staging prerequisites are present",
            ["python3", "scripts/public_staging_readiness.py"],
            ["docs/evidence/public-staging/public-staging-readiness-status.json"],
            ["GitHub staging env vars/secrets", "Render service IDs", "Cloudflare/Access credentials", "tester emails"],
        ),
        Step(
            "preflight",
            "Check public DNS, TLS, headers, health, readiness, version",
            preflight,
            ["docs/evidence/public-staging/00-public-staging-preflight.json"],
            ["STAGING_URL", "Cloudflare Access service-token env vars"],
        ),
        Step(
            "route_family_probe",
            "Probe public route families through the staging edge",
            route_probe,
            ["docs/evidence/performance/25-public-route-family-probe.json"],
            ["public URL reachable", "Cloudflare Access service-token env vars"],
        ),
        Step(
            "auth_map_slots_probe",
            "Exercise registration, verification, login, cookies, slots, CSRF, stale 409, cross-user denial, reset",
            auth_probe,
            ["docs/evidence/performance/27-public-auth-map-slots.json"],
            ["tester emails/passwords and verification/reset tokens in local env"],
        ),
        Step(
            "auth_email_report",
            "Generate authentication/email evidence report",
            [
                "python3",
                "scripts/public_staging_auth_email_report.py",
                f"--auth-map-slots={PERF_EVIDENCE / '27-public-auth-map-slots.json'}",
                f"--output={PUBLIC_EVIDENCE / '06-auth-email.md'}",
                f"--summary-output={PUBLIC_EVIDENCE / 'auth-email-summary.json'}",
            ],
            ["docs/evidence/public-staging/06-auth-email.md", "docs/evidence/public-staging/auth-email-summary.json"],
            ["docs/evidence/performance/27-public-auth-map-slots.json"],
        ),
        Step(
            "route_security_report",
            "Generate route security and security-header report",
            [
                "python3",
                "scripts/public_staging_route_security_report.py",
                f"--route-probe={PERF_EVIDENCE / '25-public-route-family-probe.json'}",
                f"--preflight={PUBLIC_EVIDENCE / '00-public-staging-preflight.json'}",
                f"--auth-security={PERF_EVIDENCE / '27-public-auth-map-slots.json'}",
                f"--output={PUBLIC_EVIDENCE / '09-route-security.md'}",
                f"--summary-output={PUBLIC_EVIDENCE / 'route-security-summary.json'}",
            ],
            ["docs/evidence/public-staging/09-route-security.md", "docs/evidence/public-staging/route-security-summary.json"],
            [
                "docs/evidence/performance/25-public-route-family-probe.json",
                "docs/evidence/public-staging/00-public-staging-preflight.json",
                "docs/evidence/performance/27-public-auth-map-slots.json",
            ],
        ),
        Step(
            "public_playwright",
            "Run Playwright tests against the public staging URL with Chromium, Firefox, and WebKit",
            [
                "python3",
                "scripts/public_staging_playwright_report.py",
                f"--base-url={base_url}",
                f"--output={PUBLIC_EVIDENCE / 'public-playwright-summary.json'}",
                f"--markdown-output={PUBLIC_EVIDENCE / '22-public-playwright.md'}",
            ],
            [
                "docs/evidence/public-staging/public-playwright-summary.json",
                "docs/evidence/public-staging/22-public-playwright.md",
            ],
            ["public URL reachable", "Cloudflare Access service-token env vars"],
        ),
        Step(
            "proxyman_browser_capture",
            "Capture Chrome public flows through Proxyman",
            proxyman_capture,
            ["docs/evidence/performance/26-public-staging-browser-har-summary.json"],
            ["Proxyman running", "SSL proxying enabled for staging and map hosts", "browser can pass Access"],
        ),
        Step(
            "direct_browser_capture",
            "Capture direct Chrome comparison without Proxyman",
            direct_capture,
            ["docs/evidence/performance/26-public-staging-direct-browser-har-summary.json"],
            ["public URL reachable without local proxy"],
        ),
        Step(
            "browser_reports",
            "Generate browser matrix and map-provider reports",
            [
                "python3",
                "scripts/public_staging_browser_reports.py",
                f"--browser-matrix={PUBLIC_EVIDENCE / 'browser-matrix.json'}",
                f"--browser-summary={PERF_EVIDENCE / '26-public-staging-browser-har-summary.json'}",
                f"--browser-output={PUBLIC_EVIDENCE / '07-browser-matrix.md'}",
                f"--map-output={PUBLIC_EVIDENCE / '08-map-provider-capture.md'}",
                f"--summary-output={PUBLIC_EVIDENCE / 'browser-map-summary.json'}",
            ],
            [
                "docs/evidence/public-staging/07-browser-matrix.md",
                "docs/evidence/public-staging/08-map-provider-capture.md",
                "docs/evidence/public-staging/browser-map-summary.json",
            ],
            [
                "filled docs/evidence/public-staging/browser-matrix.json",
                "docs/evidence/performance/26-public-staging-browser-har-summary.json",
            ],
            manual_input=True,
        ),
        Step(
            "performance_report",
            "Generate public performance evidence report",
            [
                "python3",
                "scripts/public_staging_performance_report.py",
                f"--browser-summary={PERF_EVIDENCE / '26-public-staging-browser-har-summary.json'}",
                f"--direct-summary={PERF_EVIDENCE / '26-public-staging-direct-browser-har-summary.json'}",
                f"--auth-map-slot={PERF_EVIDENCE / '27-public-auth-map-slots.json'}",
                f"--route-probe={PERF_EVIDENCE / '25-public-route-family-probe.json'}",
                f"--supplemental={PUBLIC_EVIDENCE / 'performance-supplemental.json'}",
                f"--output={PUBLIC_EVIDENCE / '15-performance.md'}",
                f"--summary-output={PUBLIC_EVIDENCE / 'performance-evidence-summary.json'}",
            ],
            ["docs/evidence/public-staging/15-performance.md", "docs/evidence/public-staging/performance-evidence-summary.json"],
            ["filled performance-supplemental.json", "Proxyman and direct HAR summaries"],
            manual_input=True,
        ),
        Step(
            "infra_reports",
            "Generate DNS/TLS/Access/Render/migration reports",
            [
                "python3",
                "scripts/public_staging_infra_reports.py",
                f"--input={PUBLIC_EVIDENCE / 'infra-evidence.json'}",
                f"--preflight={PUBLIC_EVIDENCE / '00-public-staging-preflight.json'}",
                f"--render-deploy={PUBLIC_EVIDENCE / '02-render-deploy.json'}",
                f"--image-manifest={PUBLIC_EVIDENCE / '01-image-manifest.json'}",
                f"--output-dir={PUBLIC_EVIDENCE}",
                f"--summary-output={PUBLIC_EVIDENCE / 'infra-evidence-summary.json'}",
            ],
            [
                "docs/evidence/public-staging/02-dns-tls-edge.md",
                "docs/evidence/public-staging/03-cloudflare-access.md",
                "docs/evidence/public-staging/04-render-services.md",
                "docs/evidence/public-staging/05-migration-version.md",
                "docs/evidence/public-staging/infra-evidence-summary.json",
            ],
            ["filled infra-evidence.json", "Render deploy and image manifest evidence"],
            manual_input=True,
        ),
        Step(
            "ops_reports",
            "Generate backup/restore, rollback, worker, and observability reports",
            [
                "python3",
                "scripts/public_staging_ops_reports.py",
                f"--input={PUBLIC_EVIDENCE / 'ops-evidence.json'}",
                f"--output-dir={PUBLIC_EVIDENCE}",
                f"--summary-output={PUBLIC_EVIDENCE / 'ops-evidence-summary.json'}",
            ],
            [
                "docs/evidence/public-staging/10-worker-jobs.md",
                "docs/evidence/public-staging/12-backup-restore.md",
                "docs/evidence/public-staging/13-failure-rollback.md",
                "docs/evidence/public-staging/14-observability-alerts.md",
                "docs/evidence/public-staging/ops-evidence-summary.json",
            ],
            ["filled ops-evidence.json from provider drills"],
            manual_input=True,
        ),
        Step(
            "email_delivery_report",
            "Generate transactional email delivery report",
            [
                "python3",
                "scripts/public_staging_email_delivery_report.py",
                f"--input={PUBLIC_EVIDENCE / 'email-delivery-evidence.json'}",
                f"--auth-email-summary={PUBLIC_EVIDENCE / 'auth-email-summary.json'}",
                f"--infra-summary={PUBLIC_EVIDENCE / 'infra-evidence-summary.json'}",
                f"--ops-summary={PUBLIC_EVIDENCE / 'ops-evidence-summary.json'}",
                f"--output={PUBLIC_EVIDENCE / '20-email-delivery.md'}",
                f"--summary-output={PUBLIC_EVIDENCE / 'email-delivery-summary.json'}",
            ],
            ["docs/evidence/public-staging/20-email-delivery.md", "docs/evidence/public-staging/email-delivery-summary.json"],
            ["filled email-delivery-evidence.json"],
            manual_input=True,
        ),
        Step(
            "rate_limit_report",
            "Generate public proxy/rate-limit report",
            [
                "python3",
                "scripts/public_staging_rate_limit_report.py",
                f"--input={PUBLIC_EVIDENCE / 'rate-limit-evidence.json'}",
                f"--route-security={PUBLIC_EVIDENCE / 'route-security-summary.json'}",
                f"--preflight={PUBLIC_EVIDENCE / '00-public-staging-preflight.json'}",
                f"--output={PUBLIC_EVIDENCE / '18-rate-limiting.md'}",
                f"--summary-output={PUBLIC_EVIDENCE / 'rate-limit-summary.json'}",
            ],
            ["docs/evidence/public-staging/18-rate-limiting.md", "docs/evidence/public-staging/rate-limit-summary.json"],
            ["filled rate-limit-evidence.json"],
            manual_input=True,
        ),
        Step(
            "storage_report",
            "Generate object-storage report",
            [
                "python3",
                "scripts/public_staging_storage_report.py",
                f"--input={PUBLIC_EVIDENCE / 'storage-evidence.json'}",
                f"--infra-summary={PUBLIC_EVIDENCE / 'infra-evidence-summary.json'}",
                f"--ops-summary={PUBLIC_EVIDENCE / 'ops-evidence-summary.json'}",
                f"--output={PUBLIC_EVIDENCE / '19-object-storage.md'}",
                f"--summary-output={PUBLIC_EVIDENCE / 'storage-summary.json'}",
            ],
            ["docs/evidence/public-staging/19-object-storage.md", "docs/evidence/public-staging/storage-summary.json"],
            ["filled storage-evidence.json"],
            manual_input=True,
        ),
        Step(
            "licensing_report",
            "Generate licensing report",
            [
                "python3",
                "scripts/public_staging_licensing_report.py",
                f"--input={PUBLIC_EVIDENCE / 'licensing-evidence.json'}",
                f"--browser-map-summary={PUBLIC_EVIDENCE / 'browser-map-summary.json'}",
                f"--output={PUBLIC_EVIDENCE / '17-licensing-gates.md'}",
                f"--summary-output={PUBLIC_EVIDENCE / 'licensing-summary.json'}",
            ],
            ["docs/evidence/public-staging/17-licensing-gates.md", "docs/evidence/public-staging/licensing-summary.json"],
            ["filled licensing-evidence.json", "browser-map-summary.json"],
            manual_input=True,
        ),
        Step(
            "failure_exercises_report",
            "Generate failure-exercise report",
            [
                "python3",
                "scripts/public_staging_failure_exercises_report.py",
                f"--input={PUBLIC_EVIDENCE / 'failure-exercises-evidence.json'}",
                f"--ops-summary={PUBLIC_EVIDENCE / 'ops-evidence-summary.json'}",
                f"--browser-map-summary={PUBLIC_EVIDENCE / 'browser-map-summary.json'}",
                f"--storage-summary={PUBLIC_EVIDENCE / 'storage-summary.json'}",
                f"--email-delivery-summary={PUBLIC_EVIDENCE / 'email-delivery-summary.json'}",
                f"--output={PUBLIC_EVIDENCE / '21-failure-exercises.md'}",
                f"--summary-output={PUBLIC_EVIDENCE / 'failure-exercises-summary.json'}",
            ],
            ["docs/evidence/public-staging/21-failure-exercises.md", "docs/evidence/public-staging/failure-exercises-summary.json"],
            ["filled failure-exercises-evidence.json"],
            manual_input=True,
        ),
    ]


def run_step(step: Step) -> dict[str, Any]:
    result = subprocess.run(step.command, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "key": step.key,
        "label": step.label,
        "command": command_line(step.command),
        "returncode": result.returncode,
        "stdout_tail": redact_text(result.stdout[-2000:]),
        "stderr_tail": redact_text(result.stderr[-2000:]),
    }


def step_payload(step: Step) -> dict[str, Any]:
    return {
        "key": step.key,
        "label": step.label,
        "command": command_line(step.command),
        "produces": step.produces,
        "requires": step.requires,
        "manual_input": step.manual_input,
    }


def build_payload(*, args: argparse.Namespace, steps: list[Step], results: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [item for item in results if item.get("returncode") not in {0, None}]
    dry_run = bool(args.dry_run)
    return {
        "captured_at": utc_now(),
        "branch": git_value("branch", "--show-current"),
        "commit": git_value("rev-parse", "HEAD"),
        "base_url": args.base_url,
        "proxy_server": args.proxy_server,
        "samples": args.samples,
        "dry_run": dry_run,
        "not_public_staging_proof": dry_run,
        "steps": [step_payload(step) for step in steps],
        "results": results,
        "failures": failures,
        "verdict": "planned" if dry_run else ("pass" if not failures else "investigate"),
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Full Verification Plan",
        "",
        f"Captured: {payload['captured_at']}",
        f"Branch: `{payload['branch']}`",
        f"Commit: `{payload['commit']}`",
        f"Base URL: `{payload['base_url']}`",
        f"Proxyman proxy: `{payload['proxy_server']}`",
        f"Verdict: **{payload['verdict']}**",
        "",
        "This file is an execution plan/run log. It is not approval proof unless the final gate audit is approved.",
        "",
        "## Steps",
        "",
    ]
    for index, step in enumerate(payload["steps"], start=1):
        lines.extend([
            f"### {index}. {step['label']}",
            "",
            f"- Key: `{step['key']}`",
            f"- Manual input required: `{step['manual_input']}`",
            f"- Requires: `{', '.join(step['requires']) or '-'}`",
            f"- Produces: `{', '.join(step['produces']) or '-'}`",
            "",
            "```bash",
            step["command"],
            "```",
            "",
        ])
    if payload["results"]:
        lines.extend(["## Results", ""])
        for result in payload["results"]:
            lines.append(f"- `{result['key']}` returncode `{result['returncode']}`")
        lines.append("")
    if payload["failures"]:
        lines.extend(["## Failures", ""])
        for failure in payload["failures"]:
            lines.append(f"- `{failure['key']}` returncode `{failure['returncode']}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("STAGING_URL", ""))
    parser.add_argument("--proxy-server", default=os.environ.get("OASIS_PUBLIC_PROXYMAN_PROXY", "http://127.0.0.1:9090"))
    parser.add_argument("--expect-commit", default="")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_JSON))
    parser.add_argument("--markdown-output", default=str(DEFAULT_MD))
    args = parser.parse_args()

    if not args.base_url:
        if args.dry_run:
            args.base_url = "https://staging.<approved-domain>"
        else:
            raise SystemExit("provide --base-url or STAGING_URL")
    target_failures = public_base_url_failures(args.base_url.rstrip("/"), allow_placeholder=args.dry_run)
    if target_failures:
        raise SystemExit("; ".join(target_failures))

    steps = build_steps(
        base_url=args.base_url.rstrip("/"),
        proxy_server=args.proxy_server,
        expect_commit=args.expect_commit,
        samples=max(1, args.samples),
    )
    results: list[dict[str, Any]] = []
    if not args.dry_run:
        for step in steps:
            result = run_step(step)
            results.append(result)
            if result["returncode"] != 0 and not args.continue_on_error:
                break

    payload = build_payload(args=args, steps=steps, results=results)
    output = Path(args.output)
    markdown_output = Path(args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown_output.write_text(markdown(payload))

    print(f"Wrote public staging full verification JSON to {output}")
    print(f"Wrote public staging full verification plan to {markdown_output}")
    print(json.dumps({"verdict": payload["verdict"], "failure_count": len(payload["failures"])}, indent=2))
    return 0 if payload["verdict"] in {"pass", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
