"""Staged rebuild propagation into frozen release units.

A frozen project (every repository carries ``rebuild="local"``) only rebuilds
a package when that package's own sources change.  A late fix therefore has
to be pushed to its frozen dependents with explicit rebuild triggers, and
those triggers are only safe once the OBS scheduler has seen the change they
depend on: a trigger sent too early rebuilds the dependent against the old
binaries and nothing corrects it afterwards.

This module holds the pure planning part: which packages depend on the
changed ones (``closure``), and in which stages they are triggered
(``plan_stages``).  ``aggregate_edges`` adds the edges of local
``_aggregate`` files, ``expand_failed`` covers frozen projects whose
dependency data could not be fetched, and ``upstream_projects`` lists the
projects whose dependency data the plan needs.
"""

import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import osc.core

from .common import (
    _decode_obs_response,
    apply_env_substitution,
    apply_macro_substitution,
    expand_for_blocks,
    load_macros,
    load_project_yaml,
)

Pkg = tuple[str, str]  # (obs_project, package)

# Package name standing for "every package of the project" in a dependency
# set: an <aggregate> with no <package> children pulls the whole project.
WILDCARD = "*"

SEEN_TIMEOUT_S = 120
SEEN_POLL_S = 2


@dataclass(frozen=True)
class Stage:
    """One propagation step.

    ``wait_for`` must be seen by the scheduler before ``trigger`` is sent;
    ``trigger`` maps a frozen project to the sorted packages to rebuild.
    """

    wait_for: frozenset[Pkg]
    trigger: dict[str, list[str]]


def _depends_on(deps: "set[Pkg]", target: Pkg) -> bool:
    return target in deps or (target[0], WILDCARD) in deps


def _matching(deps: "set[Pkg]", candidates: "set[Pkg]") -> "set[Pkg]":
    """Return the members of *candidates* that *deps* names, wildcards expanded."""
    out: set[Pkg] = set()
    for dep in deps:
        if dep[1] == WILDCARD:
            out.update(c for c in candidates if c[0] == dep[0])
        elif dep in candidates:
            out.add(dep)
    return out


def closure(seeds: "set[Pkg]", fwd_deps: "dict[Pkg, set[Pkg]]") -> "set[Pkg]":
    """Return every package that depends, directly or indirectly, on a seed.

    ``fwd_deps[x]`` is the set of packages *x* depends on; a ``(project,
    "*")`` member matches every package of that project.  Seeds are not part
    of the result, even when a cycle leads back to them.
    """
    reached: set[Pkg] = set(seeds)
    queue: deque[Pkg] = deque(seeds)
    while queue:
        dep = queue.popleft()
        for pkg, deps in fwd_deps.items():
            if pkg not in reached and _depends_on(deps, dep):
                reached.add(pkg)
                queue.append(pkg)
    return reached - set(seeds)


def plan_stages(
    seeds: "set[Pkg]",
    fwd_deps: "dict[Pkg, set[Pkg]]",
    frozen: "set[str]",
    project_order: "list[str]",
    aggregates: "set[Pkg]",
) -> "list[Stage]":
    """Return the staged rebuild plan for the dependents of *seeds*.

    Only closure members in *frozen* projects are triggered; OBS rebuilds the
    others itself.  One stage per frozen project, in *project_order*
    (projects missing from it last, by name); a project's *aggregates* form
    their own stage before its other packages.  Projects with nothing to
    trigger get no stage.

    A stage waits for every seed or closure member a triggered package
    depends on directly, and, behind non-frozen closure members and seeds,
    for every seed and non-frozen member on the way to it.  Frozen members
    are waited for but not walked through: their own stage waited for what
    is behind them.  Members triggered in the same stage are not waited for
    (the scheduler orders them), and neither are members triggered in a
    later stage.
    """
    members = closure(seeds, fwd_deps)
    involved = members | set(seeds)
    to_trigger = {m for m in members if m[0] in frozen}
    if not to_trigger:
        return []

    rank = {prj: i for i, prj in enumerate(project_order)}
    projects = sorted(
        {prj for prj, _ in to_trigger},
        key=lambda prj: (rank.get(prj, len(rank)), prj),
    )

    groups: list[set[Pkg]] = []
    for prj in projects:
        in_prj = {m for m in to_trigger if m[0] == prj}
        for group in (in_prj & aggregates, in_prj - aggregates):
            if group:
                groups.append(group)

    stages: list[Stage] = []
    triggered_before: set[Pkg] = set()
    for group in groups:
        wait: set[Pkg] = set()
        visited: set[Pkg] = set(group)
        queue: deque[Pkg] = deque(group)
        while queue:
            pkg = queue.popleft()
            for dep in _matching(fwd_deps.get(pkg, set()), involved):
                if dep in visited:
                    continue
                visited.add(dep)
                if dep in to_trigger:
                    if dep in triggered_before:
                        wait.add(dep)
                    continue
                wait.add(dep)
                queue.append(dep)
        triggered_before |= group
        trigger: dict[str, list[str]] = {}
        for prj, name in group:
            trigger.setdefault(prj, []).append(name)
        stages.append(
            Stage(frozenset(wait), {p: sorted(n) for p, n in trigger.items()})
        )
    return stages


