"""Exponential backoff with jitter for external API calls."""

from __future__ import annotations

import functools
import logging
import random
import time

logger = logging.getLogger(__name__)


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple = (Exception,),
):
    """Decorator for exponential backoff with jitter."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exc = e
                    if attempt == max_attempts - 1:
                        raise
                    delay = min(
                        base_delay * (2**attempt) + random.uniform(0, 1),
                        max_delay,
                    )
                    logger.warning(
                        "%s attempt %d failed: %s. Retrying in %.1fs",
                        func.__name__,
                        attempt + 1,
                        e,
                        delay,
                    )
                    time.sleep(delay)
            raise last_exc

        return wrapper

    return decorator
