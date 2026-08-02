#!/usr/bin/env python3
"""Run public-staging Playwright tests and write sanitized evidence."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
DEFAULT_JSON = PUBLIC_EVIDENCE / "public-playwright-summary.json"
DEFAULT_MD = PUBLIC_EVIDENCE / "22-public-playwright.md"
REQUIRED_PROJECTS = {"chromium", "firefox", "webkit"}
LOCAL_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
RESERVED_PUBLIC_HOSTS = {"example.com", "example.net", "example.org"}
RESERVED_PUBLIC_SUFFIXES = (".example.com", ".example.net", ".example.org", ".invalid", ".test")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def safe_base_url(value: str) -> str:
    return value.rstrip("/")


def public_base_url_failures(value: str, *, allow_placeholder: bool = False) -> list[str]:
    if allow_placeholder and "<approved-domain>" in value:
        return []
    parsed = urlparse(value)
    failures: list[str] = []
    if parsed.scheme != "https":
        failures.append("Playwright base URL is not HTTPS")
    if not parsed.hostname:
        failures.append("Playwright base URL is missing a hostname")
    hostname = (parsed.hostname or "").lower()
    if hostname in LOCAL_PUBLIC_HOSTS or hostname.endswith(".local"):
        failures.append("Playwright base URL is local")
    if hostname in RESERVED_PUBLIC_HOSTS or hostname.endswith(RESERVED_PUBLIC_SUFFIXES):
        failures.append("Playwright base URL is a reserved documentation hostname")
    return failures


def redacted_env() -> dict[str, str]:
    names = ["STAGING_URL", "OASIS_PUBLIC_PLAYWRIGHT_BASE_URL"]
    access_names = []
    if os.environ.get("OASIS_CF_ACCESS_CLIENT_ID"):
        access_names.append("CF-Access-Client-Id")
    if os.environ.get("OASIS_CF_ACCESS_CLIENT_SECRET"):
        access_names.append("CF-Access-Client-Secret")
    return {
        "url_env_names_checked": names,
        "auth_header_names_sent": access_names,
    }


def collect_specs(suites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for suite in suites:
        for spec in suite.get("specs") or []:
            specs.append(spec)
        specs.extend(collect_specs(suite.get("suites") or []))
    return specs


def summarize_report(report: dict[str, Any]) -> dict[str, Any]:
    stats = report.get("stats") or {}
    specs = collect_specs(report.get("suites") or [])
    projects = set()
    failed: list[dict[str, str]] = []
    total_tests = 0
    for spec in specs:
        for test in spec.get("tests") or []:
            total_tests += 1
            project = str(test.get("projectName") or "")
            if project:
                projects.add(project)
            status = str(test.get("status") or "")
            if status not in {"expected", "skipped"}:
                failed.append({
                    "project": project,
                    "title": str(spec.get("title") or test.get("title") or "unknown"),
                    "status": status or "unknown",
                })
    return {
        "stats": {
            "expected": int(stats.get("expected") or 0),
            "unexpected": int(stats.get("unexpected") or 0),
            "flaky": int(stats.get("flaky") or 0),
            "skipped": int(stats.get("skipped") or 0),
        },
        "project_names": sorted(projects),
        "missing_projects": sorted(REQUIRED_PROJECTS - projects),
        "test_count": total_tests,
        "failed_tests": failed,
    }


def evaluate(*, base_url: str, returncode: int | None, summary: dict[str, Any], parse_error: str = "", dry_run: bool = False) -> tuple[str, list[str]]:
    failures: list[str] = []
    if dry_run:
        return "planned", failures
    failures.extend(public_base_url_failures(base_url))
    if parse_error:
        failures.append("Playwright JSON report could not be parsed")
    if returncode not in {0, None}:
        failures.append(f"Playwright command returned {returncode}")
    stats = summary.get("stats") or {}
    if int(stats.get("expected") or 0) <= 0:
        failures.append("Playwright expected pass count is zero")
    if int(stats.get("unexpected") or 0) != 0:
        failures.append("Playwright unexpected failures are non-zero")
    if int(stats.get("flaky") or 0) != 0:
        failures.append("Playwright flaky count is non-zero")
    for project in summary.get("missing_projects") or []:
        failures.append(f"Playwright project is missing: {project}")
    if summary.get("failed_tests"):
        failures.append("Playwright failed tests are present")
    return ("pass" if not failures else "investigate"), failures


def build_command(base_url: str, config: str) -> list[str]:
    return ["npx", "playwright", "test", f"--config={config}", "--reporter=json"]


def run_playwright(command: list[str], base_url: str) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["OASIS_PUBLIC_PLAYWRIGHT_BASE_URL"] = base_url
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    return result.returncode, result.stdout, result.stderr


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    base_url = safe_base_url(args.base_url or os.environ.get("STAGING_URL", ""))
    if not base_url and not args.dry_run:
        raise SystemExit("provide --base-url, STAGING_URL, or --dry-run")
    if not base_url:
        base_url = "https://staging.<approved-domain>"
    target_failures = public_base_url_failures(base_url, allow_placeholder=args.dry_run)
    if target_failures:
        raise SystemExit("; ".join(target_failures))

    command = build_command(base_url, args.config)
    returncode: int | None = None
    stdout = ""
    stderr = ""
    parse_error = ""
    report: dict[str, Any] = {}
    if args.dry_run:
        summary = {"stats": {}, "project_names": [], "missing_projects": sorted(REQUIRED_PROJECTS), "test_count": 0, "failed_tests": []}
    else:
        if args.input_report:
            stdout = Path(args.input_report).read_text()
            returncode = 0
        else:
            returncode, stdout, stderr = run_playwright(command, base_url)
        try:
            report = json.loads(stdout)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
        summary = summarize_report(report) if report else {"stats": {}, "project_names": [], "missing_projects": sorted(REQUIRED_PROJECTS), "test_count": 0, "failed_tests": []}

    verdict, failures = evaluate(
        base_url=base_url,
        returncode=returncode,
        summary=summary,
        parse_error=parse_error,
        dry_run=args.dry_run,
    )
    return {
        "captured_at": utc_now(),
        "branch": git_value("branch", "--show-current"),
        "commit": git_value("rev-parse", "HEAD"),
        "base_url": base_url,
        "config": args.config,
        "command": " ".join(command),
        "dry_run": bool(args.dry_run),
        "not_public_staging_proof": bool(args.dry_run),
        **redacted_env(),
        "returncode": returncode,
        "stderr_tail": stderr[-2000:],
        "parse_error": parse_error,
        "summary": summary,
        "failures": failures,
        "verdict": verdict,
    }


def markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    stats = summary.get("stats") or {}
    lines = [
        "# Public Staging Playwright Evidence",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Base URL: `{payload['base_url']}`",
        f"Config: `{payload['config']}`",
        f"Verdict: **{payload['verdict']}**",
        "",
        "## Test Summary",
        "",
        f"- Expected: `{stats.get('expected', 0)}`",
        f"- Unexpected: `{stats.get('unexpected', 0)}`",
        f"- Flaky: `{stats.get('flaky', 0)}`",
        f"- Skipped: `{stats.get('skipped', 0)}`",
        f"- Total tests observed: `{summary.get('test_count', 0)}`",
        f"- Projects: `{', '.join(summary.get('project_names') or []) or 'none'}`",
        f"- Auth header names sent: `{', '.join(payload.get('auth_header_names_sent') or []) or 'none'}`",
        "",
        "## Failed Tests",
        "",
    ]
    failed = summary.get("failed_tests") or []
    if failed:
        lines.extend(f"- `{item['project']}` {item['title']} ({item['status']})" for item in failed)
    else:
        lines.append("- none")
    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in payload["failures"])
    lines.append("")
    lines.append("This generated report contains no cookies, tokens, authorization values, or Cloudflare Access secret values.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("STAGING_URL", ""))
    parser.add_argument("--config", default="playwright.public.config.js")
    parser.add_argument("--input-report", default="", help="parse an existing Playwright JSON reporter output instead of running tests")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_JSON))
    parser.add_argument("--markdown-output", default=str(DEFAULT_MD))
    args = parser.parse_args()

    payload = build_payload(args)
    output = Path(args.output)
    markdown_output = Path(args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown_output.write_text(markdown(payload))
    print(f"Wrote public staging Playwright summary to {output}")
    print(f"Wrote public staging Playwright report to {markdown_output}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"]}, indent=2))
    return 0 if payload["verdict"] in {"pass", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
