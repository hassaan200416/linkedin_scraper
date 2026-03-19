"""
parser.py
---------
Extracts structured data from a LinkedIn profile's HTML.
Takes raw HTML as input, returns a clean dictionary with
all the profile information we need.

Data extracted:
- Full name
- Job title
- Location
- About / bio section
- Work experience (all jobs)
- Recent posts (up to 3)
- Email (only if publicly listed)
"""

import importlib
import re
from typing import Any, TypedDict, cast
from .logger import logger


bs4_module = importlib.import_module("bs4")
BeautifulSoup = bs4_module.BeautifulSoup
Soup = Any


class ExperienceEntry(TypedDict):
    role: str
    company: str
    duration: str
    description: str


class PostEntry(TypedDict):
    post_text: str
    post_date: str
    post_order: int


class ProfileData(TypedDict):
    linkedin_url: str
    full_name: str
    job_title: str
    location: str
    about: str
    email: str
    keyword_searched: str
    experience: list[ExperienceEntry]
    posts: list[PostEntry]


def _class_contains(value: Any, fragment: str) -> bool:
    """Returns True when a class attr value contains the given fragment."""
    if isinstance(value, str):
        return fragment in value
    if isinstance(value, list):
        items = cast(list[Any], value)
        return any(isinstance(item, str) and fragment in item for item in items)
    return False


def _is_text_body_medium(value: Any) -> bool:
    return _class_contains(value, "text-body-medium")


def _is_text_body_small(value: Any) -> bool:
    return _class_contains(value, "text-body-small")


def _is_display_flex(value: Any) -> bool:
    return _class_contains(value, "display-flex")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean_text(text: str | None) -> str:
    """
    Cleans extracted text by stripping whitespace and newlines.

    Args:
        text: Raw text string or None.

    Returns:
        Cleaned string, or empty string if input was None.
    """
    if not text:
        return ""
    return " ".join(text.split()).strip()


def _parse_name(soup: Soup) -> str:
    """
    Extracts the full name from the profile header.
    Tries multiple selectors since LinkedIn changes their HTML structure.

    Args:
        soup: BeautifulSoup object of the profile page.

    Returns:
        Full name as a string, or empty string if not found.
    """
    try:
        # Method 1 — h1 tag with specific class
        def _is_inline_class(c: Any) -> bool:
            return _class_contains(c, "inline")
        
        name_tag = soup.find("h1", {"class": _is_inline_class})
        if name_tag:
            name = _clean_text(str(name_tag.get_text()))
            if name and "linkedin" not in name.lower():
                return name

        # Method 2 — any h1 tag
        name_tag = soup.find("h1")
        if name_tag:
            name = _clean_text(str(name_tag.get_text()))
            if name and "linkedin" not in name.lower():
                return name

        # Method 3 — og:title meta tag
        # LinkedIn sets the page title to the person's name
        og_title = soup.find("meta", {"property": "og:title"})
        if og_title:
            name = _clean_text(og_title.get("content", ""))
            if name and "linkedin" not in name.lower():
                return name

        return ""

    except Exception as e:
        logger.warning(f"Could not parse name: {e}")
        return ""


def _parse_job_title(soup: Soup) -> str:
    """
    Extracts the current job title shown below the name.

    Args:
        soup: BeautifulSoup object of the profile page.

    Returns:
        Job title as a string, or empty string if not found.
    """
    try:
        # Job title sits in a div with this specific class pattern
        title_tag = soup.find("div", {"class": _is_text_body_medium})
        return _clean_text(str(title_tag.get_text())) if title_tag else ""
    except Exception as e:
        logger.warning(f"Could not parse job title: {e}")
        return ""


def _parse_location(soup: Soup) -> str:
    """
    Extracts the location shown on the profile.

    Args:
        soup: BeautifulSoup object of the profile page.

    Returns:
        Location string, or empty string if not found.
    """
    try:
        location_tag = soup.find("span", {"class": _is_text_body_small})
        return _clean_text(str(location_tag.get_text())) if location_tag else ""
    except Exception as e:
        logger.warning(f"Could not parse location: {e}")
        return ""


def _parse_about(soup: Soup) -> str:
    """
    Extracts the About / bio section of the profile.

    Args:
        soup: BeautifulSoup object of the profile page.

    Returns:
        About text as a string, or empty string if not found.
    """
    try:
        # Find the About section by its heading
        about_section = soup.find("div", {"id": "about"})
        if not about_section:
            return ""

        # The actual text is in a sibling container
        about_container = about_section.find_next("div", {"class": _is_display_flex})
        if about_container:
            return _clean_text(str(about_container.get_text()))

        return ""
    except Exception as e:
        logger.warning(f"Could not parse about section: {e}")
        return ""


