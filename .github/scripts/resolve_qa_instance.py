#!/usr/bin/env python3
"""Resolve which OBS instance hosts a project, for the manual QA workflow.

Reads the ``OBS_INSTANCES`` repository variable (JSON list of instance
objects, see docs/PERCONA_OBS_TOOL.md) and keeps the entries whose
``include_projects``/``exclude_projects`` globs admit ``QA_PROJECT`` and whose
``qa_types`` (when set) cover the project's QA kind (``containers`` for a
``:containers`` subproject, ``packages`` otherwise).  Exactly one instance
must remain; zero or several is an error naming the candidates.

Also validates the free-text workflow inputs that are later interpolated
into shell: ``QA_PROJECT`` (strict colon-notation name), ``QA_PR_NUMBER``
(digits or empty) and ``QA_PACKAGE`` (package directory name or empty).

Writes flat scalars to ``$GITHUB_OUTPUT``: instance_name, instance_apiurl,
instance_user, instance_registry, instance_env (JSON object or ``null``) and
``rootprj`` -- the instance's production root, or ``<pr_rootprj>:pr-<N>`` when
``QA_PR_NUMBER`` is given.

Required env vars:
  OBS_INSTANCES   JSON list of instance objects
  QA_PROJECT      colon-notation project name (e.g. ppg:staging:18)
  GITHUB_OUTPUT   path of the step output file

Optional:
  QA_PR_NUMBER    PR number; empty for the production root
  QA_PACKAGE      package name; empty for none
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Scripts in this directory share the OBS-project-type helper.
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Repo root, for percona_obs (the workflow also sets PYTHONPATH; this keeps
# the script runnable from a plain checkout and under pytest).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from list_qa_matrix import qa_project_type  # noqa: E402

from percona_obs.project_config import RepositoryFilter  # noqa: E402

_SEGMENT = r"[A-Za-z0-9][A-Za-z0-9_.+-]*"
_PROJECT_RE = re.compile(rf"^{_SEGMENT}(:{_SEGMENT})*$")
_PR_RE = re.compile(r"^(|[1-9][0-9]*)$")
_PACKAGE_RE = re.compile(r"^(|[A-Za-z0-9][A-Za-z0-9_.+-]*)$")


def validate_project(project: str) -> None:
    if not _PROJECT_RE.match(project):
        raise SystemExit(
            f"error: invalid project name {project!r}; expected colon notation "
            "such as ppg:staging:18 or ppg:staging:18:containers"
        )


def validate_pr_number(pr_number: str) -> None:
    if not _PR_RE.match(pr_number):
        raise SystemExit(
            f"error: invalid pr_number {pr_number!r}; expected a positive integer or empty"
        )


def validate_package(package: str) -> None:
    if not _PACKAGE_RE.match(package):
        raise SystemExit(
            f"error: invalid package name {package!r}; expected a package "
            "directory name such as pg_tde, or empty"
        )


def _instance_qa_types(instance: dict[str, Any]) -> set[str]:
    raw = instance.get("qa_types") or ""
    if isinstance(raw, list):
        return {str(t).strip() for t in raw if str(t).strip()}
    return {t.strip() for t in str(raw).split(",") if t.strip()}


def _hosts(instance: dict[str, Any], project: str) -> bool:
    filt = RepositoryFilter.from_env_json(json.dumps(instance))
    if not filt.project_passes(project):
        return False
    kinds = _instance_qa_types(instance)
    # Prefix the type check with a dummy root: qa_project_type() looks at the
    # colon structure only, so any root works.
    return not kinds or qa_project_type("root:" + project) in kinds


def resolve_instance(instances: list[dict[str, Any]], project: str) -> dict[str, Any]:
    matches = [i for i in instances if _hosts(i, project)]
    names = ", ".join(str(i.get("name", "?")) for i in instances) or "(none)"
    if not matches:
        raise SystemExit(
            f"error: no OBS instance hosts {project} "
            f"(kind: {qa_project_type('root:' + project)}); "
            f"instances checked: {names}"
        )
    if len(matches) > 1:
        picked = ", ".join(str(i.get("name", "?")) for i in matches)
        raise SystemExit(
            f"error: ambiguous OBS instance for {project}: {picked}; "
            "narrow OBS_INSTANCES with include_projects/exclude_projects or qa_types"
        )
    return matches[0]


def _load_instances(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: OBS_INSTANCES is not valid JSON: {exc}")
    if not isinstance(data, list) or not all(isinstance(i, dict) for i in data):
        raise SystemExit("error: OBS_INSTANCES must be a JSON list of objects")
    return data


def main() -> None:
    project = os.environ.get("QA_PROJECT", "")
    pr_number = os.environ.get("QA_PR_NUMBER", "")
    validate_project(project)
    validate_pr_number(pr_number)
    validate_package(os.environ.get("QA_PACKAGE", ""))

    instances = _load_instances(os.environ.get("OBS_INSTANCES", ""))
    inst = resolve_instance(instances, project)

    if pr_number:
        rootprj = f"{inst.get('pr_rootprj', '')}:pr-{pr_number}"
    else:
        rootprj = str(inst.get("rootprj", ""))
    if not rootprj.strip(":"):
        raise SystemExit(
            f"error: instance {inst.get('name')} has no "
            f"{'pr_rootprj' if pr_number else 'rootprj'}"
        )

    outputs = {
        "instance_name": str(inst.get("name", "")),
        "instance_apiurl": str(inst.get("apiurl", "")),
        "instance_user": str(inst.get("user", "") or ""),
        "instance_registry": str(inst.get("registry", "") or ""),
        "instance_env": json.dumps(inst.get("env")) if inst.get("env") else "null",
        "rootprj": rootprj,
    }
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        for key, value in outputs.items():
            fh.write(f"{key}={value}\n")
    print(
        f"project {project} ({qa_project_type('root:' + project)}) -> "
        f"instance {outputs['instance_name']} root {rootprj}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
