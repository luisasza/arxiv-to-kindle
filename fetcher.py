"""
fetcher.py
Responsible for turning a Substack post into Paper objects with PDFs on disk.

No email, no state writes, no alerts live here.
"""

import logging
import re
import time
from pathlib import Path

import feedparser
import requests

import config
from models import Paper
from utils import sanitize_filename
from validators import (
    ArxivIDError,
    PDFError,
    validate_arxiv_id,
    validate_paper_count,
    validate_pdf_bytes,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_ARXIV_URL_RE: re.Pattern = re.compile(
    r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)'
)

_ARXIV_TITLE_RE: re.Pattern = re.compile(
    r'<h1 class="title mathjax">\s*<span[^>]*>Title:</span>\s*(.+?)\s*</h1>',
    re.DOTALL,
)

_WHITESPACE_RE: re.Pattern = re.compile(r'\s+')


# ---------------------------------------------------------------------------
# Public: RSS path (cron entry point)
# ---------------------------------------------------------------------------

def fetch_latest_post() -> tuple[str, str]:
    """
    Parse the Substack RSS feed and return (post_url, post_html) for
    the most recent post whose title matches POST_TITLE_SLUG.

    Raises ValueError if no matching post is found.
    """
    log.info("Fetching RSS feed: %s", config.SUBSTACK_RSS)
    feed = feedparser.parse(config.SUBSTACK_RSS)
    _check_feed_parse_errors(feed)

    for entry in feed.entries:
        if _title_matches(entry.get("title", "")):
            log.info("Matched post: %s", entry.title)
            return entry.link, _extract_entry_html(entry)

    raise ValueError(
        f"No post matching {config.POST_TITLE_SLUG!r} found in RSS feed."
    )


# ---------------------------------------------------------------------------
# Public: specific URL path (fetch_once entry point)
# ---------------------------------------------------------------------------

