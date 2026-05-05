#!/usr/bin/env python3
"""Discover the QA matrix for a GitHub workflow.

Lists OBS subprojects beneath ``$OBS_PROJECT``, strips that project's prefix
to yield colon-notation names (e.g. ``ppg:18``), invokes
``percona-obs -P ci qa show <project> --json`` for each, and concatenates the
results into a single JSON array printed to stdout. Subprojects without a
``qa:`` block silently contribute an empty array.

Required env vars:
  OBS_APIURL          OBS API URL (e.g. http://192.168.1.103:3000)
  OBS_PROJECT         The OBS root project to scan (e.g. home:Admin:percona,
                      or home:Admin:percona:pr-42 for PR workflows)

Optional:
  PERCONA_OBS_PROFILE Profile name to pass via -P (default: ci)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import osc.conf

from percona_obs.obs_api import _fetch_obs_subproject_names


def main() -> None:
    apiurl = os.environ["OBS_APIURL"]
    obs_project = os.environ["OBS_PROJECT"]
    profile = os.environ.get("PERCONA_OBS_PROFILE", "ci")

    osc.conf.get_config(override_apiurl=apiurl)

    prefix = obs_project + ":"
    subs = sorted(
        n
        for n in _fetch_obs_subproject_names(apiurl, obs_project)
        if n.startswith(prefix)
    )

    matrix: list = []
    for full_name in subs:
        project = full_name[len(prefix) :]
        result = subprocess.run(
            [
                "venv/bin/python",
                "-m",
                "percona_obs",
                "-P",
                profile,
                "qa",
                "show",
                project,
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"warning: qa show {project}: {result.stderr.strip()}",
                file=sys.stderr,
            )
            continue
        try:
            entries = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            print(f"warning: qa show {project}: invalid JSON ({exc})", file=sys.stderr)
            continue
        if entries:
            print(f"  {project}: {len(entries)} combo(s)", file=sys.stderr)
            matrix.extend(entries)

    print(json.dumps(matrix))


if __name__ == "__main__":
    main()
