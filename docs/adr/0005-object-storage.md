# ADR-0005: Object storage

## Status: accepted

## Decision
An abstraction with a local-filesystem backend (dev) and an S3-compatible
backend (staging/production). Objects private by default; downloads authorized
by the app, never by bucket path. Path-traversal keys rejected.

## Rationale
Exports and large artifacts should not live in the app DB or be world-readable.
S3-compatible (R2/S3/MinIO) keeps the provider swappable.

## Changes this if
A CDN-signed-URL delivery path is needed for large exports → add signed URLs to
the abstraction (interface already isolates callers).
