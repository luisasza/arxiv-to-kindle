"""
models.py
Dataclasses that represent domain objects across the pipeline.
No logic or behavior lives here.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Paper:
    """A paper extracted from a Substack post."""

    arxiv_id: str
    title: str             # sanitized, safe for use as a filename
    pdf_path: Path | None = None


@dataclass
class SendResult:
    """Outcome of a single email send attempt for one paper."""

    paper: Paper
    success: bool
    error: str | None = None


@dataclass
class RunRecord:
    """
    Persisted entry written to success.json or failures.json.
    One record is written per pipeline run.
    """

    timestamp: str      # yyyy/mm/dd hh:mm  24h  GMT-3
    substack_url: str
    papers: list[dict]  # {"arxiv_id": str, "title": str, "error": str|None}


@dataclass
class AlertRecord:
    """
    Persisted entry written to alerts.json.
    Created when the sent count does not match the extracted count,
    or when a missed run is detected.
    """

    timestamp: str       # yyyy/mm/dd hh:mm  24h  GMT-3
    reason: str
    details: dict        # free-form context depending on alert type
