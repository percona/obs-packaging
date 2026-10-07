"""Package-level ``qa:`` blocks declared in ``package.yaml``.

A project's QA lanes are its own ``project.yaml`` block plus one block per
direct package that declares ``qa:``.  Package blocks under ``_shared/`` are
reached through per-major symlinks and render macros from the link's location.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import percona_obs.cmd_qa as cmd_qa
import percona_obs.common as common

_PROJECT_QA = """\
qa:
  pipeline: ppg-multiOS-parallel
  parameters:
    VERSION: ppg-%!{PG_MAJOR_VERSION}
    IO_METHOD: [worker, sync]
  matrix: [IO_METHOD]
"""

_PKG_QA = """\
title: pkg
qa:
  pipeline: pkg-parallel
  parameters:
    PG_MAJOR: "%!{PG_MAJOR_VERSION}"
    PLATFORMS: [rocky-9, debian-13]
  matrix: [PLATFORMS]
"""


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def tree(tmp_path, monkeypatch) -> Path:
    """root/ppg/{17,18}/{project.yaml, macros.yaml, pkg -> ../_shared/pkg, other/}.

    ``other`` is a package without ``qa:``; ``17/sub/deep`` is a package in a
    subproject and must not be discovered from ``ppg:17``.
    """
    root = tmp_path / "root"
    _write(root, "macros.yaml", "- M: 1\n")
    for major in ("17", "18"):
        _write(root, f"ppg/{major}/macros.yaml", f"- PG_MAJOR_VERSION: {major}\n")
        _write(root, f"ppg/{major}/project.yaml", "title: P\n" + _PROJECT_QA)
        _write(root, f"ppg/{major}/other/package.yaml", "title: other\n")
        (root / "ppg" / major / "pkg").symlink_to(Path("..") / "_shared" / "pkg")
    _write(root, "ppg/_shared/pkg/package.yaml", _PKG_QA)
    _write(root, "ppg/17/sub/project.yaml", "title: sub\n")
    _write(root, "ppg/17/sub/deep/package.yaml", _PKG_QA)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    return root


# --- loader ----------------------------------------------------------------------


def test_lanes_project_then_packages(tree):
    lanes = cmd_qa._load_qa_lanes("ppg:17", {})
    assert [lane.package for lane in lanes] == [None, "pkg"]
    assert lanes[0].entries[0]["pipeline"] == "ppg-multiOS-parallel"
    assert lanes[1].entries[0]["pipeline"] == "pkg-parallel"


def test_shared_package_renders_per_major(tree):
    seventeen = cmd_qa._load_qa_lanes("ppg:17", {})[1].entries[0]
    eighteen = cmd_qa._load_qa_lanes("ppg:18", {})[1].entries[0]
    assert seventeen["parameters"]["PG_MAJOR"] == "17"
    assert eighteen["parameters"]["PG_MAJOR"] == "18"


def test_subproject_packages_are_not_discovered(tree):
    lanes = cmd_qa._load_qa_lanes("ppg:17", {})
    assert "deep" not in [lane.package for lane in lanes]


def test_package_without_qa_is_skipped(tree):
    lanes = cmd_qa._load_qa_lanes("ppg:17", {})
    assert "other" not in [lane.package for lane in lanes]


def test_no_blocks_at_all_is_empty(tree):
    _write(tree, "ppg/17/project.yaml", "title: P\n")
    os.remove(tree / "ppg/_shared/pkg/package.yaml")
    assert cmd_qa._load_qa_lanes("ppg:17", {}) == []


def test_package_only_project(tree):
    _write(tree, "ppg/17/project.yaml", "title: P\n")
    lanes = cmd_qa._load_qa_lanes("ppg:17", {})
    assert [lane.package for lane in lanes] == ["pkg"]


def test_package_block_validation_prefix(tree):
    _write(tree, "ppg/_shared/pkg/package.yaml", "qa:\n  pipeline: x\n")
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_lanes("ppg:17", {})
    assert str(exc.value).startswith("error: ppg:17/pkg: qa.parameters")


def test_segment_uniqueness_is_per_block(tree):
    # project block and package block both have an unnamed entry on pipeline x
    _write(tree, "ppg/17/project.yaml", "qa:\n  pipeline: x\n  parameters:\n    A: b\n")
    _write(
        tree,
        "ppg/_shared/pkg/package.yaml",
        "qa:\n  pipeline: x\n  parameters:\n    A: c\n",
    )
    lanes = cmd_qa._load_qa_lanes("ppg:17", {})
    assert len(lanes) == 2

    # two unnamed entries on the same pipeline INSIDE the package block → error
    _write(
        tree,
        "ppg/_shared/pkg/package.yaml",
        "qa:\n  - pipeline: x\n    parameters:\n      A: b\n"
        "  - pipeline: x\n    parameters:\n      A: c\n",
    )
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_lanes("ppg:17", {})
    assert str(exc.value).startswith("error: ppg:17/pkg: two qa entries")


def test_env_substitution_applies_to_package_block(tree):
    _write(
        tree,
        "ppg/_shared/pkg/package.yaml",
        "qa:\n  pipeline: x\n  parameters:\n    P: ${OBS_ROOTPRJ}:ppg\n",
    )
    lane = cmd_qa._load_qa_lanes("ppg:17", {"OBS_ROOTPRJ": "isv:percona"})[1]
    assert lane.entries[0]["parameters"]["P"] == "isv:percona:ppg"


# --- qa show ---------------------------------------------------------------------


def _show_json(project: str, capsys) -> list[dict]:
    args = SimpleNamespace(
        project=project, rootprj="isv:percona", env_overrides=[], json=True
    )
    cmd_qa.cmd_qa_show(args)
    return json.loads(capsys.readouterr().out)


def test_show_json_lists_project_then_package_combos(tree, capsys):
    out = _show_json("ppg:17", capsys)
    assert [(e["package"], e["status_context"]) for e in out] == [
        ("", "OBS QA / ppg:17 / IO_METHOD=worker"),
        ("", "OBS QA / ppg:17 / IO_METHOD=sync"),
        ("pkg", "OBS QA / ppg:17 / pkg / PLATFORMS=rocky-9"),
        ("pkg", "OBS QA / ppg:17 / pkg / PLATFORMS=debian-13"),
    ]
    assert [e["package_filter"] for e in out] == [
        "--project-only",
        "--project-only",
        "--package pkg",
        "--package pkg",
    ]
    assert out[2]["params"]["PG_MAJOR"] == "17"
    assert out[2]["pipeline"] == "pkg-parallel"


def test_show_json_package_multi_entry_segment(tree, capsys):
    _write(
        tree,
        "ppg/_shared/pkg/package.yaml",
        "qa:\n"
        "  - name: a\n    pipeline: x\n    parameters:\n      P: [1, 2]\n    matrix: [P]\n"
        "  - name: b\n    pipeline: x\n    parameters:\n      Q: v\n",
    )
    out = _show_json("ppg:17", capsys)
    pkg = [e["status_context"] for e in out if e["package"] == "pkg"]
    assert pkg == [
        "OBS QA / ppg:17 / pkg / a / P=1",
        "OBS QA / ppg:17 / pkg / a / P=2",
        "OBS QA / ppg:17 / pkg / b",
    ]
    assert {e["name_filter"] for e in out if e["package"] == "pkg"} == {
        "--name a",
        "--name b",
    }


def test_show_json_package_single_entry_no_matrix(tree, capsys):
    _write(
        tree,
        "ppg/_shared/pkg/package.yaml",
        "qa:\n  pipeline: x\n  parameters:\n    Q: v\n",
    )
    out = _show_json("ppg:17", capsys)
    assert [e["status_context"] for e in out if e["package"] == "pkg"] == [
        "OBS QA / ppg:17 / pkg"
    ]
    assert [e["label"] for e in out if e["package"] == "pkg"] == ["default"]


def test_show_json_empty_when_no_lanes(tree, capsys):
    _write(tree, "ppg/17/project.yaml", "title: P\n")
    os.remove(tree / "ppg/_shared/pkg/package.yaml")
    assert _show_json("ppg:17", capsys) == []


def test_show_human_output_names_the_package(tree, capsys):
    args = SimpleNamespace(
        project="ppg:17", rootprj="isv:percona", env_overrides=[], json=False
    )
    cmd_qa.cmd_qa_show(args)
    out = capsys.readouterr().out
    assert "ppg:17  →  pipeline: ppg-multiOS-parallel" in out
    assert "ppg:17 / pkg  →  pipeline: pkg-parallel" in out


# --- qa run --package ------------------------------------------------------------


def _run_args(project: str, **kw):
    base = dict(
        project=project,
        rootprj="isv:percona",
        env_overrides=[],
        package=None,
        project_only=False,
        name=None,
        pipeline=None,
        filter=[],
        param=[],
        dry_run=True,
        wait=False,
        report_json=None,
        profile=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_run_without_package_triggers_every_lane(tree, capsys):
    cmd_qa.cmd_qa_run(_run_args("ppg:17"))
    out = capsys.readouterr().out
    assert "would trigger pipeline 'ppg-multiOS-parallel'" in out
    assert "would trigger pipeline 'pkg-parallel'" in out


def test_run_package_selects_one_lane(tree, capsys):
    cmd_qa.cmd_qa_run(_run_args("ppg:17", package="pkg"))
    out = capsys.readouterr().out
    assert "would trigger pipeline 'pkg-parallel'" in out
    assert "ppg-multiOS-parallel" not in out
    assert "package: pkg" in out


def test_run_unknown_package_errors_listing_packages(tree):
    with pytest.raises(SystemExit) as exc:
        cmd_qa.cmd_qa_run(_run_args("ppg:17", package="nope"))
    assert str(exc.value) == (
        "error: ppg:17: no package with a qa: block named 'nope'; packages: pkg"
    )


def test_run_package_combines_with_name(tree, capsys):
    _write(
        tree,
        "ppg/_shared/pkg/package.yaml",
        "qa:\n"
        "  - name: a\n    pipeline: x\n    parameters:\n      P: va\n"
        "  - name: b\n    pipeline: x\n    parameters:\n      P: vb\n",
    )
    cmd_qa.cmd_qa_run(_run_args("ppg:17", package="pkg", name="a"))
    out = capsys.readouterr().out
    assert "P: va" in out and "P: vb" not in out

    with pytest.raises(SystemExit) as exc:
        cmd_qa.cmd_qa_run(_run_args("ppg:17", name="zzz"))
    assert "no qa entry with name 'zzz'" in str(exc.value)


def test_show_json_project_lane_package_filter_is_project_only(tree, capsys):
    out = _show_json("ppg:17", capsys)
    assert {e["package_filter"] for e in out if not e["package"]} == {"--project-only"}
    assert {e["package_filter"] for e in out if e["package"]} == {"--package pkg"}


def test_run_project_only_excludes_package_lanes_on_same_pipeline(tree, capsys):
    # the exact CI command line: qa run <project> --pipeline x --project-only
    _write(
        tree,
        "ppg/17/project.yaml",
        "qa:\n  pipeline: x\n  parameters:\n    A: projval\n",
    )
    _write(
        tree,
        "ppg/_shared/pkg/package.yaml",
        "qa:\n  pipeline: x\n  parameters:\n    A: pkgval\n",
    )
    cmd_qa.cmd_qa_run(_run_args("ppg:17", pipeline="x", project_only=True))
    out = capsys.readouterr().out
    assert "A: projval" in out
    assert "pkgval" not in out
    assert "package:" not in out


def test_run_project_only_without_project_block_errors(tree):
    _write(tree, "ppg/17/project.yaml", "title: P\n")
    with pytest.raises(SystemExit) as exc:
        cmd_qa.cmd_qa_run(_run_args("ppg:17", project_only=True))
    assert str(exc.value) == "error: ppg:17 has no qa: block in its project.yaml"


def test_run_package_and_pipeline_combine(tree, capsys):
    cmd_qa.cmd_qa_run(_run_args("ppg:17", package="pkg", pipeline="pkg-parallel"))
    out = capsys.readouterr().out
    assert "would trigger pipeline 'pkg-parallel'" in out
    assert "ppg-multiOS-parallel" not in out

    with pytest.raises(SystemExit) as exc:
        cmd_qa.cmd_qa_run(_run_args("ppg:17", package="pkg", pipeline="nope"))
    assert "(after --package pkg)" in str(exc.value)

    with pytest.raises(SystemExit) as exc:
        cmd_qa.cmd_qa_run(_run_args("ppg:17", project_only=True, pipeline="nope"))
    assert "(after --project-only)" in str(exc.value)


def test_run_project_only_and_package_are_exclusive(tree):
    with pytest.raises(SystemExit) as exc:
        cmd_qa.cmd_qa_run(_run_args("ppg:17", package="pkg", project_only=True))
    assert (
        str(exc.value) == "error: --project-only and --package are mutually exclusive"
    )


def test_package_name_colliding_with_project_segment_is_rejected(tree):
    _write(
        tree,
        "ppg/17/project.yaml",
        "qa:\n"
        "  - name: pkg\n    pipeline: x\n    parameters:\n      A: b\n"
        "  - name: other\n    pipeline: y\n    parameters:\n      A: b\n",
    )
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_lanes("ppg:17", {})
    assert "rename the project entry" in str(exc.value)
    assert "'pkg'" in str(exc.value)


def test_single_project_entry_named_like_package_is_allowed(tree):
    # a single-entry block renders no segment, so no context can collide
    _write(
        tree,
        "ppg/17/project.yaml",
        "qa:\n  name: pkg\n  pipeline: x\n  parameters:\n    A: b\n",
    )
    assert [lane.package for lane in cmd_qa._load_qa_lanes("ppg:17", {})] == [
        None,
        "pkg",
    ]


# --- run state -------------------------------------------------------------------


def test_run_state_round_trips_package(tmp_path, monkeypatch):
    import percona_obs.qa_state as qa_state

    monkeypatch.setattr(qa_state, "_STATE_DIR", tmp_path / "qa")
    state = qa_state.RunState(
        run_id="r1",
        project="ppg:17",
        pipeline="x",
        created_at="t",
        combos=[qa_state.Combo(label="", params={"A": "b"})],
        package="pkg",
    )
    qa_state.save_state(state)
    assert qa_state.load_state("r1").package == "pkg"

    # a state file written before the field existed loads with ""
    path = tmp_path / "qa" / "r0.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "r0",
                "project": "ppg:17",
                "pipeline": "x",
                "created_at": "t",
                "combos": [],
            }
        )
    )
    assert qa_state.load_state("r0").package == ""


def test_report_json_carries_package(tmp_path):
    import percona_obs.qa_state as qa_state

    state = qa_state.RunState(
        run_id="r1",
        project="ppg:17",
        pipeline="x",
        created_at="t",
        combos=[qa_state.Combo(label="P=1", params={"P": "1"})],
        package="pkg",
    )
    out = tmp_path / "report.json"
    qa_state.write_report_json(state, out)
    data = json.loads(out.read_text())
    assert data["package"] == "pkg"
    assert data["combos"][0]["package"] == "pkg"


def test_qa_list_shows_project_slash_package(tmp_path, monkeypatch, capsys):
    import percona_obs.qa_state as qa_state

    monkeypatch.setattr(qa_state, "_STATE_DIR", tmp_path / "qa")
    for run_id, package in (("r1", "pkg"), ("r2", "")):
        qa_state.save_state(
            qa_state.RunState(
                run_id=run_id,
                project="ppg:17",
                pipeline="x",
                created_at="t",
                combos=[],
                package=package,
            )
        )
    cmd_qa.cmd_qa_list(SimpleNamespace(running=False))
    out = capsys.readouterr().out
    assert "ppg:17/pkg  x" in out
    assert "ppg:17  x" in out
