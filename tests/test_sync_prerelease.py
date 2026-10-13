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
    monkeypatch.setattr(cmd_sync, "_changed_files_between", lambda *a, **k: [])
    monkeypatch.setattr(
        cmd_sync,
        "apply_mirror_meta",
        lambda apiurl, prj, path, rootprj, env, publish_override=None: calls.append(
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
        lambda *a, **k: calls.append(("copy", a[1], a[2], k.get("publish_override"))),
    )
    monkeypatch.setattr(
        cmd_sync,
        "set_project_description_marker",
        lambda apiurl, prj, key, value: calls.append(("marker", prj, value)),
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


def test_happy_path_order(tmp_path, monkeypatch):
    src, rel = _tree_with_record(tmp_path, monkeypatch)
    calls = []
    _wire(monkeypatch, src, rel, calls)
    cmd_sync.cmd_sync_prerelease(_Args())
    assert calls[0] == ("meta", "home:Admin:PR:pr-5:ppg:releases:17", True)
    assert calls[1:4] == ["drain", "green", "freeze"]
    assert calls[4] == (
        "copy",
        "home:Admin:ppg:staging:17",
        "home:Admin:PR:pr-5:ppg:releases:17",
        True,
    )
    assert calls[5] == "restore"
    assert calls[6] == ("marker", "home:Admin:PR:pr-5:ppg:releases:17", SHA)


def test_marker_not_written_when_copy_fails(tmp_path, monkeypatch):
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
