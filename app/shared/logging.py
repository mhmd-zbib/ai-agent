import logging
import logging.config
import traceback
from datetime import datetime, UTC


class DetailedFormatter(logging.Formatter):
    """Formats logs as readable text with full details and tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        # Build timestamp
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        # Build base log message
        log_msg = f"{timestamp} | {record.levelname:<8} | {record.name} | {record.getMessage()}"

        # Add extra context if present
        if hasattr(record, "extra") and record.extra:
            extra_parts = []
            for key, value in record.extra.items():
                if isinstance(value, (dict, list)):
                    extra_parts.append(f"{key}={repr(value)}")
                else:
                    extra_parts.append(f"{key}={value}")
            if extra_parts:
                log_msg += " | " + " | ".join(extra_parts)

        # Add exception traceback if present
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
            log_msg += "\n" + "".join(tb_lines)

        return log_msg


def configure_logging(level: str = "INFO") -> None:
    """Configure readable text logging."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "detailed": {
                    "()": DetailedFormatter,
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "detailed",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {
                "handlers": ["default"],
                "level": level.upper(),
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance."""
    return logging.getLogger(name)


