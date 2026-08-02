"""GCP staging deployment contract regressions."""
from __future__ import annotations

from pathlib import Path


def test_dockerfile_reads_cloud_run_port_with_local_default():
    text = Path("Dockerfile").read_text()

    assert "--host 0.0.0.0" in text
    assert "--port ${PORT:-8788}" in text
    assert "os.environ.get('PORT','8788')" in text
    assert "server.app:app" in text


def test_compose_role_commands_are_recorded_exactly():
    text = Path("compose.yaml").read_text()

    assert 'command: ["python", "-m", "alembic", "upgrade", "head"]' in text
    assert 'command: ["python", "-m", "server.worker"]' in text


def test_gcp_workflow_uses_expected_provider_resources_and_gates():
    text = Path(".github/workflows/deploy-gcp.yml").read_text()

    for needle in (
        "name: Deploy GCP",
        "google-github-actions/auth@v2",
        "workload_identity_provider: ${{ vars.GCP_WORKLOAD_IDENTITY_PROVIDER }}",
        "python3 scripts/public_staging_config_contract.py --provider=gcp",
        "python3 scripts/public_staging_readiness.py --mode=github-actions",
        "gcloud builds submit --tag",
        "gcloud run jobs deploy",
        "--command=python",
        "--args=-m,alembic,upgrade,head",
        "gcloud run deploy",
        "--no-traffic",
        "--tag=candidate",
        "python scripts/public_staging_preflight.py",
        "npx playwright test --config=playwright.public.config.js",
        "gcloud run worker-pools deploy",
        "--args=-m,server.worker",
        "gcloud run services update-traffic",
        "--to-tags=candidate=100",
        "type=cloud-storage",
        "OASIS_STORAGE_DIR=/app/outputs/storage",
        "OASIS_BUILD_COMMIT=${GITHUB_SHA}",
    ):
        assert needle in text

    assert "RENDER_API_KEY" not in text
    assert "CF-Access-Client-Id" not in text
