# ADR-0013: Staging email provider

## Status: accepted

## Decision
Use Postmark SMTP for staging transactional email.

## Rationale
OASIS already supports SMTP, so Postmark requires no application rewrite.
Registration verification and password reset can use a non-production sender
identity while preserving absolute staging links and token behavior.

Reference: https://postmarkapp.com/developer/user-guide/send-email-with-smtp

## Changes this if
The approved domain already has a different transactional provider with verified
SPF/DKIM/DMARC and equivalent staging isolation.
