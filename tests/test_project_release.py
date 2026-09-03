"""Unit tests for project release mirror regeneration (percona_obs.cmd_project)."""

import argparse
from pathlib import Path

import pytest
import yaml

import percona_obs.cmd_project as cmd_project
from percona_obs.cmd_project import _rewrite_subproject_paths, _write_release_tree


def _staging_tree(tmp_path: Path) -> Path:
    src = tmp_path / "root/ppg/staging/17"
    (src).mkdir(parents=True)
    (src / "project.yaml").write_text("repositories: []\n")
    (src / "containers").mkdir()
    (src / "containers" / "project.yaml").write_text(
        yaml.dump(
            {
                "repositories": [
                    {
                        "name": "ubi9",
                        "paths": [
                            {"subproject": "ppg:staging:17", "repository": "UBI_9"},
                            {
                                "subproject": "common:containers:ubi9",
                                "repository": "images",
                            },
                        ],
                        "archs": ["x86_64"],
                    },
                ]
            }
        )
    )
    (src / "tarballs").mkdir()
    (src / "tarballs" / "project.yaml").write_text(
        yaml.dump(
            {
                "publish": {"RockyLinux_9": False},
                "repositories": [
                    {
                        "name": "ssl3",
                        "paths": [
                            {
                                "subproject": "ppg:staging:17:tarballs",
                                "repository": "RockyLinux_9",
                            },
                        ],
                        "archs": ["x86_64"],
                    },
                ],
            }
        )
    )
    return src


def test_rewrite_keeps_self_references():
    repos = [
        {
            "name": "ssl3",
            "paths": [
                {
                    "subproject": "ppg:staging:17:tarballs",
                    "repository": "RockyLinux_9",
                }
            ],
            "archs": ["x86_64"],
        }
    ]
    out = _rewrite_subproject_paths(repos, "ppg:staging:17", "ppg:releases:17")
    assert out[0]["paths"] == [
        {"subproject": "ppg:releases:17:tarballs", "repository": "RockyLinux_9"}
    ]


def test_write_release_tree_creates_all_mirrors_and_deletes_stale(
    tmp_path, monkeypatch
):
    src = _staging_tree(tmp_path)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    rel = tmp_path / "root/ppg/releases/17"
    # simulate the pre-restructure leftover
    (rel / "containers" / "ubi9").mkdir(parents=True)
    (rel / "containers" / "ubi9" / "project.yaml").write_text("build: false\n")

    written = _write_release_tree(
        rel,
        {"build": False, "repositories": []},
        src,
        "ppg:staging:17",
        "ppg:releases:17",
        "ppg",
        "17",
    )
    assert (rel / "project.yaml").is_file()
    assert (rel / "containers" / "project.yaml").is_file()
    assert (rel / "tarballs" / "project.yaml").is_file()
    assert not (rel / "containers" / "ubi9").exists()  # stale dir deleted
    tarballs = yaml.safe_load((rel / "tarballs" / "project.yaml").read_text())
    assert tarballs["build"] is False
    assert tarballs["publish"] == {"RockyLinux_9": False}  # publish carried over
    assert (
        tarballs["repositories"][0]["paths"][0]["subproject"]
        == "ppg:releases:17:tarballs"
    )
    assert len(written) == 3


def test_write_release_tree_deletes_nested_stale_dirs_without_crashing(
    tmp_path, monkeypatch
):
    src = _staging_tree(tmp_path)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    rel = tmp_path / "root/ppg/releases/17"
    # multi-level stale branch: both the parent and a nested child carry their
    # own project.yaml, and neither maps to a current source subproject. The
    # child dirname ("zzz_nested") is chosen to sort *after* "project.yaml"
    # so "oldsub/project.yaml" < "oldsub/zzz_nested/project.yaml" — the parent
    # is processed (and rmtree'd) before the child is reached.
    (rel / "oldsub" / "zzz_nested").mkdir(parents=True)
    (rel / "oldsub" / "project.yaml").write_text("build: false\n")
    (rel / "oldsub" / "zzz_nested" / "project.yaml").write_text("build: false\n")

    written = _write_release_tree(
        rel,
        {"build": False, "repositories": []},
        src,
        "ppg:staging:17",
        "ppg:releases:17",
        "ppg",
        "17",
    )

    assert not (rel / "oldsub").exists()  # whole stale branch removed, no crash
    # expected sibling mirrors survive untouched
    assert (rel / "containers" / "project.yaml").is_file()
    assert (rel / "tarballs" / "project.yaml").is_file()
    assert len(written) == 3


