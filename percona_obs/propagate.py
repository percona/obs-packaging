"""Staged rebuild propagation into frozen release units.

A frozen project (every repository carries ``rebuild="local"``) only rebuilds
a package when that package's own sources change.  A late fix therefore has
to be pushed to its frozen dependents with explicit rebuild triggers, and
those triggers are only safe once the OBS scheduler has seen the change they
depend on: a trigger sent too early rebuilds the dependent against the old
binaries and nothing corrects it afterwards.

Planning: which packages depend on the changed ones (``closure``), and in
which stages they are triggered (``plan_stages``).  ``aggregate_edges`` adds
the edges of local ``_aggregate`` files, ``expand_failed`` covers frozen
projects whose dependency data could not be fetched, and
``upstream_projects`` lists the projects whose dependency data the plan
needs.

Running: ``run_stages`` waits until the scheduler has seen each stage's
prerequisites (``wait_seen``) and then sends the stage's ``cmd=rebuild``
triggers (``trigger_rebuild``).  ``propagate`` composes everything.
"""

import shlex
import time
import urllib.error
import xml.etree.ElementTree as ET
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import osc.connection
import osc.core

from . import release_freeze
from .common import (
    _decode_obs_response,
    _print_action,
    apply_env_substitution,
    apply_macro_substitution,
    expand_for_blocks,
    load_macros,
    load_project_yaml,
    logger,
)
from .obs_api import _fetch_combined_depinfo, _fetch_obs_package_names_or_fail
from .release_scope import list_release_units
from .targets import image_dep_query_repos, is_dockerfile_image
from .unit_freeze import _fetch_meta, frozen_projects, unit_obs_projects

