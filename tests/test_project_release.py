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


def test_suffix_subproject_versions():
    out = cmd_project._suffix_subproject_versions(
        {"percona-postgresql": "3.5-1"}, "extras"
    )
    assert out == {"percona-postgresql (extras)": "3.5-1"}


def test_split_changelog_key():
    assert cmd_project._split_changelog_key("percona-postgresql (extras)") == (
        "percona-postgresql",
        "extras",
    )
    assert cmd_project._split_changelog_key("percona-postgresql") == (
        "percona-postgresql",
        None,
    )
    assert cmd_project._split_changelog_key("x (extras:containers)") == (
        "x",
        "extras:containers",
    )


def _write_obs_service(path: Path, url: str, revision: str = "v1.0") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<services>\n"
        '  <service name="obs_scm">\n'
        f'    <param name="url">{url}</param>\n'
        f'    <param name="revision">{revision}</param>\n'
        "  </service>\n"
        "</services>\n"
    )


def test_changelog_distinguishes_colliding_package_names(tmp_path):
    src = tmp_path / "staging17"
    _write_obs_service(
        src / "percona-postgresql" / "obs" / "_service",
        "https://github.com/percona/toplevel.git",
    )
    _write_obs_service(
        src / "extras" / "percona-postgresql" / "obs" / "_service",
        "https://github.com/percona/extras.git",
    )

    source_versions = {
        "percona-postgresql": "17.11-1",
        "percona-postgresql (extras)": "3.5-1",
    }
    release_versions = {
        "percona-postgresql": "17.10-1",
        "percona-postgresql (extras)": "3.5-1",
    }

    section = cmd_project._build_changelog_section(
        "17.11-1", source_versions, release_versions, src
    )

    assert "- percona-postgresql: update upstream version 17.11" in section
    assert "percona/toplevel" in section
    assert "percona-postgresql (extras)" not in section
    assert "percona/extras" not in section


def test_changelog_distinguishes_colliding_package_names_extras_changed(tmp_path):
    src = tmp_path / "staging17"
    _write_obs_service(
        src / "percona-postgresql" / "obs" / "_service",
        "https://github.com/percona/toplevel.git",
    )
    _write_obs_service(
        src / "extras" / "percona-postgresql" / "obs" / "_service",
        "https://github.com/percona/extras.git",
    )

    source_versions = {
        "percona-postgresql": "17.10-1",
        "percona-postgresql (extras)": "3.6-1",
    }
    release_versions = {
        "percona-postgresql": "17.10-1",
        "percona-postgresql (extras)": "3.5-1",
    }

    section = cmd_project._build_changelog_section(
        "17.11-1", source_versions, release_versions, src
    )

    assert "- percona-postgresql (extras): update upstream version 3.6" in section
    assert "percona/extras" in section
    assert "percona/toplevel" not in section
    assert "- percona-postgresql: update upstream version" not in section


def test_container_changelog_label_keeps_bare_flavor_for_containers():
    lbl = cmd_project._container_changelog_label
    parent = "x:ppg:staging:17"
    assert lbl("x:ppg:staging:17:containers", "ubi9", parent) == "ubi9"
    # old layout (release project) maps onto the same key as the new layout
    assert (
        lbl("x:ppg:releases:17:containers:ubi9", "images", "x:ppg:releases:17")
        == "ubi9"
    )
    # no parent → legacy behaviour
    assert lbl("x:ppg:staging:17:containers", "ubi8", None) == "ubi8"


def test_container_changelog_label_prefixes_other_subprojects():
    lbl = cmd_project._container_changelog_label
    parent = "x:ppg:staging:17"
    assert lbl("x:ppg:staging:17:extras:containers", "ubi9", parent) == "extras/ubi9"
    assert (
        lbl("x:ppg:releases:17:extras:containers:ubi9", "images", "x:ppg:releases:17")
        == "extras/ubi9"
    )