def test_tier_validation_rejects_devel(monkeypatch):
    args = argparse.Namespace(
        project="ppg:devel:18",
        rootprj="home:Admin",
        apiurl=None,
        release_name=None,
        release_id=None,
    )

    monkeypatch.setattr(cmd_project, "resolve_project_path", lambda pid: Path("/nope"))
    with pytest.raises(SystemExit, match="staging-tier"):
        cmd_project.cmd_project_release(args)


def test_container_flavor_label_old_and_new_layouts():
    assert (
        cmd_project._container_flavor_label(
            "x:ppg:releases:17:containers:ubi9", "images"
        )
        == "ubi9"
    )
    assert (
        cmd_project._container_flavor_label("x:ppg:staging:17:containers", "ubi9")
        == "ubi9"
    )
    assert (
        cmd_project._container_flavor_label("x:ppg:staging:17:containers", "ubi8")
        == "ubi8"
    )


def test_fetch_subproject_container_pkgs_per_flavor(monkeypatch):
    monkeypatch.setattr(cmd_project, "_fetch_obs_package_names", lambda a, p: {"img"})
    monkeypatch.setattr(
        cmd_project,
        "_fetch_all_pkg_repo_archs",
        lambda a, p: {"img": [("ubi8", "x86_64"), ("ubi9", "x86_64")]},
    )
    monkeypatch.setattr(
        cmd_project, "_detect_obs_container_info", lambda a, p, k: {"kind": "docker"}
    )
    monkeypatch.setattr(
        cmd_project,
        "_fetch_build_container_packages",
        lambda a, prj, repo, arch, pkg, root: {"pg": f"17.11-{repo}"},
    )
    out = cmd_project._fetch_subproject_container_pkgs(
        "http://obs", "x:staging:17:containers", "x"
    )
    assert set(out) == {"img (ubi8)", "img (ubi9)"}


def test_fetch_all_pkg_repo_archs_prefers_succeeded(monkeypatch):
    import percona_obs.obs_api as obs_api

    xml = (
        b"<resultlist>"
        b'<result repository="ubi8" arch="x86_64"><status package="img" code="succeeded"/></result>'
        b'<result repository="ubi8" arch="aarch64"><status package="img" code="failed"/></result>'
        b'<result repository="ubi9" arch="x86_64"><status package="img" code="succeeded"/></result>'
        b"</resultlist>"
    )

    class R:  # noqa: N801
        def read(self):
            return xml

    monkeypatch.setattr(obs_api.osc.core, "makeurl", lambda *a: "http://x")
    monkeypatch.setattr(obs_api.osc.connection, "http_GET", lambda u: R())
    out = obs_api._fetch_all_pkg_repo_archs("http://obs", "prj")
    assert out == {"img": [("ubi8", "x86_64"), ("ubi9", "x86_64")]}


def test_find_pkg_service_walks_subprojects(tmp_path):
    src = tmp_path / "staging17"
    (src / "extras" / "percona-rum" / "obs").mkdir(parents=True)
    (src / "extras" / "percona-rum" / "obs" / "_service").write_text("<services/>")
    assert cmd_project._find_pkg_service(src, "percona-rum") is not None
    assert cmd_project._find_pkg_service(src, "nope") is None


