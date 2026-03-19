"""
database.py
-----------
Handles all database operations using direct PostgreSQL connection.
Uses psycopg2 to connect directly to Supabase's PostgreSQL database.
This is more reliable than the Supabase REST client in restricted networks.
"""

import os
import psycopg2
from typing import Any, cast
from datetime import datetime, timezone
from dotenv import load_dotenv
from .parser import ExperienceEntry, PostEntry, ProfileData
from .logger import logger

load_dotenv()


# ── Connection ────────────────────────────────────────────────────────────────

def get_db_connection() -> psycopg2.extensions.connection:
    """
    Creates a direct PostgreSQL connection to Supabase.
    Reads the database URL from .env file.

    Returns:
        Active psycopg2 connection object.
    """
    db_url = os.getenv("SUPABASE_DB_URL")

    if not db_url:
        raise ValueError(
            "SUPABASE_DB_URL missing from .env file. "
            "Add the PostgreSQL connection string from Supabase dashboard."
        )

    try:
        conn = psycopg2.connect(db_url)
        logger.info("Connected to Supabase database successfully.")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


# ── Keep get_supabase_client as alias so main.py doesn't break ───────────────

def get_supabase_client() -> psycopg2.extensions.connection:
    """
    Alias for get_db_connection.
    Keeps main.py working without changes.
    """
    return get_db_connection()


# ── Scrape Sessions ───────────────────────────────────────────────────────────

def create_scrape_session(
    client: psycopg2.extensions.connection,
    keyword: str,
    profiles_found: int,
) -> int:
    """
    Creates a new scrape session record.

    Args:
        client:         psycopg2 connection.
        keyword:        Search keyword for this session.
        profiles_found: Number of profile URLs found.

    Returns:
        Session ID integer.
    """
    try:
        cursor = cast(Any, client.cursor())
        cursor.execute("""
            INSERT INTO scrape_sessions (keyword, profiles_found, profiles_scraped, status, started_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (keyword, profiles_found, 0, "running", datetime.now(timezone.utc)))

        session_row = cast(tuple[int], cursor.fetchone())
        session_id = int(session_row[0])
        client.commit()
        cursor.close()

        logger.info(f"Scrape session created. Session ID: {session_id}")
        return session_id

    except Exception as e:
        client.rollback()
        logger.error(f"Failed to create scrape session: {e}")
        raise


def finish_scrape_session(
    client: psycopg2.extensions.connection,
    session_id: int,
    profiles_scraped: int,
    status: str = "completed",
) -> None:
    """
    Updates scrape session when done.

    Args:
        client:           psycopg2 connection.
        session_id:       Session to update.
        profiles_scraped: Final count of scraped profiles.
        status:           'completed', 'failed', or 'interrupted'.
    """
    try:
        cursor = cast(Any, client.cursor())
        cursor.execute("""
            UPDATE scrape_sessions
            SET profiles_scraped = %s,
                status           = %s,
                finished_at      = %s
            WHERE id = %s
        """, (profiles_scraped, status, datetime.now(timezone.utc), session_id))

        client.commit()
        cursor.close()
        logger.info(f"Session {session_id} marked as {status}.")

    except Exception as e:
        client.rollback()
        logger.error(f"Failed to update scrape session: {e}")


# ── Profiles ──────────────────────────────────────────────────────────────────

def save_profile(
    client: psycopg2.extensions.connection,
    profile_data: ProfileData,
) -> int | None:
    """
    Saves a LinkedIn profile to the profiles table.
    If profile URL already exists, updates it with fresh data.

    Args:
        client:       psycopg2 connection.
        profile_data: Parsed profile dict from parser.py

    Returns:
        Profile ID if saved, None if failed.
    """
    linkedin_url = profile_data.get("linkedin_url", "")

    try:
        cursor = cast(Any, client.cursor())

        # Check if already exists
        cursor.execute(
            "SELECT id FROM profiles WHERE linkedin_url = %s",
            (linkedin_url,)
        )
        existing = cursor.fetchone()

        if existing:
            # UPDATE existing profile with fresh data
            profile_id = cast(int, existing[0])
            cursor.execute("""
                UPDATE profiles SET
                    full_name        = %s,
                    job_title        = %s,
                    about            = %s,
                    email            = %s,
                    location         = %s,
                    keyword_searched = %s
                WHERE id = %s
            """, (
                profile_data.get("full_name", ""),
                profile_data.get("job_title", ""),
                profile_data.get("about", ""),
                profile_data.get("email", ""),
                profile_data.get("location", ""),
                profile_data.get("keyword_searched", ""),
                profile_id,
            ))
            client.commit()
            cursor.close()
            logger.info(
                f"Profile updated: {profile_data.get('full_name', 'Unknown')} "
                f"(ID: {profile_id})"
            )
            return profile_id

        # INSERT new profile
        cursor.execute("""
            INSERT INTO profiles
                (linkedin_url, full_name, job_title, about, email, location, keyword_searched)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            linkedin_url,
            profile_data.get("full_name", ""),
            profile_data.get("job_title", ""),
            profile_data.get("about", ""),
            profile_data.get("email", ""),
            profile_data.get("location", ""),
            profile_data.get("keyword_searched", ""),
        ))

        profile_row = cast(tuple[int], cursor.fetchone())
        profile_id = int(profile_row[0])
        client.commit()
        cursor.close()

        logger.info(
            f"Profile saved: {profile_data.get('full_name', 'Unknown')} "
            f"(ID: {profile_id})"
        )
        return profile_id

    except Exception as e:
        client.rollback()
        logger.error(f"Failed to save profile {linkedin_url}: {e}")
        return None


