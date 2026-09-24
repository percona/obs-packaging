"""The optional ``name:`` key of a ``qa:`` entry.

Two entries may legitimately share a pipeline (the ubi8/ubi9 container lanes),
so the check-run name (``status_context``) and ``qa run`` selection must be able
to tell them apart.  Entries without a ``name`` must keep their contexts
byte-for-byte.
"""

import json
from types import SimpleNamespace

import pytest

import percona_obs.cmd_qa as cmd_qa
import percona_obs.common as common

_SHARED_PIPELINE = "docker-server-parallel-generic"


def _write_project(tmp_path, monkeypatch, qa_yaml: str, project: str = "ppg:p"):
    root = tmp_path / "root"
    parts = project.split(":")
    d = root.joinpath(*parts)
    d.mkdir(parents=True)
    (root / "macros.yaml").write_text("- M: 1\n")
    (d / "project.yaml").write_text("title: P\n" + qa_yaml)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    return project


def _show_json(project: str, capsys) -> list[dict]:
    args = SimpleNamespace(
        project=project, rootprj="isv:percona", env_overrides=[], json=True
    )
    cmd_qa.cmd_qa_show(args)
    return json.loads(capsys.readouterr().out)


_TWO_NAMED = f"""\
qa:
  - name: ubi8
    pipeline: {_SHARED_PIPELINE}
    parameters:
      REPOSITORY: reg/ubi8
      WITH_POSTGIS: [true, false]
    matrix: [WITH_POSTGIS]
  - name: ubi9
    pipeline: {_SHARED_PIPELINE}
    parameters:
      REPOSITORY: reg/ubi9
      WITH_POSTGIS: [true, false]
    matrix: [WITH_POSTGIS]
"""

_TWO_UNNAMED = """\
qa:
  - pipeline: docker-server-parallel-generic
    parameters:
      REPOSITORY: reg/ubi9
      WITH_POSTGIS: [true, false]
    matrix: [WITH_POSTGIS]
  - pipeline: ppg-obs-upgrade
    parameters:
      REPOSITORY: reg/ubi9
      OLD_SERVER_VERSION: "15.19"
"""


# --- validation ------------------------------------------------------------------


def test_name_is_optional_and_must_be_a_non_empty_string(tmp_path, monkeypatch):
    p = _write_project(
        tmp_path,
        monkeypatch,
        "qa:\n  name: 7\n  pipeline: x\n  parameters:\n    A: b\n",
    )
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_block(p, {})
    assert "qa.name must be a non-empty string" in str(exc.value)


def test_duplicate_name_is_rejected(tmp_path, monkeypatch):
    p = _write_project(
        tmp_path,
        monkeypatch,
        f"qa:\n"
        f"  - name: ubi8\n    pipeline: {_SHARED_PIPELINE}\n"
        f"    parameters:\n      A: b\n"
        f"  - name: ubi8\n    pipeline: {_SHARED_PIPELINE}\n"
        f"    parameters:\n      A: c\n",
    )
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_block(p, {})
    assert "same check segment 'ubi8'" in str(exc.value)
    assert "rename one of them" in str(exc.value)


def test_same_pipeline_without_names_is_rejected(tmp_path, monkeypatch):
    """The defect that hid the ubi8 lane: two entries collapsing onto one check."""
    p = _write_project(
        tmp_path,
        monkeypatch,
        f"qa:\n"
        f"  - pipeline: {_SHARED_PIPELINE}\n"
        f"    parameters:\n      A: b\n"
        f"  - pipeline: {_SHARED_PIPELINE}\n"
        f"    parameters:\n      A: c\n",
    )
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_block(p, {})
    assert f"same check segment '{_SHARED_PIPELINE}'" in str(exc.value)
    assert "give each one a distinct 'name'" in str(exc.value)


def test_named_entry_loads(tmp_path, monkeypatch):
    p = _write_project(
        tmp_path,
        monkeypatch,
        "qa:\n  name: ubi8\n  pipeline: x\n  parameters:\n    A: b\n",
    )
    entries = cmd_qa._load_qa_block(p, {})
    assert entries is not None
    assert entries[0]["name"] == "ubi8"


# --- status_context --------------------------------------------------------------


