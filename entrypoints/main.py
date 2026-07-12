"""
main.py
Cron entrypoint for the kindle_papers pipeline.

Cron schedule (Sunday 20:00 GMT-3 = 23:00 UTC):
  0 23 * * 0 /path/to/.venv/bin/python /path/to/kindle_papers/main.py \
             >> /path/to/kindle_papers/kindle_papers.log 2>&1

This file contains no logic beyond logging setup and delegating to the pipeline.
"""

import logging

import config
from pipeline import run_pipeline


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


if __name__ == "__main__":
    _setup_logging()
    run_pipeline()
