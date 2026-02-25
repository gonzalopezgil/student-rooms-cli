"""
notifiers/base.py — Abstract notifier + factory.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from student_rooms.models.config import NotificationConfig

logger = logging.getLogger(__name__)


class BaseNotifier(ABC):
    """Abstract notification backend."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def send(self, message: str) -> bool:
        """Send a notification message. Returns True on success."""
        ...

    def validate(self) -> Optional[str]:
        """Return an error string if misconfigured, or None if OK."""
        return None


class StdoutNotifier(BaseNotifier):
    """Default notifier — prints to console."""

    @property
    def name(self) -> str:
        return "stdout"

    def send(self, message: str) -> bool:
        print(f"\n{'='*60}")
        print("📢 NOTIFICATION")
        print(f"{'='*60}")
        print(message)
        print(f"{'='*60}\n")
        return True


def create_notifier(config: NotificationConfig) -> BaseNotifier:
    """Factory: create the appropriate notifier based on config.type."""
    notifier_type = config.type.lower()

    if notifier_type == "stdout":
        return StdoutNotifier()

    elif notifier_type == "webhook":
        from student_rooms.notifiers.webhook import WebhookNotifier
        return WebhookNotifier(config.webhook)

    elif notifier_type == "telegram":
        from student_rooms.notifiers.telegram import TelegramNotifier
        return TelegramNotifier(config.telegram)

    elif notifier_type == "openclaw":
        from student_rooms.notifiers.openclaw import OpenClawNotifier
        return OpenClawNotifier(config.openclaw)

    else:
        logger.warning("Unknown notifier type '%s', falling back to stdout.", notifier_type)
        return StdoutNotifier()
