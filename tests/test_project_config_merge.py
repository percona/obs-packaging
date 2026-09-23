"""Unit tests for percona_obs.project_config (merge-based project.yaml inheritance)."""

import os
from pathlib import Path

import pytest

import percona_obs.common as common
from percona_obs.project_config import resolve_project_config

_ROOT_REPOS = """\
repositories:
  - name: RockyLinux_9
    paths:
      - subproject: common:deps:build
        repository: RockyLinux_9
      - project: ${REMOTE}RockyLinux:9
        repository: standard
    archs: [x86_64, aarch64]
  - name: Debian_12
    paths:
      - project: ${REMOTE}Debian:12
        repository: standard
    archs: [x86_64]
"""

_ROOT_PRJCONF = """\
project-config: |
  %if "%_repository" == "Debian_12"
  Release: <CI_CNT>.<B_CNT>.bookworm
  %endif
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Build root/ from {relpath: text}; a root macros.yaml is always present."""

    def make(files: dict, macros: str = "- ROOT_MACRO: r\n") -> Path:
        root = tmp_path / "root"
        root.mkdir(exist_ok=True)
        (root / "macros.yaml").write_text(macros)
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        monkeypatch.setattr(common, "REPO_ROOT", root)
        return root

    return make


def _names(cfg):
    return [r["name"] for r in cfg["repositories"]]


def _paths(cfg, name):
    repo = next(r for r in cfg["repositories"] if r["name"] == name)
    return [(p.get("subproject") or p.get("project"), p["repository"]) for p in repo["paths"]]


def _directives(cfg):
    return [l for l in cfg["project-config"].splitlines() if l and not l.startswith("#")]


# --- plain inheritance -----------------------------------------------------


def test_child_without_fields_inherits_root_repos_and_prjconf(repo):
    root = repo({"project.yaml": _ROOT_REPOS + _ROOT_PRJCONF, "a/project.yaml": "title: A\n"})
    cfg = resolve_project_config(root / "a")
    assert cfg["title"] == "A"
    assert _names(cfg) == ["RockyLinux_9", "Debian_12"]
    assert _paths(cfg, "RockyLinux_9") == [
        ("common:deps:build", "RockyLinux_9"),
        ("${REMOTE}RockyLinux:9", "standard"),
    ]
    assert cfg["project-config"].startswith("# --- from root/project.yaml ---\n%if")
    assert _directives(cfg) == ['%if "%_repository" == "Debian_12"', "Release: <CI_CNT>.<B_CNT>.bookworm", "%endif"]


def test_missing_project_yaml_resolves_from_ancestors(repo):
    root = repo({"project.yaml": _ROOT_REPOS, "a/obs/_service": ""})
    cfg = resolve_project_config(root / "a")
    assert _names(cfg) == ["RockyLinux_9", "Debian_12"]
    assert "title" not in cfg


# --- project-config --------------------------------------------------------


def test_prjconf_concatenates_with_provenance_headers(repo):
    root = repo(
        {
            "project.yaml": _ROOT_PRJCONF,
            "a/project.yaml": "project-config: |\n\n  Prefer: foo\n\n",
        }
    )
    cfg = resolve_project_config(root / "a")
    assert cfg["project-config"] == (
        "# --- from root/project.yaml ---\n"
        '%if "%_repository" == "Debian_12"\n'
        "Release: <CI_CNT>.<B_CNT>.bookworm\n"
        "%endif\n"
        "\n"
        "# --- from root/a/project.yaml ---\n"
        "Prefer: foo\n"
    )


def test_project_config_inherit_false_discards_ancestors(repo):
    root = repo(
        {
            "project.yaml": _ROOT_PRJCONF,
            "a/project.yaml": "project-config-inherit: false\nproject-config: |\n  Prefer: only\n",
            "a/b/project.yaml": "project-config: |\n  Prefer: child\n",
        }
    )
    assert _directives(resolve_project_config(root / "a")) == ["Prefer: only"]
    # descendants inherit from a onwards, not from root
    assert _directives(resolve_project_config(root / "a" / "b")) == ["Prefer: only", "Prefer: child"]


def test_empty_prjconf_everywhere_leaves_key_absent(repo):
    root = repo({"project.yaml": _ROOT_REPOS, "a/project.yaml": "title: A\n"})
    assert "project-config" not in resolve_project_config(root / "a")


# --- repositories ----------------------------------------------------------


