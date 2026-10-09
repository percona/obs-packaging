# tests/test_release_scope.py
"""Unit tests for percona_obs.release_scope (pure tree derivation)."""

from pathlib import Path

import pytest
import yaml

import percona_obs.common as common
import percona_obs.release_scope as rs
from percona_obs.project_config import RepositoryFilter

_AGG = (
    "<aggregatelist>\n"
    '  <aggregate project="${{OBS_ROOTPRJ}}:{prj}">\n'
    "    <package>{pkg}</package>\n"
    "  </aggregate>\n"
    "</aggregatelist>\n"
)


def _mk_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    (root / "macros.yaml").write_text("- M: 1\n")
    (root / "project.yaml").write_text(
        yaml.dump({"repositories": [{"name": "R9", "archs": ["x86_64"], "paths": []}]})
    )
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(rs, "REPO_ROOT", root)
    return root


def _pkg(path: Path, files: dict[str, str]) -> None:
    (path / "obs").mkdir(parents=True)
    for name, text in files.items():
        (path / "obs" / name).write_text(text)


def test_aggregate_sources_are_package_scoped(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    _pkg(
        src / "percona-pgbouncer",
        {"_aggregate": _AGG.format(prj="ppg:staging:tools", pkg="percona-pgbouncer")},
    )
    _pkg(src / "etcd", {"_aggregate": _AGG.format(prj="ppg:common:deps", pkg="etcd")})
    _pkg(src / "percona-postgresql", {"_service": "<services/>"})
    # the aggregate targets must exist in the tree
    for prj, pkg in (
        ("ppg/staging/tools", "percona-pgbouncer"),
        ("ppg/common/deps", "etcd"),
    ):
        _pkg(root / prj / pkg, {"_service": "<services/>"})
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.whole_projects == []
    assert scope.packages == {
        "isv:percona:ppg:staging:tools": {"percona-pgbouncer"},
        "isv:percona:ppg:common:deps": {"etcd"},
    }


def test_external_and_packageless_aggregates_ignored(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    _pkg(
        src / "ext",
        {
            "_aggregate": '<aggregatelist><aggregate project="openSUSE:Factory"><package>x</package></aggregate></aggregatelist>'
        },
    )
    _pkg(
        src / "whole",
        {
            "_aggregate": '<aggregatelist><aggregate project="${OBS_ROOTPRJ}:ppg:common:deps"/></aggregatelist>'
        },
    )
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.packages == {}
    assert scope.whole_projects == []


def test_symlinked_shared_package_is_followed(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    shared = root / "ppg/staging/_shared/percona-pgbadger"
    _pkg(
        shared,
        {"_aggregate": _AGG.format(prj="ppg:staging:tools", pkg="percona-pgbadger")},
    )
    _pkg(root / "ppg/staging/tools/percona-pgbadger", {"_service": "<services/>"})
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    (src / "percona-pgbadger").symlink_to("../_shared/percona-pgbadger")
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.packages == {"isv:percona:ppg:staging:tools": {"percona-pgbadger"}}


def test_subproject_aggregates_included_and_self_sources_skipped(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    (src / "extras").mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    (src / "extras" / "project.yaml").write_text("title: E\n")
    _pkg(
        src / "extras" / "ydiff",
        {"_aggregate": _AGG.format(prj="ppg:common:deps", pkg="ydiff")},
    )
    _pkg(
        src / "self",
        {"_aggregate": _AGG.format(prj="ppg:staging:17:extras", pkg="ydiff")},
    )
    _pkg(root / "ppg/common/deps/ydiff", {"_service": "<services/>"})
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.packages == {"isv:percona:ppg:common:deps": {"ydiff"}}


def test_container_source_adds_path_prefix_projects(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/containers"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text(
        yaml.dump(
            {
                "repositories-inherit": False,
                "project-config-inherit": False,
                "repositories": [
                    {
                        "name": "ubi9",
                        "archs": ["x86_64"],
                        "paths": [
                            {"project": "RedHat:UBI:Registry", "repository": "images"},
                            {"subproject": "ppg:staging:18", "repository": "UBI_9"},
                            {"subproject": "ppg:staging:tools", "repository": "UBI_9"},
                            {"subproject": "ppg:common:deps", "repository": "UBI_9"},
                            {
                                "subproject": "ppg:staging:containers",
                                "repository": "ubi9",
                            },
                        ],
                    },
                    {
                        "name": "ubi8",
                        "archs": ["x86_64"],
                        "paths": [
                            {"subproject": "ppg:staging:18", "repository": "UBI_8"},
                            {"subproject": "ppg:common:deps", "repository": "UBI_8"},
                        ],
                    },
                ],
            }
        )
    )
    _pkg(src / "percona-pgbouncer", {"Dockerfile": "FROM x\n"})
    # path-prefix sources must exist in the tree (missing ones are skipped)
    for sub in ("ppg/staging/18", "ppg/staging/tools", "ppg/common/deps"):
        (root / sub).mkdir(parents=True)
    scope = rs.collect_release_scope(src, "ppg:staging:containers", "isv:percona", {})
    assert scope.whole_projects == [
        "isv:percona:ppg:staging:18",
        "isv:percona:ppg:staging:tools",
        "isv:percona:ppg:common:deps",
    ]
    assert scope.packages == {}


def test_non_container_source_ignores_path_prefix(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text(
        yaml.dump(
            {
                "path-prefix": [
                    {"subproject": "ppg:common:deps", "repository": "%_repository"}
                ]
            }
        )
    )
    _pkg(src / "percona-postgresql", {"_service": "<services/>"})
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.whole_projects == []


_UBI_ONLY = RepositoryFilter(include_repos=("UBI_*",))


@pytest.fixture
def ubi_only_slice():
    common.set_default_repository_filter(_UBI_ONLY)
    try:
        yield
    finally:
        common.set_default_repository_filter(None)


def _two_repo_root(root: Path) -> None:
    (root / "project.yaml").write_text(
        yaml.dump(
            {
                "repositories": [
                    {"name": "RockyLinux_9", "archs": ["x86_64"], "paths": []},
                    {"name": "UBI_9", "archs": ["x86_64"], "paths": []},
                ]
            }
        )
    )


def test_aggregate_target_out_of_slice_is_skipped(
    tmp_path, monkeypatch, ubi_only_slice
):
    root = _mk_root(tmp_path, monkeypatch)
    _two_repo_root(root)
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    _pkg(
        src / "llvm-21",
        {"_aggregate": _AGG.format(prj="ppg:common:deps", pkg="llvm-21")},
    )
    _pkg(src / "etcd", {"_aggregate": _AGG.format(prj="ppg:common:deps", pkg="etcd")})
    deps = root / "ppg/common/deps"
    _pkg(deps / "llvm-21", {"_service": "<services/>"})
    (deps / "llvm-21" / "package.yaml").write_text(
        yaml.dump({"build": {"UBI_9": False}})
    )
    _pkg(deps / "etcd", {"_service": "<services/>"})
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.packages == {"isv:percona:ppg:common:deps": {"etcd"}}


def test_missing_aggregate_target_package_is_skipped(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    _pkg(src / "ghost", {"_aggregate": _AGG.format(prj="ppg:common:deps", pkg="ghost")})
    (root / "ppg/common/deps").mkdir(parents=True)
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.packages == {}


def test_container_path_prefix_out_of_slice_is_skipped(
    tmp_path, monkeypatch, ubi_only_slice
):
    root = _mk_root(tmp_path, monkeypatch)
    _two_repo_root(root)
    rocky_only = root / "ppg/staging/rocky-only"
    rocky_only.mkdir(parents=True)
    (rocky_only / "project.yaml").write_text(
        yaml.dump(
            {
                "repositories-inherit": False,
                "repositories": [
                    {"name": "RockyLinux_9", "archs": ["x86_64"], "paths": []}
                ],
            }
        )
    )
    (root / "ppg/staging/18").mkdir(parents=True)
    (root / "ppg/staging/18/project.yaml").write_text("title: S18\n")
    src = root / "ppg/staging/containers"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text(
        yaml.dump(
            {
                "repositories-inherit": False,
                "project-config-inherit": False,
                "repositories": [
                    {
                        "name": "ubi9",
                        "archs": ["x86_64"],
                        "paths": [
                            {"subproject": "ppg:staging:18", "repository": "UBI_9"},
                            {
                                "subproject": "ppg:staging:rocky-only",
                                "repository": "RockyLinux_9",
                            },
                            {"subproject": "ppg:staging:absent", "repository": "UBI_9"},
                        ],
                    }
                ],
            }
        )
    )
    _pkg(src / "percona-pgbouncer", {"Dockerfile": "FROM x\n"})
    scope = rs.collect_release_scope(src, "ppg:staging:containers", "isv:percona", {})
    assert scope.whole_projects == ["isv:percona:ppg:staging:18"]


def test_tree_has_server_package_major_tree(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    _pkg(src / "percona-postgresql", {"_service": "<services/>"})
    _pkg(src / "percona-pgbouncer", {"_service": "<services/>"})
    assert rs.tree_has_server_package(src) is True


def test_tree_has_server_package_suffixed_name(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/18"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    _pkg(src / "percona-postgresql18", {"_service": "<services/>"})
    assert rs.tree_has_server_package(src) is True


def test_tree_has_server_package_common_tree(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/common"
    (src / "tools").mkdir(parents=True)
    (src / "containers").mkdir()
    (src / "project.yaml").write_text("repositories-inherit: false\n")
    (src / "tools" / "project.yaml").write_text("title: T\n")
    (src / "containers" / "project.yaml").write_text("repositories-inherit: false\n")
    _pkg(src / "tools" / "percona-pgbouncer", {"_service": "<services/>"})
    _pkg(
        src / "tools" / "percona-postgresql-common-lookalike",
        {"_service": "<services/>"},
    )
    _pkg(
        src / "containers" / "percona-distribution-postgresql-upgrade",
        {"Dockerfile": "FROM x\n"},
    )
    assert rs.tree_has_server_package(src) is False
