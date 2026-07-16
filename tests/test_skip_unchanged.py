"""Unit tests for _clean_sync_check (percona_obs.cmd_sync).

_clean_sync_check is the shared fast path: it trusts the 'sync: <branch>@<sha>'
OBS revision comment and local git state, returning None (clean) or a reason
string.
"""

from pathlib import Path

import percona_obs.cmd_sync as cmd_sync
from percona_obs.cmd_sync import _clean_sync_check

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
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None


def test_reason_when_comment_not_sync_format(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_package_meaningful_comment", lambda *a: "manual edit"
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None


def test_reason_when_synced_dirty(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (local changes on somehost)",
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None


def test_reason_when_git_changes_since_sha(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(cmd_sync, "_has_package_changes_since", lambda *a: True)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None


def test_reason_when_working_tree_dirty(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(cmd_sync, "_is_path_dirty", lambda *a: True)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None


def test_reason_when_inherited_macros_changed(monkeypatch):
    _patch_git_clean(monkeypatch)
    monkeypatch.setattr(cmd_sync, "_macros_changed_since", lambda *a: True)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meaningful_comment",
        lambda *a: "sync: main@abc1234 (git@github.com:x/y.git)",
    )
    assert _clean_sync_check("http://obs", "prj", "pkg", PKG) is not None