def test_new_repository_with_archs_is_appended(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "repositories:\n  - name: images\n    paths:\n"
                "      - subproject: common:containers:ubi9\n        repository: images\n"
                "    archs: [x86_64]\n"
            ),
        }
    )
    cfg = resolve_project_config(root / "a")
    assert _names(cfg) == ["RockyLinux_9", "Debian_12", "images"]
    assert _paths(cfg, "images") == [("common:containers:ubi9", "images")]


def test_patch_for_unknown_repository_is_an_error(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "repositories:\n  - name: Debian_21\n    paths:\n"
                "      - subproject: x\n        repository: Debian_21\n"
            ),
        }
    )
    with pytest.raises(SystemExit, match=r"root/a/project.yaml: repository 'Debian_21' is not inherited"):
        resolve_project_config(root / "a")


def test_known_repository_paths_are_prepended_and_archs_replaced(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "repositories:\n  - name: RockyLinux_9\n    paths:\n"
                "      - subproject: ppg:common:deps\n        repository: RockyLinux_9\n"
                "  - name: Debian_12\n    archs: [x86_64, aarch64]\n"
                "    paths:\n      - subproject: ppg:common:deps\n        repository: Debian_12\n"
            ),
        }
    )
    cfg = resolve_project_config(root / "a")
    assert _paths(cfg, "RockyLinux_9") == [
        ("ppg:common:deps", "RockyLinux_9"),
        ("common:deps:build", "RockyLinux_9"),
        ("${REMOTE}RockyLinux:9", "standard"),
    ]
    rocky = next(r for r in cfg["repositories"] if r["name"] == "RockyLinux_9")
    assert rocky["archs"] == ["x86_64", "aarch64"]  # inherited
    deb = next(r for r in cfg["repositories"] if r["name"] == "Debian_12")
    assert deb["archs"] == ["x86_64", "aarch64"]  # replaced


def test_paths_replace(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "repositories:\n  - name: RockyLinux_9\n    paths-replace: true\n    paths:\n"
                "      - subproject: only\n        repository: RockyLinux_9\n"
            ),
        }
    )
    assert _paths(resolve_project_config(root / "a"), "RockyLinux_9") == [("only", "RockyLinux_9")]


def test_remove_repository(repo):
    root = repo(
        {"project.yaml": _ROOT_REPOS, "a/project.yaml": "repositories:\n  - name: Debian_12\n    remove: true\n"}
    )
    assert _names(resolve_project_config(root / "a")) == ["RockyLinux_9"]


def test_remove_unknown_repository_is_an_error(repo):
    root = repo(
        {"project.yaml": _ROOT_REPOS, "a/project.yaml": "repositories:\n  - name: Debian_21\n    remove: true\n"}
    )
    with pytest.raises(SystemExit, match=r"cannot remove unknown repository 'Debian_21'"):
        resolve_project_config(root / "a")


def test_remove_with_extra_keys_is_an_error(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": "repositories:\n  - name: Debian_12\n    remove: true\n    archs: [x86_64]\n",
        }
    )
    with pytest.raises(SystemExit, match=r"remove: true entry may only carry 'name'"):
        resolve_project_config(root / "a")


def test_unknown_repository_entry_key_is_an_error(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": "repositories:\n  - name: Debian_12\n    path: []\n",
        }
    )
    with pytest.raises(SystemExit, match=r"unknown key\(s\) \['path'\]"):
        resolve_project_config(root / "a")


def test_repositories_inherit_false(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "repositories-inherit: false\nrepositories:\n  - name: ssl3\n    paths:\n"
                "      - subproject: a\n        repository: RockyLinux_9\n    archs: [x86_64]\n"
            ),
        }
    )
    cfg = resolve_project_config(root / "a")
    assert _names(cfg) == ["ssl3"]
    assert "repositories-inherit" not in cfg


# --- path-prefix -----------------------------------------------------------


def test_path_prefix_applies_to_every_repo_with_token_substitution(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "path-prefix:\n  - subproject: ppg:staging:17\n    repository: \"%_repository\"\n"
            ),
        }
    )
    cfg = resolve_project_config(root / "a")
    assert _paths(cfg, "RockyLinux_9")[0] == ("ppg:staging:17", "RockyLinux_9")
    assert _paths(cfg, "Debian_12")[0] == ("ppg:staging:17", "Debian_12")
    assert "path-prefix" not in cfg


def test_path_prefix_layers_concatenate_child_first(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/subprojects.yaml": "path-prefix:\n  - subproject: tier\n    repository: \"%_repository\"\n",
            "a/b/project.yaml": "path-prefix:\n  - subproject: leaf\n    repository: \"%_repository\"\n",
        }
    )
    assert _paths(resolve_project_config(root / "a" / "b"), "Debian_12")[:3] == [
        ("leaf", "Debian_12"),
        ("tier", "Debian_12"),
        ("${REMOTE}Debian:12", "standard"),
    ]


