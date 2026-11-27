"""Tests for the QA dashboard (tools/qa-dashboard)."""

import datetime as dt
import io
import json
import pathlib
import re
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "qa-dashboard"))

import collect  # noqa: E402

NOW = dt.datetime(2026, 11, 10, 2, 38, tzinfo=dt.timezone.utc)


def build(pipeline, result="SUCCESS", label="default", url=None, **params):
    params.setdefault("VERSION", "ppg-18.6")
    return {
        "pipeline": pipeline,
        "label": label,
        "params": params,
        "result": result,
        "build_url": url or f"https://jenkins/job/{pipeline}/1/",
    }


def run(rid, day, builds, event="schedule", minutes=60, status="completed"):
    workflow = "obs-nightly-qa.yml" if event == "schedule" else "obs-qa-run.yml"
    start = dt.datetime(2026, 11, day, 2, 0, tzinfo=dt.timezone.utc)
    return {
        "id": rid,
        "url": f"https://github/run/{rid}",
        "event": event,
        "workflow": workflow,
        "status": status,
        "started_at": collect.iso(start),
        "finished_at": (
            collect.iso(start + dt.timedelta(minutes=minutes))
            if status == "completed"
            else None
        ),
        "builds": builds,
    }


KNOWN = [
    {
        "ticket": "PG-1",
        "title": "minor upgrade",
        "major": [17, 18],
        "pipeline": "^ppg-upgrade-parallel$",
        "label": "minor-upgrade",
    }
]


@pytest.mark.parametrize(
    "params,label,major",
    [
        ({"VERSION": "ppg-18.6"}, "", "18"),
        ({"NEW_SERVER_VERSION": "15.19", "OLD_SERVER_VERSION": "14.24"}, "", "15"),
        (
            {"TO_VERSION": "ppg-19.0", "OBS_PROJECT": "isv:percona:ppg:staging:19"},
            "",
            "19",
        ),
        ({"DOCKER_TAG": "17", "SERVER_VERSION": "17.11"}, "", "17"),
        ({"OBS_PROJECT": "isv:percona:ppg:staging:16:tarballs"}, "", "16"),
        ({}, "pgbackrest-pg14", "14"),
        ({"VERSION": ""}, "", None),
    ],
)
def test_major_of(params, label, major):
    assert collect.major_of(params, label) == major


def test_match_known_major_list_pipeline_and_label():
    minor = build("ppg-upgrade-parallel", label="SCENARIO=pg-18-minor-upgrade")
    major = build("ppg-upgrade-parallel", label="SCENARIO=pg-18-major-upgrade")
    assert collect.match_known(minor, "18", KNOWN)["ticket"] == "PG-1"
    assert collect.match_known(minor, "16", KNOWN) is None  # not in the majors
    assert collect.match_known(major, "18", KNOWN) is None  # label doesn't match
    assert collect.match_known(build("tde-parallel"), "18", KNOWN) is None


def test_statuses_failing_since_and_partial_manual_runs():
    up = "SCENARIO=pg-18-minor-upgrade"
    runs = [
        # newest first
        run(
            5,
            6,
            [
                build("ppg-upgrade-parallel", "FAILURE", up),
                build("tde-parallel", "FAILURE"),
            ],
        ),
        # a manual run of tde-parallel only: no upgrade build in it
        run(4, 4, [build("tde-parallel")], event="workflow_dispatch"),
        run(
            3, 3, [build("ppg-upgrade-parallel", "FAILURE", up), build("tde-parallel")]
        ),
        run(
            2, 2, [build("ppg-upgrade-parallel", "SUCCESS", up), build("tde-parallel")]
        ),
    ]
    data = collect.build_dashboard(runs, KNOWN, NOW)
    pg18 = next(m for m in data["majors"] if m["major"] == "18")
    assert (pg18["status"], pg18["failing"], pg18["new"], pg18["total"]) == (
        "fail",
        2,
        1,
        2,
    )
    # newest first; the manual (OBS QA Run) run of 4 Nov is not part of the history
    assert [r["kind"] for r in pg18["runs"]] == ["fail", "known", "pass"]
    by_ticket = {f["ticket"]: f for f in data["failures"]}
    # the upgrade failed on 3 and 6 Nov; the manual run on 4 Nov didn't include it
    assert by_ticket["PG-1"]["since"] == "3 Nov · 2 runs"
    assert by_ticket[""]["since"] == "6 Nov · 1 run" and by_ticket[""]["is_new"]
    assert data["failures"][0]["is_new"]  # new failures first
    assert "jobs" not in data["details"]["18"]  # no per-job grid


def test_majors_without_runs_and_only_known_failures():
    runs = [
        run(
            1,
            5,
            [
                build(
                    "ppg-upgrade-parallel",
                    "FAILURE",
                    "SCENARIO=pg-17-minor-upgrade",
                    VERSION="ppg-17.11",
                )
            ],
        )
    ]
    data = collect.build_dashboard(runs, KNOWN, NOW)
    statuses = {m["major"]: m["status"] for m in data["majors"]}
    assert statuses["17"] == "known" and statuses["14"] == "none"


def test_slow_run_flagged_against_median():
    runs = [
        run(i, 10 - i, [build("tde-parallel")], minutes=m)
        for i, m in enumerate([95, 60, 62, 58, 61])
    ]
    pg18 = next(
        m
        for m in collect.build_dashboard(runs, [], NOW)["majors"]
        if m["major"] == "18"
    )
    assert pg18["slow"] and pg18["runtime"] == "1h 35m" and pg18["median"] == "1h 01m"
    runs[0]["finished_at"] = collect.iso(
        collect.parse_time(runs[0]["started_at"]) + dt.timedelta(minutes=80)
    )
    pg18 = next(
        m
        for m in collect.build_dashboard(runs, [], NOW)["majors"]
        if m["major"] == "18"
    )
    assert not pg18["slow"]  # 80 < 1.5 * 61


def test_running_run_progress():
    running = run(
        9, 10, [build("tde-parallel", VERSION="ppg-15.19")], status="in_progress"
    )
    running.update(qa_jobs={"total": 39, "done": 21, "failed": 1})
    data = collect.build_dashboard(
        [running, run(1, 3, [build("tde-parallel", VERSION="ppg-15.19")])], [], NOW
    )
    assert [r["majors"] for r in data["running"]] == [["15"]]
    assert data["running"][0]["done"] == 21
    pg15 = next(m for m in data["majors"] if m["major"] == "15")
    assert pg15["status"] == "running" and pg15["progress"] == "21 / 39"
    assert pg15["runs"][0]["kind"] == "running"


