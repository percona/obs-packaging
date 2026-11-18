"""Project references (``{project: <id>}``) in ``qa:`` parameters."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import percona_obs.cmd_qa as cmd_qa
import percona_obs.common as common

_QA = """\
title: T
qa:
  - name: upgrade
    pipeline: ppg-upgrade-parallel
    parameters:
      OBS_PROJECT: ${OBS_ROOTPRJ}:%s
      FROM_OBS_PROJECT:
        project: ppg:staging:18
"""

PR = "isv:percona:PR:pr-9"


def _tree(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "root"
    (root / "macros.yaml").parent.mkdir(parents=True)
    (root / "macros.yaml").write_text("- M: 1\n")
    for tier, other in (("staging", None), ("releases", "staging")):
        for major in ("18", "19"):
            proj = root / "ppg" / tier / major
            proj.mkdir(parents=True)
            (proj / "project.yaml").write_text(_QA % f"ppg:{tier}:{major}")
            if other:
                (proj / "release.yaml").write_text(f"project: ppg:{other}:{major}\n")
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_qa, "REPO_ROOT", root)
    monkeypatch.setattr(
        cmd_qa, "_fetch_obs_project_repository_names", lambda a, p: set()
    )
    return root


def _show(capsys, monkeypatch, project, present=(), fallback="isv:percona"):
    listed: list[str] = []

    def packages(apiurl, obs_project):
        listed.append(obs_project)
        return {"percona-postgresql"} if obs_project in present else set()

    monkeypatch.setattr(cmd_qa, "_fetch_obs_package_names_or_fail", packages)
    cmd_qa.cmd_qa_show(
        SimpleNamespace(
            project=project,
            rootprj=PR,
            apiurl="https://obs.example",
            env_overrides=[],
            image_fallback_rootprj=fallback,
            json=True,
        )
    )
    captured = capsys.readouterr()
    value = json.loads(captured.out)[0]["params"]["FROM_OBS_PROJECT"]
    return value, listed, captured.err


def test_no_fallback_renders_current_root_without_obs(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    value, listed, _ = _show(capsys, monkeypatch, "ppg:staging:19", fallback=None)
    assert value == f"{PR}:ppg:staging:18"
    assert listed == []


def test_pr_uses_its_own_previous_major(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    value, _, err = _show(
        capsys, monkeypatch, "ppg:staging:19", present={f"{PR}:ppg:staging:18"}
    )
    assert value == f"{PR}:ppg:staging:18"
    assert "present in" in err


def test_release_pr_with_both_units_uses_the_prerelease(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    value, listed, _ = _show(
        capsys, monkeypatch, "ppg:releases:19", present={f"{PR}:ppg:releases:18"}
    )
    assert value == f"{PR}:ppg:releases:18"
    assert listed == [f"{PR}:ppg:releases:18"]


def test_release_pr_without_previous_major_falls_back_to_staging(
    tmp_path, monkeypatch, capsys
):
    _tree(tmp_path, monkeypatch)
    value, _, err = _show(capsys, monkeypatch, "ppg:releases:19")
    assert value == "isv:percona:ppg:staging:18"
    assert f"fallback: not in {PR}:ppg:releases:18" in err


def test_project_ref_with_extra_key_is_rejected(tmp_path, monkeypatch):
    root = _tree(tmp_path, monkeypatch)
    (root / "ppg" / "staging" / "19" / "project.yaml").write_text(
        "title: T\nqa:\n  pipeline: p\n  parameters:\n"
        "    FROM_OBS_PROJECT:\n      project: ppg:staging:18\n      repo: x\n"
    )
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_lanes("ppg:staging:19", {})
    assert "unknown key(s) repo" in str(exc.value)
