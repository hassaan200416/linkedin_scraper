# LinkedIn Profile Scraper

A fully automated LinkedIn scraping tool built with Python. It logs into LinkedIn using your credentials, searches for people by keyword, visits each profile, extracts structured data, saves everything to a cloud database (Supabase), and exports a clean CSV file — all with zero manual effort after setup.

---

## What This Project Does

You type a keyword like `"Doctor"` or `"Data Scientist"` and the scraper:

1. Opens a real Chrome browser automatically
2. Logs into LinkedIn with your account
3. Searches LinkedIn People for that keyword
4. Collects all profile links from the search results
5. Visits each profile one by one
6. Extracts the following data from every profile:
   - Full Name
   - Job Title
   - Location
   - About / Bio section
   - Complete Work Experience (all jobs, companies, durations)
   - Up to 3 Recent Posts
   - Email address (if publicly listed)
7. Saves everything to a Supabase cloud database in real time
8. Exports a clean Excel-ready CSV file at the end

---

## Who This Is For

- Recruiters building a talent database
- Sales teams finding leads by profession
- Researchers collecting professional data
- Developers learning web scraping and automation
- Anyone who wants LinkedIn data organized and exportable

---

## Tech Stack

| Tool                  | Purpose                                   |
| --------------------- | ----------------------------------------- |
| Python 3.11           | Core programming language                 |
| Playwright            | Controls a real Chrome browser            |
| Playwright Stealth    | Hides automation signals from LinkedIn    |
| BeautifulSoup4        | Reads and parses HTML pages               |
| Supabase (PostgreSQL) | Cloud database — stores all scraped data  |
| psycopg2              | Connects Python directly to the database  |
| Pandas                | Converts database data into CSV files     |
| python-dotenv         | Loads credentials securely from .env file |

---

## Project Structure

```
linkedin_scraper/
│
├── .env                        ← Your credentials (never share this)
├── .gitignore                  ← Prevents credentials from being uploaded
├── requirements.txt            ← All Python libraries listed here
├── README.md                   ← This file
├── session_cookies.json        ← Auto-created after first login
│
├── src/
│   ├── main.py                 ← Entry point — run this to start scraping
│   └── modules/
│       ├── browser.py          ← Launches Chrome with stealth settings
│       ├── auth.py             ← Handles LinkedIn login + session cookies
│       ├── search.py           ← Searches LinkedIn by keyword, collects URLs
│       ├── profile_scraper.py  ← Opens each profile + activity page
│       ├── parser.py           ← Extracts data from raw HTML
│       ├── database.py         ← Saves all data to Supabase
│       ├── exporter.py         ← Exports data from Supabase to CSV
│       └── logger.py           ← Logs all activity to terminal + log file
│
├── logs/                       ← Daily log files saved here automatically
└── output/                     ← CSV exports saved here
```

---

## Database Structure

The project uses 4 tables in Supabase. They are all connected through IDs.

### `profiles` — One row per LinkedIn profile

| Column           | Type      | Description                         |
| ---------------- | --------- | ----------------------------------- |
| id               | number    | Unique ID auto-assigned             |
| linkedin_url     | text      | The profile's LinkedIn URL (unique) |
| full_name        | text      | Person's full name                  |
| job_title        | text      | Current job title                   |
| location         | text      | City / country                      |
| about            | text      | Their bio/about section             |
| email            | text      | Email if publicly listed            |
| keyword_searched | text      | The keyword that found this person  |
| scraped_at       | timestamp | When this profile was scraped       |

### `experience` — One row per job (multiple per person)

| Column      | Type   | Description                         |
| ----------- | ------ | ----------------------------------- |
| id          | number | Unique ID                           |
| profile_id  | number | Links to profiles table             |
| company     | text   | Company name                        |
| role        | text   | Job title at that company           |
| duration    | text   | Time period e.g. Jan 2020 - Present |
| description | text   | Role description if available       |

### `posts` — Up to 3 rows per person

| Column     | Type   | Description                            |
| ---------- | ------ | -------------------------------------- |
| id         | number | Unique ID                              |
| profile_id | number | Links to profiles table                |
| post_text  | text   | Full text of the post                  |
| post_date  | text   | Date of the post                       |
| post_order | number | 1 = most recent, 2 = second, 3 = third |

### `scrape_sessions` — One row per scraping run

