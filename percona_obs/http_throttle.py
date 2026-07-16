"""Global client-side pacing and retry for all osc HTTP requests.

install() wraps osc.connection.http_request; osc's http_GET/PUT/POST/DELETE
resolve that name at call time, so a single patch covers every request made
through osc, including the osc.core.show_* helpers.  (One known exception:
osc.core imports http_request by value at core.py:48, and one direct call
site — show_devel_project — uses that binding and bypasses the patch.  That
path is unused by this repo.)

Pacing: a minimum interval of 1 / PERCONA_OBS_MAX_RPS seconds between request
starts, shared across threads (default 8 rps; set 0 to disable).  This
reshapes thread-pool bursts into a steady stream that OBS traffic limiters
tolerate.

Retry: this wrapper sits ON TOP of osc's built-in urllib3 retry layer.  osc
builds its connection pools with urllib3.Retry(total=http_retries (default
3), backoff_factor=2, status_forcelist=(500, 502, 503),
allowed_methods=None, raise_on_status=False) — see osc/connection.py.
Consequences:

* urllib3 already retries 500/502/503 for ALL methods (allowed_methods=None)
  and honors Retry-After itself; those inner retries are NOT paced by this
  module.
* Outer attempts multiply the inner ones: a persistently 503ing server costs
  up to 5 outer x 4 inner = 20 wire requests before we give up.
* 429 is clean: it is not in the inner forcelist, so it is handled solely by
  this wrapper.
* The GET-only restriction for 502/504 below therefore describes the OUTER
  layer only; urllib3 may already have retried a POST on 502 internally.

Outer retry policy: 429 and 503 are retried for every method (the server
says it did not process the request); 502/504 only for GET (a proxy may have
processed a POST).  Retry-After is honored when present (capped at 300 s),
otherwise exponential backoff capped at 60 s, up to 5 attempts.  On every
retryable error the SHARED pacing slot is pushed forward so all threads back
off, not just the one that was throttled.

We deliberately do not lower osc's http_retries: this wrapper does not catch
URLError, so the inner connection-level retries are still wanted.
"""

import functools
import os
import threading
import time
import urllib.error

import osc.connection

from .common import logger

_RETRY_ALL = {429, 503}
_RETRY_GET_ONLY = {502, 504}
_MAX_ATTEMPTS = 5
_RETRY_AFTER_CAP = 300.0

_pace_lock = threading.Lock()
_next_slot = 0.0
_installed = False

# Bound at import time: pacing sleeps are an implementation detail and must
# not be intercepted when tests monkeypatch time.sleep to observe retry
# backoff delays.  Do not replace `_pace_sleep(...)` with `time.sleep(...)`
# here, nor the `time.sleep` in `_request_with_retry` with `_pace_sleep` —
# the asymmetry is load-bearing for the tests.
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


def _defer_all_requests(delay: float) -> None:
    """Push the shared pacing slot forward: a 429/503 means the server wants
    less traffic from the whole process, not just this thread.

    Called unconditionally on retryable errors; harmless when pacing is
    disabled because _pace() early-returns without reading the slot.
    """
    global _next_slot
    with _pace_lock:
        _next_slot = max(_next_slot, time.monotonic() + delay)


def _retry_delay(e: urllib.error.HTTPError, attempt: int) -> float:
    try:
        retry_after = float((e.headers.get("Retry-After") if e.headers else None) or 0)
    except (TypeError, ValueError):
        # HTTP-date Retry-After forms deliberately fall through to the
        # exponential-backoff fallback.
        retry_after = 0.0
    return (
        min(retry_after, _RETRY_AFTER_CAP)
        if retry_after > 0
        else float(min(2**attempt, 60))
    )


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
            _defer_all_requests(delay)
            time.sleep(delay)
    raise AssertionError("unreachable")


def install() -> None:
    """Patch osc.connection.http_request with the paced, retrying wrapper."""
    global _installed
    if _installed:
        return
    orig = osc.connection.http_request

    @functools.wraps(orig)
    def throttled(method, url, *args, **kwargs):
        return _request_with_retry(orig, method, url, *args, **kwargs)

    osc.connection.http_request = throttled
    _installed = True
