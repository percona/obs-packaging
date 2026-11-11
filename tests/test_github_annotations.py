import sys

import pytest

from percona_obs import cli, cmd_qa, qa_state
from percona_obs.common import github_annotation


def test_annotation_noop_outside_actions(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    github_annotation("notice", "x")
    assert capsys.readouterr().out == ""


def test_annotation_formats(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    github_annotation("notice", "p u", title="Jenkins build")
    github_annotation("error", "a\nb 50%")
    assert capsys.readouterr().out == (
        "::notice title=Jenkins build::p u\n::error::a%0Ab 50%25\n"
    )


def test_annotation_encodes_carriage_return(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    github_annotation("error", "a\rb")
    assert capsys.readouterr().out == "::error::a%0Db\n"


def test_jenkins_notice_once_per_process(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(cmd_qa, "_jenkins_notice_emitted", False)
    cmd_qa._emit_jenkins_notice("ppg:releases:18", "https://j/job/x/1/")
    cmd_qa._emit_jenkins_notice("ppg:releases:18", "https://j/job/x/2/")
    assert capsys.readouterr().out.splitlines() == [
        "::notice title=Jenkins build::ppg:releases:18 https://j/job/x/1/"
    ]


def test_wait_and_record_emits_notice(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(cmd_qa, "_jenkins_notice_emitted", False)
    monkeypatch.setattr(cmd_qa, "wait_for_start", lambda cfg, q, t: "https://j/1/")
    monkeypatch.setattr(cmd_qa, "wait_for_finish", lambda cfg, u, t: "SUCCESS")
    monkeypatch.setattr(cmd_qa, "save_state", lambda s: None)
    state = qa_state.RunState(
        run_id="r1",
        project="ppg:releases:18:containers",
        pipeline="x",
        created_at="t",
        combos=[
            qa_state.Combo(
                label="a",
                params={},
                attempts=[qa_state.Attempt(triggered_at="t", queue_url="q")],
            )
        ],
    )
    cmd_qa._wait_and_record(None, state, {"a": "q"})  # type: ignore[arg-type]
    out = capsys.readouterr().out.splitlines()
    assert (
        "::notice title=Jenkins build::ppg:releases:18:containers https://j/1/" in out
    )


def _run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["percona-obs", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value


def test_main_annotates_string_exit(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    exc = _run_main(monkeypatch, ["project", "release", "ppg:nope:1"])
    assert isinstance(exc.code, str)
    assert (
        "::error::ppg:nope:1: project release requires a staging-tier source"
        in capsys.readouterr().out
    )


def test_main_does_not_annotate_outside_actions(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _run_main(monkeypatch, ["project", "release", "ppg:nope:1"])
    assert "::error::" not in capsys.readouterr().out
