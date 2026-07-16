"""Unit tests for _clean_sync_check (percona_obs.cmd_sync).

_clean_sync_check is the shared fast path: it trusts the 'sync: <branch>@<sha>'
OBS revision comment and local git state, returning None (clean) or a reason
string.
"""

from pathlib import Path

import percona_obs.cmd_sync as cmd_sync
from percona_obs.cmd_sync import _clean_sync_check, _resolve_skip_decision

PKG = Path("/repo/root/ppg/17/percona-pgaudit")


def _patch_git_clean(monkeypatch):
    monkeypatch.setattr(cmd_sync, "_has_package_changes_since", lambda *a: False)
    monkeypatch.setattr(cmd_sync, "_is_path_dirty", lambda *a: False)
    monkeypatch.setattr(cmd_sync, "_macros_changed_since", lambda *a: False)


def test_clean_when_sync_comment_and_no_changes(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is None


def test_reason_when_no_comment(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_package_meaningful_comment", lambda *a: None
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) == "no revision comment"


def test_reason_when_comment_not_sync_format(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_package_meaningful_comment", lambda *a: "manual edit"
    )
    assert (
        _clean_sync_check("http://obs", "prj", "pkg", PKG)
        == "comment is not a sync message: 'manual edit'"
    )


def test_reason_when_synced_dirty(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (local changes on somehost)",
    )
    assert (
        _clean_sync_check("http://obs", "prj", "pkg", PKG) == "synced dirty at abc1234"
    )


def test_reason_when_git_changes_since_sha(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(cmd_sync, "_has_package_changes_since", lambda *a: True)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert (
        _clean_sync_check("http://obs", "prj", "pkg", PKG)
        == "git changes since abc1234"
    )


def test_reason_when_working_tree_dirty(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(cmd_sync, "_is_path_dirty", lambda *a: True)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert (
        _clean_sync_check("http://obs", "prj", "pkg", PKG)
        == "uncommitted changes in package directory"
    )


def test_reason_when_inherited_macros_changed(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(cmd_sync, "_macros_changed_since", lambda *a: True)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert (
        _clean_sync_check("http://obs", "prj", "pkg", PKG) == "inherited macros changed"
    )


def test_sha_from_comment_is_passed_to_git_checks(monkeypatch):
    _patch_git_clean(monkeypatch)
    seen: list[str] = []

    def _record(sha, path):
        seen.append(sha)
        return False

    monkeypatch.setattr(cmd_sync, "_has_package_changes_since", _record)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is None
    assert seen == ["abc1234"]


def test_dirty_sync_short_circuits_before_git_checks(monkeypatch):
    _patch_git_clean(monkeypatch)

    def _boom(*a):
        raise AssertionError("_has_package_changes_since must not be called")

    monkeypatch.setattr(cmd_sync, "_has_package_changes_since", _boom)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (local changes on somehost)",
    )
    assert (
        _clean_sync_check("http://obs", "prj", "pkg", PKG) == "synced dirty at abc1234"
    )


def test_skip_decision_true_when_clean(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert _resolve_skip_decision("http://obs", "prj", "pkg", PKG) is True


def test_skip_decision_false_when_unclean(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_package_meaningful_comment", lambda *a: None
    )
    assert _resolve_skip_decision("http://obs", "prj", "pkg", PKG) is False
