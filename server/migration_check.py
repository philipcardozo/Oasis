"""Verify the database has been upgraded to the expected Alembic revision."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from server.db import engine


EXPECTED_REVISION = "29995ef61d8e"


def current_revisions() -> list[str]:
    """Return the applied Alembic revisions from the configured database."""
    with engine().connect() as connection:
        rows = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    return sorted(str(row) for row in rows)


def verify(expected: str = EXPECTED_REVISION) -> dict[str, object]:
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        current = current_revisions()
    except SQLAlchemyError as exc:
        return {
            "checked_at": checked_at,
            "expected": expected,
            "current": [],
            "ok": False,
            "error": type(exc).__name__,
        }
    return {
        "checked_at": checked_at,
        "expected": expected,
        "current": current,
        "ok": current == [expected],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", default=EXPECTED_REVISION)
    args = parser.parse_args()

    payload = verify(args.expected)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