# ── Experience ────────────────────────────────────────────────────────────────

def save_experience(
    client: psycopg2.extensions.connection,
    profile_id: int,
    experience_list: list[ExperienceEntry],
) -> None:
    """
    Saves all work experience entries for a profile.

    Args:
        client:          psycopg2 connection.
        profile_id:      Profile ID to link experience to.
        experience_list: List of experience dicts.
    """
    if not experience_list:
        return

    try:
        cursor = cast(Any, client.cursor())

        rows: list[tuple[int, str, str, str, str]] = []
        for job in experience_list:
            rows.append(
                (
                    profile_id,
                    job["company"],
                    job["role"],
                    job["duration"],
                    job["description"],
                )
            )

        cursor.executemany("""
            INSERT INTO experience (profile_id, company, role, duration, description)
            VALUES (%s, %s, %s, %s, %s)
        """, rows)

        client.commit()
        cursor.close()
        logger.info(f"Saved {len(rows)} experience entries for profile ID {profile_id}")

    except Exception as e:
        client.rollback()
        logger.error(f"Failed to save experience for profile ID {profile_id}: {e}")


def clear_experience(client: psycopg2.extensions.connection, profile_id: int) -> None:
    """Deletes existing experience rows for a profile before re-saving."""
    try:
        cursor = cast(Any, client.cursor())
        cursor.execute(
            "DELETE FROM experience WHERE profile_id = %s",
            (profile_id,)
        )
        client.commit()
        cursor.close()
    except Exception as e:
        client.rollback()
        logger.warning(f"Could not clear experience for profile {profile_id}: {e}")


def clear_posts(client: psycopg2.extensions.connection, profile_id: int) -> None:
    """Deletes existing post rows for a profile before re-saving."""
    try:
        cursor = cast(Any, client.cursor())
        cursor.execute(
            "DELETE FROM posts WHERE profile_id = %s",
            (profile_id,)
        )
        client.commit()
        cursor.close()
    except Exception as e:
        client.rollback()
        logger.warning(f"Could not clear posts for profile {profile_id}: {e}")


# ── Posts ─────────────────────────────────────────────────────────────────────

def save_posts(
    client: psycopg2.extensions.connection,
    profile_id: int,
    posts_list: list[PostEntry],
) -> None:
    """
    Saves up to 3 recent posts for a profile.

    Args:
        client:     psycopg2 connection.
        profile_id: Profile ID to link posts to.
        posts_list: List of post dicts.
    """
    if not posts_list:
        return

    try:
        cursor = cast(Any, client.cursor())

        rows: list[tuple[int, str, str, int]] = []
        for post in posts_list[:3]:
            rows.append(
                (
                    profile_id,
                    post["post_text"],
                    post["post_date"],
                    post["post_order"],
                )
            )

        cursor.executemany("""
            INSERT INTO posts (profile_id, post_text, post_date, post_order)
            VALUES (%s, %s, %s, %s)
        """, rows)

        client.commit()
        cursor.close()
        logger.info(f"Saved {len(rows)} posts for profile ID {profile_id}")

    except Exception as e:
        client.rollback()
        logger.error(f"Failed to save posts for profile ID {profile_id}: {e}")


# ── Master Save ───────────────────────────────────────────────────────────────

def save_full_profile(
    client: psycopg2.extensions.connection,
    profile_data: ProfileData,
) -> int | None:
    """
    Saves complete profile including experience and posts.
    Clears old experience and posts before re-saving to prevent duplicates.

    Args:
        client:       psycopg2 connection.
        profile_data: Complete parsed profile dict.

    Returns:
        Profile ID if successful, None if failed.
    """
    profile_id = save_profile(client, profile_data)
    if not profile_id:
        return None

    # Clear old data before re-saving fresh data
    clear_experience(client, profile_id)
    clear_posts(client, profile_id)

    # Save fresh data
    save_experience(client, profile_id, profile_data.get("experience", []))
    save_posts(client, profile_id, profile_data.get("posts", []))

    return profile_id