def test_only_failing_platforms_are_shown():
    platforms = ["ol-8", "rhel-9", "debian-12"]

    def failure(failed):
        b = build(
            "tde-parallel", "FAILURE", url="https://jenkins/x/7/", PLATFORMS=platforms
        )
        info = (
            {}
            if failed is None
            else {
                "https://jenkins/x/7/": {"duration_s": 600, "failed_platforms": failed}
            }
        )
        return collect.build_dashboard([run(1, 6, [b])], [], NOW, info)["failures"][0]

    f = failure(["ol-8"])
    assert f["failed_platforms"] == ["ol-8"] and f["platforms"] == "ol-8"
    assert f["platform_note"] == "1 of 3 platforms failed" and f["build"] == "#7"
    f = failure(None)  # no Jenkins data: say so, don't list every tested platform
    assert f["failed_platforms"] == [] and f["platforms"] == "platforms unknown"
    assert "not known" in f["platform_note"]
    f = failure([])  # failed, but in no platform's stage
    assert (
        f["failed_platforms"] == []
        and "outside the platform stages" in f["platform_note"]
    )


def test_known_failures_file():
    """The real file: every entry has a ticket and a title, and its patterns
    are valid regular expressions (independent of which entries it holds)."""
    entries = collect.load_known(ROOT / ".github" / "qa-known-failures.yaml")
    for e in entries:
        assert re.match(r"^PG-\d+$", e["ticket"]) and e.get("title")
        re.compile(e["pipeline"])
        re.compile(e.get("label") or ".")
        for regex in (e.get("params") or {}).values():
            re.compile(str(regex))


def test_server_serves_page_and_data():
    import serve

    state = serve.State()
    state.set(collect.build_dashboard([run(1, 6, [build("tde-parallel")])], [], NOW))
    server = serve.ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/") as r:
            assert "PPG Nightly QA" in r.read().decode()
        with urllib.request.urlopen(base + "/app.js") as r:
            assert r.status == 200
            assert r.headers["Cache-Control"] == "no-cache"  # never a stale script
        with urllib.request.urlopen(base + "/data.json") as r:
            assert r.headers["Cache-Control"] == "no-store"
            data = json.load(r)
        assert len(data["majors"]) == 6 and data["error"] == ""
        state.fail("URLError: down")
        with urllib.request.urlopen(base + "/data.json") as r:
            stale = json.load(r)
        assert (
            stale["error"] == "URLError: down" and stale["majors"]
        )  # last good data kept
    finally:
        server.shutdown()
        server.server_close()


def test_unreachable_jenkins_is_tried_once_per_refresh(tmp_path, capsys):
    jenkins = collect.Jenkins(None, None)
    calls = []
    real_get = jenkins._get

    def get(url):
        calls.append(url)
        return real_get("http://127.0.0.1:9/" + url.split("/", 3)[-1])  # refused

    jenkins._get = get
    builds = [
        build(
            "tde-parallel", "FAILURE", url=f"https://jenkins/x/{i}/", PLATFORMS=["ol-8"]
        )
        for i in range(30)
    ]
    info = collect.collect_build_info(jenkins, [run(1, 6, builds)], tmp_path)
    # at most the requests already under way when Jenkins was found unreachable
    assert (
        info == {} and len(calls) <= collect.JENKINS_WORKERS and not jenkins.available
    )
    assert "Jenkins not reachable" in capsys.readouterr().err
    off = collect.Jenkins(None, None, enabled=False)
    assert collect.collect_build_info(off, [run(1, 6, builds)], tmp_path) == {}


class FakeGitHub:
    def __init__(self, runs):
        self.runs, self.calls = runs, []

    def get(self, path):
        self.calls.append(path)
        if "/workflows/" in path:
            return {"workflow_runs": self.runs if "nightly" in path else []}
        if path.endswith("/artifacts?per_page=100"):
            rid = path.split("/")[2]
            return {
                "artifacts": (
                    []
                    if rid == "2"
                    else [{"name": "qa-report-0", "archive_download_url": f"zip/{rid}"}]
                )
            }
        raise AssertionError(path)

    def download(self, url):
        import io as _io
        import zipfile as _zf

        buf = _io.BytesIO()
        with _zf.ZipFile(buf, "w") as z:
            report = {
                "pipeline": "tde-parallel",
                "combos": [
                    {
                        "label": "default",
                        "params": {"VERSION": "ppg-18.6"},
                        "result": "SUCCESS",
                        "build_url": "https://j/1/",
                    }
                ],
            }
            z.writestr("qa-report.json", json.dumps(report))
        return buf.getvalue()


def test_collect_runs_caches_finished_runs_and_reports_progress(tmp_path, capsys):
    def gh_run(rid):
        return {
            "id": rid,
            "html_url": f"u/{rid}",
            "event": "schedule",
            "status": "completed",
            "run_started_at": "2026-11-06T02:00:00Z",
            "created_at": "2026-11-06T02:00:00Z",
            "updated_at": "2026-11-06T03:00:00Z",
        }

    gh = FakeGitHub(
        [gh_run(1), gh_run(2)]
    )  # run 2: no QA reports (a skipped night): kept, to show it
    runs = collect.collect_runs(gh, tmp_path)
    assert [(r["id"], len(r["builds"])) for r in runs] == [(1, 1), (2, 0)]
    assert "[1/2] run 1 (completed): 1 build reports" in capsys.readouterr().err
    assert (tmp_path / "run-1.json").is_file() and (tmp_path / "run-2.json").is_file()
    gh.calls.clear()
    assert [r["id"] for r in collect.collect_runs(gh, tmp_path)] == [1, 2]
    assert not [c for c in gh.calls if "/artifacts" in c]  # both served from the cache


def test_manual_runs_are_left_out():
    nightly = run(1, 5, [build("tde-parallel")])
    manual = run(2, 6, [build("tde-parallel", "FAILURE")], event="workflow_dispatch")
    data = collect.build_dashboard([manual, nightly], [], NOW)
    pg18 = next(m for m in data["majors"] if m["major"] == "18")
    assert pg18["status"] == "pass" and len(pg18["runs"]) == 1 and not data["failures"]


def _zip(report):
    import io as _io
    import zipfile as _zf

    buf = _io.BytesIO()
    with _zf.ZipFile(buf, "w") as z:
        z.writestr("qa-report.json", json.dumps(report))
    return buf.getvalue()


