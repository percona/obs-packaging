# percona_obs/release_scope.py
"""Extra freeze scope for ``sync release`` (spec Section 2.1).

``sync release`` freezes the release source project and its subprojects.
Two further kinds of source hold binaries the release copies:

* **aggregate sources** — every ``obs/_aggregate`` in the source tree pulls
  binaries from another local project (``ppg:staging:tools``,
  ``ppg:common:deps``).  Only the aggregated packages are frozen there.
* **path-prefix sources** — a container project's images may consume any
  package of the ``subproject:`` entries in its repository paths, so those
  projects are frozen whole.

Both kinds are limited to the active instance slice (the process default
``RepositoryFilter`` installed from the profile): a package or project that
the instance never builds is neither checked nor frozen there.

Everything here is a pure function of the git tree; no OBS traffic.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .common import REPO_ROOT, find_packages, find_projects
from .project_config import (
    RepositoryFilter,
    package_in_slice,
    project_in_slice,
    resolve_project_config,
)

_LOCAL_AGGREGATE_RE = re.compile(r"^\$\{OBS_ROOTPRJ\}:(.+)$")


@dataclass
class ReleaseScope:
    whole_projects: list[str] = field(default_factory=list)
    packages: dict[str, set[str]] = field(default_factory=dict)


def _local_aggregates(aggregate_file: Path) -> "list[tuple[str, str]]":
    """Return [(local_project_id, package)] for every local aggregate entry."""
    try:
        root_el = ET.fromstring(aggregate_file.read_text("utf-8"))
    except (ET.ParseError, OSError):
        return []
    out: list[tuple[str, str]] = []
    for agg in root_el.findall("aggregate"):
        m = _LOCAL_AGGREGATE_RE.match((agg.get("project") or "").strip())
        if not m:
            continue
        for pkg_el in agg.findall("package"):
            pkg = (pkg_el.text or "").strip()
            if pkg:
                out.append((m.group(1), pkg))
    return out


def has_container_images(project_path: Path) -> bool:
    return any(
        (p / "obs" / "Dockerfile").is_file()
        for p in project_path.iterdir()
        if p.is_dir()
    )


_SERVER_PKG_RE = re.compile(r"^percona-postgresql\d*$")


def tree_has_server_package(source_path: Path) -> bool:
    """True when the source project or any subproject holds the server package.

    Decides the release-id mode of ``project release`` from the git tree:
    a PG major carries ``percona-postgresql`` (or ``percona-postgresqlNN``)
    and gets ``MAJOR.MINOR-N`` ids; a cross-version parent such as
    ``ppg:staging:common`` does not and gets a plain counter.
    """
    return any(
        _SERVER_PKG_RE.match(pkg_path.name)
        for _, pkg_path in find_packages(source_path, "")
    )


def collect_release_scope(
    source_path: Path,
    source_project_id: str,
    rootprj: str,
    env_vars: "dict[str, str] | None",
) -> ReleaseScope:
    scope = ReleaseScope()
    own_ids = {source_project_id}
    for sub_id, _ in find_projects(source_path, source_project_id):
        own_ids.add(sub_id)

    for _, pkg_path in find_packages(source_path, source_project_id):
        agg_file = pkg_path / "obs" / "_aggregate"
        if not agg_file.is_file():
            continue
        for local_id, pkg in _local_aggregates(agg_file):
            if local_id in own_ids:
                continue
            target = REPO_ROOT.joinpath(*local_id.split(":"), pkg)
            if not target.is_dir() or not package_in_slice(target, env_vars):
                continue
            scope.packages.setdefault(f"{rootprj}:{local_id}", set()).add(pkg)

    if has_container_images(source_path):
        cfg = resolve_project_config(
            source_path, env_vars or {}, repo_filter=RepositoryFilter.EMPTY
        )
        for repo in cfg.get("repositories", []):
            for entry in repo.get("paths", []):
                sub = entry.get("subproject")
                if not sub or sub in own_ids:
                    continue
                sub_path = REPO_ROOT.joinpath(*sub.split(":"))
                if not sub_path.is_dir() or not project_in_slice(sub_path, env_vars):
                    continue
                full = f"{rootprj}:{sub}"
                if full not in scope.whole_projects:
                    scope.whole_projects.append(full)
    return scope
