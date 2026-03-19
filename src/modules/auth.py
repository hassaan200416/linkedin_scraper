"""
auth.py
-------
Handles LinkedIn authentication.
Logs in using credentials from .env file.
Saves session cookies after login so we don't need to
log in again on the next run — reuses saved session instead.
"""

import json
import os
import time
import random
from playwright.sync_api import Page
from .logger import logger


# ── Constants ────────────────────────────────────────────────────────────────

LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_FEED_URL  = "https://www.linkedin.com/feed"

# Cookies saved here after first login
COOKIES_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "session_cookies.json"
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _human_type(page: Page, selector: str, text: str) -> None:
    """
    Types text into a field with random delays between keystrokes.
    Mimics how a real human types — not all at once instantly.

    Args:
        page:     Playwright page instance.
        selector: CSS selector of the input field.
        text:     Text to type into the field.
    """
    page.click(selector)
    for character in text:
        page.type(selector, character, delay=random.randint(50, 150))


def _save_cookies(page: Page) -> None:
    """
    Saves current browser session cookies to a local JSON file.
    Next run loads these cookies to skip the login step entirely.

    Args:
        page: Playwright page instance.
    """
    cookies = page.context.cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f, indent=2)
    logger.info(f"Session cookies saved to {COOKIES_FILE}")


def _load_cookies(page: Page) -> bool:
    """
    Loads previously saved cookies into the browser.
    Returns True if cookies were loaded, False if no cookie file exists.

    Args:
        page: Playwright page instance.

    Returns:
        True if cookies loaded successfully, False otherwise.
    """
    if not os.path.exists(COOKIES_FILE):
        logger.info("No saved cookies found. Fresh login required.")
        return False

    with open(COOKIES_FILE, "r") as f:
        cookies = json.load(f)

    page.context.add_cookies(cookies)
    logger.info("Saved cookies loaded into browser.")
    return True


def _is_logged_in(page: Page) -> bool:
    """
    Checks if we are currently logged into LinkedIn.
    Navigates to the feed and checks if we land there successfully.

    Args:
        page: Playwright page instance.

    Returns:
        True if logged in, False if redirected to login page.
    """
    page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)

    # If we're on feed, we're logged in
    if "feed" in page.url:
        logger.info("Session is valid. Already logged in.")
        return True

    logger.info("Session expired or invalid. Need to log in.")
    return False


# ── Main Login Function ───────────────────────────────────────────────────────

def login(page: Page, email: str, password: str) -> bool:
    """
    Logs into LinkedIn using provided credentials.

    Strategy:
    1. First tries to reuse saved cookies (skips login if still valid)
    2. If cookies invalid/missing, performs full login with email + password
    3. Saves cookies after successful login for next run

    Args:
        page:     Playwright page instance.
        email:    LinkedIn account email from .env
        password: LinkedIn account password from .env

    Returns:
        True if login successful, False if login failed.
    """

    logger.info("Starting LinkedIn authentication...")

    # ── Step 1: Try reusing saved session ───────────────────
    cookies_loaded = _load_cookies(page)
    if cookies_loaded and _is_logged_in(page):
        return True

    # ── Step 2: Fresh login ──────────────────────────────────
    logger.info("Navigating to LinkedIn login page...")
    page.goto(LINKEDIN_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(2, 4))

    # Type email
    logger.info("Entering email...")
    _human_type(page, "#username", email)
    time.sleep(random.uniform(0.5, 1.5))

    # Type password
    logger.info("Entering password...")
    _human_type(page, "#password", password)
    time.sleep(random.uniform(0.5, 1.5))

    # Click Sign In button
    logger.info("Clicking Sign In...")
    page.click("button[type='submit']")

    # Wait for page to load after login
    time.sleep(random.uniform(4, 6))

    # ── Step 3: Handle possible outcomes ────────────────────

    current_url = page.url
    logger.info(f"Post-login URL: {current_url}")

    # Success — landed on feed
    if "feed" in current_url:
        logger.info("Login successful!")
        _save_cookies(page)
        return True

    # LinkedIn is asking for CAPTCHA or verification
    if "checkpoint" in current_url or "challenge" in current_url:
        logger.warning("LinkedIn is asking for verification/CAPTCHA.")
        logger.warning("Please solve it manually in the browser window.")
        logger.warning("Waiting up to 60 seconds for you to complete it...")

        # Wait up to 60 seconds for manual solve
        for _ in range(60):
            time.sleep(1)
            if "feed" in page.url:
                logger.info("Verification completed. Login successful!")
                _save_cookies(page)
                return True

        logger.error("Verification not completed in time. Login failed.")
        return False

    # Wrong password or other error
    logger.error(f"Login failed. Unexpected URL: {current_url}")
    return False