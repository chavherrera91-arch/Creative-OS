"""Hermes: the read-only communications agent (module 24, M8)."""

from quantos.hermes.agent import Hermes, event_from_decision
from quantos.hermes.base import Channel, HermesAgent, HermesEvent, Notifier, format_alert
from quantos.hermes.channels import ConsoleChannel, DiscordChannel, EmailChannel, TelegramChannel

__all__ = [
    "Channel",
    "ConsoleChannel",
    "DiscordChannel",
    "EmailChannel",
    "Hermes",
    "HermesAgent",
    "HermesEvent",
    "Notifier",
    "TelegramChannel",
    "event_from_decision",
    "format_alert",
]
