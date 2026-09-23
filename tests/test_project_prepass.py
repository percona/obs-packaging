"""Unit tests for the project pre-pass skip logic (percona_obs.cmd_sync)."""

from percona_obs.cmd_sync import _can_skip_project_apply


def test_skip_when_unchanged_existing_plain_push():
    assert _can_skip_project_apply((False, False), None, False) is True


def test_no_skip_when_changed():
    assert _can_skip_project_apply((True, False), None, False) is False


def test_no_skip_when_new():
    assert _can_skip_project_apply((True, True), None, False) is False
    assert _can_skip_project_apply((False, True), None, False) is False


def test_no_skip_without_verdict():
    assert _can_skip_project_apply(None, None, False) is False


def test_no_skip_in_branch_mode():
    assert _can_skip_project_apply((False, False), "isv:percona", False) is False


def test_no_skip_with_force():
    assert _can_skip_project_apply((False, False), None, True) is False
