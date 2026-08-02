#!/usr/bin/env python3
"""Generate a secret-free public-staging setup checklist.

The output is an operator checklist, not deployment evidence. It deliberately
uses placeholder values and records no provider credentials.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.public_staging_config_contract import normalize_provider
from scripts.public_staging_readiness import (
    GCP_GITHUB_STAGING_SECRETS,
    GCP_GITHUB_STAGING_VARIABLES,
    GITHUB_STAGING_SECRETS,
    GITHUB_STAGING_VARIABLES,
    git_value,
)


EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
DEFAULT_MARKDOWN = EVIDENCE / "public-staging-setup-checklist.md"
DEFAULT_JSON = EVIDENCE / "public-staging-setup-checklist.json"

RENDER_ENV_GROUP_VALUES = [
    "OASIS_PUBLIC_BASE_URL=https://staging.<approved-domain>",
    "OASIS_API_BASE_URL=https://staging.<approved-domain>",
    "OASIS_ALLOWED_ORIGINS=https://staging.<approved-domain>",
    "OASIS_TRUSTED_HOSTS=staging.<approved-domain>",
    "OASIS_EMAIL_FROM=OASIS Staging <no-reply@<approved-domain>>",
    "OASIS_SMTP_HOST=<smtp-host>",
    "OASIS_SMTP_USER=<smtp-user-if-required>",
    "OASIS_SMTP_PASSWORD=<smtp-password-if-required>",
    "OASIS_STORAGE_BACKEND=s3",
    "OASIS_S3_BUCKET=<private-r2-bucket>",
    "OASIS_S3_REGION=auto",
    "OASIS_S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com",
    "AWS_ACCESS_KEY_ID=<least-privilege-r2-access-key>",
    "AWS_SECRET_ACCESS_KEY=<least-privilege-r2-secret-key>",
    "OASIS_REGISTRATION_ALLOWED_EMAILS=<comma-separated-private-beta-testers>",
]

CLOUDFLARE_ITEMS = [
    "Create DNS hostname staging.<approved-domain> pointing to the Render web service target.",
    "Enable HTTPS/TLS for the hostname and verify HSTS policy stays staging-safe.",
    "Protect the hostname with Cloudflare Access and create service-token credentials for probes.",
    "Configure WAF/rate controls for the controlled private-beta boundary.",
    "Create a private Cloudflare R2 bucket and least-privilege S3-compatible credentials.",
]

RENDER_ITEMS = [
    "Sync render.yaml or equivalent Render Blueprint.",
    "Create registry credential ghcr-oasis with GHCR package read access.",
    "Create oasis-api-staging web service and oasis-worker-staging worker service.",
    "Create oasis-postgres-staging managed PostgreSQL with private networking.",
    "Fill Render oasis-staging-shared values marked sync: false outside Git.",
]

GCP_ITEMS = [
    "Use project-scoped staging resources in us-east1.",
    "Create Artifact Registry repository oasis in us-east1.",
    "Create Cloud SQL PostgreSQL instance oasis-staging-postgres in us-east1.",
    "Create Secret Manager secrets for OASIS_SESSION_SECRET, DATABASE_URL, and SMTP credentials.",
    "Create Cloud Storage bucket for exports and mount it into Cloud Run at /app/outputs.",
    "Deploy Cloud Run service oasis-staging with min=0 and max=3.",
    "Deploy Cloud Run worker pool oasis-staging-worker with instances=1 while testing and 0 when idle.",
    "Run migrations through a Cloud Run Job using python -m alembic upgrade head.",
    "Use Workload Identity Federation for GitHub Actions; do not create a JSON service-account key.",
]


def build_payload(*, provider: str = "render", captured_at: str | None = None) -> dict[str, Any]:
    provider = normalize_provider(provider)
    variables = GCP_GITHUB_STAGING_VARIABLES if provider == "gcp" else GITHUB_STAGING_VARIABLES
    secrets = GCP_GITHUB_STAGING_SECRETS if provider == "gcp" else GITHUB_STAGING_SECRETS
    staging_url_placeholder = "https://<generated-run-app-url>" if provider == "gcp" else "https://staging.<approved-domain>"
    github_commands = [
        f'gh variable set STAGING_URL --env staging --body "{staging_url_placeholder}"',
        *[
            f'gh variable set {name} --env staging --body "<{name.lower()}>"'
            for name in variables
            if name != "STAGING_URL"
        ],
        *[f'gh secret set {name} --env staging --body "<{name.lower()}>"' for name in secrets],
    ]
    return {
        "captured_at": captured_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "branch": git_value("branch", "--show-current"),
        "commit": git_value("rev-parse", "HEAD"),
        "not_public_staging_proof": True,
        "verdict": "operator_setup_required",
        "deploy_provider": provider,
        "github_environment": {
            "name": "staging",
            "required_variables": variables,
            "required_secrets": secrets,
            "commands": github_commands,
            "manual_requirements": [
                "Run python3 scripts/public_staging_github_environment.py to enforce required reviewer and main branch deployment policy.",
                "Keep production deployment absent from this workflow.",
            ],
        },
        "cloudflare": CLOUDFLARE_ITEMS,
        "render": RENDER_ITEMS,
        "gcp": GCP_ITEMS,
        "render_environment_group_values": RENDER_ENV_GROUP_VALUES,
        "tester_requirements": [
            "Create dedicated tester A, tester B, and lifecycle account email inboxes.",
            "Set OASIS_PUBLIC_TESTER_A_EMAIL, OASIS_PUBLIC_TESTER_A_PASSWORD, and OASIS_PUBLIC_TESTER_A_RESET_PASSWORD outside Git.",
            "Set OASIS_PUBLIC_TESTER_B_EMAIL and OASIS_PUBLIC_TESTER_B_PASSWORD outside Git.",
            "Set OASIS_PUBLIC_LIFECYCLE_EMAIL, OASIS_PUBLIC_LIFECYCLE_PASSWORD, and OASIS_PUBLIC_LIFECYCLE_CHANGED_PASSWORD outside Git.",
            "Record only verification/reset tokens in environment variables during probes.",
            "Run python3 scripts/public_staging_browser_matrix_template.py --base-url=\"$STAGING_URL\" before manual browser verification.",
            "Use installed Chrome, Firefox, and Safari apps to complete the manual browser matrix after STAGING_URL is live.",
        ],
        "verification_order": [
            "python3 scripts/public_staging_config_contract.py",
            "python3 scripts/public_staging_readiness.py",
            'gh workflow run "Deploy GCP" --ref deploy/gcp-staging -f target=staging' if provider == "gcp" else "gh workflow run Deploy --ref main -f target=staging",
            "python3 scripts/public_staging_full_verification.py --base-url=\"$STAGING_URL\" --dry-run",
            "python3 scripts/public_staging_smoke.py --base-url=\"$STAGING_URL\"",
            "python3 scripts/public_staging_preflight.py --base-url=\"$STAGING_URL\"" if provider == "gcp" else "python3 scripts/public_staging_preflight.py --base-url=\"$STAGING_URL\" --header CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID --header CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET",
            "python3 scripts/public_staging_playwright_report.py --base-url=\"$STAGING_URL\"",
            "python3 scripts/public_staging_full_verification.py --base-url=\"$STAGING_URL\" --proxy-server=http://127.0.0.1:9090",
            "Run public browser, auth, route, performance, infra, ops, storage, email, licensing, and failure report generators from docs/PUBLIC-STAGING-RUNBOOK.md.",
            "python3 scripts/public_staging_gate_audit.py",
        ],
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Setup Checklist",
        "",
        f"Captured: {payload['captured_at']}",
        f"Branch: `{payload['branch']}`",
        f"Commit: `{payload['commit']}`",
        f"Provider: `{payload['deploy_provider']}`",
        "Verdict: **operator_setup_required**",
        "",
        "This generated checklist is not public-staging proof and contains no secret values.",
        "",
        "## GitHub Staging Environment",
        "",
        "Required variable:",
        "",
    ]
    lines.extend(f"- `{name}`" for name in payload["github_environment"]["required_variables"])
    lines.extend(["", "Required secrets:", ""])
    lines.extend(f"- `{name}`" for name in payload["github_environment"]["required_secrets"])
    lines.extend(["", "Secret-free command skeletons:", ""])
    lines.extend(f"```bash\n{command}\n```" for command in payload["github_environment"]["commands"])
    lines.extend(["", "Manual requirements:", ""])
    lines.extend(f"- {item}" for item in payload["github_environment"]["manual_requirements"])

    sections = [
        ("Tester Requirements", "tester_requirements"),
        ("Verification Order", "verification_order"),
    ]
    if payload["deploy_provider"] == "gcp":
        sections = [("GCP", "gcp"), *sections]
    else:
        sections = [
            ("Cloudflare", "cloudflare"),
            ("Render", "render"),
            ("Render Environment Group Values", "render_environment_group_values"),
            *sections,
        ]

    for title, key in sections:
        lines.extend(["", f"## {title}", ""])
        lines.extend(f"- `{item}`" if "=" in item and key == "render_environment_group_values" else f"- {item}" for item in payload[key])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--json-output", default=str(DEFAULT_JSON))
    parser.add_argument("--provider", choices=["gcp", "render"], default="render")
    args = parser.parse_args()

    payload = build_payload(provider=args.provider)
    output = Path(args.output)
    json_output = Path(args.json_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(payload))
    json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging setup checklist to {output}")
    print(f"Wrote public staging setup checklist JSON to {json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
