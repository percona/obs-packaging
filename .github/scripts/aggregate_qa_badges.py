#!/usr/bin/env python3
"""Aggregate per-combo qa-report.json files into shields.io endpoint badges.

Walks ``<reports-dir>`` recursively (actions/download-artifact@v4 places each
artifact in its own subdirectory), groups every ``qa-report.json`` by the
distribution project derived from the report's ``project`` field (e.g.
``ppg:17:containers:ubi9`` → ``ppg:17``, and under the three-tier layout
``ppg:staging:18:containers:ubi9`` → ``ppg:staging:18``), and writes one
shields.io endpoint JSON per group to ``<out-dir>/qa-badge-<slug>.json``
(slug = distribution project with ``:`` replaced by ``-``).

A combo is considered passing iff its ``result`` is ``"SUCCESS"``; everything
else (``FAILURE``, ``ABORTED``, ``UNSTABLE``, ``null``) counts as failed.

Badge colour:
  brightgreen  no failures and at least one pass
  red          any failure
  lightgrey    no combos at all (e.g. job aborted before any result)

Usage:
    aggregate_qa_badges.py <reports-dir> <out-dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def top_level(project: str) -> str:
    """Return the distribution-project id a QA report belongs to.

    Two-segment ids (``ppg:18``) are already distribution projects.  Under
    the three-tier layout the second segment is a tier (staging/releases/
    devel) and the distribution project includes the version, e.g.
    ``ppg:staging:18:containers:ubi9`` → ``ppg:staging:18``.
    """
    parts = project.split(":")
    if len(parts) >= 3 and parts[1] in {"staging", "releases", "devel"}:
        return ":".join(parts[:3])
    return ":".join(parts[:2]) if len(parts) >= 2 else project


def slug(top: str) -> str:
    return top.replace(":", "-")


def write_badge(out_dir: Path, top: str, passed: int, failed: int) -> None:
    if failed > 0:
        color = "red"
    elif passed > 0:
        color = "brightgreen"
    else:
        color = "lightgrey"
    badge = {
        "schemaVersion": 1,
        "label": f"QA {top}",
        "message": f"✔ {passed}  ✗ {failed}",
        "color": color,
    }
    path = out_dir / f"qa-badge-{slug(top)}.json"
    with path.open("w") as fh:
        json.dump(badge, fh)
    print(f"wrote {path}: {badge['message']} ({color})")


def main() -> None:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <reports-dir> <out-dir>", file=sys.stderr)
        sys.exit(2)

    reports_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    # top-level project → [passed, failed]
    counts: dict[str, list[int]] = {}

    for path in sorted(reports_dir.rglob("qa-report.json")):
        try:
            report = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warning: skipping {path}: {exc}", file=sys.stderr)
            continue

        project = report.get("project", "")
        if not project:
            print(f"warning: {path} missing 'project' field", file=sys.stderr)
            continue

        top = top_level(project)
        bucket = counts.setdefault(top, [0, 0])
        for combo in report.get("combos", []):
            if combo.get("result") == "SUCCESS":
                bucket[0] += 1
            else:
                bucket[1] += 1

    if not counts:
        print("no qa-report.json files found", file=sys.stderr)
        return

    for top, (passed, failed) in sorted(counts.items()):
        write_badge(out_dir, top, passed, failed)


if __name__ == "__main__":
    main()