def test_fetch_subproject_container_pkgs_distinct_keys_across_subprojects(monkeypatch):
    monkeypatch.setattr(cmd_project, "_fetch_obs_package_names", lambda a, p: {"img"})
    monkeypatch.setattr(
        cmd_project,
        "_fetch_all_pkg_repo_archs",
        lambda a, p: {"img": [("ubi9", "x86_64")]},
    )
    monkeypatch.setattr(
        cmd_project, "_detect_obs_container_info", lambda a, p, k: {"kind": "docker"}
    )
    monkeypatch.setattr(
        cmd_project,
        "_fetch_build_container_packages",
        lambda a, prj, repo, arch, pkg, root: {"pg": prj},
    )
    parent = "x:ppg:staging:17"
    std = cmd_project._fetch_subproject_container_pkgs(
        "http://obs", f"{parent}:containers", "x", parent
    )
    extras = cmd_project._fetch_subproject_container_pkgs(
        "http://obs", f"{parent}:extras:containers", "x", parent
    )
    assert set(std) == {"img (ubi9)"}
    assert set(extras) == {"img (extras/ubi9)"}
    merged: dict = {}
    cmd_project._merge_container_pkgs(merged, std, f"{parent}:containers")
    cmd_project._merge_container_pkgs(merged, extras, f"{parent}:extras:containers")
    assert len(merged) == 2
    with pytest.raises(SystemExit, match="collide"):
        cmd_project._merge_container_pkgs(merged, std, f"{parent}:containers")


def test_changelog_emits_removed_section(tmp_path):
    src = tmp_path / "staging18"
    src.mkdir()
    section = cmd_project._build_changelog_section(
        "18.6-1",
        {"percona-postgresql": "18.6-1"},
        {"percona-postgresql": "18.4-1", "percona-old-ext": "1.0-1"},
        src,
        source_container_pkgs={"img (ubi9)": {"pg": "18.6-1"}},
        release_container_pkgs={
            "img (ubi9)": {"pg": "18.4-1"},
            "percona-distribution-postgresql-upgrade (ubi9)": {"pg": "18.4-1"},
        },
        prev_release_id="18.4-1",
    )
    assert "### Removed" in section
    assert "- percona-old-ext: removed (was 1.0)" in section
    assert (
        "- percona-distribution-postgresql-upgrade (ubi9) [container image]: "
        "remove image 18.4-1"
    ) in section
    # ordering: Added, Changed, Removed
    assert section.index("### Changed") < section.index("### Removed")


def test_changelog_omits_removed_section_when_nothing_removed(tmp_path):
    src = tmp_path / "staging18"
    src.mkdir()
    section = cmd_project._build_changelog_section(
        "18.6-1",
        {"percona-postgresql": "18.6-1"},
        {"percona-postgresql": "18.4-1"},
        src,
    )
    assert "### Removed" not in section


def test_release_no_longer_touches_macros():
    """The PPG_RELEASE bump is gone: the value is computed from release.yaml.

    A release commit that also rewrote a staging macros.yaml would stop being
    release-only, which is what obs-pr-cleanup keys its tag-and-dispatch on.
    """
    source = Path(cmd_project.__file__).read_text("utf-8")
    assert "PPG_RELEASE" not in source
    assert "release_counter" not in source


