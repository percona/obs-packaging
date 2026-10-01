"""Unit tests for _fetch_combined_depinfo image-dep enrichment (percona_obs.obs_api).

Reproduces the percona/obs-packaging PR #101 slowdown: a PR adding a
brand-new repository (ubi10) to the containers projects made the
--branch-from dep cascade query production _buildinfo for
<project>/ubi10/x86_64/<image>.  That repo does not exist in production
yet; OBS answers 404 but only after 35-80 s each, and there is one such
query per image per PG major (~20 minutes per sync run).

The fix skips the per-image _buildinfo query whenever the repository is
absent from the project's /build/<project> listing, which the function
already fetches.
"""

import io
import xml.etree.ElementTree as ET

import pytest

import osc.connection

from percona_obs.obs_api import _fetch_combined_depinfo

PROJECT = "isv:percona:ppg:staging:18:containers"
MISSING_PROJECT = "isv:percona:common:containers:ubi10"


class _Resp(io.BytesIO):
    pass


class _FakeOBS:
    """Serves /build/<project>[/<repo>[/<arch>[/<pkg>/_buildinfo]]] from a
    dict of project -> repo names and records every URL requested."""

    def __init__(self, repos_by_project: dict[str, list[str]]):
        self.repos_by_project = repos_by_project
        self.requests: list[str] = []

    def __call__(self, url: str):
        self.requests.append(url)
        path = url.split("/", 3)[3]  # strip scheme://host/
        parts = path.split("/")
        assert parts[0] == "build"
        project = parts[1]
        if project not in self.repos_by_project:
            raise RuntimeError(f"HTTP Error 404: project {project!r} unknown")
        repos = self.repos_by_project[project]
        if len(parts) == 2:
            body = "".join(f'<entry name="{r}"/>' for r in repos)
            return _Resp(f"<directory>{body}</directory>".encode())
        repo = parts[2]
        if repo not in repos:
            raise RuntimeError(f"HTTP Error 404: repo {repo!r} unknown")
        if len(parts) == 3:
            return _Resp(b'<directory><entry name="x86_64"/></directory>')
        if parts[-1] == "_builddepinfo":
            return _Resp(b"<builddepinfo/>")
        if parts[-1] == "_buildinfo":
            return _Resp(b"<buildinfo/>")
        raise AssertionError(f"unexpected url {url}")


@pytest.fixture
def fake_obs(monkeypatch):
    obs = _FakeOBS({PROJECT: ["ubi8", "ubi9"]})
    monkeypatch.setattr(osc.connection, "http_GET", obs)
    # _fetch_repo_path_projects reads project _meta via osc.core; neutralise it.
    monkeypatch.setattr(
        "percona_obs.obs_api._fetch_repo_path_projects", lambda *a, **k: []
    )
    return obs


def _buildinfo_requests(obs: _FakeOBS) -> list[str]:
    return [u for u in obs.requests if u.endswith("/_buildinfo")]


def test_skips_buildinfo_for_repo_missing_from_project(fake_obs):
    image_pkgs = {
        "percona-distribution-postgresql": [
            (PROJECT, "ubi9", "x86_64"),
            (PROJECT, "ubi10", "x86_64"),
        ]
    }
    _fetch_combined_depinfo(
        "https://obs.example", {PROJECT}, set(), image_pkgs=image_pkgs
    )
    reqs = _buildinfo_requests(fake_obs)
    assert len(reqs) == 1
    assert f"/{PROJECT}/ubi9/x86_64/" in reqs[0]
    assert not any("/ubi10/" in u for u in reqs)


def test_skips_buildinfo_for_project_not_on_obs(fake_obs):
    image_pkgs = {"createrepo_c": [(MISSING_PROJECT, "ubi10", "x86_64")]}
    _fetch_combined_depinfo(
        "https://obs.example",
        {PROJECT, MISSING_PROJECT},
        set(),
        image_pkgs=image_pkgs,
    )
    assert _buildinfo_requests(fake_obs) == []


def test_image_project_outside_dep_projects_is_listed_once(fake_obs):
    """An image project absent from branch_projects gets a single repo
    listing, shared across its images, before any _buildinfo query."""
    fake_obs.repos_by_project["isv:percona:ppg:staging:17:containers"] = ["ubi9"]
    other = "isv:percona:ppg:staging:17:containers"
    image_pkgs = {
        "percona-pgbouncer": [(other, "ubi9", "x86_64"), (other, "ubi10", "x86_64")],
        "percona-pgbackrest": [(other, "ubi9", "x86_64")],
    }
    _fetch_combined_depinfo(
        "https://obs.example", {PROJECT}, set(), image_pkgs=image_pkgs
    )
    listings = [u for u in fake_obs.requests if u.endswith(f"/build/{other}")]
    assert len(listings) == 1
    reqs = _buildinfo_requests(fake_obs)
    assert len(reqs) == 2
    assert not any("/ubi10/" in u for u in reqs)
