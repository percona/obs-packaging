"""Slice selection: filter wiring, profile parsing, in-slice predicates (percona_obs.project_config)."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import percona_obs.cmd_profile as cmd_profile
import percona_obs.common as common
from percona_obs.project_config import (
    RepositoryFilter,
    project_slice_name,
    resolve_project_config,
)

_ROOT = """\
repositories:
  - name: RockyLinux_9
    paths:
      - subproject: common:deps:build
        repository: RockyLinux_9
    archs: [x86_64]
  - name: UBI_9
    paths:
      - subproject: common:deps:build
        repository: UBI_9
    archs: [x86_64]
debuginfo: {RockyLinux_9: true, UBI_9: true}
"""

LABS = RepositoryFilter(include_repos=("UBI_*", "ubi*", "images"))
BOO = RepositoryFilter(exclude_repos=("UBI_*", "ubi*", "images"))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    def make(files: dict) -> Path:
        root = tmp_path / "root"
        root.mkdir(exist_ok=True)
        (root / "macros.yaml").write_text("- M: 1\n")
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        monkeypatch.setattr(common, "REPO_ROOT", root)
        return root

    return make


@pytest.fixture(autouse=True)
def _reset_default_filter():
    common.set_default_repository_filter(None)
    yield
    common.set_default_repository_filter(None)


def _names(cfg):
    return [r["name"] for r in cfg["repositories"]]


# --- resolver wiring -------------------------------------------------------------


def test_project_slice_name(repo):
    root = repo({"project.yaml": _ROOT, "ppg/staging/17/project.yaml": "title: S\n"})
    assert project_slice_name(root) == ""
    assert project_slice_name(root / "ppg" / "staging" / "17") == "ppg:staging:17"


def test_resolve_with_explicit_filter(repo):
    root = repo({"project.yaml": _ROOT, "a/project.yaml": "title: A\n"})
    assert _names(resolve_project_config(root / "a", repo_filter=LABS)) == ["UBI_9"]
    boo = resolve_project_config(root / "a", repo_filter=BOO)
    assert _names(boo) == ["RockyLinux_9"]
    assert boo["debuginfo"] == {"RockyLinux_9": True}


def test_resolve_uses_process_default_and_explicit_empty_wins(repo):
    root = repo({"project.yaml": _ROOT, "a/project.yaml": "title: A\n"})
    assert common.get_default_repository_filter() is RepositoryFilter.EMPTY
    common.set_default_repository_filter(LABS)
    assert _names(resolve_project_config(root / "a")) == ["UBI_9"]
    assert _names(common._load_project_config_with_inheritance(root / "a")) == ["UBI_9"]
    assert _names(
        resolve_project_config(root / "a", repo_filter=RepositoryFilter.EMPTY)
    ) == [
        "RockyLinux_9",
        "UBI_9",
    ]


# --- profiles --------------------------------------------------------------------


@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    d = tmp_path / ".profile"
    d.mkdir()
    monkeypatch.setattr(cmd_profile, "_PROFILES_DIR", d)
    return d


def test_load_profile_filter(profiles_dir):
    (profiles_dir / "labs.yaml").write_text(
        "apiurl: https://labs\nrootprj: percona\n"
        "include-repositories: ['UBI_*', 'ubi*', images]\nexclude-projects: [common:containers:ubi8]\n"
    )
    (profiles_dir / "dev.yaml").write_text("apiurl: http://dev\nrootprj: home:Admin\n")
    f = cmd_profile._load_profile_filter("labs")
    assert f == RepositoryFilter(
        include_repos=("UBI_*", "ubi*", "images"),
        exclude_projects=("common:containers:ubi8",),
    )
    assert cmd_profile._load_profile_filter("dev") is RepositoryFilter.EMPTY
    assert cmd_profile._load_profile_filter("missing") is RepositoryFilter.EMPTY
    # scalar loader unchanged for apiurl/rootprj and drops the lists
    p = cmd_profile._load_profile("labs")
    assert p["apiurl"] == "https://labs" and p["rootprj"] == "percona"
    assert "include-repositories" not in p


def test_profile_create_writes_and_round_trips_filter(profiles_dir, capsys):
    args = SimpleNamespace(
        apiurl="https://labs",
        rootprj="percona",
        name="labs",
        env_overrides=[],
        profile=None,
        include_repos=["UBI_*,ubi*", "images"],
        exclude_repos=[],
        include_projects=[],
        exclude_projects=["common:containers:ubi8"],
        narrow_repos=[],
    )
    cmd_profile.cmd_profile_create(args)
    data = yaml.safe_load((profiles_dir / "labs.yaml").read_text())
    assert data["include-repositories"] == ["UBI_*", "ubi*", "images"]
    assert data["exclude-projects"] == ["common:containers:ubi8"]
    assert "exclude-repositories" not in data
    # -P labs profile create labs with no filter flags keeps the lists
    args2 = SimpleNamespace(
        apiurl="https://labs",
        rootprj="percona",
        name="labs",
        env_overrides=["X:1"],
        profile="labs",
        include_repos=[],
        exclude_repos=[],
        include_projects=[],
        exclude_projects=[],
        narrow_repos=[],
    )
    cmd_profile.cmd_profile_create(args2)
    data2 = yaml.safe_load((profiles_dir / "labs.yaml").read_text())
    assert data2["include-repositories"] == ["UBI_*", "ubi*", "images"]
    assert data2["env"] == [{"name": "X", "value": "1"}]
    cmd_profile.cmd_profile_list(SimpleNamespace())
    out = capsys.readouterr().out
    assert "include-repositories:" in out and "UBI_*, ubi*, images" in out


# --- predicates ------------------------------------------------------------------

from percona_obs.project_config import package_in_slice, project_in_slice  # noqa: E402

_TREE = {
    "project.yaml": _ROOT,
    "ppg/staging/17/project.yaml": "title: S\n",
    "ppg/staging/17/percona-postgresql/obs/_service": "",
    "ppg/staging/17/bison/obs/_service": "",
    "ppg/staging/17/bison/package.yaml": "build:\n  UBI_9: false\n",
    "ppg/staging/17/blanket/obs/_service": "",
    "ppg/staging/17/blanket/package.yaml": "build:\n  disable: true\n",
    "ppg/staging/17/containers/project.yaml": (
        "repositories-inherit: false\nrepositories:\n  - name: ubi9\n    paths: []\n    archs: [x86_64]\n"
    ),
    "ppg/staging/17/containers/image/obs/Dockerfile": "FROM scratch\n",
    "ppg/staging/extras/project.yaml": "repositories-inherit: false\n",
}


def test_project_in_slice(repo):
    root = repo(_TREE)
    s17 = root / "ppg/staging/17"
    assert project_in_slice(s17, repo_filter=RepositoryFilter.EMPTY)
    assert project_in_slice(s17, repo_filter=LABS)
    assert project_in_slice(s17, repo_filter=BOO)
    assert project_in_slice(root, repo_filter=LABS)  # root keeps UBI_9
    containers = s17 / "containers"
    assert project_in_slice(containers, repo_filter=LABS)
    assert not project_in_slice(containers, repo_filter=BOO)
    assert not project_in_slice(
        containers, repo_filter=RepositoryFilter(exclude_projects=("*:containers",))
    )
    # zero repositories: out everywhere, even unfiltered
    assert not project_in_slice(
        root / "ppg/staging/extras", repo_filter=RepositoryFilter.EMPTY
    )
    # pre-resolved config and cache are honoured
    cfg = resolve_project_config(containers, repo_filter=BOO)
    cache: dict[Path, bool] = {}
    assert not project_in_slice(containers, repo_filter=BOO, config=cfg, cache=cache)
    assert cache == {containers: False}
    cache[containers] = True
    assert project_in_slice(
        containers, repo_filter=BOO, cache=cache
    )  # cache is authoritative


def test_package_in_slice(repo):
    root = repo(_TREE)
    s17 = root / "ppg/staging/17"
    assert package_in_slice(s17 / "percona-postgresql", repo_filter=LABS)
    assert package_in_slice(s17 / "percona-postgresql", repo_filter=BOO)
    assert not package_in_slice(
        s17 / "bison", repo_filter=LABS
    )  # disabled on its only labs repo
    assert package_in_slice(s17 / "bison", repo_filter=BOO)
    assert package_in_slice(
        s17 / "blanket", repo_filter=LABS
    )  # shorthand map is not per-repo
    assert package_in_slice(s17 / "containers" / "image", repo_filter=LABS)
    assert not package_in_slice(
        s17 / "containers" / "image", repo_filter=BOO
    )  # project out
    # default filter applies when none is passed
    common.set_default_repository_filter(LABS)
    assert not package_in_slice(s17 / "bison")
