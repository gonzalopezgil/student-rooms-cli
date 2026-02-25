"""
notifiers/telegram.py — Direct Telegram Bot API notifier.
No OpenClaw dependency — user provides bot_token + chat_id.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from student_rooms.models.config import TelegramNotifierConfig
from student_rooms.notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class TelegramNotifier(BaseNotifier):
    """Send notifications directly via Telegram Bot API."""

    def __init__(self, config: TelegramNotifierConfig):
        self._config = config

    @property
    def name(self) -> str:
        return "telegram"

    def validate(self) -> Optional[str]:
        if not self._config.bot_token:
            return "Telegram notifier requires 'bot_token' in notifications.telegram config."
        if not self._config.chat_id:
            return "Telegram notifier requires 'chat_id' in notifications.telegram config."
        return None

    def send(self, message: str) -> bool:
        error = self.validate()
        if error:
            logger.error(error)
            return False

        url = f"{TELEGRAM_API}/bot{self._config.bot_token}/sendMessage"
        payload = {
            "chat_id": self._config.chat_id,
            "text": message,
        }
        if self._config.parse_mode:
            payload["parse_mode"] = self._config.parse_mode

        try:
            resp = requests.post(url, json=payload, timeout=15)
            data = resp.json()
            if not data.get("ok"):
                logger.error("Telegram API error: %s", data.get("description", resp.text[:200]))
                return False
            logger.info("Telegram notification sent to chat %s.", self._config.chat_id)
            return True
        except requests.RequestException as exc:
            logger.error("Telegram request failed: %s", exc)
            return False
