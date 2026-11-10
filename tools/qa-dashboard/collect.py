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
import statistics
import sys
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
CACHE_VERSION = 2
JENKINS_CACHE_VERSION = 2
JENKINS_WORKERS = 8  # builds asked at the same time  # bump when what is kept per Jenkins build changes  # bump when the cached run format changes: re-read once
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


def build_key(build: dict[str, Any]) -> str:
    """Identifies 'the same build' across runs (versions change, this
    doesn't): Jenkins job, combo label and, for upgrades, the old major."""
    return "|".join(
        [
            build["pipeline"],
            build.get("label") or "default",
            old_major_of(build["params"]),
        ]
    )


def build_title(build: dict[str, Any]) -> str:
    params = build["params"]
    parts = [build["pipeline"]]
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


def load_known(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    import yaml  # PyYAML, in obs-packaging's requirements.txt

    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [e for e in entries if isinstance(e, dict) and e.get("ticket")]


def match_known(
    build: dict[str, Any], major: str, known: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The known-failures entry covering this failed build, if any. An entry
    matches on major (optional), Jenkins job (regex) and combo label or
    scenario (regex, optional)."""
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
        return entry
    return None


# ---------------------------------------------------------------------------
# the dashboard data (pure)
# ---------------------------------------------------------------------------


QUEUED_STATUSES = ("queued", "waiting", "requested", "pending")


def is_queued(run: dict[str, Any]) -> bool:
    """Not started yet: GitHub queues a nightly (or a re-run of one) while
    another nightly runs."""
    return run.get("status") in QUEUED_STATUSES


def _is_failed(build: dict[str, Any]) -> bool:
    return build.get("result") not in OK_RESULTS


def build_dashboard(
    runs: list[dict[str, Any]],
    known: list[dict[str, Any]],
    now: dt.datetime,
    build_info: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """runs: newest first, each {id, url, event, status, started_at,
    finished_at, builds: [{pipeline, label, params, result, build_url}],
    qa_jobs: {total, done, failed} (running runs)}.
    build_info: build_url -> {duration_s, failed_platforms} from Jenkins."""
    build_info = build_info or {}
    runs = [r for r in runs if r.get("workflow", NIGHTLY) == NIGHTLY]
    per_major: dict[str, list[dict[str, Any]]] = {m: [] for m in MAJORS}
    for run in runs:
        groups: dict[str, list[dict[str, Any]]] = {}
        for b in run.get("builds", []):
            m = major_of(b["params"], b.get("label") or "")
            if m in per_major:
                groups.setdefault(m, []).append(b)
        running_majors = set(run.get("running_majors") or [])
        for m in MAJORS:
            if m in groups or (run["status"] != "completed" and m in running_majors):
                per_major[m].append(dict(run, builds=groups.get(m, []), major=m))

    def run_kind(run: dict[str, Any], major: str) -> str:
        if run["status"] != "completed":
            return "queued" if is_queued(run) else "running"
        failed = [b for b in run["builds"] if _is_failed(b)]
        if not failed:
            return "pass"
        if all(match_known(b, major, known) for b in failed):
            return "known"
        return "fail"

    majors_out, failures_out, details = [], [], {}
    running: list[dict[str, Any]] = []
    queued: list[dict[str, Any]] = []
    for m in MAJORS:
        mruns = per_major[m]
        if not mruns:
            majors_out.append({"major": m, "status": "none", "runs": []})
            continue
        completed = [r for r in mruns if r["status"] == "completed"]
        shown = mruns[:RUNS_SHOWN]
        current = mruns[0]
        last = completed[0] if completed else None
        durations = [
            (parse_time(r["finished_at"]) - parse_time(r["started_at"])).total_seconds()
            for r in completed[:RUNS_SHOWN]
            if r.get("finished_at") and r.get("started_at")
        ]
        median = statistics.median(durations) if durations else None
        last_duration = durations[0] if durations else None
        slow = bool(median and last_duration and last_duration >= SLOW_FACTOR * median)

        failing = [b for b in (last["builds"] if last else []) if _is_failed(b)]
        new = [b for b in failing if not match_known(b, m, known)]
        if current["status"] != "completed":
            status = "queued" if is_queued(current) else "running"
            jobs = current.get("qa_jobs") or {}
            live = {
                "major": m,
                "url": current["url"],
                # the current attempt: a re-run's own start, not the first one's
                "since": current.get("attempt_started_at") or current["started_at"],
                "rerun": (current.get("attempt") or 1) > 1,
                "done": jobs.get("done", 0),
                "total": jobs.get("total", 0),
                "failing": jobs.get("failed", 0),
            }
            (queued if status == "queued" else running).append(live)
        else:
            status = "fail" if new else ("known" if failing else "pass")

        def started(r: dict[str, Any]) -> dt.datetime:
            return parse_time(r["started_at"]) or now

        major_row = {
            "major": m,
            "status": status,
            "failing": len(failing),
            "new": len(new),
            "total": len(last["builds"]) if last else 0,
            "last_run": fmt_date(started(last)) if last else "–",
            "last_run_url": last["url"] if last else "",
            "runtime": fmt_duration(last_duration),
            "median": fmt_duration(median),
            "slow": slow,
            "slow_pct": (
                round((last_duration / median - 1) * 100)
                if slow and median and last_duration
                else 0
            ),
            "runs": [
                {
                    "date": short_date(started(r))
                    + ("" if r["event"] == "schedule" else " (manual)"),
                    "kind": run_kind(r, m),
                    "url": r["url"],
                }
                for r in reversed(shown)
            ],
        }
        if status == "running":
            jobs = current.get("qa_jobs") or {}
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
            secs = (
                (parse_time(r["finished_at"]) - started(r)).total_seconds()
                if r.get("finished_at")
                else None
            )
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
            "runtime": major_row["runtime"],
            "median": major_row["median"],
            "slow": slow,
            "slow_pct": major_row["slow_pct"],
            "slowest": slowest_out,
            "median_minutes": round(median / 60) if median else 0,
            "runtimes": runtimes,
            "failing_builds": detail_failing,
        }

    failures_out.sort(key=lambda f: (not f["is_new"], -int(f["major"])))
    return {
        "generated_at": iso(now),
        "refresh_minutes": REFRESH_MINUTES,
        "repo": REPO,
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


class GitHub:
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
        with urllib.request.urlopen(self._request(url), timeout=60) as resp:
            return json.load(resp)

    def download(self, url: str) -> bytes:
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
        for name in zf.namelist():
            if name.endswith(".json"):
                out.append(json.loads(zf.read(name)))
    return out


def scheduled_major(created_at: str, schedule: dict[str, Any]) -> str | None:
    """The major the nightly schedule runs on that UTC weekday."""
    when = parse_time(created_at)
    if not when:
        return None
    major = schedule.get(
        ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[when.weekday()]
    )
    return str(major) if major is not None else None


def load_schedule(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def collect_runs(
    gh: GitHub,
    cache_dir: Path,
    per_workflow: int = 40,
    schedule: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    if schedule is None:
        schedule = load_schedule(
            Path(__file__).resolve().parents[2] / ".github" / "nightly-qa-schedule.yml"
        )
    runs = []
    for wf in WORKFLOWS:
        listing = gh.get(f"actions/workflows/{wf}/runs?per_page={per_workflow}")
        found = listing.get("workflow_runs", [])
        log(f"{wf}: {len(found)} runs")
        for i, r in enumerate(found, 1):
            cached = cache_dir / f"run-{r['id']}.json"
            attempt = r.get("run_attempt") or 1
            if r["status"] == "completed" and cached.is_file():
                run_cached = json.loads(cached.read_text())
                if (
                    run_cached.get("v") == CACHE_VERSION
                    and run_cached.get("attempt", 1) == attempt
                ):
                    run_cached["workflow"] = wf
                    if run_cached.get("builds"):
                        runs.append(run_cached)
                    continue
            builds = []
            artifacts = gh.get(f"actions/runs/{r['id']}/artifacts?per_page=100").get(
                "artifacts", []
            )
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
                for report in _reports_from_zip(gh.download(a["archive_download_url"])):
                    for c in report.get("combos", []):
                        builds.append(
                            {
                                "pipeline": report.get("pipeline", ""),
                                "label": c.get("label") or "default",
                                "params": c.get("params") or {},
                                "result": c.get("result"),
                                "build_url": c.get("build_url"),
                            }
                        )
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
                "started_at": started,
                "finished_at": finished,
                # the current attempt's start, for live times ("running for",
                # "queued for"); started_at stays the first attempt's
                "attempt_started_at": r.get("run_started_at") or r["created_at"],
                "builds": builds,
            }
            if r["status"] != "completed":
                jobs = gh.get(f"actions/runs/{r['id']}/jobs?per_page=100").get(
                    "jobs", []
                )
                qa = [j for j in jobs if j["name"].startswith(QA_JOB_PREFIX)]
                run["qa_jobs"] = {
                    "total": len(qa),
                    "done": sum(1 for j in qa if j["status"] == "completed"),
                    "failed": sum(1 for j in qa if j.get("conclusion") == "failure"),
                }
                majors_seen = set()
                for j in qa:
                    for staging, upgraded_to in re.findall(
                        r":staging:(1\d)\b|-to-(1\d)\b", j["name"]
                    ):
                        majors_seen.add(staging or upgraded_to)
                if not majors_seen and not builds and r["event"] == "schedule":
                    # not planned yet (queued): tonight's major, from the schedule
                    planned = scheduled_major(r["created_at"], schedule)
                    if planned:
                        majors_seen.add(planned)
                run["running_majors"] = sorted(majors_seen)
            else:
                cached.write_text(json.dumps(run))  # finished: never fetched again
            log(
                f"  [{i}/{len(found)}] run {r['id']} ({r['status']}): {len(builds)} build reports"
            )
            if builds or r["status"] != "completed":
                runs.append(run)
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
    if not todo or not jenkins.available:
        return cache
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
    path.write_text(json.dumps(cache))
    missing = sum(1 for b in todo if cache.get(b["build_url"], {}).get("missing"))
    if missing:
        log(f"  Jenkins: {missing} builds no longer exist in Jenkins (old history)")
    return cache


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--out", default=str(here / "data.json"))
    ap.add_argument("--cache-dir", default=str(here / ".cache"))
    ap.add_argument(
        "--known", default=str(here.parents[1] / ".github" / "qa-known-failures.yaml")
    )
    ap.add_argument(
        "--demo",
        action="store_true",
        help="write the built-in sample data (no network)",
    )
    ap.add_argument(
        "--no-jenkins",
        action="store_true",
        help="don't read build details (durations, failing platforms) from Jenkins",
    )
    args = ap.parse_args(argv)
    known = load_known(Path(args.known))
    now = dt.datetime.now(dt.timezone.utc)
    if args.demo:
        import demo

        data = build_dashboard(demo.runs(now), demo.KNOWN, now, demo.build_info(now))
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            print(
                "GITHUB_TOKEN is not set: GitHub requires a token to download the QA reports.",
                file=sys.stderr,
            )
            return 2
        cache = Path(args.cache_dir)
        runs = collect_runs(GitHub(args.repo, token), cache)
        info = collect_build_info(
            Jenkins(
                os.environ.get("JENKINS_USER"),
                os.environ.get("JENKINS_TOKEN"),
                enabled=not args.no_jenkins,
            ),
            runs,
            cache,
        )
        data = build_dashboard(runs, known, now, info)
    Path(args.out).write_text(json.dumps(data, indent=1))
    print(
        f"wrote {args.out}: {sum(1 for m in data['majors'] if m['runs'])} majors, {len(data['failures'])} failures"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
