#!/usr/bin/env python3
"""Narrow a ``percona-obs qa show --json`` matrix for the manual QA workflow.

Reads the combo list on stdin and prints the kept combos on stdout.

  QA_NAME    keep only combos of the ``qa:`` entry with this ``name``
  QA_FILTER  space-separated ``AXIS=val[,val...]`` tokens; a combo is kept
             when, for every token, its ``params[AXIS]`` is one of the values
             (same shape as ``qa run --filter``).  Only ``matrix:`` axes
             qualify: a list parameter outside ``matrix:`` is joined into one
             value and cannot narrow anything.
  QA_PACKAGE  keep only combos of the package.yaml ``qa:`` block of this
              package (combos whose ``package`` equals it)

  QA_PACKAGES_PRESENT_ONLY  "true" (manual runs against a PR project): drop
              package lanes whose package is not in ``$OBS_PROJECT`` on
              ``$OBS_APIURL`` before narrowing, same rule as list_qa_matrix.py.

A selection that matches nothing is an error, and the message lists the entry
names / axis values that exist so a typo is caught before Jenkins is called.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Scripts in this directory share the presence helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from list_qa_matrix import drop_absent_packages, fetch_present_packages  # noqa: E402


def _parse_filter(text: str) -> dict[str, set[str]]:
    wanted: dict[str, set[str]] = {}
    for token in text.split():
        axis, sep, values = token.partition("=")
        vals = {v.strip() for v in values.split(",") if v.strip()}
        if not sep or not axis.strip() or not vals:
            raise SystemExit(
                f"error: malformed filter token {token!r}; expected AXIS=val[,val...]"
            )
        wanted.setdefault(axis.strip(), set()).update(vals)
    return wanted


def _matrix_axes(combo: dict[str, Any]) -> list[str]:
    """Axes of a combo, read back from its tool-generated ``--filter`` flags."""
    tokens = str(combo.get("axis_filters") or "").split()
    return [t.partition("=")[0] for t in tokens if t != "--filter" and "=" in t]


def filter_matrix(
    matrix: list[dict[str, Any]], name: str, filter_text: str, package: str = ""
) -> list[dict[str, Any]]:
    if not matrix:
        raise SystemExit("error: no QA combos found: the project has no qa: block")

    package = package.strip()
    if package:
        packages = sorted({str(c.get("package") or "") for c in matrix})
        matrix = [c for c in matrix if (c.get("package") or "") == package]
        if not matrix:
            shown = ", ".join(p or "(project)" for p in packages)
            raise SystemExit(
                f"error: no qa: block for package {package!r}; lanes: {shown}"
            )

    name = name.strip()
    if name:
        names = sorted({str(c.get("name") or "") for c in matrix})
        matrix = [c for c in matrix if (c.get("name") or "") == name]
        if not matrix:
            shown = ", ".join(n or "(unnamed)" for n in names)
            raise SystemExit(f"error: no qa: entry named {name!r}; entries: {shown}")

    for axis, values in _parse_filter(filter_text).items():
        axes = sorted({a for c in matrix for a in _matrix_axes(c)})
        if axis not in axes:
            params = sorted({a for c in matrix for a in (c.get("params") or {})})
            hint = (
                "a parameter but not a matrix axis (joined lists cannot narrow combos)"
                if axis in params
                else "not a parameter of this qa: block"
            )
            raise SystemExit(
                f"error: {axis!r} is {hint}; matrix axes: {', '.join(axes) or '(none)'}"
            )
        have = sorted({str(c["params"][axis]) for c in matrix if axis in c["params"]})
        matrix = [c for c in matrix if str(c["params"].get(axis)) in values]
        if not matrix:
            raise SystemExit(
                f"error: no combo has {axis} in {sorted(values)}; "
                f"values: {', '.join(have)}"
            )
    return matrix


def _configure_osc(apiurl: str) -> None:
    import osc.conf

    osc.conf.get_config(override_apiurl=apiurl)


def main() -> None:
    try:
        matrix = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: matrix on stdin is not valid JSON: {exc}")
    if not isinstance(matrix, list):
        raise SystemExit("error: matrix on stdin must be a JSON list")

    package = os.environ.get("QA_PACKAGE", "").strip()
    if os.environ.get("QA_PACKAGES_PRESENT_ONLY", "") == "true" and any(
        c.get("package") for c in matrix
    ):
        apiurl = os.environ["OBS_APIURL"]
        obs_project = os.environ["OBS_PROJECT"]
        _configure_osc(apiurl)
        matrix, dropped = drop_absent_packages(
            matrix, fetch_present_packages(apiurl, obs_project)
        )
        if dropped:
            print(
                f"package lane(s) skipped, not present in {obs_project}: "
                + ", ".join(dropped),
                file=sys.stderr,
            )
        if package and package in dropped:
            raise SystemExit(
                f"error: package {package!r} declares a qa: block but is not "
                f"present in {obs_project}; it was not promoted into this PR project"
            )

    kept = filter_matrix(
        matrix,
        os.environ.get("QA_NAME", ""),
        os.environ.get("QA_FILTER", ""),
        package=package,
    )
    for combo in kept:
        print(f"  {combo.get('status_context')}", file=sys.stderr)
    print(json.dumps(kept))


if __name__ == "__main__":
    main()
