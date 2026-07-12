"""
state.py
Manages all persistent pipeline state:
  - PID lockfile to prevent overlapping runs.
  - Ledger of processed post IDs to prevent duplicate sends.
  - Last-run timestamp for missed-run detection.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import config
from utils import TZ_GMT_MINUS_3, format_timestamp, now_gmt3

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LockError(Exception):
    """Raised when the pipeline is already running."""


# ---------------------------------------------------------------------------
# Lockfile
# ---------------------------------------------------------------------------

def acquire_lock() -> None:
    """
    Write a PID lockfile. Raises LockError if one already exists
    and the recorded PID is still alive.
    """
    if config.LOCKFILE_PATH.exists():
        _handle_existing_lock()

    config.LOCKFILE_PATH.write_text(str(os.getpid()), encoding="utf-8")
    log.debug("Lock acquired (PID %d).", os.getpid())


def release_lock() -> None:
    """Remove the PID lockfile if it belongs to this process."""
    if not config.LOCKFILE_PATH.exists():
        return

    recorded_pid = _read_lock_pid()
    if recorded_pid == os.getpid():
        config.LOCKFILE_PATH.unlink()
        log.debug("Lock released.")


def _handle_existing_lock() -> None:
    recorded_pid = _read_lock_pid()
    if recorded_pid is not None and _pid_is_alive(recorded_pid):
        raise LockError(
            f"Another pipeline instance is already running (PID {recorded_pid}). "
            "If this is wrong, delete kindle_papers.lock manually."
        )
    log.warning(
        "Stale lockfile found (PID %s no longer alive). Removing.",
        recorded_pid,
    )
    config.LOCKFILE_PATH.unlink()


def _read_lock_pid() -> int | None:
    try:
        return int(config.LOCKFILE_PATH.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Processed-post ledger
# ---------------------------------------------------------------------------

def already_processed(post_id: str) -> bool:
    """
    Return True if *post_id* is in the processed posts ledger.
    Prevents re-sending if a run partially completed then re-ran.
    """
    ledger = _read_ledger()
    return post_id in ledger.get("processed_ids", [])


def mark_processed(post_id: str) -> None:
    """
    Add *post_id* to the processed posts ledger.
    Only called after all sends succeed.
    """
    ledger = _read_ledger()
    processed = ledger.get("processed_ids", [])
    if post_id not in processed:
        processed.append(post_id)
    _write_ledger({"processed_ids": processed})
    log.debug("Post %r marked as processed.", post_id)


def _read_ledger() -> dict:
    path = config.PROCESSED_LOG
    if not path.exists():
        return {"processed_ids": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Could not read processed log (%s). Treating as empty.", exc)
        return {"processed_ids": []}


def _write_ledger(data: dict) -> None:
    _write_json_atomic(data, config.PROCESSED_LOG)


# ---------------------------------------------------------------------------
# Last-run tracking
# ---------------------------------------------------------------------------

def record_run_start() -> None:
    """Persist the current timestamp as the last run start time."""
    _write_json_atomic(
        {"last_run": format_timestamp()},
        config.LAST_RUN_FILE,
    )
    log.debug("Last-run timestamp recorded.")


def check_for_missed_runs() -> list[datetime]:
    """
    Return a list of Sunday datetimes that should have triggered a run
    but have no record in last_run.json.

    A missed run is any Sunday since the last recorded run time that
    has already passed by more than one hour (grace period for late starts).
    """
    last_run = _read_last_run()
    if last_run is None:
        log.info("No last-run record found. Skipping missed-run check.")
        return []

    return _sundays_since(last_run)


def _read_last_run() -> datetime | None:
    path = config.LAST_RUN_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("last_run", "")
        return datetime.strptime(raw, "%Y/%m/%d %H:%M").replace(
            tzinfo=TZ_GMT_MINUS_3
        )
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        log.warning("Could not read last-run file (%s).", exc)
        return None


def _sundays_since(last_run: datetime) -> list[datetime]:
    missed: list[datetime] = []
    now = now_gmt3()
    grace = timedelta(hours=1)
    interval = timedelta(days=config.EXPECTED_CRON_INTERVAL_DAYS)

    candidate = last_run + interval
    while candidate + grace < now:
        missed.append(candidate)
        candidate += interval

    return missed


# ---------------------------------------------------------------------------
# Shared atomic write helper
# ---------------------------------------------------------------------------

def _write_json_atomic(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
