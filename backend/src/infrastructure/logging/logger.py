"""Structured logging configuration using structlog.

Rule 18: Mandatory structured JSON logs everywhere.
Never use bare print() or logging.info("string").

Usage:
    from src.infrastructure.logging.logger import get_logger

    logger = get_logger(__name__)
    logger.info("stt.started", job_id=str(job_id), worker="stt")
"""

import logging
import logging.handlers
from pathlib import Path
import sys

import structlog
from structlog.types import EventDict, WrappedLogger


def _add_severity(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Map structlog level names to Google Cloud / Datadog severity labels."""
    level_map = {
        "debug": "DEBUG",
        "info": "INFO",
        "warning": "WARNING",
        "error": "ERROR",
        "critical": "CRITICAL",
    }
    event_dict["severity"] = level_map.get(method_name, "INFO")
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for structured JSON output.

    Call once at application startup before any loggers are created.

    Args:
        log_level: Logging level string e.g. "INFO", "DEBUG", "WARNING".
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _add_severity,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    log_dir = Path("D:/projects/audio-analysis/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "audio_analysis.log", when="midnight", backupCount=14, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "aio_pika", "aiormq"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given module.

    Args:
        name: Module name, typically __name__.

    Returns:
        Bound structlog logger with context binding support.

    Example:
        logger = get_logger(__name__)
        logger.info("job.created", job_id=str(job.id), source_id=str(source_id))
    """
    return structlog.get_logger(name)
