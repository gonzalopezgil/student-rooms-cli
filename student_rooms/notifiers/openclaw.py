"""
notifiers/openclaw.py — OpenClaw CLI integration (optional).
Requires the `openclaw` CLI to be installed and configured.
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from student_rooms.models.config import OpenClawNotifierConfig
from student_rooms.notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)


def _run(cmd: list[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


class OpenClawNotifier(BaseNotifier):
    """Send notifications via OpenClaw CLI (message or agent mode)."""

    def __init__(self, config: OpenClawNotifierConfig):
        self._config = config

    @property
    def name(self) -> str:
        return "openclaw"

    def validate(self) -> Optional[str]:
        if not self._config.target:
            return "OpenClaw notifier requires 'target' in notifications.openclaw config."
        if self._config.mode not in {"message", "agent"}:
            return "notifications.openclaw.mode must be 'message' or 'agent'."
        return None

    def send(self, message: str) -> bool:
        error = self.validate()
        if error:
            logger.error(error)
            return False

        if self._config.mode == "agent":
            return self._send_agent(message)
        return self._send_message(message)

    def _send_message(self, message: str) -> bool:
        cmd = [
            "openclaw", "message", "send",
            "--channel", self._config.channel,
            "--target", str(self._config.target),
            "--message", message,
        ]
        code, out, err = _run(cmd)
        if code != 0:
            logger.error("OpenClaw message send failed: %s | %s", out, err)
            return False
        return True

    def _send_agent(self, message: str) -> bool:
        cmd = [
            "openclaw", "agent",
            "--message", message,
            "--deliver",
            "--reply-channel", self._config.channel,
            "--reply-to", str(self._config.target),
        ]
        code, out, err = _run(cmd)
        if code != 0:
            logger.error("OpenClaw agent send failed: %s | %s", out, err)
            return False
        return True

    def create_job(self, job_prompt: str) -> bool:
        """Create an OpenClaw cron job (e.g. for reservation assist)."""
        if not job_prompt:
            return False

        run_at = (
            (datetime.now(timezone.utc) + timedelta(seconds=5))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        job_name = f"student-rooms-reservation-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        channel = self._config.job_channel or self._config.channel
        target = self._config.job_target or self._config.target

        cmd = [
            "openclaw", "cron", "add",
            "--name", job_name,
            "--at", run_at,
            "--session", "isolated",
            "--model", self._config.job_model,
            "--announce",
            "--channel", channel,
            "--to", str(target),
            "--timeout-seconds", str(self._config.job_timeout_seconds),
            "--message", job_prompt,
        ]

        code, out, err = _run(cmd)
        if code != 0:
            logger.error("OpenClaw cron add failed: %s | %s", out, err)
            return False
        logger.info("Created reservation job: %s", out)
        return True
