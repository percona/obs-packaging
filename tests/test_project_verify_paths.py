"""Live ``project:`` path validation (`project verify` without --offline).

Every resolvable ``project:`` reference of an in-slice project is looked up
on the OBS instance, interconnect references included; out-of-slice
repositories are skipped; a 401/403 aborts once instead of producing a
false "not found" per project; ``--no-scm-validate`` skips only the git
revision check so CI can run the live path check on its own."""

import argparse
import urllib.error
from pathlib import Path

import pytest

import percona_obs.cmd_project as cmd_project
from percona_obs.project_config import RepositoryFilter

APIURL = "https://obs.example"


def _write_tree(tmp_path: Path, monkeypatch, project_yaml: str) -> Path:
    """Minimal packaging tree: one root project.yaml under <tmp>/root."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "project.yaml").write_text(project_yaml)
    monkeypatch.setattr(cmd_project, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_project.common, "REPO_ROOT", root)
    return root


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("url", code, "msg", {}, None)  # type: ignore[arg-type]


def _meta(*repos: str) -> bytes:
    body = "".join(f'<repository name="{r}"/>' for r in repos)
    return f'<project name="x">{body}</project>'.encode()


ROOT_YAML = """\
name: isv:percona
repositories:
  - name: RockyLinux_9
    paths:
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:9
        repository: standard
      - project: Fedora:EPEL:9
        repository: standard
    archs: [x86_64]
  - name: Debian_12
    paths:
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Debian:12
        repository: standard
    archs: [x86_64]
"""


def _run(monkeypatch, root: Path, metas: dict, env: dict, repo_filter=None):
    calls: list[str] = []

    def show_project_meta(apiurl, project):
        assert apiurl == APIURL
        calls.append(project)
        result = metas[project]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(cmd_project.osc.core, "show_project_meta", show_project_meta)
    monkeypatch.setattr(
        cmd_project,
        "get_default_repository_filter",
        lambda: repo_filter or RepositoryFilter.EMPTY,
    )
    errors = cmd_project._validate_project_path_refs(root, env, APIURL, "isv:percona")
    return errors, calls


def test_external_and_interconnect_refs_are_checked(tmp_path, monkeypatch):
    root = _write_tree(tmp_path, monkeypatch, ROOT_YAML)
    env = {"REMOTE_OBS_ORG_INTERCONNECT": "openSUSE.org:"}
    metas = {
        "openSUSE.org:RockyLinux:9": _meta("standard"),
        "Fedora:EPEL:9": _http_error(404),
        "openSUSE.org:Debian:12": _meta("update"),
    }
    errors, calls = _run(monkeypatch, root, metas, env)
    assert sorted(calls) == sorted(metas)  # each project fetched exactly once
    msgs = [m for _, m in errors]
    assert len(msgs) == 2
    assert any("'Fedora:EPEL:9': not found" in m for m in msgs)
    assert any(
        "openSUSE.org:Debian:12/standard" in m and "no repository 'standard'" in m
        for m in msgs
    )


def test_out_of_slice_repositories_are_skipped(tmp_path, monkeypatch):
    root = _write_tree(tmp_path, monkeypatch, ROOT_YAML)
    env = {"REMOTE_OBS_ORG_INTERCONNECT": ""}
    metas = {"RockyLinux:9": _meta("standard"), "Fedora:EPEL:9": _meta("standard")}
    errors, calls = _run(
        monkeypatch,
        root,
        metas,
        env,
        repo_filter=RepositoryFilter(exclude_repos=("Debian_*",)),
    )
    assert errors == []
    assert "Debian:12" not in calls  # excluded repo's paths never looked up


def test_unresolved_env_var_is_skipped(tmp_path, monkeypatch):
    root = _write_tree(tmp_path, monkeypatch, ROOT_YAML)
    metas = {"Fedora:EPEL:9": _meta("standard")}
    errors, calls = _run(monkeypatch, root, metas, env={})
    assert errors == []
    assert calls == ["Fedora:EPEL:9"]


def test_auth_failure_aborts_once(tmp_path, monkeypatch):
    root = _write_tree(tmp_path, monkeypatch, ROOT_YAML)
    env = {"REMOTE_OBS_ORG_INTERCONNECT": ""}
    metas = {
        k: _http_error(401) for k in ("RockyLinux:9", "Fedora:EPEL:9", "Debian:12")
    }
    with pytest.raises(cmd_project.ObsAuthError) as exc:
        _run(monkeypatch, root, metas, env)
    assert "credentials" in str(exc.value)
    assert "HTTP 401" in str(exc.value)


def test_other_http_errors_are_reported_not_fatal(tmp_path, monkeypatch):
    root = _write_tree(tmp_path, monkeypatch, ROOT_YAML)
    env = {"REMOTE_OBS_ORG_INTERCONNECT": ""}
    metas = {
        "RockyLinux:9": _http_error(502),
        "Fedora:EPEL:9": _meta("standard"),
        "Debian:12": _meta("standard"),
    }
    errors, _ = _run(monkeypatch, root, metas, env)
    assert [m for _, m in errors] == [
        f"repository 'RockyLinux_9' paths to OBS project 'RockyLinux:9': "
        f"HTTP 502 fetching meta on {APIURL}"
    ]


# --- --no-scm-validate -------------------------------------------------------


def _args(**kw):
    base = dict(
        project=None,
        package=None,
        profile="main",
        env_overrides=[],
        rootprj="isv:percona",
        offline=False,
        no_scm_validate=False,
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
    monkeypatch.setattr(cmd_project, "_load_profile", lambda n: {"apiurl": APIURL})
    monkeypatch.setattr(cmd_project, "_load_profile_env", lambda n: {})
    monkeypatch.setattr(cmd_project.osc.conf, "get_config", lambda **k: None)


def test_no_scm_validate_skips_only_the_scm_check(monkeypatch):
    calls: list[str] = []
    _stub_validators(monkeypatch, calls)
    cmd_project.cmd_project_verify(_args(no_scm_validate=True))
    assert "_validate_obs_scm_revisions" not in calls
    assert "_validate_project_path_refs" in calls


def test_default_runs_both_network_checks(monkeypatch):
    calls: list[str] = []
    _stub_validators(monkeypatch, calls)
    cmd_project.cmd_project_verify(_args())
    assert "_validate_obs_scm_revisions" in calls
    assert "_validate_project_path_refs" in calls
