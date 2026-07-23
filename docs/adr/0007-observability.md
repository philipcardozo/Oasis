# ADR-0007: Observability

## Status: accepted

## Decision
OpenTelemetry-first, provider-neutral instrumentation. Structured JSON logs +
correlation IDs now; wire to a collector later.

## Rationale
Avoids per-host APM pricing lock-in early. OTel lets Datadog/Dynatrace/Grafana
be introduced later without rewriting instrumentation.

## Changes this if
Enterprise SLAs require a vendor APM with support → point the OTel collector at
it; app instrumentation stays the same.
