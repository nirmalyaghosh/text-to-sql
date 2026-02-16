"""
Centralized logging configuration.

Configures a TimedRotatingFileHandler using LOG_FILES_DIR_PATH
and LOG_FILE_NAME from environment variables.
"""

import logging
import os

from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


_configured = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def setup_logging(level: int = logging.INFO):
    """
    Configure the root logger with a TimedRotatingFileHandler.
    Log directory and file name are read from environment variables.
    """
    global _configured
    if _configured:
        return
    _configured = True

    log_dir = os.getenv("LOG_FILES_DIR_PATH", "logs")
    log_file = os.getenv("LOG_FILE_NAME", "text_to_sql.log")

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(log_dir) / log_file

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = TimedRotatingFileHandler(
        filename=str(log_path),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
