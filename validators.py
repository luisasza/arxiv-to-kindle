"""
validators.py
All validation checks for the pipeline.

Design contract:
- Every public function raises a specific exception on failure.
- No boolean returns — booleans get ignored, exceptions don't.
- No side effects beyond raising.
"""

import re
import logging
from urllib.parse import urlparse

import requests

import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception types
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when a required config value is missing or invalid."""


class NetworkError(Exception):
    """Raised when the network is unreachable."""


class URLError(Exception):
    """Raised when a supplied URL fails allowlist or slug validation."""


class ArxivIDError(Exception):
    """Raised when a string does not match the expected arxiv ID format."""


class PDFError(Exception):
    """Raised when downloaded bytes are not a valid PDF."""


class PaperCountError(Exception):
    """Raised when the number of papers exceeds the hard cap."""


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_ARXIV_ID_RE: re.Pattern = re.compile(r'^\d{4}\.\d{4,5}(v\d+)?$')
_EMAIL_RE: re.Pattern    = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_PDF_MAGIC: bytes        = b"%PDF-"
_PLACEHOLDER_STRINGS: frozenset[str] = frozenset({
    "you@gmail.com",
    "your_app_password",
    "yourdevice@kindle.com",
})


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def validate_config() -> None:
    """
    Verify that all required config values have been filled in and are
    structurally valid. Must be called before any network or file I/O.
    """
    _check_no_placeholders()
    _check_email_format(config.SMTP_USER, "SMTP_USER")
    _check_email_format(config.KINDLE_EMAIL, "KINDLE_EMAIL")
    _check_email_format(config.NOTIFY_EMAIL, "NOTIFY_EMAIL")
    _check_kindle_domain()
    _check_directories_creatable()
    log.debug("Config validation passed.")


def _check_no_placeholders() -> None:
    candidates = {
        "SMTP_USER":     config.SMTP_USER,
        "SMTP_PASSWORD": config.SMTP_PASSWORD,
        "KINDLE_EMAIL":  config.KINDLE_EMAIL,
    }
    for field_name, value in candidates.items():
        if value in _PLACEHOLDER_STRINGS:
            raise ConfigError(
                f"{field_name} still contains its placeholder value. "
                "Edit config.py before running."
            )


def _check_email_format(value: str, field_name: str) -> None:
    if not _EMAIL_RE.match(value):
        raise ConfigError(
            f"{field_name} does not look like a valid email address: {value!r}"
        )


def _check_kindle_domain() -> None:
    if not config.KINDLE_EMAIL.endswith("@kindle.com"):
        raise ConfigError(
            f"KINDLE_EMAIL must end with @kindle.com, got: {config.KINDLE_EMAIL!r}"
        )


def _check_directories_creatable() -> None:
    for directory in (config.DATA_DIR, config.DOWNLOAD_DIR):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigError(
                f"Cannot create required directory {directory}: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Network validation
# ---------------------------------------------------------------------------

def validate_network() -> None:
    """
    Confirm that arxiv.org is reachable before starting any work.
    Raises NetworkError with a clear message if not.
    """
    try:
        response = requests.head(
            config.NETWORK_CHECK_URL,
            timeout=config.NETWORK_CHECK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        log.debug("Network check passed (%s).", config.NETWORK_CHECK_URL)
    except requests.RequestException as exc:
        raise NetworkError(
            f"Network unreachable — {config.NETWORK_CHECK_URL} did not respond. "
            f"Detail: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# URL validation (used by fetch_once.py)
# ---------------------------------------------------------------------------

def validate_substack_url(url: str) -> None:
    """
    Confirm that *url* points to an allowed Substack host and contains
    the expected post path slug. Rejects before any network call is made.
    """
    _check_url_host(url)
    _check_url_slug(url)
    log.debug("Substack URL validation passed: %s", url)


def _check_url_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise URLError(f"URL scheme must be http or https, got: {parsed.scheme!r}")

    if parsed.netloc not in config.ALLOWED_SUBSTACK_HOSTS:
        raise URLError(
            f"URL host {parsed.netloc!r} is not in the allowed list. "
            f"Allowed: {sorted(config.ALLOWED_SUBSTACK_HOSTS)}"
        )


def _check_url_slug(url: str) -> None:
    parsed = urlparse(url)
    if config.EXPECTED_POST_PATH_SLUG not in parsed.path:
        raise URLError(
            f"URL path does not contain expected slug "
            f"{config.EXPECTED_POST_PATH_SLUG!r}. Got path: {parsed.path!r}"
        )


# ---------------------------------------------------------------------------
# URL validation (used by fetch_paper.py)
# ---------------------------------------------------------------------------

_ARXIV_ALLOWED_HOSTS: frozenset[str] = frozenset({
    "arxiv.org",
    "www.arxiv.org",
})

_ARXIV_PATH_RE: re.Pattern = re.compile(
    r'^/(?:abs|pdf)/\d{4}\.\d{4,5}(?:v\d+)?$'
)


def validate_arxiv_url(url: str) -> None:
    """
    Confirm that *url* points to arxiv.org and has a valid abs or pdf path.
    Rejects before any network call is made.
    """
    _check_arxiv_host(url)
    _check_arxiv_path(url)
    log.debug("Arxiv URL validation passed: %s", url)


def _check_arxiv_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise URLError(
            f"URL scheme must be http or https, got: {parsed.scheme!r}"
        )
    if parsed.netloc not in _ARXIV_ALLOWED_HOSTS:
        raise URLError(
            f"URL host {parsed.netloc!r} is not allowed. "
            f"Expected one of: {sorted(_ARXIV_ALLOWED_HOSTS)}"
        )


def _check_arxiv_path(url: str) -> None:
    parsed = urlparse(url)
    if not _ARXIV_PATH_RE.match(parsed.path):
        raise URLError(
            f"URL path does not match expected arxiv pattern "
            f"/abs/YYMM.NNNNN or /pdf/YYMM.NNNNN. Got: {parsed.path!r}"
        )


# ---------------------------------------------------------------------------
# Arxiv ID validation
# ---------------------------------------------------------------------------

def validate_arxiv_id(arxiv_id: str) -> None:
    """
    Confirm that *arxiv_id* matches the standard arxiv ID format.
    Rejects anything a regex mis-extracted from the post HTML.
    """
    if not _ARXIV_ID_RE.match(arxiv_id):
        raise ArxivIDError(
            f"String does not match arxiv ID format YYMM.NNNNN: {arxiv_id!r}"
        )


# ---------------------------------------------------------------------------
# PDF validation
# ---------------------------------------------------------------------------

def validate_pdf_bytes(data: bytes, arxiv_id: str) -> None:
    """
    Confirm that *data* starts with the PDF magic bytes.
    Guards against arxiv serving an HTML error page saved as .pdf.
    """
    if not data.startswith(_PDF_MAGIC):
        raise PDFError(
            f"Downloaded content for {arxiv_id} is not a valid PDF "
            f"(missing %PDF- header). Arxiv may have served an error page."
        )


# ---------------------------------------------------------------------------
# Paper count validation
# ---------------------------------------------------------------------------

def validate_paper_count(count: int) -> None:
    """
    Enforce the hard cap on papers per post.
    Rejects runaway regex matches or unexpectedly large posts.
    """
    if count > config.MAX_PAPERS_PER_POST:
        raise PaperCountError(
            f"Extracted {count} arxiv IDs, which exceeds the hard cap of "
            f"{config.MAX_PAPERS_PER_POST}. Inspect the post manually."
        )
