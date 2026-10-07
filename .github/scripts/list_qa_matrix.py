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
  QA_TYPES                  comma-separated subset of packages,containers; only
                            subprojects of those kinds are scanned
  QA_PACKAGES_PRESENT_ONLY  "true": drop package lanes (combos with a non-empty
                            ``package``) whose package is not in the OBS
                            subproject.  Set by PR runs, where the PR project
                            holds only promoted packages; unset for the nightly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


def qa_project_type(full_name: str) -> str:
    """QA type of an OBS project: containers vs packages.

    Matches both layouts: the old per-flavor ":containers:<flavor>"
    subprojects and the restructured single ":containers" subproject.
    """
    if ":containers:" in full_name or full_name.endswith(":containers"):
        return "containers"
    return "packages"


def normalize_entry(entry: dict) -> dict:
    """Ensure a combo carries ready-to-use ``name_filter``/``package_filter`` strings.

    Mirrors the ``axis_filters`` convention: the workflow interpolates the
    values straight into the ``qa run`` command line, so each is either
    ``--name <name>`` / ``--package <pkg>`` or the empty string.
    """
    if not entry.get("name_filter"):
        name = entry.get("name") or ""
        entry["name_filter"] = f"--name {name}" if name else ""
    if not entry.get("package_filter"):
        package = entry.get("package") or ""
        entry["package_filter"] = f"--package {package}" if package else ""
    return entry


def fetch_present_packages(apiurl: str, full_project: str) -> set[str]:
    """Package names currently in an OBS project (empty on 404 / error)."""
    from percona_obs.obs_api import _fetch_obs_package_names

    return _fetch_obs_package_names(apiurl, full_project)


def drop_absent_packages(
    matrix: list[dict], present: set[str]
) -> tuple[list[dict], list[str]]:
    """Keep project lanes and the package lanes whose package is in ``present``.

    Returns ``(kept, dropped_package_names)``; project lanes (``package`` empty)
    are never dropped.
    """
    kept: list[dict] = []
    dropped: set[str] = set()
    for combo in matrix:
        package = combo.get("package") or ""
        if package and package not in present:
            dropped.add(package)
            continue
        kept.append(combo)
    return kept, sorted(dropped)


def main() -> None:
    import osc.conf

    from percona_obs.obs_api import _fetch_obs_subproject_names

    apiurl = os.environ["OBS_APIURL"]
    obs_project = os.environ["OBS_PROJECT"]
    profile = os.environ.get("PERCONA_OBS_PROFILE", "ci")
    qa_types_raw = os.environ.get("QA_TYPES", "")
    qa_types = {t.strip() for t in qa_types_raw.split(",") if t.strip()}
    present_only = os.environ.get("QA_PACKAGES_PRESENT_ONLY", "") == "true"

    osc.conf.get_config(override_apiurl=apiurl)

    prefix = obs_project + ":"
    pr_prefix = prefix + "PR:"
    subs = sorted(
        n
        for n in _fetch_obs_subproject_names(apiurl, obs_project)
        if n.startswith(prefix) and not n.startswith(pr_prefix)
    )

    matrix: list = []
    for full_name in subs:
        project = full_name[len(prefix) :]
        proj_type = qa_project_type(full_name)
        if qa_types and proj_type not in qa_types:
            continue
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
        if entries and present_only and any(e.get("package") for e in entries):
            present = fetch_present_packages(apiurl, full_name)
            entries, dropped = drop_absent_packages(entries, present)
            if dropped:
                print(
                    f"  {project}: package lane(s) skipped, not in {full_name}: "
                    + ", ".join(dropped),
                    file=sys.stderr,
                )
        if entries:
            print(f"  {project}: {len(entries)} combo(s)", file=sys.stderr)
            matrix.extend(normalize_entry(e) for e in entries)

    print(json.dumps(matrix))


if __name__ == "__main__":
    main()
