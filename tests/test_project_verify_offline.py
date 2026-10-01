"""`project verify --offline` must skip both network validators (obs_scm
revision lookups via git ls-remote, and project: path checks against the
live OBS) while still running the static checks.  CI's Project Config Check
workflow relies on this: it renders the tree per OBS instance with a
credential-less profile."""

import argparse

import percona_obs.cmd_project as cmd_project


def _args(**kw):
    base = dict(
        project=None,
        package=None,
        profile=None,
        env_overrides=[],
        rootprj="isv:percona",
        offline=False,
    )
    base.update(kw)
    return argparse.Namespace(**base)


def _stub_validators(monkeypatch, calls):
    def rec(name):
        def _f(*a, **k):
            calls.append(name)
            return []

        return _f

    for name in (
        "_validate_subproject_refs",
        "_validate_repo_path_refs",
        "_validate_env_vars",
        "_validate_obs_scm_revisions",
        "_validate_project_path_refs",
    ):
        monkeypatch.setattr(cmd_project, name, rec(name))
    # A profile with an apiurl is what would normally enable the OBS check.
    monkeypatch.setattr(
        cmd_project, "_load_profile", lambda n: {"apiurl": "https://obs.example"}
    )
    monkeypatch.setattr(cmd_project, "_load_profile_env", lambda n: {})
    monkeypatch.setattr(cmd_project.osc.conf, "get_config", lambda **k: None)


def test_offline_skips_scm_and_obs_path_checks(monkeypatch):
    calls: list[str] = []
    _stub_validators(monkeypatch, calls)
    cmd_project.cmd_project_verify(_args(profile="main", offline=True))
    assert "_validate_obs_scm_revisions" not in calls
    assert "_validate_project_path_refs" not in calls
    assert {
        "_validate_subproject_refs",
        "_validate_repo_path_refs",
        "_validate_env_vars",
    } <= set(calls)


def test_online_runs_scm_and_obs_path_checks(monkeypatch):
    calls: list[str] = []
    _stub_validators(monkeypatch, calls)
    cmd_project.cmd_project_verify(_args(profile="main", offline=False))
    assert "_validate_obs_scm_revisions" in calls
    assert "_validate_project_path_refs" in calls