def test_registry_prefix_old_and_new_layouts():
    old = cmd_project._container_registry_prefix(
        "isv:percona:ppg:releases:17:containers:ubi9", "isv:percona", None, "images"
    )
    assert (
        old
        == "registry.opensuse.org/isv/percona/ppg/releases/17/containers/ubi9/images"
    )
    new = cmd_project._container_registry_prefix(
        "isv:percona:ppg:releases:17:containers", "isv:percona", None, "ubi9"
    )
    assert new == "registry.opensuse.org/isv/percona/ppg/releases/17/containers/ubi9"


def test_project_image_repo_names_new_layout(tmp_path):
    proj = tmp_path / "containers"
    (proj / "img-a" / "obs").mkdir(parents=True)
    (proj / "img-a" / "obs" / "Dockerfile").write_text("FROM x\n")
    config = {"repositories": [{"name": "ubi8"}, {"name": "ubi9"}]}
    assert cmd_project._project_image_repo_names(proj, config) == {"ubi8", "ubi9"}


def test_project_image_repo_names_old_layout_keeps_helper_repos(tmp_path):
    proj = tmp_path / "containers-ubi9"
    (proj / "img-a" / "obs").mkdir(parents=True)
    (proj / "img-a" / "obs" / "Dockerfile").write_text("FROM x\n")
    config = {"repositories": [{"name": "RockyLinux_9"}, {"name": "images"}]}
    assert cmd_project._project_image_repo_names(proj, config) == {"images"}


def test_project_image_repo_names_mixed_project_is_not_images(tmp_path):
    proj = tmp_path / "tarballs"
    (proj / "percona-psql" / "obs").mkdir(parents=True)
    (proj / "percona-psql" / "obs" / "_service").write_text("<services/>")
    config = {"repositories": [{"name": "ssl3"}, {"name": "RockyLinux_9"}]}
    assert cmd_project._project_image_repo_names(proj, config) == set()


def test_project_image_repo_names_packageless_containers_dir(tmp_path):
    # Release mirror project: only project.yaml, no local package dirs.
    proj = tmp_path / "containers"
    proj.mkdir()
    config = {"repositories": [{"name": "ubi8"}, {"name": "ubi9"}]}
    assert cmd_project._project_image_repo_names(
        proj, config, "isv:percona:ppg:releases:17:containers"
    ) == {"ubi8", "ubi9"}


def test_project_image_repo_names_packageless_non_containers_dir(tmp_path):
    proj = tmp_path / "tarballs"
    proj.mkdir()
    config = {"repositories": [{"name": "ssl1.1"}, {"name": "ssl3"}]}
    assert (
        cmd_project._project_image_repo_names(
            proj, config, "isv:percona:ppg:releases:17:tarballs"
        )
        == set()
    )


def test_commit_release_paths_scopes_add_and_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    release_dir = tmp_path / "root" / "ppg" / "releases" / "17.9"
    release_dir.mkdir(parents=True)

    calls = []

    def fake_run(cmd, cwd=None, check=None):
        calls.append(cmd)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(cmd_project.subprocess, "run", fake_run)

    committed_paths = ["root/ppg/staging/macros.yaml"]
    cmd_project._commit_release_paths("release: 17.9", committed_paths, release_dir)

    assert len(calls) == 2
    add_cmd, commit_cmd = calls
    release_dir_rel = "root/ppg/releases/17.9"
    assert add_cmd[:3] == ["git", "add", "-A"]
    assert add_cmd[4:] == [*committed_paths, release_dir_rel]
    assert commit_cmd[:5] == ["git", "commit", "-s", "-m", "release: 17.9"]
    assert commit_cmd[6:] == [*committed_paths, release_dir_rel]
    # An unrelated file staged beforehand elsewhere must not be part of the
    # pathspec list passed to either git add or git commit.
    assert "unrelated/file.txt" not in add_cmd
    assert "unrelated/file.txt" not in commit_cmd


def test_project_image_repo_names_packageless_containers_with_images_repo(tmp_path):
    proj = tmp_path / "containers"
    proj.mkdir()
    config = {"repositories": [{"name": "RockyLinux_9"}, {"name": "images"}]}
    assert cmd_project._project_image_repo_names(
        proj, config, "isv:percona:ppg:releases:17:containers"
    ) == {"images"}