def fetch_specific_post(url: str) -> tuple[str, str]:
    """
    Fetch a specific Substack post by URL and return (url, html).
    Raises requests.RequestException on network or HTTP errors.
    """
    log.info("Fetching specific post: %s", url)
    response = requests.get(url, timeout=config.REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return url, response.text


# ---------------------------------------------------------------------------
# Public: single arxiv paper path (fetch_paper entry point)
# ---------------------------------------------------------------------------

def fetch_paper_by_arxiv_url(url: str) -> Paper:
    """
    Fetch a single paper from a direct arxiv URL.
    Extracts the arxiv ID, fetches the title, downloads the PDF,
    and returns a Paper with pdf_path set.

    Raises ArxivIDError if the ID cannot be extracted from the URL.
    """
    arxiv_id = _extract_arxiv_id_from_url(url)
    validate_arxiv_id(arxiv_id)
    paper = _build_single_paper(arxiv_id)
    _download_single_pdf(paper)
    return paper


def _extract_arxiv_id_from_url(url: str) -> str:
    match = _ARXIV_URL_RE.search(url)
    if not match:
        raise ArxivIDError(
            f"Could not extract a valid arxiv ID from URL: {url!r}"
        )
    return match.group(1)


# ---------------------------------------------------------------------------
# Public: arxiv ID extraction
# ---------------------------------------------------------------------------

def extract_arxiv_ids(html: str) -> list[str]:
    """
    Extract unique arxiv IDs from post HTML, preserving order.
    Validates each ID and enforces the hard paper count cap.

    Raises PaperCountError if count exceeds MAX_PAPERS_PER_POST.
    Invalid IDs are skipped with a warning rather than failing the run.
    """
    raw_ids = list(dict.fromkeys(_ARXIV_URL_RE.findall(html)))
    valid_ids = _filter_valid_ids(raw_ids)
    validate_paper_count(len(valid_ids))
    log.info("Extracted %d valid arxiv IDs.", len(valid_ids))
    return valid_ids


# ---------------------------------------------------------------------------
# Public: paper construction and PDF download
# ---------------------------------------------------------------------------

def build_papers(arxiv_ids: list[str]) -> list[Paper]:
    """
    Fetch a title for each arxiv ID and return a list of Paper objects.
    Title fetch failures fall back to the arxiv ID as the title.
    """
    return [_build_single_paper(arxiv_id) for arxiv_id in arxiv_ids]


def download_pdfs(papers: list[Paper]) -> list[Paper]:
    """
    Download PDFs for each Paper in *papers*, respecting ARXIV_DELAY_SECONDS
    between requests. Returns the same list with pdf_path set on success.

    Papers that fail to download have pdf_path left as None.
    """
    for index, paper in enumerate(papers):
        _download_single_pdf(paper)
        if index < len(papers) - 1:
            time.sleep(config.ARXIV_DELAY_SECONDS)
    return papers


# ---------------------------------------------------------------------------
# Private: feed helpers
# ---------------------------------------------------------------------------

def _check_feed_parse_errors(feed: feedparser.FeedParserDict) -> None:
    if feed.bozo:
        raise ValueError(
            f"RSS feed parse error: {feed.bozo_exception}"
        )


def _title_matches(title: str) -> bool:
    return config.POST_TITLE_SLUG.lower() in title.lower()


def _extract_entry_html(entry: feedparser.FeedParserDict) -> str:
    if hasattr(entry, "content"):
        return entry.content[0].value
    return entry.get("summary", "")


# ---------------------------------------------------------------------------
# Private: ID validation
# ---------------------------------------------------------------------------

def _filter_valid_ids(raw_ids: list[str]) -> list[str]:
    valid = []
    for arxiv_id in raw_ids:
        try:
            validate_arxiv_id(arxiv_id)
            valid.append(arxiv_id)
        except ArxivIDError as exc:
            log.warning("Skipping invalid arxiv ID: %s", exc)
    return valid


# ---------------------------------------------------------------------------
# Private: paper construction
# ---------------------------------------------------------------------------

def _build_single_paper(arxiv_id: str) -> Paper:
    title = _fetch_arxiv_title(arxiv_id)
    return Paper(arxiv_id=arxiv_id, title=title)


def _fetch_arxiv_title(arxiv_id: str) -> str:
    """
    Scrape the arxiv abstract page for the paper title.
    Returns *arxiv_id* as a fallback if the title cannot be extracted.
    """
    url = f"https://arxiv.org/abs/{arxiv_id}"
    try:
        response = requests.get(url, timeout=config.REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return _parse_title_from_html(response.text, arxiv_id)
    except requests.RequestException as exc:
        log.warning("Could not fetch title for %s (%s). Using ID as title.", arxiv_id, exc)
        return arxiv_id


def _parse_title_from_html(html: str, fallback: str) -> str:
    match = _ARXIV_TITLE_RE.search(html)
    if not match:
        log.warning("Title not found in arxiv page for %s. Using ID as title.", fallback)
        return fallback
    raw_title = _WHITESPACE_RE.sub(" ", match.group(1)).strip()
    return sanitize_filename(raw_title)


# ---------------------------------------------------------------------------
# Private: PDF download
# ---------------------------------------------------------------------------

def _download_single_pdf(paper: Paper) -> None:
    dest = _pdf_destination(paper)

    if _valid_pdf_already_exists(dest, paper.arxiv_id):
        paper.pdf_path = dest
        return

    log.info("Downloading %s → %s", paper.arxiv_id, dest.name)
    try:
        data = _stream_pdf(paper.arxiv_id)
        validate_pdf_bytes(data, paper.arxiv_id)
        dest.write_bytes(data)
        paper.pdf_path = dest
        log.info("Saved: %s", dest.name)
    except (requests.RequestException, PDFError, OSError) as exc:
        log.error("Failed to download %s: %s", paper.arxiv_id, exc)


def _pdf_destination(paper: Paper) -> Path:
    config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return config.DOWNLOAD_DIR / f"{paper.title}.pdf"


def _valid_pdf_already_exists(dest: Path, arxiv_id: str) -> bool:
    if not dest.exists():
        return False
    try:
        header = dest.read_bytes()[:5]
        if header == b"%PDF-":
            log.info("Already downloaded (valid PDF): %s", dest.name)
            return True
        log.warning(
            "Existing file for %s failed magic-byte check. Re-downloading.",
            arxiv_id,
        )
        return False
    except OSError as exc:
        log.warning("Could not read existing file for %s (%s). Re-downloading.", arxiv_id, exc)
        return False


def _stream_pdf(arxiv_id: str) -> bytes:
    """
    Stream the PDF from arxiv, enforcing the MAX_PDF_SIZE_BYTES hard limit.
    Raises ValueError if the download exceeds the limit.
    Raises requests.RequestException on HTTP/network errors.
    """
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    chunks: list[bytes] = []
    total = 0

    with requests.get(
        url,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        stream=True,
    ) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > config.MAX_PDF_SIZE_BYTES:
                raise ValueError(
                    f"PDF for {arxiv_id} exceeds size limit of "
                    f"{config.MAX_PDF_SIZE_BYTES // (1024 * 1024)} MB. "
                    "Aborting download."
                )
            chunks.append(chunk)

    return b"".join(chunks)
