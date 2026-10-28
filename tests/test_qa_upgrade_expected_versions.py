"""Per-phase versions for upgrade entries (EXPECTED_VERSIONS / OLD_EXPECTED_VERSIONS).

An upgrade entry tests two images from two projects (the old and the new
major). One list computed from the entry's own (common) project cannot be
right for both phases: percona-postgresql and percona-pgaudit differ between
majors, and the common project lists whichever major comes first in its paths.
Versions come from OBS builds (faked here by replacing project_binary_versions).
"""

import json
import re
from types import SimpleNamespace

import pytest

from percona_obs import cmd_qa
from percona_obs.common import find_packages, resolve_project_path


def _lookup():
    lookup = cmd_qa._VersionLookup("http://obs", "isv:percona", None, None)
    lookup._fetch = lambda root, prj: object()  # the project under test exists
    return lookup


def test_image_projects_only_references_with_a_project():
    entry = {
        "parameters": {
            "OLD_REPOSITORY": {"image": "x", "repository": "ubi9", "project": "p:16"},
            "UPGRADE_REPOSITORY": {"image": "u", "repository": "ubi9"},
            "VERSION": "18",
        }
    }
    assert cmd_qa._image_projects(entry) == {"OLD_REPOSITORY": "p:16"}


def _fake_versions(monkeypatch, conflicts_in=None):
    data = {
        "lane": {"a": "0"},
        "p:16": {"a": "16", "s": "1"},
        "p:17": {"a": "17", "s": "1"},
    }

    def package_versions(prj, lookup):
        if prj == conflicts_in:
            lookup.conflicts["s"] = "percona-s: OBS builds disagree"
        return data[prj]

    monkeypatch.setattr(cmd_qa, "_package_versions", package_versions)
    monkeypatch.setattr(
        cmd_qa, "resolve_project_path", lambda p: SimpleNamespace(is_dir=lambda: True)
    )


def _lanes(*entries):
    return [cmd_qa.Lane(None, list(entries))]


def _upgrade(**params):
    return {
        "name": "u",
        "parameters": dict(params),
        "_image_projects": {
            "OLD_REPOSITORY": "p:16",
            "NEW_REPOSITORY": "p:17",
            "REPOSITORY": "p:17",
        },
    }


def _versions(text):
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def test_upgrade_entry_gets_one_list_per_phase(monkeypatch):
    _fake_versions(monkeypatch)
    plain = {"name": "server", "parameters": {}}
    lanes = cmd_qa._lanes_with_expected_versions(
        _lanes(_upgrade(), plain), "lane", _lookup()
    )
    up, server = lanes[0].entries
    assert _versions(up["parameters"]["EXPECTED_VERSIONS"]) == {"a": "17", "s": "1"}
    assert _versions(up["parameters"]["OLD_EXPECTED_VERSIONS"]) == {"a": "16", "s": "1"}
    assert server["parameters"] == {
        "EXPECTED_VERSIONS": "a=0"
    }  # other entries unchanged


def test_repository_is_the_new_image_without_new_repository(monkeypatch):
    _fake_versions(monkeypatch)
    entry = {
        "parameters": {},
        "_image_projects": {"OLD_REPOSITORY": "p:16", "REPOSITORY": "p:17"},
    }
    out = cmd_qa._lanes_with_expected_versions(_lanes(entry), "lane", _lookup())[
        0
    ].entries[0]["parameters"]
    assert out["EXPECTED_VERSIONS"].startswith("a=17") and out[
        "OLD_EXPECTED_VERSIONS"
    ].startswith("a=16")


def test_explicit_values_are_kept(monkeypatch):
    _fake_versions(monkeypatch)
    entry = _upgrade(EXPECTED_VERSIONS="a=mine", OLD_EXPECTED_VERSIONS="a=old-mine")
    out = cmd_qa._lanes_with_expected_versions(_lanes(entry), "lane", _lookup())[
        0
    ].entries[0]["parameters"]
    assert (
        out["EXPECTED_VERSIONS"] == "a=mine"
        and out["OLD_EXPECTED_VERSIONS"] == "a=old-mine"
    )


def test_conflict_in_an_image_project_blocks_the_upgrade(monkeypatch):
    """A conflict in the old major's project aborts, as for the lane's own packages."""
    _fake_versions(monkeypatch, conflicts_in="p:16")
    with pytest.raises(SystemExit, match="disagree"):
        cmd_qa._lanes_with_expected_versions(_lanes(_upgrade()), "lane", _lookup())


def _obs_by_major(monkeypatch):
    """Fake OBS: every package of a project is built at '<major>.0', the major
    taken from the project name (ppg:staging:16:containers -> 16)."""

    def fetch(apiurl, obs_project, repo_filter=None):
        local = obs_project.split(":", 2)[2]  # drop the isv:percona root
        path = resolve_project_path(local)
        if not path.is_dir():
            return None
        m = re.search(r":(1[4-9]):", obs_project + ":")
        version = "%s.0-1" % (m.group(1) if m else "1")
        return {
            pkg.name: {("RockyLinux_9", "x86_64"): version}
            for _, pkg in find_packages(path, local, recursive=False)
        }

    monkeypatch.setattr(cmd_qa, "project_binary_versions", fetch)


@pytest.mark.parametrize(
    "project,pipeline",
    [
        ("ppg:staging:common:containers", "docker-server-parallel-upgrade"),
        (
            "ppg:staging:common:extras:containers",
            "docker-server-parallel-custom-upgrade",
        ),
    ],
)
def test_real_upgrade_entries_get_each_majors_versions(
    monkeypatch, capsys, project, pipeline
):
    """End to end on the repository tree: 16-to-17 gets 16.x before, 17.x after."""
    _obs_by_major(monkeypatch)
    args = SimpleNamespace(
        project=project,
        rootprj="isv:percona",
        env_overrides=["REMOTE_OBS_ORG_INTERCONNECT:"],
        json=True,
        apiurl="http://obs",
        image_fallback_rootprj=None,
        expected_versions=True,
        profile=None,
    )
    cmd_qa.cmd_qa_show(args)
    combos = [
        r
        for r in json.loads(capsys.readouterr().out)
        if r.get("name") == "ubi9-16-to-17" and r["pipeline"] == pipeline
    ]
    assert combos
    for r in combos:
        old, new = _versions(r["params"]["OLD_EXPECTED_VERSIONS"]), _versions(
            r["params"]["EXPECTED_VERSIONS"]
        )
        assert (
            old["percona-postgresql"] == "16.0" and new["percona-postgresql"] == "17.0"
        )
        assert old["percona-pgaudit"] == "16.0" and new["percona-pgaudit"] == "17.0"
