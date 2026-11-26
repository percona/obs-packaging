# tests/test_propagate_run.py
"""Unit tests for running a propagation plan against OBS.

No OBS traffic: release_freeze.fetch_project_results, the _jobhistory and
source-info GETs and http_POST are faked; wait_seen gets fake sleep and
clock callables so no real time passes.
"""

import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest

from percona_obs import cli, cmd_build
import percona_obs.propagate as pp
from percona_obs.propagate import Stage

API = "https://obs.example"


class _Resp:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


class FakeObs:
    """Canned build results, job histories and source md5s."""

    def __init__(self, monkeypatch):
        self.codes: dict[str, dict[tuple[str, str, str], str]] = {}
        # (project, repo, arch, package) -> list of (readytime, srcmd5)
        self.jobs: dict[tuple[str, str, str, str], list[tuple[str, str]]] = {}
        # (project, package) -> (srcmd5, verifymd5 or None)
        self.source: dict[tuple[str, str], tuple[str, "str | None"]] = {}
        self.absent: set[str] = set()
        self.posts: list[str] = []
        self.gets: list[str] = []
        monkeypatch.setattr(
            pp.release_freeze, "fetch_project_results", self.fetch_results
        )
        monkeypatch.setattr(pp.osc.connection, "http_GET", self.http_get)
        monkeypatch.setattr(
            pp.osc.connection,
            "http_POST",
            lambda url, *a, **kw: self.posts.append(url) or _Resp(b"<status/>"),
        )

    def fetch_results(self, apiurl, project):
        if project in self.absent:
            raise urllib.error.HTTPError(project, 404, "not found", {}, None)  # type: ignore[arg-type]
        return self.codes.get(project, {}), {}

    def http_get(self, url, *a, **kw):
        self.gets.append(url)
        parts = urlsplit(url)
        path = parts.path.strip("/").split("/")
        query = parse_qs(parts.query)
        if path[0] == "build" and path[-1] == "_jobhistory":
            prj, repo, arch = path[1], path[2], path[3]
            pkg = query["package"][0]
            entries = self.jobs.get((prj, repo, arch, pkg), [])[-1:]
            body = "".join(
                f'<jobhist package="{pkg}" readytime="{rt}" srcmd5="{md5}" code="succeeded"/>'
                for rt, md5 in entries
            )
            return _Resp(f"<jobhistlist>{body}</jobhistlist>".encode())
        if path[0] == "source":
            prj, pkg = path[1], path[2]
            srcmd5, verifymd5 = self.source[(prj, pkg)]
            verify = f' verifymd5="{verifymd5}"' if verifymd5 else ""
            return _Resp(
                f'<sourceinfo package="{pkg}" srcmd5="{srcmd5}"{verify}/>'.encode()
            )
        raise AssertionError(f"unexpected GET {url}")


@pytest.fixture
def obs(monkeypatch):
    return FakeObs(monkeypatch)


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = 0

    def clock(self):
        return self.now

    def sleep(self, s):
        self.sleeps += 1
        self.now += s


# ---------------------------------------------------------------------------
# trigger_rebuild


def test_trigger_chunks(obs):
    pp.trigger_rebuild(API, "P", [f"p{i}" for i in range(120)])
    assert [len(parse_qs(urlsplit(u).query)["package"]) for u in obs.posts] == [
        50,
        50,
        20,
    ]
    assert all("cmd=rebuild" in u for u in obs.posts)
    assert all(urlsplit(u).path == "/build/P" for u in obs.posts)


# ---------------------------------------------------------------------------
# wait_seen


def test_seen_when_pending_on_all_built_targets(obs):
    obs.codes["P"] = {
        ("a", "R1", "x86_64"): "building",
        ("a", "R2", "x86_64"): "excluded",
    }
    assert pp.wait_seen(API, {("P", "a")}, since={}) == set()
    assert obs.gets == []  # pending needs no job history


