#!/usr/bin/env python3
"""Collect the data shown by the PPG QA dashboard (data.json).

Sources:
- GitHub Actions: the OBS Nightly QA and OBS QA Run workflow runs, their
  qa-report-* artifacts (one per Jenkins build: pipeline, combo, parameters,
  build URL, result) and, for a run in progress, its job list (progress).
- Jenkins: for builds shown in detail, the build's duration and which
  platform stages failed (best effort: shown without them if Jenkins can't be
  reached).
- .github/qa-known-failures.yaml: failures with an open ticket (amber).

build_dashboard() turns the collected runs into the dashboard's data and is
pure (no network), so it is tested on its own. Finished runs and finished
Jenkins builds never change, so they are cached on disk; a refresh only
fetches new or running runs.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import io
import json
import os
import re
import shutil
import statistics
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

REPO = "percona/obs-packaging"
NIGHTLY = "obs-nightly-qa.yml"
# Only the nightly: manual OBS QA Run runs test whatever someone picked, so
# they would distort each major's history, status and counts.
WORKFLOWS = (NIGHTLY,)
CACHE_VERSION = 5  # bump when the cached run format changes: re-read once
JENKINS_CACHE_VERSION = 2  # bump when what is kept per Jenkins build changes
JENKINS_WORKERS = 8  # Jenkins builds asked at the same time
RUNS_LISTED = 40  # newest runs read per refresh; older cache files are removed
KNOWN_FAILURES = ".github/qa-known-failures.yaml"  # read from main on GitHub
SCHEDULE = ".github/nightly-qa-schedule.yml"  # read from main on GitHub
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MAJORS = ("14", "15", "16", "17", "18", "19")
RUNS_SHOWN = 5  # last runs per major (nightly and manual)
SLOW_FACTOR = 1.5  # run flagged when this many times the median
REFRESH_MINUTES = 10
# Where a known failure's ticket links to; an entry's own "url" wins.
TICKET_URL = os.environ.get(
    "QA_DASHBOARD_TICKET_URL", "https://perconadev.atlassian.net/browse/{ticket}"
)
QA_JOB_PREFIX = "OBS QA /"  # matrix jobs are named "OBS QA / <project> / ..."
OK_RESULTS = ("SUCCESS",)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def log(message: str) -> None:
    """Progress, on stderr (stdout stays for the final summary)."""
    print(message, file=sys.stderr, flush=True)


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def major_of(params: dict[str, Any], label: str = "") -> str | None:
    """The PG major a build belongs to. Upgrades count toward the major
    they upgrade into (NEW_SERVER_VERSION / TO_VERSION)."""
    for key in (
        "NEW_SERVER_VERSION",
        "TO_VERSION",
        "VERSION",
        "SERVER_VERSION",
        "DOCKER_TAG",
    ):
        value = str(params.get(key) or "")
        m = re.match(r"^(?:ppg-|psp-)?(1\d)(?:\.|$)", value)
        if m:
            return m.group(1)
    m = re.search(r":staging:(1\d)(?::|$)", str(params.get("OBS_PROJECT") or ""))
    if m:
        return m.group(1)
    m = re.search(r"pg-?(1\d)\b", label)
    return m.group(1) if m else None


def old_major_of(params: dict[str, Any]) -> str:
    for key in ("OLD_SERVER_VERSION", "FROM_VERSION"):
        m = re.match(r"^(?:ppg-)?(1\d)(?:\.|$)", str(params.get(key) or ""))
        if m:
            return m.group(1)
    return ""


def component_of(build: dict[str, Any]) -> str:
    """The package a package-lane build tests (its qa: entry's package, e.g.
    percona-pg_repack), "" for a project's own builds. component-generic-parallel
    runs every component under the label "default": without this they would
    all be the same build. Older reports have no package: PRODUCT names it."""
    params = build["params"]
    return str(
        build.get("package") or params.get("PRODUCT") or params.get("COMPONENT") or ""
    )


def project_of(build: dict[str, Any]) -> str:
    """The build's OBS project from ppg: on (ppg:staging:19, ppg:devel:19,
    ppg:staging:16:tde, ...): the nightly tests both staging and devel
    projects, so the same Jenkins job can fail in either. "" if unknown."""
    project = str(build.get("project") or "")
    m = re.search(r"(?:^|:)(ppg:.+)$", project)
    return m.group(1) if m else project


def main_projects(builds: list[dict[str, Any]], major: str) -> list[str]:
    """The major's own projects these builds come from: ppg:staging:<major>,
    ppg:devel:<major> (not their subprojects, nor shared ones)."""
    found = set()
    for b in builds:
        m = re.match(r"(ppg:[a-z]+:%s)(?::|$)" % re.escape(major), project_of(b))
        if m:
            found.add(m.group(1))
    return sorted(found, key=lambda p: (not p.startswith("ppg:staging:"), p))


def build_key(build: dict[str, Any]) -> str:
    """Identifies 'the same build' across runs (versions change, this
    doesn't): Jenkins job, OBS project, component, combo label and, for
    upgrades, the old major."""
    return "|".join(
        [
            build["pipeline"],
            project_of(build),
            component_of(build),
            build.get("label") or "default",
            old_major_of(build["params"]),
        ]
    )


def build_title(build: dict[str, Any]) -> str:
    params = build["params"]
    parts = [build["pipeline"]]
    component = component_of(build)
    if component:
        parts.append(component.removeprefix("percona-"))
    old = old_major_of(params)
    new = major_of(params, build.get("label") or "")
    if old and new and old != new:
        parts.append(f"{old} → {new}")
    label = build.get("label") or ""
    if label and label != "default":
        parts.append(label.replace(",", " · "))
    return " · ".join(parts)


def platforms_of(params: dict[str, Any]) -> list[str]:
    value = params.get("PLATFORMS") or []
    if isinstance(value, str):
        value = [v for v in re.split(r"[\s,]+", value) if v]
    return [str(v) for v in value]


# The PPG Jenkins jobs run one stage per platform, named exactly after it
# (moleculeParallelTestPPG: stage("${os}"), e.g. "debian-12", "rocky-8-arm").
PLATFORM_STAGE = re.compile(
    r"^(?:debian|ubuntu|rocky|ol|rhel|oraclelinux|centos|alma)-[a-z0-9.]+(?:-arm)?$"
)


def failed_platforms_from(failed_stages: list[str], platforms: list[str]) -> list[str]:
    """Platforms whose stage failed. Stage names equal platform names, so
    match exactly (rocky-8-arm failing doesn't make rocky-8 fail). Jobs
    without a PLATFORMS parameter (e.g. the upgrade jobs) use their own
    default platforms: take the failed stages that look like platforms."""
    if platforms:
        return [p for p in platforms if p in failed_stages]
    return [name for name in failed_stages if PLATFORM_STAGE.match(name)]


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "–"
    minutes = int(round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def fmt_date(value: dt.datetime) -> str:
    return f"{value:%a} {value.day} {value:%b}"


def short_date(value: dt.datetime) -> str:
    return f"{value.day} {value:%b}"


# ---------------------------------------------------------------------------
# known failures
# ---------------------------------------------------------------------------


def parse_known(text: str) -> list[dict[str, Any]]:
    import yaml  # PyYAML, in obs-packaging's requirements.txt

    entries = yaml.safe_load(text) or []
    return [e for e in entries if isinstance(e, dict) and e.get("ticket")]


def load_known(path: Path) -> list[dict[str, Any]]:
    return parse_known(path.read_text(encoding="utf-8")) if path.is_file() else []


def parse_schedule(text: str) -> dict[str, str]:
    """{weekday: major} from nightly-qa-schedule.yml."""
    import yaml

    data = yaml.safe_load(text) or {}
    return {d: str(data[d]) for d in WEEKDAYS if data.get(d) is not None}


def match_known(
    build: dict[str, Any], major: str, known: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The known-failures entry covering this failed build, if any. An entry
    matches on major (optional), Jenkins job (regex), combo label or
    scenario (regex, optional) and Jenkins parameters (regex per parameter,
    optional: e.g. PRODUCT for the component jobs, which run every component
    under the label 'default')."""
    label = build.get("label") or ""
    scenario = str(build["params"].get("SCENARIO") or "")
    for entry in known:
        majors = entry.get("major")
        if majors is not None:
            majors = majors if isinstance(majors, list) else [majors]
            if major not in [str(x) for x in majors]:
                continue
        if not re.search(str(entry.get("pipeline", ".")), build["pipeline"]):
            continue
        pattern = entry.get("label")
        if pattern and not re.search(str(pattern), f"{label} {scenario}"):
            continue
        wanted = entry.get("params") or {}
        if any(
            not re.search(str(regex), str(build["params"].get(name, "")))
            for name, regex in wanted.items()
        ):
            continue
        return entry
    return None


# ---------------------------------------------------------------------------
# the dashboard data (pure)
# ---------------------------------------------------------------------------


QUEUED_STATUSES = ("queued", "waiting", "requested", "pending")


def is_queued(run: dict[str, Any]) -> bool:
    """Not started yet. GitHub's own status is not enough: it reports a run
    that is working as "queued" again whenever its next jobs wait for a
    runner. A run is queued only while none of its current attempt's jobs
    has started (collect_runs reads that from the attempt's job list)."""
    return run.get("status") in QUEUED_STATUSES and not run.get("jobs_started")


def has_results(run: dict[str, Any]) -> bool:
    """Finished with builds, or a re-run (queued or running) of a finished
    attempt, whose results stand until the re-run replaces them."""
    if run.get("status") == "completed":
        return bool(run.get("builds"))
    return (
        (run.get("attempt") or 1) > 1
        and bool(run.get("builds"))
        and bool(run.get("finished_at"))
    )


def no_builds(run: dict[str, Any]) -> bool:
    """A finished run without QA builds: a scheduled night skipped because
    nothing changed (it succeeds), or a run that failed before Jenkins."""
    return run.get("status") == "completed" and not run.get("builds")


def scheduled_major(run: dict[str, Any], schedule: dict[str, str]) -> str | None:
    """The major a scheduled run was for: the schedule's major for its UTC
    weekday. Only used for runs without builds (their builds say it)."""
    when = parse_time(run.get("started_at"))
    return schedule.get(WEEKDAYS[when.weekday()]) if when else None


def schedule_text(schedule: dict[str, str]) -> str:
    """'Mon PG 14 → Sat PG 19' from the schedule file, so the page can't drift
    from it."""
    days = [d for d in WEEKDAYS if d in schedule]
    if not days:
        return ""
    first, last = days[0], days[-1]
    return f"{first.title()} PG {schedule[first]} → {last.title()} PG {schedule[last]}"


def run_seconds(run: dict[str, Any]) -> float | None:
    """From the run's start to its end; None while it hasn't finished."""
    start, end = parse_time(run.get("started_at")), parse_time(run.get("finished_at"))
    return (end - start).total_seconds() if start and end else None


def _not_run(build: dict[str, Any]) -> bool:
    """No Jenkins result: the build wasn't run (e.g. a scenario that skips
    itself) or its result wasn't recorded. Its GitHub job passes."""
    return build.get("result") is None


def _is_failed(build: dict[str, Any]) -> bool:
    return not _not_run(build) and build.get("result") not in OK_RESULTS


def build_dashboard(
    runs: list[dict[str, Any]],
    known: list[dict[str, Any]],
    now: dt.datetime,
    build_info: dict[str, dict[str, Any]] | None = None,
    schedule: dict[str, str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """runs: newest first, each {id, url, event, status, conclusion,
    started_at, finished_at, builds: [{pipeline, project, package, label,
    params, result, build_url}], qa_jobs: {total, done, failed} (unfinished
    runs)}. build_info: build_url -> {duration_s, failed_platforms} from
    Jenkins. schedule: {weekday: major} (nightly-qa-schedule.yml)."""
    build_info = build_info or {}
    schedule = schedule or {}
    runs = [r for r in runs if r.get("workflow", NIGHTLY) == NIGHTLY]
    per_major: dict[str, list[dict[str, Any]]] = {m: [] for m in MAJORS}
    running: list[dict[str, Any]] = []
    queued: list[dict[str, Any]] = []
    for run in runs:
        if no_builds(run):
            m = scheduled_major(run, schedule) if run["event"] == "schedule" else None
            if m in per_major:
                per_major[m].append(dict(run, builds=[], major=m))
            continue
        groups: dict[str, list[dict[str, Any]]] = {}
        for b in run.get("builds", []):
            m = major_of(b["params"], b.get("label") or "")
            if m in per_major:
                groups.setdefault(m, []).append(b)
        for m, builds in groups.items():
            per_major[m].append(dict(run, builds=builds, major=m))
        if run["status"] != "completed":
            # Every unfinished nightly, not just the newest: one started by
            # hand can run while the scheduled one waits behind it. Its majors
            # are known once its first builds have reported.
            jobs = run.get("qa_jobs") or {}
            (queued if is_queued(run) else running).append(
                {
                    "majors": sorted(groups),
                    "url": run["url"],
                    # the current attempt: a re-run's own start; for a running
                    # one, when its first job started (a run can wait for a
                    # runner well after GitHub created it)
                    "since": (None if is_queued(run) else run.get("jobs_started_at"))
                    or run.get("attempt_started_at")
                    or run["started_at"],
                    "rerun": (run.get("attempt") or 1) > 1,
                    "github_status": run.get("status", ""),
                    "done": jobs.get("done", 0),
                    "total": jobs.get("total", 0),
                    "failing": jobs.get("failed", 0),
                }
            )

    def run_kind(run: dict[str, Any], major: str) -> str:
        if run["status"] != "completed":
            return "queued" if is_queued(run) else "running"
        if no_builds(run):
            return "skipped" if run.get("conclusion") == "success" else "error"
        failed = [b for b in run["builds"] if _is_failed(b)]
        if not failed:
            return "pass"
        if all(match_known(b, major, known) for b in failed):
            return "known"
        return "fail"

    def started(r: dict[str, Any]) -> dt.datetime:
        return parse_time(r["started_at"]) or now

    majors_out, failures_out, details = [], [], {}
    for m in MAJORS:
        mruns = per_major[m]
        if not mruns:
            majors_out.append({"major": m, "status": "none", "runs": []})
            continue
        completed = [r for r in mruns if has_results(r)]
        shown = mruns[:RUNS_SHOWN]
        last = completed[0] if completed else None
        durations = [
            s for s in map(run_seconds, completed[:RUNS_SHOWN]) if s is not None
        ]
        median = statistics.median(durations) if durations else None
        last_duration = durations[0] if durations else None
        slow = bool(median and last_duration and last_duration >= SLOW_FACTOR * median)

        failing = [b for b in (last["builds"] if last else []) if _is_failed(b)]
        new = [b for b in failing if not match_known(b, m, known)]
        unfinished = [r for r in mruns if r["status"] != "completed"]
        active = next((r for r in unfinished if not is_queued(r)), None)
        if active is not None:
            status = "running"
        elif unfinished:
            status = "queued"
        elif last is None:
            status = "none"
        else:
            status = "fail" if new else ("known" if failing else "pass")

        major_row = {
            "major": m,
            "status": status,
            "failing": len(failing),
            "new": len(new),
            # builds that ran; the ones without a result are counted apart
            "total": len([b for b in last["builds"] if not _not_run(b)]) if last else 0,
            "not_run": len([b for b in last["builds"] if _not_run(b)]) if last else 0,
            "last_run": fmt_date(started(last)) if last else "–",
            "last_run_url": last["url"] if last else "",
            # the newest night when it ran no build: skipped (nothing changed)
            # or failed before Jenkins; "last run" stays the last with results
            "latest_night": (
                {
                    "date": fmt_date(started(mruns[0])),
                    "kind": run_kind(mruns[0], m),
                    "url": mruns[0]["url"],
                }
                if no_builds(mruns[0])
                else None
            ),
            "runtime": fmt_duration(last_duration),
            "median": fmt_duration(median),
            "slow": slow,
            "slow_pct": (
                round((last_duration / median - 1) * 100)
                if slow and median and last_duration
                else 0
            ),
            # newest first
            "runs": [
                {
                    "date": short_date(started(r))
                    + ("" if r["event"] == "schedule" else " (manual)"),
                    "kind": run_kind(r, m),
                    "url": r["url"],
                }
                for r in shown
            ],
        }
        if active is not None:
            jobs = active.get("qa_jobs") or {}
            major_row["progress"] = f"{jobs.get('done', 0)} / {jobs.get('total', 0)}"
            major_row["total"] = jobs.get("total", 0) or major_row["total"]
        majors_out.append(major_row)

        # failing now, with "failing since"
        detail_failing = []
        for b in failing:
            key = build_key(b)
            since, count = None, 0
            for r in completed:
                same = [x for x in r["builds"] if build_key(x) == key]
                if not same:
                    continue  # not part of that run (e.g. a narrower manual run)
                if not _is_failed(same[0]):
                    break
                since, count = started(r), count + 1
            entry = match_known(b, m, known)
            info = build_info.get(b.get("build_url") or "", {})
            platforms = platforms_of(b["params"])
            failed_platforms = info.get("failed_platforms")  # None: unknown
            if info.get("missing"):
                platform_note = "This build is no longer kept in Jenkins"
            elif failed_platforms is None:
                platform_note = (
                    "Which platforms failed is not known (no data from Jenkins)"
                )
            elif not failed_platforms:
                platform_note = (
                    "Failed outside the platform stages (e.g. setup or clean-up)"
                )
            else:
                n = len(failed_platforms)
                platform_note = (
                    f"{n} of {len(platforms)} platforms failed"
                    if platforms
                    else f"{n} platform{'s' if n != 1 else ''} failed"
                )
            item = {
                "major": m,
                "is_new": entry is None,
                "ticket": entry["ticket"] if entry else "",
                "ticket_url": (
                    (entry.get("url") or TICKET_URL.format(ticket=entry["ticket"]))
                    if entry
                    else ""
                ),
                "title": (entry or {}).get("title") or build_title(b),
                "project": project_of(b),
                "job": build_title(b) if entry else b["pipeline"],
                "platforms": ", ".join(failed_platforms or []) or "platforms unknown",
                "since": (
                    f"{short_date(since)} · {count} run{'s' if count != 1 else ''}"
                    if since
                    else "–"
                ),
                "build_url": b.get("build_url") or "",
                "build": (
                    "#" + (b.get("build_url") or "").rstrip("/").rsplit("/", 1)[-1]
                    if b.get("build_url")
                    else ""
                ),
                "failed_platforms": failed_platforms or [],
                "platform_note": platform_note,
            }
            failures_out.append(item)
            detail_failing.append(item)

        # detail page: run times, per-job matrix, slowest build
        recent = completed[:RUNS_SHOWN][::-1]
        runtimes = []
        for r in recent:
            secs = run_seconds(r)
            runtimes.append(
                {
                    "date": short_date(started(r))
                    + ("" if r["event"] == "schedule" else " (manual)"),
                    "label": fmt_duration(secs),
                    "minutes": round(secs / 60) if secs else 0,
                    "slow": bool(median and secs and secs >= SLOW_FACTOR * median),
                }
            )
        slowest = None
        for b in last["builds"] if last else []:
            d = build_info.get(b.get("build_url") or "", {}).get("duration_s")
            if d and (slowest is None or d > slowest[1]):
                slowest = (b, d)
        slowest_out = None
        if slowest:
            usual = [
                build_info.get(x.get("build_url") or "", {}).get("duration_s")
                for r in completed[1:RUNS_SHOWN]
                for x in r["builds"]
                if build_key(x) == build_key(slowest[0])
            ]
            usual = [u for u in usual if u]
            slowest_out = {
                "name": build_title(slowest[0]),
                "duration": fmt_duration(slowest[1]),
                "usual": fmt_duration(statistics.median(usual)) if usual else "",
            }
        details[m] = {
            "major": m,
            "last_run": major_row["last_run"],
            "last_run_window": (
                (
                    f"{started(last):%H:%M} → {parse_time(last['finished_at']):%H:%M} UTC · "
                    + ("nightly" if last["event"] == "schedule" else "manual")
                )
                if last and last.get("finished_at")
                else ""
            ),
            "failing": len(failing),
            "new": len(new),
            "known_tickets": sorted(
                {f["ticket"] for f in detail_failing if f["ticket"]}
            ),
            "total": major_row["total"],
            "not_run": major_row["not_run"],
            "not_run_builds": [
                {
                    "label": b.get("label") or "default",
                    "pipeline": b["pipeline"],
                    "error": b.get("error") or "No result recorded",
                    # the job when its report names it, else the run
                    "job_url": b.get("job_url") or (last["url"] if last else ""),
                    "exact_job": bool(b.get("job_url")),
                }
                for b in (last["builds"] if last else [])
                if _not_run(b)
            ],
            "runtime": major_row["runtime"],
            "median": major_row["median"],
            "slow": slow,
            "slow_pct": major_row["slow_pct"],
            "slowest": slowest_out,
            "median_minutes": round(median / 60) if median else 0,
            "runtimes": runtimes,
            "failing_builds": detail_failing,
            # where the last runs' builds come from (staging, devel or both)
            "projects": main_projects(
                [b for r in completed[:RUNS_SHOWN] for b in r["builds"]], m
            ),
        }

    failures_out.sort(key=lambda f: (not f["is_new"], -int(f["major"])))
    return {
        "generated_at": iso(now),
        "refresh_minutes": REFRESH_MINUTES,
        "repo": REPO,
        "schedule": schedule_text(schedule),
        # project families the shown runs tested: ["ppg:staging", "ppg:devel"]
        "projects": sorted(
            {
                ":".join(p.split(":")[:2])
                for m in MAJORS
                for p in (details.get(m) or {}).get("projects", [])
            },
            key=lambda p: (p != "ppg:staging", p),
        ),
        "schedule_days": {major: day.title() for day, major in schedule.items()},
        # problems that don't stop the refresh (e.g. known failures unreadable)
        "warnings": list(warnings or []),
        "running": running,  # every nightly in progress
        "queued": queued,  # nightlies waiting to start (e.g. behind another run)
        "majors": majors_out,
        "failures": failures_out,
        "details": details,
    }


# ---------------------------------------------------------------------------
# collecting (network)
# ---------------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


class GitHubError(Exception):
    """A GitHub request that failed for good (after retries), with what it was."""


class GitHub:
    # waits between attempts: GitHub answers 502/503 now and then, and one
    # failed request must not throw a whole refresh away
    RETRY_DELAYS = (2, 5)

    def __init__(self, repo: str, token: str | None) -> None:
        self.repo = repo
        self.token = token

    def _request(self, url: str, auth: bool = True) -> urllib.request.Request:
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.github+json"}
        )
        if auth and self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        return req

    def get(self, path: str) -> Any:
        url = (
            path
            if path.startswith("http")
            else f"https://api.github.com/repos/{self.repo}/{path}"
        )

        def fetch() -> Any:
            with urllib.request.urlopen(self._request(url), timeout=60) as resp:
                return json.load(resp)

        return self._retrying(fetch, f"GET {path}")

    def file(self, path: str, ref: str = "main") -> str:
        """A file of the repository as it is on ref (the contents API)."""
        url = f"https://api.github.com/repos/{self.repo}/contents/{path}?ref={ref}"

        def fetch() -> str:
            req = self._request(url)
            req.add_header("Accept", "application/vnd.github.raw")
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8")

        return self._retrying(fetch, f"read of {path}")

    def download(self, url: str) -> bytes:
        def fetch() -> bytes:
            # The archive URL redirects to storage that must not get our token.
            opener = urllib.request.build_opener(_NoRedirect)
            try:
                with opener.open(self._request(url), timeout=120) as resp:
                    return resp.read()
            except urllib.error.HTTPError as err:
                location = err.headers.get("Location")
                if err.code in (301, 302, 303, 307, 308) and location:
                    with urllib.request.urlopen(
                        self._request(location, auth=False), timeout=120
                    ) as resp:
                        return resp.read()
                raise

        return self._retrying(fetch, "download of a QA report")

    def _retrying(self, fetch: Any, what: str) -> Any:
        """Run fetch, retrying what may pass on a second try: server errors,
        429, timeouts and dropped connections. Others (404...) fail at once."""
        for attempt, delay in enumerate((*self.RETRY_DELAYS, None), 1):
            try:
                return fetch()
            except urllib.error.HTTPError as err:
                if err.code == 403 and err.headers.get("X-RateLimit-Remaining") == "0":
                    reset = err.headers.get("X-RateLimit-Reset", "")
                    when = (
                        dt.datetime.fromtimestamp(int(reset), dt.timezone.utc).strftime(
                            "%H:%M UTC"
                        )
                        if reset.isdigit()
                        else "later"
                    )
                    raise GitHubError(
                        f"GitHub rate limit reached for this token; it resets at {when}"
                    ) from err
                if delay is None or not (err.code >= 500 or err.code == 429):
                    raise GitHubError(
                        f"GitHub {what} failed after {attempt} attempt(s): {err}"
                    ) from err
            except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
                if delay is None:
                    raise GitHubError(
                        f"GitHub {what} failed after {attempt} attempts: {err}"
                    ) from err
            log(f"  GitHub {what}: attempt {attempt} failed, retrying in {delay}s")
            time.sleep(delay)
        raise AssertionError("unreachable")


class Jenkins:
    def __init__(
        self, user: str | None, token: str | None, enabled: bool = True
    ) -> None:
        # False after a connection failure: one unreachable Jenkins must not
        # make every build wait for its own timeout.
        self.available = enabled
        self.user = user
        self.auth = None
        if user and token:
            import base64

            self.auth = "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()

    def _get(self, url: str) -> Any:
        req = urllib.request.Request(url)
        if self.auth:
            req.add_header("Authorization", self.auth)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)

    def build_info(self, build_url: str, platforms: list[str]) -> dict[str, Any] | None:
        """Duration and failed platforms of a finished build; None if
        Jenkins can't be reached or the build is still running."""
        base = build_url.rstrip("/") + "/"
        if not self.available:
            return None
        try:
            info = self._get(base + "api/json?tree=building,duration,result")
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                self.available = False
                log(
                    f"Jenkins refused access ({err.code}) to {err.url},"
                    + (
                        f" logged in as {self.user}: check that user's access to this job."
                        if self.auth
                        else " without a login: set JENKINS_USER and JENKINS_TOKEN."
                    )
                    + " Continuing without build durations and failing platforms."
                )
                return None
            if err.code == 404:
                # Jenkins keeps a limited history and deletes old builds:
                # remember it, so it isn't asked again at every refresh.
                return {"missing": True}
            return None
        except (urllib.error.URLError, OSError, ValueError) as err:
            self.available = False
            log(
                f"Jenkins not reachable ({err}): continuing without build durations"
                " and failing platforms for this refresh."
            )
            return None
        if info.get("building"):
            return None
        out: dict[str, Any] = {"duration_s": (info.get("duration") or 0) / 1000}
        if info.get("result") not in OK_RESULTS:
            try:
                stages = self._get(base + "wfapi/describe").get("stages", [])
                failed = [
                    s.get("name", "")
                    for s in stages
                    if s.get("status") in ("FAILED", "UNSTABLE")
                ]
                out["failed_platforms"] = failed_platforms_from(failed, platforms)
            except (urllib.error.URLError, OSError, ValueError):
                pass
        return out


def _reports_from_zip(data: bytes) -> list[dict[str, Any]]:
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        # the GitHub job's name (its matrix status_context), written by the
        # workflow next to the report: links a build to its job
        job = next(
            (zf.read(n).decode().strip() for n in names if n.endswith("qa-job.txt")), ""
        )
        for name in names:
            if name.endswith(".json"):
                report = json.loads(zf.read(name))
                if job:
                    report["job"] = job
                out.append(report)
    return out


def _short_error(error: str | None) -> str:
    """A build's error as one readable line: Jenkins answers errors with an
    HTML page, so keep the text before it."""
    if not error:
        return ""
    text = error.split("<", 1)[0].strip().rstrip(":").strip()
    return (text or "Jenkins answered with an error page")[:300]


def _artifact_reports(
    gh: Any, artifact: dict[str, Any], folder: Path
) -> list[dict[str, Any]]:
    """An artifact's QA reports. GitHub never changes an uploaded artifact, so
    each is downloaded once and kept (by id) while its run is unfinished:
    otherwise every refresh downloaded a running nightly's ~50 reports again."""
    art_id = artifact.get("id")
    path = folder / f"{art_id}.json"
    if art_id is not None and path.is_file():
        return json.loads(path.read_text())
    reports = _reports_from_zip(gh.download(artifact["archive_download_url"]))
    if art_id is not None:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(reports))
    return reports


def get_all(gh: Any, path: str, key: str, per_page: int = 100) -> list[Any]:
    """Every item of a paginated GitHub list, not just the first page: a
    nightly re-run several times has well over 100 artifacts, and the newest
    (the re-runs' results) are not on the first page."""
    items: list[Any] = []
    for page in range(1, 51):  # up to 5,000 items
        suffix = f"?per_page={per_page}" + (f"&page={page}" if page > 1 else "")
        data = gh.get(path + suffix)
        batch = data.get(key, [])
        items += batch
        total = data.get("total_count")
        if len(batch) < per_page or (total is not None and len(items) >= total):
            break
    return items


def repo_file(
    gh: GitHub, path: str, cache_dir: Path, warnings: list[str], ref: str = "main"
) -> str | None:
    """A file from a branch on GitHub (main), so that merging a change to it
    is enough (no pull or restart on the dashboard host). When GitHub can't
    be read, the last copy read is used, with a warning; None if there is
    none."""
    copy = cache_dir / Path(path).name
    try:
        text = gh.file(path, ref)
    except GitHubError as err:
        where = f"{path} from GitHub ({ref})"
        if copy.is_file():
            warnings.append(f"Could not read {where}: {err}. Using the last copy read.")
            return copy.read_text(encoding="utf-8")
        warnings.append(f"Could not read {where}: {err}.")
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    copy.write_text(text, encoding="utf-8")
    return text


def collect_runs(
    gh: GitHub, cache_dir: Path, per_workflow: int = RUNS_LISTED
) -> list[dict[str, Any]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    runs = []
    listed: set[str] = set()
    for wf in WORKFLOWS:
        listing = gh.get(f"actions/workflows/{wf}/runs?per_page={per_workflow}")
        found = listing.get("workflow_runs", [])
        log(f"{wf}: {len(found)} runs")
        for i, r in enumerate(found, 1):
            listed.add(str(r["id"]))
            cached = cache_dir / f"run-{r['id']}.json"
            attempt = r.get("run_attempt") or 1
            if r["status"] == "completed" and cached.is_file():
                run_cached = json.loads(cached.read_text())
                if (
                    run_cached.get("v") == CACHE_VERSION
                    and run_cached.get("attempt", 1) == attempt
                ):
                    run_cached["workflow"] = wf
                    if run_cached.get("builds") or run_cached["event"] == "schedule":
                        runs.append(run_cached)
                    continue
            builds = []
            artifacts = get_all(gh, f"actions/runs/{r['id']}/artifacts", "artifacts")
            # One qa-report-<job index> per QA job; a re-run of the job uploads
            # another one with the same name: only the newest (the job's final
            # result) counts.
            latest: dict[str, dict[str, Any]] = {}
            for a in artifacts:
                if a["name"].startswith("qa-report") and not a.get("expired"):
                    seen = latest.get(a["name"])
                    if seen is None or (a.get("created_at") or "") > (
                        seen.get("created_at") or ""
                    ):
                        latest[a["name"]] = a
            for a in latest.values():
                for report in _artifact_reports(
                    gh, a, cache_dir / f"run-{r['id']}-artifacts"
                ):
                    for c in report.get("combos", []):
                        builds.append(
                            {
                                "pipeline": report.get("pipeline", ""),
                                "project": report.get("project", ""),
                                "package": c.get("package")
                                or report.get("package")
                                or "",
                                "label": c.get("label") or "default",
                                "params": c.get("params") or {},
                                "result": c.get("result"),
                                "build_url": c.get("build_url"),
                                "error": _short_error(c.get("error")),
                                "job": report.get("job", ""),
                            }
                        )
            if any(_not_run(b) for b in builds):
                # link each build that didn't run to its GitHub job, where the
                # error is (one call, only for runs that have such builds)
                job_urls = {
                    j["name"]: j.get("html_url", "")
                    for j in get_all(gh, f"actions/runs/{r['id']}/jobs", "jobs")
                }
                for b in builds:
                    if _not_run(b):
                        b["job_url"] = job_urls.get(b.get("job", ""), "")
            started = r.get("run_started_at") or r["created_at"]
            finished = r["updated_at"] if r["status"] == "completed" else None
            if attempt > 1:
                # A re-run moves the run's start to the re-run's: date and run
                # time come from the first attempt, the results from the last.
                first = gh.get(f"actions/runs/{r['id']}/attempts/1")
                started = first.get("run_started_at") or r["created_at"]
                finished = first.get("updated_at") or finished
            run = {
                "v": CACHE_VERSION,
                "id": r["id"],
                "workflow": wf,
                "attempt": attempt,
                "url": r["html_url"],
                "event": r["event"],
                "status": r["status"],
                "conclusion": r.get("conclusion"),
                "started_at": started,
                "finished_at": finished,
                # the current attempt's start, for live times ("running for",
                # "queued for"); started_at stays the first attempt's
                "attempt_started_at": r.get("run_started_at") or r["created_at"],
                "builds": builds,
            }
            if r["status"] != "completed":
                jobs = get_all(gh, f"actions/runs/{r['id']}/jobs", "jobs")
                # Has the current attempt started? Its own jobs only: the run's
                # job list also holds the earlier attempt's finished jobs that a
                # re-run of failed jobs leaves in place.
                attempt_jobs = (
                    get_all(
                        gh, f"actions/runs/{r['id']}/attempts/{attempt}/jobs", "jobs"
                    )
                    if attempt > 1
                    else jobs
                )
                begun = [
                    j
                    for j in attempt_jobs
                    if j.get("status") in ("in_progress", "completed")
                ]
                run["jobs_started"] = bool(begun)
                run["jobs_started_at"] = min(
                    (j["started_at"] for j in begun if j.get("started_at")),
                    default=None,
                )
                qa = [j for j in jobs if j["name"].startswith(QA_JOB_PREFIX)]
                run["qa_jobs"] = {
                    "total": len(qa),
                    "done": sum(1 for j in qa if j["status"] == "completed"),
                    "failed": sum(1 for j in qa if j.get("conclusion") == "failure"),
                }
            else:
                cached.write_text(json.dumps(run))  # finished: never fetched again
                # its reports, kept while it ran, are in the run file now
                shutil.rmtree(
                    cache_dir / f"run-{r['id']}-artifacts", ignore_errors=True
                )
            log(
                f"  [{i}/{len(found)}] run {r['id']} ({r['status']}): {len(builds)} build reports"
            )
            # a scheduled run without builds is kept: the page shows the night
            # as skipped (or failed before Jenkins) instead of hiding it
            if builds or r["status"] != "completed" or r["event"] == "schedule":
                runs.append(run)
    # runs no longer listed are never shown again: drop their cache files
    for path in cache_dir.glob("run-*"):
        m = re.match(r"run-(\d+)(?:\.json|-artifacts)$", path.name)
        if m and m.group(1) not in listed:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    runs.sort(key=lambda x: x["started_at"], reverse=True)
    return runs


def collect_build_info(
    jenkins: Jenkins, runs: list[dict[str, Any]], cache_dir: Path
) -> dict[str, dict[str, Any]]:
    """Durations and failed platforms for the builds the dashboard shows in
    detail: every build of each major's last RUNS_SHOWN completed runs."""
    path = cache_dir / "jenkins-builds.json"
    cache: dict[str, dict[str, Any]] = (
        json.loads(path.read_text()) if path.is_file() else {}
    )
    # only builds of the runs read: the file doesn't grow forever
    listed = {b["build_url"] for r in runs for b in r["builds"] if b.get("build_url")}
    cache = {url: v for url, v in cache.items() if url in listed}
    seen_per_major: dict[str, int] = {}
    todo: list[dict[str, Any]] = []
    for run in runs:
        if run["status"] != "completed":
            continue
        majors = {major_of(b["params"], b.get("label") or "") for b in run["builds"]}
        for m in majors:
            seen_per_major[m or ""] = seen_per_major.get(m or "", 0) + 1
        if all(seen_per_major.get(m or "", 0) > RUNS_SHOWN for m in majors):
            continue
        todo += [
            b
            for b in run["builds"]
            if b.get("build_url")
            and cache.get(b["build_url"], {}).get("v") != JENKINS_CACHE_VERSION
        ]
    if todo and jenkins.available:
        log(f"Jenkins: details for {len(todo)} builds (cached afterwards)")

        def fetch(b: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
            if not jenkins.available:  # gave up meanwhile (refused, unreachable)
                return b["build_url"], None
            return b["build_url"], jenkins.build_info(
                b["build_url"], platforms_of(b["params"])
            )

        # A few builds at a time: one by one, a first pass over hundreds of
        # builds takes minutes.
        with concurrent.futures.ThreadPoolExecutor(max_workers=JENKINS_WORKERS) as pool:
            for i, (url, info) in enumerate(pool.map(fetch, todo), 1):
                if info is not None:
                    cache[url] = dict(info, v=JENKINS_CACHE_VERSION)
                if i % 50 == 0:
                    log(f"  Jenkins: {i}/{len(todo)}")
                    path.write_text(json.dumps(cache))
        missing = sum(1 for b in todo if cache.get(b["build_url"], {}).get("missing"))
        if missing:
            log(f"  Jenkins: {missing} builds no longer exist in Jenkins (old history)")
    path.write_text(json.dumps(cache))
    return cache


def refresh(
    gh: GitHub, jenkins: Jenkins, cache_dir: Path, ref: str = "main"
) -> dict[str, Any]:
    """One refresh: GitHub (runs, known failures, schedule), then Jenkins.
    ref: the branch the two files are read from."""
    warnings: list[str] = []
    known: list[dict[str, Any]] = []
    schedule: dict[str, str] = {}
    import yaml

    text = repo_file(gh, KNOWN_FAILURES, cache_dir, warnings, ref)
    try:
        known = parse_known(text) if text is not None else []
    except yaml.YAMLError as err:
        text = None
        warnings.append(f"{KNOWN_FAILURES} is not valid YAML: {err}")
    if text is None:
        warnings.append("Known failures not loaded: every failure shows as new.")
    text = repo_file(gh, SCHEDULE, cache_dir, warnings, ref)
    try:
        schedule = parse_schedule(text) if text is not None else {}
    except yaml.YAMLError as err:
        warnings.append(f"{SCHEDULE} is not valid YAML: {err}")
    runs = collect_runs(gh, cache_dir)
    info = collect_build_info(jenkins, runs, cache_dir)
    for w in warnings:
        log(f"warning: {w}")
    return build_dashboard(
        runs, known, dt.datetime.now(dt.timezone.utc), info, schedule, warnings
    )


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--repo", default=REPO)
    ap.add_argument(
        "--ref",
        default="main",
        help="branch the known failures and the schedule are read from",
    )
    ap.add_argument("--out", default=str(here / "data.json"))
    ap.add_argument("--cache-dir", default=str(here / ".cache"))
    ap.add_argument(
        "--no-jenkins",
        action="store_true",
        help="don't read build details (durations, failing platforms) from Jenkins",
    )
    args = ap.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print(
            "GITHUB_TOKEN is not set: GitHub requires a token to download the QA reports.",
            file=sys.stderr,
        )
        return 2
    jenkins = Jenkins(
        os.environ.get("JENKINS_USER"),
        os.environ.get("JENKINS_TOKEN"),
        enabled=not args.no_jenkins,
    )
    data = refresh(GitHub(args.repo, token), jenkins, Path(args.cache_dir), args.ref)
    Path(args.out).write_text(json.dumps(data, indent=1))
    print(
        f"wrote {args.out}: {sum(1 for m in data['majors'] if m['runs'])} majors, {len(data['failures'])} failures"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
