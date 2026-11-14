"""Tests for the QA dashboard (tools/qa-dashboard)."""

import datetime as dt
import json
import re
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "qa-dashboard"))

import collect  # noqa: E402
import demo  # noqa: E402

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
    # the manual (OBS QA Run) run of 4 Nov is not part of the history
    assert [r["kind"] for r in pg18["runs"]] == ["pass", "known", "fail"]
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
    running.update(
        running_majors=["15"], qa_jobs={"total": 39, "done": 21, "failed": 1}
    )
    data = collect.build_dashboard(
        [running, run(1, 3, [build("tde-parallel", VERSION="ppg-15.19")])], [], NOW
    )
    assert [r["major"] for r in data["running"]] == ["15"] and data["running"][0][
        "done"
    ] == 21
    pg15 = next(m for m in data["majors"] if m["major"] == "15")
    assert pg15["status"] == "running" and pg15["progress"] == "21 / 39"
    assert pg15["runs"][-1]["kind"] == "running"


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


def test_demo_data_tells_the_mockup_story():
    data = collect.build_dashboard(
        demo.runs(NOW), demo.KNOWN, NOW, demo.build_info(NOW)
    )
    totals = {m["major"]: m["total"] for m in data["majors"]}
    assert totals == {"14": 33, "15": 39, "16": 40, "17": 46, "18": 53, "19": 45}
    pg18 = data["details"]["18"]
    assert pg18["slow"] and pg18["failing"] == 2 and pg18["new"] == 1
    assert pg18["slowest"]["name"] == "tde-auxiliary-parallel"
    assert [r["major"] for r in data["running"]] == ["15"]
    assert [(q["major"], q["rerun"]) for q in data["queued"]] == [("16", True)]
    assert sorted(f["ticket"] for f in data["failures"] if f["ticket"]) == [
        "PG-2883",
        "PG-2885",
        "PG-2886",
        "PG-2888",
    ]


def test_known_failures_file():
    entries = collect.load_known(ROOT / ".github" / "qa-known-failures.yaml")
    assert entries
    for e in entries:
        assert re.match(r"^PG-\d+$", e["ticket"]) and e.get("title")
        re.compile(e["pipeline"])
        re.compile(e.get("label") or ".")


def test_server_serves_page_and_demo_data():
    import serve

    state = serve.State()
    state.set(serve.demo_source())
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
        assert data["demo"] and len(data["majors"]) == 6 and data["error"] == ""
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
    )  # run 2: no QA reports (e.g. nothing planned)
    runs = collect.collect_runs(gh, tmp_path)
    assert [r["id"] for r in runs] == [1] and len(runs[0]["builds"]) == 1
    assert "[1/2] run 1 (completed): 1 build reports" in capsys.readouterr().err
    assert (tmp_path / "run-1.json").is_file() and (tmp_path / "run-2.json").is_file()
    gh.calls.clear()
    assert [r["id"] for r in collect.collect_runs(gh, tmp_path)] == [1]
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
        running_majors=["17"],
        qa_jobs={"total": 46, "done": 10, "failed": 0},
        attempt_started_at="2026-11-11T02:00:00Z",
    )
    data = collect.build_dashboard([pg17, pg15], [], NOW)
    assert [(r["major"], r["since"]) for r in data["running"]] == [
        ("17", "2026-11-11T02:00:00Z")
    ]
    assert [(q["major"], q["rerun"], q["since"]) for q in data["queued"]] == [
        ("15", True, "2026-11-11T05:50:00Z")
    ]
    assert data["queued"][0]["github_status"] == "queued"
    pg15row = next(m for m in data["majors"] if m["major"] == "15")
    assert pg15row["status"] == "queued" and "progress" not in pg15row
    assert pg15row["runs"][-1]["kind"] == "queued"


