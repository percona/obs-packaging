#!/usr/bin/env python3
"""Poll OBS build results until all builds reach a terminal state.

Exits 0 when every build succeeded (or was excluded), and 1 when any build
failed, was broken, or was unresolvable — so the calling GitHub Actions job
fails when OBS reports a build problem.

Also writes two artefacts for downstream consumers:

  /tmp/obs-build-badge.json    shields.io endpoint JSON for the README badge
  /tmp/obs-build-details.json  per-repo and per-state counts for the PR comment

Required environment variables
-------------------------------
OBS_APIURL          OBS API URL (e.g. http://my-obs:3000)
OBS_ROOTPRJ         Root OBS project (e.g. home:Admin:percona)

Optional environment variables
-------------------------------
OBS_POLL_INTERVAL       Base seconds between polls (default: 30)
OBS_POLL_MAX_INTERVAL   Cap for the poll-interval backoff (default: 300); the
                        interval ramps 1.5x per unchanged cycle up to this cap
                        and resets to the base on any state change
OBS_INITIAL_WAIT        Seconds to wait before the first poll so OBS has time
                        to schedule builds after a fresh service upload
                        (default: 30)
OBS_SYNC_REPORT         Path to the JSON report written by `sync push
                        --report-json`; when set (and the file exists),
                        monitoring is scoped to the projects the sync actually
                        touched, with a final full-tree sweep to adopt
                        cross-project rebuild cascades
"""

import json
import os
import subprocess
import sys
import time

import osc.conf

from percona_obs.cmd_build import _fetch_build_results
from percona_obs.common import (
    REPO_ROOT,
    find_packages,
    load_project_yaml,
    next_poll_interval,
)
from percona_obs.http_throttle import install as _install_http_throttle

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
apiurl = os.environ["OBS_APIURL"]
rootprj = os.environ["OBS_ROOTPRJ"]

poll_interval = int(os.environ.get("OBS_POLL_INTERVAL", "30"))
max_interval = int(os.environ.get("OBS_POLL_MAX_INTERVAL", "300"))
initial_wait = int(os.environ.get("OBS_INITIAL_WAIT", "30"))
# Path to the `sync push --report-json` output; when present, monitoring is
# scoped to the projects the sync actually touched.
sync_report_path = os.environ.get("OBS_SYNC_REPORT", "")
# When set, restrict monitoring to packages under this project subtree
# (colon-notation relative to rootprj, e.g. "ppg:releases:17").
scope_project = os.environ.get("OBS_SCOPE_PROJECT", "")

# ---------------------------------------------------------------------------
# Initialise osc (reads credentials from ~/.config/osc/oscrc)
# ---------------------------------------------------------------------------
osc.conf.get_config(override_apiurl=apiurl)
_install_http_throttle()

# ---------------------------------------------------------------------------
# Discover OBS projects from the local repo tree
# ---------------------------------------------------------------------------
from percona_obs.common import resolve_project_path

root_config = load_project_yaml(REPO_ROOT / "project.yaml")
root_obs = root_config.get("name") or rootprj

if scope_project:
    scope_path = resolve_project_path(scope_project)
    scope_obs = f"{root_obs}:{scope_project}"
else:
    scope_path = REPO_ROOT
    scope_obs = root_obs

# Devel projects build unreleased branches and are expected to fail; they
# must not gate sync-main (PG-2518 D-decision).  But when the operator
# explicitly scopes the run to a devel project, monitoring it is the whole
# point — only apply the devel skip when the scope itself is not devel.
scope_is_devel = "devel" in scope_project.split(":") if scope_project else False

obs_projects: set[str] = set()
for obs_project, package_path in find_packages(scope_path, scope_obs):
    project_config = load_project_yaml(package_path.parent / "project.yaml")
    obs_name = project_config.get("name") or obs_project
    # When rootprj differs from root_obs (e.g. a PR-specific project like
    # home:Admin:percona:pr-1 vs the canonical home:Admin:percona), substitute
    # the root_obs prefix so builds are fetched from the correct project.
    if rootprj != root_obs and obs_name.startswith(root_obs):
        obs_name = rootprj + obs_name[len(root_obs) :]
    # Skip devel projects (expected build failures) unless explicitly scoped.
    if not scope_is_devel and "devel" in obs_name.split(":"):
        continue
    obs_projects.add(obs_name)

