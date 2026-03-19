"""
logger.py
---------
Sets up a centralized logger for the entire project.
Every module imports and uses this same logger.
Logs are written to both the terminal and a daily log file.
"""

import logging
import os
from datetime import datetime


def setup_logger(name: str = "linkedin_scraper") -> logging.Logger:
    """
    Creates and configures the application logger.

    Args:
        name: Name of the logger instance.

    Returns:
        Configured logger object.
    """

    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # Log file named by today's date e.g. 2024-03-19.log
    log_filename = os.path.join(logs_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    # ── Format ──────────────────────────────────────────────
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(module)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # ── Terminal Handler (shows logs in terminal) ────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # ── File Handler (saves logs to file) ───────────────────
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Attach both handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Single shared logger instance used across all modules
logger = setup_logger()