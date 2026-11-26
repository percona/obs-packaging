# tests/test_propagate_run.py
"""Unit tests for running a propagation plan against OBS.

No OBS traffic: release_freeze.fetch_project_results, the _jobhistory,
binary-list, source-info and source-history GETs and http_POST are faked;
wait_seen gets fake sleep and clock callables so no real time passes.
"""

import shlex
import urllib.error
from types import SimpleNamespace
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
    """Canned build results, job histories, binary lists and sources."""

    def __init__(self, monkeypatch):
        self.codes: dict[str, dict[tuple[str, str, str], str]] = {}
        # (project, repo, arch, package) -> list of (readytime, srcmd5)
        self.jobs: dict[tuple[str, str, str, str], list[tuple[str, str]]] = {}
        # (project, repo, arch, package) -> list of (filename, mtime, size)
        self.binaries: dict[tuple[str, str, str, str], list[tuple[str, str, str]]] = {}
        # (project, package) -> (srcmd5, verifymd5 or None)
        self.source: dict[tuple[str, str], tuple[str, "str | None"]] = {}
        # (project, package) -> time of the newest source revision
        self.history: dict[tuple[str, str], str] = {}
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

    def kind_gets(self, kind):
        return [u for u in self.gets if self._kind(u) == kind]

    @staticmethod
    def _kind(url):
        path = urlsplit(url).path.strip("/").split("/")
        if path[0] == "build" and path[-1] == "_jobhistory":
            return "jobhistory"
        if path[0] == "build" and len(path) == 5:
            return "binaries"
        if path[0] == "source" and path[-1] == "_history":
            return "history"
        if path[0] == "source":
            return "info"
        return "other"

    def http_get(self, url, *a, **kw):
        self.gets.append(url)
        parts = urlsplit(url)
        path = parts.path.strip("/").split("/")
        query = parse_qs(parts.query)
        kind = self._kind(url)
        if kind == "jobhistory":
            prj, repo, arch = path[1], path[2], path[3]
            pkg = query["package"][0]
            entries = self.jobs.get((prj, repo, arch, pkg), [])[-1:]
            body = "".join(
                f'<jobhist package="{pkg}" readytime="{rt}" srcmd5="{md5}" code="succeeded"/>'
                for rt, md5 in entries
            )
            return _Resp(f"<jobhistlist>{body}</jobhistlist>".encode())
        if kind == "binaries":
            prj, repo, arch, pkg = path[1], path[2], path[3], path[4]
            body = "".join(
                f'<binary filename="{f}" mtime="{m}" size="{s}"/>'
                for f, m, s in self.binaries.get((prj, repo, arch, pkg), [])
            )
            return _Resp(f"<binarylist>{body}</binarylist>".encode())
        if kind == "history":
            prj, pkg = path[1], path[2]
            t = self.history[(prj, pkg)]
            return _Resp(
                f'<revisionlist><revision rev="3"><time>{t}</time></revision>'
                "</revisionlist>".encode()
            )
        if kind == "info":
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


def _wait(pkgs, since, *, seeds=frozenset(), timeout_s=4):
    t = FakeTime()
    return pp.wait_seen(
        API,
        pkgs,
        since,
        timeout_s=timeout_s,
        sleep=t.sleep,
        clock=t.clock,
        seeds=seeds,
    )


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
# wait_seen: common rules


def test_seen_when_pending_on_all_built_targets(obs):
    obs.codes["P"] = {
        ("a", "R1", "x86_64"): "building",
        ("a", "R2", "x86_64"): "excluded",
    }
    assert pp.wait_seen(API, {("P", "a")}, since={}) == set()
    assert obs.gets == []  # pending needs no job history


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

    unseen = pp.wait_seen(
        API, {("P", "a")}, since={}, sleep=sleep, clock=t.clock, seeds={("P", "a")}
    )
    assert unseen == set()
    assert t.sleeps == 1


def test_package_without_built_targets_is_seen(obs):
    obs.codes["P"] = {
        ("a", "R1", "x86_64"): "excluded",
        ("a", "R2", "x86_64"): "disabled",
    }
    obs.absent.add("Q")
    assert pp.wait_seen(API, {("P", "a"), ("P", "gone"), ("Q", "b")}, since={}) == (
        set()
    )


# ---------------------------------------------------------------------------
# wait_seen: packages we triggered (record moved)


def test_seen_when_jobhistory_moved(obs):
    obs.codes["P"] = {("a", "R1", "x86_64"): "succeeded"}
    obs.jobs[("P", "R1", "x86_64", "a")] = [("7", "m")]
    since = pp.record_since(API, {("P", "a")})
    obs.jobs[("P", "R1", "x86_64", "a")] = [("7", "m"), ("8", "m")]
    assert _wait({("P", "a")}, since) == set()