# When a sync report is available, scope monitoring to the projects the sync
# actually touched (committed uploads or meta/prjconf changes).  The full
# discovered tree is kept for the badge snapshot and the final cascade sweep.
# A corrupt, stale, or drifted report fails OPEN: full-tree polling as before.
all_projects = set(obs_projects)
touched: "set[str] | None" = None
if sync_report_path and os.path.isfile(sync_report_path):
    report = {}
    try:
        with open(sync_report_path) as fh:
            report = json.load(fh)
        raw = report.get("rebuild_projects", [])
        touched = (
            {p for p in raw if isinstance(p, str)} if isinstance(raw, list) else None
        )
        if touched is None:
            print("WARNING: malformed sync report; polling full tree", flush=True)
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: unreadable sync report ({e}); polling full tree", flush=True)
        touched = None
    # Stale-report anchor: the report records the git HEAD it was produced
    # from.  If the checkout has moved on, its project discovery no longer
    # matches the report — fall back to the full tree.  A missing head_sha
    # (older tool) or a git error keeps the report (backward tolerant).
    if touched is not None:
        report_sha = report.get("head_sha")
        if isinstance(report_sha, str) and report_sha:
            checkout_sha = ""
            try:
                checkout_sha = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    cwd=REPO_ROOT.parent,
                ).stdout.strip()
            except OSError:
                pass
            if checkout_sha and checkout_sha != report_sha:
                print(
                    f"WARNING: sync report is for {report_sha}, checkout is "
                    f"{checkout_sha}; polling full tree",
                    flush=True,
                )
                touched = None
    # Naming-drift guard: a non-devel report project that discovery does not
    # know about means the report and checkout disagree on project naming —
    # scoping would silently drop builds, so fall back to the full tree.
    if touched is not None:
        stray = {
            t for t in touched if "devel" not in t.split(":") and t not in all_projects
        }
        if stray:
            print(
                f"WARNING: sync report names unknown project(s) "
                f"{', '.join(sorted(stray))}; polling full tree",
                flush=True,
            )
            touched = None
if touched is not None:
    obs_projects = obs_projects & touched
    print(
        f"Sync report: {len(touched)} project(s) touched, "
        f"monitoring {len(obs_projects)} after devel filter"
    )

print(
    f"Monitoring {len(obs_projects)} OBS project(s): {', '.join(sorted(obs_projects))}"
)

# ---------------------------------------------------------------------------
# Build-state classification
# ---------------------------------------------------------------------------
NON_TERMINAL = {"building", "dispatching", "scheduled", "blocked", "finished"}
FAILED_STATES = {"failed"}
BROKEN_STATES = {"broken"}
UNRESOLVABLE_STATES = {"unresolvable"}
EXCLUDED_STATES = {"excluded", "disabled"}
FAILURE_STATES = FAILED_STATES | BROKEN_STATES | UNRESOLVABLE_STATES


def collect(projects):
    """One pass over *projects*; returns (state_counts, per_repo_counts)."""
    state_counts: dict[str, int] = {}
    per_repo_counts: dict[str, dict[str, int]] = {}
    for obs_name in projects:
        results, _ = _fetch_build_results(apiurl, obs_name)
        for _pkg, repos in results.items():
            for repo, flavors in repos.items():
                repo_counts = per_repo_counts.setdefault(repo, {})
                for _flavor, code in flavors.items():
                    state_counts[code] = state_counts.get(code, 0) + 1
                    repo_counts[code] = repo_counts.get(code, 0) + 1
    return state_counts, per_repo_counts


# ---------------------------------------------------------------------------
# Badge and details helpers
# ---------------------------------------------------------------------------
_BADGE_PATH = "/tmp/obs-build-badge.json"
_DETAILS_PATH = "/tmp/obs-build-details.json"


def write_badge(
    succeeded: int,
    failed: int,
    broken: int,
    unresolvable: int,
    excluded: int,
) -> None:
    """Write a shields.io endpoint JSON badge to _BADGE_PATH."""
    msg = f"\u2714 {succeeded}  \u2717 {failed}  \u26d4 {broken}  \u26a0 {unresolvable}  \u2014 {excluded}"
    if failed > 0 or broken > 0:
        color = "red"
    elif unresolvable > 0:
        color = "yellow"
    else:
        color = "brightgreen"
    badge = {"schemaVersion": 1, "label": "OBS build", "message": msg, "color": color}
    with open(_BADGE_PATH, "w") as fh:
        json.dump(badge, fh)


