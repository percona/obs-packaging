"""`project verify` validates qa: image references against the tree."""

from pathlib import Path

import percona_obs.cmd_project as cmd_project
import percona_obs.common as common

_PROJECT = """\
title: C
repositories:
  - name: ubi9
    archs: [x86_64]
    paths:
      - project: RedHat:UBI-9
        repository: standard
qa:
  pipeline: p
  parameters:
    REPOSITORY:
      image: {image}
      repository: {repository}
      {project_line}
"""


def _tree(tmp_path, monkeypatch, image="img", repository="ubi9", project_line=""):
    root = tmp_path / "root"
    proj = root / "ppg" / "staging" / "c"
    (proj / "img").mkdir(parents=True)
    (proj / "img" / "package.yaml").write_text("title: img\n")
    (root / "macros.yaml").write_text("- M: 1\n")
    (root / "project.yaml").write_text("title: R\nname: isv:percona\n")
    (proj / "project.yaml").write_text(
        _PROJECT.format(image=image, repository=repository, project_line=project_line)
    )
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_project.common, "REPO_ROOT", root)
    return root


def _errors(root):
    return [msg for _p, msg in cmd_project._validate_qa_image_refs(root, {})]


def test_valid_reference_passes(tmp_path, monkeypatch):
    assert _errors(_tree(tmp_path, monkeypatch)) == []


def test_unknown_image_is_reported(tmp_path, monkeypatch):
    errs = _errors(_tree(tmp_path, monkeypatch, image="nope"))
    assert len(errs) == 1
    assert "REPOSITORY" in errs[0] and "nope" in errs[0] and "ppg:staging:c" in errs[0]


def test_unknown_repository_is_reported(tmp_path, monkeypatch):
    errs = _errors(_tree(tmp_path, monkeypatch, repository="ubi8"))
    assert len(errs) == 1
    assert "ubi8" in errs[0]


def test_project_outside_the_tree_is_skipped(tmp_path, monkeypatch):
    errs = _errors(
        _tree(
            tmp_path,
            monkeypatch,
            project_line="project: ppg:staging:15:extras:containers",
        )
    )
    assert errs == []


def test_explicit_project_in_tree_is_checked(tmp_path, monkeypatch):
    root = _tree(tmp_path, monkeypatch, project_line="project: ppg:staging:d")
    other = root / "ppg" / "staging" / "d"
    other.mkdir()
    (other / "project.yaml").write_text(
        "title: D\nrepositories:\n  - name: ubi8\n    archs: [x86_64]\n"
    )
    errs = _errors(root)
    # image `img` is not a package of ppg:staging:d, and ubi9 is not its repo
    assert len(errs) == 2


def _other(root, text):
    other = root / "ppg" / "staging" / "d"
    other.mkdir()
    (other / "project.yaml").write_text(text)


def test_malformed_referenced_project_is_reported_not_fatal(tmp_path, monkeypatch):
    root = _tree(tmp_path, monkeypatch, project_line="project: ppg:staging:d")
    _other(root, "title: D\nrepositories: nope\n")
    res = cmd_project._validate_qa_image_refs(root, {})
    assert len(res) >= 1
    assert all(p.name == "project.yaml" for p, _m in res)


def test_undefined_variable_in_referenced_project_is_skipped(tmp_path, monkeypatch):
    root = _tree(tmp_path, monkeypatch, project_line="project: ppg:staging:d")
    _other(
        root,
        "title: ${MISSING}\nrepositories:\n  - name: ubi9\n    archs: [x86_64]\n",
    )
    (root / "ppg" / "staging" / "d" / "img").mkdir()
    res = cmd_project._validate_qa_image_refs(root, {"X": "1"})
    assert res == []
