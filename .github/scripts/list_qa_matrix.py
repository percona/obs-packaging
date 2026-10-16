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
  OBS_INSTANCES             JSON list of OBS instances (the repository variable).
                            When set (the nightly), projects come from this
                            checkout's qa: blocks instead of one OBS server's
                            subproject list, each resolved to the instance that
                            hosts it (as obs-qa-run.yml does), and every combo
                            carries that instance (instance_name, _apiurl,
                            _user, _registry, _rootprj, _env). One server
                            does not host every project: e.g. container
                            projects live on another instance than tarballs.
  QA_MAJOR                  a PostgreSQL major (e.g. "17"): keep only that
                            major's combos (see ``belongs_to_major``). Set by the
                            nightly's one-major-per-day schedule; unset = all.
"""

from __future__ import annotations

import json
from pathlib import Path
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


def is_release_tier(full_name: str) -> bool:
    """True for production release projects (``...:releases:<major>[:sub]``)."""
    return ":releases:" in full_name


def normalize_entry(entry: dict) -> dict:
    """Ensure a combo carries ready-to-use ``name_filter``/``package_filter`` strings.

    Mirrors the ``axis_filters`` convention: the workflow interpolates the
    values straight into the ``qa run`` command line, so each is either
    ``--name <name>`` (or empty) and ``--package <pkg>`` / ``--project-only``.
    """
    if not entry.get("name_filter"):
        name = entry.get("name") or ""
        entry["name_filter"] = f"--name {name}" if name else ""
    if not entry.get("package_filter"):
        package = entry.get("package") or ""
        entry["package_filter"] = (
            f"--package {package}" if package else "--project-only"
        )
    return entry


def fetch_present_packages(apiurl: str, full_project: str) -> set[str]:
    """Package names currently in an OBS project.

    Empty only on 404; any other OBS error aborts the run (SystemExit).
    """
    from percona_obs.obs_api import _fetch_obs_package_names_or_fail

    return _fetch_obs_package_names_or_fail(apiurl, full_project)


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


def belongs_to_major(project: str, name: str | None, major: str) -> bool:
    """Whether a QA combo is part of PostgreSQL *major*'s nightly.

    A major's own projects carry it as a project component
    (``ppg:staging:17``, ``ppg:staging:17:containers``, ...). Version-independent
    projects (``ppg:staging:common:...``) hold entries for several majors, told
    apart by name: component images against a major's server end in
    ``-pg<major>``; image upgrades belong to the major they upgrade *into*
    (``...-16-to-17`` is PG 17's), so each upgrade runs exactly once a week.
    """
    project_majors = [part for part in project.split(":") if part.isdigit()]
    if project_majors:  # a major's own project: that major only, whatever the name
        return major in project_majors
    name = name or ""
    return name.endswith(f"-pg{major}") or name.endswith(f"-to-{major}")



def local_qa_projects(root: Path) -> list[str]:
    """Projects of this checkout (``root/``) with a qa: block, own or a package's."""
    found = []
    for y in sorted(root.rglob("project.yaml")):
        rel = y.parent.relative_to(root)
        if "_shared" in rel.parts:
            continue
        text = y.read_text(encoding="utf-8")
        pkgs = [d / "package.yaml" for d in y.parent.iterdir() if (d / "package.yaml").is_file()]
        if "\nqa:" in text or text.startswith("qa:") or any("\nqa:" in q.read_text(encoding="utf-8") for q in pkgs):
            found.append(":".join(rel.parts))
    return found


def _qa_show(project: str, profile: str) -> list:
    result = subprocess.run(
        ["venv/bin/python", "-m", "percona_obs", "-P", profile, "qa", "show", project, "--json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"warning: qa show {project}: {result.stderr.strip()}", file=sys.stderr)
        return []
    for line in result.stderr.rstrip().splitlines():
        print(f"  {project}: {line.strip()}", file=sys.stderr)
    try:
        return json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        print(f"warning: qa show {project}: invalid JSON ({exc})", file=sys.stderr)
        return []


def matrix_per_instance(instances_json: str, root: Path, profile: str, major: str) -> list:
    """Nightly matrix: every qa: project of the checkout, on the instance hosting it."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from resolve_qa_instance import _load_instances, resolve_instance

    instances = _load_instances(instances_json)
    matrix: list = []
    for project in local_qa_projects(root):
        if is_release_tier("root:" + project):
            continue
        try:
            inst = resolve_instance(instances, project)
        except SystemExit as exc:  # no instance (or several): cannot run, say so
            print(f"warning: {project}: {exc}", file=sys.stderr)
            continue
        entries = _qa_show(project, profile)
        if major:
            entries = [e for e in entries if belongs_to_major(project, e.get("name"), major)]
        if not entries:
            continue
        print(f"  {project}: {len(entries)} combo(s) on instance {inst.get('name')}", file=sys.stderr)
        fields = {
            "instance_name": str(inst.get("name", "")),
            "instance_apiurl": str(inst.get("apiurl", "")),
            "instance_user": str(inst.get("user", "") or ""),
            "instance_registry": str(inst.get("registry", "") or ""),
            "instance_rootprj": str(inst.get("rootprj", "") or ""),
            "instance_env": json.dumps(inst.get("env")) if inst.get("env") else "null",
        }
        for e in entries:
            e.setdefault("project", project)
            matrix.append({**normalize_entry(e), **fields})
    return matrix


def main() -> None:
    instances_json = os.environ.get("OBS_INSTANCES", "").strip()
    if instances_json:
        major = os.environ.get("QA_MAJOR", "").strip()
        matrix = matrix_per_instance(instances_json, Path("root"),
                                     os.environ.get("PERCONA_OBS_PROFILE", "ci"), major)
        print(f"{('PG ' + major) if major else 'all majors'}: {len(matrix)} combo(s) in total", file=sys.stderr)
        print(json.dumps(matrix))
        return

    import osc.conf

    from percona_obs.obs_api import _fetch_obs_subproject_names

    apiurl = os.environ["OBS_APIURL"]
    obs_project = os.environ["OBS_PROJECT"]
    profile = os.environ.get("PERCONA_OBS_PROFILE", "ci")
    qa_types_raw = os.environ.get("QA_TYPES", "")
    qa_types = {t.strip() for t in qa_types_raw.split(",") if t.strip()}
    present_only = os.environ.get("QA_PACKAGES_PRESENT_ONLY", "") == "true"
    major = os.environ.get("QA_MAJOR", "").strip()

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
        # Release mirrors now carry qa: blocks meant for the per-PR
        # pre-release; the frozen production snapshots must not be re-tested
        # by the nightly (production-root enumeration, i.e. not PR mode).
        if not present_only and is_release_tier(full_name):
            continue
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
            if present_only:
                # PR mode: a dropped project would silently shrink the matrix.
                raise SystemExit(f"error: qa show {project}: {result.stderr.strip()}")
            print(
                f"warning: qa show {project}: {result.stderr.strip()}",
                file=sys.stderr,
            )
            continue
        if result.stderr.strip():
            # `qa show` reports image-reference decisions (which rootprj each
            # image path got) on stderr; keep them in the detect log.
            for line in result.stderr.rstrip().splitlines():
                print(f"  {project}: {line.strip()}", file=sys.stderr)
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
        if entries and major:
            entries = [e for e in entries if belongs_to_major(project, e.get("name"), major)]
        if entries:
            print(f"  {project}: {len(entries)} combo(s)", file=sys.stderr)
            matrix.extend(normalize_entry(e) for e in entries)

    if major:
        print(f"PG {major}: {len(matrix)} combo(s) in total", file=sys.stderr)
    print(json.dumps(matrix))


if __name__ == "__main__":
    main()
