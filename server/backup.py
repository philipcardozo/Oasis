"""Backup and restore for the transactional database.

Postgres uses pg_dump/pg_restore; SQLite (dev) copies the file. A backup is not
considered valid until a restore test succeeds — run_drill() proves it by
round-tripping representative users and map slots.

    python -m server.backup create   --out backups/
    python -m server.backup restore  --file backups/oasis-YYYYMMDD.dump
    python -m server.backup drill                     # create->wipe->restore->verify
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from server.config import get_settings


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _sqlite_path(url: str) -> Path:
    return Path(url.split("sqlite:///")[-1])


def create_backup(out_dir: str | Path) -> Path:
    settings = get_settings()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    url = settings.database_url
    if _is_sqlite(url):
        dest = out / f"oasis-{stamp}.sqlite"
        shutil.copy2(_sqlite_path(url), dest)
        return dest
    dest = out / f"oasis-{stamp}.dump"
    p = urlparse(url.replace("+psycopg", ""))
    cmd = ["pg_dump", "--format=custom", "--file", str(dest), "--dbname",
           f"postgresql://{p.username}:{p.password}@{p.hostname}:{p.port or 5432}{p.path}"]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return dest


def restore_backup(backup_file: str | Path) -> None:
    settings = get_settings()
    url = settings.database_url
    src = Path(backup_file)
    if _is_sqlite(url):
        shutil.copy2(src, _sqlite_path(url))
        from server.db import reset_engine_for_tests
        reset_engine_for_tests()
        return
    p = urlparse(url.replace("+psycopg", ""))
    dsn = f"postgresql://{p.username}:{p.password}@{p.hostname}:{p.port or 5432}{p.path}"
    subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--dbname", dsn, str(src)],
                   check=True, capture_output=True, text=True)


def run_drill(out_dir: str | Path = "backups") -> dict:
    """Create representative data, back up, wipe, restore, and confirm."""
    from server.db import engine, reset_engine_for_tests, session_scope
    from server.models import Base
    from server import repositories as repo
    from server.security import hash_password

    Base.metadata.create_all(engine())
    with session_scope() as db:
        user = repo.create_user(db, "drill@example.com", hash_password("correcthorse"))
        uid = user.id
    with session_scope() as db:
        before_slots = len(repo.list_map_slots(db, uid))

    backup = create_backup(out_dir)

    # Wipe (drop every table) to simulate loss.
    Base.metadata.drop_all(engine())
    reset_engine_for_tests()

    restore_backup(backup)

    with session_scope() as db:
        restored_user = repo.get_user_by_email(db, "drill@example.com")
        slots = repo.list_map_slots(db, uid) if restored_user else []
    ok = bool(restored_user) and len(slots) == before_slots == 3
    return {"ok": ok, "backup": str(backup), "user_restored": bool(restored_user), "slots": len(slots)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create"); c.add_argument("--out", default="backups")
    r = sub.add_parser("restore"); r.add_argument("--file", required=True)
    d = sub.add_parser("drill"); d.add_argument("--out", default="backups")
    args = p.parse_args()

    if args.cmd == "create":
        print("backup:", create_backup(args.out))
    elif args.cmd == "restore":
        restore_backup(args.file)
        print("restored from", args.file)
    elif args.cmd == "drill":
        result = run_drill(args.out)
        print("drill:", result)
        return 0 if result["ok"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