def test_seen_needs_every_target(obs):
    obs.codes["P"] = {
        ("a", "R1", "x86_64"): "scheduled",
        ("a", "R1", "aarch64"): "succeeded",
    }
    obs.jobs[("P", "R1", "aarch64", "a")] = [("7", "m")]
    since = pp.record_since(API, {("P", "a")})
    assert _wait({("P", "a")}, since) == {("P", "a")}


def test_multibuild_flavors_are_targets(obs):
    obs.codes["P"] = {
        ("a", "R1", "x86_64"): "building",
        ("a:docs", "R1", "x86_64"): "succeeded",
    }
    obs.jobs[("P", "R1", "x86_64", "a:docs")] = [("7", "m")]
    since = pp.record_since(API, {("P", "a")})
    assert _wait({("P", "a")}, since) == {("P", "a")}


def test_record_since_fails_loudly(obs, monkeypatch):
    def boom(apiurl, project):
        raise urllib.error.HTTPError(project, 500, "error", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(pp.release_freeze, "fetch_project_results", boom)
    with pytest.raises(urllib.error.HTTPError):
        pp.record_since(API, {("P", "a")})


def test_jobless_target_seen_when_binary_list_changes(obs):
    # An aggregate: no job history, its binaries are re-copied in place.
    obs.codes["P"] = {("agg", "R1", "x86_64"): "succeeded"}
    obs.binaries[("P", "R1", "x86_64", "agg")] = [("x.rpm", "100", "5")]
    since = pp.record_since(API, {("P", "agg")})
    obs.binaries[("P", "R1", "x86_64", "agg")] = [("x.rpm", "200", "5")]
    assert _wait({("P", "agg")}, since) == set()


def test_jobless_target_not_seen_while_binary_list_unchanged(obs):
    obs.codes["P"] = {("agg", "R1", "x86_64"): "succeeded"}
    obs.binaries[("P", "R1", "x86_64", "agg")] = [("x.rpm", "100", "5")]
    since = pp.record_since(API, {("P", "agg")})
    assert _wait({("P", "agg")}, since) == {("P", "agg")}


def test_target_with_job_history_needs_no_binary_list(obs):
    obs.codes["P"] = {("a", "R1", "x86_64"): "succeeded"}
    obs.jobs[("P", "R1", "x86_64", "a")] = [("7", "m")]
    since = pp.record_since(API, {("P", "a")})
    _wait({("P", "a")}, since)
    assert obs.kind_gets("binaries") == []


def test_triggered_seed_uses_its_record(obs):
    # A chained seed we triggered: its newest job already built the current
    # source, but only a job after the trigger counts.
    obs.codes["P"] = {("s", "R1", "x86_64"): "succeeded"}
    obs.jobs[("P", "R1", "x86_64", "s")] = [("7", "new")]
    obs.source[("P", "s")] = ("new", None)
    since = pp.record_since(API, {("P", "s")})
    assert _wait({("P", "s")}, since, seeds={("P", "s")}) == {("P", "s")}


# ---------------------------------------------------------------------------
# wait_seen: seeds (current source built)


def test_seed_seen_when_newest_job_built_current_source(obs):
    obs.codes["P"] = {("s", "R1", "x86_64"): "succeeded"}
    obs.jobs[("P", "R1", "x86_64", "s")] = [("7", "new")]
    obs.source[("P", "s")] = ("new", None)
    assert _wait({("P", "s")}, {}, seeds={("P", "s")}) == set()


@pytest.mark.parametrize("job_md5", ["unexpanded", "expanded"])
def test_seed_accepts_srcmd5_or_verifymd5(obs, job_md5):
    obs.codes["P"] = {("s", "R1", "x86_64"): "succeeded"}
    obs.jobs[("P", "R1", "x86_64", "s")] = [("7", job_md5)]
    obs.source[("P", "s")] = ("unexpanded", "expanded")
    assert _wait({("P", "s")}, {}, seeds={("P", "s")}) == set()


def test_seed_not_seen_while_newest_job_is_old_source(obs):
    obs.codes["P"] = {("s", "R1", "x86_64"): "succeeded"}
    obs.jobs[("P", "R1", "x86_64", "s")] = [("7", "old")]
    obs.source[("P", "s")] = ("new", "newer")
    assert _wait({("P", "s")}, {}, seeds={("P", "s")}) == {("P", "s")}


# ---------------------------------------------------------------------------
# wait_seen: members OBS rebuilds itself (job after the seed commit)


def test_member_seen_when_job_ready_after_seed_commit(obs):
    obs.codes["D"] = {
        ("lib", "R1", "x86_64"): "succeeded",
        ("mid", "R1", "x86_64"): "succeeded",
    }
    obs.jobs[("D", "R1", "x86_64", "lib")] = [("1050", "new")]
    obs.jobs[("D", "R1", "x86_64", "mid")] = [("1100", "m")]
    obs.source[("D", "lib")] = ("new", None)
    obs.history[("D", "lib")] = "1000"
    assert _wait({("D", "mid")}, {}, seeds={("D", "lib")}) == set()


def test_member_not_seen_with_job_before_seed_commit(obs):
    obs.codes["D"] = {("mid", "R1", "x86_64"): "succeeded"}
    obs.jobs[("D", "R1", "x86_64", "mid")] = [("900", "m")]
    obs.history[("D", "lib")] = "1000"
    assert _wait({("D", "mid")}, {}, seeds={("D", "lib")}) == {("D", "mid")}


def test_member_uses_newest_seed_commit(obs):
    obs.codes["D"] = {("mid", "R1", "x86_64"): "succeeded"}
    obs.jobs[("D", "R1", "x86_64", "mid")] = [("1500", "m")]
    obs.history[("D", "lib")] = "1000"
    obs.history[("D", "lib2")] = "2000"
    seeds = {("D", "lib"), ("D", "lib2")}
    assert _wait({("D", "mid")}, {}, seeds=seeds) == {("D", "mid")}


# ---------------------------------------------------------------------------
# run_stages


@pytest.fixture
def events(monkeypatch):
    log: list[str] = []
    unseen: dict[frozenset, set] = {}
    wait_kw: list[dict] = []

    def fake_wait(apiurl, pkgs, since, **kw):
        log.append("wait:" + ",".join(sorted(n for _, n in pkgs)))
        log.append("since:" + ",".join(sorted(f"{p}/{n}" for p, n in since)))
        wait_kw.append(kw)
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
    return SimpleNamespace(log=log, unseen=unseen, wait_kw=wait_kw)


STAGES = [
    Stage(frozenset({("P", "a")}), {"P": ["b"]}),
    Stage(frozenset({("P", "b")}), {"Q": ["img"]}),
]


def test_run_stages_orders_wait_then_trigger(events):
    pp.run_stages(API, STAGES, dry_run=False, seeds={("P", "a")})
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
    assert all(kw["seeds"] == {("P", "a")} for kw in events.wait_kw)


def test_run_stages_triggers_every_project_of_a_stage(events):
    stages = [Stage(frozenset({("P", "a")}), {"P": ["b"], "Q": ["t"]})]
    pp.run_stages(API, stages, dry_run=False)
    assert "trigger:P:b" in events.log and "trigger:Q:t" in events.log
    assert "record:P/b,Q/t" in events.log


def test_run_stages_triggered_package_without_record_is_an_error(events, monkeypatch):
    monkeypatch.setattr(pp, "record_since", lambda apiurl, pkgs: {})
    with pytest.raises(RuntimeError, match="P/b"):
        pp.run_stages(API, STAGES, dry_run=False)
    assert "trigger:Q:img" not in events.log


def test_run_stages_continues_after_timeout(capsys, events, obs):
    obs.codes["P"] = {
        ("a", "R1", "x86_64"): "unresolvable",
        ("a", "R2", "aarch64"): "succeeded",
    }
    events.unseen[frozenset({("P", "a")})] = {("P", "a")}
    pp.run_stages(API, STAGES, dry_run=False)
    out = capsys.readouterr().out
    assert "trigger:P:b" in events.log and "trigger:Q:img" in events.log
    assert "not seen" in out
    assert "P/a [R1/x86_64: unresolvable, R2/aarch64: succeeded]" in out


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
    st = SimpleNamespace(
        states={R: "frozen", C: "frozen"},
        paths={R: {D}, C: {R}, D: set()},
        fwd={(R, "b"): {(D, "lib")}, (C, "img"): {(R, "b")}},
        fail=set(),
        absent=set(),
        depinfo_calls=[],
        run=[],
        recorded=[],
    )

    monkeypatch.setattr(
        pp, "list_release_units", lambda: [{"unit": "u"}, {"unit": "v"}]
    )
    monkeypatch.setattr(
        pp, "unit_obs_projects", lambda unit, rootprj: [f"r:{unit}", f"r:{unit}:x"]
    )
    monkeypatch.setattr(pp, "frozen_projects", lambda apiurl, projs: dict(st.states))
    monkeypatch.setattr(
        pp, "_project_path_projects", lambda apiurl, prj: st.paths.get(prj, set())
    )
    monkeypatch.setattr(pp, "_project_exists", lambda apiurl, prj: prj not in st.absent)

    def fake_depinfo(apiurl, projects, local, image_pkgs=None, **kw):
        st.depinfo_calls.append((set(projects), kw))
        if kw.get("failed") is not None:
            kw["failed"].update(st.fail)
        return {k: set(v) for k, v in st.fwd.items()}

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
        lambda apiurl, pkgs: st.recorded.append(set(pkgs)) or {p: {} for p in pkgs},
    )

    def fake_run(apiurl, stages, dry_run, *, seeds=frozenset(), **kw):
        print("RUN")
        st.run.append((stages, dry_run, set(seeds)))

    monkeypatch.setattr(pp, "run_stages", fake_run)
    return st


