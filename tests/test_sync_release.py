"""Unit tests for the sync release subproject handling (percona_obs.cmd_sync).

_collect_release_subprojects maps source subprojects to release mirrors;
_sync_release_subprojects must hard-error on missing mirrors and report
OBS-side orphans.  OBS interaction is monkeypatched out.
"""

from pathlib import Path

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