def test_seen_when_jobhistory_moved(obs):
    obs.codes["P"] = {("a", "R1", "x86_64"): "succeeded"}
    obs.jobs[("P", "R1", "x86_64", "a")] = [("6", "m"), ("7", "m")]
    since = pp.record_since(API, {("P", "a")})
    obs.jobs[("P", "R1", "x86_64", "a")] = [("6", "m")]
    assert pp.wait_seen(API, {("P", "a")}, since={("P", "a"): {}}) == set()
    obs.jobs[("P", "R1", "x86_64", "a")] = [("6", "m"), ("7", "m"), ("8", "m")]
    assert pp.wait_seen(API, {("P", "a")}, since=since) == set()


def test_timeout_returns_unseen(obs):
    obs.codes["P"] = {("a", "R1", "x86_64"): "succeeded"}
    obs.jobs[("P", "R1", "x86_64", "a")] = [("7", "m")]
    since = pp.record_since(API, {("P", "a")})
    t = FakeTime()
    unseen = pp.wait_seen(
        API, {("P", "a")}, since=since, timeout_s=6, sleep=t.sleep, clock=t.clock
    )
    assert unseen == {("P", "a")}
    assert t.sleeps == 3 and t.now == 6


def test_seen_needs_every_target(obs):
    obs.codes["P"] = {
        ("a", "R1", "x86_64"): "scheduled",
        ("a", "R1", "aarch64"): "succeeded",
    }
    obs.jobs[("P", "R1", "aarch64", "a")] = [("7", "m")]
    since = pp.record_since(API, {("P", "a")})
    t = FakeTime()
    assert pp.wait_seen(
        API, {("P", "a")}, since=since, timeout_s=4, sleep=t.sleep, clock=t.clock
    ) == {("P", "a")}


def test_target_seen_once_stays_seen(obs):
    # Poll 1: x86_64 pending (seen), aarch64 still on the old source.
    obs.codes["P"] = {
        ("a", "R1", "x86_64"): "building",
        ("a", "R1", "aarch64"): "succeeded",
    }
    obs.jobs[("P", "R1", "x86_64", "a")] = [("7", "old")]
    obs.jobs[("P", "R1", "aarch64", "a")] = [("7", "old")]
    obs.source[("P", "a")] = ("new", None)
    t = FakeTime()

    def sleep(s):
        t.sleep(s)
        # Poll 2: aarch64 pending; x86_64 no longer is but was seen before.
        obs.codes["P"] = {
            ("a", "R1", "x86_64"): "failed",
            ("a", "R1", "aarch64"): "scheduled",
        }

    assert pp.wait_seen(API, {("P", "a")}, since={}, sleep=sleep, clock=t.clock) == (
        set()
    )
    assert t.sleeps == 1


def test_seed_seen_when_newest_job_built_current_source(obs):
    obs.codes["P"] = {("s", "R1", "x86_64"): "succeeded"}
    obs.jobs[("P", "R1", "x86_64", "s")] = [("7", "new")]
    obs.source[("P", "s")] = ("new", None)
    assert pp.wait_seen(API, {("P", "s")}, since={}) == set()


def test_seed_prefers_verifymd5(obs):
    obs.codes["P"] = {("s", "R1", "x86_64"): "succeeded"}
    obs.jobs[("P", "R1", "x86_64", "s")] = [("7", "expanded")]
    obs.source[("P", "s")] = ("unexpanded", "expanded")
    assert pp.wait_seen(API, {("P", "s")}, since={}) == set()


def test_seed_not_seen_while_newest_job_is_old_source(obs):
    obs.codes["P"] = {("s", "R1", "x86_64"): "succeeded"}
    obs.jobs[("P", "R1", "x86_64", "s")] = [("7", "old")]
    obs.source[("P", "s")] = ("new", None)
    t = FakeTime()
    assert pp.wait_seen(
        API, {("P", "s")}, since={}, timeout_s=2, sleep=t.sleep, clock=t.clock
    ) == {("P", "s")}


