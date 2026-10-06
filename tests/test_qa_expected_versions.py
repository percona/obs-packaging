"""``percona-obs qa`` adds EXPECTED_VERSIONS to every triggered job.

The value lists the project's ``*_VERSION`` macros, resolved from its own
macros.yaml chain, so test jobs check installed software against the versions
OBS builds for exactly this project (and, in a PR, against the PR's values)
without every qa: entry repeating them.
"""

import json
from types import SimpleNamespace

import percona_obs.cmd_qa as cmd_qa
import percona_obs.common as common

_QA = """\
title: P
qa:
  - name: server
    pipeline: ppg-multiOS-parallel
    parameters:
      VERSION: ppg-%!{PG_VERSION}
  - name: pinned
    pipeline: other-job
    parameters:
      EXPECTED_VERSIONS: "PGBACKREST_VERSION=1.0"
"""


def _tree(tmp_path, monkeypatch, root_macros="", qa=_QA):
    """root/ppg/staging/{17,18} sharing root macros, each with its own."""
    root = tmp_path / "root"
    (root / "ppg" / "staging").mkdir(parents=True)
    (root / "macros.yaml").write_text(root_macros)
    for major, minor in (("17", "11"), ("18", "6")):
        d = root / "ppg" / "staging" / major
        d.mkdir()
        (d / "macros.yaml").write_text(
            f"- PG_MAJOR_VERSION: {major}\n"
            f"- PG_MINOR_VERSION: {minor}\n"
            "- PG_VERSION: %!{PG_MAJOR_VERSION}.%!{PG_MINOR_VERSION}\n"
            f"- PGAUDIT_VERSION: {major}.0\n"
        )
        (d / "project.yaml").write_text(qa)
    monkeypatch.setattr(common, "REPO_ROOT", root)


def _show(project, capsys):
    args = SimpleNamespace(
        project=project, rootprj="isv:percona", env_overrides=[], json=True
    )
    cmd_qa.cmd_qa_show(args)
    return {r["name"]: r["params"] for r in json.loads(capsys.readouterr().out)}


_ROOT = "- PGBACKREST_VERSION: 2.59.2\n- PATRONI_VERSION: 4.1.5\n- PGBOUNCER_TAG: pgbouncer_1_26_0\n"


def test_versions_are_added_resolved_and_sorted(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch, root_macros=_ROOT)
    server = _show("ppg:staging:18", capsys)["server"]
    lines = server["EXPECTED_VERSIONS"].split("\n")
    assert lines == sorted(lines)
    for expected in (
        "PATRONI_VERSION=4.1.5",
        "PGAUDIT_VERSION=18.0",
        "PGBACKREST_VERSION=2.59.2",
        "PG_VERSION=18.6",
    ):
        assert expected in lines
    # tool-computed macros are included too, resolved for this project
    assert "PG_PREV_MAJOR_VERSION=17" in lines
    assert server["VERSION"] == "ppg-18.6"


def test_only_version_macros_are_sent(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch, root_macros=_ROOT)
    server = _show("ppg:staging:18", capsys)["server"]
    assert "PGBOUNCER_TAG" not in server["EXPECTED_VERSIONS"]


def test_values_follow_the_project(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch, root_macros=_ROOT)
    lines = _show("ppg:staging:17", capsys)["server"]["EXPECTED_VERSIONS"].split("\n")
    assert "PG_VERSION=17.11" in lines and "PGAUDIT_VERSION=17.0" in lines


def test_entry_value_wins(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch, root_macros=_ROOT)
    assert (
        _show("ppg:staging:18", capsys)["pinned"]["EXPECTED_VERSIONS"]
        == "PGBACKREST_VERSION=1.0"
    )


def test_nothing_added_without_version_macros(monkeypatch):
    monkeypatch.setattr(cmd_qa, "_expected_versions", lambda project: "")
    entries = [{"name": "x", "pipeline": "p", "parameters": {"A": "1"}}]
    assert cmd_qa._with_expected_versions(entries, "any") is entries


def test_no_entries_stays_none():
    assert cmd_qa._with_expected_versions(None, "any") is None


def test_qa_run_dry_run_shows_it(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch, root_macros=_ROOT)
    args = SimpleNamespace(
        project="ppg:staging:18",
        rootprj="isv:percona",
        env_overrides=[],
        profile=None,
        name="server",
        pipeline=None,
        filter=[],
        param=[],
        dry_run=True,
        wait=False,
        report_json=None,
        run_id=None,
        running=False,
        include_aborted=False,
    )
    cmd_qa.cmd_qa_run(args)
    out = capsys.readouterr().out
    assert "EXPECTED_VERSIONS" in out and "PGBACKREST_VERSION=2.59.2" in out
