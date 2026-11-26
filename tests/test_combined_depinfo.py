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


class _GraphOBS:
    """Serves a configurable /build tree with per-(project, repo, arch)
    _builddepinfo documents.  ``fail`` holds project names whose
    _builddepinfo answers HTTP 500."""

    def __init__(self, tree, fail=(), image_fail=()):
        # tree[project][repo][arch] = list of (src, [subpkgs], [pkgdeps])
        self.tree = tree
        self.fail = set(fail)
        self.image_fail = set(image_fail)

    def __call__(self, url: str):
        parts = url.split("/", 3)[3].split("/")
        assert parts[0] == "build"
        project = parts[1]
        if project not in self.tree:
            raise RuntimeError(f"HTTP Error 404: {project}")
        repos = self.tree[project]
        if len(parts) == 2:
            return _Resp(
                (
                    "<directory>"
                    + "".join(f'<entry name="{r}"/>' for r in repos)
                    + "</directory>"
                ).encode()
            )
        repo = parts[2]
        if len(parts) == 3:
            return _Resp(
                (
                    "<directory>"
                    + "".join(f'<entry name="{a}"/>' for a in repos[repo])
                    + "</directory>"
                ).encode()
            )
        arch = parts[3]
        if parts[-1] == "_buildinfo":
            if project in self.image_fail:
                raise RuntimeError("HTTP Error 500: buildinfo")
            return _Resp(b'<buildinfo><bdep name="liba"/></buildinfo>')
        assert parts[-1] == "_builddepinfo"
        if project in self.fail:
            raise RuntimeError("HTTP Error 500: builddepinfo")
        body = ""
        for src, subpkgs, deps in repos[repo][arch]:
            body += f'<package name="{src}">'
            body += "".join(f"<subpkg>{s}</subpkg>" for s in subpkgs)
            body += "".join(f"<pkgdep>{d}</pkgdep>" for d in deps)
            body += "</package>"
        return _Resp(f"<builddepinfo>{body}</builddepinfo>".encode())


def _graph(monkeypatch, obs):
    monkeypatch.setattr(osc.connection, "http_GET", obs)
    monkeypatch.setattr(
        "percona_obs.obs_api._fetch_repo_path_projects", lambda *a, **k: []
    )


API = "https://obs.example"


def test_all_targets_unions_repos_and_archs(monkeypatch):
    tree = {
        "P": {
            "R1": {
                "x86_64": [("a", ["liba"], []), ("b", ["libb"], ["liba"])],
                "aarch64": [],
            },
            "R2": {"aarch64": [("a", ["liba"], []), ("c", ["libc"], ["liba"])]},
        }
    }
    _graph(monkeypatch, _GraphOBS(tree))
    local = {("P", "a"), ("P", "b"), ("P", "c")}
    default = _fetch_combined_depinfo(API, {"P"}, local)
    exact = _fetch_combined_depinfo(API, {"P"}, local, all_targets=True)
    assert ("P", "c") not in default
    assert ("P", "a") in default[("P", "b")]
    assert ("P", "a") in exact[("P", "c")]
    assert ("P", "a") in exact[("P", "b")]


def test_all_targets_edge_on_second_arch_of_first_repo(monkeypatch):
    tree = {
        "P": {
            "R1": {
                "x86_64": [("a", ["liba"], [])],
                "aarch64": [("a", ["liba"], []), ("d", ["libd"], ["liba"])],
            }
        }
    }
    _graph(monkeypatch, _GraphOBS(tree))
    local = {("P", "a"), ("P", "d")}
    assert _fetch_combined_depinfo(API, {"P"}, local) == {}
    exact = _fetch_combined_depinfo(API, {"P"}, local, all_targets=True)
    assert exact == {("P", "d"): {("P", "a")}}


def test_failed_projects_are_reported(monkeypatch):
    tree = {
        "P": {"R1": {"x86_64": [("a", ["liba"], []), ("b", ["libb"], ["liba"])]}},
        "Q": {"R1": {"x86_64": []}},
    }
    _graph(monkeypatch, _GraphOBS(tree, fail={"Q"}))
    local = {("P", "a"), ("P", "b")}
    failed: set[str] = set()
    got = _fetch_combined_depinfo(
        API, {"P", "Q"}, local, all_targets=True, failed=failed
    )
    assert failed == {"Q"}
    assert ("P", "a") in got[("P", "b")]


def test_unlisted_project_is_reported_failed(monkeypatch):
    tree = {"P": {"R1": {"x86_64": []}}}
    _graph(monkeypatch, _GraphOBS(tree))
    failed: set[str] = set()
    _fetch_combined_depinfo(API, {"P", "Gone"}, set(), failed=failed)
    assert failed == {"Gone"}


def test_failed_not_touched_when_everything_fetches(monkeypatch):
    tree = {"P": {"R1": {"x86_64": [("a", ["liba"], [])]}}}
    _graph(monkeypatch, _GraphOBS(tree))
    failed: set[str] = set()
    _fetch_combined_depinfo(API, {"P"}, {("P", "a")}, failed=failed)
    assert failed == set()


def test_image_buildinfo_failure_reports_project(monkeypatch):
    tree = {
        "P": {"R1": {"x86_64": [("a", ["liba"], [])]}},
        "I": {"R1": {"x86_64": []}},
    }
    _graph(monkeypatch, _GraphOBS(tree, image_fail={"I"}))
    failed: set[str] = set()
    got = _fetch_combined_depinfo(
        API,
        {"P", "I"},
        {("P", "a")},
        image_pkgs={"img": [("I", "R1", "x86_64")]},
        failed=failed,
    )
    assert failed == {"I"}
    assert got == {}


def test_image_edges_still_returned_without_failure(monkeypatch):
    tree = {"P": {"R1": {"x86_64": [("a", ["liba"], [])]}}, "I": {"R1": {"x86_64": []}}}
    _graph(monkeypatch, _GraphOBS(tree))
    failed: set[str] = set()
    got = _fetch_combined_depinfo(
        API,
        {"P", "I"},
        {("P", "a"), ("I", "img")},
        image_pkgs={"img": [("I", "R1", "x86_64")]},
        failed=failed,
    )
    assert failed == set()
    assert got == {("I", "img"): {("P", "a")}}
