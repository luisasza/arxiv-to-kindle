# kindle_papers

Fetches AI papers from the NLP Newsletter Substack and sends them to Kindle.
Supports automated weekly fetching, one-time post fetching, and single paper fetching.

All commands are run from the project root.

---

## First-time setup

```bash
# 1. Clone the repo and enter the project folder
git clone <your-repo-url>
cd kindle_papers

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Gmail app password

1. Go to [myaccount.google.com](https://myaccount.google.com) → Security
2. Enable 2-Step Verification if not already on
3. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
4. Name it `kindle_papers` → click **Create**
5. Copy the 16-character password — you will not see it again

### Kindle approved sender

1. Go to Amazon → Account → **Manage Your Content and Devices**
2. Open **Preferences** → **Personal Document Settings**
3. Under **Approved Personal Document E-mail List**, add your Gmail address

### Credentials

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```
SMTP_USER=your.email@gmail.com
SMTP_PASSWORD=your16charapppassword
KINDLE_EMAIL=yourdevice@kindle.com
NOTIFY_EMAIL=your.email@gmail.com
```

`NOTIFY_EMAIL` is where failure alert emails are sent — can be the same as `SMTP_USER`.

Never commit `.env`.

### config.py

The only value you may want to change before first run:

```python
DOWNLOAD_DIR: Path = Path("~/Documents/kindle_papers").expanduser()
```

Set this to wherever you want PDFs saved locally.

---

<details>
<summary><strong>Fetch on a schedule — automated every Sunday</strong></summary>

<br>

The cron schedule targets **Sunday 23:00 UTC (20:00 GMT-3)**.

```bash
crontab -e
```

Add these two lines, replacing paths with your actual paths:

```
50 22 * * 0 /usr/sbin/rtcwake -m no -t $(date -d 'next Sunday 23:00 UTC' +%s)
0 23 * * 0 /path/to/kindle_papers/.venv/bin/python -m entrypoints.main >> /path/to/kindle_papers/kindle_papers.log 2>&1
```

The first line wakes your machine from sleep at 22:50 UTC, 10 minutes before the run.
The second line runs the pipeline.

The cron line points directly to the venv Python — no need to activate it first.
Your machine does not need to be unlocked, only on and not suspended.

</details>

---

<details>
<summary><strong>Fetch once — a specific Substack post</strong></summary>

<br>

Pass the URL of any Top AI Papers of the Week post:

```bash
source .venv/bin/activate
python -m entrypoints.fetch_once https://nlp.elvissaravia.com/p/top-ai-papers-of-the-week-848
```

**URL requirements:**
- Host must be `nlp.elvissaravia.com`, `nlpnews.substack.com`, or `open.substack.com`
- Path must contain `top-ai-papers-of-the-week`

Any other URL is rejected before a network call is made.

If the post was already successfully sent in a previous run, it will be skipped.

</details>

---

<details>
<summary><strong>Fetch once — a single arxiv paper</strong></summary>

<br>

Pass a direct arxiv abstract URL:

```bash
source .venv/bin/activate
python -m entrypoints.fetch_paper https://arxiv.org/abs/2605.17292
```

**URL requirements:**
- Host must be `arxiv.org` or `www.arxiv.org`
- Path must match `/abs/YYMM.NNNNN` or `/pdf/YYMM.NNNNN`

If the paper was already successfully sent in a previous run, it will be skipped.

</details>

---

<details>
<summary><strong>Technical reference</strong></summary>

<br>

### Project structure

```
kindle_papers/
├── entrypoints/
│   ├── __init__.py
│   ├── main.py           # Cron entrypoint
│   ├── fetch_once.py     # Manual entrypoint — specific Substack post by URL
│   └── fetch_paper.py    # Manual entrypoint — single arxiv paper by URL
├── pipeline.py           # Shared orchestration used by all entrypoints
├── config.py             # All settings and hard limits
├── models.py             # Dataclasses: Paper, SendResult, RunRecord, AlertRecord
├── fetcher.py            # RSS parsing, arxiv scraping, PDF download
├── mailer.py             # SMTP send logic with batch and individual retry
├── validators.py         # Pre-flight and mid-flight checks — raises on failure
├── logger.py             # Atomic JSON writes to success, failure, alert logs
├── state.py              # Lockfile, processed-post ledger, missed-run detection
├── alerter.py            # Writes alert files and sends alert emails
├── utils.py              # Filename sanitization and timestamp formatting
├── requirements.txt
├── .env                  # Credentials — never committed
├── .env.example          # Credentials template — committed
└── data/                 # Created automatically on first run
    ├── success.json          # One record per fully successful run
    ├── failures.json         # One record per run with send failures
    ├── alerts.json           # Missed runs, count mismatches, critical errors
    ├── processed_posts.json  # Ledger of post IDs already sent — prevents dupes
    └── last_run.json         # Timestamp of last run start
