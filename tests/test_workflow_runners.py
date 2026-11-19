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
    for path in sorted(WORKFLOWS.glob("*.yml")):
        jobs = yaml.safe_load(path.read_text())["jobs"]
        for name, job in jobs.items():
            if "uses" in job:
                continue
            want = LARGE if (path.name, name) in LARGE_JOBS else SMALL
            if job.get("runs-on") != want:
                bad.append(f"{path.name}:{name}")
    assert not bad, f"jobs not using the runner variable: {bad}"
