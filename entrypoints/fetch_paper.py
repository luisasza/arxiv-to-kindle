"""
fetch_paper.py
Manual CLI entrypoint for fetching a single arxiv paper by URL and sending
it to Kindle.

Usage:
  python fetch_paper.py https://arxiv.org/abs/2605.17292

Runs the full pipeline identically to the cron job and fetch_once.py:
all validators, guardrails, deduplication, reconciliation, and logging apply.
A successfully sent paper is marked as processed and will be skipped if the
same URL is passed again.
"""

import argparse
import logging
import sys

import config
from models import Paper, RunRecord, SendResult
from fetcher import fetch_paper_by_arxiv_url
from mailer import send_all
from pipeline import _reconcile
from state import (
    acquire_lock,
    already_processed,
    mark_processed,
    record_run_start,
)
from utils import format_timestamp
from validators import (
    ArxivIDError,
    NetworkError,
    URLError,
    validate_arxiv_url,
    validate_config,
    validate_network,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a single arxiv paper by URL and send it to Kindle.",
    )
    parser.add_argument(
        "url",
        help="Full arxiv URL, e.g. https://arxiv.org/abs/2605.17292",
    )
    return parser.parse_args()


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S",
        handlers=[
            logging.FileHandler(config.RUN_LOG, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _validated_url(raw_url: str) -> str:
    try:
        validate_arxiv_url(raw_url)
        return raw_url
    except URLError as exc:
        print(f"Invalid URL: {exc}", file=sys.stderr)
        sys.exit(1)


def _pre_flight_checks() -> None:
    validate_config()
    try:
        validate_network()
    except NetworkError as exc:
        logging.getLogger(__name__).error("Aborting: %s", exc)
        raise SystemExit(1) from exc


def _derive_post_id(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).path


def _run(url: str) -> None:
    log = logging.getLogger(__name__)
    post_id = _derive_post_id(url)

    if already_processed(post_id):
        log.info("Paper %r already sent to Kindle. Skipping.", post_id)
        return

    record_run_start()

    try:
        paper = fetch_paper_by_arxiv_url(url)
    except (ArxivIDError, ValueError) as exc:
        log.error("Failed to fetch paper: %s", exc)
        sys.exit(1)

    if paper.pdf_path is None:
        log.error("PDF download failed for %s. Aborting.", url)
        sys.exit(1)

    results: list[SendResult] = send_all([paper])
    _reconcile(results, [paper], url)

    if results[0].success:
        mark_processed(post_id)


if __name__ == "__main__":
    _setup_logging()
    args = _parse_args()
    url  = _validated_url(args.url)

    _pre_flight_checks()

    try:
        acquire_lock()
        _run(url)
    finally:
        from state import release_lock
        release_lock()
