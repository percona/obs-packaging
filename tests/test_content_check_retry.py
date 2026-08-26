"""Unit tests for service-failure handling in the --branch-from content check.

Reproduces the PR #12 CI failure: a transient ``obs_scm`` clone error
(``curl 56 Connection reset by peer``) inside ``_content_matches_branch`` was
swallowed and reported as "content differs", which promoted an unrelated,
unchanged package.  A failed service run says nothing about whether the
content matches, so the check must retry once and then abort the sync with
the real error — never return a verdict.
"""

import hashlib
from pathlib import Path

import pytest

import percona_obs.cmd_sync as cmd_sync
from percona_obs.cmd_sync import _content_matches_branch


def _patch_static(monkeypatch, obs_md5s):
    monkeypatch.setattr(cmd_sync, "_fetch_obs_file_md5s", lambda *a, **k: obs_md5s)
    monkeypatch.setattr(cmd_sync, "_is_link_package", lambda *a: False)
    monkeypatch.setattr(cmd_sync, "load_macros", lambda *a: {})
    monkeypatch.setattr(cmd_sync, "_has_runnable_services", lambda *a: True)


def _make_service_stub(tmp_path: Path, fail_times: int):
    """Return (stub, calls) where stub fails *fail_times* times, then succeeds.

    On success it produces a workdir holding one artifact ``foo`` so the
    caller's MD5 comparison can complete against a matching OBS file list.
    """
    calls: list[int] = []

    def stub(obs_dir, pkg_label="", cache=True, env_vars=None, macros=None):
        calls.append(1)
        if len(calls) <= fail_times:
            raise SystemExit("error: service 'obs_scm' exited with 1:\n  curl 56")
        workdir = tmp_path / f"workdir-{len(calls)}"
        workdir.mkdir()
        (workdir / "foo").write_text("hello")
        return workdir

    return stub, calls


def _obs_dir(tmp_path: Path) -> Path:
    obs_dir = tmp_path / "pkg" / "obs"
    obs_dir.mkdir(parents=True)
    (obs_dir / "_service").write_text("<services/>")
    return obs_dir


FOO_MD5 = hashlib.md5(b"hello").hexdigest()


def test_service_failing_twice_aborts_instead_of_reporting_differs(
    monkeypatch, tmp_path
):
    _patch_static(monkeypatch, {"foo": FOO_MD5})
    stub, calls = _make_service_stub(tmp_path, fail_times=2)
    monkeypatch.setattr(cmd_sync, "_run_local_services", stub)

    with pytest.raises(SystemExit) as excinfo:
        _content_matches_branch("http://obs", "prod:ppg:17", "pkg", _obs_dir(tmp_path))

    assert len(calls) == 2
    msg = str(excinfo.value)
    assert "prod:ppg:17/pkg" in msg
    assert "curl 56" in msg


def test_service_failing_once_is_retried_and_comparison_completes(
    monkeypatch, tmp_path
):
    _patch_static(monkeypatch, {"foo": FOO_MD5})
    stub, calls = _make_service_stub(tmp_path, fail_times=1)
    monkeypatch.setattr(cmd_sync, "_run_local_services", stub)

    assert (
        _content_matches_branch("http://obs", "prod:ppg:17", "pkg", _obs_dir(tmp_path))
        is True
    )
    assert len(calls) == 2


def test_service_succeeding_first_time_runs_once(monkeypatch, tmp_path):
    _patch_static(monkeypatch, {"foo": FOO_MD5})
    stub, calls = _make_service_stub(tmp_path, fail_times=0)
    monkeypatch.setattr(cmd_sync, "_run_local_services", stub)

    assert (
        _content_matches_branch("http://obs", "prod:ppg:17", "pkg", _obs_dir(tmp_path))
        is True
    )
    assert len(calls) == 1