class RerunGitHub:
    """A nightly whose job 1 was re-run: its first attempt failed, the
    re-run passed. Job 0 ran once."""

    def __init__(self, attempt=2):
        self.calls, self.attempt = [], attempt

    def get(self, path):
        self.calls.append(path)
        if "/workflows/" in path:
            return {
                "workflow_runs": [
                    {
                        "id": 7,
                        "html_url": "u/7",
                        "event": "schedule",
                        "status": "completed",
                        "run_attempt": self.attempt,
                        "created_at": "2026-11-09T02:00:00Z",
                        "run_started_at": "2026-11-10T09:00:00Z",
                        "updated_at": "2026-11-10T09:20:00Z",
                    }
                ]
            }
        if path.endswith("/attempts/1"):
            return {
                "run_started_at": "2026-11-09T02:00:00Z",
                "updated_at": "2026-11-09T03:05:00Z",
            }
        if path.endswith("/artifacts?per_page=100"):
            return {
                "artifacts": [
                    {
                        "name": "qa-report-0",
                        "created_at": "2026-11-09T02:40:00Z",
                        "archive_download_url": "ok0",
                    },
                    {
                        "name": "qa-report-1",
                        "created_at": "2026-11-09T02:50:00Z",
                        "archive_download_url": "fail1",
                    },
                    {
                        "name": "qa-report-1",
                        "created_at": "2026-11-10T09:15:00Z",
                        "archive_download_url": "ok1",
                    },
                ]
            }
        raise AssertionError(path)

    def download(self, url):
        result = "FAILURE" if url.startswith("fail") else "SUCCESS"
        job = url[-1]
        return _zip(
            {
                "pipeline": f"job{job}",
                "combos": [
                    {
                        "label": "default",
                        "params": {"VERSION": "ppg-14.24"},
                        "result": result,
                        "build_url": f"https://j/{url}/",
                    }
                ],
            }
        )


def test_rerun_jobs_count_once_with_their_final_result(tmp_path):
    gh = RerunGitHub()
    runs = collect.collect_runs(gh, tmp_path)
    assert len(runs[0]["builds"]) == 2  # not 3
    assert all(b["result"] == "SUCCESS" for b in runs[0]["builds"])
    # date and run time from the first attempt, not the re-run
    assert (
        runs[0]["started_at"] == "2026-11-09T02:00:00Z"
        and runs[0]["finished_at"] == "2026-11-09T03:05:00Z"
    )
    pg14 = next(
        m
        for m in collect.build_dashboard(runs, [], NOW)["majors"]
        if m["major"] == "14"
    )
    assert (pg14["status"], pg14["failing"], pg14["total"]) == ("pass", 0, 2)
    assert pg14["last_run"] == "Mon 9 Nov" and pg14["runtime"] == "1h 05m"


def test_cache_is_reread_after_a_rerun_or_format_change(tmp_path):
    collect.collect_runs(RerunGitHub(attempt=2), tmp_path)
    gh = RerunGitHub(attempt=2)
    collect.collect_runs(gh, tmp_path)
    assert not [c for c in gh.calls if "/artifacts" in c]  # cached
    gh = RerunGitHub(attempt=3)  # re-run again since it was cached
    collect.collect_runs(gh, tmp_path)
    assert [c for c in gh.calls if "/artifacts" in c]
    cached = tmp_path / "run-7.json"
    old = json.loads(cached.read_text())
    old.pop("v")
    cached.write_text(json.dumps(old))  # cached by the first version
    gh = RerunGitHub(attempt=3)
    collect.collect_runs(gh, tmp_path)
    assert [c for c in gh.calls if "/artifacts" in c]


def test_jenkins_refusal_says_whether_a_login_was_sent(capsys):
    import urllib.error

    def refuse(url):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    for user, token, expected in (
        (None, None, "without a login"),
        ("mohit", "t", "logged in as mohit"),
    ):
        jenkins = collect.Jenkins(user, token)
        jenkins._get = refuse
        assert jenkins.build_info("https://jenkins/job/x/5/", ["ol-8"]) is None
        err = capsys.readouterr().err
        assert expected in err and "https://jenkins/job/x/5/" in err


def test_failed_platforms_match_stage_names_exactly():
    both = ["rocky-8", "rocky-8-arm", "debian-12"]
    assert collect.failed_platforms_from(["rocky-8-arm"], both) == ["rocky-8-arm"]
    # no PLATFORMS parameter (upgrade jobs): the failed stages that are platforms
    stages = ["debian-12", "Prepare", "rhel-9-arm", "Post"]
    assert collect.failed_platforms_from(stages, []) == ["debian-12", "rhel-9-arm"]


def test_upgrade_job_without_platforms_parameter():
    jenkins = collect.Jenkins("u", "t")

    def get(url):
        if url.endswith("wfapi/describe"):
            return {
                "stages": [
                    {"name": "Checkout", "status": "SUCCESS"},
                    {"name": "debian-12", "status": "FAILED"},
                    {"name": "ol-9-arm", "status": "FAILED"},
                    {"name": "rocky-9", "status": "SUCCESS"},
                ]
            }
        return {"building": False, "duration": 600000, "result": "FAILURE"}

    jenkins._get = get
    info = jenkins.build_info("https://jenkins/job/ppg-upgrade-parallel/1537/", [])
    assert info["failed_platforms"] == ["debian-12", "ol-9-arm"]
    b = build(
        "ppg-upgrade-parallel",
        "FAILURE",
        "SCENARIO=pg-15-major-upgrade",
        url="https://jenkins/job/ppg-upgrade-parallel/1537/",
        VERSION="ppg-15.19",
    )
    f = collect.build_dashboard([run(1, 10, [b])], [], NOW, {b["build_url"]: info})[
        "failures"
    ][0]
    assert (
        f["failed_platforms"] == ["debian-12", "ol-9-arm"]
        and f["platform_note"] == "2 platforms failed"
    )


def test_builds_cached_before_platform_detection_are_rechecked(tmp_path):
    url = "https://jenkins/job/x/9/"
    (tmp_path / "jenkins-builds.json").write_text(
        json.dumps({url: {"duration_s": 60}})
    )  # old entry
    jenkins = collect.Jenkins("u", "t")
    asked = []
    jenkins.build_info = lambda u, p: asked.append(u) or {
        "duration_s": 60,
        "failed_platforms": ["ol-8"],
    }
    info = collect.collect_build_info(
        jenkins, [run(1, 6, [build("tde-parallel", "FAILURE", url=url)])], tmp_path
    )
    assert asked == [url] and info[url]["failed_platforms"] == ["ol-8"]
    asked.clear()
    collect.collect_build_info(
        jenkins, [run(1, 6, [build("tde-parallel", "FAILURE", url=url)])], tmp_path
    )
    assert asked == []  # now cached in the current format


