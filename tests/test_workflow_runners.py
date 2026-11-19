"""Guard: workflow jobs must select their runner through repository variables.

Hardcoding ``runs-on: ubuntu-latest`` would bypass the self-hosted runners.
Deleting the variables falls back to GitHub-hosted ``ubuntu-latest``.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

SMALL = "${{ vars.CI_RUNNER || 'ubuntu-latest' }}"
LARGE = "${{ vars.CI_RUNNER_LARGE || 'ubuntu-latest' }}"
LARGE_JOBS = {("build-obs-image.yml", "build")}


def test_every_job_uses_the_runner_variable():
    bad = []
    seen_large = set()
    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    assert files, "no workflow files found"
    for path in files:
        jobs = yaml.safe_load(path.read_text())["jobs"]
        for name, job in jobs.items():
            if "uses" in job:
                continue
            if (path.name, name) in LARGE_JOBS:
                seen_large.add((path.name, name))
            want = LARGE if (path.name, name) in LARGE_JOBS else SMALL
            if job.get("runs-on") != want:
                bad.append(f"{path.name}:{name}")
    assert seen_large == LARGE_JOBS, f"large jobs missing: {LARGE_JOBS - seen_large}"
    assert not bad, f"jobs not using the runner variable: {bad}"
