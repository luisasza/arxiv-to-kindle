"""
config.py
All user-configurable settings and hard limits for the kindle_papers pipeline.
No logic lives here. Import order: this file imports nothing from the project.
"""

import os
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path

# ---------------------------------------------------------------------------
# Substack
# ---------------------------------------------------------------------------

SUBSTACK_RSS: str = "https://nlpnews.substack.com/feed"
POST_TITLE_SLUG: str = "top ai papers of the week"  # case-insensitive match

ALLOWED_SUBSTACK_HOSTS: frozenset[str] = frozenset({
    "nlp.elvissaravia.com",
    "nlpnews.substack.com",
    "open.substack.com",
})

EXPECTED_POST_PATH_SLUG: str = "top-ai-papers-of-the-week"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR: Path = Path(__file__).parent
DATA_DIR: Path = BASE_DIR / "data"
DOWNLOAD_DIR: Path = Path("~/Documents/kindle_papers").expanduser()

SUCCESS_LOG: Path  = DATA_DIR / "success.json"
FAILURE_LOG: Path  = DATA_DIR / "failures.json"
ALERTS_LOG: Path   = DATA_DIR / "alerts.json"
PROCESSED_LOG: Path = DATA_DIR / "processed_posts.json"
LAST_RUN_FILE: Path = DATA_DIR / "last_run.json"
LOCKFILE_PATH: Path = BASE_DIR / "kindle_papers.lock"
RUN_LOG: Path      = BASE_DIR / "kindle_papers.log"

# ---------------------------------------------------------------------------
# SMTP
# ---------------------------------------------------------------------------

SMTP_HOST: str     = "smtp.gmail.com"
SMTP_PORT: int     = 587
SMTP_USER: str     = os.getenv("SMTP_USER", "")          # must be on Kindle approved list
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")       # Gmail 16-char app password
KINDLE_EMAIL: str  = os.getenv("KINDLE_EMAIL", "")
NOTIFY_EMAIL: str  = os.getenv("NOTIFY_EMAIL", "")           # receives failure alerts

# ---------------------------------------------------------------------------
# Hard limits — do not raise these without understanding the consequences
# ---------------------------------------------------------------------------

MAX_PAPERS_PER_POST: int     = 10
MAX_PDF_SIZE_BYTES: int      = 50 * 1024 * 1024   # 50 MB
BATCH_SIZE: int              = 5
REQUEST_TIMEOUT_SECONDS: int = 60
ARXIV_DELAY_SECONDS: int     = 3    # polite delay between PDF downloads
BATCH_RETRY_DELAY_SECONDS: int = 300  # 5 min before individual retries

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

NETWORK_CHECK_URL: str             = "https://arxiv.org"
NETWORK_CHECK_TIMEOUT_SECONDS: int = 10

# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

EXPECTED_CRON_INTERVAL_DAYS: int = 7
