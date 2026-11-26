"""Every release unit project holding an _aggregate package gets aggregate-checklocal."""

import os

import pytest

from percona_obs.common import (
    BUNDLED_SUBPROJECTS,
    REPO_ROOT,
    _load_project_config_with_inheritance,
    auto_rootprj_env,
)
from percona_obs.release_scope import list_release_units

LINE = "BuildFlags: aggregate-checklocal"


def _has_aggregate(project_dir) -> bool:
    for dirpath, _dirs, files in os.walk(project_dir, followlinks=True):
        if "_aggregate" in files:
            return True
    return False


def _aggregate_projects():
    root = REPO_ROOT
    found = []
    for unit in list_release_units(root):
        unit_dir = root.joinpath(*unit["unit"].split(":"))
        for name in (None, *BUNDLED_SUBPROJECTS):
            path = unit_dir / name if name else unit_dir
            if path.is_dir() and _has_aggregate(path):
                found.append(path)
    return found


def test_aggregate_projects_get_checklocal():
    projects = _aggregate_projects()
    assert projects, "no project with an _aggregate package found"
    env_vars = {
        **auto_rootprj_env("ppg"),
        "REMOTE_OBS_ORG_INTERCONNECT": "openSUSE.org:",
    }
    missing = []
    for path in projects:
        cfg = _load_project_config_with_inheritance(path, dict(env_vars))
        if LINE not in cfg["project-config"].splitlines():
            missing.append(str(path.relative_to(REPO_ROOT)))
    assert not missing, f"missing {LINE}: {missing}"