Pkg = tuple[str, str]  # (obs_project, package)
# One build target of a package: (status package name, repository, arch).
# The status name is the package or one of its multibuild flavors
# ("pkg:flavor").
Target = tuple[str, str, str]

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
    *,
    extra: "set[Pkg] | frozenset[Pkg]" = frozenset(),
) -> "list[Stage]":
    """Return the staged rebuild plan for the dependents of *seeds*.

    Triggered: closure members in *frozen* projects (OBS rebuilds the others
    itself), seeds in frozen projects that depend, directly or indirectly,
    on another seed (their own upload alone may be built against the other
    seed's old binary), and the members of *extra* in frozen projects
    (e.g. ``expand_failed`` output), whose dependents join the closure too.
    Every other seed is never triggered.

    Triggered packages are grouped per project, a project's *aggregates*
    apart from its other packages.  Groups are ordered by the dependency
    graph; *project_order* (projects missing from it last, by name), then
    aggregates before other packages, only breaks ties.  Groups that depend
    on each other (a cycle) are merged into one stage, whose trigger may
    then hold several projects.  Groups with nothing to trigger get no stage.

    A stage waits for every package its triggered packages reach through
    their dependencies, walking through seeds and non-frozen members;
    triggered packages reached are waited for (they come from earlier
    stages) but not walked through, since their own stage waited for what
    is behind them.  Packages triggered in the same stage are not waited
    for, except seeds, which are seen through their own upload.  A
    triggered package with no dependency among the involved packages (an
    *extra* member) makes its stage wait for every seed.
    """
    seed_set = set(seeds)
    start = seed_set | set(extra)
    members = closure(start, fwd_deps) | set(extra)
    chained = {s for s in seed_set if s in closure(start - {s}, fwd_deps)}
    involved = members | seed_set
    to_trigger = {m for m in members | chained if m[0] in frozen}
    if not to_trigger:
        return []

    # Per triggered package: non-triggered packages it reaches (to wait for)
    # and the triggered packages that bound the walk.
    reach_wait: dict[Pkg, set[Pkg]] = {}
    reach_trig: dict[Pkg, set[Pkg]] = {}
    for pkg in to_trigger:
        wait: set[Pkg] = set()
        trig: set[Pkg] = set()
        visited: set[Pkg] = {pkg}
        queue: deque[Pkg] = deque([pkg])
        while queue:
            cur = queue.popleft()
            for dep in _matching(fwd_deps.get(cur, set()), involved):
                if dep in visited:
                    continue
                visited.add(dep)
                if dep in to_trigger:
                    trig.add(dep)
                else:
                    wait.add(dep)
                    queue.append(dep)
        if not wait and not trig:
            wait = set(seed_set)
        reach_wait[pkg] = wait
        reach_trig[pkg] = trig

    rank = {prj: i for i, prj in enumerate(project_order)}

    def group_key(pkg: Pkg) -> "tuple[int, str, int]":
        return (rank.get(pkg[0], len(rank)), pkg[0], 0 if pkg in aggregates else 1)

    groups: dict[tuple[int, str, int], set[Pkg]] = {}
    for pkg in to_trigger:
        groups.setdefault(group_key(pkg), set()).add(pkg)
    group_deps: dict[tuple[int, str, int], set[tuple[int, str, int]]] = {
        g: {group_key(d) for p in pkgs for d in reach_trig[p]} - {g}
        for g, pkgs in groups.items()
    }

    def reachable(g: "tuple[int, str, int]") -> "set[tuple[int, str, int]]":
        seen: set[tuple[int, str, int]] = set()
        stack = [g]
        while stack:
            for d in group_deps[stack.pop()]:
                if d not in seen:
                    seen.add(d)
                    stack.append(d)
        return seen

    reach = {g: reachable(g) for g in groups}
    # Strongly connected sets of groups, each named by its smallest key.
    comp_of: dict[tuple[int, str, int], tuple[int, str, int]] = {}
    for g in sorted(groups):
        if g not in comp_of:
            for h in groups:
                if h == g or (h in reach[g] and g in reach[h]):
                    comp_of[h] = g
    comp_deps: dict[tuple[int, str, int], set[tuple[int, str, int]]] = {}
    for g, deps in group_deps.items():
        comp_deps.setdefault(comp_of[g], set()).update(
            comp_of[d] for d in deps if comp_of[d] != comp_of[g]
        )

    order: list[tuple[int, str, int]] = []
    pending = dict(comp_deps)
    while pending:
        ready = min(c for c, deps in pending.items() if not deps - set(order))
        order.append(ready)
        del pending[ready]

    stages: list[Stage] = []
    triggered_before: set[Pkg] = set()
    for comp in order:
        stage_pkgs = {p for g in groups if comp_of[g] == comp for p in groups[g]}
        wait: set[Pkg] = set()
        for pkg in stage_pkgs:
            wait |= reach_wait[pkg]
            for dep in reach_trig[pkg]:
                if dep in triggered_before or (dep in stage_pkgs and dep in seed_set):
                    wait.add(dep)
        triggered_before |= stage_pkgs
        trigger: dict[str, list[str]] = {}
        for prj, name in sorted(stage_pkgs, key=group_key):
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


def _project_path_projects(apiurl: str, prj: str) -> "set[str]":
    """The ``<path project>`` entries of every repository of *prj*."""
    return _path_projects(_decode_obs_response(osc.core.show_project_meta(apiurl, prj)))


def _path_map(apiurl: str, start: "set[str]", rootprj: str) -> "dict[str, set[str]]":
    """``{project: path projects under rootprj}`` for *start* and everything
    they build against, transitively.

    Projects outside *rootprj* (distribution bases) are neither keys nor
    values.  A meta fetch error propagates: a missing project would mean
    missing edges.
    """

    def under_root(prj: str) -> bool:
        return prj == rootprj or prj.startswith(rootprj + ":")

    paths: dict[str, set[str]] = {}
    queue: deque[str] = deque(sorted(start))
    while queue:
        prj = queue.popleft()
        if prj in paths:
            continue
        paths[prj] = {p for p in _project_path_projects(apiurl, prj) if under_root(p)}
        queue.extend(sorted(paths[prj] - set(paths)))
    return paths


