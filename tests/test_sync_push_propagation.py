"""sync push hands uploads to the propagator and reports frozen projects."""

from types import SimpleNamespace

import pytest

from percona_obs import cmd_sync as cs


@pytest.fixture
def spy(monkeypatch):
    calls: list = []
    queries: list = []
    frozen: dict = {}

    def fake_propagate(apiurl, rootprj, seeds, targets, env_vars, dry_run):
        calls.append((set(seeds), dry_run))

    def fake_frozen(apiurl, projects):
        queries.append(set(projects))
        return {p: s for p, s in frozen.items() if p in projects}

    monkeypatch.setattr(cs.propagate_mod, "propagate", fake_propagate)
    monkeypatch.setattr(cs.unit_freeze, "frozen_projects", fake_frozen)
    return SimpleNamespace(calls=calls, queries=queries, frozen=frozen)


def args(branch_from=None):
    return SimpleNamespace(branch_from=branch_from, rootprj="r")


def test_calls_propagate_with_uploaded_seeds(spy):
    cs._propagate_after_push(
        "api", args(), ["r:u/a", "r:deps/lib"], set(), [], {}, False
    )
    assert spy.calls == [({("r:u", "a"), ("r:deps", "lib")}, False)]


def test_dry_run_passed_through(spy):
    cs._propagate_after_push("api", args(), ["r:u/a"], set(), [], {}, True)
    assert spy.calls == [({("r:u", "a")}, True)]


def test_skipped_for_branch_from(spy):
    cs._propagate_after_push(
        "api", args(branch_from="main"), ["r:u/a"], {"r:u"}, [], {}, False
    )
    assert spy.calls == [] and spy.queries == []


def test_skipped_when_nothing_uploaded_and_no_config_change(spy):
    cs._propagate_after_push("api", args(), [], set(), [], {}, False)
    assert spy.calls == [] and spy.queries == []


def test_warns_on_config_change_in_frozen_project(spy, capsys):
    spy.frozen["r:u"] = "frozen"
    cs._propagate_after_push("api", args(), [], {"r:u", "r:x"}, [], {}, False)
    out = capsys.readouterr().out
    assert "warning: r:u is frozen" in out and "r:x" not in out
    assert "run 'build propagate' or unfreeze" in out
    assert spy.calls == []


def test_partial_state_is_not_frozen(spy, capsys):
    spy.frozen["r:u"] = "partial"
    cs._propagate_after_push("api", args(), ["r:u/a"], {"r:u"}, [], {}, False)
    assert "frozen" not in capsys.readouterr().out


def test_notice_for_upload_into_frozen_project(spy, capsys):
    spy.frozen["r:u"] = "frozen"
    cs._propagate_after_push("api", args(), ["r:u/a", "r:v/b"], set(), [], {}, False)
    out = capsys.readouterr().out
    assert "r:u  frozen (rebuild=local): dependents are rebuilt by the tool" in out
    assert "r:v" not in out
    assert spy.queries == [{"r:u", "r:v"}]
