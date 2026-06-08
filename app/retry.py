from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from app.logging_utils import get_logger


T = TypeVar("T")

logger = get_logger(__name__)


def retry_call(
    operation: str,
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 1.0,
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if attempt == attempts:
                break
            delay = base_delay_seconds * (2 ** (attempt - 1))
            logger.warning(
                "retrying operation after failure",
                extra={
                    "_operation": operation,
                    "_attempt": attempt,
                    "_attempts": attempts,
                    "_retry_delay_seconds": delay,
                    "_error": str(exc),
                },
            )
            if delay > 0:
                time.sleep(delay)

    assert last_exc is not None
    raise last_exc
