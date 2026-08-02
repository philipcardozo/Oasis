"""Public-staging Playwright evidence regressions."""
from __future__ import annotations

import json
import subprocess
import sys

from scripts.public_staging_playwright_report import evaluate, public_base_url_failures, summarize_report

PUBLIC_BASE_URL = "https://staging.oasis-private-beta.com"


def _report(projects: list[str] | None = None, unexpected: int = 0) -> dict:
    projects = projects or ["chromium", "firefox", "webkit"]
    return {
        "stats": {"expected": len(projects), "unexpected": unexpected, "flaky": 0, "skipped": 0},
        "suites": [
            {
                "title": "smoke.spec.js",
                "specs": [
                    {
                        "title": "app boots",
                        "tests": [
                            {
                                "projectName": project,
                                "status": "expected" if unexpected == 0 else "unexpected",
                                "results": [{"status": "passed" if unexpected == 0 else "failed"}],
                            }
                            for project in projects
                        ],
                    }
                ],
            }
        ],
    }


def test_playwright_report_passes_complete_public_json():
    summary = summarize_report(_report())
    verdict, failures = evaluate(
        base_url=PUBLIC_BASE_URL,
        returncode=0,
        summary=summary,
    )

    assert verdict == "pass"
    assert failures == []
    assert summary["project_names"] == ["chromium", "firefox", "webkit"]


def test_playwright_report_rejects_missing_browser_project():
    summary = summarize_report(_report(["chromium", "firefox"]))
    verdict, failures = evaluate(
        base_url=PUBLIC_BASE_URL,
        returncode=0,
        summary=summary,
    )

    assert verdict == "investigate"
    assert "Playwright project is missing: webkit" in failures


def test_playwright_report_rejects_local_or_failed_run():
    summary = summarize_report(_report(unexpected=1))
    verdict, failures = evaluate(
        base_url="http://127.0.0.1:8788",
        returncode=1,
        summary=summary,
    )

    assert verdict == "investigate"
    assert "Playwright base URL is not HTTPS" in failures
    assert "Playwright base URL is local" in failures
    assert "Playwright command returned 1" in failures
    assert "Playwright unexpected failures are non-zero" in failures


def test_playwright_report_rejects_non_public_base_url_before_run():
    assert public_base_url_failures(PUBLIC_BASE_URL) == []
    assert "Playwright base URL is not HTTPS" in public_base_url_failures("http://staging.example.com")
    assert "Playwright base URL is local" in public_base_url_failures("https://localhost:8443")
    assert "Playwright base URL is a reserved documentation hostname" in public_base_url_failures("https://staging.example.com")
    assert public_base_url_failures("https://staging.<approved-domain>", allow_placeholder=True) == []


def test_playwright_report_cli_rejects_explicit_local_dry_run_url(tmp_path):
    output = tmp_path / "summary.json"
    markdown = tmp_path / "summary.md"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_playwright_report.py",
            "--base-url=https://127.0.0.1:8443",
            "--dry-run",
            f"--output={output}",
            f"--markdown-output={markdown}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Playwright base URL is local" in result.stderr
    assert not output.exists()
    assert not markdown.exists()


def test_playwright_report_cli_parses_existing_json(tmp_path):
    report = tmp_path / "playwright-report.json"
    output = tmp_path / "summary.json"
    markdown = tmp_path / "summary.md"
    report.write_text(json.dumps(_report()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_playwright_report.py",
            f"--base-url={PUBLIC_BASE_URL}",
            f"--input-report={report}",
            f"--output={output}",
            f"--markdown-output={markdown}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(output.read_text())
    text = output.read_text() + markdown.read_text()
    assert data["verdict"] == "pass"
    assert "Public Staging Playwright Evidence" in text
    assert "Bearer " not in text
    assert "CF-Access-Client-Secret=" not in text


def test_playwright_report_input_report_requires_explicit_base_url(tmp_path):
    report = tmp_path / "playwright-report.json"
    output = tmp_path / "summary.json"
    markdown = tmp_path / "summary.md"
    report.write_text(json.dumps(_report()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_playwright_report.py",
            f"--input-report={report}",
            f"--output={output}",
            f"--markdown-output={markdown}",
        ],
        capture_output=True,
        text=True,
        env={},
    )

    assert result.returncode != 0
    assert "provide --base-url, STAGING_URL, or --dry-run" in result.stderr
    assert not output.exists()
    assert not markdown.exists()


def test_playwright_report_dry_run_is_not_public_proof(tmp_path):
    output = tmp_path / "summary.json"
    markdown = tmp_path / "summary.md"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_playwright_report.py",
            "--dry-run",
            f"--output={output}",
            f"--markdown-output={markdown}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(output.read_text())
    assert data["verdict"] == "planned"
    assert data["not_public_staging_proof"] is True
