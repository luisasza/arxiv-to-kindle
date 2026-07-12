"""
utils.py
Pure transformation helpers: filename sanitization and timestamp formatting.
No I/O, no side effects, no imports from this project.
"""

import re
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------

TZ_GMT_MINUS_3: timezone = timezone(timedelta(hours=-3))

# ---------------------------------------------------------------------------
# Filename sanitization constants
# ---------------------------------------------------------------------------

# Windows + Unix reserved / problematic characters and control chars 0x00-0x1f
_INVALID_CHARS_RE: re.Pattern = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

# Additional characters unsafe in many filesystems
_EXTRA_UNSAFE_RE: re.Pattern = re.compile(r'[#%&{}$!\'@+`=]')

# Collapse runs of hyphens or spaces produced after substitution
_MULTI_HYPHEN_RE: re.Pattern = re.compile(r'-{2,}')
_MULTI_SPACE_RE: re.Pattern  = re.compile(r' {2,}')

# Windows reserved filenames — reject regardless of extension
_WINDOWS_RESERVED_RE: re.Pattern = re.compile(
    r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)',
    re.IGNORECASE,
)

MAX_FILENAME_LENGTH: int = 180  # headroom for .pdf + filesystem variance


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """
    Return a filename-safe version of *name*, compatible with Windows and Unix.

    Steps applied in order:
    1. Replace all reserved/invalid characters with hyphens.
    2. Replace extra unsafe characters with hyphens.
    3. Collapse consecutive hyphens and spaces.
    4. Strip leading and trailing hyphens and spaces.
    5. Prefix Windows-reserved base names with an underscore.
    6. Truncate to MAX_FILENAME_LENGTH.
    """
    name = _INVALID_CHARS_RE.sub("-", name)
    name = _EXTRA_UNSAFE_RE.sub("-", name)
    name = _MULTI_HYPHEN_RE.sub("-", name)
    name = _MULTI_SPACE_RE.sub(" ", name)
    name = name.strip("- ")

    if _WINDOWS_RESERVED_RE.match(name):
        name = f"_{name}"

    return name[:MAX_FILENAME_LENGTH]


def now_gmt3() -> datetime:
    """Return the current datetime in GMT-3."""
    return datetime.now(TZ_GMT_MINUS_3)


def format_timestamp(dt: datetime | None = None) -> str:
    """
    Return a timestamp string in the format yyyy/mm/dd hh:mm (24h, GMT-3).
    Uses the current time if *dt* is not provided.
    """
    dt = dt or now_gmt3()
    return dt.strftime("%Y/%m/%d %H:%M")