def _parse_experience(soup: Soup) -> list[ExperienceEntry]:
    """
    Extracts all work experience entries from the profile.
    Each entry includes company, role, and duration.

    Args:
        soup: BeautifulSoup object of the profile page.

    Returns:
        List of dicts, each containing:
        - company:     Company name
        - role:        Job title at that company
        - duration:    Time period e.g. "Jan 2020 - Present"
        - description: Role description if available
    """
    experience_list: list[ExperienceEntry] = []

    try:
        # Find the Experience section by its id
        experience_section = soup.find("div", {"id": "experience"})
        if not experience_section:
            return []

        # Each job is in a list item inside the experience section
        experience_ul = experience_section.find_next("ul")
        if not experience_ul:
            return []

        job_items = experience_ul.find_all("li", recursive=False)

        for item in job_items:
            # Extract all text spans inside this job entry
            spans = item.find_all("span", {"aria-hidden": "true"})
            texts: list[str] = [
                _clean_text(str(s.get_text()))
                for s in spans
                if _clean_text(str(s.get_text()))
            ]

            if len(texts) >= 2:
                experience_list.append({
                    "role":        texts[0] if len(texts) > 0 else "",
                    "company":     texts[1] if len(texts) > 1 else "",
                    "duration":    texts[2] if len(texts) > 2 else "",
                    "description": texts[4] if len(texts) > 4 else "",
                })

    except Exception as e:
        logger.warning(f"Could not parse experience: {e}")

    return experience_list


def _parse_posts(soup: Soup) -> list[PostEntry]:
    """
    Extracts up to 3 most recent posts from the profile's activity section.

    Args:
        soup: BeautifulSoup object of the profile page.

    Returns:
        List of up to 3 dicts, each containing:
        - post_text:  Text content of the post
        - post_date:  Date string if available
        - post_order: 1, 2, or 3 (most recent first)
    """
    posts_list: list[PostEntry] = []

    try:
        # Find activity/posts section
        activity_section = soup.find("div", {"id": "activity"})
        if not activity_section:
            return []

        # Posts are in span tags with specific class inside activity
        post_ul = activity_section.find_next("ul")
        if not post_ul:
            return []

        post_containers = post_ul.find_all("li", recursive=False)

        for index, post in enumerate(post_containers[:3]):  # max 3 posts
            spans = post.find_all("span", {"aria-hidden": "true"})
            texts: list[str] = [
                _clean_text(str(s.get_text()))
                for s in spans
                if _clean_text(str(s.get_text()))
            ]

            post_text = texts[0] if texts else ""
            post_date = texts[1] if len(texts) > 1 else ""

            if post_text:
                posts_list.append({
                    "post_text":  post_text,
                    "post_date":  post_date,
                    "post_order": index + 1,
                })

    except Exception as e:
        logger.warning(f"Could not parse posts: {e}")

    return posts_list


def _parse_email(soup: Soup) -> str:
    """
    Attempts to find a publicly listed email address on the profile.
    LinkedIn hides most emails — this only works if the person
    has made their email visible in their contact info.

    Args:
        soup: BeautifulSoup object of the profile page.

    Returns:
        Email string if found, or empty string if not available.
    """
    try:
        # Look for any text that looks like an email address
        all_text = soup.get_text()
        email_pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        matches = re.findall(email_pattern, all_text)

        # Filter out LinkedIn's own system emails
        filtered = [
            m for m in matches
            if "linkedin.com" not in m and "sentry.io" not in m
        ]

        return filtered[0] if filtered else ""

    except Exception as e:
        logger.warning(f"Could not parse email: {e}")
        return ""


# ── Main Parse Function ───────────────────────────────────────────────────────

def parse_profile(html: str, profile_url: str, keyword: str) -> ProfileData:
    """
    Master function that parses a complete LinkedIn profile page.
    Calls all individual parsers and assembles the final data dict.

    Args:
        html:        Raw HTML string of the profile page.
        profile_url: The LinkedIn URL of this profile.
        keyword:     The search keyword that led to this profile.

    Returns:
        Dictionary with all extracted profile data:
        {
            linkedin_url, full_name, job_title, location,
            about, email, keyword_searched,
            experience: [...],
            posts: [...]
        }
    """
    logger.info(f"Parsing profile: {profile_url}")

    soup = BeautifulSoup(html, "lxml")

    # Build the profile data dictionary
    profile_data: ProfileData = {
        "linkedin_url":     profile_url,
        "full_name":        _parse_name(soup),
        "job_title":        _parse_job_title(soup),
        "location":         _parse_location(soup),
        "about":            _parse_about(soup),
        "email":            _parse_email(soup),
        "keyword_searched": keyword,
        "experience":       _parse_experience(soup),
        "posts":            _parse_posts(soup),
    }

    logger.info(f"Parsed: {profile_data['full_name']} | {profile_data['job_title']}")

    return profile_data