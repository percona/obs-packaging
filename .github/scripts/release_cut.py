#!/usr/bin/env python3
"""Pure helpers for obs-release-cut.yml, plus a CLI used by its steps.

CLI:  release_cut.py check <unit>...
        prints ::error::<unit>: <reason> per problem, exit 1
      release_cut.py summarize --out <file> <unit>...
        writes {unit: changelog section} JSON, prints "release: <id>, <id>..."
        (input order); exit 1 with ::error:: when a unit has no section

`check` runs under the runner's system python3 before the venv exists, so it
needs the stdlib only; yaml is imported lazily where release.yaml is read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent.parent


def load_units(repo_dir: Path) -> dict[str, dict]:
    path = repo_dir / "docs" / "versions" / "release-units.json"
    return {u["unit"]: u for u in json.loads(path.read_text(encoding="utf-8"))}


def check_units(units: list[str], known: dict[str, dict]) -> list[str]:
    if not units:
        return ["no release units given"]
    errors: list[str] = []
    seen: set[str] = set()
    for unit in units:
        if unit in seen:
            errors.append(f"{unit}: repeated")
            continue
        seen.add(unit)
        if unit.startswith("-"):
            errors.append(f"{unit}: not a release unit root")
            continue
        if unit not in known:
            errors.append(f"{unit}: not a release unit root")
    return errors


def release_id(release_dir: Path) -> str:
    """Id of the last ``releases:`` entry of release.yaml (text after the
    first ``/`` of its tag)."""
    import yaml

    data = yaml.safe_load((release_dir / "release.yaml").read_text(encoding="utf-8"))
    entries = (data or {}).get("releases") or []
    if not entries:
        raise ValueError(f"{release_dir / 'release.yaml'}: no releases entries")
    last = entries[-1]
    tag = last["tag"] if isinstance(last, dict) else last
    return str(tag).split("/", 1)[1]


def changelog_section(text: str, release_id: str) -> "str | None":
    """The ``## [<id>]`` section: its heading line up to, not including, the
    next ``## [`` line; ends with exactly one newline."""
    lines = text.splitlines()
    heading = re.compile(r"^## \[" + re.escape(release_id) + r"\]")
    start = next((i for i, ln in enumerate(lines) if heading.match(ln)), None)
    if start is None:
        return None
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## [")),
        len(lines),
    )
    return "\n".join(lines[start:end]).rstrip("\n") + "\n"


def summarize(repo_dir: Path, units: list[str]) -> tuple[dict[str, str], list[str]]:
    """({unit: section}, ids in input order); raises ValueError per problem."""
    known = load_units(repo_dir)
    sections: dict[str, str] = {}
    ids: list[str] = []
    for unit in units:
        release_dir = repo_dir / known[unit]["release_dir"]
        rid = release_id(release_dir)
        changelog = release_dir / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8") if changelog.is_file() else ""
        section = changelog_section(text, rid)
        if section is None:
            raise ValueError(f"{unit}: no CHANGELOG section for {rid}")
        sections[unit] = section
        ids.append(rid)
    return sections, ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check")
    p_check.add_argument("units", nargs="*")
    p_sum = sub.add_parser("summarize")
    p_sum.add_argument("--out", required=True)
    p_sum.add_argument("units", nargs="+")
    args = parser.parse_args(argv)

    if args.cmd == "check":
        errors = check_units(args.units, load_units(REPO_DIR))
        for e in errors:
            print(f"::error::{e}")
        return 1 if errors else 0

    try:
        sections, ids = summarize(REPO_DIR, args.units)
    except ValueError as e:
        # stderr: the workflow captures stdout as the commit subject, and the
        # runner parses workflow commands on stderr too.
        print(f"::error::{e}", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(sections, indent=2) + "\n", encoding="utf-8")
    print("release: " + ", ".join(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
