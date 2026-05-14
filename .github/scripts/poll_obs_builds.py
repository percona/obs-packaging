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
OBS_POLL_INTERVAL   Seconds between polls (default: 30)
OBS_INITIAL_WAIT    Seconds to wait before the first poll so OBS has time to
                    schedule builds after a fresh service upload (default: 30)
"""

import json
import os
import sys
import time

import osc.conf

from percona_obs.cmd_build import _fetch_build_results
from percona_obs.common import REPO_ROOT, find_packages, load_project_yaml

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
apiurl = os.environ["OBS_APIURL"]
rootprj = os.environ["OBS_ROOTPRJ"]

poll_interval = int(os.environ.get("OBS_POLL_INTERVAL", "30"))
initial_wait = int(os.environ.get("OBS_INITIAL_WAIT", "30"))
# When set, restrict monitoring to packages under this project subtree
# (colon-notation relative to rootprj, e.g. "ppg:releases:17").
scope_project = os.environ.get("OBS_SCOPE_PROJECT", "")

# ---------------------------------------------------------------------------
# Initialise osc (reads credentials from ~/.config/osc/oscrc)
# ---------------------------------------------------------------------------
osc.conf.get_config(override_apiurl=apiurl)

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

obs_projects: set[str] = set()
for obs_project, package_path in find_packages(scope_path, scope_obs):
    project_config = load_project_yaml(package_path.parent / "project.yaml")
    obs_name = project_config.get("name") or obs_project
    # When rootprj differs from root_obs (e.g. a PR-specific project like
    # home:Admin:percona:pr-1 vs the canonical home:Admin:percona), substitute
    # the root_obs prefix so builds are fetched from the correct project.
    if rootprj != root_obs and obs_name.startswith(root_obs):
        obs_name = rootprj + obs_name[len(root_obs) :]
    obs_projects.add(obs_name)

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
# Wait for OBS to schedule the builds, then poll
# ---------------------------------------------------------------------------
print(f"Waiting {initial_wait}s for OBS to schedule builds…", flush=True)
time.sleep(initial_wait)

# ---------------------------------------------------------------------------
# Poll loop
# ---------------------------------------------------------------------------
while True:
    state_counts: dict[str, int] = {}
    per_repo_counts: dict[str, dict[str, int]] = {}
    for obs_name in obs_projects:
        results, _ = _fetch_build_results(apiurl, obs_name)
        for _pkg, repos in results.items():
            for repo, flavors in repos.items():
                repo_counts = per_repo_counts.setdefault(repo, {})
                for _flavor, code in flavors.items():
                    state_counts[code] = state_counts.get(code, 0) + 1
                    repo_counts[code] = repo_counts.get(code, 0) + 1

    total = sum(state_counts.values())
    still_building = sum(state_counts.get(s, 0) for s in NON_TERMINAL)
    succeeded = state_counts.get("succeeded", 0)
    failed = sum(state_counts.get(s, 0) for s in FAILED_STATES)
    broken = sum(state_counts.get(s, 0) for s in BROKEN_STATES)
    unresolvable = sum(state_counts.get(s, 0) for s in UNRESOLVABLE_STATES)
    excluded = sum(state_counts.get(s, 0) for s in EXCLUDED_STATES)
    summary = ", ".join(f"{s}={n}" for s, n in sorted(state_counts.items()))
    print(f"{summary or 'no results yet'}", flush=True)

    if total > 0 and still_building == 0:
        break

    time.sleep(poll_interval)

# ---------------------------------------------------------------------------
# Report final outcome
# ---------------------------------------------------------------------------
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
