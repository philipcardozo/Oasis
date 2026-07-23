# Staging Backup And Restore

## Policy

- PostgreSQL: managed backup plus on-demand `pg_dump` before risky deploys.
- Object storage: private bucket, versioning/lifecycle where enabled.
- Evidence: restore into a separate database before trusting the backup.

## Drill

1. Create two users.
2. Verify sessions.
3. Confirm exactly three map slots per user.
4. Customize maps.
5. Create audit/job records.
6. Create on-demand PostgreSQL backup.
7. Record checksum and size.
8. Restore into a separate database.
9. Run `python -m alembic upgrade head && python -m server.migration_check --expected 29995ef61d8e`.
10. Point a temporary OASIS service at the restored database.
11. Verify authentication, authorization, map slots, and job metadata.

Record result in `docs/evidence/public-staging/12-backup-restore.md`.