def test_path_prefix_entry_validation(repo):
    root = repo({"project.yaml": _ROOT_REPOS, "a/project.yaml": "path-prefix:\n  - repository: x\n"})
    with pytest.raises(SystemExit, match=r"path-prefix entry"):
        resolve_project_config(root / "a")


# --- subprojects.yaml ------------------------------------------------------


def test_subprojects_yaml_applies_to_descendants_only(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "tier/project.yaml": "title: Tier\n",
            "tier/subprojects.yaml": (
                "debuginfo:\n  RockyLinux_9: true\n"
                "repositories:\n  - name: RockyLinux_9\n    paths:\n"
                "      - subproject: ppg:common:deps\n        repository: RockyLinux_9\n"
                "project-config: |\n  Prefer: tier-only\n"
            ),
            "tier/17/project.yaml": "title: Seventeen\n",
        }
    )
    tier = resolve_project_config(root / "tier")
    assert "debuginfo" not in tier
    assert _paths(tier, "RockyLinux_9")[0] == ("common:deps:build", "RockyLinux_9")
    assert "project-config" not in tier
    leaf = resolve_project_config(root / "tier" / "17")
    assert leaf["debuginfo"] == {"RockyLinux_9": True}
    assert _paths(leaf, "RockyLinux_9")[0] == ("ppg:common:deps", "RockyLinux_9")
    assert _directives(leaf) == ["Prefer: tier-only"]
    assert "# --- from root/tier/subprojects.yaml ---" in leaf["project-config"]


def test_subprojects_yaml_may_use_leaf_macros(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "tier/project.yaml": "title: Tier\n",
            "tier/subprojects.yaml": "project-config: |\n  Prefer: percona-postgresql%!{PG_MAJOR_VERSION}-server\n",
            "tier/17/project.yaml": "title: S\n",
            "tier/17/macros.yaml": "- PG_MAJOR_VERSION: 17\n",
            "tier/other/project.yaml": "project-config-inherit: false\nproject-config: |\n  Prefer: x\n",
        }
    )
    assert _directives(resolve_project_config(root / "tier" / "17")) == ["Prefer: percona-postgresql17-server"]
    # the tier itself and an opted-out descendant never see the undefined macro
    assert "project-config" not in resolve_project_config(root / "tier")
    assert _directives(resolve_project_config(root / "tier" / "other")) == ["Prefer: x"]


def test_leftover_macro_in_resolved_config_is_an_error(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "tier/subprojects.yaml": "project-config: |\n  Prefer: percona-postgresql%!{PG_MAJOR_VERSION}-server\n",
            "tier/x/project.yaml": "title: X\n",
        }
    )
    with pytest.raises(SystemExit, match=r"root/tier/x/project.yaml: undefined macro %!\{PG_MAJOR_VERSION\}"):
        resolve_project_config(root / "tier" / "x")


def test_subprojects_yaml_rejects_unknown_keys(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "tier/subprojects.yaml": "title: nope\n",
            "tier/x/project.yaml": "title: X\n",
        }
    )
    with pytest.raises(SystemExit, match=r"root/tier/subprojects.yaml: unknown key\(s\) \['title'\]"):
        resolve_project_config(root / "tier" / "x")


def test_symlinked_subprojects_yaml(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "staging/subprojects.yaml": "project-config: |\n  Prefer: shared\n",
            "devel/17/project.yaml": "title: D\n",
        }
    )
    os.symlink("../staging/subprojects.yaml", root / "devel" / "subprojects.yaml")
    cfg = resolve_project_config(root / "devel" / "17")
    assert _directives(cfg) == ["Prefer: shared"]
    assert "# --- from root/devel/subprojects.yaml ---" in cfg["project-config"]


def test_standalone_drops_every_ancestor_layer(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS + _ROOT_PRJCONF,
            "releases/project.yaml": "title: R\n",
            "releases/subprojects.yaml": "standalone: true\n",
            "releases/17/project.yaml": (
                "repositories:\n  - name: RockyLinux_9\n    paths:\n"
                "      - subproject: frozen\n        repository: RockyLinux_9\n    archs: [x86_64]\n"
                "project-config: |\n  Prefer: frozen\n"
            ),
            "releases/17/tarballs/project.yaml": (
                "repositories:\n  - name: RockyLinux_9\n    paths:\n"
                "      - subproject: frozen-tarballs\n        repository: RockyLinux_9\n    archs: [x86_64]\n"
            ),
        }
    )
    # the tier itself still inherits from root
    assert _names(resolve_project_config(root / "releases")) == ["RockyLinux_9", "Debian_12"]
    r17 = resolve_project_config(root / "releases" / "17")
    assert _paths(r17, "RockyLinux_9") == [("frozen", "RockyLinux_9")]
    assert _directives(r17) == ["Prefer: frozen"]
    tb = resolve_project_config(root / "releases" / "17" / "tarballs")
    assert _paths(tb, "RockyLinux_9") == [("frozen-tarballs", "RockyLinux_9")]
    assert "project-config" not in tb


