"""Structured logging configuration for the Spondex daemon.

Sets up two log streams via ``RotatingFileHandler``:

- ``daemon.log`` — human-readable, all log events
- ``sync.log`` — JSON-formatted, only ``spondex.sync.*`` events

Both handlers rotate at 10 MB with 5 backup files.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5

# Shared structlog pre-processors (used for both structlog-originated
# events and stdlib-originated "foreign" events).
_shared_processors: list[structlog.types.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.stdlib.ExtraAdder(),
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.UnicodeDecoder(),
]


def setup_logging(log_level: str = "info", log_dir: Path | None = None) -> None:
    """Configure structlog and stdlib logging for the daemon.

    Parameters
    ----------
    log_level:
        Python log-level name (``debug``, ``info``, ``warning``, etc.).
    log_dir:
        Directory for log files.  When *None* no file handlers are created
        (useful for testing).
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # -- structlog pipeline (structlog → stdlib bridge) ---------------------
    structlog.configure(
        processors=[
            *_shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # -- formatters --------------------------------------------------------
    human_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=False),
        foreign_pre_chain=_shared_processors,
    )
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=_shared_processors,
    )

    # -- root logger -------------------------------------------------------
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)

        # daemon.log — all events, human-readable
        daemon_handler = RotatingFileHandler(
            log_dir / "daemon.log",
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        daemon_handler.setFormatter(human_formatter)
        root.addHandler(daemon_handler)

        # sync.log — sync events only, JSON
        sync_handler = RotatingFileHandler(
            log_dir / "sync.log",
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        sync_handler.setFormatter(json_formatter)
        sync_handler.addFilter(logging.Filter("spondex.sync"))
        root.addHandler(sync_handler)

    # -- suppress noisy third-party loggers --------------------------------
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(max(level, logging.WARNING))

    # -- catch unhandled exceptions ----------------------------------------
    def _excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: object,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)  # type: ignore[arg-type]
            return
        logging.getLogger("spondex").critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_tb),
        )

    sys.excepthook = _excepthook  # type: ignore[assignment]
