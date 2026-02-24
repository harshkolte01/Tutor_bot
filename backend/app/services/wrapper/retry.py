"""
Retry helper for the wrapper HTTP client.

Usage:
    response = call_with_retry(fn, max_retries=3, base_delay=1.0)

`fn` must be a zero-argument callable that returns a requests.Response.
Retries are attempted on status codes 429, 502, 503, 504.
Backoff is exponential with full jitter:
    sleep = random(0, base_delay * 2 ** attempt)
For 429 responses the Retry-After header is respected when present.
"""

import random
import time
import logging

log = logging.getLogger(__name__)

RETRYABLE_STATUSES = {429, 502, 503, 504}


def call_with_retry(fn, max_retries: int = 3, base_delay: float = 1.0):
    """
    Call `fn()` and retry up to `max_retries` times on retryable HTTP status.

    Parameters
    ----------
    fn : callable() -> requests.Response
    max_retries : int   maximum retry attempts (not counting the first call)
    base_delay  : float base sleep time in seconds for backoff calculation

    Returns
    -------
    requests.Response   the first successful (non-retryable) response

    Raises
    ------
    requests.exceptions.RequestException  on network-level failure after retries
    The last response is returned even if its status is retryable (caller decides
    whether to raise on it).
    """
    last_response = None
    for attempt in range(max_retries + 1):
        try:
            response = fn()
        except Exception:
            if attempt < max_retries:
                _sleep(base_delay, attempt)
                continue
            raise

        last_response = response

        if response.status_code not in RETRYABLE_STATUSES:
            return response

        if attempt >= max_retries:
            log.warning(
                "wrapper: status %s still retryable after %d attempts, giving up",
                response.status_code,
                attempt + 1,
            )
            return response

        delay = _compute_delay(response, base_delay, attempt)
        log.info(
            "wrapper: status %s on attempt %d/%d, retrying in %.2fs",
            response.status_code,
            attempt + 1,
            max_retries + 1,
            delay,
        )
        time.sleep(delay)

    return last_response  # unreachable in practice but satisfies type checkers


def _compute_delay(response, base_delay: float, attempt: int) -> float:
    """Exponential backoff with full jitter; honour Retry-After when present."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    cap = base_delay * (2 ** attempt)
    return random.uniform(0, cap)


def _sleep(base_delay: float, attempt: int) -> None:
    cap = base_delay * (2 ** attempt)
    time.sleep(random.uniform(0, cap))
