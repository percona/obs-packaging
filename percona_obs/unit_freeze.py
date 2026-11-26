# percona_obs/unit_freeze.py
"""Freeze marker for release units: ``rebuild="local"`` on every repository.

A unit is frozen when its OBS projects (the unit root and its bundled
children) carry ``rebuild="local"`` on all ``<repository>`` elements of the
project meta.  This module only reads and writes that marker and resolves
which OBS projects make up a unit.
"""

import urllib.error
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import osc.core

from .common import (
    BUNDLED_SUBPROJECTS,
    REPO_ROOT,
    _decode_obs_response,
    load_project_yaml,
)
from .obs_api import _edit_project_meta
from .release_scope import list_release_units

REBUILD_FROZEN = "local"


def freeze_state(meta_xml: str) -> str:
    """``frozen``, ``partial``, ``unfrozen`` or ``empty`` (no repositories)."""
    repos = ET.fromstring(meta_xml).findall("repository")
    if not repos:
        return "empty"
    n = sum(1 for r in repos if r.get("rebuild") == REBUILD_FROZEN)
    if n == len(repos):
        return "frozen"
    return "unfrozen" if n == 0 else "partial"


def with_rebuild_mode(meta_xml: str, mode: "str | None") -> str:
    """Meta with ``rebuild`` set to *mode* on every repository (removed if None)."""
    root = ET.fromstring(meta_xml)
    for repo in root.findall("repository"):
        if mode is None:
            repo.attrib.pop("rebuild", None)
        else:
            repo.set("rebuild", mode)
    return ET.tostring(root, encoding="unicode")


def carry_rebuild(current_xml: str, desired_xml: str) -> str:
    """*desired_xml* with the live ``rebuild`` values of *current_xml* kept.

    Each repository takes the value of the same-named live repository.  A
    repository that is new in a fully frozen project is frozen too.
    """
    live = {
        r.get("name"): r.get("rebuild")
        for r in ET.fromstring(current_xml).findall("repository")
    }
    frozen = freeze_state(current_xml) == "frozen"
    root = ET.fromstring(desired_xml)
    for repo in root.findall("repository"):
        mode = live.get(repo.get("name"))
        if mode is None and frozen:
            mode = REBUILD_FROZEN
        if mode is not None:
            repo.set("rebuild", mode)
    return ET.tostring(root, encoding="unicode")


def unit_obs_projects(unit: str, rootprj: str, root: Path = REPO_ROOT) -> "list[str]":
    """OBS projects of release unit *unit*: its root and existing bundled children."""
    units = {u["unit"] for u in list_release_units(root)}
    if unit not in units:
        raise ValueError(f"{unit} is not a release unit")
    unit_dir = root.joinpath(*unit.split(":"))
    projects = []
    for name, path in [(None, unit_dir)] + [
        (n, unit_dir / n) for n in BUNDLED_SUBPROJECTS
    ]:
        yaml_path = path / "project.yaml"
        if not yaml_path.is_file():
            continue
        default = f"{rootprj}:{unit}" + (f":{name}" if name else "")
        projects.append(load_project_yaml(yaml_path).get("name") or default)
    return projects


def _fetch_meta(apiurl: str, project: str) -> "str | None":
    """Project meta XML, or None when the project does not exist."""
    try:
        return _decode_obs_response(osc.core.show_project_meta(apiurl, project))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def apply_freeze(
    apiurl: str, obs_projects: "list[str]", frozen: bool, dry_run: bool
) -> "list[tuple[str, str]]":
    """Set or clear the freeze marker; one ``(project, outcome)`` per project.

    Outcomes: ``changed``, ``unchanged``, ``absent``.  Each write is
    re-fetched and verified.
    """
    mode = REBUILD_FROZEN if frozen else None
    want = "frozen" if frozen else "unfrozen"
    out: "list[tuple[str, str]]" = []
    for prj in obs_projects:
        meta = _fetch_meta(apiurl, prj)
        if meta is None:
            out.append((prj, "absent"))
            continue
        if freeze_state(meta) in (want, "empty"):
            out.append((prj, "unchanged"))
            continue
        if not dry_run:
            _edit_project_meta(apiurl, prj, with_rebuild_mode(meta, mode), force=True)
            after = _fetch_meta(apiurl, prj)
            if after is None or freeze_state(after) != want:
                raise RuntimeError(f"{prj}: freeze state is not {want} after write")
        out.append((prj, "changed"))
    return out


def frozen_projects(apiurl: str, obs_projects: "list[str]") -> "dict[str, str]":
    """``{project: freeze_state}``; projects absent on OBS are omitted."""

    def one(prj: str) -> "tuple[str, str | None]":
        meta = _fetch_meta(apiurl, prj)
        return prj, None if meta is None else freeze_state(meta)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, obs_projects))
    return {prj: state for prj, state in results if state is not None}
