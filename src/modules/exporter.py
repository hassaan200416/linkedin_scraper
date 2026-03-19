"""
exporter.py
-----------
Exports all scraped data from Supabase to a CSV file.
Fetches profiles, experience, and posts then joins
them into a single flat CSV that can be opened in Excel.

Output file is saved to the output/ folder with a
timestamp in the filename so each export is unique.
"""

import os
import pandas as pd
import psycopg2.extras
import psycopg2.extensions
from datetime import datetime
from typing import Any, TypedDict
from .logger import logger


# ── Constants ─────────────────────────────────────────────────────────────────

OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "output"
)


class ProfileRow(TypedDict):
    id: int
    full_name: str
    job_title: str
    location: str
    email: str
    about: str
    linkedin_url: str
    keyword_searched: str
    scraped_at: str


class ExperienceRow(TypedDict):
    role: str
    company: str
    duration: str


class PostRow(TypedDict):
    post_text: str
    post_order: int


class FlatExportRow(TypedDict):
    full_name: str
    job_title: str
    location: str
    email: str
    about: str
    experience: str
    post_1: str
    post_2: str
    post_3: str
    linkedin_url: str
    keyword_searched: str
    scraped_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_all_profiles(client: psycopg2.extensions.connection) -> list[dict[str, Any]]:
    """
    Fetches all rows from the profiles table in Supabase.

    Args:
        client: Connected Supabase client.

    Returns:
        List of profile dicts.
    """
    cursor = client.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM profiles")
    rows = cursor.fetchall()
    cursor.close()
    return [dict(r) for r in rows]


def _fetch_experience_for_profile(
    client: psycopg2.extensions.connection,
    profile_id: int,
) -> list[dict[str, Any]]:
    """
    Fetches all experience rows for a given profile ID.

    Args:
        client:     Connected Supabase client.
        profile_id: Profile ID to fetch experience for.

    Returns:
        List of experience dicts.
    """
    cursor = client.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM experience WHERE profile_id = %s", (profile_id,))
    rows = cursor.fetchall()
    cursor.close()
    return [dict(r) for r in rows]


def _fetch_posts_for_profile(
    client: psycopg2.extensions.connection,
    profile_id: int,
) -> list[dict[str, Any]]:
    """
    Fetches up to 3 posts for a given profile ID.

    Args:
        client:     Connected Supabase client.
        profile_id: Profile ID to fetch posts for.

    Returns:
        List of post dicts ordered by post_order.
    """
    cursor = client.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        "SELECT * FROM posts WHERE profile_id = %s ORDER BY post_order",
        (profile_id,)
    )
    rows = cursor.fetchall()
    cursor.close()
    return [dict(r) for r in rows]


def _flatten_profile(
    profile: dict[str, Any],
    experience: list[dict[str, Any]],
    posts: list[dict[str, Any]],
) -> FlatExportRow:
    """
    Flattens a profile with its experience and posts
    into a single dictionary row for the CSV.

    Experience jobs are joined into one string.
    Posts are put into separate columns (post_1, post_2, post_3).

    Args:
        profile:    Profile dict from profiles table.
        experience: List of experience dicts.
        posts:      List of post dicts.

    Returns:
        Single flat dict ready for CSV export.
    """

    # Join all experience into readable string
    # e.g. "Software Engineer @ Google (2020-2023) | PM @ Meta (2018-2020)"
    experience_str = " | ".join([
        f"{str(job.get('role', ''))} @ {str(job.get('company', ''))} ({str(job.get('duration', ''))})"
        for job in experience
        if job.get("role") or job.get("company")
    ])

    # Posts into separate columns
    posts_sorted = sorted(posts, key=lambda p: int(p.get("post_order", 0)))
    post_1 = str(posts_sorted[0].get("post_text", "")) if len(posts_sorted) > 0 else ""
    post_2 = str(posts_sorted[1].get("post_text", "")) if len(posts_sorted) > 1 else ""
    post_3 = str(posts_sorted[2].get("post_text", "")) if len(posts_sorted) > 2 else ""

    return {
        "full_name":        str(profile.get("full_name", "")),
        "job_title":        str(profile.get("job_title", "")),
        "location":         str(profile.get("location", "")),
        "email":            str(profile.get("email", "")),
        "about":            str(profile.get("about", "")),
        "experience":       experience_str,
        "post_1":           post_1,
        "post_2":           post_2,
        "post_3":           post_3,
        "linkedin_url":     str(profile.get("linkedin_url", "")),
        "keyword_searched": str(profile.get("keyword_searched", "")),
        "scraped_at":       str(profile.get("scraped_at", "")),
    }


# ── Main Export Function ──────────────────────────────────────────────────────

def export_to_csv(client: psycopg2.extensions.connection, keyword: str = "all") -> str:
    """
    Fetches all data from Supabase and exports it to a CSV file.
    Each row in the CSV is one LinkedIn profile with all their
    data flattened into columns.

    Args:
        client:  Connected Supabase client.
        keyword: Used in the filename to identify what was searched.
                 Defaults to 'all' if exporting everything.

    Returns:
        Full path to the exported CSV file.
    """

    logger.info("Starting CSV export from Supabase...")

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Fetch all profiles ────────────────────────────────────
    profiles = _fetch_all_profiles(client)

    if not profiles:
        logger.warning("No profiles found in database to export.")
        return ""

    logger.info(f"Fetched {len(profiles)} profiles from Supabase.")

    # ── Build flat rows ───────────────────────────────────────
    rows: list[FlatExportRow] = []

    for profile in profiles:
        profile_id = int(profile.get("id", 0))

        # Fetch related experience and posts
        experience = _fetch_experience_for_profile(client, profile_id)
        posts      = _fetch_posts_for_profile(client, profile_id)

        # Flatten into single row
        flat_row = _flatten_profile(profile, experience, posts)
        rows.append(flat_row)

    # ── Convert to DataFrame and save CSV ─────────────────────
    df = pd.DataFrame(rows)

    # Timestamp in filename — each export is unique
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    keyword_clean = keyword.replace(" ", "_").lower()
    filename  = f"linkedin_{keyword_clean}_{timestamp}.csv"
    filepath  = os.path.join(OUTPUT_DIR, filename)

    df.to_csv(filepath, index=False, encoding="utf-8-sig")

    logger.info(f"CSV exported successfully: {filepath}")
    logger.info(f"Total rows exported: {len(rows)}")

    return filepath