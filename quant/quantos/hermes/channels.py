"""Delivery channels — console by default, real messengers via env config.

:class:`ConsoleChannel` is the offline default (I6): it prints and captures.
The real channels (Telegram, Discord webhook, SMTP e-mail) are stdlib-only
HTTP/SMTP adapters whose credentials come **exclusively** from environment
variables — no token ever lives in code, and no test ever sends anything.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

__all__ = ["ConsoleChannel", "DiscordChannel", "EmailChannel", "TelegramChannel"]


def _require_env(*names: str) -> list[str]:
    """Read the named environment variables, failing loudly on any gap."""
    values = [os.environ.get(name, "") for name in names]
    missing = [name for name, value in zip(names, values, strict=True) if not value]
    if missing:
        raise ValueError(f"missing environment variables: {', '.join(missing)}")
    return values


class ConsoleChannel:
    """Print alerts to stdout and keep them in ``sent`` (the test channel)."""

    name = "console"

    def __init__(self, echo: bool = True) -> None:
        """
        Args:
            echo: also print each alert (silence with False under test).
        """
        self.echo = echo
        self.sent: list[str] = []

    def send(self, message: str) -> None:
        """Record (and optionally print) one alert."""
        self.sent.append(message)
        if self.echo:
            print(message)


class TelegramChannel:
    """Send alerts to a Telegram chat via the Bot API.

    Credentials come only from ``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_ID``.
    """

    name = "telegram"

    def __init__(self, timeout: float = 10.0) -> None:
        """
        Raises:
            ValueError: when either environment variable is unset.
        """
        self._token, self._chat_id = _require_env("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
        self.timeout = timeout

    def send(self, message: str) -> None:  # pragma: no cover - network, never in tests
        """POST the alert to ``sendMessage``."""
        data = urllib.parse.urlencode({"chat_id": self._chat_id, "text": message}).encode()
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self._token}/sendMessage", data=data, method="POST"
        )
        urllib.request.urlopen(request, timeout=self.timeout).read()


class DiscordChannel:
    """Send alerts to a Discord channel via an incoming webhook.

    The webhook URL comes only from ``DISCORD_WEBHOOK_URL``.
    """

    name = "discord"

    def __init__(self, timeout: float = 10.0) -> None:
        """
        Raises:
            ValueError: when ``DISCORD_WEBHOOK_URL`` is unset.
        """
        (self._url,) = _require_env("DISCORD_WEBHOOK_URL")
        self.timeout = timeout

    def send(self, message: str) -> None:  # pragma: no cover - network, never in tests
        """POST the alert as the webhook's message content."""
        request = urllib.request.Request(
            self._url,
            data=json.dumps({"content": message}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(request, timeout=self.timeout).read()


class EmailChannel:
    """Send alerts by e-mail over SMTP (stdlib ``smtplib``, lazy import).

    Configuration comes only from ``SMTP_HOST``, ``SMTP_USER``,
    ``SMTP_PASSWORD`` and ``EMAIL_TO`` (plus optional ``SMTP_PORT``,
    default 587).
    """

    name = "email"

    def __init__(self, timeout: float = 10.0) -> None:
        """
        Raises:
            ValueError: when any required environment variable is unset.
        """
        self._host, self._user, self._password, self._to = _require_env(
            "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"
        )
        self._port = int(os.environ.get("SMTP_PORT", "587"))
        self.timeout = timeout

    def send(self, message: str) -> None:  # pragma: no cover - network, never in tests
        """Deliver the alert as a plain-text e-mail (STARTTLS)."""
        import smtplib
        from email.message import EmailMessage

        mail = EmailMessage()
        subject = message.splitlines()[0] if message else "[quantos] alert"
        mail["Subject"] = subject
        mail["From"] = self._user
        mail["To"] = self._to
        mail.set_content(message)
        with smtplib.SMTP(self._host, self._port, timeout=self.timeout) as smtp:
            smtp.starttls()
            smtp.login(self._user, self._password)
            smtp.send_message(mail)
