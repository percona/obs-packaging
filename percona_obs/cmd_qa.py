"""Implements `percona-obs qa` subcommands.

Reads the optional ``qa:`` block of a project's ``project.yaml``, expands its
matrix into one Jenkins job per combination, optionally polls for completion,
and persists per-combo state under ``.percona-obs/qa/<run-id>.json``.
"""

from __future__ import annotations

import argparse
import concurrent.futures
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
    load_macros,
    load_yaml_with_env,
    parse_env_overrides,
    resolve_project_path,
)
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


def _load_qa_block(
    project: str, env_vars: dict[str, str]
) -> list[dict[str, Any]] | None:
    """Load and validate the ``qa:`` block of a project's project.yaml.

    Returns a list of validated pipeline entry dicts, or ``None`` if the
    project has no ``qa:`` block.  A single-dict ``qa:`` is normalised to a
    one-element list so callers can always iterate.
    """
    project_path = resolve_project_path(project)
    if not project_path.is_dir():
        raise SystemExit(f"error: project {project!r} not found at {project_path}")
    macros = load_macros(project_path)
    cfg = load_yaml_with_env(project_path / "project.yaml", env_vars, macros=macros)
    qa = cfg.get("qa")
    if qa is None:
        return None
    if isinstance(qa, dict):
        entries: list[Any] = [qa]
    elif isinstance(qa, list):
        entries = qa
    else:
        raise SystemExit(f"error: {project}: qa block must be a mapping or a list")
    for entry in entries:
        _validate_qa(entry, project)
    return entries


def _validate_qa(qa: Any, project: str) -> None:
    if not isinstance(qa, dict):
        raise SystemExit(f"error: {project}: qa entry must be a mapping")
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


# ---------------------------------------------------------------------------
# `qa show`
# ---------------------------------------------------------------------------


def cmd_qa_show(args: argparse.Namespace) -> None:
    env_vars = _qa_env_vars(args)
    entries = _load_qa_block(args.project, env_vars)
    json_mode: bool = bool(getattr(args, "json", False))

    if entries is None:
        if json_mode:
            print("[]")
        return

    if json_mode:
        out: list[dict[str, Any]] = []
        multi_pipeline = len(entries) > 1
        for entry in entries:
            pipeline = entry["pipeline"]
            combos = _expand_matrix(entry)
            matrix_axes = list(entry.get("matrix") or [])
            for label, params in combos:
                entry_label = label or "default"
                axis_filters = " ".join(
                    f"--filter {axis}={params[axis]}" for axis in matrix_axes
                )
                if multi_pipeline:
                    status_context = (
                        f"OBS QA / {args.project} / {pipeline} / {entry_label}"
                        if matrix_axes
                        else f"OBS QA / {args.project} / {pipeline}"
                    )
                else:
                    status_context = (
                        f"OBS QA / {args.project} / {entry_label}"
                        if matrix_axes
                        else f"OBS QA / {args.project}"
                    )
                out.append(
                    {
                        "project": args.project,
                        "pipeline": pipeline,
                        "label": entry_label,
                        "axis_filters": axis_filters,
                        "status_context": status_context,
                        "params": params,
                    }
                )
        print(json.dumps(out, indent=2))
        return

    for entry in entries:
        pipeline = entry["pipeline"]
        combos = _expand_matrix(entry)
        matrix_axes = list(entry.get("matrix") or [])
        print(_col(_BOLD, f"{args.project}  →  pipeline: {pipeline}"))
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
    entries = _load_qa_block(args.project, env_vars)
    if entries is None:
        raise SystemExit(f"error: {args.project} has no qa: block in its project.yaml")

    if args.pipeline:
        entries = [e for e in entries if e["pipeline"] == args.pipeline]
        if not entries:
            raise SystemExit(
                f"error: {args.project}: no qa entry with pipeline {args.pipeline!r}"
            )

    filters = _parse_filter(args.filter or [])
    overrides = _parse_param_overrides(args.param or [])

    # Pre-expand all entries so we can detect the no-match case before triggering.
    active: list[tuple[str, list[tuple[str, dict[str, str]]]]] = []
    for entry in entries:
        pipeline = entry["pipeline"]
        combos = _expand_matrix(entry)
        combos = _apply_filters(combos, filters)
        combos = _apply_param_overrides(combos, overrides)
        if combos:
            active.append((pipeline, combos))

    if not active:
        raise SystemExit("error: no matrix combinations match the given --filter")

    if args.dry_run:
        for pipeline, combos in active:
            print(_col(_BOLD, f"DRY RUN: would trigger pipeline {pipeline!r}"))
            print(f"  project: {args.project}")
            print(f"  combos:  {len(combos)}")
            for label, params in combos:
                print()
                print(_col(_CYAN, f"• {label or '(no matrix)'}"))
                _print_params(params)
            print()
        return

    cfg = load_jenkins_config(args.profile)

    any_failed = False
    for pipeline, combos in active:
        state = RunState(
            run_id=new_run_id(),
            project=args.project,
            pipeline=pipeline,
            created_at=_utcnow_iso(),
            combos=[],
        )
        print(
            _col(
                _BOLD,
                f"qa run {args.project}  pipeline: {pipeline}  (run-id: {state.run_id})",
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
            f"qa retry {state.project}  "
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
            f"{state.project}  {state.pipeline}  "
            f"{_col(_DIM, state.created_at)}  {summary}"
        )
