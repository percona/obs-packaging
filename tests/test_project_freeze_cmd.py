"""Tests for the project freeze / unfreeze / freeze-status commands."""

import pytest

from percona_obs import cli, cmd_project, unit_freeze


@pytest.fixture(autouse=True)
def _fake_osc(monkeypatch):
    monkeypatch.setitem(cmd_project.osc.conf.config, "apiurl", "https://obs.example")
    # Never read a real oscrc in tests.
    monkeypatch.setattr(cmd_project.osc.conf, "get_config", lambda **_kw: None)


def _run(argv):
    args = cli.build_parser().parse_args(argv)
    args.func(args)


def test_freeze_prints_one_line_per_project(monkeypatch, capsys):
    monkeypatch.setattr(unit_freeze, "unit_obs_projects", lambda u, r: [f"r:{u}"])
    monkeypatch.setattr(
        unit_freeze,
        "apply_freeze",
        lambda *a: [
            ("r:ppg:staging:18", "changed"),
            ("r:ppg:staging:18:containers", "absent"),
        ],
    )
    _run(["-R", "r", "project", "freeze", "ppg:staging:18"])
    out = capsys.readouterr().out
    assert "r:ppg:staging:18  frozen" in out
    assert "r:ppg:staging:18:containers  absent" in out


def test_unfreeze_unchanged_wording(monkeypatch, capsys):
    monkeypatch.setattr(unit_freeze, "unit_obs_projects", lambda u, r: [f"r:{u}"])
    monkeypatch.setattr(
        unit_freeze, "apply_freeze", lambda *a: [("r:ppg:staging:18", "unchanged")]
    )
    _run(["-R", "r", "project", "unfreeze", "ppg:staging:18"])
    assert "already unfrozen" in capsys.readouterr().out


@pytest.mark.parametrize(
    "command, frozen, dry_run",
    [
        ("freeze", True, True),
        ("freeze", True, False),
        ("unfreeze", False, True),
        ("unfreeze", False, False),
    ],
)
def test_dry_run_reaches_apply_freeze(monkeypatch, command, frozen, dry_run):
    monkeypatch.setattr(unit_freeze, "unit_obs_projects", lambda u, r: [f"r:{u}"])
    calls = []
    monkeypatch.setattr(unit_freeze, "apply_freeze", lambda *a: calls.append(a) or [])
    argv = ["-R", "r", "project", command, "ppg:staging:18"]
    _run(argv + (["--dry-run"] if dry_run else []))
    assert calls == [("https://obs.example", ["r:ppg:staging:18"], frozen, dry_run)]


def test_invalid_unit_makes_no_call(monkeypatch):
    apply_calls = []

    def fake_projects(unit, rootprj):
        if unit == "bad":
            raise ValueError("bad is not a release unit")
        return [f"r:{unit}"]

    monkeypatch.setattr(unit_freeze, "unit_obs_projects", fake_projects)
    monkeypatch.setattr(
        unit_freeze, "apply_freeze", lambda *a: apply_calls.append(a) or []
    )
    with pytest.raises(SystemExit) as e:
        _run(["-R", "r", "project", "freeze", "ppg:staging:18", "bad"])
    assert e.value.code != 0 and apply_calls == []
    assert "bad" in str(e.value.code)


def _status_setup(monkeypatch, states):
    monkeypatch.setattr(
        cmd_project,
        "list_release_units",
        lambda: [
            {"unit": u} for u in ("ppg:staging:18", "ppg:staging:17", "ppg:staging:16")
        ],
    )
    monkeypatch.setattr(unit_freeze, "unit_obs_projects", lambda u, r: [f"r:{u}"])
    monkeypatch.setattr(
        unit_freeze,
        "frozen_projects",
        lambda apiurl, projs: {p: states[p] for p in projs if p in states},
    )


def test_freeze_status_github_warning(monkeypatch, capsys):
    _status_setup(
        monkeypatch,
        {
            "r:ppg:staging:18": "frozen",
            "r:ppg:staging:17": "unfrozen",
            "r:ppg:staging:16": "partial",
        },
    )
    _run(["-R", "r", "project", "freeze-status", "--github-warning"])
    out = capsys.readouterr().out
    assert "::warning::" in out and "ppg:staging:18" in out
    assert "ppg:staging:16 (partial)" in out
    assert "ppg:staging:17" not in out


def test_freeze_status_silent_when_nothing_frozen(monkeypatch, capsys):
    _status_setup(monkeypatch, {"r:ppg:staging:17": "unfrozen"})
    _run(["-R", "r", "project", "freeze-status", "--github-warning"])
    out = capsys.readouterr().out
    assert "::warning::" not in out and out == ""


def _fake_get_config(monkeypatch):
    """Replace osc.conf.get_config with a recorder that loads a known apiurl.

    The `project` command group is skipped by main()'s osc configuration, so
    each subcommand that talks to OBS must load the credentials itself.
    """
    calls = []

    def fake(override_apiurl=None, **_kw):
        calls.append(override_apiurl)
        cmd_project.osc.conf.config["apiurl"] = "https://loaded.example"

    monkeypatch.setattr(cmd_project.osc.conf, "get_config", fake)
    return calls


@pytest.mark.parametrize("action", ["freeze", "unfreeze"])
def test_freeze_loads_osc_config_before_obs_calls(monkeypatch, action):
    calls = _fake_get_config(monkeypatch)
    monkeypatch.setattr(unit_freeze, "unit_obs_projects", lambda u, r: [f"r:{u}"])
    seen = []
    monkeypatch.setattr(
        unit_freeze, "apply_freeze", lambda api, *a: seen.append(api) or []
    )
    _run(["-A", "https://cli.example", "-R", "r", "project", action, "ppg:staging:18"])
    assert calls == ["https://cli.example"]
    assert seen == ["https://loaded.example"]


def test_freeze_invalid_unit_does_not_need_osc_config(monkeypatch):
    calls = _fake_get_config(monkeypatch)

    def bad(unit, rootprj):
        raise ValueError("not a release unit root")

    monkeypatch.setattr(unit_freeze, "unit_obs_projects", bad)
    with pytest.raises(SystemExit):
        _run(["-R", "r", "project", "freeze", "nope"])
    assert calls == []


def test_freeze_status_loads_osc_config_before_obs_calls(monkeypatch):
    calls = _fake_get_config(monkeypatch)
    monkeypatch.setattr(
        cmd_project, "list_release_units", lambda: [{"unit": "ppg:staging:18"}]
    )
    monkeypatch.setattr(unit_freeze, "unit_obs_projects", lambda u, r: [f"r:{u}"])
    seen = []
    monkeypatch.setattr(
        unit_freeze, "frozen_projects", lambda api, prjs: seen.append(api) or {}
    )
    _run(["-A", "https://cli.example", "-R", "r", "project", "freeze-status"])
    assert calls == ["https://cli.example"]
    assert seen == ["https://loaded.example"]