def test_propagate_nothing_frozen_queries_no_dependencies(prop, capsys):
    prop.states = {R: "partial", C: "unfrozen"}
    pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=False)
    assert prop.depinfo_calls == [] and prop.run == []
    assert "build propagate" not in capsys.readouterr().out


def test_propagate_runs_plan_over_seed_and_upstream_projects(prop, capsys):
    pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=False)
    projects, kw = prop.depinfo_calls[0]
    assert projects == {R, C, D}
    assert kw["all_targets"] is True
    stages, dry_run, seeds = prop.run[0]
    assert [s.trigger for s in stages] == [{R: ["b"]}, {C: ["img"]}]
    assert dry_run is False and seeds == {(D, "lib")}
    out = capsys.readouterr().out
    assert "build propagate r:deps/lib" in out
    assert out.index("build propagate") < out.index("RUN")
    assert "r:deps/lib" in out.split("build propagate")[0]  # seeds printed


def test_propagate_records_nothing_for_members_obs_rebuilds(prop):
    prop.fwd = {(D, "mid"): {(D, "lib")}, (R, "b"): {(D, "mid")}}
    pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=False)
    assert prop.recorded == []
    assert (D, "mid") in prop.run[0][0][0].wait_for


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


def test_propagate_dry_run(prop, capsys):
    pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=True)
    assert prop.run[0][1] is True
    assert "build propagate" not in capsys.readouterr().out