def write_details(
    per_repo_counts: dict[str, dict[str, int]],
    succeeded: int,
    failed: int,
    broken: int,
    unresolvable: int,
    excluded: int,
) -> None:
    """Write a per-repo build breakdown to _DETAILS_PATH."""
    repos: dict[str, dict[str, int]] = {}
    for repo, counts in sorted(per_repo_counts.items()):
        repos[repo] = {
            "succeeded": counts.get("succeeded", 0),
            "failed": sum(counts.get(s, 0) for s in FAILED_STATES),
            "broken": sum(counts.get(s, 0) for s in BROKEN_STATES),
            "unresolvable": sum(counts.get(s, 0) for s in UNRESOLVABLE_STATES),
            "excluded": sum(counts.get(s, 0) for s in EXCLUDED_STATES),
        }
    details = {
        "repos": repos,
        "total": {
            "succeeded": succeeded,
            "failed": failed,
            "broken": broken,
            "unresolvable": unresolvable,
            "excluded": excluded,
        },
    }
    with open(_DETAILS_PATH, "w") as fh:
        json.dump(details, fh)


# ---------------------------------------------------------------------------
# Poll loop
# ---------------------------------------------------------------------------
if not obs_projects:
    # Nothing uploaded → no rebuilds triggered by this run.  Take a single
    # full-tree snapshot so the badge reflects reality, then exit on it
    # without waiting for unrelated in-flight builds.
    print("No monitored projects; taking one badge snapshot.")
    state_counts, per_repo_counts = collect(all_projects)
else:
    print(f"Waiting {initial_wait}s for OBS to schedule builds…", flush=True)
    time.sleep(initial_wait)
    interval = poll_interval
    prev_counts: dict[str, int] = {}
    while True:
        state_counts, per_repo_counts = collect(obs_projects)
        total = sum(state_counts.values())
        still_building = sum(state_counts.get(s, 0) for s in NON_TERMINAL)
        summary = ", ".join(f"{s}={n}" for s, n in sorted(state_counts.items()))
        print(f"{summary or 'no results yet'}", flush=True)
        if total > 0 and still_building == 0:
            # Monitored set is terminal.  One sweep over the rest of the tree
            # adopts projects rebuilt by cross-project cascades (e.g.
            # containers aggregating freshly built packages).
            remaining = all_projects - obs_projects
            if not remaining:
                # Already monitoring the full tree — the loop's counts are
                # the final counts; no sweep or re-collect needed.
                break
            sweep_counts, _ = collect(remaining)
            sweep_building = sum(sweep_counts.get(s, 0) for s in NON_TERMINAL)
            if sweep_building == 0:
                state_counts, per_repo_counts = collect(all_projects)
                break
            print(
                f"Adopting {sweep_building} still-building result(s) from full tree",
                flush=True,
            )
            obs_projects = set(all_projects)
        interval = next_poll_interval(
            interval,
            changed=(state_counts != prev_counts),
            base=poll_interval,
            cap=max_interval,
        )
        prev_counts = state_counts
        time.sleep(interval)

# ---------------------------------------------------------------------------
# Report final outcome
# ---------------------------------------------------------------------------
succeeded = state_counts.get("succeeded", 0)
failed = sum(state_counts.get(s, 0) for s in FAILED_STATES)
broken = sum(state_counts.get(s, 0) for s in BROKEN_STATES)
unresolvable = sum(state_counts.get(s, 0) for s in UNRESOLVABLE_STATES)
excluded = sum(state_counts.get(s, 0) for s in EXCLUDED_STATES)

write_badge(succeeded, failed, broken, unresolvable, excluded)
write_details(per_repo_counts, succeeded, failed, broken, unresolvable, excluded)

if failed or broken or unresolvable:
    parts = []
    if failed:
        parts.append(f"{failed} failed")
    if broken:
        parts.append(f"{broken} broken")
    if unresolvable:
        parts.append(f"{unresolvable} unresolvable")
    msg = ", ".join(parts)
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

msg = f"{succeeded} build(s) succeeded"
print(f"OK: {msg}")
sys.exit(0)
