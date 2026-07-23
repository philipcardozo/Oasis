# ADR-0011: Container registry

## Status: accepted

## Decision
Publish staging images to GHCR from GitHub Actions with commit SHA tags,
SBOM/provenance, and vulnerability scanning.

## Rationale
GHCR is close to the existing CI/CD system and supports immutable image
references tied to repository permissions. The deploy workflow records commit,
digest, build time, architecture, and registry evidence before triggering
staging deployment.

Reference: https://docs.docker.com/build/ci/github-actions/attestations/

## Changes this if
Render image-backed services become the deployment source of truth, or an
enterprise registry is mandated.
