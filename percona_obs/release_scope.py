# percona_obs/release_scope.py
"""Extra freeze scope for ``sync release`` (spec Section 2.1).

``sync release`` freezes the release source project and its subprojects.
Two further kinds of source hold binaries the release copies:

* **aggregate sources** — every ``obs/_aggregate`` in the source tree pulls
  binaries from another local project (``ppg:staging:common:tools``,
  ``ppg:common:deps``).  Only the aggregated packages are frozen there.
* **path-prefix sources** — for a release source without a server package
  (a cross-version parent such as ``ppg:staging:common``), every
  image-holding project under it may consume any package of the
  ``subproject:`` entries in its repository paths, so those projects are
  frozen whole.

Both kinds are limited to the active instance slice (the process default
``RepositoryFilter`` installed from the profile): a package or project that
the instance never builds is neither checked nor frozen there.

Everything here is a pure function of the git tree; no OBS traffic.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .common import (
    BUNDLED_SUBPROJECTS,
    REPO_ROOT,
    find_packages,
    is_shared_source_dir,
)
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


def release_unit_members(
    source_path: Path, source_project_id: str
) -> "list[tuple[str, Path]]":
    """[(project_id, path)] of a release unit: its root, then the bundled
    children (``containers``, ``tarballs``) that are OBS projects."""
    members = [(source_project_id, source_path)]
    for name in BUNDLED_SUBPROJECTS:
        child = source_path / name
        if (child / "project.yaml").is_file():
            members.append((f"{source_project_id}:{name}", child))
    return members


def unit_packages(source_path: Path, source_project_id: str):
    """Yield (project_id, package_path) for every package of a release unit."""
    for project_id, path in release_unit_members(source_path, source_project_id):
        yield from find_packages(path, project_id, recursive=False)


def unit_members_in_slice(
    source_path: Path,
    source_project_id: str,
    env_vars: "dict[str, str] | None" = None,
    repo_filter: "RepositoryFilter | None" = None,
) -> "list[str]":
    """Project ids of the unit members that hold a package of the slice
    (*repo_filter*, default the active one).

    Empty when the instance does not carry the unit at all: instances hold
    disjoint slices, and a unit can live on one of them only
    (``ppg:staging:16:tde`` has no UBI repository; ``ppg:staging:18:extras``
    builds only for UBI).  Packages decide, not repositories: a package-less
    unit root keeps repositories on an instance that carries none of the
    unit's packages, and is not created there.
    """
    return [
        member
        for member, path in release_unit_members(source_path, source_project_id)
        if any(
            package_in_slice(pkg_path, env_vars, repo_filter=repo_filter)
            for _, pkg_path in find_packages(path, member, recursive=False)
        )
    ]


def bundled_parent(project_id: str) -> "str | None":
    """The unit root a bundled child belongs to, or None for a unit root."""
    parent, _, name = project_id.rpartition(":")
    return parent if name in BUNDLED_SUBPROJECTS and parent else None


def nested_unit_dirs(source_path: Path) -> "list[Path]":
    """Directories of the direct child projects that are release units of
    their own (non-bundled children with a ``project.yaml``)."""
    if not source_path.is_dir():
        return []
    return [
        child
        for child in sorted(source_path.iterdir())
        if child.is_dir()
        and child.name not in BUNDLED_SUBPROJECTS
        and not is_shared_source_dir(child)
        and (child / "project.yaml").is_file()
    ]


def nested_unit_roots(source_path: Path, source_project_id: str) -> "list[str]":
    """Direct child projects that are release units of their own."""
    return [
        f"{source_project_id}:{child.name}" for child in nested_unit_dirs(source_path)
    ]


def list_release_units(root: Path = REPO_ROOT) -> "list[dict]":
    """Every releasable staging unit of the tree (git only), sorted by unit.

    A unit is a staging project (at any depth below ``<product>/staging``)
    that holds packages in itself or in its bundled children.  Namespace
    roots without packages (``ppg:staging``, ``ppg:staging:common``) are not
    units, but are descended into.  A unit that was never released is listed.
    """
    units: "list[dict]" = []

    def walk(path: Path, project_id: str) -> None:
        for child in nested_unit_dirs(path):
            child_id = f"{project_id}:{child.name}"
            if any(True for _ in unit_packages(child, child_id)):
                release_project = release_location(child_id).release_project
                units.append(
                    {
                        "unit": child_id,
                        "members": [
                            m for m, _ in release_unit_members(child, child_id)
                        ],
                        "release_project": release_project,
                        "release_dir": "root/" + release_project.replace(":", "/"),
                    }
                )
            walk(child, child_id)

    if root.is_dir():
        for product in sorted(root.iterdir()):
            staging = product / "staging"
            if product.is_dir() and staging.is_dir():
                walk(staging, f"{product.name}:staging")
    return sorted(units, key=lambda u: u["unit"])


@dataclass(frozen=True)
class ReleaseLocation:
    product: str
    major: str  # third component of the source id: "18", "common"
    top: str  # release directory name of that component (--release-name)
    unit_path: "tuple[str, ...]"  # components below it: ("extras",), ()
    release_dir: Path
    release_project: str

    @property
    def id_prefix(self) -> str:
        """PG-mode id prefix: "" for a major, "extras-" for 18:extras."""
        return "".join(f"{p}-" for p in self.unit_path)

    @property
    def counter_name(self) -> str:
        """Counter-mode id stem: "common", "common-upgrade-extras"."""
        return "-".join((self.top, *self.unit_path))


def release_location(
    project_id: str, release_name: "str | None" = None
) -> ReleaseLocation:
    """Where a staging unit root is released to (spec § 2)."""
    parts = project_id.split(":")
    product, major, unit_path = parts[0], parts[2], tuple(parts[3:])
    top = release_name or major
    rel = (top, *unit_path)
    return ReleaseLocation(
        product=product,
        major=major,
        top=top,
        unit_path=unit_path,
        release_dir=REPO_ROOT.joinpath(product, "releases", *rel),
        release_project=":".join((product, "releases", *rel)),
    )


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
    """True when the release unit holds the server package.

    Decides the release-id mode of ``project release`` from the git tree:
    a PG major carries ``percona-postgresql`` (or ``percona-postgresqlNN``)
    and gets ``MAJOR.MINOR-N`` ids; a cross-version parent such as
    ``ppg:staging:common`` does not and gets a plain counter.
    """
    return any(
        _SERVER_PKG_RE.match(pkg_path.name)
        for _, pkg_path in unit_packages(source_path, "")
    )


def collect_release_scope(
    source_path: Path,
    source_project_id: str,
    rootprj: str,
    env_vars: "dict[str, str] | None",
) -> ReleaseScope:
    scope = ReleaseScope()
    members = release_unit_members(source_path, source_project_id)
    own_ids = {pid for pid, _ in members}

    for _, pkg_path in unit_packages(source_path, source_project_id):
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

    # A PG major's own containers/extras:containers subprojects list
    # ppg:common:deps, common:containers:* and the previous major on their
    # paths; those are aggregate-covered or unrelated, and per-major releases
    # stay aggregate-scoped (spec Decision 3).  Only a cross-version parent
    # (no server package) freezes its image projects' path sources whole.
    if not tree_has_server_package(source_path):
        for _, project_path in members:
            if not has_container_images(project_path):
                continue
            cfg = resolve_project_config(
                project_path, env_vars or {}, repo_filter=RepositoryFilter.EMPTY
            )
            for repo in cfg.get("repositories", []):
                for entry in repo.get("paths", []):
                    sub = entry.get("subproject")
                    if not sub or sub in own_ids:
                        continue
                    sub_path = REPO_ROOT.joinpath(*sub.split(":"))
                    if not sub_path.is_dir() or not project_in_slice(
                        sub_path, env_vars
                    ):
                        continue
                    full = f"{rootprj}:{sub}"
                    if full not in scope.whole_projects:
                        scope.whole_projects.append(full)
    return scope
