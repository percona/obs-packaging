"""``project versions --online``: find a version wherever OBS has one, and say
why when it has none.

It used to print ``version: null`` with no explanation when the first
succeeded repository listed no readable binary, when an aggregate's source
project yielded nothing (no build, or an API error), or when any OBS call
failed.  These tests run the real command over the repo tree with the OBS
calls replaced.
"""

import logging
from types import SimpleNamespace

import osc.conf
import pytest
import yaml

import percona_obs.cmd_project as cmd_project

DEPS = "isv:percona:ppg:common:deps"
STAGING = "isv:percona:ppg:staging:18"


@pytest.fixture
def obs(monkeypatch):
    """Fake OBS: build results and binary lists per project, plus a call log."""
    state = SimpleNamespace(succeeded={}, binaries={}, calls=[])

    def fetch_build_results(apiurl, project):
        state.calls.append(("_result", project))
        return {}, state.succeeded.get(project, {})

    def fetch_pkg_versrel(apiurl, project, repo, arch, pkg):
        state.calls.append(("binaries", project, repo, pkg))
        return state.binaries.get((project, repo, pkg))

    monkeypatch.setattr(cmd_project, "_fetch_build_results", fetch_build_results)
    monkeypatch.setattr(cmd_project, "_fetch_pkg_versrel", fetch_pkg_versrel)
    monkeypatch.setattr(osc.conf, "get_config", lambda **kw: None)
    monkeypatch.setattr(
        osc.conf, "config", {"apiurl": "https://obs.example"}, raising=False
    )
    return state


def _etcd_version(capsys):
    args = SimpleNamespace(
        project="ppg:staging:18",
        package="etcd",
        online=True,
        recursive=False,
        markdown=False,
        apiurl="https://obs.example",
        rootprj="isv:percona",
    )
    cmd_project.cmd_project_versions(args)
    (record,) = yaml.safe_load(capsys.readouterr().out)
    assert record["name"] == "etcd"
    return record["version"]


_BOTH = {"etcd": {"Debian_12": ("x86_64", ""), "RockyLinux_9": ("x86_64", "")}}


def test_version_from_the_aggregate_source(obs, capsys):
    obs.succeeded[DEPS] = _BOTH
    obs.binaries[(DEPS, "Debian_12", "etcd")] = "3.5.33-1.1"
    assert _etcd_version(capsys) == "3.5.33-1.1"


def test_next_repository_is_tried_when_the_first_has_no_readable_binary(obs, capsys):
    obs.succeeded[DEPS] = _BOTH
    obs.binaries[(DEPS, "RockyLinux_9", "etcd")] = "3.5.33-1.1"  # Debian_12: none
    assert _etcd_version(capsys) == "3.5.33-1.1"


def test_aggregating_project_is_used_when_the_source_yields_nothing(obs, capsys):
    obs.succeeded[STAGING] = _BOTH  # source project: no succeeded build visible
    obs.binaries[(STAGING, "Debian_12", "etcd")] = "3.5.33-1.1"
    assert _etcd_version(capsys) == "3.5.33-1.1"
    assert ("_result", DEPS) in obs.calls and ("_result", STAGING) in obs.calls


def test_nothing_found_is_explained(obs, capsys, caplog):
    with caplog.at_level(logging.WARNING, logger="percona-obs"):
        assert _etcd_version(capsys) is None
    assert f"etcd: no version found" in caplog.text
    assert DEPS in caplog.text and STAGING in caplog.text


def test_api_errors_are_reported_not_hidden(monkeypatch, caplog):
    import percona_obs.cmd_build as cmd_build

    def boom(url):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(cmd_build.osc.connection, "http_GET", boom)
    with caplog.at_level(logging.WARNING, logger="percona-obs"):
        assert cmd_build._fetch_build_results("https://obs.example", DEPS) == ({}, {})
        assert (
            cmd_build._fetch_pkg_versrel(
                "https://obs.example", DEPS, "Debian_12", "x86_64", "etcd"
            )
            is None
        )
    assert "could not fetch build results of " + DEPS in caplog.text
    assert "403" in caplog.text
    assert (
        "could not list binaries of " + DEPS + "/Debian_12/x86_64/etcd" in caplog.text
    )
