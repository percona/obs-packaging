"""Unit tests for `sync prerelease` (percona_obs.cmd_sync.cmd_sync_prerelease).

OBS, osc, git and gh are all monkeypatched; the staging/release trees come
from tests.test_sync_release._mk_tree.
"""

import pytest

import percona_obs.cmd_sync as cmd_sync
import percona_obs.release_copy as rc
from tests.test_sync_release import _REPO_YAML, _mk_tree

SHA = "a" * 40


class _Args:
    def __init__(self, **kw):
        self.project = "ppg:releases:17"
        self.rootprj = "home:Admin:PR:pr-5"
        self.branch_from = "main"
        self.synced_commit = SHA
        self.source_commit = None
        self.force = False
        self.dry_run = False
        self.no_freeze = False
        self.freeze_timeout = 1
        self.verify_timeout = 0
        self.env_overrides = None
        self.profile = None
        self.__dict__.update(kw)


def _tree_with_record(tmp_path, monkeypatch, source_commit=SHA):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ssl3")
    )
    entry = (
        f"  - tag: ppg/17.11-1\n    source_commit: {source_commit}\n"
        if source_commit
        else "  - ppg/17.11-1\n"
    )
    (rel / "release.yaml").write_text(f"project: ppg:staging:17\nreleases:\n{entry}")
    return src, rel


def _wire(monkeypatch, src, rel, calls):
    monkeypatch.setattr(
        cmd_sync,
        "resolve_project_path",
        lambda pid: src if pid == "ppg:staging:17" else rel,
    )
    monkeypatch.setattr(
        rc, "resolve_project_path", lambda pid: src if pid == "ppg:staging:17" else rel
    )
    monkeypatch.setattr(cmd_sync, "_REPO_DIR", rel.parents[2])
    monkeypatch.setattr(cmd_sync.osc.conf, "config", {"apiurl": "http://obs"})
    monkeypatch.setattr(
        cmd_sync,
        "_load_profile",
        lambda name: {"rootprj": "home:Admin", "apiurl": "http://obs"},
    )
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda *a, **k: True)
    monkeypatch.setattr(cmd_sync, "_fetch_obs_subproject_names", lambda *a: set())
    monkeypatch.setattr(
        cmd_sync,
        "_delete_obs_project",
        lambda apiurl, prj, dry_run, recursive=False: calls.append(
            ("delete", prj, recursive)
        ),
    )
    monkeypatch.setattr(cmd_sync, "_changed_files_between", lambda *a, **k: [])
    monkeypatch.setattr(
        cmd_sync,
        "apply_mirror_meta",
        lambda apiurl, prj, path, rootprj, env, publish_override=None, **k: calls.append(
            ("meta", prj, publish_override)
        ),
    )
    monkeypatch.setattr(
        cmd_sync, "wait_for_quiesce", lambda *a, **k: calls.append("drain")
    )
    monkeypatch.setattr(
        cmd_sync, "assert_all_green", lambda *a, **k: calls.append("green") or []
    )
    monkeypatch.setattr(
        cmd_sync,
        "freeze_builds",
        lambda *a, **k: calls.append("freeze") or {"p": "<x/>"},
    )
    monkeypatch.setattr(cmd_sync, "freeze_packages", lambda *a, **k: {})
    monkeypatch.setattr(cmd_sync, "restore_packages", lambda *a, **k: None)
    monkeypatch.setattr(
        cmd_sync, "restore_builds", lambda *a, **k: calls.append("restore")
    )
    monkeypatch.setattr(
        cmd_sync,
        "release_tree",
        lambda *a, **k: calls.append(
            ("copy", a[1], a[2], k.get("publish_override"), k.get("release_id"))
        ),
    )
    monkeypatch.setattr(
        cmd_sync,
        "set_project_description_markers",
        lambda apiurl, prj, markers: calls.append(("marker", prj, markers)),
    )


def test_requires_source_commit(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch, source_commit=None)
    _wire(monkeypatch, src, rel, [])
    with pytest.raises(SystemExit, match="has no source_commit"):
        cmd_sync.cmd_sync_prerelease(_Args())


