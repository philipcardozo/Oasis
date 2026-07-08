# Oasis Project Rules

## Terrain Ingestion and Big Data Processing Rules

1. **Incremental Processing & Space Management**:
   - When importing large spatial datasets (e.g., DEMs, GeoTIFFs), always process incrementally in batches (e.g., tile-by-tile or state-by-state).
   - Unconditionally delete raw files immediately after generating the processed output tiles to prevent disk space exhaustion.

2. **Network Resilience and SSL Certificate Handling**:
   - If public federal endpoints (like USGS TNM) return SSL/certificate verification errors, fall back to `ssl._create_unverified_context()` since local environment certificate bundles may lack specific root authorities.
   - Implement exponential backoff (e.g., 3 retries, starting at 1s, doubling each time) for all HTTP requests to survive transient Gateway Timeouts (HTTP 504).

3. **Orchestrator Automation**:
   - Provide an outer orchestrator shell or python script when processing multiple sequential zones.
   - The orchestrator must check current coverage reports (`terrain_coverage.json`) and resume immediately from the first incomplete zone/tile to allow seamless stopping and restarting.
