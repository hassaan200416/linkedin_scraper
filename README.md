# LinkedIn Profile Scraper

A fully automated LinkedIn scraper built with Python and Playwright. Given a search keyword it logs into LinkedIn, collects profile URLs from the search results, visits each profile, extracts structured data, persists everything to a Supabase PostgreSQL database, and exports a flat CSV — with no manual steps after the initial setup.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Architecture](#architecture)
3. [Module Reference](#module-reference)
4. [Prerequisites](#prerequisites)
5. [Setup](#setup)
6. [Supabase Database Schema](#supabase-database-schema)
7. [Environment Variables](#environment-variables)
8. [Running the Scraper](#running-the-scraper)
9. [Output](#output)
10. [Configuration Reference](#configuration-reference)
11. [How Re-scraping Works](#how-re-scraping-works)
12. [Known Limitations](#known-limitations)
13. [Troubleshooting](#troubleshooting)

---

## What It Does

1. Launches a real Chromium browser (with stealth patches to avoid bot detection)
2. Logs into LinkedIn using your credentials, reusing saved session cookies on subsequent runs
3. Searches LinkedIn People for your keyword across multiple pages
4. Visits each profile and its `/recent-activity/all/` page
5. Extracts: full name, job title, location, about/bio, all work experience, up to 3 recent posts, email (if public)
6. Saves each profile to Supabase immediately after scraping (crash-safe)
7. Exports a flat CSV of all profiles in the database at the end of the run

---

## Architecture

```
User Input (keyword, pages)
        │
        ▼
   main.py  ──orchestrates──►  auth.py          login + cookie reuse
                           ►  search.py         collect profile URLs
                           ►  profile_scraper.py navigate + scroll each profile
                                    └──────────► parser.py   HTML → structured data
                           ►  database.py        persist to Supabase/PostgreSQL
                           ►  exporter.py        dump DB → CSV

   logger.py  ──shared by all modules── terminal + daily log file
```

**Key design decisions:**

- **Save-on-scrape:** each profile is written to the database immediately after it is scraped, not batched at the end. A crash mid-run does not lose already-scraped data.
- **Upsert by URL:** re-running the same keyword refreshes existing profiles rather than creating duplicates. Experience and posts are fully replaced on each re-scrape.
- **Separate activity page:** LinkedIn does not render posts on the main profile page. The scraper visits `/recent-activity/all/` as a separate request per profile.
- **Direct PostgreSQL connection:** `database.py` connects via `psycopg2` directly to Supabase's PostgreSQL endpoint instead of the Supabase REST client, which proved unreliable on restricted networks.

---

## Module Reference

| File | Responsibility |
|---|---|
| `src/main.py` | Entry point. Reads `.env`, runs the full pipeline, handles `KeyboardInterrupt` and errors. |
| `src/modules/browser.py` | Launches Chromium with stealth patches, random user-agent and viewport per session. |
| `src/modules/auth.py` | Logs into LinkedIn. Saves session cookies after first login; reuses them on subsequent runs. Handles CAPTCHA with a 60-second manual-solve window. |
| `src/modules/search.py` | Paginates LinkedIn people search, scrolls each page to trigger lazy load, returns a deduplicated list of profile URLs. |
| `src/modules/profile_scraper.py` | Navigates to each profile URL, scrolls to trigger lazy-loaded sections, navigates to the activity page for posts. |
| `src/modules/parser.py` | Pure HTML → data extraction using BeautifulSoup. No browser dependency. Exports `ProfileData`, `ExperienceEntry`, `PostEntry` TypedDicts. |
| `src/modules/database.py` | All PostgreSQL operations: create/finish scrape sessions, upsert profiles, replace experience and posts. |
| `src/modules/exporter.py` | Fetches all profiles from the database (note: all rows, not keyword-filtered), joins with experience and posts, writes a flat CSV. |
| `src/modules/logger.py` | Single shared `logging.Logger` instance. `INFO` to terminal, `DEBUG` to a daily log file in `logs/`. |

---

## Prerequisites

- **Python 3.11** — other versions may work but are untested
- **pip** — comes with Python
- **A LinkedIn account** — the scraper logs in as you
- **A Supabase account** — free tier is sufficient ([supabase.com](https://supabase.com))
- **Chrome/Chromium** — installed by Playwright automatically (see setup below)

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/linkedin_scraper.git
cd linkedin_scraper
```

### 2. Create and activate a virtual environment

```bash
python3.11 -m venv venv
```

**Windows:**
```bash
venv\Scripts\activate
```

**Mac / Linux:**
```bash
source venv/bin/activate
```

You should see `(venv)` in your terminal prompt.

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright's Chromium browser

This downloads the actual browser binary Playwright controls:

```bash
playwright install chromium
```

### 5. Set up Supabase

1. Create a free account at [supabase.com](https://supabase.com)
2. Create a new project (name it anything)
3. Open the **SQL Editor** and run the schema below to create all four tables
4. Go to **Project Settings → Database** and copy the **Connection string (URI)** — this is your `SUPABASE_DB_URL`
5. Go to **Project Settings → API** and copy the **Project URL** and **anon/public key** — these are `SUPABASE_URL` and `SUPABASE_KEY`

### 6. Configure your `.env` file

Create a `.env` file in the project root (same level as `requirements.txt`):

```env
# LinkedIn credentials
LINKEDIN_EMAIL=your_email@example.com
LINKEDIN_PASSWORD=your_password

# Supabase — direct PostgreSQL connection string
# Found in: Supabase dashboard → Project Settings → Database → Connection string (URI)
SUPABASE_DB_URL=postgresql://postgres.yourprojectid:yourpassword@aws-region.pooler.supabase.com:5432/postgres

# Supabase — REST API credentials (used for the initial connection check)
# Found in: Supabase dashboard → Project Settings → API
SUPABASE_URL=https://yourprojectid.supabase.co
SUPABASE_KEY=your_anon_public_key

# Scraper behaviour
MAX_PAGES=3        # pages of search results per run (~10 profiles per page)
MIN_DELAY=4        # minimum seconds to wait between profile visits
MAX_DELAY=8        # maximum seconds to wait between profile visits
HEADLESS=False     # False = browser window visible; True = runs in background
```

> `.env` is listed in `.gitignore` and will never be committed to Git. Never share this file.

---

## Supabase Database Schema

Run this SQL in your Supabase SQL Editor exactly once, before first use:

```sql
CREATE TABLE profiles (
    id               BIGSERIAL PRIMARY KEY,
    linkedin_url     TEXT UNIQUE NOT NULL,
    full_name        TEXT,
    job_title        TEXT,
    about            TEXT,
    email            TEXT,
    location         TEXT,
    keyword_searched TEXT,
    scraped_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE experience (
    id          BIGSERIAL PRIMARY KEY,
    profile_id  BIGINT REFERENCES profiles(id) ON DELETE CASCADE,
    company     TEXT,
    role        TEXT,
    duration    TEXT,
    description TEXT
);

CREATE TABLE posts (
    id         BIGSERIAL PRIMARY KEY,
    profile_id BIGINT REFERENCES profiles(id) ON DELETE CASCADE,
    post_text  TEXT,
    post_date  TEXT,
    post_order INT   -- 1 = most recent, 2 = second, 3 = third
);

CREATE TABLE scrape_sessions (
    id               BIGSERIAL PRIMARY KEY,
    keyword          TEXT,
    profiles_found   INT DEFAULT 0,
    profiles_scraped INT DEFAULT 0,
    started_at       TIMESTAMPTZ DEFAULT NOW(),
    finished_at      TIMESTAMPTZ,
    status           TEXT DEFAULT 'running'  -- running / completed / failed / interrupted
);
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LINKEDIN_EMAIL` | Yes | Your LinkedIn login email |
| `LINKEDIN_PASSWORD` | Yes | Your LinkedIn login password |
| `SUPABASE_DB_URL` | Yes | PostgreSQL connection URI from Supabase dashboard |
| `SUPABASE_URL` | Yes | Supabase project REST URL |
| `SUPABASE_KEY` | Yes | Supabase anon/public API key |
| `MAX_PAGES` | No | Search result pages to scrape per run (default: `3`) |
| `MIN_DELAY` | No | Min seconds between profile visits (default: `4`) |
| `MAX_DELAY` | No | Max seconds between profile visits (default: `8`) |
| `HEADLESS` | No | `True` hides the browser window (default: `False`) |

---

## Running the Scraper

Make sure your virtual environment is active, then:

```bash
python -m src.main
```

You will be prompted for:

```
Enter keyword to search (e.g. 'Data Scientist'):  Doctor
How many pages to scrape? (default 3, each page ~10 profiles):  2
```

The browser opens, logs in, and starts scraping. You can watch it work in the browser window (when `HEADLESS=False`).

When complete:

```
============================================================
  Scraping Complete!
============================================================
  Keyword:          Doctor
  Profiles found:   21
  Profiles scraped: 19
  CSV saved to:     output/linkedin_doctor_20260329_143022.csv
============================================================
```

To stop mid-run, press `Ctrl+C`. The session will be marked as `interrupted` in the database and any profiles already scraped will be preserved.

---

## Output

### CSV file

Saved to `output/` with a timestamp in the filename. Each row is one LinkedIn profile. Columns:

| Column | Description |
|---|---|
| `full_name` | Person's full name |
| `job_title` | Current job title |
| `location` | City / country |
| `email` | Email address (often empty — only public ones are found) |
| `about` | Bio/About section |
| `experience` | All jobs joined as: `Role @ Company (Duration) \| Role @ Company (Duration)` |
| `post_1` | Most recent post text |
| `post_2` | Second most recent post text |
| `post_3` | Third most recent post text |
| `linkedin_url` | Full profile URL |
| `keyword_searched` | The keyword that found this person |
| `scraped_at` | Timestamp of when the profile was scraped |

> **Note:** The CSV export pulls ALL profiles currently in the database, not just those from the most recent run. This is by design — it gives you the full accumulated dataset in one file. The `keyword_searched` column lets you filter by run in Excel or SQL.

### Supabase database

All data is stored live in your Supabase project. You can query it directly in the Supabase SQL Editor, connect it to a dashboard, or share it with teammates.

### Log files

Saved to `logs/` named by date (e.g. `2026-03-29.log`). Terminal shows `INFO` level; the file contains full `DEBUG` detail including every warning and error.

---

## Configuration Reference

### Delay settings

`MIN_DELAY` and `MAX_DELAY` control how long the scraper waits between visiting profiles. A random value between the two is chosen each time. These delays are what prevent LinkedIn from detecting and rate-limiting your account. Do not set them below `3` / `5`.

### Page count

Each page of LinkedIn search results contains approximately 10 profiles. `MAX_PAGES=3` will scrape around 30 profiles per keyword. The actual number may be slightly lower if some profiles fail to load or are private.

### Headless mode

`HEADLESS=False` (the default) shows the browser window. Use this during development to see what is happening and to solve CAPTCHA challenges manually. Set `HEADLESS=True` for unattended background runs.

---

## How Re-scraping Works

Running the scraper again with the same keyword does not create duplicate records. The `profiles` table has a `UNIQUE` constraint on `linkedin_url`. When a profile URL already exists:

1. The profile row is **updated** with fresh data (name, title, location, about, email)
2. All old `experience` rows for that profile are **deleted and re-inserted**
3. All old `posts` rows for that profile are **deleted and re-inserted**

This means you can re-run keywords periodically to keep the data fresh.

---

## Known Limitations

| Limitation | Details |
|---|---|
| Private profiles | Some users restrict profile visibility to connections only. The scraper will see "LinkedIn Member" or a limited view. |
| Emails are usually empty | LinkedIn hides contact info unless the person has explicitly made their email public in their profile. |
| ~10 profiles per page | LinkedIn's people search always returns approximately 10 results per page. |
| Scraping is intentionally slow | 4–8 second random delays between profiles are necessary to avoid account bans. Expect ~6 minutes per 30 profiles. |
| Posts may be empty | Many users do not post publicly or have their activity set to private. |
| LinkedIn HTML changes | LinkedIn regularly updates their CSS class names. If parsing starts returning empty fields, inspect the page and update the selectors in `parser.py`. |
| Single account only | The scraper runs as a single logged-in user. LinkedIn may flag the account if it scrapes too aggressively. |

---

## Troubleshooting

**`ModuleNotFoundError: playwright` or similar on first run**
You are not inside the virtual environment. Run `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Mac/Linux) and then run again.

**`playwright install chromium` fails**
Run it with admin/sudo privileges or check your network proxy settings.

**Browser opens but login fails**
- Check `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` in `.env` are correct
- LinkedIn may prompt for CAPTCHA verification — when prompted, the scraper waits up to 60 seconds for you to solve it manually in the open browser window
- If LinkedIn shows a "verify it's you" step via email/phone, complete it and the scraper will resume

**`could not connect to server` database error**
- Confirm `SUPABASE_DB_URL` is the full PostgreSQL URI from Supabase, not the REST API URL
- Your IP or network may block outbound connections to Supabase on port 5432 — try a different network or enable a VPN

**Profiles scraping but all fields are empty**
LinkedIn changed their HTML. Open a profile in your browser, inspect the element you want, and update the relevant selector in `src/modules/parser.py`.

**`session_cookies.json` causes instant logout on load**
Delete the file and the scraper will perform a fresh login on the next run.

**`KeyError` or `TypeError` in `database.py`**
Confirm your Supabase tables were created with the exact schema above. A missing column or wrong type will cause insert failures.
