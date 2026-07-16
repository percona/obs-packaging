"""Global client-side pacing and retry for all osc HTTP requests.

install() wraps osc.connection.http_request; osc's http_GET/PUT/POST/DELETE
resolve that name at call time, so a single patch covers every request made
through osc (including osc.core.show_* helpers).

Pacing: a minimum interval of 1 / PERCONA_OBS_MAX_RPS seconds between request
starts, shared across threads (default 8 rps; set 0 to disable).  This
reshapes thread-pool bursts into a steady stream that OBS traffic limiters
tolerate.

Retry: 429 and 503 are retried for every method (the request was not
processed); 502/504 only for GET (a proxy may have processed a POST).
Retry-After is honored when present, otherwise exponential backoff capped at
60 s, up to 5 attempts.
"""

import os
import threading
import time
import urllib.error

import osc.connection

from .common import logger

_RETRY_ALL = {429, 503}
_RETRY_GET_ONLY = {502, 504}
_MAX_ATTEMPTS = 5

_pace_lock = threading.Lock()
_next_slot = 0.0
_installed = False

# Bound at import time: pacing sleeps are an implementation detail and must
# not be intercepted when tests monkeypatch time.sleep to observe retry
# backoff delays.
_pace_sleep = time.sleep


def _min_interval() -> float:
    raw = os.environ.get("PERCONA_OBS_MAX_RPS", "8")
    try:
        rps = float(raw)
    except ValueError:
        rps = 8.0
    return 1.0 / rps if rps > 0 else 0.0


def _pace() -> None:
    """Block until this thread may start a request (shared min-interval)."""
    global _next_slot
    interval = _min_interval()
    if interval <= 0:
        return
    with _pace_lock:
        now = time.monotonic()
        start = max(now, _next_slot)
        _next_slot = start + interval
    delay = start - now
    if delay > 0:
        _pace_sleep(delay)


def _retry_delay(e: urllib.error.HTTPError, attempt: int) -> float:
    try:
        retry_after = float(e.headers.get("Retry-After") or 0)
    except (TypeError, ValueError):
        retry_after = 0.0
    return retry_after if retry_after > 0 else float(min(2**attempt, 60))


def _request_with_retry(orig, method: str, url: str, *args, **kwargs):
    retry_codes = _RETRY_ALL | (_RETRY_GET_ONLY if method == "GET" else set())
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        _pace()
        try:
            return orig(method, url, *args, **kwargs)
        except urllib.error.HTTPError as e:
            if e.code not in retry_codes or attempt == _MAX_ATTEMPTS:
                raise
            delay = _retry_delay(e, attempt)
            logger.warning(
                f"OBS returned HTTP {e.code} for {method} {url}; "
                f"retrying in {delay:.0f}s ({attempt}/{_MAX_ATTEMPTS})"
            )
            time.sleep(delay)
    raise AssertionError("unreachable")


def install() -> None:
    """Patch osc.connection.http_request with the paced, retrying wrapper."""
    global _installed
    if _installed:
        return
    _installed = True
    orig = osc.connection.http_request

    def throttled(method, url, *args, **kwargs):
        return _request_with_retry(orig, method, url, *args, **kwargs)

    osc.connection.http_request = throttled