def upstream_projects(apiurl: str, frozen: "set[str]", rootprj: str) -> "set[str]":
    """Return *frozen* plus every project under *rootprj* they build against.

    Follows the ``<path project>`` entries of every repository, transitively.
    Projects outside *rootprj* (distribution bases) are not followed.  A meta
    fetch error propagates: a missing project would mean missing edges.
    """
    return set(_path_map(apiurl, frozen, rootprj))


# ---------------------------------------------------------------------------
# Running a plan

# Package codes of targets that never build; they are ignored by the waits.
_NOT_BUILT_CODES = frozenset({"excluded", "disabled"})
_JOB_WORKERS = 8


def trigger_rebuild(apiurl: str, obs_project: str, packages: "list[str]") -> None:
    """Send ``cmd=rebuild`` for *packages* of *obs_project*, 50 per request."""
    for i in range(0, len(packages), 50):
        url = osc.core.makeurl(
            apiurl,
            ["build", obs_project],
            query={"cmd": "rebuild", "package": packages[i : i + 50]},
        )
        osc.connection.http_POST(url)


def _project_codes(apiurl: str, prj: str) -> "dict[Target, str] | None":
    """Built targets of every package of *prj*: ``{target: code}``.

    Excluded and disabled targets are left out; a project absent on this
    instance has none (``{}``).  ``None`` when the results cannot be read.
    """
    try:
        pkg_codes, _ = release_freeze.fetch_project_results(apiurl, prj)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}
        logger.debug(f"propagate: build results of {prj}: {exc}")
        return None
    except Exception as exc:
        logger.debug(f"propagate: build results of {prj}: {exc}")
        return None
    return {t: c for t, c in pkg_codes.items() if c not in _NOT_BUILT_CODES}


def _pkg_targets(codes: "dict[Target, str]", name: str) -> "dict[Target, str]":
    """The targets of package *name*, its multibuild flavors included."""
    return {
        t: c for t, c in codes.items() if t[0] == name or t[0].startswith(name + ":")
    }


def _newest_job(apiurl: str, prj: str, target: Target) -> "tuple[str, str, int]":
    """``(identity, srcmd5, readytime)`` of the newest job of *target*;
    ``("", "", 0)`` when the job history is empty."""
    name, repo, arch = target
    url = osc.core.makeurl(
        apiurl,
        ["build", prj, repo, arch, "_jobhistory"],
        query={"package": name, "limit": 1},
    )
    root = ET.fromstring(osc.connection.http_GET(url).read())
    jobs = root.findall("jobhist")
    if not jobs:
        return "", "", 0
    job = max(jobs, key=lambda j: int(j.get("readytime") or 0))
    srcmd5 = job.get("srcmd5", "")
    readytime = int(job.get("readytime") or 0)
    return f"{job.get('readytime', '')}:{srcmd5}", srcmd5, readytime


# Prefix of a record taken from the binary list, for targets without job
# history (aggregates: the scheduler copies them without a build job).
_BINARIES_PREFIX = "binaries:"


def _binaries_signature(apiurl: str, prj: str, target: Target) -> str:
    """Sorted ``(filename, mtime, size)`` of *target*'s binary list."""
    name, repo, arch = target
    url = osc.core.makeurl(apiurl, ["build", prj, repo, arch, name])
    root = ET.fromstring(osc.connection.http_GET(url).read())
    entries = sorted(
        (b.get("filename", ""), b.get("mtime", ""), b.get("size", ""))
        for b in root.findall("binary")
    )
    return _BINARIES_PREFIX + ";".join("|".join(e) for e in entries)


def _source_md5s(apiurl: str, prj: str, name: str) -> "set[str]":
    """The md5s naming the current source: ``srcmd5`` and ``verifymd5``."""
    url = osc.core.makeurl(apiurl, ["source", prj, name], query={"view": "info"})
    root = ET.fromstring(osc.connection.http_GET(url).read())
    return {m for m in (root.get("srcmd5"), root.get("verifymd5")) if m}