| Column           | Type      | Description                                |
| ---------------- | --------- | ------------------------------------------ |
| id               | number    | Session ID                                 |
| keyword          | text      | What was searched                          |
| profiles_found   | number    | How many URLs were collected               |
| profiles_scraped | number    | How many were successfully saved           |
| started_at       | timestamp | When the run started                       |
| finished_at      | timestamp | When the run ended                         |
| status           | text      | running / completed / failed / interrupted |

---

## Setup Guide

### Step 1 — Requirements

- Windows / Mac / Linux
- Python 3.11 installed
- A LinkedIn account
- A free Supabase account (supabase.com)
- VS Code (recommended)

---

### Step 2 — Clone or Download the Project

```bash
git clone https://github.com/yourusername/linkedin_scraper.git
cd linkedin_scraper
```

---

### Step 3 — Create a Virtual Environment

```bash
python3.11 -m venv venv
```

Activate it:

**Windows:**

```bash
venv\Scripts\activate
```

**Mac / Linux:**

```bash
source venv/bin/activate
```

You will see `(venv)` appear in your terminal. This means it is active.

---

### Step 4 — Install All Libraries

```bash
pip install -r requirements.txt
```

Then install the Chrome browser that Playwright uses:

```bash
playwright install chromium
```

---

### Step 5 — Set Up Supabase

1. Go to [supabase.com](https://supabase.com) and create a free account
2. Create a new project called `linkedin_scraper`
3. Go to **SQL Editor** and run the following SQL to create all tables:

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
    id           BIGSERIAL PRIMARY KEY,
    profile_id   BIGINT REFERENCES profiles(id) ON DELETE CASCADE,
    company      TEXT,
    role         TEXT,
    duration     TEXT,
    description  TEXT
);

CREATE TABLE posts (
    id          BIGSERIAL PRIMARY KEY,
    profile_id  BIGINT REFERENCES profiles(id) ON DELETE CASCADE,
    post_text   TEXT,
    post_date   TEXT,
    post_order  INT
);

CREATE TABLE scrape_sessions (
    id               BIGSERIAL PRIMARY KEY,
    keyword          TEXT,
    profiles_found   INT DEFAULT 0,
    profiles_scraped INT DEFAULT 0,
    started_at       TIMESTAMPTZ DEFAULT NOW(),
    finished_at      TIMESTAMPTZ,
    status           TEXT DEFAULT 'running'
);
```

4. Go to **Project Settings → Database** and copy your connection URI
5. Go to **Project Settings → API Keys** and copy your Publishable key

---

### Step 6 — Configure Your .env File

Create a file called `.env` in the root of the project and fill in your details:

```env
# LinkedIn Account
LINKEDIN_EMAIL=your_linkedin_email@gmail.com
LINKEDIN_PASSWORD=your_linkedin_password

# Supabase Direct Database Connection
SUPABASE_DB_URL=postgresql://postgres:yourpassword@db.yourprojectid.supabase.co:5432/postgres

# Supabase API (used for initial connection check)
SUPABASE_URL=https://yourprojectid.supabase.co
SUPABASE_KEY=your_publishable_key_here

# Scraper Settings
MAX_PAGES=3
MIN_DELAY=4
MAX_DELAY=8
HEADLESS=False
```

> **Important:** Never share your `.env` file or commit it to GitHub. It is already listed in `.gitignore` for your protection.

---

## How to Run

Make sure your virtual environment is active, then run:

```bash
python -m src.main
```

You will see:

```
============================================================
  LinkedIn Profile Scraper
============================================================