def test_standalone_must_be_alone(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "r/subprojects.yaml": "standalone: true\nproject-config: |\n  Prefer: x\n",
            "r/17/project.yaml": "title: X\n",
        }
    )
    with pytest.raises(SystemExit, match=r"standalone: true must be the only key"):
        resolve_project_config(root / "r" / "17")


# --- flags and leaf-only keys ------------------------------------------------


def test_flags_child_wins_and_null_resets(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS + "publish: false\n",
            "a/subprojects.yaml": "debuginfo:\n  RockyLinux_9: true\n  Debian_12: true\n",
            "a/b/project.yaml": "debuginfo:\n  RockyLinux_9: true\n",
            "a/c/project.yaml": "debuginfo: ~\npublish:\n  RockyLinux_9: true\n",
            "a/d/project.yaml": "title: D\n",
        }
    )
    assert resolve_project_config(root / "a" / "b")["debuginfo"] == {"RockyLinux_9": True}
    assert resolve_project_config(root / "a" / "b")["publish"] is False
    c = resolve_project_config(root / "a" / "c")
    assert "debuginfo" not in c
    assert c["publish"] == {"RockyLinux_9": True}
    d = resolve_project_config(root / "a" / "d")
    assert d["debuginfo"] == {"RockyLinux_9": True, "Debian_12": True}


def test_title_description_name_qa_are_leaf_only(repo):
    root = repo(
        {
            "project.yaml": "title: Root\ndescription: R\nname: custom:root\nqa:\n  pipeline: p\n",
            "a/project.yaml": "publish: false\n",
        }
    )
    cfg = resolve_project_config(root / "a")
    for key in ("title", "description", "name", "qa"):
        assert key not in cfg
    assert cfg["publish"] is False


def test_alias_in_common_delegates(repo):
    root = repo({"project.yaml": _ROOT_REPOS, "a/project.yaml": "title: A\n"})
    assert common._load_project_config_with_inheritance(root / "a") == resolve_project_config(root / "a")


def test_env_vars_are_substituted(repo):
    root = repo({"project.yaml": _ROOT_REPOS, "a/project.yaml": "title: A\n"})
    cfg = resolve_project_config(root / "a", {"REMOTE": "openSUSE.org:"})
    assert _paths(cfg, "Debian_12") == [("openSUSE.org:Debian:12", "standard")]


# --- validators (cmd_project) ----------------------------------------------


def test_validate_subproject_refs_sees_inherited_paths(repo):
    from percona_obs.cmd_project import _validate_subproject_refs

    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "tier/project.yaml": "title: T\n",
            "tier/subprojects.yaml": (
                "repositories:\n  - name: RockyLinux_9\n    paths:\n"
                "      - subproject: does:not:exist\n        repository: RockyLinux_9\n"
            ),
            "tier/17/project.yaml": "title: S\n",
            "common/deps/build/project.yaml": "title: B\n",
        }
    )
    errors = _validate_subproject_refs(root)
    assert [(str(p.relative_to(root)), m.split(" (")[0]) for p, m in errors] == [
        ("tier/17/project.yaml", "subproject 'does:not:exist' not found"),
    ]


def test_validate_subproject_refs_surfaces_merge_errors(repo):
    from percona_obs.cmd_project import _validate_subproject_refs

    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": "repositories:\n  - name: Debian_21\n    remove: true\n",
        }
    )
    with pytest.raises(SystemExit, match="cannot remove unknown repository"):
        _validate_subproject_refs(root)


def test_render_resolved_yaml(repo):
    from percona_obs.cmd_project import _render_resolved_yaml

    root = repo({"project.yaml": _ROOT_REPOS, "a/project.yaml": "title: A\n"})
    out = _render_resolved_yaml("ROOT:a", resolve_project_config(root / "a"))
    assert out.startswith("# project ROOT:a\n")
    assert "repositories:" in out and "name: RockyLinux_9" in out
    assert out.endswith("\n")
