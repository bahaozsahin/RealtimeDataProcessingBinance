"""
Structured JSON logging setup.

Provides a single function to configure logging identically across all services.
Reads log_level from Docker Secrets.

Usage:
    from shared.logging_config import setup_logging

    logger = setup_logging("producer")
"""

from __future__ import annotations

import logging
import sys


JSON_FORMAT = (
    '{"time":"%(asctime)s","level":"%(levelname)s",'
    '"logger":"%(name)s","msg":"%(message)s"}'
)
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(service_name: str, level: str = "INFO") -> logging.Logger:
    """Configure structured JSON logging and return a named logger.

    Args:
        service_name: Logger name (e.g. "producer", "consumer").
        level: Log level string (e.g. "INFO", "DEBUG").

    Returns:
        A configured logger instance.
    """
    logging.basicConfig(
        level=logging.INFO,
        format=JSON_FORMAT,
        datefmt=DATE_FORMAT,
        stream=sys.stdout,
    )

    logger = logging.getLogger(service_name)
    logger.setLevel(level.upper())
    return logger
