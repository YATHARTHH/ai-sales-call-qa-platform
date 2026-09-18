"""Structured logging configuration with correlation IDs and PII masking."""

import logging
import sys
from typing import Any

import structlog


def mask_sensitive_data(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Ensure raw transcripts, passwords, tokens, and payment card numbers are never logged."""
    sensitive_keys = {
        "password",
        "token",
        "secret",
        "authorization",
        "card_number",
        "cvv",
        "raw_transcript",
        "audio_bytes",
    }
    for key in list(event_dict.keys()):
        if any(s in key.lower() for s in sensitive_keys):
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(log_level: str = "INFO", json_format: bool = True) -> None:
    """Initialize structlog with processors and console/json formatters."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        mask_sensitive_data,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "salescall") -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
