"""Outgoing email.

Backends (EMAIL_BACKEND):

* ``console``: development default. Logs the message, including password reset
  links, so the flow can be tested locally. Refused in production.
* ``smtp``: sends through any SMTP relay (Gmail Workspace, Amazon SES, Mailgun,
  Postmark, a self-hosted server...) using STARTTLS or implicit TLS.
* ``disabled``: production default. Nothing is sent; password resets must then
  be done by a manager (User Management) or an administrator.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger("smartpos.email")


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> bool: ...


class ConsoleEmailSender:
    def send(self, to: str, subject: str, body: str) -> bool:
        # Development only: the body may contain a one-time reset link.
        logger.info("DEV EMAIL to=%s subject=%s\n%s", to, subject, body)
        return True


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _message(self, to: str, subject: str, body: str) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self.settings.email_from
        message["To"] = to
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(domain=self.settings.email_from.rsplit("@", 1)[-1].strip("> "))
        message.set_content(body)
        return message

    def send(self, to: str, subject: str, body: str) -> bool:
        s = self.settings
        assert s.smtp_host is not None
        context = ssl.create_default_context()
        try:
            if s.smtp_security == "ssl":
                server: smtplib.SMTP = smtplib.SMTP_SSL(
                    s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds, context=context
                )
            else:
                server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds)
            with server:
                if s.smtp_security == "starttls":
                    server.starttls(context=context)
                if s.smtp_username and s.smtp_password:
                    server.login(s.smtp_username, s.smtp_password)
                server.send_message(self._message(to, subject, body))
        except (OSError, smtplib.SMTPException) as exc:
            # Never log the body: it can contain a password reset link.
            logger.warning(
                "Email to the configured SMTP server failed (%s); message '%s' not sent", type(exc).__name__, subject
            )
            return False
        logger.info("Email '%s' sent via SMTP", subject)
        return True


class DisabledEmailSender:
    def send(self, to: str, subject: str, body: str) -> bool:
        logger.warning("Email delivery is not configured; message '%s' was not sent", subject)
        return False


def get_email_sender() -> EmailSender:
    settings = get_settings()
    backend = settings.effective_email_backend
    if backend == "console":
        return ConsoleEmailSender()
    if backend == "smtp":
        return SmtpEmailSender(settings)
    return DisabledEmailSender()
