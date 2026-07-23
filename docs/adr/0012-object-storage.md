# ADR-0012: Public staging object storage

## Status: accepted

## Decision
Use a private Cloudflare R2 bucket through the existing S3-compatible storage
adapter.

## Rationale
OASIS already has local/S3 storage abstraction. R2 provides S3-compatible
credentials, private buckets, lifecycle controls, and low operational burden in
the same Cloudflare account used for DNS and Access.

Staging object storage is for exports, approved logos, future report artifacts,
and temporary private files. Bucket listing stays private; browsers receive only
server-authorized expiring downloads.

References:

- R2 S3 API: https://developers.cloudflare.com/r2/get-started/s3/
- R2 lifecycle rules: https://developers.cloudflare.com/r2/buckets/object-lifecycles/

## Changes this if
Provider procurement requires AWS S3, or export volume requires a different
retention/cost model.
