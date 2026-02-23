import logging
from typing import Optional

import requests

from models.config import NotificationConfig

API_PUSHOVER = "https://api.pushover.net/1/messages.json"

logger = logging.getLogger(__name__)


def send_pushover(message: str, api_token: str, user_key: str) -> bool:
    if not message:
        return False
    response = requests.post(
        API_PUSHOVER,
        data={
            "token": api_token,
            "user": user_key,
            "message": message,
        },
        timeout=30,
    )
    if response.status_code != 200:
        logger.error("Error sending Pushover notification: %s", response.text)
        return False
    return True


def notify(message: str, config: NotificationConfig) -> None:
    if config.pushover.enabled and config.pushover.api_token and config.pushover.user_key:
        send_pushover(message, config.pushover.api_token, config.pushover.user_key)

    if config.openclaw.enabled:
        logger.info("OpenClaw trigger placeholder: %s", config.openclaw.endpoint or "(no endpoint)")


def validate_notification_config(config: NotificationConfig) -> Optional[str]:
    if config.pushover.enabled:
        if not config.pushover.api_token or not config.pushover.user_key:
            return "Pushover enabled but api_token/user_key missing."
    return None
