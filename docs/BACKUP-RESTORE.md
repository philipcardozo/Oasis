# Backup and Restore

Covers PostgreSQL (users, sessions, orgs, map slots, audit, job metadata).
Object storage and analytical dataset manifests are backed up by their own
lifecycle (bucket versioning / regenerable from source).

## Policy
- Frequency: nightly full + WAL/PITR where the managed DB supports it.
- Retention: 7 daily, 4 weekly (tune to RPO).
- Encryption: at rest (managed) + encrypted backup artifacts.
- Access: restore initiated only by an operator with the ops role.
- RPO target: <= 24h (nightly) / minutes (PITR). RTO target: <= 1h.

## Commands
```bash
python -m server.backup create  --out backups/          # pg_dump (SQLite: file copy)
python -m server.backup restore --file backups/oasis-*.dump
python -m server.backup drill                           # create->wipe->restore->verify
```

## A backup is not valid until a restore test succeeds
`run_drill()` creates representative users + three map slots, backs up, drops all
tables, restores, and asserts the user and all three slots return. Covered by
`test_phase1_infra.py::test_backup_restore_drill` (passes against SQLite;
run the same drill against a staging Postgres before relying on it).

## Schema versions
Restores carry the `alembic_version`. After restore, run `alembic upgrade head`
if the running code is newer; migrations are backward-compatible one release.
