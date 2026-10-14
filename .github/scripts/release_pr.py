#!/usr/bin/env python3
"""Pure helpers for obs-release-pr.yml, plus a CLI used by its `resolve` job.

CLI:  release_pr.py classify <pr_number>
Reads the PR's changed files and every open PR's files through `gh`, and
appends to $GITHUB_OUTPUT: kind=release|mixed|none, release_files=<json>,
release_projects=<json>.  Exits 1 (with ::error::) on a mixed PR or on a
one-in-flight conflict.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

_RELEASE_YAML_RE = re.compile(r"^root/[^/]+/releases/[^/]+/release\.yaml$")


def classify_files(paths: list[str]) -> tuple[str, list[str]]:
    root = [p for p in paths if p.startswith("root/")]
    if not root:
        return "none", []
    under_releases = [p for p in root if re.match(r"^root/[^/]+/releases/", p)]
    release_yamls = sorted({p for p in root if _RELEASE_YAML_RE.match(p)})
    if len(under_releases) != len(root):
        return "mixed", release_yamls
    return "release", release_yamls


def release_projects(release_yaml_paths: list[str]) -> list[str]:
    out = set()
    for p in release_yaml_paths:
        rel = p.removeprefix("root/").removesuffix("/release.yaml")
        out.add(rel.replace("/", ":"))
    return sorted(out)


def conflicting_prs(
    this_pr: int, this_files: list[str], open_prs: list[dict]
) -> list[tuple[int, str]]:
    mine = {p for p in this_files if _RELEASE_YAML_RE.match(p)}
    hits: list[tuple[int, str]] = []
    for pr in open_prs:
        number = int(pr["number"])
        if number >= this_pr:
            continue
        for path in pr.get("files") or []:
            if path in mine:
                hits.append((number, path))
    return sorted(hits)


def prerelease_project(pr_rootprj: str, pr_number: int | str, project: str) -> str:
    return f"{pr_rootprj}:pr-{pr_number}:{project}"


def _gh_json(args: list[str]):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"error: gh {' '.join(args)}: {r.stderr.strip()}")
    return json.loads(r.stdout or "null")


def _cli_classify(pr_number: int) -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    files = [f["path"] for f in _gh_json(["pr", "view", str(pr_number), "-R", repo, "--json", "files", "--jq", ".files"])]
    kind, release_files = classify_files(files)
    if kind == "mixed":
        print("::error::release PRs must change only files under root/*/releases/; this PR also changes other root/ files")
        sys.exit(1)
    open_prs = _gh_json(["pr", "list", "-R", repo, "--state", "open", "--limit", "200", "--json", "number,files"])
    open_prs = [{"number": p["number"], "files": [f["path"] for f in p.get("files") or []]} for p in open_prs]
    conflicts = conflicting_prs(pr_number, release_files, open_prs)
    if conflicts:
        for number, path in conflicts:
            print(f"::error::open PR #{number} already releases {path}; one in-flight release PR per major")
        sys.exit(1)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        fh.write(f"kind={kind}\n")
        fh.write(f"release_files={json.dumps(release_files)}\n")
        fh.write(f"release_projects={json.dumps(release_projects(release_files))}\n")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "classify":
        _cli_classify(int(sys.argv[2]))
    else:
        print(__doc__)
        sys.exit(2)
