import logging
import logging.config
import sys
import traceback
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# ANSI color codes
# ---------------------------------------------------------------------------
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

_LEVEL_COLORS = {
    "DEBUG": "\033[96m",  # bright cyan
    "INFO": "\033[92m",  # bright green
    "WARNING": "\033[93m",  # bright yellow
    "ERROR": "\033[91m",  # bright red
    "CRITICAL": "\033[95m",  # bright magenta + bold
}

# ---------------------------------------------------------------------------
# Standard LogRecord fields — we skip these when extracting user extras
# ---------------------------------------------------------------------------
_LOGRECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "relativeCreated",
        "thread",
        "threadName",
        "process",
        "processName",
        "pathname",
        "filename",
        "module",
        "funcName",
        "lineno",
        "exc_info",
        "exc_text",
        "stack_info",
        "levelname",
        "levelno",
        "msecs",
        "message",
        "taskName",
    }
)

# ---------------------------------------------------------------------------
# Logger name → short label mapping
# ---------------------------------------------------------------------------
_KNOWN_NAMES: dict[str, str] = {
    "uvicorn.access": "http",
    "uvicorn.error": "uvicorn",
    "uvicorn": "uvicorn",
    "httpx": "httpx",
}

_SKIP_SEGMENTS = frozenset(
    {
        "app",
        "modules",
        "services",
        "repositories",
        "infrastructure",
        "shared",
    }
)


def _shorten_name(name: str) -> str:
    if name in _KNOWN_NAMES:
        return _KNOWN_NAMES[name]
    parts = name.split(".")
    meaningful = [p for p in parts if p not in _SKIP_SEGMENTS]
    if not meaningful:
        return name
    return ".".join(meaningful[-2:]) if len(meaningful) >= 2 else meaningful[0]


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


class AppFormatter(logging.Formatter):
    """
    Colored, structured formatter.

    - Extracts all user-supplied extra={} fields and appends them as
      key=value pairs (Python logging puts them directly on the record).
    - Falls back to plain text when stdout is not a TTY (e.g. Docker logs).
    """

    _color: bool = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        level = record.levelname
        name = _shorten_name(record.name)
        msg = record.getMessage()

        # Collect extras (any attribute not part of the base LogRecord schema)
        extras: list[str] = []
        for key, val in record.__dict__.items():
            if key.startswith("_") or key in _LOGRECORD_ATTRS:
                continue
            formatted = repr(val) if isinstance(val, (dict, list)) else str(val)
            extras.append(f"{key}={formatted}")

        if self._color:
            color = _LEVEL_COLORS.get(level, "")
            level_str = f"{color}{_BOLD}{level:<8}{_RESET}"
            name_str = f"\033[34m{_BOLD}{name:<22}{_RESET}"
            extra_str = (
                "  " + "  ".join(f"{_DIM}{e}{_RESET}" for e in extras) if extras else ""
            )
        else:
            level_str = f"{level:<8}"
            name_str = f"{name:<22}"
            extra_str = ("  " + "  ".join(extras)) if extras else ""

        line = f"{ts}  {level_str}  {name_str}  {msg}{extra_str}"

        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            line += "\n" + "".join(
                traceback.format_exception(exc_type, exc_value, exc_tb)
            )

        return line


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def configure_logging(level: str = "INFO") -> None:
    """
    Configure unified logging for the app and uvicorn.

    Uvicorn loggers are explicitly registered with propagate=False so their
    access/error messages go through our formatter and never double-print via
    the root handler.
    """
    lvl = level.upper()
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "app": {"()": AppFormatter},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "app",
                    "stream": "ext://sys.stdout",
                }
            },
            "loggers": {
                # Uvicorn — override their format and stop propagation so we
                # don't see the old "INFO:     ip - ..." style lines.
                "uvicorn": {
                    "handlers": ["console"],
                    "level": lvl,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["console"],
                    "level": lvl,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": lvl,
                    "propagate": False,
                },
                # External libs — keep at WARNING to reduce noise
                "httpx": {
                    "handlers": ["console"],
                    "level": "WARNING",
                    "propagate": False,
                },
            },
            "root": {
                "handlers": ["console"],
                "level": lvl,
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