def _source_commit_time(apiurl: str, prj: str, name: str) -> int:
    """Time (OBS server clock, epoch seconds) of the newest source revision."""
    url = osc.core.makeurl(
        apiurl, ["source", prj, name, "_history"], query={"limit": 1}
    )
    root = ET.fromstring(osc.connection.http_GET(url).read())
    return max(
        (int((r.findtext("time") or "0").strip()) for r in root.findall("revision")),
        default=0,
    )


def record_since(apiurl: str, pkgs: "set[Pkg]") -> "dict[Pkg, dict[Target, str]]":
    """Record the current state of every built target of *pkgs*.

    The record is the identity of the newest job, or, for a target without
    job history (an aggregate), its binary-list signature.  ``wait_seen``
    counts a target as seen once that record changes.  Read errors
    propagate: a missing record would make the next wait pass at once, and
    the trigger after it could come too early.
    """
    jobs: list[tuple[Pkg, Target]] = []
    since: dict[Pkg, dict[Target, str]] = {pkg: {} for pkg in pkgs}
    for prj in sorted({p for p, _ in pkgs}):
        try:
            pkg_codes, _ = release_freeze.fetch_project_results(apiurl, prj)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            pkg_codes = {}
        codes = {t: c for t, c in pkg_codes.items() if c not in _NOT_BUILT_CODES}
        for pkg in sorted(p for p in pkgs if p[0] == prj):
            jobs.extend((pkg, t) for t in sorted(_pkg_targets(codes, pkg[1])))

    def one(item: "tuple[Pkg, Target]") -> "tuple[Pkg, Target, str]":
        pkg, target = item
        ident = _newest_job(apiurl, pkg[0], target)[0]
        if not ident:
            ident = _binaries_signature(apiurl, pkg[0], target)
        return pkg, target, ident

    with ThreadPoolExecutor(max_workers=_JOB_WORKERS) as pool:
        for pkg, target, ident in pool.map(one, jobs):
            since[pkg][target] = ident
    return since


class _SeenRules:
    """Decides whether one non-pending target shows the change.

    - A package in *since* (triggered by us): its record changed (newest
      job, or binary list for a job-less target).  Checked first, so a seed
      we triggered waits for the rebuild we asked for.
    - A seed: its newest job built the current source.
    - Any other package (a member OBS rebuilds by itself): its newest job
      became ready after the newest seed commit.
    """

    def __init__(
        self,
        apiurl: str,
        since: "dict[Pkg, dict[Target, str]]",
        seeds: "set[Pkg] | frozenset[Pkg]",
    ):
        self.apiurl = apiurl
        self.since = since
        self.seeds = seeds
        self._md5s: dict[Pkg, set[str]] = {}
        self._seed_time: "int | None" = None

    def seed_time(self) -> int:
        if self._seed_time is None:
            self._seed_time = max(
                (_source_commit_time(self.apiurl, p, n) for p, n in self.seeds),
                default=0,
            )
        return self._seed_time

    def shows_change(self, pkg: Pkg, target: Target) -> bool:
        ident, srcmd5, readytime = _newest_job(self.apiurl, pkg[0], target)
        if pkg in self.since:
            recorded = self.since[pkg].get(target, "")
            if ident:
                return ident != recorded
            if recorded.startswith(_BINARIES_PREFIX):
                return recorded != _binaries_signature(self.apiurl, pkg[0], target)
            return False
        if pkg in self.seeds:
            if pkg not in self._md5s:
                self._md5s[pkg] = _source_md5s(self.apiurl, pkg[0], pkg[1])
            return srcmd5 in self._md5s[pkg]
        if not self.seeds or not readytime:
            return False
        return readytime > self.seed_time()


