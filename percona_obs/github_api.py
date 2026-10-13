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
    max_runs: int = 20,
) -> str:
    """Head SHA of the newest completed *workflow_file* run on *branch* whose
    sync jobs (name starting with *job_prefix*) all concluded ``success``.

    The run's own conclusion is ignored on purpose: the build poll job fails
    the run after the upload already happened, and that upload is what OBS
    holds.
    """
    data = _gh_api_json(
        f"repos/{repo_slug}/actions/workflows/{workflow_file}/runs"
        f"?branch={branch}&status=completed&per_page={max_runs}"
    )
    for run in data.get("workflow_runs") or []:
        jobs = (
            _gh_api_json(
                f"repos/{repo_slug}/actions/runs/{run['id']}/jobs?per_page=100"
            ).get("jobs")
            or []
        )
        sync_jobs = [j for j in jobs if str(j.get("name", "")).startswith(job_prefix)]
        if sync_jobs and all(j.get("conclusion") == "success" for j in sync_jobs):
            return str(run["head_sha"])
    raise SystemExit(
        f"error: no completed {workflow_file} run on {branch} of {repo_slug} "
        f"with successful sync jobs in the last {max_runs} runs; "
        "pass --source-commit explicitly"
    )
