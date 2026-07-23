# ADR-0011: Container registry

## Status: accepted

## Decision
Publish staging images to GHCR from GitHub Actions with commit SHA tags,
SBOM/provenance, and vulnerability scanning.

## Rationale
GHCR is close to the existing CI/CD system and supports immutable image
references tied to repository permissions. Render pulls the image through a
workspace registry credential, and the deploy workflow passes the scanned digest
to Render as `imageUrl`.

Reference: https://docs.docker.com/build/ci/github-actions/attestations/

## Changes this if
An enterprise registry is mandated or Render cannot pull private GHCR images
reliably.