def test_package_without_built_targets_is_seen(obs):
    obs.codes["P"] = {
        ("a", "R1", "x86_64"): "excluded",
        ("a", "R2", "x86_64"): "disabled",
    }
    obs.absent.add("Q")
    assert pp.wait_seen(API, {("P", "a"), ("P", "gone"), ("Q", "b")}, since={}) == (
        set()
    )


def test_record_since_fails_loudly(obs, monkeypatch):
    def boom(apiurl, project):
        raise urllib.error.HTTPError(project, 500, "error", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(pp.release_freeze, "fetch_project_results", boom)
    with pytest.raises(urllib.error.HTTPError):
        pp.record_since(API, {("P", "a")})


def test_multibuild_flavors_are_targets(obs):
    obs.codes["P"] = {
        ("a", "R1", "x86_64"): "building",
        ("a:docs", "R1", "x86_64"): "succeeded",
    }
    obs.jobs[("P", "R1", "x86_64", "a:docs")] = [("7", "m")]
    since = pp.record_since(API, {("P", "a")})
    t = FakeTime()
    assert pp.wait_seen(
        API, {("P", "a")}, since=since, timeout_s=2, sleep=t.sleep, clock=t.clock
    ) == {("P", "a")}


# ---------------------------------------------------------------------------
# run_stages


@pytest.fixture
def events(monkeypatch):
    log: list[str] = []
    unseen: dict[frozenset, set] = {}

    def fake_wait(apiurl, pkgs, since, **kw):
        log.append("wait:" + ",".join(sorted(n for _, n in pkgs)))
        log.append("since:" + ",".join(sorted(f"{p}/{n}" for p, n in since)))
        return unseen.get(frozenset(pkgs), set())

    def fake_record(apiurl, pkgs):
        log.append("record:" + ",".join(sorted(f"{p}/{n}" for p, n in pkgs)))
        return {p: {} for p in pkgs}

    monkeypatch.setattr(pp, "wait_seen", fake_wait)
    monkeypatch.setattr(pp, "record_since", fake_record)
    monkeypatch.setattr(
        pp,
        "trigger_rebuild",
        lambda apiurl, prj, pkgs: log.append(f"trigger:{prj}:{','.join(pkgs)}"),
    )
    log_obj = type("E", (), {})()
    log_obj.log = log  # type: ignore[attr-defined]
    log_obj.unseen = unseen  # type: ignore[attr-defined]
    return log_obj


STAGES = [
    Stage(frozenset({("P", "a")}), {"P": ["b"]}),
    Stage(frozenset({("P", "b")}), {"Q": ["img"]}),
]


def test_run_stages_orders_wait_then_trigger(events):
    pp.run_stages(API, STAGES, dry_run=False)
    assert [e for e in events.log if not e.startswith("since:")] == [
        "wait:a",
        "record:P/b",
        "trigger:P:b",
        "wait:b",
        "record:Q/img",
        "trigger:Q:img",
    ]
    # The second wait sees the record taken before b was triggered.
    assert events.log[events.log.index("wait:b") + 1] == "since:P/b"


def test_run_stages_triggers_every_project_of_a_stage(events):
    stages = [Stage(frozenset({("P", "a")}), {"P": ["b"], "Q": ["t"]})]
    pp.run_stages(API, stages, dry_run=False)
    assert "trigger:P:b" in events.log and "trigger:Q:t" in events.log
    assert "record:P/b,Q/t" in events.log


def test_run_stages_keeps_given_since(events):
    pp.run_stages(API, STAGES[:1], dry_run=False, since={("D", "mid"): {}})
    assert events.log[1] == "since:D/mid"


def test_run_stages_continues_after_timeout(capsys, events):
    events.unseen[frozenset({("P", "a")})] = {("P", "a")}
    pp.run_stages(API, STAGES, dry_run=False)
    out = capsys.readouterr().out
    assert "trigger:P:b" in events.log and "trigger:Q:img" in events.log
    assert "not seen" in out and "P/a" in out


def test_dry_run_sends_nothing(capsys, obs, monkeypatch):
    monkeypatch.setattr(
        pp, "wait_seen", lambda *a, **k: pytest.fail("dry run must not wait")
    )
    pp.run_stages(API, STAGES, dry_run=True)
    out = capsys.readouterr().out
    assert obs.posts == [] and obs.gets == []
    assert "P: b" in out and "Q: img" in out and "P/a" in out


# ---------------------------------------------------------------------------
# propagate


R, C, D = "r:u", "r:u:containers", "r:deps"


@pytest.fixture
def prop(monkeypatch):
    """Fake every OBS-facing piece propagate composes."""
    st = type("S", (), {})()
    st.states = {R: "frozen", C: "frozen"}  # type: ignore[attr-defined]
    st.paths = {R: {D}, C: {R}, D: set()}  # type: ignore[attr-defined]
    st.fwd = {(R, "b"): {(D, "lib")}, (C, "img"): {(R, "b")}}  # type: ignore[attr-defined]
    st.fail = set()  # type: ignore[attr-defined]
    st.absent = set()  # type: ignore[attr-defined]
    st.depinfo_calls = []  # type: ignore[attr-defined]
    st.run = []  # type: ignore[attr-defined]
    st.recorded = []  # type: ignore[attr-defined]

    monkeypatch.setattr(
        pp, "list_release_units", lambda: [{"unit": "u"}, {"unit": "v"}]
    )
    monkeypatch.setattr(
        pp, "unit_obs_projects", lambda unit, rootprj: [f"r:{unit}", f"r:{unit}:x"]
    )
    monkeypatch.setattr(
        pp,
        "frozen_projects",
        lambda apiurl, projs: {p: s for p, s in st.states.items()},  # type: ignore[attr-defined]
    )

    def fake_paths(apiurl, prj):
        return st.paths.get(prj, set())  # type: ignore[attr-defined]

    monkeypatch.setattr(pp, "_project_path_projects", fake_paths)
    monkeypatch.setattr(
        pp,
        "_project_exists",
        lambda apiurl, prj: prj not in st.absent,  # type: ignore[attr-defined]
    )

    def fake_depinfo(apiurl, projects, local, image_pkgs=None, **kw):
        st.depinfo_calls.append((set(projects), kw))  # type: ignore[attr-defined]
        if kw.get("failed") is not None:
            kw["failed"].update(st.fail)  # type: ignore[attr-defined]
        return {k: set(v) for k, v in st.fwd.items()}  # type: ignore[attr-defined]

    monkeypatch.setattr(pp, "_fetch_combined_depinfo", fake_depinfo)
    monkeypatch.setattr(pp, "aggregate_edges", lambda targets, env: {})
    monkeypatch.setattr(
        pp,
        "_fetch_obs_package_names_or_fail",
        lambda apiurl, prj: {"b", "z"} if prj == R else {"img"},
    )
    monkeypatch.setattr(
        pp,
        "record_since",
        lambda apiurl, pkgs: st.recorded.append(set(pkgs)) or {p: {} for p in pkgs},  # type: ignore[attr-defined]
    )

    def fake_run(apiurl, stages, dry_run, *, since=None, **kw):
        print("RUN")
        st.run.append((stages, dry_run, since))  # type: ignore[attr-defined]

    monkeypatch.setattr(pp, "run_stages", fake_run)
    return st


def test_propagate_nothing_frozen_queries_no_dependencies(prop, capsys):
    prop.states = {R: "partial", C: "unfrozen"}
    pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=False)
    assert prop.depinfo_calls == [] and prop.run == []


