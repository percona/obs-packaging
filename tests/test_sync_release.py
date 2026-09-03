"""Unit tests for the sync release subproject handling (percona_obs.cmd_sync).

_collect_release_subprojects maps source subprojects to release mirrors;
_sync_release_subprojects must hard-error on missing mirrors and report
OBS-side orphans.  OBS interaction is monkeypatched out.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import percona_obs.cmd_sync as cmd_sync
from percona_obs.cmd_sync import (
    _collect_release_subprojects,
    _sync_release_subprojects,
)


def _mk_tree(tmp_path: Path):
    """staging tree with containers+tarballs; release tree mirroring only containers."""
    src = tmp_path / "root/ppg/staging/17"
    for sub in ("containers", "tarballs"):
        (src / sub).mkdir(parents=True)
        (src / sub / "project.yaml").write_text("repositories: []\n")
    (src / "project.yaml").write_text("repositories: []\n")
    rel = tmp_path / "root/ppg/releases/17"
    (rel / "containers").mkdir(parents=True)
    (rel / "containers" / "project.yaml").write_text("build: false\n")
    (rel / "release.yaml").write_text(
        "project: ppg:staging:17\nreleases: [ppg/17.11-1]\n"
    )
    return src, rel


def test_collect_pairs_and_missing(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path)
    monkeypatch.setattr(cmd_sync, "resolve_project_path", lambda pid: src)
    pairs, missing = _collect_release_subprojects("ppg:staging:17", rel)
    assert [name for name, _ in pairs] == ["containers"]
    assert missing == ["tarballs"]


def test_missing_mirror_is_hard_error(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path)
    monkeypatch.setattr(cmd_sync, "resolve_project_path", lambda pid: src)
    monkeypatch.setattr(cmd_sync, "_REPO_DIR", tmp_path)

    class Args:
        rootprj = "home:Admin"

    with pytest.raises(SystemExit, match="tarballs"):
        _sync_release_subprojects(
            "http://obs",
            Args(),
            "ppg:staging:17",
            "home:Admin:ppg:releases:17",
            rel,
            env_vars={},
        )


def test_orphan_reporting(tmp_path, monkeypatch, capsys):
    src, rel = _mk_tree(tmp_path)
    # complete the mirror so no hard error fires
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text("build: false\n")
    monkeypatch.setattr(cmd_sync, "resolve_project_path", lambda pid: src)
    monkeypatch.setattr(cmd_sync, "_REPO_DIR", tmp_path)
    # neutralize the OBS side of the per-subproject body
    monkeypatch.setattr(
        cmd_sync, "_apply_project_config", lambda *a, **k: (False, None)
    )
    monkeypatch.setattr(cmd_sync, "_disable_project_builds", lambda *a, **k: None)
    monkeypatch.setattr(
        cmd_sync, "_read_project_release_source", lambda *a, **k: ([], None)
    )
    monkeypatch.setattr(cmd_sync, "_add_release_targets", lambda *a, **k: None)
    monkeypatch.setattr(cmd_sync, "_remove_release_targets", lambda *a, **k: None)
    monkeypatch.setattr(cmd_sync.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_subproject_names",
        lambda apiurl, prefix: {
            "home:Admin:ppg:releases:17:containers",
            "home:Admin:ppg:releases:17:containers:ubi9",  # old layout = orphan
        },
    )

    class Args:
        rootprj = "home:Admin"

    _sync_release_subprojects(
        "http://obs",
        Args(),
        "ppg:staging:17",
        "home:Admin:ppg:releases:17",
        rel,
        env_vars={},
    )
    out = capsys.readouterr().out
    assert "orphaned release subproject" in out
    assert "containers:ubi9" in out
    assert "sync delete" in out


class _Args:
    """Minimal args namespace matching what cmd_sync_release touches."""

    def __init__(self, project, rootprj, no_freeze=False, verify_timeout=600):
        self.project = project
        self.force = False
        self.skip_tag_check = True
        self.no_freeze = no_freeze
        self.freeze_timeout = 1
        self.verify_timeout = verify_timeout
        self.profile = None
        self.rootprj = rootprj
        self.env_overrides = None
        self.message = None


def _wire_release_update_path(monkeypatch, src, rel):
    """Stub every OBS/osc touchpoint cmd_sync_release hits on the update
    (project-exists) path, so the test only exercises the freeze wiring."""
    monkeypatch.setattr(
        cmd_sync,
        "resolve_project_path",
        lambda pid: src if pid == "ppg:staging:17" else rel,
    )
    monkeypatch.setattr(cmd_sync, "_REPO_DIR", rel.parents[2])
    monkeypatch.setattr(cmd_sync.osc.conf, "config", {"apiurl": "http://obs"})
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda *a, **k: True)
    monkeypatch.setattr(
        cmd_sync, "_apply_project_config", lambda *a, **k: (False, None)
    )
    monkeypatch.setattr(cmd_sync, "_disable_project_builds", lambda *a, **k: None)
    monkeypatch.setattr(
        cmd_sync, "_read_project_release_source", lambda *a, **k: ([], None)
    )
    monkeypatch.setattr(
        cmd_sync, "_filter_release_repo_names", lambda apiurl, names, target: names
    )
    monkeypatch.setattr(cmd_sync, "_add_release_targets", lambda *a, **k: None)
    monkeypatch.setattr(cmd_sync, "_remove_release_targets", lambda *a, **k: None)
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_subproject_names", lambda apiurl, prefix: set()
    )


def test_freeze_order_and_restore_on_failure(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text("build: false\n")
    _wire_release_update_path(monkeypatch, src, rel)

    calls = []
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
    monkeypatch.setattr(
        cmd_sync, "restore_builds", lambda *a, **k: calls.append("restore")
    )
    monkeypatch.setattr(cmd_sync, "verify_release_landed", lambda *a, **k: None)

    def boom(*a, **k):
        calls.append("release")
        raise RuntimeError("osc failed")

    monkeypatch.setattr(cmd_sync.subprocess, "run", boom)

    args = _Args(project="ppg:releases:17", rootprj="home:Admin")

    with pytest.raises(RuntimeError):
        cmd_sync.cmd_sync_release(args)

    assert calls[:3] == ["drain", "green", "freeze"]
    assert calls[-1] == "restore"


def test_red_staging_aborts_before_freeze(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text("build: false\n")
    _wire_release_update_path(monkeypatch, src, rel)

    freeze_called = []
    monkeypatch.setattr(cmd_sync, "wait_for_quiesce", lambda *a, **k: None)
    monkeypatch.setattr(
        cmd_sync, "assert_all_green", lambda *a, **k: ["p/pkg repo/x86_64: failed"]
    )
    monkeypatch.setattr(
        cmd_sync, "freeze_builds", lambda *a, **k: freeze_called.append(1) or {}
    )
    monkeypatch.setattr(cmd_sync, "restore_builds", lambda *a, **k: None)
    monkeypatch.setattr(cmd_sync, "verify_release_landed", lambda *a, **k: None)
    monkeypatch.setattr(
        cmd_sync.subprocess,
        "run",
        lambda *a, **k: pytest.fail("osc release must not run"),
    )

    args = _Args(project="ppg:releases:17", rootprj="home:Admin")

    with pytest.raises(SystemExit, match="not fully green"):
        cmd_sync.cmd_sync_release(args)

    assert freeze_called == []


def test_no_freeze_skips_gate_but_verifies(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text("build: false\n")
    _wire_release_update_path(monkeypatch, src, rel)

    def fail_if_called(*a, **k):
        pytest.fail("drain/green/freeze must be skipped with --no-freeze")

    monkeypatch.setattr(cmd_sync, "wait_for_quiesce", fail_if_called)
    monkeypatch.setattr(cmd_sync, "assert_all_green", fail_if_called)
    monkeypatch.setattr(cmd_sync, "freeze_builds", fail_if_called)
    monkeypatch.setattr(cmd_sync, "restore_builds", lambda *a, **k: None)
    monkeypatch.setattr(cmd_sync.subprocess, "run", lambda *a, **k: None)

    verified = []
    monkeypatch.setattr(
        cmd_sync,
        "verify_release_landed",
        lambda apiurl, src_prj, rel_prj, timeout_s=600: verified.append(
            (src_prj, rel_prj)
        ),
    )

    args = _Args(
        project="ppg:releases:17",
        rootprj="home:Admin",
        no_freeze=True,
        verify_timeout=5,
    )

    cmd_sync.cmd_sync_release(args)

    assert ("home:Admin:ppg:staging:17", "home:Admin:ppg:releases:17") in verified
    assert (
        "home:Admin:ppg:staging:17:containers",
        "home:Admin:ppg:releases:17:containers",
    ) in verified
    assert (
        "home:Admin:ppg:staging:17:tarballs",
        "home:Admin:ppg:releases:17:tarballs",
    ) in verified


def _dry_run_args(project="ppg:releases:17"):
    return SimpleNamespace(
        project=project,
        rootprj="home:Admin",
        env_overrides=None,
        profile=None,
        force=False,
        skip_tag_check=False,
        dry_run=True,
        no_freeze=False,
        freeze_timeout=1,
        verify_timeout=0,
        message=None,
    )


def _patch_dry_run_common(monkeypatch, tmp_path, src, rel):
    monkeypatch.setattr(
        cmd_sync,
        "resolve_project_path",
        lambda pid: rel if "releases" in pid else src,
    )
    monkeypatch.setattr(cmd_sync, "_REPO_DIR", tmp_path)
    monkeypatch.setattr(cmd_sync.osc.conf, "config", {"apiurl": "http://obs"})


def test_dry_run_reports_all_failures(tmp_path, monkeypatch, capsys):
    src, rel = _mk_tree(tmp_path)  # tarballs mirror missing by construction
    (rel / "CHANGELOG.md").write_text("# Changelog\n")  # no release section
    _patch_dry_run_common(monkeypatch, tmp_path, src, rel)
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda a, p: False)
    monkeypatch.setattr(cmd_sync, "assert_all_green", lambda a, p: [])
    monkeypatch.setattr(
        cmd_sync.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
    )
    with pytest.raises(SystemExit, match="dry-run failed"):
        cmd_sync.cmd_sync_release(_dry_run_args())
    err = capsys.readouterr().err
    assert "missing release mirror" in err and "tarballs" in err
    assert "## [17.11-1]" in err
    assert "not found on OBS" in err


def test_dry_run_passes_when_clean(tmp_path, monkeypatch, capsys):
    src, rel = _mk_tree(tmp_path)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text("build: false\n")
    (rel / "CHANGELOG.md").write_text("# Changelog\n\n## [17.11-1] - 2026-09-03\n")
    _patch_dry_run_common(monkeypatch, tmp_path, src, rel)
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda a, p: True)
    monkeypatch.setattr(cmd_sync, "assert_all_green", lambda a, p: [])
    monkeypatch.setattr(
        cmd_sync.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
    )
    cmd_sync.cmd_sync_release(_dry_run_args())
    assert "dry-run passed" in capsys.readouterr().out


def test_filter_release_repo_names_warns_and_drops(monkeypatch, capsys):
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_project_repository_names",
        lambda apiurl, prj: {"RockyLinux_9", "Debian_13"},
    )
    kept = cmd_sync._filter_release_repo_names(
        "http://obs", ["RockyLinux_9", "UBI_9", "Debian_13"], "x:rel"
    )
    assert kept == ["RockyLinux_9", "Debian_13"]
    assert "UBI_9 has no counterpart" in capsys.readouterr().out