def test_builds_deleted_from_jenkins_are_not_asked_again(tmp_path):
    import urllib.error

    jenkins = collect.Jenkins("u", "t")
    asked = []

    def gone(url):
        asked.append(url)
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    jenkins._get = gone
    builds = [build("tde-parallel", "FAILURE", url="https://jenkins/job/x/1/")]
    info = collect.collect_build_info(jenkins, [run(1, 6, builds)], tmp_path)
    assert info["https://jenkins/job/x/1/"]["missing"] and jenkins.available
    asked.clear()
    collect.collect_build_info(jenkins, [run(1, 6, builds)], tmp_path)
    assert asked == []
    f = collect.build_dashboard([run(1, 6, builds)], [], NOW, info)["failures"][0]
    assert f["platform_note"] == "This build is no longer kept in Jenkins"


def test_jenkins_builds_are_asked_several_at_a_time(tmp_path):
    import time

    jenkins = collect.Jenkins("u", "t")

    def slow(url, platforms):
        time.sleep(0.2)
        return {"duration_s": 60}

    jenkins.build_info = slow
    builds = [
        build("tde-parallel", url=f"https://jenkins/job/x/{i}/") for i in range(16)
    ]
    start = time.monotonic()
    info = collect.collect_build_info(jenkins, [run(1, 6, builds)], tmp_path)
    assert len(info) == 16 and time.monotonic() - start < 1.5  # one by one: 3.2 s


def test_known_failures_link_to_their_ticket():
    up = "SCENARIO=pg-18-minor-upgrade"
    known = KNOWN + [
        {
            "ticket": "GH-7",
            "url": "https://github.com/x/y/issues/7",
            "major": 18,
            "pipeline": "^tde-parallel$",
        }
    ]
    builds = [
        build("ppg-upgrade-parallel", "FAILURE", up),
        build("tde-parallel", "FAILURE"),
        build("pgsm-parallel", "FAILURE"),
    ]
    urls = {
        f["ticket"]: f["ticket_url"]
        for f in collect.build_dashboard([run(1, 6, builds)], known, NOW)["failures"]
    }
    assert urls == {
        "PG-1": "https://perconadev.atlassian.net/browse/PG-1",
        "GH-7": "https://github.com/x/y/issues/7",
        "": "",  # a new failure has no ticket
    }


def test_queued_rerun_is_not_running():
    """PG 17's nightly runs while a re-run of PG 15's (failed jobs) waits."""
    first = "2026-11-10T02:00:00Z"
    pg15 = run(1, 10, [build("tde-parallel", "FAILURE", VERSION="ppg-15.20")])
    pg15.update(
        status="queued",
        attempt=2,
        attempt_started_at="2026-11-11T05:50:00Z",
        started_at=first,
    )
    pg17 = run(
        2, 11, [build("tde-parallel", VERSION="ppg-17.12")], status="in_progress"
    )
    pg17.update(
        qa_jobs={"total": 46, "done": 10, "failed": 0},
        attempt_started_at="2026-11-11T02:00:00Z",
    )
    data = collect.build_dashboard([pg17, pg15], [], NOW)
    assert [(r["majors"], r["since"]) for r in data["running"]] == [
        (["17"], "2026-11-11T02:00:00Z")
    ]
    assert [(q["majors"], q["rerun"], q["since"]) for q in data["queued"]] == [
        (["15"], True, "2026-11-11T05:50:00Z")
    ]
    assert data["queued"][0]["github_status"] == "queued"
    pg15row = next(m for m in data["majors"] if m["major"] == "15")
    assert pg15row["status"] == "queued" and "progress" not in pg15row
    assert pg15row["runs"][0]["kind"] == "queued"


def test_unfinished_run_has_no_major_until_its_builds_report():
    """A nightly that has just started has no build reports yet: it is shown
    as a nightly in progress, without guessing its major from job names."""
    queued = run(5, 10, [], status="queued")
    data = collect.build_dashboard([queued], [], NOW)
    assert [q["majors"] for q in data["queued"]] == [[]] and data["running"] == []
    assert all(m["status"] == "none" for m in data["majors"])


def test_rerun_keeps_its_earlier_results_while_queued():
    """Re-running the failed jobs of PG 15's 10 Nov nightly: until the re-run
    finishes, that nightly's results are still PG 15's latest."""
    older = run(1, 3, [build("tde-parallel", VERSION="ppg-15.20")])
    rerun = run(
        2,
        10,
        [
            build("tde-parallel", "FAILURE", VERSION="ppg-15.20"),
            build("pgsm-parallel", VERSION="ppg-15.20"),
        ],
    )
    rerun.update(status="queued", attempt=2, attempt_started_at="2026-11-11T05:50:00Z")
    pg15 = next(
        m
        for m in collect.build_dashboard([rerun, older], [], NOW)["majors"]
        if m["major"] == "15"
    )
    assert pg15["status"] == "queued"
    assert (pg15["last_run"], pg15["failing"], pg15["total"]) == (
        "Tue 10 Nov",
        1,
        2,
    )  # not 3 Nov
    assert [r["kind"] for r in pg15["runs"]] == ["queued", "pass"]


def test_all_artifact_pages_are_read(tmp_path):
    """Like run 43044888795: re-run 4 times, over 100 artifacts; the passing
    re-run reports are on page 2, the first attempts' failures on page 1."""

    class ManyAttempts:
        def __init__(self):
            self.calls = []
            arts = [
                {
                    "name": f"qa-report-{i}",
                    "created_at": "2026-11-11T16:00:00Z",
                    "archive_download_url": f"ok{i}",
                }
                for i in range(53)
            ]
            # earlier attempts: job 0..3 failed before Jenkins (no result), re-uploaded many times
            arts += [
                {
                    "name": f"qa-report-{i % 4}",
                    "created_at": f"2026-11-11T16:{10 + n:02d}:00Z",
                    "archive_download_url": f"none{i % 4}",
                }
                for n, i in enumerate(range(73))
            ]
            # the last attempt: jobs 0..3 pass
            arts += [
                {
                    "name": f"qa-report-{i}",
                    "created_at": "2026-11-12T09:00:00Z",
                    "archive_download_url": f"ok{i}",
                }
                for i in range(4)
            ]
            self.arts = arts  # 130 artifacts

        def get(self, path):
            self.calls.append(path)
            if "/workflows/" in path:
                return {
                    "workflow_runs": [
                        {
                            "id": 43044888795,
                            "html_url": "u",
                            "event": "schedule",
                            "status": "completed",
                            "run_attempt": 5,
                            "created_at": "2026-11-11T15:05:47Z",
                            "run_started_at": "2026-11-12T08:30:00Z",
                            "updated_at": "2026-11-12T09:10:00Z",
                        }
                    ]
                }
            if path.endswith("/attempts/1"):
                return {
                    "run_started_at": "2026-11-11T15:05:47Z",
                    "updated_at": "2026-11-11T16:20:00Z",
                }
            if "/artifacts?per_page=100" in path:
                page = int(path.split("&page=")[1]) if "&page=" in path else 1
                return {
                    "total_count": len(self.arts),
                    "artifacts": self.arts[(page - 1) * 100 : page * 100],
                }
            raise AssertionError(path)

        def download(self, url):
            ok = url.startswith("ok")
            return _zip(
                {
                    "pipeline": "job" + url.lstrip("oknone"),
                    "combos": [
                        {
                            "label": "default",
                            "params": {"VERSION": "ppg-18.7"},
                            "result": "SUCCESS" if ok else None,
                            "build_url": f"https://j/{url}/" if ok else None,
                        }
                    ],
                }
            )

    gh = ManyAttempts()
    runs = collect.collect_runs(gh, tmp_path)
    assert [c for c in gh.calls if "&page=2" in c]  # the second page was read
    assert len(runs[0]["builds"]) == 53
    assert all(
        b["result"] == "SUCCESS" for b in runs[0]["builds"]
    )  # not the old 'None' reports
    pg18 = next(
        m
        for m in collect.build_dashboard(runs, [], NOW)["majors"]
        if m["major"] == "18"
    )
    assert (pg18["status"], pg18["failing"], pg18["total"]) == ("pass", 0, 53)