def test_record_mismatch_aborts_before_drain(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    monkeypatch.setattr(
        cmd_sync,
        "_changed_files_between",
        lambda *a, **k: ["root/ppg/staging/17/x/rpm/x.spec"],
    )
    with pytest.raises(SystemExit, match="staging changed since the cut"):
        cmd_sync.cmd_sync_prerelease(_Args())
    assert "drain" not in calls
    assert not any(c[0] == "delete" for c in calls if isinstance(c, tuple))


def test_rootprj_equal_to_branch_root_refused(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    with pytest.raises(SystemExit, match="is the --branch-from root"):
        cmd_sync.cmd_sync_prerelease(_Args(rootprj="home:Admin"))
    assert calls == []


def test_existing_prerelease_tree_deleted_deepest_first(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    top = "home:Admin:PR:pr-5:ppg:releases:17"
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_subproject_names",
        lambda apiurl, prj: {f"{prj}:tarballs", f"{prj}:containers:extras"},
    )
    cmd_sync.cmd_sync_prerelease(_Args())
    deletes = [c for c in calls if isinstance(c, tuple) and c[0] == "delete"]
    assert deletes == [
        ("delete", f"{top}:containers:extras", True),
        ("delete", f"{top}:tarballs", True),
        ("delete", top, True),
    ]
    assert calls.index(deletes[-1]) < calls.index(("meta", top, True))


def test_repopulate_keeps_nested_unit_prerelease(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    top = "home:Admin:PR:pr-5:ppg:releases:17"
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_subproject_names",
        lambda apiurl, prj: {
            f"{prj}:containers",
            f"{prj}:containers:ubi9",
            f"{prj}:extras",
            f"{prj}:extras:containers",
        },
    )
    cmd_sync.cmd_sync_prerelease(_Args())
    deletes = [c[1] for c in calls if isinstance(c, tuple) and c[0] == "delete"]
    assert deletes == [f"{top}:containers:ubi9", f"{top}:containers", top]


def test_prerelease_unit_tree_filters_by_first_component():
    names = ["P:containers", "P:tarballs:x", "P:extras", "P:extras:containers", "Q:c"]
    assert cmd_sync._prerelease_unit_tree("P", names) == [
        "P:containers",
        "P:tarballs:x",
    ]


def test_happy_path_order(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    cmd_sync.cmd_sync_prerelease(_Args())
    assert calls.pop(0) == ("delete", "home:Admin:PR:pr-5:ppg:releases:17", True)
    assert calls[0] == ("meta", "home:Admin:PR:pr-5:ppg:releases:17", True)
    assert calls[1:4] == ["drain", "green", "freeze"]
    assert calls[4] == (
        "copy",
        "home:Admin:ppg:staging:17",
        "home:Admin:PR:pr-5:ppg:releases:17",
        True,
        "17.11-1",
    )
    assert calls[5] == "restore"
    # source_commit marks the completed populate; release_id stays the last line.
    final = [("source_commit", SHA), ("release_id", "17.11-1")]
    assert calls[6] == ("marker", "home:Admin:PR:pr-5:ppg:releases:17", final)
    assert ("marker", "home:Admin:PR:pr-5:ppg:releases:17:tarballs", final) in calls


def test_marker_not_written_when_copy_fails(tmp_path, monkeypatch):
    """The top-level mirror meta (which rewrites the description and drops any
    previous source_commit marker) is applied before anything is frozen or
    copied.  A failed repopulate therefore leaves no valid marker: the meta
    apply already removed the old one and the new one is only written after a
    successful copy."""
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)

    def boom(*a, **k):
        raise RuntimeError("osc")

    monkeypatch.setattr(cmd_sync, "release_tree", boom)
    with pytest.raises(RuntimeError):
        cmd_sync.cmd_sync_prerelease(_Args())
    assert "restore" in calls and not any(
        c[0] == "marker" for c in calls if isinstance(c, tuple)
    )
    top_meta = ("meta", "home:Admin:PR:pr-5:ppg:releases:17", True)
    assert top_meta in calls and "drain" in calls
    assert calls.index(top_meta) < calls.index("drain")


def test_dry_run_checks_only(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    (rel / "CHANGELOG.md").write_text("# Changelog\n\n## [17.11-1] - 2026-01-01\n")
    calls = []
    _wire(monkeypatch, src, rel, calls)
    monkeypatch.setattr(
        cmd_sync.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
    )
    cmd_sync.cmd_sync_prerelease(_Args(dry_run=True))
    assert calls == ["green"]


def test_scope_local_paths_maps_obs_names_back(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    monkeypatch.setattr(
        cmd_sync,
        "resolve_project_path",
        lambda pid: src.parents[2] / pid.replace(":", "/"),
    )
    paths = cmd_sync._scope_local_paths(
        src,
        ["home:Admin:ppg:staging:17", "home:Admin:ppg:staging:17:containers"],
        {"home:Admin:ppg:common:deps": {"geos"}},
        "home:Admin",
    )
    assert src in paths
    assert src.parents[2] / "ppg/common/deps/geos" in paths
    assert any(p.name == "macros.yaml" for p in paths)
    assert src.parent / "project.yaml" in paths
    assert src.parents[1] / "project.yaml" in paths


def test_scope_local_paths_includes_release_record(tmp_path, monkeypatch):
    """PPG_RELEASE is computed from <product>/releases/<major>/release.yaml,
    so the record is part of what decides the staging container images."""
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    assert src == tmp_path / "root/ppg/staging/17"
    paths = cmd_sync._scope_local_paths(src, [], {}, "home:Admin")
    assert tmp_path / "root/ppg/releases/17/release.yaml" in paths


def test_shared_symlink_target_edit_is_detected(tmp_path, monkeypatch):
    import subprocess

    import percona_obs.common as common

    def git(*a):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@x", *a],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "-q")
    shared = tmp_path / "root/ppg/staging/_shared/pkgx/rpm"
    shared.mkdir(parents=True)
    spec = shared / "x.spec"
    spec.write_text("Version: 1\n")
    src = tmp_path / "root/ppg/staging/17"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: S\n")
    (src / "pkgx").symlink_to("../_shared/pkgx")
    (tmp_path / "root/macros.yaml").write_text("- M: 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "a")
    a = git("rev-parse", "HEAD")
    spec.write_text("Version: 2\n")
    git("commit", "-q", "-am", "b")
    b = git("rev-parse", "HEAD")

    monkeypatch.setattr(cmd_sync, "_REPO_DIR", tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", tmp_path / "root")
    monkeypatch.setattr(
        cmd_sync,
        "resolve_project_path",
        lambda pid: tmp_path / "root" / pid.replace(":", "/"),
    )
    paths = cmd_sync._scope_local_paths(
        src, ["home:Admin:ppg:staging:17"], {}, "home:Admin"
    )
    assert cmd_sync._changed_files_between(a, b, paths) == [
        "root/ppg/staging/_shared/pkgx/rpm/x.spec"
    ]


def test_scope_local_paths_nested_unit_watches_both_records(tmp_path, monkeypatch):
    import percona_obs.common as common

    root = tmp_path / "root"
    src = root / "ppg/staging/18/extras"
    src.mkdir(parents=True)
    (src / "project.yaml").write_text("title: e\n")
    monkeypatch.setattr(common, "REPO_ROOT", root)
    paths = cmd_sync._scope_local_paths(src, [], {}, "R")
    assert root / "ppg/releases/18/extras/release.yaml" in paths
    assert root / "ppg/releases/18/release.yaml" in paths


def _nested_units_repo(tmp_path, monkeypatch):
    """Git repo with staging/18 (+containers, a package) and a nested
    staging/18/extras unit; returns (git, commit)."""
    import subprocess

    import percona_obs.common as common

    def git(*a):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@x", *a],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    s18 = tmp_path / "root/ppg/staging/18"
    for d in ("", "containers", "pkg", "extras", "extras/containers"):
        (s18 / d).mkdir(parents=True, exist_ok=True)
    for d in ("", "containers", "extras", "extras/containers"):
        (s18 / d / "project.yaml").write_text("title: t\n")
    for d in ("containers", "pkg", "extras"):
        (s18 / d / "x").write_text("1\n")
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "a")
    monkeypatch.setattr(cmd_sync, "_REPO_DIR", tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", tmp_path / "root")
    monkeypatch.setattr(
        cmd_sync,
        "resolve_project_path",
        lambda pid: tmp_path / "root" / pid.replace(":", "/"),
    )

    def commit(rel):
        (s18 / rel).write_text("2\n")
        git("commit", "-q", "-am", rel)
        return git("rev-parse", "HEAD")

    return s18, git("rev-parse", "HEAD"), commit


def test_nested_unit_change_not_reported_for_parent(tmp_path, monkeypatch):
    s18, a, commit = _nested_units_repo(tmp_path, monkeypatch)
    b = commit("extras/x")
    paths = cmd_sync._scope_local_paths(
        s18,
        ["home:Admin:ppg:staging:18", "home:Admin:ppg:staging:18:containers"],
        {},
        "home:Admin",
    )
    assert cmd_sync._changed_files_between(a, b, paths) == []
    extras = cmd_sync._scope_local_paths(
        s18 / "extras", ["home:Admin:ppg:staging:18:extras"], {}, "home:Admin"
    )
    assert cmd_sync._changed_files_between(a, b, extras) == [
        "root/ppg/staging/18/extras/x"
    ]


@pytest.mark.parametrize("rel", ["containers/x", "pkg/x"])
def test_own_change_reported_for_parent(tmp_path, monkeypatch, rel):
    s18, a, commit = _nested_units_repo(tmp_path, monkeypatch)
    b = commit(rel)
    paths = cmd_sync._scope_local_paths(
        s18, ["home:Admin:ppg:staging:18"], {}, "home:Admin"
    )
    assert cmd_sync._changed_files_between(a, b, paths) == [
        f"root/ppg/staging/18/{rel}"
    ]


def test_nested_unit_frozen_whole_is_not_excluded(tmp_path, monkeypatch):
    s18, a, commit = _nested_units_repo(tmp_path, monkeypatch)
    b = commit("extras/x")
    paths = cmd_sync._scope_local_paths(
        s18,
        ["home:Admin:ppg:staging:18", "home:Admin:ppg:staging:18:extras"],
        {},
        "home:Admin",
    )
    assert cmd_sync._changed_files_between(a, b, paths) == [
        "root/ppg/staging/18/extras/x"
    ]


def test_tag_check_ignores_nested_unit(tmp_path, monkeypatch):
    s18, a, commit = _nested_units_repo(tmp_path, monkeypatch)
    import subprocess

    subprocess.run(["git", "tag", "t1", a], cwd=tmp_path, check=True)
    commit("extras/x")
    args = type("A", (), {"skip_tag_check": False})()
    cmd_sync._check_source_unchanged_since_tag("ppg:staging:18", "t1", args)
    commit("pkg/x")
    with pytest.raises(SystemExit, match="diverged"):
        cmd_sync._check_source_unchanged_since_tag("ppg:staging:18", "t1", args)


# --- a unit this instance's slice does not hold ------------------------------


def _unit_tree(tmp_path, monkeypatch):
    """_tree_with_record plus one package in the unit root (RockyLinux_9) and
    one in containers (ubi9)."""
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    (src / "percona-postgresql" / "obs").mkdir(parents=True)
    (src / "containers" / "img" / "obs").mkdir(parents=True)
    return src, rel


def _slice(monkeypatch, **kw):
    import percona_obs.common as common
    from percona_obs.project_config import RepositoryFilter

    monkeypatch.setattr(common, "_default_repository_filter", RepositoryFilter(**kw))


def test_unit_members_in_slice(tmp_path, monkeypatch):
    from percona_obs.project_config import RepositoryFilter
    from percona_obs.release_scope import unit_members_in_slice

    src, _ = _unit_tree(tmp_path, monkeypatch)
    members = lambda **kw: unit_members_in_slice(
        src, "ppg:staging:17", {}, repo_filter=RepositoryFilter(**kw)
    )
    assert members() == ["ppg:staging:17", "ppg:staging:17:containers"]
    assert members(include_repos=("ubi*",)) == ["ppg:staging:17:containers"]
    assert members(include_repos=("Debian_*",)) == []


def test_prerelease_skips_a_unit_out_of_slice(tmp_path, monkeypatch, capsys):
    src, rel = _unit_tree(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    _slice(monkeypatch, include_repos=("Debian_*",))
    cmd_sync.cmd_sync_prerelease(_Args())
    assert calls == []
    assert "skipped: ppg:releases:17" in capsys.readouterr().out


def test_prerelease_check_slice_exit_codes(tmp_path, monkeypatch, capsys):
    src, rel = _unit_tree(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    cmd_sync.cmd_sync_prerelease(_Args(check_slice=True))
    assert "in slice: ppg:releases:17" in capsys.readouterr().out
    _slice(monkeypatch, include_repos=("Debian_*",))
    with pytest.raises(SystemExit) as exc:
        cmd_sync.cmd_sync_prerelease(_Args(check_slice=True))
    assert exc.value.code == cmd_sync.OUT_OF_SLICE_EXIT == 3
    assert calls == []


def test_release_from_skips_a_unit_out_of_slice(tmp_path, monkeypatch, capsys):
    src, rel = _unit_tree(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    monkeypatch.setattr(
        cmd_sync,
        "read_project_description_marker",
        lambda *a, **k: pytest.fail("no OBS lookup for a skipped unit"),
    )
    _slice(monkeypatch, include_repos=("Debian_*",))
    cmd_sync.cmd_sync_release(
        _Args(
            rootprj="home:Admin",
            from_project="home:Admin:PR:pr-5:ppg:releases:17",
            skip_tag_check=False,
        )
    )
    assert calls == []
    assert "skipped: ppg:releases:17" in capsys.readouterr().out
