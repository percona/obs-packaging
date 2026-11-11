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
        {
            "_aggregate": _AGG.format(
                prj="ppg:staging:common:tools", pkg="percona-pgbouncer"
            )
        },
    )
    _pkg(src / "etcd", {"_aggregate": _AGG.format(prj="ppg:common:deps", pkg="etcd")})
    _pkg(src / "percona-postgresql", {"_service": "<services/>"})
    # the aggregate targets must exist in the tree
    for prj, pkg in (
        ("ppg/staging/common/tools", "percona-pgbouncer"),
        ("ppg/common/deps", "etcd"),
    ):
        _pkg(root / prj / pkg, {"_service": "<services/>"})
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.whole_projects == []
    assert scope.packages == {
        "isv:percona:ppg:staging:common:tools": {"percona-pgbouncer"},
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
        {
            "_aggregate": _AGG.format(
                prj="ppg:staging:common:tools", pkg="percona-pgbadger"
            )
        },
    )
    _pkg(
        root / "ppg/staging/common/tools/percona-pgbadger", {"_service": "<services/>"}
    )
    src = root / "ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    (src / "percona-pgbadger").symlink_to("../_shared/percona-pgbadger")
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.packages == {
        "isv:percona:ppg:staging:common:tools": {"percona-pgbadger"}
    }