def test_running_major_with_a_newer_queued_run():
    """PG 19's nightly runs while a newer PG 19 nightly waits behind it: the
    major is running, and both runs are shown."""
    done = run(1, 7, [build("tde-parallel", VERSION="ppg-19.0")])
    # its first QA jobs have finished and reported their builds
    running = run(
        2, 13, [build("pgsm-parallel", VERSION="ppg-19.0")], status="in_progress"
    )
    running.update(
        started_at="2026-11-14T02:00:00Z",
        attempt_started_at="2026-11-14T02:00:00Z",
        qa_jobs={"total": 45, "done": 12, "failed": 1},
    )
    waiting = run(3, 13, [], status="queued")
    waiting.update(
        started_at="2026-11-14T03:05:00Z",
        attempt_started_at="2026-11-14T03:05:00Z",
    )
    data = collect.build_dashboard([waiting, running, done], [], NOW)
    pg19 = next(m for m in data["majors"] if m["major"] == "19")
    assert pg19["status"] == "running" and pg19["progress"] == "12 / 45"
    assert [(r["majors"], r["done"]) for r in data["running"]] == [(["19"], 12)]
    assert [q["majors"] for q in data["queued"]] == [[]]  # no builds reported yet


def test_a_refresh_reads_the_runs_once_and_the_files_from_main(tmp_path, monkeypatch):
    """One GitHub pass per refresh (then Jenkins); known failures and the
    schedule come from main, so merging them is enough."""
    import serve

    calls = []

    class FakeGitHub:
        def __init__(self, *a):
            pass

        def get(self, path):
            calls.append(path)
            if "/workflows/" in path:
                return {"workflow_runs": []}
            raise AssertionError(path)

        def file(self, path, ref="main"):
            calls.append(f"file {path}@{ref}")
            if path.endswith("qa-known-failures.yaml"):
                return "- ticket: PG-1\n  title: t\n  pipeline: x\n"
            return "mon: 14\nsat: 19\n"

    monkeypatch.setattr(collect, "GitHub", FakeGitHub)
    data = serve.live_source("x/y", tmp_path, use_jenkins=False)()
    assert len([c for c in calls if "/workflows/" in c]) == 1
    assert "file .github/qa-known-failures.yaml@main" in calls
    assert data["schedule"] == "Mon PG 14 → Sat PG 19" and data["warnings"] == []
    assert data["schedule_days"] == {"14": "Mon", "19": "Sat"}
    calls.clear()
    serve.live_source("x/y", tmp_path, use_jenkins=False, ref="my-branch")()
    assert "file .github/qa-known-failures.yaml@my-branch" in calls


def test_builds_without_a_result_are_not_run_not_failing():
    """PG 19's nightly: 26 SUCCESS, 13 FAILURE and 6 builds with no Jenkins
    result (scenarios that don't run yet). GitHub shows 13 failing jobs."""
    builds = (
        [build("pgsm-parallel", VERSION="ppg-19.0") for _ in range(26)]
        + [
            build(
                "docker-server-parallel",
                "FAILURE",
                f"WITH_POSTGIS={i % 2 == 0}",
                VERSION="ppg-19.0",
            )
            for i in range(13)
        ]
        + [
            dict(
                build(
                    "ppg-multiOS-parallel", None, f"IO_METHOD={io}", VERSION="ppg-19.0"
                ),
                build_url=None,
            )
            for io in ("worker", "sync", "io_uring") * 2
        ]
    )
    data = collect.build_dashboard([run(1, 14, builds)], [], NOW)
    pg19 = next(m for m in data["majors"] if m["major"] == "19")
    assert (pg19["failing"], pg19["total"], pg19["not_run"]) == (13, 39, 6)
    assert data["details"]["19"]["not_run"] == 6
    assert (
        len([f for f in data["failures"] if f["major"] == "19"]) == 13
    )  # not-run builds aren't failures


def test_a_running_nightlys_reports_are_downloaded_once(tmp_path):
    """Every read of a running nightly used to download all its reports again
    (~50, twice per refresh). Each artifact is now downloaded once."""

    class Nightly:
        def __init__(self):
            self.status, self.arts, self.downloads = "in_progress", 3, []

        def get(self, path):
            if "/workflows/" in path:
                return {
                    "workflow_runs": [
                        {
                            "id": 9,
                            "html_url": "u/9",
                            "event": "schedule",
                            "status": self.status,
                            "created_at": "2026-11-14T02:00:00Z",
                            "run_started_at": "2026-11-14T02:00:00Z",
                            "updated_at": "2026-11-14T03:00:00Z",
                        }
                    ]
                }
            if "/artifacts" in path:
                return {
                    "artifacts": [
                        {
                            "id": 100 + i,
                            "name": f"qa-report-{i}",
                            "created_at": "2026-11-14T02:30:00Z",
                            "archive_download_url": f"zip{i}",
                        }
                        for i in range(self.arts)
                    ]
                }
            if "/jobs" in path:
                return {
                    "jobs": [
                        {
                            "name": "OBS QA / ppg:staging:19 / server",
                            "status": "in_progress",
                        }
                    ]
                }
            raise AssertionError(path)

        def download(self, url):
            self.downloads.append(url)
            return _zip(
                {
                    "pipeline": "p",
                    "combos": [
                        {
                            "label": "default",
                            "params": {"VERSION": "ppg-19.0"},
                            "result": "SUCCESS",
                        }
                    ],
                }
            )

    gh = Nightly()
    collect.collect_runs(gh, tmp_path)
    collect.collect_runs(gh, tmp_path)  # the second read of the same refresh
    assert sorted(gh.downloads) == ["zip0", "zip1", "zip2"]  # once each
    gh.arts = 4  # a job finishes and uploads its report
    runs = collect.collect_runs(gh, tmp_path)
    assert gh.downloads.count("zip3") == 1 and len(runs[0]["builds"]) == 4
    gh.status = "completed"  # the nightly ends: cached as a whole, kept reports dropped
    collect.collect_runs(gh, tmp_path)
    assert (tmp_path / "run-9.json").is_file() and not (
        tmp_path / "run-9-artifacts"
    ).exists()