def test_propagate_prints_recovery_before_dependency_queries(prop, capsys, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("depinfo down")

    monkeypatch.setattr(pp, "_fetch_combined_depinfo", boom)
    with pytest.raises(RuntimeError):
        pp.propagate(API, "r", {(D, "lib")}, [], {}, dry_run=False)
    assert "build propagate r:deps/lib" in capsys.readouterr().out


def test_recovery_command_runs_as_printed(prop, capsys):
    seeds = {(D, "lib"), (R, "a b")}
    env = ["OBS_CONTAINER_REGISTRY:reg.example/x", "ODD:it's $HOME"]
    pp.propagate(
        "https://obs.example:444",
        "home:me:ppg",
        seeds,
        [],
        {},
        dry_run=False,
        env_overrides=env,
        profile="labs main",
    )
    line = next(
        ln for ln in capsys.readouterr().out.splitlines() if "build propagate" in ln
    )
    argv = shlex.split(line[line.index("percona-obs") :])
    assert argv[0] == "percona-obs"
    args = cli.build_parser().parse_args(argv[1:])
    assert args.apiurl == "https://obs.example:444"
    assert args.rootprj == "home:me:ppg"
    assert args.profile == "labs main"
    assert args.env_overrides == env
    assert args.build_command == "propagate" and args.dry_run is False
    assert {tuple(p.rsplit("/", 1)) for p in args.packages} == seeds


def test_project_order_puts_paths_first():
    order = pp._project_order({C: {R}, R: {D}, D: set(), "r:x": set()})
    assert order.index(D) < order.index(R) < order.index(C)


# ---------------------------------------------------------------------------
# build propagate


def test_cli_build_propagate(monkeypatch):
    monkeypatch.setitem(cmd_build.osc.conf.config, "apiurl", API)
    calls = []
    monkeypatch.setattr(cmd_build, "_propagate_targets", lambda args, env: [])

    def fake_propagate(apiurl, rootprj, seeds, targets, env, dry_run, **kw):
        calls.append((apiurl, rootprj, seeds, dry_run, kw))

    monkeypatch.setattr(pp, "propagate", fake_propagate)
    args = cli.build_parser().parse_args(
        [
            "-R",
            "r",
            "-P",
            "labs",
            "-e",
            "K:V",
            "build",
            "propagate",
            "r:u/a",
            "r:deps/lib",
            "--dry-run",
        ]
    )
    args.func(args)
    assert calls == [
        (
            API,
            "r",
            {("r:u", "a"), ("r:deps", "lib")},
            True,
            {"env_overrides": ["K:V"], "profile": "labs"},
        )
    ]


def test_cli_build_propagate_rejects_bad_argument(monkeypatch):
    monkeypatch.setitem(cmd_build.osc.conf.config, "apiurl", API)
    monkeypatch.setattr(
        pp, "propagate", lambda *a, **k: pytest.fail("must not propagate")
    )
    args = cli.build_parser().parse_args(["-R", "r", "build", "propagate", "nopkg"])
    with pytest.raises(SystemExit) as e:
        args.func(args)
    assert e.value.code not in (0, None)
