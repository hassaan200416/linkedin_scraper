"""
main.py
-------
Entry point for the LinkedIn scraper.
Run this file to start scraping.

What it does:
1. Loads credentials from .env
2. Launches the browser
3. Logs into LinkedIn
4. Takes keyword input from you
5. Searches LinkedIn for that keyword
6. Scrapes each profile found
7. Saves everything to Supabase
8. Exports a CSV to the output/ folder
"""

import os
import sys
from dotenv import load_dotenv

# Add project root to path so imports work correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.modules.logger import logger
from src.modules.browser import create_browser, close_browser
from src.modules.auth import login
from src.modules.search import search_profiles
from src.modules.profile_scraper import scrape_profile
from src.modules.database import (
    get_supabase_client,
    create_scrape_session,
    finish_scrape_session,
    save_full_profile,
)
from src.modules.exporter import export_to_csv

# Load all environment variables from .env
load_dotenv()


# ── Settings from .env ────────────────────────────────────────────────────────

LINKEDIN_EMAIL    = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")
MAX_PAGES         = int(os.getenv("MAX_PAGES", "3"))
MIN_DELAY         = int(os.getenv("MIN_DELAY", "4"))
MAX_DELAY         = int(os.getenv("MAX_DELAY", "8"))
HEADLESS          = os.getenv("HEADLESS", "False").lower() == "true"


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_credentials() -> bool:
    """
    Checks that LinkedIn credentials are present in .env
    Stops the script early with a clear message if missing.

    Returns:
        True if credentials exist, False if missing.
    """
    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        logger.error(
            "LinkedIn credentials missing. "
            "Add LINKEDIN_EMAIL and LINKEDIN_PASSWORD to your .env file."
        )
        return False
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """
    Main function — orchestrates the entire scraping pipeline.

    Flow:
    1. Validate credentials
    2. Connect to Supabase
    3. Get keyword input from user
    4. Launch browser and log in
    5. Search for profiles
    6. Create scrape session in DB
    7. Scrape each profile
    8. Save each profile to Supabase
    9. Mark session complete
    10. Export CSV
    """

    logger.info("=" * 60)
    logger.info("  LinkedIn Scraper Starting")
    logger.info("=" * 60)

    # ── Step 1: Validate credentials ─────────────────────────
    if not _validate_credentials():
        sys.exit(1)

    # ── Step 2: Connect to Supabase ──────────────────────────
    logger.info("Connecting to Supabase...")
    try:
        supabase = get_supabase_client()
    except Exception as e:
        logger.error(f"Could not connect to Supabase: {e}")
        sys.exit(1)

    # ── Step 3: Get keyword from user ────────────────────────
    print("\n" + "=" * 60)
    print("  LinkedIn Profile Scraper")
    print("=" * 60)
    keyword = input("\nEnter keyword to search (e.g. 'Data Scientist'): ").strip()

    if not keyword:
        logger.error("No keyword entered. Exiting.")
        sys.exit(1)

    max_pages_input = input(
        f"How many pages to scrape? (default {MAX_PAGES}, each page ~10 profiles): "
    ).strip()

    # Use input if provided, otherwise use default from .env
    pages = int(max_pages_input) if max_pages_input.isdigit() else MAX_PAGES

    logger.info(f"Keyword: '{keyword}' | Pages: {pages}")

    # ── Step 4: Launch browser and login ─────────────────────
    playwright, browser, page = create_browser(headless=HEADLESS)
    session_id: int | None = None
    scraped_count = 0

    try:
        logged_in = login(page, LINKEDIN_EMAIL, LINKEDIN_PASSWORD)

        if not logged_in:
            logger.error("Login failed. Exiting.")
            close_browser(playwright, browser)
            sys.exit(1)

        # ── Step 5: Search for profiles ──────────────────────
        profile_urls = search_profiles(
            page=page,
            keyword=keyword,
            max_pages=pages,
        )

        if not profile_urls:
            logger.warning("No profiles found for this keyword.")
            close_browser(playwright, browser)
            sys.exit(0)

        # ── Step 6: Create scrape session in DB ──────────────
        session_id = create_scrape_session(
            client=supabase,
            keyword=keyword,
            profiles_found=len(profile_urls),
        )

        # ── Step 7 & 8: Scrape and save each profile ─────────
        logger.info(f"Scraping {len(profile_urls)} profiles...")

        for index, url in enumerate(profile_urls, start=1):

            logger.info(f"[{index}/{len(profile_urls)}] Scraping: {url}")

            # Scrape the profile
            profile_data = scrape_profile(
                page=page,
                profile_url=url,
                keyword=keyword,
                min_delay=MIN_DELAY,
                max_delay=MAX_DELAY,
            )

            # Save to Supabase immediately after each scrape
            # This means data is safe even if script crashes midway
            if profile_data:
                saved = save_full_profile(supabase, profile_data)
                if saved:
                    scraped_count += 1
                    logger.info(
                        f"[{index}/{len(profile_urls)}] ✓ Saved: "
                        f"{profile_data.get('full_name', 'Unknown')}"
                    )
            else:
                logger.warning(
                    f"[{index}/{len(profile_urls)}] ✗ Failed: {url}"
                )

        # ── Step 9: Mark session complete ────────────────────
        finish_scrape_session(
            client=supabase,
            session_id=session_id,
            profiles_scraped=scraped_count,
            status="completed",
        )

        # ── Step 10: Export CSV ───────────────────────────────
        logger.info("Exporting data to CSV...")
        csv_path = export_to_csv(client=supabase, keyword=keyword)

        # ── Done ──────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("  Scraping Complete!")
        print("=" * 60)
        print(f"  Keyword:          {keyword}")
        print(f"  Profiles found:   {len(profile_urls)}")
        print(f"  Profiles scraped: {scraped_count}")
        print(f"  CSV saved to:     {csv_path}")
        print("=" * 60 + "\n")

        logger.info("Scraping session finished successfully.")

    except KeyboardInterrupt:
        # User pressed Ctrl+C — save what we have and exit cleanly
        logger.warning("Scraping interrupted by user.")
        if session_id is not None:
            finish_scrape_session(
                client=supabase,
                session_id=session_id,
                profiles_scraped=scraped_count,
                status="interrupted",
            )

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if session_id is not None:
            finish_scrape_session(
                client=supabase,
                session_id=session_id,
                profiles_scraped=scraped_count,
                status="failed",
            )

    finally:
        # Always close the browser no matter what happens
        close_browser(playwright, browser)


if __name__ == "__main__":
    main()