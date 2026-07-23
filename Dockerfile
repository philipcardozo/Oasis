# OASIS production image — API and worker share this image, differ only by command.
# Multi-stage: build wheels in a fat stage, copy into a slim runtime.
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements.txt ./
# Deterministic install of the declared runtime + auth/db extras.
RUN pip install --prefix=/install \
    "fastapi>=0.110" "uvicorn[standard]>=0.29" "duckdb>=0.10" "certifi>=2024.2.2" \
    "openpyxl>=3.1" "ujson>=5.9" \
    "sqlalchemy>=2.0" "alembic>=1.13" "argon2-cffi>=23.1" "itsdangerous>=2.1" \
    "psycopg[binary]>=3.1" "httpx>=0.27"

FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.title="OASIS" \
      org.opencontainers.image.source="https://github.com/veratori/oasis"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OASIS_MODE=production
# Non-root runtime user.
RUN useradd --create-home --uid 10001 oasis
WORKDIR /app
COPY --from=build /install /usr/local
# Application code (data/ and secrets are mounted, never baked in).
COPY --chown=oasis:oasis server ./server
COPY --chown=oasis:oasis map_api.py dcf_export.py comps.py reverse_dcf.py political.py \
     store.py gates.py data_sources.py oasis_paths.py cache_companyfacts.py \
     build_events.py build_briefing.py build_map_geojson.py expand_us.py build_store.py \
     refresh_financial_facts.py alembic.ini pyproject.toml ./
COPY --chown=oasis:oasis graph ./graph
# Writable dirs (mounted volumes override in compose).
RUN mkdir -p /app/data /app/outputs && chown -R oasis:oasis /app/data /app/outputs
USER oasis
EXPOSE 8788
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8788/healthz',timeout=3).status==200 else 1)"
# Production: no reload. Graceful shutdown via uvicorn's default SIGTERM handling.
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8788", "--workers", "2", "--timeout-graceful-shutdown", "20"]
