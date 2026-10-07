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