JENKINS_500 = (
    "Jenkins https://pg.cd.percona.com/job/ppg-multiOS-parallel/buildWithParameters: HTTP 500:\n"
    '<!DOCTYPE html><html data-disable-sticky="false"><head resURL="/static/bd8c26a7">'
)


def _zip_with_job(report, job):
    import io as _io
    import zipfile as _zf

    buf = _io.BytesIO()
    with _zf.ZipFile(buf, "w") as z:
        z.writestr("qa-report.json", json.dumps(report))
        if job:
            z.writestr("qa-job.txt", job)
    return buf.getvalue()


def test_error_is_one_readable_line():
    assert collect._short_error(JENKINS_500) == (
        "Jenkins https://pg.cd.percona.com/job/ppg-multiOS-parallel/buildWithParameters: HTTP 500"
    )
    assert collect._short_error(None) == ""
    assert (
        collect._short_error("<html>only a page</html>")
        == "Jenkins answered with an error page"
    )


def test_not_run_builds_link_to_their_github_job(tmp_path):
    """PG 19: Jenkins refused SCENARIO=pg-19-meta-server (HTTP 500). The
    major's page lists the build with the error and a link to its job."""

    class Run:
        def __init__(self):
            self.job_calls = 0

        def get(self, path):
            if "/workflows/" in path:
                return {
                    "workflow_runs": [
                        {
                            "id": 5,
                            "html_url": "https://gh/runs/5",
                            "event": "schedule",
                            "status": "completed",
                            "created_at": "2026-11-14T02:00:00Z",
                            "run_started_at": "2026-11-14T02:00:00Z",
                            "updated_at": "2026-11-14T04:00:00Z",
                        }
                    ]
                }
            if "/artifacts" in path:
                return {
                    "artifacts": [
                        {
                            "id": i,
                            "name": f"qa-report-{i}",
                            "created_at": "2026-11-14T03:00:00Z",
                            "archive_download_url": f"zip{i}",
                        }
                        for i in range(3)
                    ]
                }
            if "/jobs" in path:
                self.job_calls += 1
                return {
                    "jobs": [
                        {
                            "name": "OBS QA / ppg:staging:19 / server",
                            "html_url": "https://gh/runs/5/job/77",
                        },
                        {
                            "name": "OBS QA / ppg:staging:19 / upgrade",
                            "html_url": "https://gh/runs/5/job/78",
                        },
                    ]
                }
            raise AssertionError(path)

        def download(self, url):
            if url == "zip0":  # the server lane: one combo Jenkins refused
                return _zip_with_job(
                    {
                        "pipeline": "ppg-multiOS-parallel",
                        "combos": [
                            {
                                "label": "IO_METHOD=sync,SCENARIO=pg-19-meta-server",
                                "params": {"VERSION": "ppg-19.0"},
                                "result": None,
                                "error": JENKINS_500,
                            }
                        ],
                    },
                    "OBS QA / ppg:staging:19 / server",
                )
            if url == "zip1":  # an older report: no job name
                return _zip(
                    {
                        "pipeline": "tde-parallel",
                        "combos": [
                            {
                                "label": "default",
                                "params": {"VERSION": "ppg-19.0"},
                                "result": None,
                            }
                        ],
                    }
                )
            return _zip(
                {
                    "pipeline": "pgsm-parallel",
                    "combos": [
                        {
                            "label": "default",
                            "params": {"VERSION": "ppg-19.0"},
                            "result": "SUCCESS",
                        }
                    ],
                }
            )

    gh = Run()
    runs = collect.collect_runs(gh, tmp_path)
    assert gh.job_calls == 1
    collect.collect_runs(gh, tmp_path)  # finished and cached: no more calls
    assert gh.job_calls == 1
    details = collect.build_dashboard(runs, [], NOW)["details"]["19"]
    assert details["not_run"] == 2
    exact, fallback = sorted(details["not_run_builds"], key=lambda b: b["pipeline"])
    assert exact == {
        "label": "IO_METHOD=sync,SCENARIO=pg-19-meta-server",
        "pipeline": "ppg-multiOS-parallel",
        "error": "Jenkins https://pg.cd.percona.com/job/ppg-multiOS-parallel/buildWithParameters: HTTP 500",
        "job_url": "https://gh/runs/5/job/77",
        "exact_job": True,
    }
    assert fallback["job_url"] == "https://gh/runs/5" and not fallback["exact_job"]
    assert fallback["error"] == "No result recorded"


