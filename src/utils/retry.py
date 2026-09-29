"""
One retry policy, reused by every external client (LLM, Firecrawl,
Serper, Pexels), so failure handling is consistent across the whole
pipeline instead of copy-pasted per client.
"""
from __future__ import annotations

import functools
from typing import Callable, Tuple, Type

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
    RetryError,
)
import logging

from src.config import settings

logger = logging.getLogger("retry")


def with_retries(
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable:
    """
    Decorator factory. Wraps a function that calls an external API with:
      - exponential backoff + jitter (avoids thundering-herd retries)
      - a hard cap on attempts, so a dead upstream fails loudly instead
        of hanging forever
      - a log line before every retry sleep, so retries are visible in
        the trace instead of silently eating latency
    """

    def decorator(func: Callable) -> Callable:
        @retry(
            # reraise=False so callers get RetryError and can convert it
            # to UpstreamFailure via exhausted() — the pattern every
            # client already uses.
            reraise=False,
            stop=stop_after_attempt(settings.max_retries),
            wait=wait_exponential_jitter(
                initial=settings.retry_min_wait_seconds,
                max=settings.retry_max_wait_seconds,
            ),
            retry=retry_if_exception_type(exceptions),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


class UpstreamFailure(RuntimeError):
    """Raised when an external API keeps failing after every retry attempt.

    Deliberately distinct from RetryError so calling code (agent nodes)
    can catch one clean exception type instead of reaching into tenacity
    internals.
    """


def exhausted(retry_error: RetryError, service: str) -> UpstreamFailure:
    last_exc = retry_error.last_attempt.exception()
    return UpstreamFailure(
        f"{service} failed after {settings.max_retries} attempts: {last_exc}"
    )
