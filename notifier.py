import logging
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from models.config import NotificationConfig, OpenClawConfig

logger = logging.getLogger(__name__)


def _run(cmd: list[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def send_openclaw_message(message: str, cfg: OpenClawConfig) -> bool:
    if not message:
        return False

    cmd = [
        "openclaw",
        "message",
        "send",
        "--channel",
        cfg.channel,
        "--target",
        str(cfg.target),
        "--message",
        message,
    ]
    code, out, err = _run(cmd)
    if code != 0:
        logger.error("OpenClaw message send failed: %s | %s", out, err)
        return False
    return True


def send_openclaw_agent(message: str, cfg: OpenClawConfig) -> bool:
    cmd = [
        "openclaw",
        "agent",
        "--message",
        message,
        "--deliver",
        "--reply-channel",
        cfg.channel,
        "--reply-to",
        str(cfg.target),
    ]
    code, out, err = _run(cmd)
    if code != 0:
        logger.error("OpenClaw agent send failed: %s | %s", out, err)
        return False
    return True


def create_openclaw_job(job_prompt: str, cfg: OpenClawConfig) -> bool:
    if not job_prompt:
        return False

    run_at = (datetime.now(timezone.utc) + timedelta(seconds=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    job_name = f"yugo-reservation-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    channel = cfg.job_channel or cfg.channel
    target = cfg.job_target or cfg.target

    cmd = [
        "openclaw",
        "cron",
        "add",
        "--name",
        job_name,
        "--at",
        run_at,
        "--session",
        "isolated",
        "--model",
        cfg.job_model,
        "--announce",
        "--channel",
        channel,
        "--to",
        str(target),
        "--timeout-seconds",
        str(cfg.job_timeout_seconds),
        "--message",
        job_prompt,
    ]

    code, out, err = _run(cmd)
    if code != 0:
        logger.error("OpenClaw cron add failed: %s | %s", out, err)
        return False
    logger.info("Created reservation job: %s", out)
    return True


def notify(message: str, config: NotificationConfig, reservation_job_prompt: Optional[str] = None) -> None:
    if not config.openclaw.enabled:
        logger.info("OpenClaw notifications disabled. Message not sent.")
        return

    if config.openclaw.mode == "agent":
        send_openclaw_agent(message, config.openclaw)
    else:
        send_openclaw_message(message, config.openclaw)

    if config.openclaw.create_job_on_match and reservation_job_prompt:
        create_openclaw_job(reservation_job_prompt, config.openclaw)


def validate_notification_config(config: NotificationConfig) -> Optional[str]:
    oc = config.openclaw
    if not oc.enabled:
        return None

    if not oc.target:
        return "OpenClaw notifications enabled but target is missing (notifications.openclaw.target)."

    if oc.mode not in {"message", "agent"}:
        return "notifications.openclaw.mode must be one of: message, agent."

    if oc.reservation_mode not in {"assist", "autobook"}:
        return "notifications.openclaw.reservation_mode must be assist or autobook."

    return None