```

### Log files

All logs are in `data/`. Each JSON file is a list of records, newest last.

| File | Written when |
|---|---|
| `success.json` | All papers in a run were sent successfully |
| `failures.json` | One or more papers failed after individual retry |
| `alerts.json` | Sent count ≠ extracted count, or a missed run is detected |
| `kindle_papers.log` | Every run — full timestamped stdout and stderr |

### Guardrails

| Guardrail | What it prevents |
|---|---|
| PID lockfile | Two runs overlapping and sending duplicates |
| Processed-post ledger | Re-sending the same post or paper on a retry or manual re-run |
| Config validation at startup | Placeholder credentials reaching the network |
| Network check at startup | Silent failure when Wi-Fi isn't up yet |
| URL allowlist (Substack) | Wrong post URL passed to `fetch_once` by human error |
| URL allowlist (arxiv) | Non-arxiv URL passed to `fetch_paper` by human error |
| Arxiv ID format validation | Regex mis-extraction from post HTML sending garbage to download |
| PDF magic-byte check | Arxiv serving an HTML error page saved as `.pdf` |
| PDF size cap (50 MB) | Runaway download from a bad or unexpected URL |
| Paper count cap (10 per post) | Regex runaway or unexpectedly large posts |
| Request timeouts everywhere | Process hanging indefinitely on a dead network mid-run |
| Stale lockfile detection | Leftover `.lock` file from a hard crash blocking all future runs |
| Existing PDF re-validation | Reusing a corrupted file from an interrupted run |
| Missed-run detection | Machine was off on Sunday — surfaces silently skipped weeks |
| Sent count vs extracted count reconciliation | Partial send passing as success |
| Atomic JSON writes (temp + rename) | Log file corruption if the process dies mid-write |
| Alert file written before alert email | Alert email failure hiding the alert entirely |

### Retry contract

1. Papers are sent in batches of 5.
2. If a batch fails, the pipeline waits 5 minutes then retries each paper in that batch individually, exactly once.
3. Papers that still fail after individual retry are logged to `failures.json` and trigger an alert email.
4. No further retries. The post is not marked as processed if any paper failed.

### Hard limits

Defined in `config.py`. Do not raise these without understanding the consequence.

| Constant | Default | Purpose |
|---|---|---|
| `MAX_PAPERS_PER_POST` | 10 | Hard cap on arxiv IDs extracted per post |
| `MAX_PDF_SIZE_BYTES` | 50 MB | Enforced during streaming, not after download |
| `BATCH_SIZE` | 5 | Papers per Kindle email |
| `REQUEST_TIMEOUT_SECONDS` | 60 | Applied to every network call |
| `ARXIV_DELAY_SECONDS` | 3 | Delay between consecutive arxiv PDF downloads |
| `BATCH_RETRY_DELAY_SECONDS` | 300 | Wait before individual retries after a batch failure |

</details>