def test_propagate_runs_plan_over_seed_and_upstream_projects(prop, capsys):
    pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=False)
    projects, kw = prop.depinfo_calls[0]
    assert projects == {R, C, D}
    assert kw["all_targets"] is True
    stages, dry_run, since = prop.run[0]
    assert [s.trigger for s in stages] == [{R: ["b"]}, {C: ["img"]}]
    assert dry_run is False
    out = capsys.readouterr().out
    assert "percona-obs build propagate r:deps/lib" in out
    assert out.index("build propagate") < out.index("RUN")
    assert "r:deps/lib" in out.split("build propagate")[0]  # seeds printed


def test_propagate_records_non_frozen_members_before_running(prop):
    prop.paths = {R: {D}, D: set(), C: {R}}
    prop.fwd = {(D, "mid"): {(D, "lib")}, (R, "b"): {(D, "mid")}}
    pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=False)
    assert prop.recorded == [{(D, "mid")}]
    assert prop.run[0][2] == {(D, "mid"): {}}


def test_propagate_empty_plan_says_so(prop, capsys):
    prop.fwd = {}
    pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=False)
    assert prop.run == []
    assert "nothing in a frozen project depends" in capsys.readouterr().out


def test_propagate_failed_frozen_project_triggers_all_of_it(prop):
    prop.fwd = {}
    prop.fail = {R}
    pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=False)
    stages = prop.run[0][0]
    assert {n for s in stages for n in s.trigger.get(R, [])} == {"b", "z"}
    # C consumes R, so it is expanded too.
    assert {n for s in stages for n in s.trigger.get(C, [])} == {"img"}


