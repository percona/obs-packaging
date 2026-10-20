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
import percona_obs.obs_versions as obs_versions

DEPS = "isv:percona:ppg:common:deps"
STAGING = "isv:percona:ppg:staging:18"


@pytest.fixture
def obs(monkeypatch):
    """Fake OBS: batch binary versions per project, plus a call log."""
    obs_versions.clear_cache()
    state = SimpleNamespace(data={}, calls=[])

    def project_binary_versions(apiurl, project, repo_filter=None):
        state.calls.append(project)
        return state.data.get(project)

    monkeypatch.setattr(cmd_project, "project_binary_versions", project_binary_versions)
    monkeypatch.setattr(osc.conf, "get_config", lambda **kw: None)
    monkeypatch.setattr(
        osc.conf, "config", {"apiurl": "https://obs.example"}, raising=False
    )
    yield state
    obs_versions.clear_cache()


def _versions(capsys, package="etcd"):
    args = SimpleNamespace(
        project="ppg:staging:18",
        package=package,
        online=True,
        recursive=False,
        markdown=False,
        apiurl="https://obs.example",
        rootprj="isv:percona",
    )
    cmd_project.cmd_project_versions(args)
    (record,) = yaml.safe_load(capsys.readouterr().out)
    assert record["name"] == package
    return record["version"]


def _etcd_version(capsys):
    return _versions(capsys)


def test_version_from_the_aggregate_source(obs, capsys):
    obs.data[DEPS] = {"etcd": {("Debian_12", "x86_64"): "3.5.33-1.1"}}
    assert _etcd_version(capsys) == "3.5.33-1.1"


def test_first_repository_with_a_binary_is_used(obs, capsys):
    # Debian_12 sorts first but has no readable binary, so no entry.
    obs.data[DEPS] = {"etcd": {("RockyLinux_9", "x86_64"): "3.5.33-1.1"}}
    assert _etcd_version(capsys) == "3.5.33-1.1"


def test_aggregating_project_is_used_when_the_source_yields_nothing(obs, capsys):
    obs.data[DEPS] = {"etcd": {}}  # listed without a readable binary
    obs.data[STAGING] = {"etcd": {("Debian_12", "x86_64"): "3.5.33-1.1"}}
    assert _etcd_version(capsys) == "3.5.33-1.1"
    assert DEPS in obs.calls and STAGING in obs.calls


def test_nothing_found_is_explained(obs, capsys, caplog):
    with caplog.at_level(logging.WARNING, logger="percona-obs"):
        assert _etcd_version(capsys) is None
    assert f"etcd: no version found" in caplog.text
    assert DEPS in caplog.text and STAGING in caplog.text


def test_first_sorted_versrel_and_conflict_warning(obs, capsys, caplog):
    obs.data["isv:percona:ppg:staging:18"] = {
        "percona-pgbackrest": {
            ("RockyLinux_9", "x86_64"): "2.60.0-1.1",
            ("Debian_12", "x86_64"): "2.59.2-1",
        }
    }
    with caplog.at_level(logging.WARNING, logger="percona-obs"):
        version = _versions(capsys, "percona-pgbackrest")
    assert version == "2.59.2-1"
    assert "OBS builds disagree" in caplog.text
    assert obs.calls.count("isv:percona:ppg:staging:18") == 1


def test_batch_api_error_is_reported_with_the_project(monkeypatch):
    obs_versions.clear_cache()

    def boom(url):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(obs_versions.osc.connection, "http_GET", boom)
    with pytest.raises(SystemExit) as exc:
        obs_versions.project_binary_versions("https://obs.example", DEPS)
    assert DEPS in str(exc.value)
    obs_versions.clear_cache()


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
