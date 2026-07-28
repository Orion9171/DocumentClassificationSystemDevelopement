from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


_CONFIGURED = False


def configure_logging(base_dir: Optional[str] = None) -> None:
    """Configure rotating application logs once per process.

    Log files intentionally contain operational metadata only. Callers must not
    log passwords, tokens, full email bodies, or document contents.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    root_dir = os.path.abspath(base_dir or os.path.dirname(__file__))
    log_dir = os.path.join(root_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    app_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    app_handler.setFormatter(formatter)
    app_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(app_handler)

    email_handler = RotatingFileHandler(
        os.path.join(log_dir, "email.log"),
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    email_handler.setFormatter(formatter)
    email_handler.setLevel(logging.INFO)

    email_logger = logging.getLogger("email")
    email_logger.setLevel(logging.INFO)
    email_logger.propagate = False
    email_logger.addHandler(email_handler)

    _CONFIGURED = True
