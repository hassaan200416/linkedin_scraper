"""
search.py
---------
Handles LinkedIn people search.
Takes a keyword, searches LinkedIn, and collects
all profile URLs from the search results pages.
"""

import time
import random
from playwright.sync_api import Page
from .logger import logger


# ── Constants ────────────────────────────────────────────────────────────────

# origin=GLOBAL_SEARCH_HEADER mimics a search triggered from LinkedIn's top nav bar.
# Without it, LinkedIn may classify the request as a bot probe and throttle results.
SEARCH_URL = "https://www.linkedin.com/search/results/people/?keywords={keyword}&origin=GLOBAL_SEARCH_HEADER"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _scroll_page(page: Page) -> None:
    """
    Scrolls the page slowly from top to bottom.
    LinkedIn loads results lazily — scrolling forces
    all profile cards to appear in the DOM.

    Args:
        page: Playwright page instance.
    """
    logger.info("Scrolling page to load all results...")

    # Get total page height
    total_height = page.evaluate("document.body.scrollHeight")
    scrolled     = 0
    step         = 300  # pixels per scroll step

    while scrolled < total_height:
        page.evaluate(f"window.scrollBy(0, {step})")
        scrolled += step
        time.sleep(random.uniform(0.3, 0.7))  # small human-like pause

    # Scroll back to top
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)


def _extract_profile_urls(page: Page) -> list[str]:
    """
    Extracts all LinkedIn profile URLs from the current search results page.
    Looks for anchor tags that point to /in/ profile paths.

    Args:
        page: Playwright page instance.

    Returns:
        List of full LinkedIn profile URLs found on this page.
    """
    urls: list[str] = []

    anchors = page.query_selector_all("a[href*='/in/']")

    for anchor in anchors:
        href = anchor.get_attribute("href")
        if not href or "/in/" not in href:
            continue

        # Remove query params
        clean_path = href.split("?")[0]

        # Build final URL — handle both relative and absolute hrefs
        if clean_path.startswith("http"):
            # Already a full URL — use as is
            final_url = clean_path
        else:
            # Relative path — prepend base domain
            final_url = "https://www.linkedin.com" + clean_path

        # Skip LinkedIn internal member ID URLs — they are duplicates of vanity URLs
        if "/in/ACoAA" in final_url:
            continue

        # Remove duplicates
        if final_url not in urls:
            urls.append(final_url)

    return urls


def _go_to_next_page(page: Page) -> bool:
    """
    Clicks the 'Next' pagination button to go to the next results page.

    Args:
        page: Playwright page instance.

    Returns:
        True if next page exists and was clicked.
        False if no next button found (last page reached).
    """
    try:
        # LinkedIn next button aria-label
        next_button = page.query_selector("button[aria-label='Next']")

        if next_button and next_button.is_enabled():
            next_button.click()
            logger.info("Moving to next page...")
            time.sleep(random.uniform(3, 5))
            return True

        logger.info("No more pages available.")
        return False

    except Exception as e:
        logger.warning(f"Could not click next page button: {e}")
        return False


# ── Main Search Function ──────────────────────────────────────────────────────

def search_profiles(page: Page, keyword: str, max_pages: int = 3) -> list[str]:
    """
    Searches LinkedIn for people matching the given keyword.
    Collects profile URLs across multiple pages of results.

    Args:
        page:      Playwright page instance.
        keyword:   Search term e.g. 'Data Scientist' or 'CTO'
        max_pages: How many pages of results to scrape (default 3)
                   Each page has ~10 profiles = 30 profiles max by default.

    Returns:
        List of unique LinkedIn profile URLs to scrape.
    """

    all_profile_urls: list[str] = []

    # Format the search URL with the keyword
    search_url = SEARCH_URL.format(keyword=keyword.replace(" ", "%20"))

    logger.info(f"Searching LinkedIn for: '{keyword}'")
    logger.info(f"Search URL: {search_url}")

    # Navigate to search results
    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(3, 5))

    # ── Loop through pages ───────────────────────────────────
    for page_number in range(1, max_pages + 1):

        logger.info(f"Scraping search results page {page_number}/{max_pages}...")

        # Scroll to load all cards on this page
        _scroll_page(page)

        # Extract profile URLs from this page
        urls_on_page = _extract_profile_urls(page)
        logger.info(f"Found {len(urls_on_page)} profiles on page {page_number}")

        # Add to master list (avoid duplicates)
        for url in urls_on_page:
            if url not in all_profile_urls:
                all_profile_urls.append(url)

        # Try going to next page — stop if no more pages
        if page_number < max_pages:
            has_next = _go_to_next_page(page)
            if not has_next:
                break

    logger.info(f"Total profiles found for '{keyword}': {len(all_profile_urls)}")
    return all_profile_urls