def test_same_pipeline_named_entries_get_distinct_contexts(
    tmp_path, monkeypatch, capsys
):
    p = _write_project(tmp_path, monkeypatch, _TWO_NAMED)
    out = _show_json(p, capsys)
    assert len(out) == 4
    contexts = {e["status_context"] for e in out}
    assert contexts == {
        "OBS QA / ppg:p / ubi8 / WITH_POSTGIS=true",
        "OBS QA / ppg:p / ubi8 / WITH_POSTGIS=false",
        "OBS QA / ppg:p / ubi9 / WITH_POSTGIS=true",
        "OBS QA / ppg:p / ubi9 / WITH_POSTGIS=false",
    }
    # one context per (flavour, axis) combo — nothing would be de-duplicated
    assert len(contexts) == len(out)


def test_unnamed_multi_entry_contexts_are_unchanged(tmp_path, monkeypatch, capsys):
    p = _write_project(tmp_path, monkeypatch, _TWO_UNNAMED)
    out = _show_json(p, capsys)
    assert [e["status_context"] for e in out] == [
        "OBS QA / ppg:p / docker-server-parallel-generic / WITH_POSTGIS=true",
        "OBS QA / ppg:p / docker-server-parallel-generic / WITH_POSTGIS=false",
        "OBS QA / ppg:p / ppg-obs-upgrade",
    ]
    assert all(e["name"] == "" for e in out)


def test_single_entry_context_ignores_the_name(tmp_path, monkeypatch, capsys):
    p = _write_project(
        tmp_path,
        monkeypatch,
        "qa:\n  name: ubi8\n  pipeline: x\n"
        "  parameters:\n    P: [a]\n  matrix: [P]\n",
    )
    out = _show_json(p, capsys)
    assert [e["status_context"] for e in out] == ["OBS QA / ppg:p / P=a"]


# --- name_filter -----------------------------------------------------------------


def test_name_filter_is_emitted(tmp_path, monkeypatch, capsys):
    p = _write_project(tmp_path, monkeypatch, _TWO_NAMED)
    out = _show_json(p, capsys)
    assert {e["name_filter"] for e in out} == {"--name ubi8", "--name ubi9"}


def test_name_filter_is_empty_when_unnamed(tmp_path, monkeypatch, capsys):
    p = _write_project(tmp_path, monkeypatch, _TWO_UNNAMED)
    out = _show_json(p, capsys)
    assert {e["name_filter"] for e in out} == {""}


# --- qa run --name ---------------------------------------------------------------


def _run_args(project: str, **kw):
    base = dict(
        project=project,
        rootprj="isv:percona",
        env_overrides=[],
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


def test_qa_run_name_selects_one_entry(tmp_path, monkeypatch, capsys):
    p = _write_project(tmp_path, monkeypatch, _TWO_NAMED)
    cmd_qa.cmd_qa_run(_run_args(p, name="ubi9"))
    out = capsys.readouterr().out
    assert "reg/ubi9" in out
    assert "reg/ubi8" not in out


def test_qa_run_name_combines_with_pipeline(tmp_path, monkeypatch, capsys):
    p = _write_project(tmp_path, monkeypatch, _TWO_NAMED)
    cmd_qa.cmd_qa_run(_run_args(p, name="ubi8", pipeline=_SHARED_PIPELINE))
    out = capsys.readouterr().out
    assert "reg/ubi8" in out
    assert "reg/ubi9" not in out

    with pytest.raises(SystemExit) as exc:
        cmd_qa.cmd_qa_run(_run_args(p, name="ubi8", pipeline="other"))
    assert "no qa entry with pipeline 'other' (after --name ubi8)" in str(exc.value)


def test_qa_run_unknown_name_errors(tmp_path, monkeypatch):
    p = _write_project(tmp_path, monkeypatch, _TWO_NAMED)
    with pytest.raises(SystemExit) as exc:
        cmd_qa.cmd_qa_run(_run_args(p, name="ubi7"))
    assert "no qa entry with name 'ubi7'" in str(exc.value)


# --- the tree --------------------------------------------------------------------


def test_container_projects_name_both_lanes():
    from pathlib import Path

    import yaml

    repo_root = Path(__file__).resolve().parent.parent / "root"
    for rel in (
        "ppg/staging/_shared/containers/project.yaml",
        "ppg/staging/containers/project.yaml",
    ):
        text = (repo_root / rel).read_text(encoding="utf-8")
        qa = yaml.safe_load(text.replace("%!{", "${"))["qa"]
        assert isinstance(qa, list) and len(qa) == 2, rel
        assert [e["name"] for e in qa] == ["ubi8", "ubi9"], rel