def test_subproject_aggregates_included_and_self_sources_skipped(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    src = root / "ppg/staging/17"
    (src / "containers").mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    (src / "containers" / "project.yaml").write_text("title: E\n")
    _pkg(
        src / "containers" / "ydiff",
        {"_aggregate": _AGG.format(prj="ppg:common:deps", pkg="ydiff")},
    )
    _pkg(
        src / "self",
        {"_aggregate": _AGG.format(prj="ppg:staging:17:containers", pkg="ydiff")},
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
                            {
                                "subproject": "ppg:staging:common:tools",
                                "repository": "UBI_9",
                            },
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
    for sub in ("ppg/staging/18", "ppg/staging/common/tools", "ppg/common/deps"):
        (root / sub).mkdir(parents=True)
    scope = rs.collect_release_scope(src, "ppg:staging:containers", "isv:percona", {})
    assert scope.whole_projects == [
        "isv:percona:ppg:staging:18",
        "isv:percona:ppg:staging:common:tools",
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


def _image_project_yaml(paths: list[str]) -> str:
    return yaml.dump(
        {
            "repositories-inherit": False,
            "project-config-inherit": False,
            "repositories": [
                {
                    "name": "ubi9",
                    "archs": ["x86_64"],
                    "paths": [{"subproject": p, "repository": "UBI_9"} for p in paths],
                }
            ],
        }
    )


def test_common_parent_collects_paths_from_image_subprojects(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    for major in ("17", "18"):
        (root / "ppg/staging" / major).mkdir(parents=True)
        (root / "ppg/staging" / major / "project.yaml").write_text("title: S\n")
    (root / "ppg/common/deps").mkdir(parents=True)
    (root / "ppg/common/deps/project.yaml").write_text("title: D\n")
    src = root / "ppg/staging/common"
    (src / "tools" / "containers").mkdir(parents=True)
    (src / "containers").mkdir()
    (src / "project.yaml").write_text(
        "repositories-inherit: false\nproject-config-inherit: false\n"
    )
    (src / "tools" / "project.yaml").write_text("title: T\n")
    _pkg(src / "tools" / "percona-pgbouncer", {"_service": "<services/>"})
    (src / "containers" / "project.yaml").write_text(
        _image_project_yaml(
            ["ppg:staging:18", "ppg:common:deps", "ppg:staging:common:tools"]
        )
    )
    _pkg(src / "containers" / "upgrade", {"Dockerfile": "FROM x\n"})
    (src / "tools" / "containers" / "project.yaml").write_text(
        _image_project_yaml(["ppg:staging:17", "ppg:staging:common:tools"])
    )
    _pkg(src / "tools" / "containers" / "percona-pgbouncer", {"Dockerfile": "FROM x\n"})
    # the bundled containers subproject belongs to the common unit; the
    # tools:containers image project belongs to the tools unit
    scope = rs.collect_release_scope(src, "ppg:staging:common", "isv:percona", {})
    assert scope.whole_projects == [
        "isv:percona:ppg:staging:18",
        "isv:percona:ppg:common:deps",
    ]
    assert scope.packages == {}
    tools = rs.collect_release_scope(
        src / "tools", "ppg:staging:common:tools", "isv:percona", {}
    )
    assert tools.whole_projects == ["isv:percona:ppg:staging:17"]
    assert tools.packages == {}


def test_major_with_image_subproject_keeps_aggregate_only_scope(tmp_path, monkeypatch):
    root = _mk_root(tmp_path, monkeypatch)
    for sub in ("ppg/common/deps", "ppg/staging/16"):
        (root / sub).mkdir(parents=True)
        (root / sub / "project.yaml").write_text("title: X\n")
    src = root / "ppg/staging/17"
    (src / "containers").mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    _pkg(src / "percona-postgresql", {"_service": "<services/>"})
    (src / "containers" / "project.yaml").write_text(
        _image_project_yaml(["ppg:common:deps", "ppg:staging:16"])
    )
    _pkg(src / "containers" / "upgrade", {"Dockerfile": "FROM x\n"})
    scope = rs.collect_release_scope(src, "ppg:staging:17", "isv:percona", {})
    assert scope.whole_projects == []


def _unit_tree(tmp_path, monkeypatch):
    root = tmp_path / "root"
    src = root / "ppg/staging/18"
    for sub in ("", "containers", "tarballs", "extras", "extras/containers", "tde"):
        d = src / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.yaml").write_text("title: x\n")
    (src / "containers" / "ubi9").mkdir()
    (src / "containers" / "ubi9" / "project.yaml").write_text("title: x\n")
    for pkg in ("percona-pgvector", "extras/percona-postgresql", "containers/img"):
        (src / pkg / "obs").mkdir(parents=True)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(rs, "REPO_ROOT", root)
    return root, src


def test_release_unit_members_main(tmp_path, monkeypatch):
    _, src = _unit_tree(tmp_path, monkeypatch)
    ids = [i for i, _ in rs.release_unit_members(src, "ppg:staging:18")]
    assert ids == [
        "ppg:staging:18",
        "ppg:staging:18:containers",
        "ppg:staging:18:tarballs",
    ]


def test_release_unit_members_nested_and_bare(tmp_path, monkeypatch):
    _, src = _unit_tree(tmp_path, monkeypatch)
    ids = [
        i for i, _ in rs.release_unit_members(src / "extras", "ppg:staging:18:extras")
    ]
    assert ids == ["ppg:staging:18:extras", "ppg:staging:18:extras:containers"]
    ids = [i for i, _ in rs.release_unit_members(src / "tde", "ppg:staging:18:tde")]
    assert ids == ["ppg:staging:18:tde"]


def test_unit_packages_and_server_package_are_unit_scoped(tmp_path, monkeypatch):
    _, src = _unit_tree(tmp_path, monkeypatch)
    names = sorted(p.name for _, p in rs.unit_packages(src, "ppg:staging:18"))
    assert names == ["img", "percona-pgvector"]
    # the server package lives in extras only: the main unit has none
    assert rs.tree_has_server_package(src) is False
    assert rs.tree_has_server_package(src / "extras") is True


def test_bundled_parent_and_nested_unit_roots(tmp_path, monkeypatch):
    _, src = _unit_tree(tmp_path, monkeypatch)
    assert rs.bundled_parent("ppg:staging:18:containers") == "ppg:staging:18"
    assert rs.bundled_parent("ppg:staging:18:extras") is None
    assert rs.nested_unit_roots(src, "ppg:staging:18") == [
        "ppg:staging:18:extras",
        "ppg:staging:18:tde",
    ]


@pytest.mark.parametrize(
    "project,release_name,rel,relprj,prefix,counter",
    [
        ("ppg:staging:18", None, "ppg/releases/18", "ppg:releases:18", "", "18"),
        (
            "ppg:staging:18:extras",
            None,
            "ppg/releases/18/extras",
            "ppg:releases:18:extras",
            "extras-",
            "18-extras",
        ),
        (
            "ppg:staging:common:upgrade:extras",
            None,
            "ppg/releases/common/upgrade/extras",
            "ppg:releases:common:upgrade:extras",
            "upgrade-extras-",
            "common-upgrade-extras",
        ),
        ("ppg:staging:18", "lts", "ppg/releases/lts", "ppg:releases:lts", "", "lts"),
    ],
)
def test_release_location(
    tmp_path, monkeypatch, project, release_name, rel, relprj, prefix, counter
):
    root, _ = _unit_tree(tmp_path, monkeypatch)
    loc = rs.release_location(project, release_name)
    assert loc.release_dir == root / rel
    assert loc.release_project == relprj
    assert loc.id_prefix == prefix
    assert loc.counter_name == counter
    assert loc.major == project.split(":")[2]
