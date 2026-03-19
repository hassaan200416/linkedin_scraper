"""
profile_scraper.py
------------------
Visits each LinkedIn profile URL one by one.
Scrolls the page to load all lazy sections.
Captures the full HTML and passes it to parser.py.
Handles errors gracefully so one failed profile
doesn't stop the entire scraping session.
"""

import time
import random
import importlib
from typing import Any, cast
from playwright.sync_api import Page
from .parser import PostEntry, ProfileData, parse_profile
from .logger import logger


bs4_module = importlib.import_module("bs4")
BeautifulSoup = bs4_module.BeautifulSoup


# ── Constants ────────────────────────────────────────────────────────────────

# Sections to scroll to — ensures lazy-loaded content appears
# LinkedIn loads Experience, Posts etc. only when scrolled into view
SCROLL_PAUSE_SECONDS = 1.5


# ── Helpers ──────────────────────────────────────────────────────────────────

def _scroll_to_load_all_sections(page: Page) -> None:
    """
    Scrolls down the profile page in steps to trigger
    lazy loading of all sections (Experience, Posts, etc.)
    Then scrolls back to top.

    Args:
        page: Playwright page instance.
    """
    logger.info("Scrolling profile to load all sections...")

    # Get full page height
    total_height = page.evaluate("document.body.scrollHeight")
    current_pos  = 0
    step         = 500  # pixels per step

    while current_pos < total_height:
        page.evaluate(f"window.scrollBy(0, {step})")
        current_pos += step

        # Small random pause — mimics human reading while scrolling
        time.sleep(random.uniform(0.4, 0.9))

        # Update total height in case new content loaded
        total_height = page.evaluate("document.body.scrollHeight")

    # Pause at bottom to let final sections load
    time.sleep(SCROLL_PAUSE_SECONDS)

    # Scroll back to top
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)


def _wait_for_profile_load(page: Page) -> bool:
    """
    Waits for the profile page to fully load.
    Checks that the main profile header (h1 name tag) is visible.

    Args:
        page: Playwright page instance.

    Returns:
        True if profile loaded successfully.
        False if page timed out or showed an error.
    """
    try:
        # Wait for the h1 (name) to appear — confirms profile loaded
        page.wait_for_selector("h1", timeout=15000)
        return True
    except Exception:
        logger.warning("Profile page did not load in time.")
        return False


def _class_contains_text(class_val: Any, text: str) -> bool:
    """Helper to check if class value contains text fragment."""
    if isinstance(class_val, str):
        return text in class_val
    if isinstance(class_val, list):
        items = cast(list[Any], class_val)
        return any(isinstance(item, str) and text in item for item in items)
    return False


def _is_feed_shared_update(c: Any) -> bool:
    """Check if class contains feed-shared-update-v2."""
    return _class_contains_text(c, "feed-shared-update-v2")


def _is_feed_shared_text(c: Any) -> bool:
    """Check if class contains feed-shared-text."""
    return _class_contains_text(c, "feed-shared-text")


def _is_break_words(c: Any) -> bool:
    """Check if class contains break-words."""
    return _class_contains_text(c, "break-words")


def _scrape_activity_page(
    page: Page,
    profile_url: str,
) -> list[PostEntry]:
    """
    Visits the profile's activity page to get recent posts.
    LinkedIn does not load posts on the main profile page —
    they are only available at the /recent-activity/all/ URL.

    Args:
        page:        Playwright page instance.
        profile_url: Base profile URL e.g. linkedin.com/in/john-smith

    Returns:
        List of up to 3 post dicts with post_text, post_date, post_order.
    """
    posts: list[PostEntry] = []

    try:
        # Build activity URL from profile URL
        # Strip trailing slash if present then append activity path
        base_url     = profile_url.rstrip("/")
        activity_url = f"{base_url}/recent-activity/all/"

        logger.info(f"Visiting activity page: {activity_url}")

        page.goto(activity_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(3, 5))

        # Scroll to load posts
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(2)
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(2)

        # Get full HTML of activity page
        html = page.content()
        soup_obj = BeautifulSoup(html, "lxml")

        # Posts are inside feed update containers
        # Each post is in a div with class containing 'feed-shared-update'
        post_containers = cast(list[Any], soup_obj.find_all(
            "div",
            {"class": _is_feed_shared_update}
        ))

        logger.info(f"Found {len(post_containers)} post containers")

        seen_texts: list[str] = []

        for container in post_containers:
            # Stop once we have 3 unique posts
            if len(posts) >= 3:
                break

            # Extract post text
            text_div = container.find(
                "div",
                {"class": _is_feed_shared_text}
            )
            if not text_div:
                text_div = container.find(
                    "span",
                    {"class": _is_break_words}
                )

            post_text = ""
            if text_div:
                post_text = " ".join(str(text_div.get_text()).split()).strip()

            # Skip empty posts
            if not post_text:
                continue

            # Skip duplicate posts — same text already seen
            if post_text in seen_texts:
                continue

            # Mark this text as seen
            seen_texts.append(post_text)

            # Extract post date
            time_tag  = container.find("time")
            post_date = ""
            if time_tag:
                post_date = str(
                    time_tag.get("datetime", "") or time_tag.get_text().strip()
                )

            # Add unique post
            posts.append({
                "post_text":  post_text,
                "post_date":  post_date,
                "post_order": len(posts) + 1,
            })
            logger.info(f"Post {len(posts)} extracted: {post_text[:60]}...")

        if not posts:
            logger.info("No posts found on activity page.")

    except Exception as e:
        logger.warning(f"Could not scrape activity page: {e}")

    return posts