Enter keyword to search (e.g. 'Data Scientist'):
```

Type your keyword and press Enter. Then:

```
How many pages to scrape? (default 3, each page ~10 profiles):
```

Type a number and press Enter. The scraper will start automatically.

---

## What You Will See While It Runs

**In your terminal:**

```
[INFO] Connecting to Supabase...
[INFO] Browser launched
[INFO] Login successful
[INFO] Searching LinkedIn for: 'Doctor'
[INFO] Found 11 profiles on page 1
[INFO] [1/32] Scraping: linkedin.com/in/dr-ramisha...
[INFO] Parsed: Dr. Ramisha Fatima | Public Health Professional
[INFO] Profile saved (ID: 1)
...
[INFO] CSV exported: output/linkedin_doctor_20260319.csv
```

**In your Chrome window:**

- Browser opens and logs into LinkedIn
- Searches your keyword
- Opens each profile one by one
- Scrolls through each profile
- Visits the activity page for posts
- Closes when done

---

## Output

After the run completes you get two outputs:

### 1. CSV File

Saved in the `output/` folder with a timestamp in the filename.
Open it in Excel or Google Sheets. Each row is one LinkedIn profile.

Columns: `full_name`, `job_title`, `location`, `email`, `about`, `experience`, `post_1`, `post_2`, `post_3`, `linkedin_url`, `keyword_searched`, `scraped_at`

### 2. Supabase Database

All data is stored live in your Supabase project. You can:

- View it in the Supabase Table Editor
- Query it with SQL
- Connect it to any frontend or dashboard
- Share access with your team

---

## Settings You Can Change

All settings are in your `.env` file:

| Setting   | Default | Description                               |
| --------- | ------- | ----------------------------------------- |
| MAX_PAGES | 3       | Pages of search results to scrape per run |
| MIN_DELAY | 4       | Minimum seconds to wait between profiles  |
| MAX_DELAY | 8       | Maximum seconds to wait between profiles  |
| HEADLESS  | False   | Set to True to hide the browser window    |

**Tip:** Keep `HEADLESS=False` during development so you can see what is happening. Set it to `True` for background runs.

---

## Tips for Getting More Data

- Run the scraper with different keywords to build a larger database:

```
  "Doctor" → "Medical Doctor" → "Physician" → "Surgeon" → "MBBS"
```

- Each keyword finds different people
- All results save to the same database without duplicates
- Every LinkedIn profile URL is unique — running the same keyword twice just refreshes existing data

---

## Important Limitations

| Limitation                                      | Reason                                                                |
| ----------------------------------------------- | --------------------------------------------------------------------- |
| Names may show "LinkedIn respects your privacy" | Some users set their profile to private — only visible to connections |
| Emails are usually empty                        | LinkedIn hides emails unless the person made them public              |
| ~10 profiles per page                           | LinkedIn's search shows 10 results per page                           |
| Scraping speed is intentionally slow            | Random 4-8 second delays between profiles prevent account bans        |
| Posts may be empty for some profiles            | Some users have not posted publicly or have their activity hidden     |

---

## How the Code Works — Simple Explanation

```
main.py starts
    │
    ├── Connects to Supabase database
    ├── Asks you for a keyword
    ├── Opens Chrome browser (browser.py)
    ├── Logs into LinkedIn (auth.py)
    │       └── Reuses saved cookies if available
    │           Otherwise logs in fresh and saves cookies
    │
    ├── Searches LinkedIn (search.py)
    │       └── Collects all profile URLs from search results
    │
    ├── Creates a scrape session in the database
    │
    └── For each profile URL:
            ├── Opens the profile (profile_scraper.py)
            ├── Scrolls to load all sections
            ├── Extracts HTML and parses data (parser.py)
            │       ├── Name, title, location, about, email
            │       └── Work experience entries
            ├── Visits the activity page for posts
            │       └── Up to 3 unique recent posts
            ├── Saves everything to Supabase (database.py)
            └── Waits 4-8 random seconds before next profile

    └── Exports full CSV from database (exporter.py)
```

---

## Logging

Every action is logged in two places:

1. **Terminal** — you see INFO level logs in real time while it runs
2. **Log file** — saved in `logs/` folder, named by date e.g. `2026-03-19.log`

Log files contain DEBUG level detail including every warning and error. Useful for diagnosing issues after a run.

---

## Security Notes

- Your LinkedIn credentials are stored only in your local `.env` file
- Nothing is sent to any third party server
- Session cookies are saved locally in `session_cookies.json`
- The `.gitignore` file prevents `.env` and cookies from being committed to Git
- The Supabase publishable key is safe to use in backend scripts

---

## Troubleshooting

**Browser does not open:**
Make sure you ran `playwright install chromium`

**Login fails:**
Check your email and password in `.env`. LinkedIn may also ask for CAPTCHA verification — solve it manually in the browser window when prompted.

**Database connection fails:**
Make sure your VPN is on if you are in a region that blocks Supabase. Check your `SUPABASE_DB_URL` is correct in `.env`.

**Names showing as "LinkedIn respects your privacy":**
This is a LinkedIn privacy setting on the other user's account. Not fixable — their name is simply not public.

**Posts are empty for most profiles:**
Most LinkedIn users do not post publicly or have their activity set to private. This is normal.
