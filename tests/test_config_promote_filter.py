"""Config-triggered promotion must render the desired config under the branch slice.

``check_project_config_changed`` compares a locally rendered project config
against the project on OBS.  In ``--branch-from`` mode that OBS project is the
production one, written under the *instance* slice, while the active profile may
be narrowed further by PR labels.  Rendering the comparison under the narrower
slice drops repositories the production project still has, so every project
reports "config changed" and cmd_sync force-promotes the whole tree.
"""

from pathlib import Path

import osc.core
import pytest

import percona_obs.common as common
from percona_obs.common import build_project_meta
from percona_obs.obs_api import check_project_config_changed
from percona_obs.project_config import RepositoryFilter, resolve_project_config

_ROOT = """\
project-config: |
  Prefer: something
"""

_DEPS = """\
title: Deps
description: Shared deps
repositories:
  - name: UBI_8
    paths:
      - project: RedHat:UBI-8
        repository: standard
    archs: [x86_64]
  - name: UBI_9
    paths:
      - project: RedHat:UBI-9
        repository: standard
    archs: [x86_64]
"""

# The instance slice the production project was written under (UBI_8 + UBI_9).
INSTANCE = RepositoryFilter(include_repos=("UBI_*", "ubi*", "images"))
# The same profile narrowed by PR labels to a single repository (UBI_9).
NARROWED = RepositoryFilter(include_repos=("UBI_9", "ubi9", "images"))

PROJECT = "isv:percona:ppg:common:deps"
ROOTPRJ = "isv:percona"


@pytest.fixture
def deps_project(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "ppg" / "common" / "deps").mkdir(parents=True)
    (root / "macros.yaml").write_text("- M: 1\n")
    (root / "project.yaml").write_text(_ROOT)
    (root / "ppg" / "common" / "deps" / "project.yaml").write_text(_DEPS)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    return root / "ppg" / "common" / "deps"


@pytest.fixture(autouse=True)
def _reset_default_filter():
    common.set_default_repository_filter(None)
    yield
    common.set_default_repository_filter(None)


@pytest.fixture
def obs_production(deps_project, monkeypatch):
    """Serve the production project exactly as the instance slice wrote it."""
    cfg = resolve_project_config(deps_project, None, INSTANCE)
    meta = build_project_meta(
        PROJECT,
        cfg.get("title", ""),
        cfg.get("description", ""),
        cfg.get("repositories", []),
        ROOTPRJ,
        publish=cfg.get("publish"),
        build=cfg.get("build"),
        debuginfo=cfg.get("debuginfo"),
    )
    conf = (cfg.get("project-config") or "").strip()
    monkeypatch.setattr(osc.core, "show_project_meta", lambda *a, **k: meta.encode())
    monkeypatch.setattr(osc.core, "show_project_conf", lambda *a, **k: conf.encode())
    return meta, conf


def _changed(project_path: Path, repo_filter) -> bool:
    changed, is_new = check_project_config_changed(
        "https://obs.example",
        PROJECT,
        project_path,
        ROOTPRJ,
        env_vars={},
        active_projects=None,
        branch_rootprj=None,
        repo_filter=repo_filter,
    )
    assert is_new is False
    return changed


def test_branch_slice_matches_production(deps_project, obs_production):
    """The branch profile's slice reproduces what production was written with."""
    common.set_default_repository_filter(NARROWED)
    assert _changed(deps_project, INSTANCE) is False


def test_narrowed_slice_would_report_every_project_changed(
    deps_project, obs_production
):
    """Guard the regression: the label-narrowed slice drops UBI_8 and misreports."""
    assert _changed(deps_project, NARROWED) is True


def test_falls_back_to_process_default_when_unset(deps_project, obs_production):
    """repo_filter=None keeps the documented fallback to the active profile."""
    common.set_default_repository_filter(INSTANCE)
    assert _changed(deps_project, None) is False
    common.set_default_repository_filter(NARROWED)
    assert _changed(deps_project, None) is True
