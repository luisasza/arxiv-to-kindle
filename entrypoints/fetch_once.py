"""
fetch_once.py
Manual CLI entrypoint for fetching a specific Substack post by URL.

Usage:
  python fetch_once.py https://nlp.elvissaravia.com/p/top-ai-papers-of-the-week-848

The full pipeline runs identically to the cron job, including all
validators, guardrails, deduplication, and reconciliation.
The only difference is the post source: URL argument instead of RSS feed.
"""

import argparse
import logging
import sys

import config
from pipeline import run_pipeline
from validators import URLError, validate_substack_url


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a specific Top AI Papers post and send to Kindle.",
    )
    parser.add_argument(
        "url",
        help=(
            "Full URL of the Substack post. "
            "Must be from an allowed host and contain the expected path slug."
        ),
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
        validate_substack_url(raw_url)
        return raw_url
    except URLError as exc:
        print(f"Invalid URL: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _setup_logging()
    args    = _parse_args()
    url     = _validated_url(args.url)
    run_pipeline(specific_url=url)
