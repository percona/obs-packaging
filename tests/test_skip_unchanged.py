"""Unit tests for the --skip-unchanged fast path (percona_obs.cmd_sync).

_clean_sync_check is the shared fast path: it trusts the 'sync: <branch>@<sha>'
OBS revision comment and local git state, returning None (clean) or a reason
string.  _resolve_skip_decision wraps it for plain pushes, and
_has_moving_upstream_ref guards against freezing packages whose _service
tracks a moving upstream ref (branch or default HEAD).
"""

import subprocess
from pathlib import Path

import percona_obs.cmd_sync as cmd_sync
from percona_obs.cmd_sync import _clean_sync_check, _resolve_skip_decision
from percona_obs.services import upstream_scm_refs

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
        _clean_sync_check("http://obs", "prj", "pkg", PKG)
        == "referenced macros changed"
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


# --- upstream_scm_refs ---


def test_upstream_scm_refs_substitutes_and_excludes_packaging(tmp_path):
    svc = tmp_path / "_service"
    svc.write_text(
        "<services>"
        '<service name="obs_scm">'
        '<param name="url">https://github.com/x/y.git</param>'
        '<param name="revision">v%!{FOO_VERSION}</param>'
        "</service>"
        '<service name="obs_scm">'
        '<param name="url">https://github.com/p/packaging.git</param>'
        '<param name="subdir">root/ppg/17/pkg/debian</param>'
        "</service>"
        "</services>"
    )
    assert upstream_scm_refs(svc, macros={"FOO_VERSION": "1.2.3"}) == [
        ("https://github.com/x/y.git", "v1.2.3")
    ]


def test_upstream_scm_refs_empty_revision_when_param_missing(tmp_path):
    svc = tmp_path / "_service"
    svc.write_text(
        "<services>"
        '<service name="obs_scm">'
        '<param name="url">https://github.com/x/y.git</param>'
        "</service>"
        "</services>"
    )
    assert upstream_scm_refs(svc) == [("https://github.com/x/y.git", "")]


# --- _classify_remote_ref ---


class _Proc:
    def __init__(self, stdout=b"", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def test_classify_remote_ref_branch_when_head_matches(monkeypatch):
    monkeypatch.setattr(cmd_sync, "_ref_types", {})
    monkeypatch.setattr(
        cmd_sync.subprocess,
        "run",
        lambda *a, **k: _Proc(stdout=b"abc123\trefs/heads/main\n"),
    )
    assert cmd_sync._classify_remote_ref("http://r/branch.git", "main") == "branch"
    assert cmd_sync._ref_types == {"http://r/branch.git|main": "branch"}


def test_classify_remote_ref_tag_when_no_head_matches(monkeypatch):
    monkeypatch.setattr(cmd_sync, "_ref_types", {})
    monkeypatch.setattr(cmd_sync.subprocess, "run", lambda *a, **k: _Proc())
    assert cmd_sync._classify_remote_ref("http://r/tag.git", "v1.0") == "tag"
    assert cmd_sync._ref_types == {"http://r/tag.git|v1.0": "tag"}


def test_classify_remote_ref_error_is_branch_and_uncached(monkeypatch):
    monkeypatch.setattr(cmd_sync, "_ref_types", {})

    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=15)

    monkeypatch.setattr(cmd_sync.subprocess, "run", _raise)
    assert cmd_sync._classify_remote_ref("http://r/err.git", "main") == "branch"
    assert cmd_sync._ref_types == {}


def test_classify_remote_ref_nonzero_exit_is_branch_and_uncached(monkeypatch):
    monkeypatch.setattr(cmd_sync, "_ref_types", {})
    monkeypatch.setattr(
        cmd_sync.subprocess, "run", lambda *a, **k: _Proc(returncode=128)
    )
    assert cmd_sync._classify_remote_ref("http://r/err2.git", "main") == "branch"
    assert cmd_sync._ref_types == {}


def test_classify_remote_ref_uses_cache(monkeypatch):
    monkeypatch.setattr(cmd_sync, "_ref_types", {"http://r/c.git|main": "tag"})

    def _boom(*a, **k):
        raise AssertionError("subprocess.run must not be called on a cache hit")

    monkeypatch.setattr(cmd_sync.subprocess, "run", _boom)
    assert cmd_sync._classify_remote_ref("http://r/c.git", "main") == "tag"


# --- _has_moving_upstream_ref ---


def _write_service(tmp_path, revision=None):
    pkg = tmp_path / "pkg"
    (pkg / "obs").mkdir(parents=True)
    rev = f'<param name="revision">{revision}</param>' if revision is not None else ""
    (pkg / "obs" / "_service").write_text(
        "<services>"
        '<service name="obs_scm">'
        '<param name="url">https://github.com/x/y.git</param>'
        f"{rev}"
        "</service>"
        "</services>"
    )
    return pkg


def _forbid_classification(monkeypatch):
    def _boom(*a):
        raise AssertionError("_classify_remote_ref must not be called")

    monkeypatch.setattr(cmd_sync, "_classify_remote_ref", _boom)


def test_moving_ref_false_for_pinned_sha(monkeypatch, tmp_path):
    pkg = _write_service(tmp_path, revision="a" * 40)
    _forbid_classification(monkeypatch)
    assert cmd_sync._has_moving_upstream_ref(pkg, {}) is False


def test_moving_ref_true_when_revision_param_missing(monkeypatch, tmp_path):
    pkg = _write_service(tmp_path, revision=None)
    _forbid_classification(monkeypatch)
    assert cmd_sync._has_moving_upstream_ref(pkg, {}) is True


def test_moving_ref_true_for_branch_classification(monkeypatch, tmp_path):
    pkg = _write_service(tmp_path, revision="main")
    monkeypatch.setattr(cmd_sync, "_classify_remote_ref", lambda *a: "branch")
    assert cmd_sync._has_moving_upstream_ref(pkg, {}) is True


def test_moving_ref_false_for_tag_classification(monkeypatch, tmp_path):
    pkg = _write_service(tmp_path, revision="v1.2.3")
    monkeypatch.setattr(cmd_sync, "_classify_remote_ref", lambda *a: "tag")
    assert cmd_sync._has_moving_upstream_ref(pkg, {}) is False


def test_moving_ref_false_when_no_service_file(monkeypatch, tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "obs").mkdir(parents=True)
    _forbid_classification(monkeypatch)
    assert cmd_sync._has_moving_upstream_ref(pkg, {}) is False


def test_moving_ref_true_for_malformed_service_file(monkeypatch, tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "obs").mkdir(parents=True)
    (pkg / "obs" / "_service").write_text(
        '<services><service name="obs_scm"><param name="url">x</param>'
    )
    _forbid_classification(monkeypatch)
    assert cmd_sync._has_moving_upstream_ref(pkg, {}) is True
