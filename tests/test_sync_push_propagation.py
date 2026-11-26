"""sync push hands uploads to the propagator and reports frozen projects."""

from types import SimpleNamespace

import pytest

from percona_obs import cmd_sync as cs


@pytest.fixture
def spy(monkeypatch):
    from percona_obs import cmd_build

    monkeypatch.setattr(cmd_build, "_propagate_targets", lambda a, env: [])
    calls: list = []
    queries: list = []
    frozen: dict = {}
    rerun: list = []

    def fake_propagate(apiurl, rootprj, seeds, targets, env_vars, dry_run, **kw):
        calls.append((set(seeds), dry_run))
        rerun.append(kw)

    def fake_frozen(apiurl, projects):
        queries.append(set(projects))
        return {p: s for p, s in frozen.items() if p in projects}

    monkeypatch.setattr(cs.propagate_mod, "propagate", fake_propagate)
    monkeypatch.setattr(cs.unit_freeze, "frozen_projects", fake_frozen)
    return SimpleNamespace(calls=calls, queries=queries, frozen=frozen, rerun=rerun)


def args(branch_from=None, profile=None, env_overrides=None):
    return SimpleNamespace(
        branch_from=branch_from,
        rootprj="r",
        profile=profile,
        env_overrides=env_overrides or [],
    )


def test_calls_propagate_with_uploaded_seeds(spy):
    cs._propagate_after_push("api", args(), ["r:u/a", "r:deps/lib"], set(), {}, False)
    assert spy.calls == [({("r:u", "a"), ("r:deps", "lib")}, False)]


def test_rerun_flags_passed_through(spy):
    cs._propagate_after_push(
        "api",
        args(profile="labs", env_overrides=["K:V"]),
        ["r:u/a"],
        set(),
        {},
        False,
    )
    assert spy.rerun == [{"env_overrides": ["K:V"], "profile": "labs"}]


def test_dry_run_passed_through(spy):
    cs._propagate_after_push("api", args(), ["r:u/a"], set(), {}, True)
    assert spy.calls == [({("r:u", "a")}, True)]


def test_skipped_for_branch_from(spy):
    cs._propagate_after_push(
        "api", args(branch_from="main"), ["r:u/a"], {"r:u"}, {}, False
    )
    assert spy.calls == [] and spy.queries == []


def test_skipped_when_nothing_uploaded_and_no_config_change(spy):
    cs._propagate_after_push("api", args(), [], set(), {}, False)
    assert spy.calls == [] and spy.queries == []


def test_warns_on_config_change_in_frozen_project(spy, capsys):
    spy.frozen["r:u"] = "frozen"
    cs._propagate_after_push("api", args(), [], {"r:u", "r:x"}, {}, False)
    out = capsys.readouterr().out
    assert "warning: r:u is frozen" in out and "r:x" not in out
    assert "run 'build propagate' or unfreeze" in out
    assert spy.calls == []


def test_partial_state_is_not_frozen(spy, capsys):
    spy.frozen["r:u"] = "partial"
    cs._propagate_after_push("api", args(), ["r:u/a"], {"r:u"}, {}, False)
    assert "frozen" not in capsys.readouterr().out


def test_notice_for_upload_into_frozen_project(spy, capsys):
    spy.frozen["r:u"] = "frozen"
    cs._propagate_after_push("api", args(), ["r:u/a", "r:v/b"], set(), {}, False)
    out = capsys.readouterr().out
    assert "r:u  frozen (rebuild=local): dependents are rebuilt by the tool" in out
    assert "r:v" not in out
    assert spy.queries == [{"r:u", "r:v"}]


# --- F1/F3: failure tail -------------------------------------------------


def test_finish_push_writes_manifest_and_report_when_propagation_exits(capsys):
    order: list[str] = []

    def boom():
        raise SystemExit("OBS api error")

    with pytest.raises(SystemExit) as exc:
        cs._finish_push(
            boom,
            lambda: order.append("manifest"),
            lambda: order.append("report"),
            "percona-obs build propagate r:u/a",
        )
    assert exc.value.code != 0
    assert order == ["manifest", "report"]
    out = capsys.readouterr().out
    assert "OBS api error" in out and "percona-obs build propagate r:u/a" in out


def test_finish_push_plain_exception_exits_nonzero(capsys):
    def boom():
        raise RuntimeError("x")

    with pytest.raises(SystemExit) as exc:
        cs._finish_push(boom, lambda: None, lambda: None, "cmd")
    assert exc.value.code == 1


def test_finish_push_lets_keyboard_interrupt_through():
    def boom():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        cs._finish_push(boom, lambda: None, lambda: None, "cmd")


def test_finish_push_success_returns(capsys):
    order: list[str] = []
    cs._finish_push(
        lambda: order.append("p"),
        lambda: order.append("m"),
        lambda: order.append("r"),
        "cmd",
    )
    assert order == ["p", "m", "r"]


def test_push_recovery_command_names_uploaded_packages():
    a = SimpleNamespace(
        rootprj="r", env_overrides=["A=1"], profile="labs", branch_from=None
    )
    cmd = cs._push_recovery_command("api", a, ["r:u/a", "r:v/b"])
    assert cmd.startswith("percona-obs -P labs -A api -R r -e A=1 build propagate")
    assert "r:u/a" in cmd and "r:v/b" in cmd


# --- F2: targets independent of sync scope -------------------------------


def test_propagate_gets_full_slice_targets(spy, monkeypatch):
    from percona_obs import cmd_build

    full = [("r:u", "PATH")]
    monkeypatch.setattr(cmd_build, "_propagate_targets", lambda a, env: full)
    got: list = []
    monkeypatch.setattr(cs.propagate_mod, "propagate", lambda *a, **k: got.append(a[3]))
    cs._propagate_after_push("api", args(), ["r:u/a"], set(), {}, False)
    assert got == [full]


# --- F4: --project-only warns without propagating -----------------------


def test_project_only_style_call_warns_without_propagating(spy, capsys):
    spy.frozen["r:u"] = "frozen"
    cs._propagate_after_push("api", args(), [], {"r:u"}, {}, True)
    assert "warning: r:u is frozen" in capsys.readouterr().out
    assert spy.calls == []
