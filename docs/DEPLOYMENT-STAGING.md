# Staging Deployment

Staging is fully separate from production: separate DB, secrets, storage
namespace, email sandbox, domain, origins, logs. No production user data. A clear
environment indicator (`OASIS_MODE=staging`) and controlled access during beta.

## Low-cost recommended topology
```
Cloudflare (DNS/CDN/WAF) ─► Caddy (TLS) ─► api container(s)
                                        ─► worker container
                            managed PostgreSQL
                            S3-compatible object storage (R2)
                            scheduled refresh (worker cron)
                            OTel-compatible log/metric sink
```

## Bring up locally (staging simulation)
```bash
cp .env.example .env
# set OASIS_SESSION_SECRET (>=32), OASIS_ALLOWED_ORIGINS, OASIS_TRUSTED_HOSTS,
#     OASIS_PUBLIC_BASE_URL (https), SMTP + POSTGRES_PASSWORD
docker compose up --build
# compose runs: postgres -> migrate (alembic upgrade head) -> api + worker + caddy
curl -k https://localhost:8443/healthz
curl -k https://localhost:8443/readyz
```

## Scalable production evolution (documented, not required for beta)
Multiple API replicas · separate worker pool · managed queue/Redis · CDN ·
dedicated object storage · read replicas · autoscaling · regional deploys.
Same process boundaries — replicate, don't re-architect.

## Deploy safety
- `migrate` runs as its own one-shot service/step (never at API startup).
- Blue-green via image tag; keep the previous tag for rollback.
- Production deploy requires an explicit protected-environment approval
  (`.github/workflows/deploy.yml`, environment: production).