def test_queued_scheduled_run_gets_its_major_from_the_schedule(tmp_path):
    assert (
        collect.scheduled_major("2026-11-10T02:00:00Z", {"tue": 15}) == "15"
    )  # a Tuesday
    assert (
        collect.scheduled_major("2026-11-15T02:00:00Z", {"tue": 15}) is None
    )  # Sunday: nothing

    class QueuedGitHub:
        def get(self, path):
            if "/workflows/" in path:
                return {
                    "workflow_runs": [
                        {
                            "id": 5,
                            "html_url": "u/5",
                            "event": "schedule",
                            "status": "queued",
                            "created_at": "2026-11-10T02:00:00Z",
                            "updated_at": "2026-11-10T02:00:01Z",
                        }
                    ]
                }
            if path.endswith("/artifacts?per_page=100"):
                return {"artifacts": []}
            if "/jobs" in path:
                return {"jobs": []}  # nothing planned yet
            raise AssertionError(path)

    runs = collect.collect_runs(QueuedGitHub(), tmp_path, schedule={"tue": 15})
    assert runs[0]["running_majors"] == ["15"]
    data = collect.build_dashboard(runs, [], NOW)
    assert [q["major"] for q in data["queued"]] == ["15"] and data["running"] == []


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
    assert [r["kind"] for r in pg15["runs"]] == ["pass", "queued"]


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
    running = run(2, 13, [], status="in_progress")
    running.update(
        started_at="2026-11-14T02:00:00Z",
        attempt_started_at="2026-11-14T02:00:00Z",
        running_majors=["19"],
        qa_jobs={"total": 45, "done": 12, "failed": 1},
    )
    waiting = run(3, 13, [], status="queued")
    waiting.update(
        started_at="2026-11-14T03:05:00Z",
        attempt_started_at="2026-11-14T03:05:00Z",
        running_majors=["19"],
    )
    data = collect.build_dashboard([waiting, running, done], [], NOW)
    pg19 = next(m for m in data["majors"] if m["major"] == "19")
    assert pg19["status"] == "running" and pg19["progress"] == "12 / 45"
    assert [(r["major"], r["done"]) for r in data["running"]] == [("19", 12)]
    assert [q["major"] for q in data["queued"]] == ["19"]


def test_status_is_read_again_after_the_slow_jenkins_step(tmp_path, monkeypatch):
    """PG 19's scheduled nightly is queued at 02:00 UTC, while a refresh reads
    the runs; it starts while Jenkins is being asked about builds. The
    published status must be 'running', not the stale 'queued'."""
    import serve

    state = {"status": "queued"}

    class FakeGitHub:
        def __init__(self, *a):
            pass

        def get(self, path):
            if "/workflows/" in path:
                return {
                    "workflow_runs": [
                        {
                            "id": 77,
                            "html_url": "u/77",
                            "event": "schedule",
                            "status": state["status"],
                            "created_at": "2026-11-14T02:00:00Z",
                            "run_started_at": "2026-11-14T02:00:00Z",
                            "updated_at": "2026-11-14T02:01:00Z",
                        }
                    ]
                }
            if "/artifacts" in path:
                return {"artifacts": []}
            if "/jobs" in path:
                return {
                    "jobs": [
                        {
                            "name": "OBS QA / ppg:staging:19 / server",
                            "status": (
                                "in_progress"
                                if state["status"] == "in_progress"
                                else "queued"
                            ),
                        }
                    ]
                }
            raise AssertionError(path)

    class SlowJenkins:
        available = True

        def __init__(self, *a, **k):
            pass

    def jenkins_step(jenkins, runs, cache_dir):
        state["status"] = "in_progress"  # the run starts meanwhile
        return {}

    monkeypatch.setattr(collect, "GitHub", FakeGitHub)
    monkeypatch.setattr(collect, "Jenkins", SlowJenkins)
    monkeypatch.setattr(collect, "collect_build_info", jenkins_step)
    data = serve.live_source("x/y", tmp_path, tmp_path / "none.yaml")()
    pg19 = next(m for m in data["majors"] if m["major"] == "19")
    assert (
        pg19["status"] == "running"
        and [r["major"] for r in data["running"]] == ["19"]
        and data["queued"] == []
    )