def expand_failed(
    failed: "set[str]",
    frozen: "set[str]",
    consumers_of: "dict[str, set[str]]",
    packages: "dict[str, list[str]]",
) -> "set[Pkg]":
    """Return every package of the frozen projects the missing data can affect.

    A frozen project is affected when its own dependency data is in *failed*
    or when it consumes (``consumers_of[failed_project]``) a project whose
    data is.  Callers add the result to the closure, so an unknown edge
    rebuilds too much rather than shipping a stale binary.
    """
    affected = {prj for prj in failed if prj in frozen}
    for prj in failed:
        affected |= consumers_of.get(prj, set()) & frozen
    return {(prj, name) for prj in affected for name in packages.get(prj, [])}


def aggregate_edges(
    targets: "list[tuple[str, Path]]", env_vars: "dict[str, str]"
) -> "dict[Pkg, set[Pkg]]":
    """Return forward edges from the local ``obs/_aggregate`` files of *targets*.

    ``edges[(project, aggregate_pkg)]`` is the set of packages it aggregates;
    an ``<aggregate>`` with no ``<package>`` children yields ``(project,
    "*")``.  Files get the substitution ``sync push`` applies before upload
    (macros, ``for`` blocks, then ``${VAR}``), so project names match OBS.
    """
    # Lazy import: cmd_sync imports this module.
    from .cmd_sync import _pkg_env_vars

    edges: dict[Pkg, set[Pkg]] = {}
    for obs_project, package_path in targets:
        agg_file = package_path / "obs" / "_aggregate"
        if not agg_file.is_file():
            continue
        project_config = load_project_yaml(package_path.parent / "project.yaml")
        obs_project_name = project_config.get("name") or obs_project
        text = agg_file.read_text("utf-8")
        pkg_macros = load_macros(package_path)
        if pkg_macros:
            text = apply_macro_substitution(text, pkg_macros, source=agg_file)
            text = expand_for_blocks(text)
        text = apply_env_substitution(
            text, {**env_vars, **_pkg_env_vars(package_path)}, source=agg_file
        )
        root = ET.fromstring(text)
        deps: set[Pkg] = set()
        for agg in root.findall("aggregate"):
            src_project = (agg.get("project") or "").strip()
            if not src_project:
                continue
            names = [
                (el.text or "").strip()
                for el in agg.findall("package")
                if (el.text or "").strip()
            ]
            if names:
                deps.update((src_project, name) for name in names)
            else:
                deps.add((src_project, WILDCARD))
        if deps:
            edges[(obs_project_name, package_path.name)] = deps
    return edges


def _path_projects(meta_xml: str) -> "set[str]":
    root = ET.fromstring(meta_xml)
    return {
        p.get("project", "")
        for repo in root.findall("repository")
        for p in repo.findall("path")
        if p.get("project")
    }


def upstream_projects(apiurl: str, frozen: "set[str]", rootprj: str) -> "set[str]":
    """Return *frozen* plus every project under *rootprj* they build against.

    Follows the ``<path project>`` entries of every repository, transitively.
    Projects outside *rootprj* (distribution bases) are not followed.  A meta
    fetch error propagates: a missing project would mean missing edges.
    """
    result: set[str] = set(frozen)
    queue: deque[str] = deque(sorted(frozen))
    while queue:
        prj = queue.popleft()
        meta = _decode_obs_response(osc.core.show_project_meta(apiurl, prj))
        for path_prj in sorted(_path_projects(meta)):
            if path_prj in result:
                continue
            if path_prj != rootprj and not path_prj.startswith(rootprj + ":"):
                continue
            result.add(path_prj)
            queue.append(path_prj)
    return result
