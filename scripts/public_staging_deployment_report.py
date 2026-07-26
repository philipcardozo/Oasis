#!/usr/bin/env python3
"""Build public-staging deployment automation evidence.

This report ties the GitHub Actions deployment workflow, the actual workflow
run, the immutable image manifest, the Render deploy result, and the public
preflight into one non-secret gate artifact.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


WORKFLOW_CHECKS = {
    "workflow_dispatch_staging": (
        "workflow_dispatch is limited to the staging target",
        ("workflow_dispatch:", "options: [staging]"),
    ),
    "push_main_only": (
        "push deployment is scoped to main",
        ("push:", "branches: [main]"),
    ),
    "protected_environment_declared": (
        "GitHub staging environment is declared",
        ("environment: staging",),
    ),
    "deployment_concurrency": (
        "deployment concurrency group is configured",
        ("concurrency:", "cancel-in-progress: false"),
    ),
    "permissions_minimal_for_release": (
        "release permissions cover packages, OIDC, and attestations",
        ("contents: read", "packages: write", "id-token: write", "attestations: write"),
    ),
    "migration_validation": (
        "migration validation runs before deployment",
        ("python -m alembic upgrade head", "python -m server.migration_check --expected 29995ef61d8e"),
    ),
    "python_tests": ("Python tests run", ("python -m pytest -q",)),
    "playwright_tests": ("Playwright tests run", ("npx playwright test",)),
    "ghcr_login": ("GHCR login is configured", ("docker/login-action", "registry: ghcr.io")),
    "linux_amd64_build": ("linux/amd64 image build is configured", ("platforms: linux/amd64",)),
    "immutable_tags": ("immutable SHA/staging tags are configured", ("type=sha", "staging-${{ github.sha }}")),
    "provenance": ("build provenance is enabled", ("provenance: mode=max",)),
    "sbom": ("SBOM generation is enabled", ("sbom: true",)),
    "blocking_image_scan": (
        "high/critical image scan blocks deployment",
        ("aquasecurity/trivy-action", 'exit-code: "1"', "severity: CRITICAL,HIGH"),
    ),
    "image_manifest": (
        "image manifest evidence is generated",
        ("scripts/public_staging_image_manifest.py", "01-image-manifest.json"),
    ),
    "render_deploy": (
        "exact image deploy to Render API and worker is configured",
        ("scripts/render_deploy_image.py", "RENDER_API_SERVICE_ID", "RENDER_WORKER_SERVICE_ID"),
    ),
    "public_preflight": (
        "public staging preflight runs after deploy",
        ("scripts/public_staging_preflight.py", "STAGING_URL"),
    ),
    "artifact_upload": (
        "public staging evidence artifact is uploaded",
        ("actions/upload-artifact", "docs/evidence/public-staging/"),
    ),
    "no_production_target": (
        "workflow has no production deployment target",
        ("options: [staging]",),
    ),
}

RUN_CHECKS = {
    "run_captured": "workflow run evidence was captured",
    "run_success": "workflow run concluded successfully",
    "environment_staging": "workflow ran in the staging environment",
    "protected_environment": "GitHub staging environment protection is enabled",
    "manual_approval": "manual approval or environment approval is recorded",
    "secrets_isolated": "deployment secrets are isolated to the staging environment",
    "no_production_deploy": "run did not deploy production",
    "concurrency_observed": "deployment concurrency was observed or configured for the run",
    "artifact_uploaded": "public staging evidence artifact was uploaded",
    "install_dependencies": "Install dependencies step succeeded",
    "validate_migrations": "Validate migrations step succeeded",
    "python_tests": "Python tests step succeeded",
    "playwright_tests": "Playwright tests step succeeded",
    "build_publish_image": "Build and publish immutable image step succeeded",
    "scan_image": "Scan published image step succeeded",
    "record_image_manifest": "Record image manifest step succeeded",
    "deploy_render": "Deploy exact image to Render API and worker step succeeded",
    "public_preflight": "Public staging preflight step succeeded",
    "upload_evidence": "Upload public staging evidence step succeeded",
}

STEP_NAMES = {
    "install_dependencies": "Install dependencies",
    "validate_migrations": "Validate migrations",
    "python_tests": "Python tests",
    "playwright_tests": "Playwright tests",
    "build_publish_image": "Build and publish immutable image",
    "scan_image": "Scan published image",
    "record_image_manifest": "Record image manifest",
    "deploy_render": "Deploy exact image to Render API and worker",
    "public_preflight": "Public staging preflight",
    "upload_evidence": "Upload public staging evidence",
}

ARTIFACT_CHECKS = {
    "image_manifest_pass": "image manifest verdict is pass",
    "render_deploy_pass": "Render deploy verdict is pass",
    "preflight_pass": "public preflight verdict is pass",
    "workflow_run_matches_manifest": "workflow run identity matches the image manifest",
    "commit_consistent": "run, image manifest, deploy, and preflight commits agree",
    "image_digest_pinned": "image is digest pinned",
    "render_image_matches_manifest": "Render deploy image matches the image manifest",
    "api_worker_deployed": "Render deployments include exactly API and worker",
    "preflight_version_matches_commit": "public /version includes the deployed commit",
}


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines())


def status_ok(value: Any) -> bool:
    return str(value or "").lower() in {"pass", "passed", "ok", "success", "succeeded", "true", "present"}


def step_succeeded(run: dict[str, Any], name: str) -> bool:
    steps = run.get("steps") or {}
    value = steps.get(name)
    if value is None:
        value = steps.get(name.lower())
    if isinstance(value, dict):
        value = value.get("conclusion") or value.get("status")
    return status_ok(value)


def endpoint_text(preflight: dict[str, Any] | None, path: str) -> str:
    if not preflight:
        return ""
    result = (preflight.get("endpoints") or {}).get(path) or {}
    if isinstance(result.get("body_json"), dict):
        return json.dumps(result["body_json"], sort_keys=True)
    return str(result.get("body_text") or "")


def render_roles(render_deploy: dict[str, Any] | None) -> list[str]:
    if not render_deploy:
        return []
    return sorted(str(item.get("role") or "") for item in render_deploy.get("deployments") or [])


def check_row(key: str, label: str, value: bool) -> dict[str, Any]:
    return {"key": key, "label": label, "value": bool(value)}


def workflow_rows(text: str) -> list[dict[str, Any]]:
    normalized = normalize(text)
    rows = []
    for key, (label, needles) in WORKFLOW_CHECKS.items():
        rows.append(check_row(key, label, all(needle in normalized for needle in needles)))
    return rows


def run_rows(run: dict[str, Any] | None) -> list[dict[str, Any]]:
    run = run or {}
    rows = [
        check_row("run_captured", RUN_CHECKS["run_captured"], bool(run.get("captured_at") and run.get("run_id"))),
        check_row("run_success", RUN_CHECKS["run_success"], status_ok(run.get("conclusion"))),
        check_row("environment_staging", RUN_CHECKS["environment_staging"], run.get("environment") == "staging"),
        check_row("protected_environment", RUN_CHECKS["protected_environment"], run.get("protected_environment") is True),
        check_row("manual_approval", RUN_CHECKS["manual_approval"], run.get("manual_approval") is True),
        check_row("secrets_isolated", RUN_CHECKS["secrets_isolated"], run.get("secrets_isolated") is True),
        check_row("no_production_deploy", RUN_CHECKS["no_production_deploy"], run.get("production_deploy") is False),
        check_row("concurrency_observed", RUN_CHECKS["concurrency_observed"], run.get("deployment_concurrency_observed") is True),
        check_row("artifact_uploaded", RUN_CHECKS["artifact_uploaded"], run.get("artifact_uploaded") is True),
    ]
    for key, step_name in STEP_NAMES.items():
        rows.append(check_row(key, RUN_CHECKS[key], step_succeeded(run, step_name)))
    return rows


def artifact_rows(
    run: dict[str, Any] | None,
    image_manifest: dict[str, Any] | None,
    render_deploy: dict[str, Any] | None,
    preflight: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    run = run or {}
    image_manifest = image_manifest or {}
    render_deploy = render_deploy or {}
    preflight = preflight or {}

    image = str(image_manifest.get("image") or "")
    digest = str(image_manifest.get("digest") or "")
    manifest_ci = image_manifest.get("ci") or {}
    manifest_commit = str(image_manifest.get("commit") or "")
    run_commit = str(run.get("commit") or "")
    render_commit = str(render_deploy.get("commit") or manifest_commit)
    preflight_commit = str(preflight.get("commit") or manifest_commit)

    rows = [
        check_row("image_manifest_pass", ARTIFACT_CHECKS["image_manifest_pass"], image_manifest.get("verdict") == "pass"),
        check_row("render_deploy_pass", ARTIFACT_CHECKS["render_deploy_pass"], render_deploy.get("verdict") == "pass"),
        check_row("preflight_pass", ARTIFACT_CHECKS["preflight_pass"], preflight.get("verdict") == "pass"),
        check_row(
            "workflow_run_matches_manifest",
            ARTIFACT_CHECKS["workflow_run_matches_manifest"],
            str(manifest_ci.get("workflow") or "") == str(run.get("workflow") or "")
            and str(manifest_ci.get("run_id") or "") == str(run.get("run_id") or "")
            and str(manifest_ci.get("run_attempt") or "") == str(run.get("run_attempt") or ""),
        ),
        check_row(
            "commit_consistent",
            ARTIFACT_CHECKS["commit_consistent"],
            bool(manifest_commit)
            and manifest_commit == run_commit
            and manifest_commit == render_commit
            and manifest_commit == preflight_commit,
        ),
        check_row("image_digest_pinned", ARTIFACT_CHECKS["image_digest_pinned"], "@" in image and DIGEST_RE.match(digest) is not None and image.endswith(f"@{digest}")),
        check_row("render_image_matches_manifest", ARTIFACT_CHECKS["render_image_matches_manifest"], render_deploy.get("image_url") == image),
        check_row("api_worker_deployed", ARTIFACT_CHECKS["api_worker_deployed"], render_roles(render_deploy) == ["api", "worker"]),
        check_row("preflight_version_matches_commit", ARTIFACT_CHECKS["preflight_version_matches_commit"], bool(manifest_commit and manifest_commit in endpoint_text(preflight, "/version"))),
    ]
    return rows


def failures_for_section(section: str, rows: list[dict[str, Any]]) -> list[str]:
    return [f"{section} check is not true: {row['key']}" for row in rows if row.get("value") is not True]


def build_payload(
    *,
    workflow_text: str,
    run: dict[str, Any] | None,
    image_manifest: dict[str, Any] | None,
    render_deploy: dict[str, Any] | None,
    preflight: dict[str, Any] | None,
    workflow_path: str,
) -> dict[str, Any]:
    workflow = workflow_rows(workflow_text)
    run_section = run_rows(run)
    artifacts = artifact_rows(run, image_manifest, render_deploy, preflight)
    failures = (
        failures_for_section("workflow", workflow)
        + failures_for_section("run", run_section)
        + failures_for_section("artifacts", artifacts)
    )
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "input_captured_at": (run or {}).get("captured_at"),
        "verdict": "pass" if not failures else "investigate",
        "failures": failures,
        "warnings": [],
        "target": {
            "workflow_path": workflow_path,
            "workflow": (run or {}).get("workflow"),
            "run_id": (run or {}).get("run_id"),
            "run_attempt": (run or {}).get("run_attempt"),
            "environment": (run or {}).get("environment"),
            "commit": (run or {}).get("commit"),
        },
        "workflow": {"rows": workflow},
        "run": {"rows": run_section},
        "artifacts": {"rows": artifacts},
    }
    return payload


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Deployment Automation Evidence",
        "",
        f"Verdict: **{payload['verdict']}**",
        "",
        f"- Workflow: `{payload['target'].get('workflow') or '<missing>'}`",
        f"- Run ID: `{payload['target'].get('run_id') or '<missing>'}`",
        f"- Run attempt: `{payload['target'].get('run_attempt') or '<missing>'}`",
        f"- Environment: `{payload['target'].get('environment') or '<missing>'}`",
        f"- Commit: `{payload['target'].get('commit') or '<missing>'}`",
        "",
        "## Workflow Checks",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for row in payload["workflow"]["rows"]:
        lines.append(f"| {row['label']} | `{row['value']}` |")
    lines.extend(["", "## Run Checks", "", "| Check | Result |", "|---|---|"])
    for row in payload["run"]["rows"]:
        lines.append(f"| {row['label']} | `{row['value']}` |")
    lines.extend(["", "## Artifact Consistency", "", "| Check | Result |", "|---|---|"])
    for row in payload["artifacts"]["rows"]:
        lines.append(f"| {row['label']} | `{row['value']}` |")
    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        for item in payload["failures"]:
            lines.append(f"- {item}")
    lines.extend(["", "This generated report contains sanitized evidence only."])
    return "\n".join(lines) + "\n"


def template() -> dict[str, Any]:
    return {
        "captured_at": "2026-07-25T00:00:00Z",
        "workflow": "Deploy",
        "run_id": "123456789",
        "run_attempt": "1",
        "event": "workflow_dispatch",
        "branch": "main",
        "commit": "abcdef123456",
        "environment": "staging",
        "conclusion": "success",
        "protected_environment": True,
        "manual_approval": True,
        "secrets_isolated": True,
        "production_deploy": False,
        "deployment_concurrency_observed": True,
        "artifact_uploaded": True,
        "artifact_name": "public-staging-evidence-abcdef123456",
        "steps": {name: "success" for name in STEP_NAMES.values()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-template", action="store_true", help="print a non-secret deployment run evidence template and exit")
    parser.add_argument("--workflow", default=str(WORKFLOW))
    parser.add_argument("--run-evidence", default=str(EVIDENCE / "deployment-automation-run.json"))
    parser.add_argument("--image-manifest", default=str(EVIDENCE / "01-image-manifest.json"))
    parser.add_argument("--render-deploy", default=str(EVIDENCE / "02-render-deploy.json"))
    parser.add_argument("--preflight", default=str(EVIDENCE / "00-public-staging-preflight.json"))
    parser.add_argument("--output", default=str(EVIDENCE / "16-deployment-automation.md"))
    parser.add_argument("--summary-output", default=str(EVIDENCE / "deployment-automation-summary.json"))
    args = parser.parse_args()

    if args.print_template:
        print(json.dumps(template(), indent=2, sort_keys=True))
        return 0

    workflow_path = Path(args.workflow)
    workflow_text = workflow_path.read_text() if workflow_path.exists() else ""
    payload = build_payload(
        workflow_text=workflow_text,
        run=load_json(Path(args.run_evidence)),
        image_manifest=load_json(Path(args.image_manifest)),
        render_deploy=load_json(Path(args.render_deploy)),
        preflight=load_json(Path(args.preflight)),
        workflow_path=str(workflow_path),
    )

    output = Path(args.output)
    summary = Path(args.summary_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(payload))
    write_json(summary, payload)
    print(f"Wrote public staging deployment automation report to {output}")
    print(f"Wrote public staging deployment automation summary to {summary}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
