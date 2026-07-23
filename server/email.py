"""Transactional email abstraction.

Backends: console (dev, prints), memory (tests, captures), smtp (staging/prod).
Domain logic never imports a specific provider — it calls send(). Links are
absolute URLs built from trusted config, single-use, and expiring.
"""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from server.config import Settings, get_settings

log = logging.getLogger("oasis.email")

# Test capture buffer (memory backend).
SENT: list["Message"] = []


@dataclass
class Message:
    to: str
    subject: str
    text: str
    html: str | None = None


def _verify_url(settings: Settings, token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/verify-email?token={token}"


def _reset_url(settings: Settings, token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/reset-password?token={token}"


def send(msg: Message, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    backend = settings.email_backend
    if backend == "memory":
        SENT.append(msg)
        return
    if backend == "console":
        print(f"[email:console] to={msg.to} subject={msg.subject}\n{msg.text}")
        return
    if backend == "smtp":
        em = EmailMessage()
        em["From"] = settings.email_from
        em["To"] = msg.to
        em["Subject"] = msg.subject
        em.set_content(msg.text)
        if msg.html:
            em.add_alternative(msg.html, subtype="html")
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as srv:
                if settings.smtp_starttls:
                    srv.starttls()
                if settings.smtp_user:
                    srv.login(settings.smtp_user, settings.smtp_password)
                srv.send_message(em)
        except Exception as exc:  # delivery failure is logged; caller may retry via a job
            log.error("email delivery failed to=%s subject=%s err=%s", msg.to, msg.subject, type(exc).__name__)
            raise
        return
    raise ValueError(f"unknown email backend {backend!r}")


def send_verification(to: str, token: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    url = _verify_url(settings, token)
    send(Message(to=to, subject="Verify your OASIS account",
                 text=f"Confirm your email to activate OASIS:\n\n{url}\n\nThis link expires in 24 hours."), settings)


def send_password_reset(to: str, token: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    url = _reset_url(settings, token)
    send(Message(to=to, subject="Reset your OASIS password",
                 text=f"Reset your password:\n\n{url}\n\nThis link expires in 1 hour. If you did not request this, ignore it."), settings)
