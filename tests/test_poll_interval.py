"""Unit tests for the poll-interval backoff helper (percona_obs.common)."""

from percona_obs.common import next_poll_interval


def test_ramps_up_when_unchanged():
    assert next_poll_interval(30, changed=False, base=30, cap=300) == 45
    assert next_poll_interval(45, changed=False, base=30, cap=300) == 67


def test_caps_at_max():
    assert next_poll_interval(280, changed=False, base=30, cap=300) == 300
    assert next_poll_interval(300, changed=False, base=30, cap=300) == 300


def test_resets_on_change():
    assert next_poll_interval(300, changed=True, base=30, cap=300) == 30