def test_propagate_absent_project_is_not_a_failure(prop):
    prop.absent = {"r:other"}
    prop.fwd = {}
    pp.propagate(API, "r", {("r:other", "x")}, [], {}, dry_run=False)
    projects, _ = prop.depinfo_calls[0]
    assert "r:other" not in projects
    assert prop.run == []


def test_propagate_dry_run_records_nothing(prop, capsys):
    prop.paths = {R: {D}, D: set(), C: {R}}
    prop.fwd = {(D, "mid"): {(D, "lib")}, (R, "b"): {(D, "mid")}}
    pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=True)
    assert prop.recorded == []
    assert prop.run[0][1] is True
    assert "build propagate" not in capsys.readouterr().out


def test_propagate_prints_recovery_before_dependency_queries(prop, capsys, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("depinfo down")

    monkeypatch.setattr(pp, "_fetch_combined_depinfo", boom)
    with pytest.raises(RuntimeError):
        pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=False)
    assert "percona-obs build propagate r:deps/lib" in capsys.readouterr().out


def test_project_order_puts_paths_first():
    order = pp._project_order({C: {R}, R: {D}, D: set(), "r:x": set()})
    assert order.index(D) < order.index(R) < order.index(C)


# ---------------------------------------------------------------------------
# build propagate


def test_cli_build_propagate(monkeypatch):
    monkeypatch.setitem(cmd_build.osc.conf.config, "apiurl", API)
    calls = []
    monkeypatch.setattr(cmd_build, "_propagate_targets", lambda args, env: [])
    monkeypatch.setattr(
        pp,
        "propagate",
        lambda apiurl, rootprj, seeds, targets, env, dry_run: calls.append(
            (apiurl, rootprj, seeds, dry_run)
        ),
    )
    args = cli.build_parser().parse_args(
        ["-R", "r", "build", "propagate", "r:u/a", "r:deps/lib", "--dry-run"]
    )
    args.func(args)
    assert calls == [(API, "r", {("r:u", "a"), ("r:deps", "lib")}, True)]


def test_cli_build_propagate_rejects_bad_argument(monkeypatch):
    monkeypatch.setitem(cmd_build.osc.conf.config, "apiurl", API)
    monkeypatch.setattr(
        pp, "propagate", lambda *a, **k: pytest.fail("must not propagate")
    )
    args = cli.build_parser().parse_args(["-R", "r", "build", "propagate", "nopkg"])
    with pytest.raises(SystemExit) as e:
        args.func(args)
    assert e.value.code not in (0, None)
