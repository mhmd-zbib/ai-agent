"""
Decorators for embedding service.

Implements Decorator Pattern for adding cross-cutting concerns.
"""

import time
from functools import wraps
from typing import Callable, Any

from app.shared.logging import get_logger

logger = get_logger(__name__)


def with_retry(max_retries: int = 3, delay: float = 1.0):
    """
    Decorator to add retry logic with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        delay: Initial delay between retries in seconds.

    Returns:
        Decorated function with retry logic.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2**attempt)
                        logger.debug(
                            f"Retry attempt {attempt + 1}/{max_retries} after {wait_time}s",
                            extra={"error": str(e), "attempt": attempt + 1},
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"All {max_retries} retry attempts failed",
                            extra={"error": str(e)},
                        )

            raise last_exception  # type: ignore

        return wrapper

    return decorator


def with_timing(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to log execution time of a function.

    Args:
        func: Function to decorate.

    Returns:
        Decorated function with timing logs.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start_time

        logger.debug(
            f"{func.__name__} completed",
            extra={"elapsed_seconds": round(elapsed, 3)},
        )

        return result

    return wrapper


def with_validation(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to validate inputs before processing.

    Args:
        func: Function to decorate.

    Returns:
        Decorated function with input validation.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Extract text argument (handle both positional and keyword args)
        text = None
        if len(args) > 1:
            text = args[1]
        elif "text" in kwargs:
            text = kwargs["text"]
        elif "texts" in kwargs:
            texts = kwargs["texts"]
            if not isinstance(texts, list):
                raise ValueError("texts must be a list")
            if not texts:
                raise ValueError("texts list cannot be empty")

        if text is not None and (not text or not text.strip()):
            raise ValueError("Input text cannot be empty or whitespace only")

        return func(*args, **kwargs)

    return wrapper
