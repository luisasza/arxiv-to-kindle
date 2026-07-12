"""
alerter.py
Raises loud alarms when the pipeline detects an anomaly.

Design:
- Always writes to alerts.json first, then attempts the email.
- If the alert email fails, the file record still exists.
- Never raises from raise_alert itself — alerting must not crash the caller.
"""

import logging
import smtplib
from email.message import EmailMessage

import config
import logger as log_writer
from models import AlertRecord
from utils import format_timestamp

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def raise_alert(reason: str, details: dict) -> None:
    """
    Persist an alert record and attempt to notify via email.
    Safe to call from any point in the pipeline — never raises.
    """
    record = AlertRecord(
        timestamp=format_timestamp(),
        reason=reason,
        details=details,
    )
    _persist_alert(record)
    _send_alert_email(record)


# ---------------------------------------------------------------------------
# Alert persistence
# ---------------------------------------------------------------------------

def _persist_alert(record: AlertRecord) -> None:
    try:
        log_writer.log_alert(record)
    except OSError as exc:
        log.error(
            "CRITICAL: Could not write alert to disk. Reason: %s. "
            "Alert details: %s — %s",
            exc,
            record.reason,
            record.details,
        )


# ---------------------------------------------------------------------------
# Alert email
# ---------------------------------------------------------------------------

def _send_alert_email(record: AlertRecord) -> None:
    msg = _build_alert_message(record)
    try:
        _send_via_smtp(msg)
        log.info("Alert email sent to %s.", config.NOTIFY_EMAIL)
    except smtplib.SMTPException as exc:
        log.error(
            "Alert email failed to send (%s). "
            "Check alerts.json for the persisted record.",
            exc,
        )
    except OSError as exc:
        log.error(
            "Network error while sending alert email (%s). "
            "Check alerts.json for the persisted record.",
            exc,
        )


def _build_alert_message(record: AlertRecord) -> EmailMessage:
    msg = EmailMessage()
    msg["From"]    = config.SMTP_USER
    msg["To"]      = config.NOTIFY_EMAIL
    msg["Subject"] = f"[kindle_papers] Alert: {record.reason}"
    msg.set_content(_format_alert_body(record))
    return msg


def _format_alert_body(record: AlertRecord) -> str:
    lines = [
        f"Timestamp : {record.timestamp}",
        f"Reason    : {record.reason}",
        "",
        "Details:",
    ]
    for key, value in record.details.items():
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def _send_via_smtp(msg: EmailMessage) -> None:
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)