def _poll_unseen(
    apiurl: str,
    pkgs: "set[Pkg]",
    rules: _SeenRules,
    seen: "set[tuple[Pkg, Target]]",
) -> "set[Pkg]":
    """One poll of ``wait_seen``: the members of *pkgs* not seen yet.

    *seen* (targets already seen) carries over between polls.
    """
    unseen: set[Pkg] = set()
    to_check: list[tuple[Pkg, Target]] = []
    for prj in sorted({p for p, _ in pkgs}):
        codes = _project_codes(apiurl, prj)
        prj_pkgs = {p for p in pkgs if p[0] == prj}
        if codes is None:
            unseen |= prj_pkgs
            continue
        for pkg in prj_pkgs:
            for target, code in _pkg_targets(codes, pkg[1]).items():
                if (pkg, target) in seen:
                    continue
                if code in release_freeze.PENDING_PKG_CODES:
                    seen.add((pkg, target))
                else:
                    to_check.append((pkg, target))

    def one(item: "tuple[Pkg, Target]") -> bool:
        try:
            return rules.shows_change(*item)
        except Exception as exc:
            logger.debug(f"propagate: state of {item[0][0]}/{item[1]}: {exc}")
            return False

    with ThreadPoolExecutor(max_workers=_JOB_WORKERS) as pool:
        for item, ok in zip(to_check, pool.map(one, to_check)):
            if ok:
                seen.add(item)
            else:
                unseen.add(item[0])
    return unseen


def wait_seen(
    apiurl: str,
    pkgs: "set[Pkg]",
    since: "dict[Pkg, dict[Target, str]]",
    timeout_s: float = SEEN_TIMEOUT_S,
    poll_s: float = SEEN_POLL_S,
    sleep: "Callable[[float], None]" = time.sleep,
    clock: "Callable[[], float]" = time.monotonic,
    *,
    seeds: "set[Pkg] | frozenset[Pkg]" = frozenset(),
) -> "set[Pkg]":
    """Wait until the scheduler has seen every package of *pkgs*.

    A package is seen when every target it builds on (excluded and disabled
    targets ignored; a package with none left is seen) is pending
    (``release_freeze.PENDING_PKG_CODES``) or shows the change by the rule
    of its class (see ``_SeenRules``): packages in *since* were triggered by
    us, *seeds* are the changed packages, anything else is a member OBS
    rebuilds by itself.  A target seen once stays seen.

    Returns the packages still not seen when *timeout_s* runs out.
    """
    deadline = clock() + timeout_s
    rules = _SeenRules(apiurl, since, seeds)
    seen: set[tuple[Pkg, Target]] = set()
    remaining = set(pkgs)
    while True:
        remaining = _poll_unseen(apiurl, remaining, rules, seen)
        if not remaining or clock() >= deadline:
            return remaining
        sleep(poll_s)


def _names(pkgs: "set[Pkg] | frozenset[Pkg]") -> str:
    return ", ".join(f"{p}/{n}" for p, n in sorted(pkgs))


def _describe_codes(apiurl: str, pkgs: "set[Pkg]") -> str:
    """``prj/pkg [repo/arch: code, ...]`` per package, for the timeout warning."""
    parts: list[str] = []
    codes_by_prj = {prj: _project_codes(apiurl, prj) for prj in {p for p, _ in pkgs}}
    for prj, name in sorted(pkgs):
        codes = codes_by_prj[prj]
        if codes is None:
            parts.append(f"{prj}/{name} [build results unreadable]")
            continue
        states = ", ".join(
            f"{repo}/{arch}{'' if t_name == name else ' ' + t_name}: {code}"
            for (t_name, repo, arch), code in sorted(
                _pkg_targets(codes, name).items(), key=lambda kv: kv[0][1:] + kv[0][:1]
            )
        )
        parts.append(f"{prj}/{name} [{states}]")
    return "; ".join(parts)


