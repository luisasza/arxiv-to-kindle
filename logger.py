"""
logger.py
Writes run records to success.json, failures.json, and alerts.json.

Design:
- Each write is atomic: write to a temp file, then rename.
  This prevents corruption if the process dies mid-write.
- Each JSON file is a list of records, newest last.
- No reads from these files happen here — logger only appends.
"""

import json
import logging
import tempfile
from dataclasses import asdict
from pathlib import Path

from models import AlertRecord, RunRecord

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def log_success(record: RunRecord) -> None:
    """Append *record* to the success log."""
    _append_record(record, _success_log_path())
    log.info("Run record written to success log.")


def log_failure(record: RunRecord) -> None:
    """Append *record* to the failure log."""
    _append_record(record, _failure_log_path())
    log.info("Run record written to failure log.")


def log_alert(record: AlertRecord) -> None:
    """Append *record* to the alerts log."""
    _append_record(record, _alerts_log_path())
    log.info("Alert record written to alerts log.")


# ---------------------------------------------------------------------------
# Path accessors — deferred import avoids circular dependency at module load
# ---------------------------------------------------------------------------

def _success_log_path() -> Path:
    import config
    return config.SUCCESS_LOG


def _failure_log_path() -> Path:
    import config
    return config.FAILURE_LOG


def _alerts_log_path() -> Path:
    import config
    return config.ALERTS_LOG


# ---------------------------------------------------------------------------
# Core write logic
# ---------------------------------------------------------------------------

def _append_record(record: RunRecord | AlertRecord, path: Path) -> None:
    """
    Atomically append *record* (as a dict) to the JSON list at *path*.
    Creates the file with an empty list if it does not exist.
    """
    existing = _read_existing(path)
    existing.append(asdict(record))
    _write_atomic(existing, path)


def _read_existing(path: Path) -> list[dict]:
    """Return the current list from *path*, or an empty list if missing."""
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        return json.loads(content)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning(
            "Could not read existing log at %s (%s). Starting fresh list.",
            path,
            exc,
        )
        return []


def _write_atomic(records: list[dict], path: Path) -> None:
    """
    Write *records* to *path* atomically via a sibling temp file and rename.
    Raises OSError if the write or rename fails.
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=parent,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(records, tmp, indent=2, ensure_ascii=False)
        tmp_path = Path(tmp.name)

    tmp_path.replace(path)