def _github_answers(monkeypatch, answers):
    """GitHub answers each request with the next item: an HTTP code (error)
    or a dict (JSON body). Returns the list of requested URLs."""
    import email.message
    import urllib.error
    import urllib.request

    calls = []

    class Body(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        answer = answers.pop(0)
        if isinstance(answer, tuple):
            code, headers = answer
        elif isinstance(answer, int):
            code, headers = answer, {}
        else:
            return Body(json.dumps(answer).encode())
        msg = email.message.Message()
        for k, v in headers.items():
            msg[k] = v
        raise urllib.error.HTTPError(req.full_url, code, "error", msg, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(collect.time, "sleep", lambda s: None)
    return calls


def test_github_502_is_retried(monkeypatch):
    calls = _github_answers(monkeypatch, [502, 503, {"ok": 1}])
    assert collect.GitHub("p/o", "t").get("actions/runs/1/jobs") == {"ok": 1}
    assert len(calls) == 3


def test_github_failing_for_good_names_the_request(monkeypatch):
    _github_answers(monkeypatch, [502, 502, 502])
    with pytest.raises(
        collect.GitHubError,
        match=r"GET actions/runs/1/jobs failed after 3 attempt\(s\): HTTP Error 502",
    ):
        collect.GitHub("p/o", "t").get("actions/runs/1/jobs")


def test_github_404_is_not_retried(monkeypatch):
    calls = _github_answers(monkeypatch, [404])
    with pytest.raises(collect.GitHubError, match="after 1 attempt"):
        collect.GitHub("p/o", "t").get("actions/runs/1")
    assert len(calls) == 1


def test_github_rate_limit_says_when_it_resets(monkeypatch):
    _github_answers(
        monkeypatch,
        [(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1794630600"})],
    )
    with pytest.raises(
        collect.GitHubError,
        match=r"rate limit reached for this token; it resets at \d\d:\d\d UTC",
    ):
        collect.GitHub("p/o", "t").get("actions/runs/1")


def test_known_failure_can_match_one_component():
    """PG-2914 (pg_repack's repack-check, PostgreSQL's pg_attver) affects every
    major, in component-generic-parallel, which runs all components under the
    label 'default': only pg_repack's failure is known."""
    known = [
        {
            "ticket": "PG-2914",
            "title": "repack-check",
            "major": [14, 15, 16, 17, 18],
            "pipeline": "^component-generic-parallel$",
            "params": {"PRODUCT": "^pg_repack$"},
        }
    ]
    repack = build(
        "component-generic-parallel", "FAILURE", PRODUCT="pg_repack", VERSION="ppg-18.7"
    )
    backrest = build(
        "component-generic-parallel",
        "FAILURE",
        PRODUCT="pgbackrest",
        VERSION="ppg-18.7",
    )
    assert collect.match_known(repack, "18", known)["ticket"] == "PG-2914"
    assert (
        collect.match_known(backrest, "18", known) is None
    )  # a real new failure stays new
    assert (
        collect.match_known(
            dict(repack, params={"PRODUCT": "pg_repack", "VERSION": "ppg-19.0"}),
            "19",
            known,
        )
        is None
    )


def _live_github(run_status, attempt=1, jobs=(), attempt_jobs=None):
    """A GitHub stub with one unfinished PG 19 run."""

    class G:
        calls = []

        def get(self, path):
            G.calls.append(path)
            if "/workflows/" in path:
                return {
                    "workflow_runs": [
                        {
                            "id": 63,
                            "html_url": "u/63",
                            "event": "workflow_dispatch",
                            "status": run_status,
                            "run_attempt": attempt,
                            "created_at": "2026-11-16T14:51:20Z",
                            "run_started_at": "2026-11-16T14:51:20Z",
                            "updated_at": "2026-11-16T15:30:00Z",
                        }
                    ]
                }
            if "/artifacts" in path:
                return {"artifacts": []}
            if "/attempts/" in path and path.split("?")[0].endswith("/jobs"):
                return {
                    "jobs": list(attempt_jobs if attempt_jobs is not None else jobs)
                }
            if "/jobs" in path:
                return {"jobs": list(jobs)}
            if "/attempts/1" in path:
                return {"run_started_at": "2026-11-16T14:51:20Z"}
            raise AssertionError(path)

    return G()


def _job(
    status, started="2026-11-16T15:05:00Z", name="OBS QA / ppg:staging:19 / server"
):
    return {"name": name, "status": status, "started_at": started}


def test_run_reported_queued_while_its_jobs_run_is_running(tmp_path):
    """GitHub can report a run as "queued" again while it works (its jobs in
    progress done, the next ones waiting for a runner). Started jobs make it
    running, timed from its first job, not from when GitHub created it."""
    gh = _live_github(
        "queued",
        jobs=[
            _job("completed", "2026-11-16T15:05:00Z"),
            _job(
                "in_progress",
                "2026-11-16T15:20:00Z",
                "OBS QA / ppg:staging:19 / pg_tde",
            ),
            _job("queued", None, "OBS QA / ppg:staging:19 / upgrade"),
        ],
    )
    data = collect.build_dashboard(collect.collect_runs(gh, tmp_path), [], NOW)
    assert data["queued"] == []
    assert [r["since"] for r in data["running"]] == ["2026-11-16T15:05:00Z"]


def test_run_with_no_started_job_stays_queued(tmp_path):
    gh = _live_github("queued", jobs=[_job("queued", None)])
    data = collect.build_dashboard(collect.collect_runs(gh, tmp_path), [], NOW)
    assert len(data["queued"]) == 1 and data["running"] == []
    assert data["queued"][0]["since"] == "2026-11-16T14:51:20Z"


def test_queued_rerun_ignores_the_earlier_attempts_finished_jobs(tmp_path):
    """A re-run of failed jobs keeps attempt 1's finished jobs in the run's job
    list; only the re-run's own jobs say whether it has started."""
    gh = _live_github(
        "queued",
        attempt=2,
        jobs=[_job("completed", "2026-11-16T02:05:00Z"), _job("queued", None)],
        attempt_jobs=[_job("queued", None)],
    )
    runs = collect.collect_runs(gh, tmp_path)
    assert any("/attempts/2/jobs" in c for c in gh.calls)
    assert runs[0]["jobs_started"] is False
    assert collect.is_queued(runs[0])


def component(product, result="SUCCESS", url=None, major="18"):
    """A component-generic-parallel build: every component has the label
    "default"; the report's package tells them apart."""
    b = build(
        "component-generic-parallel",
        result,
        url=url,
        PRODUCT=product,
        VERSION=f"ppg-{major}.7",
    )
    b["package"] = f"percona-{product}"
    b["project"] = f"isv:percona:ppg:staging:{major}"
    return b


def test_failing_since_stays_separate_per_component():
    """pg_repack has failed for 3 nights; credcheck only since the last one.
    With one key for every component-generic-parallel build, pg_repack's
    "failing since" stopped at credcheck's earlier passing build."""
    runs = [
        run(
            3, 6, [component("credcheck", "FAILURE"), component("pg_repack", "FAILURE")]
        ),
        run(2, 5, [component("credcheck"), component("pg_repack", "FAILURE")]),
        run(1, 4, [component("credcheck"), component("pg_repack", "FAILURE")]),
    ]
    data = collect.build_dashboard(runs, [], NOW)
    since = {f["title"]: f["since"] for f in data["failures"]}
    assert since == {
        "component-generic-parallel · credcheck": "6 Nov · 1 run",
        "component-generic-parallel · pg_repack": "4 Nov · 3 runs",
    }


def test_slowest_build_usually_compares_the_same_component():
    def builds(day, repack_s, credcheck_s):
        r = f"https://j/repack/{day}/"
        c = f"https://j/credcheck/{day}/"
        return [component("pg_repack", url=r), component("credcheck", url=c)], {
            r: {"duration_s": repack_s},
            c: {"duration_s": credcheck_s},
        }

    runs, info = [], {}
    for rid, (day, repack_s, credcheck_s) in enumerate(
        [(6, 3600, 60), (5, 1800, 60), (4, 1800, 60)], 1
    ):
        b, i = builds(day, repack_s, credcheck_s)
        runs.append(run(rid, day, b))
        info.update(i)
    slowest = collect.build_dashboard(runs, [], NOW, info)["details"]["18"]["slowest"]
    assert slowest == {
        "name": "component-generic-parallel · pg_repack",
        "duration": "1h 00m",
        "usual": "30m",  # pg_repack's own earlier runs, not credcheck's 1 minute
    }


def test_component_title_and_key_from_older_reports_use_product():
    """Reports written before the package field: PRODUCT names the component."""
    old = build("component-generic-parallel", PRODUCT="patroni")
    assert collect.build_title(old) == "component-generic-parallel · patroni"
    assert collect.build_key(old) != collect.build_key(
        build("component-generic-parallel", PRODUCT="pgbouncer")
    )
    tde = dict(component("pg_tde"), project="isv:percona:ppg:staging:16:tde")
    assert collect.project_of(tde) == "ppg:staging:16:tde"
    assert collect.build_key(tde) != collect.build_key(component("pg_tde", major="16"))


def test_skipped_and_broken_nights_are_shown():
    """A scheduled night without builds: skipped (nothing changed, the run
    succeeded) or failed before Jenkins. Last run stays the last with results."""
    schedule = {"fri": "18"}  # 6 and 13 Nov 2026 are Fridays
    skipped = run(3, 13, [])
    skipped["conclusion"] = "success"
    tested = run(2, 6, [build("tde-parallel")])
    data = collect.build_dashboard([skipped, tested], [], NOW, schedule=schedule)
    pg18 = next(m for m in data["majors"] if m["major"] == "18")
    assert [r["kind"] for r in pg18["runs"]] == ["skipped", "pass"]
    assert pg18["last_run"] == "Fri 6 Nov" and pg18["status"] == "pass"
    assert pg18["latest_night"] == {
        "date": "Fri 13 Nov",
        "kind": "skipped",
        "url": "https://github/run/3",
    }
    skipped["conclusion"] = "failure"
    pg18 = next(
        m
        for m in collect.build_dashboard([skipped, tested], [], NOW, schedule=schedule)[
            "majors"
        ]
        if m["major"] == "18"
    )
    assert pg18["latest_night"]["kind"] == "error"
    # a night the schedule doesn't know (no schedule read) is left out
    data = collect.build_dashboard([skipped, tested], [], NOW)
    assert [r["kind"] for r in data["majors"][4]["runs"]] == ["pass"]


def test_caches_keep_only_the_listed_runs(tmp_path):
    for rid in (1, 99):
        (tmp_path / f"run-{rid}.json").write_text("{}")
    (tmp_path / "run-99-artifacts").mkdir()
    (tmp_path / "run-99-artifacts" / "5.json").write_text("[]")
    (tmp_path / "jenkins-builds.json").write_text(
        json.dumps(
            {
                "https://j/1/": {"v": collect.JENKINS_CACHE_VERSION, "duration_s": 5},
                "https://j/old/": {"v": collect.JENKINS_CACHE_VERSION, "duration_s": 9},
            }
        )
    )
    gh = FakeGitHub(
        [
            {
                "id": 1,
                "html_url": "u/1",
                "event": "schedule",
                "status": "completed",
                "run_started_at": "2026-11-06T02:00:00Z",
                "created_at": "2026-11-06T02:00:00Z",
                "updated_at": "2026-11-06T03:00:00Z",
            }
        ]
    )
    runs = collect.collect_runs(gh, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "jenkins-builds.json",
        "run-1.json",
    ]
    info = collect.collect_build_info(
        collect.Jenkins(None, None, enabled=False), runs, tmp_path
    )
    assert list(info) == ["https://j/1/"]
    assert list(json.loads((tmp_path / "jenkins-builds.json").read_text())) == [
        "https://j/1/"
    ]


def test_files_from_main_fall_back_to_the_last_copy(tmp_path):
    class Down:
        def file(self, path, ref="main"):
            raise collect.GitHubError("GitHub read of x failed after 3 attempts")

    class Up:
        def file(self, path, ref="main"):
            return "- ticket: PG-1\n"

    warnings: list = []
    assert collect.repo_file(Down(), collect.KNOWN_FAILURES, tmp_path, warnings) is None
    assert (
        "Could not read .github/qa-known-failures.yaml from GitHub (main)"
        in warnings[0]
    )
    warnings.clear()
    assert collect.repo_file(Up(), collect.KNOWN_FAILURES, tmp_path, warnings)
    assert warnings == []
    text = collect.repo_file(Down(), collect.KNOWN_FAILURES, tmp_path, warnings)
    assert text == "- ticket: PG-1\n" and "Using the last copy read" in warnings[0]


def test_schedule_text():
    schedule = collect.parse_schedule("mon: 14\ntue: 15\nsat: 19\n# sun: none\n")
    assert schedule == {"mon": "14", "tue": "15", "sat": "19"}
    assert collect.schedule_text(schedule) == "Mon PG 14 → Sat PG 19"
    assert collect.schedule_text({}) == ""


def test_staging_and_devel_failures_are_kept_apart_and_show_their_project():
    """The nightly tests ppg:staging:<major> and ppg:devel:<major>: the same
    Jenkins job failing in both is two failures, each with its project."""

    def in_project(stage, result, url):
        b = build("ppg-multiOS-parallel", result, url=url, VERSION="ppg-19.0")
        b["project"] = f"isv:percona:ppg:{stage}:19"
        return b

    runs = [
        run(
            2,
            14,
            [
                in_project("staging", "FAILURE", "s2"),
                in_project("devel", "FAILURE", "d2"),
            ],
        ),
        run(
            1,
            7,
            [
                in_project("staging", "SUCCESS", "s1"),
                in_project("devel", "FAILURE", "d1"),
            ],
        ),
    ]
    data = collect.build_dashboard(runs, [], NOW)
    rows = {f["project"]: f["since"] for f in data["failures"]}
    assert rows == {
        "ppg:staging:19": "14 Nov · 1 run",
        "ppg:devel:19": "7 Nov · 2 runs",
    }
    assert data["details"]["19"]["projects"] == ["ppg:staging:19", "ppg:devel:19"]
    assert data["projects"] == ["ppg:staging", "ppg:devel"]
