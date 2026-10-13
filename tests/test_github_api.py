"""Unit tests for percona_obs.github_api (gh is monkeypatched)."""

import pytest

import percona_obs.github_api as gha


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/percona/obs-packaging.git",
        "https://github.com/percona/obs-packaging",
        "git@github.com:percona/obs-packaging.git",
    ],
)
def test_repo_slug_from_url(url):
    assert gha.repo_slug_from_url(url) == "percona/obs-packaging"


def test_repo_slug_rejects_unknown():
    with pytest.raises(SystemExit, match="cannot derive owner/repo"):
        gha.repo_slug_from_url("file:///tmp/x")


def _fake_api(monkeypatch, runs, jobs_by_run):
    def fake(path):
        if "/workflows/sync-main.yml/runs" in path:
            return {"workflow_runs": runs}
        for run_id, jobs in jobs_by_run.items():
            if f"/runs/{run_id}/jobs" in path:
                return {"jobs": jobs}
        raise AssertionError(path)

    monkeypatch.setattr(gha, "_gh_api_json", fake)


def test_last_synced_skips_runs_with_failed_sync_job(monkeypatch):
    runs = [
        {"id": 3, "head_sha": "c" * 40},
        {"id": 2, "head_sha": "b" * 40},
        {"id": 1, "head_sha": "a" * 40},
    ]
    jobs = {
        3: [
            {"name": "percona-obs sync push (boo)", "conclusion": "success"},
            {"name": "percona-obs sync push (labs)", "conclusion": "failure"},
            {"name": "Wait for OBS builds (boo)", "conclusion": "success"},
        ],
        2: [
            {"name": "percona-obs sync push (boo)", "conclusion": "success"},
            {"name": "percona-obs sync push (labs)", "conclusion": "success"},
            {"name": "Wait for OBS builds (boo)", "conclusion": "failure"},
        ],
    }
    _fake_api(monkeypatch, runs, jobs)
    assert gha.last_synced_head_sha("percona/obs-packaging") == "b" * 40


def test_last_synced_no_qualifying_run(monkeypatch):
    _fake_api(monkeypatch, [{"id": 1, "head_sha": "a" * 40}], {1: []})
    with pytest.raises(SystemExit, match="no completed sync-main.yml run"):
        gha.last_synced_head_sha("percona/obs-packaging")


def test_gh_failure_is_reported(monkeypatch):
    class R:
        returncode = 1
        stdout = ""
        stderr = "gh: not logged in"

    monkeypatch.setattr(gha.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(SystemExit, match="not logged in"):
        gha._gh_api_json("repos/x/y")
