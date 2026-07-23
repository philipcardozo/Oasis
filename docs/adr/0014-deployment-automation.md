# ADR-0014: Public staging deployment automation

## Status: accepted

## Decision
Use a protected GitHub Actions `Deploy` workflow for public staging.

## Rationale
The workflow runs dependency install, migration validation, Python tests,
Playwright tests, immutable image build, SBOM/provenance, image scan, Render API
deploy with exact `imageUrl`, Render API predeploy migration, in-image Alembic
revision verification through `python -m server.migration_check`, Render worker
deploy with the same image digest, and public staging preflight.

Render API keys and raw service IDs remain GitHub environment secrets.
Production deployment is intentionally absent from this workflow.

References:

- https://api-docs.render.com/reference/create-deploy
- https://api-docs.render.com/reference/retrieve-deploy

## Changes this if
Render native auto-deploy or a provider one-off migration job can prove the same
migration, image, smoke-test, rollback, and audit controls with less custom
workflow code.