# ── Main Scraper Function ─────────────────────────────────────────────────────

def scrape_profile(
    page: Page,
    profile_url: str,
    keyword: str,
    min_delay: int = 4,
    max_delay: int = 8,
) -> ProfileData | None:
    """
    Visits a single LinkedIn profile, scrolls it fully,
    extracts the HTML, and returns parsed profile data.

    Args:
        page:        Playwright page instance.
        profile_url: Full LinkedIn profile URL to scrape.
        keyword:     Search keyword that found this profile.
        min_delay:   Minimum seconds to wait after scraping (default 4).
        max_delay:   Maximum seconds to wait after scraping (default 8).
                     Random value between min and max is used each time.
                     This delay is what prevents LinkedIn from banning us.

    Returns:
        Parsed profile dictionary if successful.
        None if the profile could not be scraped.
    """

    logger.info(f"Opening profile: {profile_url}")

    try:
        # ── Step 1: Navigate to profile ──────────────────────
        page.goto(
            profile_url,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        # ── Step 2: Wait for profile to load ─────────────────
        loaded = _wait_for_profile_load(page)
        if not loaded:
            logger.warning(f"Skipping profile — failed to load: {profile_url}")
            return None

        # ── Step 3: Check we're not on an error page ─────────
        current_url = page.url
        if "authwall" in current_url or "login" in current_url:
            logger.error("Hit LinkedIn auth wall — session may have expired.")
            return None

        if "unavailable" in current_url or "404" in page.title():
            logger.warning(f"Profile unavailable: {profile_url}")
            return None

        # ── Step 4: Scroll to load all sections ──────────────
        _scroll_to_load_all_sections(page)

        # ── Step 5: Capture full page HTML ───────────────────
        html = page.content()

        # ── Step 6: Parse the HTML into structured data ──────
        profile_data = parse_profile(html, profile_url, keyword)

        # ── Step 6b: Scrape activity page for posts ───────────
        # Posts are not on the main profile page —
        # we visit the activity URL separately
        if profile_data:
            posts = _scrape_activity_page(page, profile_url)
            profile_data["posts"] = posts
            logger.info(
                f"Found {len(posts)} posts for "
                f"{profile_data.get('full_name', 'Unknown')}"
            )

        # ── Step 7: Human-like delay before next profile ─────
        delay = random.uniform(min_delay, max_delay)
        logger.info(f"Waiting {delay:.1f}s before next profile...")
        time.sleep(delay)

        return profile_data

    except Exception as e:
        logger.error(f"Failed to scrape profile {profile_url}: {e}")
        return None


# ── Batch Scraper ─────────────────────────────────────────────────────────────

def scrape_all_profiles(
    page: Page,
    profile_urls: list[str],
    keyword: str,
    min_delay: int = 4,
    max_delay: int = 8,
) -> list[ProfileData]:
    """
    Scrapes a list of LinkedIn profile URLs one by one.
    Skips failed profiles and continues with the rest.
    Logs progress throughout.

    Args:
        page:         Playwright page instance.
        profile_urls: List of LinkedIn profile URLs to scrape.
        keyword:      Search keyword used to find these profiles.
        min_delay:    Minimum delay between profiles in seconds.
        max_delay:    Maximum delay between profiles in seconds.

    Returns:
        List of successfully parsed profile dictionaries.
    """

    results: list[ProfileData] = []
    total        = len(profile_urls)
    failed_count = 0

    logger.info(f"Starting batch scrape of {total} profiles...")

    for index, url in enumerate(profile_urls, start=1):

        logger.info(f"[{index}/{total}] Scraping profile...")

        profile_data = scrape_profile(
            page=page,
            profile_url=url,
            keyword=keyword,
            min_delay=min_delay,
            max_delay=max_delay,
        )

        if profile_data:
            results.append(profile_data)
            logger.info(
                f"[{index}/{total}] ✓ Scraped: "
                f"{profile_data['full_name'] or 'Unknown'}"
            )
        else:
            failed_count += 1
            logger.warning(f"[{index}/{total}] ✗ Failed: {url}")

    logger.info(
        f"Batch complete — "
        f"Success: {len(results)}/{total} | "
        f"Failed: {failed_count}/{total}"
    )

    return results