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


def test_prerelease_meta_redirects_external_paths_to_production_root(
    tmp_path, monkeypatch
):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    seen = {}
    monkeypatch.setattr(
        cmd_sync,
        "apply_mirror_meta",
        lambda apiurl, prj, path, rootprj, env, **k: seen.setdefault(
            "meta",
            (
                prj,
                k.get("branch_rootprj"),
                k.get("active_projects"),
                k.get("branch_fallbacks"),
            ),
        ),
    )
    monkeypatch.setattr(
        cmd_sync,
        "release_tree",
        lambda *a, **k: seen.setdefault(
            "tree",
            (
                k.get("branch_rootprj"),
                k.get("active_projects"),
                k.get("branch_fallbacks"),
            ),
        ),
    )
    cmd_sync.cmd_sync_prerelease(_Args())
    top = "home:Admin:PR:pr-5:ppg:releases:17"
    expected = {top, f"{top}:containers", f"{top}:tarballs"}
    assert seen["meta"] == (top, "home:Admin", expected, False)
    assert seen["tree"] == ("home:Admin", expected, False)
    assert seen["meta"][3] is False and seen["tree"][2] is False
