"""Implements `percona-obs qa` subcommands.

Reads the optional ``qa:`` block of a project's ``project.yaml`` and of each
direct package's ``package.yaml`` (one *lane* per block), expands every
matrix into one Jenkins job per combination, optionally polls for completion,
and persists per-combo state under ``.percona-obs/qa/<run-id>.json``.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import itertools
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .common import (
    _BOLD,
    _CYAN,
    _DIM,
    _GREEN,
    _RED,
    _YELLOW,
    _col,
    _print_pending,
    auto_rootprj_env,
    REPO_ROOT,
    apply_macro_substitution,
    find_packages,
    load_macros,
    load_project_yaml,
    load_yaml_with_env,
    parse_env_overrides,
    resolve_project_path,
)
from .cmd_project import _extract_version_from_service, _resolve_aggregate_source
from .jenkins import (
    JenkinsConfig,
    load_jenkins_config,
    trigger,
    wait_for_finish,
    wait_for_start,
)
from .qa_state import (
    Attempt,
    Combo,
    RunState,
    _utcnow_iso,
    is_run_terminal,
    list_runs,
    load_state,
    new_run_id,
    save_state,
    write_report_json,
)

# ---------------------------------------------------------------------------
# YAML loading + validation
# ---------------------------------------------------------------------------


def _qa_env_vars(args: argparse.Namespace) -> dict[str, str]:
    """Build the env dict used for ``${VAR}`` substitution in project.yaml.

    Always seeds OBS_ROOTPRJ and OBS_CONTAINER_REGISTRY_ROOTPRJ from ``args.rootprj``;
    profile env + ``-e`` overrides take precedence.
    """
    env_vars: dict[str, str] = dict(auto_rootprj_env(args.rootprj))
    if args.env_overrides:
        env_vars.update(parse_env_overrides(args.env_overrides))
    return env_vars


@dataclasses.dataclass
class Lane:
    """One ``qa:`` block: the project's own (``package is None``) or a package's."""

    package: str | None
    entries: list[dict[str, Any]]


def _lane_where(project: str, package: str | None) -> str:
    """Error-message prefix for a lane: ``<project>`` or ``<project>/<package>``."""
    return project if package is None else f"{project}/{package}"


def _normalise_qa_block(qa: Any, where: str) -> list[dict[str, Any]]:
    """Validate one loaded ``qa:`` value and return it as a list of entries.

    A single-dict ``qa:`` is normalised to a one-element list so callers can
    always iterate.  ``where`` prefixes error messages.
    """
    if isinstance(qa, dict):
        entries: list[Any] = [qa]
    elif isinstance(qa, list):
        entries = qa
    else:
        raise SystemExit(f"error: {where}: qa block must be a mapping or a list")
    # Two entries that disambiguate to the same segment would render the same
    # status_context, i.e. the same check-run name: CI would drop one lane and
    # `qa run` would trigger both under one check.  Reject it here instead.
    seen_segments: set[str] = set()
    for entry in entries:
        _validate_qa(entry, where)
        segment = _entry_segment(entry)
        if segment in seen_segments:
            hint = (
                "give each one a distinct 'name'"
                if not entry.get("name")
                else "rename one of them"
            )
            raise SystemExit(
                f"error: {where}: two qa entries resolve to the same check segment "
                f"{segment!r}; {hint}"
            )
        seen_segments.add(segment)
    return entries


def _load_qa_lanes(project: str, env_vars: dict[str, str]) -> list[Lane]:
    """Load every ``qa:`` block of a project: its own, then its direct packages'.

    The project's ``project.yaml`` block (when present) comes first as
    ``Lane(None, ...)``; then one ``Lane(<dirname>, ...)`` per direct package
    whose ``package.yaml`` declares ``qa:``, in ``find_packages`` order.
    Packages are enumerated on disk only (symlinks into ``_shared/`` are
    followed, and macros resolve from the link's location); subprojects are
    not descended into because CI calls this once per OBS subproject.
    Returns ``[]`` when the project declares no QA at all.
    """
    project_path = resolve_project_path(project)
    if not project_path.is_dir():
        raise SystemExit(f"error: project {project!r} not found at {project_path}")
    lanes: list[Lane] = []
    cfg = load_project_yaml(project_path / "project.yaml", env_vars)
    if cfg.get("qa") is not None:
        lanes.append(Lane(None, _normalise_qa_block(cfg["qa"], project)))
    for _obs_project, package_path in find_packages(
        project_path, project, recursive=False
    ):
        pkg_yaml = package_path / "package.yaml"
        if not pkg_yaml.is_file():
            continue
        pkg_cfg = load_yaml_with_env(
            pkg_yaml, env_vars, macros=load_macros(package_path)
        )
        if pkg_cfg.get("qa") is None:
            continue
        package = package_path.name
        lanes.append(
            Lane(
                package,
                _normalise_qa_block(pkg_cfg["qa"], _lane_where(project, package)),
            )
        )
    return lanes


def _entry_segment(entry: "dict[str, Any]") -> str:
    """The part of ``status_context`` that tells two entries of one block apart."""
    name = entry.get("name")
    return name if isinstance(name, str) and name else str(entry["pipeline"])


def _validate_qa(qa: Any, project: str) -> None:
    if not isinstance(qa, dict):
        raise SystemExit(f"error: {project}: qa entry must be a mapping")
    if "name" in qa:
        name = qa.get("name")
        if not isinstance(name, str) or not name:
            raise SystemExit(f"error: {project}: qa.name must be a non-empty string")
    pipeline = qa.get("pipeline")
    if not isinstance(pipeline, str) or not pipeline:
        raise SystemExit(f"error: {project}: qa.pipeline must be a non-empty string")
    parameters = qa.get("parameters")
    if not isinstance(parameters, dict) or not parameters:
        raise SystemExit(f"error: {project}: qa.parameters must be a non-empty mapping")
    matrix = qa.get("matrix") or []
    if not isinstance(matrix, list) or not all(isinstance(a, str) for a in matrix):
        raise SystemExit(f"error: {project}: qa.matrix must be a list of strings")
    for axis in matrix:
        if axis not in parameters:
            raise SystemExit(
                f"error: {project}: qa.matrix axis {axis!r} not present in qa.parameters"
            )
        if not isinstance(parameters[axis], list) or not parameters[axis]:
            raise SystemExit(
                f"error: {project}: qa.parameters.{axis} must be a non-empty list "
                "(it is referenced by qa.matrix)"
            )


# ---------------------------------------------------------------------------
# Matrix expansion
# ---------------------------------------------------------------------------


def _format_scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _format_value(v: Any) -> str:
    """Format a parameter value for the Jenkins POST body.

    Lists are joined with ``\\n`` so Jenkins multi-line text params receive
    each entry on its own line. Scalars are stringified (booleans → ``true``/
    ``false`` to match Jenkins boolean param convention).
    """
    if isinstance(v, list):
        return "\n".join(_format_scalar(x) for x in v)
    return _format_scalar(v)


def _expand_matrix(qa: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
    """Cartesian product over the ``matrix`` axes.

    Returns ``[(label, params)]``. ``label`` is empty when the project has no
    matrix; otherwise it is ``"AXIS=value,AXIS2=value2"``.
    """
    parameters: dict[str, Any] = qa["parameters"]
    matrix_axes: list[str] = list(qa.get("matrix") or [])

    fixed: dict[str, str] = {
        k: _format_value(v) for k, v in parameters.items() if k not in matrix_axes
    }

    if not matrix_axes:
        return [("", fixed)]

    axis_values: list[list[Any]] = [list(parameters[a]) for a in matrix_axes]
    out: list[tuple[str, dict[str, str]]] = []
    for combo_values in itertools.product(*axis_values):
        params = dict(fixed)
        label_parts: list[str] = []
        for axis, value in zip(matrix_axes, combo_values):
            params[axis] = _format_scalar(value)
            label_parts.append(f"{axis}={_format_scalar(value)}")
        out.append((",".join(label_parts), params))
    return out


# ---------------------------------------------------------------------------
# Filter + override
# ---------------------------------------------------------------------------


def _parse_filter(entries: list[str]) -> dict[str, set[str]]:
    """Parse repeated ``--filter AXIS=val[,val...]`` flags.

    Multiple flags AND together; values within one flag OR together.
    """
    out: dict[str, set[str]] = {}
    for entry in entries:
        axis, sep, vals = entry.partition("=")
        if not sep:
            raise SystemExit(f"error: --filter {entry!r}: expected AXIS=VAL[,VAL...]")
        out.setdefault(axis.strip(), set()).update(
            v.strip() for v in vals.split(",") if v.strip()
        )
    return out


def _parse_param_overrides(entries: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in entries:
        name, sep, value = entry.partition("=")
        if not sep:
            raise SystemExit(f"error: --param {entry!r}: expected NAME=VALUE")
        out[name.strip()] = value
    return out


def _apply_filters(
    combos: list[tuple[str, dict[str, str]]],
    filters: dict[str, set[str]],
) -> list[tuple[str, dict[str, str]]]:
    if not filters:
        return combos
    return [
        (label, params)
        for label, params in combos
        if all(params.get(axis) in vals for axis, vals in filters.items())
    ]


def _apply_param_overrides(
    combos: list[tuple[str, dict[str, str]]],
    overrides: dict[str, str],
) -> list[tuple[str, dict[str, str]]]:
    if not overrides:
        return combos
    return [(label, {**params, **overrides}) for label, params in combos]


# ---------------------------------------------------------------------------
# Pretty-printers
# ---------------------------------------------------------------------------


def _run_target(state: RunState) -> str:
    """``<project>`` or ``<project>/<package>`` for headings and `qa list` rows."""
    return f"{state.project}/{state.package}" if state.package else state.project


def _print_params(params: dict[str, str], indent: str = "    ") -> None:
    for k in sorted(params):
        v = params[k]
        if "\n" in v:
            print(f"{indent}{k}:")
            for line in v.split("\n"):
                print(f"{indent}  {line}")
        else:
            print(f"{indent}{k}: {v}")


def _summarize(state: RunState) -> bool:
    """Print a per-combo summary; return True if any combo failed."""
    print()
    success = 0
    failure = 0
    pending = 0
    for combo in state.combos:
        last = combo.attempts[-1] if combo.attempts else None
        result = last.result if last else None
        if result == "SUCCESS":
            success += 1
            sym = _col(_GREEN, "✔")
        elif result is None:
            pending += 1
            sym = _col(_YELLOW, "◌")
        else:
            failure += 1
            sym = _col(_RED, "✗")
        label = combo.label or "(no matrix)"
        url = last.build_url if last else None
        url_str = f"  {_col(_DIM, url)}" if url else ""
        result_str = result or ("error" if last and last.error else "pending")
        print(f"  {sym} {label:<40} {result_str}{url_str}")
        if last and last.error:
            print(f"      {_col(_DIM, last.error)}")
    summary = f"{success} succeeded, {failure} failed, {pending} pending"
    print()
    label = f"qa run {state.run_id}: {summary}"
    if failure:
        print(_col(_RED + _BOLD, label))
    else:
        print(_col(_GREEN + _BOLD, label))
    return failure > 0


def _status_context(
    project: str, package: str | None, segment: str | None, label: str
) -> str:
    """Check-run name of one combo.

    ``OBS QA / <project>[ / <package>][ / <segment>][ / <combo>]`` — the
    package only for package lanes, the segment only for multi-entry blocks,
    the combo label only when the entry has a ``matrix:``.  Project-lane
    contexts are byte-for-byte what they were before package lanes existed.
    """
    parts = ["OBS QA", project]
    if package:
        parts.append(package)
    if segment:
        parts.append(segment)
    if label:
        parts.append(label)
    return " / ".join(parts)


# ---------------------------------------------------------------------------
# `qa show`
# ---------------------------------------------------------------------------


EXPECTED_VERSIONS_PARAM = "EXPECTED_VERSIONS"


def _package_versions(project: str) -> dict[str, str]:
    """Version of each package in *project*, keyed by OBS package name.

    The version is the one OBS builds: the ``version`` of the package's
    obs/_service (for an aggregate, of its source package), with ``%!{VAR}``
    macros resolved from that package's macros.yaml chain in the current
    checkout, so a PR run gets the PR's values.  Only the project's own
    packages are listed (not subprojects); packages whose _service declares no
    version, or whose version cannot be resolved, are left out.
    """
    project_path = resolve_project_path(project)
    versions: dict[str, str] = {}
    for _, pkg_path in find_packages(project_path, project, recursive=False):
        service = pkg_path / "obs" / "_service"
        aggregate = pkg_path / "obs" / "_aggregate"
        raw, macros_dir = None, pkg_path
        if service.is_file():
            raw = _extract_version_from_service(service)
        elif aggregate.is_file():
            source = _resolve_aggregate_source(aggregate)
            if source is not None:
                local_project, src_pkg = source
                macros_dir = REPO_ROOT.joinpath(*local_project.split(":")) / src_pkg
                raw = _extract_version_from_service(macros_dir / "obs" / "_service")
        if not raw:
            continue
        version = apply_macro_substitution(raw, load_macros(macros_dir), strict=False)
        if "%!{" not in version:
            versions[pkg_path.name] = version
    return versions


def _expected_versions(versions: dict[str, str], package: str | None = None) -> str:
    """``package=version`` lines, sorted by package name, for EXPECTED_VERSIONS.

    With *package*, only that package's line (an entry declared for a single
    package tests only that package).
    """
    if package is not None:
        versions = {package: versions[package]} if package in versions else {}
    return "\n".join(f"{name}={version}" for name, version in sorted(versions.items()))


def _with_expected_versions(
    entries: list[dict[str, Any]] | None,
    project: str,
    package: str | None = None,
    versions: dict[str, str] | None = None,
) -> list[dict[str, Any]] | None:
    """Add ``EXPECTED_VERSIONS`` to the parameters of every entry, unless the
    entry sets it itself.

    The value lists the versions OBS builds for the packages under test, as
    ``package=version`` lines keyed by OBS package name (so test scripts do
    not depend on macro names): every package of *project* for a project
    entry, only its own package for an entry marked with ``_package``
    or when *package* names the lane's package (package-level qa: blocks).
    *versions* lets callers that process several lanes compute
    :func:`_package_versions` once.  Added here rather than in each qa: entry so
    the versions are not repeated in every job declaration; jobs that do not
    declare the parameter ignore it.
    """
    if not entries:
        return entries
    if versions is None:
        versions = _package_versions(project)
    if not versions:
        return entries
    out = []
    for entry in entries:
        value = _expected_versions(
            versions, package if package is not None else entry.get("_package")
        )
        params = dict(entry.get("parameters") or {})
        if value:
            params.setdefault(EXPECTED_VERSIONS_PARAM, value)
        out.append({**entry, "parameters": params})
    return out


def _lanes_with_expected_versions(lanes: list[Lane], project: str) -> list[Lane]:
    """Apply :func:`_with_expected_versions` to every lane.

    The project lane lists every package of *project*; a package lane lists
    only its own package.
    """
    if not lanes:
        return lanes
    versions = _package_versions(project)
    return [
        Lane(
            lane.package,
            _with_expected_versions(lane.entries, project, lane.package, versions)
            or lane.entries,
        )
        for lane in lanes
    ]


def cmd_qa_show(args: argparse.Namespace) -> None:
    env_vars = _qa_env_vars(args)
    lanes = _lanes_with_expected_versions(
        _load_qa_lanes(args.project, env_vars), args.project
    )
    json_mode: bool = bool(getattr(args, "json", False))

    if not lanes:
        if json_mode:
            print("[]")
        return

    if json_mode:
        out: list[dict[str, Any]] = []
        for lane in lanes:
            package = lane.package or ""
            package_filter = f"--package {package}" if package else ""
            multi_entry = len(lane.entries) > 1
            for entry in lane.entries:
                pipeline = entry["pipeline"]
                name = entry.get("name")
                combos = _expand_matrix(entry)
                matrix_axes = list(entry.get("matrix") or [])
                # Disambiguating segment for a multi-entry block: the entry
                # `name` when it has one (two entries may share a pipeline),
                # else the pipeline, which keeps unnamed entries' contexts.
                segment = (name or pipeline) if multi_entry else None
                name_filter = f"--name {name}" if name else ""
                for label, params in combos:
                    axis_filters = " ".join(
                        f"--filter {axis}={params[axis]}" for axis in matrix_axes
                    )
                    out.append(
                        {
                            "project": args.project,
                            "package": package,
                            "pipeline": pipeline,
                            "name": name or "",
                            "label": label or "default",
                            "axis_filters": axis_filters,
                            "name_filter": name_filter,
                            "package_filter": package_filter,
                            "status_context": _status_context(
                                args.project, lane.package, segment, label
                            ),
                            "params": params,
                        }
                    )
        print(json.dumps(out))
        return

    for lane in lanes:
        where = _lane_where(args.project, lane.package).replace("/", " / ")
        for entry in lane.entries:
            pipeline = entry["pipeline"]
            name = entry.get("name")
            combos = _expand_matrix(entry)
            matrix_axes = list(entry.get("matrix") or [])
            heading = f"{where}  →  pipeline: {pipeline}"
            if name:
                heading += f"  (name: {name})"
            print(_col(_BOLD, heading))
            print(f"{_col(_DIM, 'matrix:')} {', '.join(matrix_axes) or '(none)'}")
            print(f"{_col(_DIM, 'combos:')} {len(combos)}")
            for label, params in combos:
                print()
                print(_col(_CYAN, f"• {label or '(no matrix)'}"))
                _print_params(params)
            print()


# ---------------------------------------------------------------------------
# `qa run`
# ---------------------------------------------------------------------------


def _trigger_combos(
    cfg: JenkinsConfig,
    pipeline: str,
    todo: list[tuple[str, dict[str, str]]],
    state: RunState,
    record_new_combo: bool,
) -> dict[str, str]:
    """Trigger Jenkins for each (label, params); record an Attempt per combo.

    When ``record_new_combo`` is True, append a fresh Combo to ``state.combos``;
    otherwise locate the existing Combo by label and append a new attempt.
    """
    queue_urls: dict[str, str] = {}
    by_label = {c.label: c for c in state.combos}
    for label, params in todo:
        display = label or "(no matrix)"
        _print_pending(f"trigger  {display}")
        try:
            queue_url = trigger(cfg, pipeline, params)
        except Exception as exc:
            print(_col(_RED, f"  ✗ trigger failed: {display}: {exc}"))
            attempt = Attempt(triggered_at=_utcnow_iso(), queue_url="", error=str(exc))
            if record_new_combo:
                state.combos.append(
                    Combo(label=label, params=params, attempts=[attempt])
                )
            else:
                by_label[label].attempts.append(attempt)
            continue
        attempt = Attempt(triggered_at=_utcnow_iso(), queue_url=queue_url)
        if record_new_combo:
            state.combos.append(Combo(label=label, params=params, attempts=[attempt]))
        else:
            by_label[label].attempts.append(attempt)
        queue_urls[label] = queue_url
        print(_col(_CYAN, f"  > {display}  →  {queue_url}"))
    return queue_urls


def _wait_and_record(
    cfg: JenkinsConfig,
    state: RunState,
    queue_urls: dict[str, str],
) -> None:
    """Poll triggered builds in parallel, persisting state between phases.

    Phase 1 — wait for each queued build to start; as soon as a build URL is
    known, record it on the combo's latest attempt and save the state file
    (so external watchers can see ``build_url`` without waiting for the
    terminal result).

    Phase 2 — wait for each build to reach a terminal state; record the
    result on the combo and save again. Each combo is saved as soon as its
    own poll completes, not in a single batch at the end.
    """
    if not queue_urls:
        return

    print()
    print(_col(_DIM, f"polling {len(queue_urls)} build(s)..."))
    timeout = int(os.environ.get("QA_POLL_TIMEOUT", str(6 * 60 * 60)))
    deadline = time.monotonic() + timeout
    by_label = {c.label: c for c in state.combos}

    # Phase 1: wait for queue items to become active builds.
    build_urls: dict[str, str] = {}
    max_workers = max(1, min(len(queue_urls), 8))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(wait_for_start, cfg, qurl, timeout): label
            for label, qurl in queue_urls.items()
        }
        for fut in concurrent.futures.as_completed(futures):
            label = futures[fut]
            combo = by_label.get(label)
            display = label or "(no matrix)"
            try:
                build_url = fut.result()
            except Exception as exc:
                if combo and combo.attempts:
                    combo.attempts[-1].error = str(exc)
                save_state(state)
                print(_col(_RED, f"  ✗ {display}: {exc}"))
                continue
            if combo and combo.attempts:
                combo.attempts[-1].build_url = build_url
            save_state(state)
            build_urls[label] = build_url
            print(_col(_CYAN, f"  > {display} started: {build_url}"))

    # Phase 2: wait for each build to reach a terminal state.
    if not build_urls:
        return
    remaining = max(1, int(deadline - time.monotonic()))
    max_workers = max(1, min(len(build_urls), 8))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(wait_for_finish, cfg, burl, remaining): label
            for label, burl in build_urls.items()
        }
        for fut in concurrent.futures.as_completed(futures):
            label = futures[fut]
            combo = by_label.get(label)
            display = label or "(no matrix)"
            if combo is None or not combo.attempts:
                continue
            try:
                result = fut.result()
            except Exception as exc:
                combo.attempts[-1].error = str(exc)
                save_state(state)
                print(_col(_RED, f"  ✗ {display}: {exc}"))
                continue
            combo.attempts[-1].result = result
            save_state(state)
            sym = _col(_GREEN, "✔") if result == "SUCCESS" else _col(_RED, "✗")
            print(f"  {sym} {display}: {result}")


def cmd_qa_run(args: argparse.Namespace) -> None:
    env_vars = _qa_env_vars(args)
    lanes = _lanes_with_expected_versions(
        _load_qa_lanes(args.project, env_vars), args.project
    )
    if not lanes:
        raise SystemExit(
            f"error: {args.project} has no qa: block in its project.yaml "
            "or in any package.yaml"
        )

    package = getattr(args, "package", None)
    if package:
        lanes = [lane for lane in lanes if lane.package == package]
        if not lanes:
            have = sorted(
                lane.package
                for lane in _load_qa_lanes(args.project, env_vars)
                if lane.package
            )
            raise SystemExit(
                f"error: {args.project}: no package with a qa: block named "
                f"{package!r}; packages: {', '.join(have) or '(none)'}"
            )

    name = getattr(args, "name", None)
    if name:
        lanes = [
            Lane(lane.package, [e for e in lane.entries if e.get("name") == name])
            for lane in lanes
        ]
        lanes = [lane for lane in lanes if lane.entries]
        if not lanes:
            raise SystemExit(f"error: {args.project}: no qa entry with name {name!r}")

    if args.pipeline:
        lanes = [
            Lane(
                lane.package,
                [e for e in lane.entries if e["pipeline"] == args.pipeline],
            )
            for lane in lanes
        ]
        lanes = [lane for lane in lanes if lane.entries]
        if not lanes:
            suffix = f" (after --name {name})" if name else ""
            raise SystemExit(
                f"error: {args.project}: no qa entry with pipeline "
                f"{args.pipeline!r}{suffix}"
            )

    filters = _parse_filter(args.filter or [])
    overrides = _parse_param_overrides(args.param or [])

    # Pre-expand all entries so we can detect the no-match case before triggering.
    active: list[tuple[str, str, list[tuple[str, dict[str, str]]]]] = []
    for lane in lanes:
        for entry in lane.entries:
            pipeline = entry["pipeline"]
            combos = _expand_matrix(entry)
            combos = _apply_filters(combos, filters)
            combos = _apply_param_overrides(combos, overrides)
            if combos:
                active.append((lane.package or "", pipeline, combos))

    if not active:
        raise SystemExit("error: no matrix combinations match the given --filter")

    if args.dry_run:
        for lane_package, pipeline, combos in active:
            print(_col(_BOLD, f"DRY RUN: would trigger pipeline {pipeline!r}"))
            print(f"  project: {args.project}")
            if lane_package:
                print(f"  package: {lane_package}")
            print(f"  combos:  {len(combos)}")
            for label, params in combos:
                print()
                print(_col(_CYAN, f"• {label or '(no matrix)'}"))
                _print_params(params)
            print()
        return

    cfg = load_jenkins_config(args.profile)

    any_failed = False
    for lane_package, pipeline, combos in active:
        state = RunState(
            run_id=new_run_id(),
            project=args.project,
            pipeline=pipeline,
            created_at=_utcnow_iso(),
            combos=[],
            package=lane_package,
        )
        target = _run_target(state)
        print(
            _col(
                _BOLD,
                f"qa run {target}  pipeline: {pipeline}  (run-id: {state.run_id})",
            )
        )
        queue_urls = _trigger_combos(
            cfg, pipeline, combos, state, record_new_combo=True
        )
        save_state(state)

        if args.wait and queue_urls:
            _wait_and_record(cfg, state, queue_urls)

        if args.report_json:
            write_report_json(state, Path(args.report_json))

        if args.wait and _summarize(state):
            any_failed = True

    if args.wait and any_failed:
        sys.exit(1)


# ---------------------------------------------------------------------------
# `qa status`
# ---------------------------------------------------------------------------


def cmd_qa_status(args: argparse.Namespace) -> None:
    state = load_state(args.run_id)
    cfg: JenkinsConfig | None = None
    timeout = int(os.environ.get("QA_POLL_TIMEOUT", "60"))
    for combo in state.combos:
        if not combo.attempts:
            continue
        last = combo.attempts[-1]
        if last.result is not None:
            continue
        if not last.queue_url and not last.build_url:
            continue
        if cfg is None:
            cfg = load_jenkins_config(args.profile)
        # Phase 1: queue → build. Save as soon as we have a build_url.
        if not last.build_url:
            try:
                last.build_url = wait_for_start(cfg, last.queue_url, timeout=timeout)
                save_state(state)
            except Exception as exc:
                last.error = str(exc)
                save_state(state)
                continue
        # Phase 2: build → terminal. Save once result is known.
        try:
            last.result = wait_for_finish(cfg, last.build_url, timeout=timeout)
        except Exception as exc:
            last.error = str(exc)
        save_state(state)
    if _summarize(state):
        sys.exit(1)


# ---------------------------------------------------------------------------
# `qa retry`
# ---------------------------------------------------------------------------


def cmd_qa_retry(args: argparse.Namespace) -> None:
    state = load_state(args.run_id)
    cfg = load_jenkins_config(args.profile)

    todo: list[tuple[str, dict[str, str]]] = []
    for combo in state.combos:
        if not combo.attempts:
            continue
        result = combo.attempts[-1].result
        if result == "SUCCESS":
            continue
        if result == "ABORTED" and not args.include_aborted:
            continue
        todo.append((combo.label, combo.params))

    if not todo:
        print(_col(_DIM, "no failed combos to retry"))
        if _summarize(state):
            sys.exit(1)
        return

    print(
        _col(
            _BOLD,
            f"qa retry {_run_target(state)}  "
            f"(run-id: {state.run_id}, retrying {len(todo)} combo(s))",
        )
    )
    queue_urls = _trigger_combos(
        cfg, state.pipeline, todo, state, record_new_combo=False
    )
    save_state(state)

    if args.wait and queue_urls:
        _wait_and_record(cfg, state, queue_urls)

    if args.report_json:
        write_report_json(state, Path(args.report_json))

    failed = _summarize(state) if args.wait else False
    if args.wait and failed:
        sys.exit(1)


# ---------------------------------------------------------------------------
# `qa list`
# ---------------------------------------------------------------------------


def cmd_qa_list(args: argparse.Namespace) -> None:
    runs = list_runs()
    if args.running:
        runs = [r for r in runs if not is_run_terminal(r)]
    if not runs:
        msg = "no running qa runs" if args.running else "no qa runs recorded"
        print(_col(_DIM, msg))
        return
    for state in runs:
        success = sum(
            1 for c in state.combos if c.attempts and c.attempts[-1].result == "SUCCESS"
        )
        failure = sum(
            1
            for c in state.combos
            if c.attempts
            and c.attempts[-1].result is not None
            and c.attempts[-1].result != "SUCCESS"
        )
        pending = sum(
            1 for c in state.combos if not c.attempts or c.attempts[-1].result is None
        )
        summary = f"{success}✔  {failure}✗  {pending}◌"
        print(
            f"  {_col(_BOLD, state.run_id)}  "
            f"{_run_target(state)}  {state.pipeline}  "
            f"{_col(_DIM, state.created_at)}  {summary}"
        )