def run_stages(
    apiurl: str,
    stages: "list[Stage]",
    dry_run: bool,
    *,
    seeds: "set[Pkg] | frozenset[Pkg]" = frozenset(),
    sleep: "Callable[[float], None]" = time.sleep,
    clock: "Callable[[], float]" = time.monotonic,
) -> None:
    """Send the triggers of *stages* in order, each after its wait.

    The state of each stage's packages is recorded (``record_since``) right
    before they are triggered; later waits on them need that record, and a
    triggered package without one is an error.  *seeds* tells the waits
    which packages are the changed ones.  A wait that times out prints a
    warning with the packages' current codes and the stage is triggered
    anyway.  With *dry_run* the stages are only printed.
    """
    known: dict[Pkg, dict[Target, str]] = {}
    triggered_before: set[Pkg] = set()
    for i, stage in enumerate(stages, 1):
        triggered = {(prj, n) for prj, names in stage.trigger.items() for n in names}
        prefix = "dry-run: " if dry_run else ""
        _print_action(
            f"{prefix}propagate stage {i}/{len(stages)}: wait for "
            f"{_names(stage.wait_for) or 'nothing'}"
        )
        for prj, names in stage.trigger.items():
            print(f"      {prj}: {' '.join(names)}")
        if dry_run:
            triggered_before |= triggered
            continue
        missing = {p for p in stage.wait_for & triggered_before if p not in known}
        if missing:
            raise RuntimeError(
                f"propagate stage {i}: no record for triggered {_names(missing)}"
            )
        if stage.wait_for:
            unseen = wait_seen(
                apiurl,
                set(stage.wait_for),
                known,
                sleep=sleep,
                clock=clock,
                seeds=seeds,
            )
            if unseen:
                print(
                    f"warning: propagate stage {i}: not seen by the scheduler "
                    f"after {SEEN_TIMEOUT_S}s: {_describe_codes(apiurl, unseen)}; "
                    "triggering anyway"
                )
        known.update(record_since(apiurl, triggered))
        triggered_before |= triggered
        for prj, names in stage.trigger.items():
            trigger_rebuild(apiurl, prj, names)


def _project_order(paths: "dict[str, set[str]]") -> "list[str]":
    """Projects ordered so each comes after every project in its paths."""
    order: list[str] = []
    done: set[str] = set()

    def visit(prj: str, stack: "set[str]") -> None:
        if prj in done or prj in stack:
            return
        stack.add(prj)
        for dep in sorted(paths.get(prj, set())):
            visit(dep, stack)
        stack.discard(prj)
        done.add(prj)
        order.append(prj)

    for prj in sorted(paths):
        visit(prj, set())
    return order


def _image_pkgs(
    targets: "list[tuple[str, Path]]", env_vars: "dict[str, str]", projects: "set[str]"
) -> "dict[str, list[tuple[str, str, str]]]":
    """Dockerfile images of *projects*, in ``_fetch_combined_depinfo`` form.

    Same shape as ``sync push`` builds it: one ``(project, repo, "x86_64")``
    entry per image repository.
    """
    image_pkgs: dict[str, list[tuple[str, str, str]]] = {}
    repos_cache: dict[Path, set[str]] = {}
    for obs_project, pkg_path in targets:
        if obs_project not in projects or not is_dockerfile_image(pkg_path):
            continue
        for repo in sorted(image_dep_query_repos(pkg_path, env_vars, repos_cache)):
            image_pkgs.setdefault(pkg_path.name, []).append(
                (obs_project, repo, "x86_64")
            )
    return image_pkgs


def _project_exists(apiurl: str, prj: str) -> bool:
    return _fetch_meta(apiurl, prj) is not None


