#!/usr/bin/env python3
"""Plan tonight's OBS Nightly QA: which major, and whether to run at all.

Used by .github/workflows/obs-nightly-qa.yml (job ``plan``). Writes ``run``
(true/false) and ``major`` (a major, or empty for all) to $GITHUB_OUTPUT.

- The major is the manual input (``today`` = the schedule), or the major that
  .github/nightly-qa-schedule.yml lists for today's UTC weekday.
- A scheduled run is skipped when nothing under root/ changed since the last
  successful run *of the same major* (so a quiet Monday never hides a change
  from Tuesday's major). Each run marks the major it tested with an artifact
  named ``nightly-major-<major>`` (``nightly-major-all`` for a full run).
  Without such a run, it runs. Manual runs always run.

Env: EVENT_NAME, INPUT_MAJOR, GITHUB_REPOSITORY, GH_TOKEN, GITHUB_OUTPUT,
GITHUB_STEP_SUMMARY.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

SCHEDULE_FILE = Path(".github/nightly-qa-schedule.yml")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def parse_schedule(text: str) -> dict[str, str]:
    """``mon: 14`` lines -> {"mon": "14"}; comments and other lines ignored."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\s*(mon|tue|wed|thu|fri|sat|sun)\s*:\s*['\"]?(\d+)['\"]?\s*(#.*)?$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def resolve_major(input_major: str, weekday: str, schedule: dict[str, str]) -> tuple[bool, str, str]:
    """(run, major, reason). major "" with run=True means all majors."""
    wanted = (input_major or "today").strip().lower()
    if wanted == "all":
        return True, "", "manual run: all majors"
    if wanted != "today":
        return True, wanted, f"manual run: PG {wanted}"
    day = weekday.strip().lower()[:3]
    major = schedule.get(day, "")
    if not major:
        return False, "", f"nothing scheduled for {day}"
    return True, major, f"scheduled for {day}: PG {major}"


def marker(major: str) -> str:
    return f"nightly-major-{major or 'all'}"


def covers(artifact_names: list[str], major: str) -> bool:
    """A run with these artifacts tested *major* (or all majors)."""
    return marker(major) in artifact_names or marker("") in artifact_names


def last_tested_sha(runs: list[dict], artifacts_of: Callable[[int], list[str]], major: str) -> str:
    """headSha of the newest successful run that tested *major*, or ""."""
    for run in runs:  # newest first
        if covers(artifacts_of(run["databaseId"]), major):
            return run["headSha"]
    return ""


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def _changed_since(sha: str) -> bool:
    out = subprocess.run(["git", "log", "--oneline", f"{sha}..HEAD", "--", "root/"],
                         capture_output=True, text=True)
    if out.returncode != 0:  # unknown commit (e.g. history rewritten): be safe, run
        return True
    return bool(out.stdout.strip())


def main() -> None:
    event = os.environ.get("EVENT_NAME", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    schedule = parse_schedule(SCHEDULE_FILE.read_text())
    weekday = dt.datetime.now(dt.timezone.utc).strftime("%a")
    run, major, reason = resolve_major(os.environ.get("INPUT_MAJOR", ""), weekday, schedule)

    if run and event == "schedule":
        runs = json.loads(_gh("run", "list", "-R", repo, "--workflow", "obs-nightly-qa.yml",
                              "--status", "success", "--limit", "50", "--json", "databaseId,headSha") or "[]")
        artifacts_of = lambda rid: _gh("api", f"repos/{repo}/actions/runs/{rid}/artifacts",  # noqa: E731
                                       "--jq", ".artifacts[].name").split()
        sha = last_tested_sha(runs, artifacts_of, major)
        if not sha:
            reason += "; no earlier successful run for it, running"
        elif _changed_since(sha):
            reason += f"; root/ changed since its last successful run ({sha[:8]}), running"
        else:
            run = False
            reason += f"; no change in root/ since its last successful run ({sha[:8]}), skipping"

    print(reason)
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"run={'true' if run else 'false'}\nmajor={major}\nmarker={marker(major)}\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(f"### Nightly QA: {('PG ' + major) if major else 'all majors'}\n{reason}\n")


if __name__ == "__main__":
    sys.exit(main())
