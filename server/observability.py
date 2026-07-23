"""Structured logging and request/correlation IDs. Provider-neutral.

JSON logs in secure modes, human-readable in development. Never logs passwords,
tokens, credentials, authorization headers, or user research content.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

from server.config import get_settings

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Header/field names that must never be logged verbatim.
_REDACT = {"authorization", "cookie", "set-cookie", "password", "token", "secret", "session"}


def _sensitive(name: str) -> bool:
    lowered = name.lower()
    return any(part in lowered for part in _REDACT)


def new_correlation_id() -> str:
    cid = uuid.uuid4().hex
    _correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    _correlation_id.set(cid)


def correlation_id() -> str | None:
    return _correlation_id.get()


def redact(mapping: dict) -> dict:
    out = {}
    for k, v in (mapping or {}).items():
        out[k] = "<redacted>" if _sensitive(k) else v
    return out


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        cid = correlation_id()
        if cid:
            payload["correlation_id"] = cid
        for key, val in getattr(record, "extra_fields", {}).items():
            payload[key] = "<redacted>" if _sensitive(key) else val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


def configure_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)-5s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))


def log_event(logger: logging.Logger, level: int, msg: str, **fields) -> None:
    logger.log(level, msg, extra={"extra_fields": redact(fields)})