def recovery_command(
    apiurl: str,
    rootprj: str,
    seeds: "set[Pkg]",
    env_overrides: "list[str] | None",
    profile: "str | None",
) -> str:
    """The ``build propagate`` command line that repeats this run.

    ``-P`` brings the profile's slice (repository filter); the explicit
    ``-A``/``-R`` values override the profile's, and the ``-e`` values come
    last, so the run resolves to the same apiurl, rootprj and env vars.
    """
    argv = ["percona-obs"]
    if profile:
        argv += ["-P", profile]
    argv += ["-A", apiurl, "-R", rootprj]
    for entry in env_overrides or []:
        argv += ["-e", entry]
    argv += ["build", "propagate"] + [f"{p}/{n}" for p, n in sorted(seeds)]
    return shlex.join(argv)


def propagate(
    apiurl: str,
    rootprj: str,
    seeds: "set[Pkg]",
    targets: "list[tuple[str, Path]]",
    env_vars: "dict[str, str]",
    dry_run: bool,
    *,
    env_overrides: "list[str] | None" = None,
    profile: "str | None" = None,
) -> None:
    """Trigger rebuilds of everything in a frozen project that depends on *seeds*.

    *targets* are the local ``(obs_project, package_path)`` packages (for
    ``_aggregate`` edges, image edges and the dependency filter) and
    *env_vars* the substitution variables of ``sync push``.  Does nothing,
    and queries no dependency, when no release unit project is frozen.

    *profile* and *env_overrides* (the ``-P`` and ``-e`` values of this run)
    only go into the printed recovery command.
    """
    unit_projects = sorted(
        {
            prj
            for unit in list_release_units()
            for prj in unit_obs_projects(unit["unit"], rootprj)
        }
    )
    states = frozen_projects(apiurl, unit_projects)
    frozen = {prj for prj, state in states.items() if state == "frozen"}
    if not frozen:
        logger.debug("propagate: no frozen project, nothing to trigger")
        return
    _print_action(f"propagate: seeds {_names(seeds)}")
    if not dry_run:
        print(
            "propagate: if this run stops early, re-run: "
            + recovery_command(apiurl, rootprj, seeds, env_overrides, profile)
        )

    paths = _path_map(apiurl, frozen, rootprj)
    # Instances build a slice of the tree: a seed project absent here has
    # nothing to query and is no fetch failure.
    seed_projects = {
        prj for prj, _ in seeds if prj in paths or _project_exists(apiurl, prj)
    }
    projects = set(paths) | seed_projects
    local_pkg_set = {(prj, path.name) for prj, path in targets}
    image_pkgs = _image_pkgs(targets, env_vars, projects)
    failed: set[str] = set()
    fwd = _fetch_combined_depinfo(
        apiurl,
        projects,
        local_pkg_set,
        image_pkgs or None,
        all_targets=True,
        failed=failed,
    )
    agg = aggregate_edges(targets, env_vars)
    for pkg, deps in agg.items():
        fwd.setdefault(pkg, set()).update(deps)

    extra: set[Pkg] = set()
    if failed:
        print(f"warning: propagate: no dependency data for {', '.join(sorted(failed))}")
        consumers_of: dict[str, set[str]] = {}
        for prj in frozen:
            reach: set[str] = set()
            stack = [prj]
            while stack:
                for dep in paths.get(stack.pop(), set()):
                    if dep not in reach:
                        reach.add(dep)
                        stack.append(dep)
            for dep in reach:
                consumers_of.setdefault(dep, set()).add(prj)
        for (prj, _), deps in agg.items():
            for dep_prj, _ in deps:
                consumers_of.setdefault(dep_prj, set()).add(prj)
        packages = {
            prj: sorted(_fetch_obs_package_names_or_fail(apiurl, prj)) for prj in frozen
        }
        extra = expand_failed(failed, frozen, consumers_of, packages)

    stages = plan_stages(
        seeds, fwd, frozen, _project_order(paths), set(agg), extra=extra
    )
    if not stages:
        _print_action(
            "propagate: nothing in a frozen project depends on the changed packages"
        )
        return

    run_stages(apiurl, stages, dry_run, seeds=frozenset(seeds))