def test_write_release_tree_materializes_delta_source(tmp_path, monkeypatch):
    """A staging subproject that only patches its parent's subprojects.yaml still yields a full mirror."""
    import percona_obs.common as common

    root = tmp_path / "root"
    (root / "ppg/staging/17/extras").mkdir(parents=True)
    (root / "macros.yaml").write_text("- X: 1\n")
    (root / "project.yaml").write_text(
        yaml.dump(
            {
                "repositories": [
                    {
                        "name": "UBI_9",
                        "paths": [{"project": "ext:UBI-9", "repository": "standard"}],
                        "archs": ["x86_64"],
                    }
                ]
            }
        )
    )
    (root / "ppg/staging/17/subprojects.yaml").write_text(
        yaml.dump(
            {
                "repositories": [
                    {
                        "name": "UBI_9",
                        "paths": [
                            {"subproject": "ppg:common:deps", "repository": "UBI_9"}
                        ],
                    }
                ],
                "project-config": "Prefer: shared\n",
            }
        )
    )
    (root / "ppg/staging/17/project.yaml").write_text("title: S17\n")
    (root / "ppg/staging/17/extras/project.yaml").write_text(
        yaml.dump(
            {
                "repositories": [
                    {
                        "name": "UBI_9",
                        "paths": [
                            {"subproject": "ppg:staging:17", "repository": "UBI_9"}
                        ],
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    rel = root / "ppg/releases/17"
    _write_release_tree(
        rel,
        {"build": False, "repositories": []},
        root / "ppg/staging/17",
        "ppg:staging:17",
        "ppg:releases:17",
        "ppg",
        "17",
    )
    extras = yaml.safe_load((rel / "extras" / "project.yaml").read_text())
    paths = [
        (p.get("subproject") or p.get("project"), p["repository"])
        for p in extras["repositories"][0]["paths"]
    ]
    assert paths == [
        ("ppg:releases:17", "UBI_9"),
        ("ppg:common:deps", "UBI_9"),
        ("ext:UBI-9", "standard"),
    ]
    assert extras["repositories"][0]["archs"] == ["x86_64"]
    assert "Prefer: shared" in extras["project-config"]


def test_write_release_tree_ignores_the_process_default_filter(tmp_path, monkeypatch):
    """Release mirrors are instance-agnostic: a labs/boo default filter must not slice them."""
    import percona_obs.common as common
    from percona_obs.project_config import RepositoryFilter

    root = tmp_path / "root"
    (root / "ppg/staging/17/extras").mkdir(parents=True)
    (root / "macros.yaml").write_text("- X: 1\n")
    (root / "project.yaml").write_text(
        yaml.dump(
            {
                "repositories": [
                    {"name": "UBI_9", "paths": [], "archs": ["x86_64"]},
                    {"name": "RockyLinux_9", "paths": [], "archs": ["x86_64"]},
                ]
            }
        )
    )
    (root / "ppg/staging/17/project.yaml").write_text("title: S17\n")
    (root / "ppg/staging/17/extras/project.yaml").write_text("title: E\n")
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    common.set_default_repository_filter(RepositoryFilter(exclude_repos=("UBI_*",)))
    try:
        rel = root / "ppg/releases/17"
        _write_release_tree(
            rel,
            {"build": False, "repositories": []},
            root / "ppg/staging/17",
            "ppg:staging:17",
            "ppg:releases:17",
            "ppg",
            "17",
        )
    finally:
        common.set_default_repository_filter(None)
    extras = yaml.safe_load((rel / "extras" / "project.yaml").read_text())
    assert [r["name"] for r in extras["repositories"]] == ["UBI_9", "RockyLinux_9"]


def test_derive_release_id_pg_mode():
    rid = cmd_project._derive_release_id(
        pkg_archs={"percona-postgresql": ("RockyLinux_9", "x86_64")},
        existing_releases=["ppg/17.10-1", "ppg/17.11-1"],
        release_name="17",
        versrel_lookup=lambda repo, arch, pkg: "17.11.1-2.1",
    )
    assert rid == "17.11-2"


def test_derive_release_id_major_suffixed_package():
    rid = cmd_project._derive_release_id(
        pkg_archs={"percona-postgresql18": ("RockyLinux_9", "x86_64")},
        existing_releases=[],
        release_name="18",
        versrel_lookup=lambda repo, arch, pkg: "18.6-1.1",
    )
    assert rid == "18.6-1"


def test_derive_release_id_pg_mode_uses_major_not_release_name():
    seen = []

    def _lookup(repo, arch, pkg):
        seen.append(pkg)
        return "17.11.1-2.1"

    rid = cmd_project._derive_release_id(
        pkg_archs={"percona-postgresql17": ("RockyLinux_9", "x86_64")},
        existing_releases=["ppg/17.11-1"],
        release_name="foo",
        versrel_lookup=_lookup,
        major="17",
    )
    assert rid == "17.11-2"
    assert seen == ["percona-postgresql17"]


def test_derive_release_id_counter_mode_without_server_package():
    def _fail(repo, arch, pkg):
        raise AssertionError("not called")

    rid = cmd_project._derive_release_id(
        pkg_archs={"percona-pgbouncer": ("ubi9", "x86_64")},
        existing_releases=["ppg/common-1", "ppg/common-2"],
        release_name="common",
        versrel_lookup=_fail,
        counter_mode=True,
    )
    assert rid == "common-3"


def test_derive_release_id_counter_mode_first_release():
    rid = cmd_project._derive_release_id(
        pkg_archs={},
        existing_releases=[],
        release_name="containers",
        versrel_lookup=lambda repo, arch, pkg: None,
        counter_mode=True,
    )
    assert rid == "containers-1"


def test_derive_release_id_without_server_package_errors_unless_counter_mode():
    with pytest.raises(SystemExit, match="percona-postgresql"):
        cmd_project._derive_release_id(
            pkg_archs={},
            existing_releases=[],
            release_name="17",
            versrel_lookup=lambda repo, arch, pkg: None,
        )


def test_rewrite_qa_project_refs_recurses_and_keeps_env_tokens():
    from percona_obs.cmd_project import _rewrite_qa_project_refs

    qa = [
        {
            "pipeline": "p",
            "parameters": {
                "OBS_PROJECT": "${OBS_ROOTPRJ}:ppg:staging:17:containers",
                "PLATFORMS": ["ppg:staging:17", "other"],
            },
        }
    ]
    out = _rewrite_qa_project_refs(qa, "ppg:staging:17", "ppg:releases:17")
    assert (
        out[0]["parameters"]["OBS_PROJECT"]
        == "${OBS_ROOTPRJ}:ppg:releases:17:containers"
    )
    assert out[0]["parameters"]["PLATFORMS"] == ["ppg:releases:17", "other"]
    assert qa[0]["parameters"]["PLATFORMS"][0] == "ppg:staging:17"  # input untouched


def test_write_release_tree_carries_rendered_qa_blocks(tmp_path, monkeypatch):
    import percona_obs.common as common

    src = _staging_tree(tmp_path)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", tmp_path / "root")
    (tmp_path / "root/macros.yaml").write_text("- PG_VERSION: 17.11\n")
    (src / "containers" / "project.yaml").write_text(
        (src / "containers" / "project.yaml").read_text()
        + "qa:\n  - pipeline: p\n    parameters:\n"
        "      OBS_PROJECT: ${OBS_ROOTPRJ}:ppg:staging:17:containers\n"
        "      VERSION: ppg-%!{PG_VERSION}\n"
    )
    rel = tmp_path / "root/ppg/releases/17"
    _write_release_tree(
        rel,
        {"build": False, "repositories": []},
        src,
        "ppg:staging:17",
        "ppg:releases:17",
        "ppg",
        "17",
    )
    containers = yaml.safe_load((rel / "containers" / "project.yaml").read_text())
    assert containers["qa"][0]["parameters"] == {
        "OBS_PROJECT": "${OBS_ROOTPRJ}:ppg:releases:17:containers",
        "VERSION": "ppg-17.11",
    }
    tarballs = yaml.safe_load((rel / "tarballs" / "project.yaml").read_text())
    assert "qa" not in tarballs


def _pkg_with_qa(project_dir, name, qa_yaml):
    pkg = project_dir / name
    (pkg / "obs").mkdir(parents=True)
    (pkg / "obs" / "_service").write_text("<services/>\n")
    (pkg / "package.yaml").write_text(qa_yaml)
    return pkg


_AUDIT_QA = "qa:\n  - pipeline: audit\n    parameters:\n      X: 1\n"


def test_mirror_qa_entries_appends_package_lanes(tmp_path, monkeypatch):
    import percona_obs.common as common
    from percona_obs.cmd_project import _mirror_qa_entries

    src = _staging_tree(tmp_path)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", tmp_path / "root")
    (tmp_path / "root/macros.yaml").write_text("- PG_VERSION: 17.11\n")
    _pkg_with_qa(
        src,
        "percona-pg_tde",
        "qa:\n  - name: pg_tde\n    pipeline: tde-core-parallel\n    parameters:\n"
        "      OBS_PROJECT: ${OBS_ROOTPRJ}:ppg:staging:17\n      VERSION: ppg-%!{PG_VERSION}\n",
    )
    _pkg_with_qa(src, "percona-pgaudit", _AUDIT_QA)
    _pkg_with_qa(src, "percona-haproxy", "build:\n  RockyLinux_9: true\n")
    cfg = {
        "qa": [
            {"name": "server", "pipeline": "p", "parameters": {"A": "ppg:staging:17"}}
        ]
    }
    out = _mirror_qa_entries(
        cfg, src, "ppg:staging:17", "ppg:staging:17", "ppg:releases:17"
    )
    assert [e["name"] for e in out] == [
        "server",
        "percona-pg_tde.pg_tde",
        "percona-pgaudit.audit",
    ]
    assert out[0]["parameters"]["A"] == "ppg:releases:17"
    assert out[1]["parameters"] == {
        "OBS_PROJECT": "${OBS_ROOTPRJ}:ppg:releases:17",
        "VERSION": "ppg-17.11",
    }
    assert out[1]["pipeline"] == "tde-core-parallel"


def test_mirror_qa_entries_none_when_nothing_and_package_only(tmp_path, monkeypatch):
    import percona_obs.common as common
    from percona_obs.cmd_project import _mirror_qa_entries

    src = _staging_tree(tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", tmp_path / "root")
    ids = ("ppg:staging:17", "ppg:staging:17", "ppg:releases:17")
    assert _mirror_qa_entries({}, src, *ids) is None
    _pkg_with_qa(src, "percona-pgaudit", _AUDIT_QA)
    out = _mirror_qa_entries({}, src, *ids)
    assert [e["name"] for e in out] == ["percona-pgaudit.audit"]


def test_mirror_qa_entries_rejects_duplicate_names(tmp_path, monkeypatch):
    import percona_obs.common as common
    from percona_obs.cmd_project import _mirror_qa_entries

    src = _staging_tree(tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", tmp_path / "root")
    _pkg_with_qa(src, "percona-pgaudit", _AUDIT_QA)
    cfg = {
        "qa": [
            {"name": "percona-pgaudit.audit", "pipeline": "p", "parameters": {"A": 1}}
        ]
    }
    with pytest.raises(SystemExit, match="percona-pgaudit.audit"):
        _mirror_qa_entries(
            cfg, src, "ppg:staging:17", "ppg:staging:17", "ppg:releases:17"
        )


def test_mirror_qa_entries_follows_shared_symlinks(tmp_path, monkeypatch):
    import percona_obs.common as common
    from percona_obs.cmd_project import _mirror_qa_entries

    src = _staging_tree(tmp_path)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", tmp_path / "root")
    shared = tmp_path / "root/ppg/staging/_shared"
    shared.mkdir(parents=True)
    _pkg_with_qa(shared, "percona-pgaudit", _AUDIT_QA)
    (src / "percona-pgaudit").symlink_to("../_shared/percona-pgaudit")
    out = _mirror_qa_entries(
        {}, src, "ppg:staging:17", "ppg:staging:17", "ppg:releases:17"
    )
    assert [e["name"] for e in out] == ["percona-pgaudit.audit"]


def test_write_release_tree_carries_package_lanes_into_subproject_mirror(
    tmp_path, monkeypatch
):
    import percona_obs.common as common

    src = _staging_tree(tmp_path)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", tmp_path / "root")
    (tmp_path / "root/macros.yaml").write_text("- PG_VERSION: 17.11\n")
    _pkg_with_qa(
        src / "containers",
        "percona-postgresql-image",
        "qa:\n  - name: img\n    pipeline: img-p\n    parameters:\n"
        "      OBS_PROJECT: ${OBS_ROOTPRJ}:ppg:staging:17:containers\n",
    )
    rel = tmp_path / "root/ppg/releases/17"
    _write_release_tree(
        rel,
        {"build": False, "repositories": []},
        src,
        "ppg:staging:17",
        "ppg:releases:17",
        "ppg",
        "17",
    )
    containers = yaml.safe_load((rel / "containers" / "project.yaml").read_text())
    assert containers["qa"] == [
        {
            "name": "percona-postgresql-image.img",
            "pipeline": "img-p",
            "parameters": {"OBS_PROJECT": "${OBS_ROOTPRJ}:ppg:releases:17:containers"},
        }
    ]


def test_replace_changelog_section():
    from percona_obs.cmd_project import _replace_changelog_section

    text = "# Changelog\n\n## [18.6-1] - 2026-01-01\n\n### Added\n- a\n\n## [18.4-1] - 2025-12-01\n\n### Added\n- b\n"
    out = _replace_changelog_section(
        text, "18.6-1", "## [18.6-1] - 2026-02-02\n\n### Added\n- c\n"
    )
    assert "- a" not in out and "- c" in out and "- b" in out
    assert out.index("[18.6-1]") < out.index("[18.4-1]")
    # absent -> prepended above the first section
    out2 = _replace_changelog_section(text, "18.7-1", "## [18.7-1] - x\n")
    assert out2.index("[18.7-1]") < out2.index("[18.6-1]")


def test_resolve_source_commit_override_and_ancestor(monkeypatch):
    from percona_obs import cmd_project as cp

    monkeypatch.setattr(cp, "_is_ancestor_of_head", lambda sha: sha == "good")
    assert cp._resolve_source_commit("good", "https://github.com/o/r.git") == "good"
    with pytest.raises(SystemExit, match="not an ancestor of HEAD"):
        cp._resolve_source_commit("bad", "https://github.com/o/r.git")
    monkeypatch.setattr(cp, "last_synced_head_sha", lambda slug: "good")
    assert cp._resolve_source_commit(None, "https://github.com/o/r.git") == "good"
    with pytest.raises(SystemExit, match="PERCONA_OBS_PACKAGING_REPO"):
        cp._resolve_source_commit(None, "")


def test_open_release_is_refreshed_in_place(monkeypatch):
    from percona_obs import cmd_project as cp
    from percona_obs.release_record import ReleaseEntry

    entries = [ReleaseEntry("ppg/18.4-1"), ReleaseEntry("ppg/18.6-1", "old")]
    rid, new_entries, prev = cp._plan_release_entries(
        entries, None, lambda: "18.6-2", "ppg", "newsha", lambda t: False
    )
    assert rid == "18.6-1"
    assert new_entries == [
        ReleaseEntry("ppg/18.4-1"),
        ReleaseEntry("ppg/18.6-1", "newsha"),
    ]
    assert prev == "18.4-1"


def test_shipped_release_appends_next_id(monkeypatch):
    from percona_obs import cmd_project as cp
    from percona_obs.release_record import ReleaseEntry

    entries = [ReleaseEntry("ppg/18.6-1", "old")]
    rid, new_entries, prev = cp._plan_release_entries(
        entries, None, lambda: "18.6-2", "ppg", "newsha", lambda t: True
    )
    assert rid == "18.6-2"
    assert new_entries == [
        ReleaseEntry("ppg/18.6-1", "old"),
        ReleaseEntry("ppg/18.6-2", "newsha"),
    ]
    assert prev == "18.6-1"


def test_explicit_release_id_wins_over_refresh(monkeypatch):
    from percona_obs import cmd_project as cp
    from percona_obs.release_record import ReleaseEntry

    entries = [ReleaseEntry("ppg/18.6-1")]
    with pytest.raises(SystemExit, match="already present"):
        cp._plan_release_entries(
            entries, "18.6-1", lambda: "x", "ppg", "s", lambda t: False
        )
    rid, new_entries, _ = cp._plan_release_entries(
        entries, "18.6-9", lambda: "x", "ppg", "s", lambda t: False
    )
    assert rid == "18.6-9" and new_entries[-1] == ReleaseEntry("ppg/18.6-9", "s")


def test_tag_exists_on_remote(monkeypatch):
    from types import SimpleNamespace

    from percona_obs import cmd_project as cp

    monkeypatch.setattr(
        cp.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="abc\trefs/tags/t\n"),
    )
    assert cp._tag_exists_on_remote("u", "t") is True
    monkeypatch.setattr(
        cp.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=""),
    )
    assert cp._tag_exists_on_remote("u", "t") is False
    monkeypatch.setattr(
        cp.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )
    assert cp._tag_exists_on_remote("u", "t") is False
