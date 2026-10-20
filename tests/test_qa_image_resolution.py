"""Image references flow through `qa show` / `qa run` and the profile."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import percona_obs.cli as cli
import percona_obs.cmd_qa as cmd_qa
import percona_obs.common as common
from percona_obs.common import registry_env_override

_QA = """\
title: C
qa:
  - name: ubi9
    pipeline: docker-component-parallel
    parameters:
      TAG: "18"
      REPOSITORY:
        image: percona-pgbouncer
        repository: ubi9
      SERVER_REPOSITORY:
        image: percona-distribution-postgresql
        repository: ubi9
        project: ppg:staging:18:containers
"""


def _tree(tmp_path, monkeypatch, qa_text=_QA) -> Path:
    root = tmp_path / "root"
    proj = root / "ppg" / "staging" / "common" / "tools" / "containers"
    proj.mkdir(parents=True)
    (root / "macros.yaml").write_text("- M: 1\n")
    (proj / "project.yaml").write_text(qa_text)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    return root


def _args(**kw):
    base = dict(
        project="ppg:staging:common:tools:containers",
        rootprj="isv:percona:PR:pr-9",
        apiurl="https://obs.example",
        env_overrides=[registry_env_override("reg.example")],
        image_fallback_rootprj=None,
        json=True,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _show_json(capsys, args):
    cmd_qa.cmd_qa_show(args)
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.err


def test_show_renders_image_refs_without_fallback_and_without_obs(
    tmp_path, monkeypatch, capsys
):
    _tree(tmp_path, monkeypatch)

    def boom(apiurl, project):
        raise AssertionError("OBS must not be queried without a fallback rootprj")

    monkeypatch.setattr(cmd_qa, "_fetch_obs_package_names_or_fail", boom)
    entries, err = _show_json(capsys, _args())
    params = entries[0]["params"]
    assert params["REPOSITORY"] == (
        "reg.example/isv/percona/pr/pr-9/ppg/staging/common/tools/containers/ubi9"
    )
    assert params["SERVER_REPOSITORY"] == (
        "reg.example/isv/percona/pr/pr-9/ppg/staging/18/containers/ubi9"
    )
    assert params["TAG"] == "18"


def test_show_falls_back_for_absent_image_and_reports(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    listed: list[str] = []

    def fake_list(apiurl, project):
        listed.append(project)
        return {"percona-pgbouncer"} if project.endswith("tools:containers") else set()

    monkeypatch.setattr(cmd_qa, "_fetch_obs_package_names_or_fail", fake_list)
    entries, err = _show_json(capsys, _args(image_fallback_rootprj="isv:percona"))
    params = entries[0]["params"]
    assert params["REPOSITORY"].startswith("reg.example/isv/percona/pr/pr-9/")
    assert params["SERVER_REPOSITORY"] == (
        "reg.example/isv/percona/ppg/staging/18/containers/ubi9"
    )
    assert listed == [
        "isv:percona:PR:pr-9:ppg:staging:common:tools:containers",
        "isv:percona:PR:pr-9:ppg:staging:18:containers",
    ]
    assert "percona-distribution-postgresql" in err and "fallback" in err
    assert "percona-pgbouncer" in err and "present" in err


def test_mapping_without_image_is_rejected(tmp_path, monkeypatch):
    _tree(
        tmp_path,
        monkeypatch,
        "title: C\nqa:\n  pipeline: p\n  parameters:\n    REPOSITORY:\n      repository: ubi9\n",
    )
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_lanes("ppg:staging:common:tools:containers", {})
    assert "qa.parameters.REPOSITORY" in str(exc.value)
    assert "image" in str(exc.value)


def test_image_ref_inside_a_list_is_rejected(tmp_path, monkeypatch):
    _tree(
        tmp_path,
        monkeypatch,
        "title: C\nqa:\n  pipeline: p\n  parameters:\n    REPOSITORY:\n"
        "      - {image: a, repository: ubi9}\n      - {image: b, repository: ubi9}\n"
        "  matrix: [REPOSITORY]\n",
    )
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_lanes("ppg:staging:common:tools:containers", {})
    assert "scalars" in str(exc.value)


def test_run_dry_run_resolves_images(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    monkeypatch.setattr(cmd_qa, "_fetch_obs_package_names_or_fail", lambda a, p: set())
    monkeypatch.setattr(cmd_qa, "project_binary_versions", lambda *a, **k: {})
    monkeypatch.setattr(cmd_qa, "load_jenkins_config", lambda *a, **k: None)
    args = _args(
        image_fallback_rootprj="isv:percona",
        dry_run=True,
        wait=False,
        filter=[],
        param=[],
        pipeline=None,
        name=None,
        package=None,
        project_only=False,
        report_json=None,
    )
    cmd_qa.cmd_qa_run(args)
    out = capsys.readouterr().out
    assert "reg.example/isv/percona/ppg/staging/common/tools/containers/ubi9" in out


# --- profile / CLI plumbing -----------------------------------------------------


import argparse

import percona_obs.cmd_profile as cmd_profile


def _run_main(monkeypatch, argv, profiles_dir):
    """Run ``cli.main()`` with a stub parser (same pattern as
    tests/test_container_registry.py::_run_main) and return the resolved
    ``args.image_fallback_rootprj``.  The stub uses the local-only ``project``
    command so no OBS connection is attempted."""
    monkeypatch.setattr(cmd_profile, "_PROFILES_DIR", profiles_dir)
    captured: dict[str, object] = {}

    def fake_build_parser() -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(prog="percona-obs")
        p.add_argument("-A", "--apiurl")
        p.add_argument("-R", "--rootprj")
        p.add_argument("-P", "--profile")
        p.add_argument("-e", "--env", action="append", default=[], dest="env_overrides")
        p.add_argument(
            "--image-fallback-rootprj", default=None, dest="image_fallback_rootprj"
        )
        p.add_argument("--verbose", action="store_true", default=False)
        p.add_argument("command")
        p.set_defaults(
            func=lambda a: captured.__setitem__("fallback", a.image_fallback_rootprj)
        )
        return p

    monkeypatch.setattr(cli, "build_parser", fake_build_parser)
    monkeypatch.setattr(cli.sys, "argv", ["percona-obs", *argv])
    cli.main()
    return captured["fallback"]


def test_profile_key_sets_fallback(tmp_path, monkeypatch):
    (tmp_path / "ci.yaml").write_text(
        "apiurl: http://a\nrootprj: isv:percona:PR:pr-9\nimage-fallback-rootprj: isv:percona\n"
    )
    assert _run_main(monkeypatch, ["-P", "ci", "project"], tmp_path) == "isv:percona"


def test_cli_flag_overrides_profile_key(tmp_path, monkeypatch):
    (tmp_path / "ci.yaml").write_text(
        "apiurl: http://a\nrootprj: isv:percona:PR:pr-9\nimage-fallback-rootprj: isv:percona\n"
    )
    assert (
        _run_main(
            monkeypatch,
            ["-P", "ci", "--image-fallback-rootprj", "home:me", "project"],
            tmp_path,
        )
        == "home:me"
    )


def test_no_key_means_no_fallback(tmp_path, monkeypatch):
    (tmp_path / "ci.yaml").write_text("apiurl: http://a\nrootprj: isv:percona\n")
    assert _run_main(monkeypatch, ["-P", "ci", "project"], tmp_path) is None
