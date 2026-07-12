"""
pipeline.py
Shared orchestration for both the cron job and the manual fetch.

Both main.py and fetch_once.py call run_pipeline(). All guardrails,
reconciliation, and state management live here so neither entrypoint
duplicates logic.
"""

import logging

import alerter
import fetcher
import logger as log_writer
import mailer
import state
from models import Paper, RunRecord, SendResult
from utils import format_timestamp
from validators import NetworkError, validate_config, validate_network

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(specific_url: str | None = None) -> None:
    """
    Execute the full pipeline.

    Args:
        specific_url: If provided, fetch this post directly instead of
                      reading from the RSS feed. Used by fetch_once.py.
    """
    _pre_flight_checks()

    try:
        state.acquire_lock()
        _check_for_missed_runs()
        _execute(specific_url)
    finally:
        state.release_lock()


# ---------------------------------------------------------------------------
# Private: pre-flight
# ---------------------------------------------------------------------------

def _pre_flight_checks() -> None:
    validate_config()
    _check_network()


def _check_network() -> None:
    try:
        validate_network()
    except NetworkError as exc:
        log.error("Aborting: %s", exc)
        raise SystemExit(1) from exc


def _check_for_missed_runs() -> None:
    missed = state.check_for_missed_runs()
    if not missed:
        return

    formatted = [format_timestamp(dt) for dt in missed]
    log.warning("Missed runs detected: %s", formatted)
    alerter.raise_alert(
        reason="Missed scheduled run(s) detected",
        details={"missed_run_timestamps": formatted},
    )


# ---------------------------------------------------------------------------
# Private: main execution
# ---------------------------------------------------------------------------

def _execute(specific_url: str | None) -> None:
    state.record_run_start()

    post_url, post_html = _fetch_post(specific_url)
    post_id             = _derive_post_id(post_url)

    if state.already_processed(post_id):
        log.info("Post %r already processed. Skipping.", post_id)
        return

    papers = _prepare_papers(post_html)
    if not papers:
        log.error("No papers with downloaded PDFs. Aborting send.")
        return

    results = mailer.send_all(papers)
    _reconcile(results, papers, post_url)


def _fetch_post(specific_url: str | None) -> tuple[str, str]:
    if specific_url is not None:
        return fetcher.fetch_specific_post(specific_url)
    return fetcher.fetch_latest_post()


def _derive_post_id(post_url: str) -> str:
    """
    Use the post URL path as a stable, human-readable ID.
    E.g. '/p/top-ai-papers-of-the-week-848' from the full URL.
    """
    from urllib.parse import urlparse
    return urlparse(post_url).path


def _prepare_papers(post_html: str) -> list[Paper]:
    arxiv_ids = fetcher.extract_arxiv_ids(post_html)
    papers    = fetcher.build_papers(arxiv_ids)
    papers    = fetcher.download_pdfs(papers)
    return [p for p in papers if p.pdf_path is not None]


# ---------------------------------------------------------------------------
# Private: reconciliation
# ---------------------------------------------------------------------------

def _reconcile(
    results: list[SendResult],
    papers: list[Paper],
    post_url: str,
) -> None:
    """
    Compare sent count against extracted count. Write appropriate log
    entries and raise an alert if they do not match.
    """
    successes = [r for r in results if r.success]
    failures  = [r for r in results if not r.success]
    expected  = len(papers)
    delivered = len(successes)

    log.info("Reconciliation: %d/%d papers sent.", delivered, expected)

    match delivered == expected:
        case True:
            _handle_full_success(results, post_url)
        case False:
            _handle_partial_failure(results, failures, post_url, expected, delivered)


def _handle_full_success(results: list[SendResult], post_url: str) -> None:
    record = _build_run_record(results, post_url)
    log_writer.log_success(record)
    state.mark_processed(_derive_post_id(post_url))
    log.info("All papers sent. Run marked as complete.")


def _handle_partial_failure(
    results: list[SendResult],
    failures: list[SendResult],
    post_url: str,
    expected: int,
    delivered: int,
) -> None:
    record = _build_run_record(results, post_url)
    log_writer.log_failure(record)

    failed_titles = [r.paper.title for r in failures]
    log.error("Send incomplete: %d/%d failed. %s", len(failures), expected, failed_titles)

    alerter.raise_alert(
        reason="Send count mismatch — not all papers delivered to Kindle",
        details={
            "post_url":       post_url,
            "expected":       expected,
            "delivered":      delivered,
            "failed_papers":  [
                {"title": r.paper.title, "error": r.error}
                for r in failures
            ],
        },
    )


def _build_run_record(results: list[SendResult], post_url: str) -> RunRecord:
    return RunRecord(
        timestamp=format_timestamp(),
        substack_url=post_url,
        papers=[
            {
                "arxiv_id": r.paper.arxiv_id,
                "title":    r.paper.title,
                "error":    r.error,
            }
            for r in results
        ],
    )
