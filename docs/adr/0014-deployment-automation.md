# ADR-0014: Public staging deployment automation

## Status: accepted

## Decision
Use a protected GitHub Actions `Deploy` workflow for public staging.

## Rationale
The workflow runs dependency install, migration validation, Python tests,
Playwright tests, immutable image build, SBOM/provenance, image scan, Render API
deploy, Render worker deploy, and public staging preflight.

Deploy hooks remain secrets. Production deployment is intentionally absent from
this workflow.

Reference: https://render.com/docs/deploy-hooks

## Changes this if
Render native auto-deploy with required CI checks can prove the same migration,
image, smoke-test, rollback, and audit controls with less custom workflow code.
