"""GitHub REST lookups through the ``gh`` CLI.

Only ``gh`` is used (no token handling in the tool): locally the operator is
logged in, in CI ``GH_TOKEN`` is set.  Every call is a subprocess so tests
monkeypatch ``_gh_api_json``.
"""

import json
import re
import subprocess
from typing import Any

_SLUG_RE = re.compile(r"github\.com[/:]([^/\s]+/[^/\s]+?)(?:\.git)?/?$")

# Job name prefix of sync-main.yml's upload legs ("percona-obs sync push (<instance>)").
SYNC_JOB_PREFIX = "percona-obs sync push"


def repo_slug_from_url(url: str) -> str:
    """``https://github.com/o/r.git`` / ``git@github.com:o/r.git`` → ``o/r``."""
    m = _SLUG_RE.search(url.strip())
    if not m:
        raise SystemExit(f"error: cannot derive owner/repo from {url!r}")
    return m.group(1)


def _gh_api_json(path: str) -> Any:
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"error: gh api {path} failed: {r.stderr.strip()}")
    return json.loads(r.stdout or "null")


def last_synced_head_sha(
    repo_slug: str,
    *,
    workflow_file: str = "sync-main.yml",
    branch: str = "main",
    job_prefix: str = SYNC_JOB_PREFIX,
    instance: "str | None" = None,
    max_runs: int = 20,
) -> str:
    """Head SHA of the newest *workflow_file* run on *branch* whose sync jobs
    (name starting with *job_prefix*) all concluded ``success``.

    Neither the run's status nor its conclusion is consulted: the build poll
    job keeps the run in progress for hours after the upload (and may fail it
    afterwards), and that finished upload is what OBS holds.  A sync job that
    is still running has no conclusion, so its run does not qualify.

    *instance* restricts the check to that instance's upload leg (job
    ``"<job_prefix> (<instance>)"``): a failed upload to another instance does
    not disqualify the run, and a run without that leg never qualifies.
    """
    data = _gh_api_json(
        f"repos/{repo_slug}/actions/workflows/{workflow_file}/runs"
        f"?branch={branch}&per_page={max_runs}"
    )
    wanted = f"{job_prefix} ({instance})" if instance is not None else None
    for run in data.get("workflow_runs") or []:
        jobs = (
            _gh_api_json(
                f"repos/{repo_slug}/actions/runs/{run['id']}/jobs?per_page=100"
            ).get("jobs")
            or []
        )
        sync_jobs = [
            j
            for j in jobs
            if str(j.get("name", "")).startswith(job_prefix)
            and (wanted is None or j.get("name") == wanted)
        ]
        if sync_jobs and all(j.get("conclusion") == "success" for j in sync_jobs):
            return str(run["head_sha"])
    leg = f" for instance {instance}" if instance is not None else ""
    raise SystemExit(
        f"error: no {workflow_file} run on {branch} of {repo_slug} "
        f"with successful sync jobs{leg} in the last {max_runs} runs; "
        "pass --source-commit explicitly"
    )
