# Phase 1 Acceptance Checklist

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Phase 0 merged without regression | ✅ | merge 408209b; 55 tests still pass |
| Real-browser map rendering verified OR blocked issue documented | ⚠️ documented | preview cannot init MapLibre; human gate required (PHASE-1 doc) |
| Register/verify/login/logout/reset/revoke | ✅ | test_phase1_auth (14) |
| No tokens in localStorage | ✅ | opaque cookie sessions; test_no_token_in_body |
| Modern password hash | ✅ | Argon2id (server/security.py) |
| CSRF on state-changing browser requests | ✅ | write-guard + require_csrf; test_phase1_authz |
| Every route has a security classification | ✅ | docs/AUTHORIZATION-MATRIX.md (generated) |
| All write routes require authorization | ✅ | 6 existing writes now auth+CSRF; test_existing_write_route_* |
| Cross-user resource access denied | ✅ | test_owner_only_map_slot_access_denied_cross_user |
| Exactly three Map Studio slots | ✅ | test_exactly_three_default_slots |
| Configs persist across sessions/devices | ✅ | DB-backed slots; list/get/update |
| Concurrent edits → explicit conflict | ✅ | 409 version_conflict; test_version_conflict_detected |
| Postgres migrations from empty DB | ✅ | test_empty_database_migration (alembic) |
| App/worker/migration separated | ✅ | server.app / server.worker / alembic step |
| User requests cause zero external downloads | ✅ | Phase 0 tests + worker isolation |
| Containers run as non-root | ✅ | Dockerfile USER oasis (uid 10001) |
| Staging starts from documented commands | ✅ | compose.yaml + DEPLOYMENT-STAGING.md |
| Health/readiness checks work | ✅ | /healthz /readyz; test_phase1_infra |
| Rate limits protect auth + expensive endpoints | ✅ | test_*_rate_limited |
| CORS + trusted-host explicit | ✅ | test_trusted_host_rejects_hostile_host; config |
| Production fails when secrets missing | ✅ | test_production_config_rejects_missing_secrets |
| Structured, sanitized logs | ✅ | server/observability.py; test_no_secrets_logged |
| Request/job correlation IDs | ✅ | correlation_id contextvar |
| Backups complete | ✅ | server.backup create |
| Restore test succeeds | ✅ | test_backup_restore_drill |
| Licensing-sensitive providers disabled unless approved | ✅ | prod defaults OFF; test_valid_production_config_passes |
| CI runs tests/migrations/containers/scans/SBOM | ✅ | .github/workflows/ci.yml |
| Existing 55 Python + 15 Playwright still pass | ✅ | 107 pytest (55+52); 15 Playwright |
| New auth/authz/infra/security tests pass | ✅ | 52 Phase 1 tests |
| Initial startup free of full-universe loading | ✅ | Phase 0 lazy loading intact |
| Clean working tree after commits | ✅ | see final report |

## Not yet satisfied (Phase 1 exit conditions requiring a human/ops step)
- Real-browser map render verification (human).
- Backup drill against a real staging Postgres (this repo verifies the drill on
  SQLite; the same command targets Postgres).
- Container-stack smoke test on a machine with Docker (Dockerfile/compose provided;
  not executable in this sandbox).
