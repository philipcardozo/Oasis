# Public Staging Deployment Automation Evidence

Verdict: **investigate**

- Workflow: `Deploy`
- Run ID: `123456789`
- Run attempt: `1`
- Environment: `staging`
- Commit: `abcdef123456`

## Workflow Checks

| Check | Result |
|---|---|
| workflow_dispatch is limited to the staging target | `True` |
| push deployment is scoped to main | `True` |
| GitHub staging environment is declared | `True` |
| deployment concurrency group is configured | `True` |
| release permissions cover packages, OIDC, and attestations | `True` |
| public staging config contract runs before deployment | `True` |
| migration validation runs before deployment | `True` |
| Python tests run | `True` |
| Playwright tests run | `True` |
| GHCR login is configured | `True` |
| linux/amd64 image build is configured | `True` |
| immutable SHA/staging tags are configured | `True` |
| build provenance is enabled | `True` |
| SBOM generation is enabled | `True` |
| high/critical image scan blocks deployment | `True` |
| image manifest evidence is generated | `True` |
| exact image deploy to Render API and worker is configured | `True` |
| public staging preflight runs after deploy | `True` |
| public staging evidence artifact is uploaded | `True` |
| workflow has no production deployment target | `True` |

## Run Checks

| Check | Result |
|---|---|
| workflow run evidence was captured | `True` |
| workflow run identity is not the template scaffold | `False` |
| workflow run ID is numeric | `True` |
| workflow run attempt is numeric | `True` |
| workflow run commit is a full 40-character SHA | `False` |
| workflow ran from the main branch | `True` |
| workflow run concluded successfully | `True` |
| workflow ran in the staging environment | `True` |
| GitHub staging environment protection is enabled | `True` |
| manual approval or environment approval is recorded | `True` |
| deployment secrets are isolated to the staging environment | `True` |
| run did not deploy production | `True` |
| deployment concurrency was observed or configured for the run | `True` |
| public staging evidence artifact was uploaded | `True` |
| Validate public staging config contract step succeeded | `True` |
| Install dependencies step succeeded | `True` |
| Validate migrations step succeeded | `True` |
| Python tests step succeeded | `True` |
| Playwright tests step succeeded | `True` |
| Build and publish immutable image step succeeded | `True` |
| Scan published image step succeeded | `True` |
| Record image manifest step succeeded | `True` |
| Deploy exact image to Render API and worker step succeeded | `True` |
| Public staging preflight step succeeded | `True` |
| Upload public staging evidence step succeeded | `True` |

## Artifact Consistency

| Check | Result |
|---|---|
| image manifest verdict is pass | `False` |
| Render deploy verdict is pass | `False` |
| public preflight verdict is pass | `False` |
| public preflight target is non-local HTTPS | `False` |
| workflow run identity matches the image manifest | `False` |
| run, image manifest, deploy, and preflight commits agree | `False` |
| run, image manifest, deploy, and preflight use full 40-character SHAs | `False` |
| image is digest pinned | `False` |
| Render deploy image matches the image manifest | `False` |
| Render deployments include exactly API and worker | `False` |
| public /version includes the deployed commit | `False` |

## Failures

- run check is not true: run_identity_real
- run check is not true: run_commit_full_sha
- artifacts check is not true: image_manifest_pass
- artifacts check is not true: render_deploy_pass
- artifacts check is not true: preflight_pass
- artifacts check is not true: public_preflight_target
- artifacts check is not true: workflow_run_matches_manifest
- artifacts check is not true: commit_consistent
- artifacts check is not true: commit_full_sha
- artifacts check is not true: image_digest_pinned
- artifacts check is not true: render_image_matches_manifest
- artifacts check is not true: api_worker_deployed
- artifacts check is not true: preflight_version_matches_commit

This generated report contains sanitized evidence only.
