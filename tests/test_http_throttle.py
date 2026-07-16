"""Unit tests for the osc HTTP throttle/retry wrapper (percona_obs.http_throttle)."""

import urllib.error

import pytest

import percona_obs.http_throttle as ht


@pytest.fixture(autouse=True)
def _isolate_pacing(monkeypatch):
    """Reset shared pacing state and neutralize real pacing sleeps.

    _defer_all_requests pushes _next_slot into the future on every retryable
    error; with time.sleep mocked, time.monotonic never catches up, so
    without this fixture _pace would really sleep for the backoff duration.
    Pacing-specific tests re-patch _pace_sleep to record delays instead.
    """
    monkeypatch.setattr(ht, "_next_slot", 0.0)
    monkeypatch.setattr(ht, "_pace_sleep", lambda s: None)


def _http_error(code: int, headers: dict | None = None):
    import email.message

    msg = email.message.Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError("http://obs/x", code, "err", msg, None)


def test_retries_on_429_then_succeeds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(ht.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def orig(method, url, *a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)
        return "ok"

    assert ht._request_with_retry(orig, "GET", "http://obs/x") == "ok"
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_honors_retry_after(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(ht.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def orig(method, url, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(503, {"Retry-After": "42"})
        return "ok"

    assert ht._request_with_retry(orig, "GET", "http://obs/x") == "ok"
    assert sleeps == [42.0]


def test_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(ht.time, "sleep", lambda s: None)

    def orig(method, url, *a, **k):
        raise _http_error(429)

    try:
        ht._request_with_retry(orig, "GET", "http://obs/x")
        assert False, "should have raised"
    except urllib.error.HTTPError as e:
        assert e.code == 429


def test_502_retried_for_get_only(monkeypatch):
    monkeypatch.setattr(ht.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def orig(method, url, *a, **k):
        calls["n"] += 1
        raise _http_error(502)

    try:
        ht._request_with_retry(orig, "POST", "http://obs/x")
    except urllib.error.HTTPError:
        pass
    assert calls["n"] == 1  # POST not retried on 502

    calls["n"] = 0
    try:
        ht._request_with_retry(orig, "GET", "http://obs/x")
    except urllib.error.HTTPError:
        pass
    assert calls["n"] == ht._MAX_ATTEMPTS  # GET retried


def test_other_errors_not_retried(monkeypatch):
    calls = {"n": 0}

    def orig(method, url, *a, **k):
        calls["n"] += 1
        raise _http_error(404)

    try:
        ht._request_with_retry(orig, "GET", "http://obs/x")
    except urllib.error.HTTPError:
        pass
    assert calls["n"] == 1


def test_min_interval_parsing(monkeypatch):
    monkeypatch.setenv("PERCONA_OBS_MAX_RPS", "4")
    assert ht._min_interval() == 0.25
    monkeypatch.setenv("PERCONA_OBS_MAX_RPS", "0")
    assert ht._min_interval() == 0.0
    monkeypatch.setenv("PERCONA_OBS_MAX_RPS", "-3")
    assert ht._min_interval() == 0.0
    monkeypatch.setenv("PERCONA_OBS_MAX_RPS", "garbage")
    assert ht._min_interval() == 0.125  # falls back to 8 rps
    monkeypatch.delenv("PERCONA_OBS_MAX_RPS")
    assert ht._min_interval() == 0.125


def test_pace_spaces_consecutive_calls(monkeypatch):
    delays: list[float] = []
    monkeypatch.setattr(ht, "_pace_sleep", lambda s: delays.append(s))
    monkeypatch.setattr(ht.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(ht, "_next_slot", 0.0)
    monkeypatch.delenv("PERCONA_OBS_MAX_RPS", raising=False)  # default 8 rps

    ht._pace()
    assert delays == []  # first call goes through immediately
    ht._pace()
    assert len(delays) == 1
    assert abs(delays[0] - 0.125) < 1e-9  # spaced by the min interval


def test_pace_disabled_skips_sleep_and_slot(monkeypatch):
    delays: list[float] = []
    monkeypatch.setattr(ht, "_pace_sleep", lambda s: delays.append(s))
    monkeypatch.setenv("PERCONA_OBS_MAX_RPS", "0")
    monkeypatch.setattr(ht, "_next_slot", 123.0)  # sentinel

    ht._pace()
    ht._pace()
    assert delays == []
    assert ht._next_slot == 123.0  # slot untouched when pacing is disabled


def test_defer_all_requests_delays_next_pace(monkeypatch):
    delays: list[float] = []
    monkeypatch.setattr(ht, "_pace_sleep", lambda s: delays.append(s))
    monkeypatch.setattr(ht.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(ht, "_next_slot", 0.0)
    monkeypatch.delenv("PERCONA_OBS_MAX_RPS", raising=False)

    ht._defer_all_requests(42.0)
    ht._pace()
    assert len(delays) == 1
    assert abs(delays[0] - 42.0) < 1e-9  # next request start pushed out 42s


def test_install_idempotent(monkeypatch):
    import osc.connection

    original = osc.connection.http_request
    monkeypatch.setattr(ht, "_installed", False)
    try:
        ht.install()
        first_wrap = osc.connection.http_request
        assert first_wrap is not original
        ht.install()
        assert osc.connection.http_request is first_wrap
    finally:
        osc.connection.http_request = original
        ht._installed = False
