"""
browser.py
----------
Handles launching and closing the Playwright Chromium browser.
Applies stealth patches to avoid LinkedIn bot detection.
Returns a configured browser page ready to use.
"""

import random
import importlib
from typing import Callable
from playwright.sync_api import sync_playwright, Browser, Page, Playwright, ViewportSize
from .logger import logger


# playwright_stealth has no type stubs; load dynamically to avoid type-check errors.
stealth_sync = importlib.import_module("playwright_stealth").stealth_sync
stealth_sync_fn: Callable[[Page], None] = stealth_sync


# ── Constants ───────────────────────────────────────────────────────────────

# List of real user agents to rotate randomly
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# Realistic screen resolutions to randomize
VIEWPORTS: list[ViewportSize] = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
]


def create_browser(headless: bool = False) -> tuple[Playwright, Browser, Page]:
    """
    Launches a Chromium browser with stealth configuration.

    Args:
        headless: If True, browser runs in background (invisible).
                  If False, browser window is visible on screen.
                  Always use False during development so you can see what's happening.

    Returns:
        Tuple of (playwright instance, browser instance, page instance)
        All three are returned so they can be properly closed later.
    """

    logger.info("Launching browser...")

    # Pick random user agent and viewport for each session
    user_agent = random.choice(USER_AGENTS)
    viewport   = random.choice(VIEWPORTS)

    # Start Playwright
    playwright = sync_playwright().start()

    # Launch Chromium browser
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",  # hides automation flag
            "--disable-infobars",
            "--start-maximized",
        ]
    )

    # Create a browser context (like a fresh browser profile)
    context = browser.new_context(
        user_agent=user_agent,
        viewport=viewport,
        locale="en-US",
        timezone_id="America/New_York",
    )

    # Open a new page (tab)
    page = context.new_page()

    # Apply all stealth patches to this page
    # This removes all signs that the browser is automated
    stealth_sync_fn(page)

    logger.info(f"Browser launched | User-Agent: {user_agent[:50]}...")
    logger.info(f"Viewport: {viewport['width']}x{viewport['height']}")

    return playwright, browser, page


def close_browser(playwright: Playwright, browser: Browser) -> None:
    """
    Cleanly closes the browser and stops Playwright.

    Args:
        playwright: The Playwright instance to stop.
        browser: The Browser instance to close.
    """
    logger.info("Closing browser...")
    browser.close()
    playwright.stop()
    logger.info("Browser closed.")