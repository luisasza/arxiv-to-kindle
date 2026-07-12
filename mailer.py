"""
mailer.py
Responsible for sending papers to the Kindle email address.

Retry contract (per spec):
  1. Send papers in batches of BATCH_SIZE.
  2. If a batch fails: wait BATCH_RETRY_DELAY_SECONDS, then retry each
     paper in that batch individually, exactly once.
  3. Individual retries that still fail are logged — no further retries.
"""

import logging
import smtplib
import time
from email.message import EmailMessage

import config
from models import Paper, SendResult

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def send_all(papers: list[Paper]) -> list[SendResult]:
    """
    Send all papers to Kindle in batches, with individual retry on batch failure.
    Returns one SendResult per paper.
    """
    results: list[SendResult] = []
    batches = _chunk(papers, config.BATCH_SIZE)

    for batch_number, batch in enumerate(batches, start=1):
        batch_results = _process_batch(batch, batch_number)
        results.extend(batch_results)

    return results


# ---------------------------------------------------------------------------
# Private: batch processing
# ---------------------------------------------------------------------------

def _process_batch(batch: list[Paper], batch_number: int) -> list[SendResult]:
    log.info(
        "Sending batch %d (%d papers): %s",
        batch_number,
        len(batch),
        [p.title for p in batch],
    )
    batch_success = _send_batch(batch, batch_number)

    if batch_success:
        return [SendResult(paper=p, success=True) for p in batch]

    return _retry_batch_individually(batch, batch_number)


def _retry_batch_individually(
    batch: list[Paper],
    batch_number: int,
) -> list[SendResult]:
    log.warning(
        "Batch %d failed. Waiting %ds before individual retries.",
        batch_number,
        config.BATCH_RETRY_DELAY_SECONDS,
    )
    time.sleep(config.BATCH_RETRY_DELAY_SECONDS)
    return [_send_single_with_result(paper) for paper in batch]


# ---------------------------------------------------------------------------
# Private: send operations
# ---------------------------------------------------------------------------

def _send_batch(batch: list[Paper], batch_number: int) -> bool:
    """
    Attempt to send all papers in *batch* as one email.
    Returns True on success, False on any failure.
    """
    msg = _build_message_with_attachments(batch)
    try:
        _send_via_smtp(msg)
        log.info("Batch %d sent successfully.", batch_number)
        return True
    except smtplib.SMTPException as exc:
        log.error("Batch %d SMTP error: %s", batch_number, exc)
        return False
    except OSError as exc:
        log.error("Batch %d network error: %s", batch_number, exc)
        return False


def _send_single_with_result(paper: Paper) -> SendResult:
    """
    Attempt to send one paper as an individual email, exactly once.
    Returns a SendResult reflecting success or failure.
    """
    log.info("Retrying individually: %s", paper.title)
    msg = _build_message_with_attachments([paper])
    try:
        _send_via_smtp(msg)
        log.info("Individual send succeeded: %s", paper.title)
        return SendResult(paper=paper, success=True)
    except smtplib.SMTPException as exc:
        log.error("Individual send failed for %s: %s", paper.title, exc)
        return SendResult(paper=paper, success=False, error=str(exc))
    except OSError as exc:
        log.error("Network error for %s: %s", paper.title, exc)
        return SendResult(paper=paper, success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Private: message construction
# ---------------------------------------------------------------------------

def _build_message_with_attachments(papers: list[Paper]) -> EmailMessage:
    msg = EmailMessage()
    msg["From"]    = config.SMTP_USER
    msg["To"]      = config.KINDLE_EMAIL
    msg["Subject"] = "Convert"

    for paper in papers:
        _attach_pdf(msg, paper)

    return msg


def _attach_pdf(msg: EmailMessage, paper: Paper) -> None:
    if paper.pdf_path is None or not paper.pdf_path.exists():
        log.warning("PDF path missing for %s — skipping attachment.", paper.title)
        return

    with open(paper.pdf_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="pdf",
            filename=f"{paper.title}.pdf",
        )


# ---------------------------------------------------------------------------
# Private: SMTP transport
# ---------------------------------------------------------------------------

def _send_via_smtp(msg: EmailMessage) -> None:
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)


# ---------------------------------------------------------------------------
# Private: utility
# ---------------------------------------------------------------------------

def _chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]
