#!/usr/bin/env python3
"""Pure helpers for obs-release-pr.yml, plus a CLI used by its `resolve` job.

CLI:  release_pr.py classify <pr_number> [--strict] [--since <sha>]
Reads the PR's changed files and every open PR's files through `gh`, and
appends to $GITHUB_OUTPUT: kind=release|changelog|none, release_files=<json>,
release_projects=<json>.  With --since (the pre-push head of a synchronize
event), a push that changed only release CHANGELOG.md files is kind=changelog:
the changelog is not part of the OBS tree, so the pre-release already
populated for the previous head stands and populate is skipped.  A PR that changes no release.yaml is not a release
PR: kind=none with a notice and exit 0 (the workflow skips populate), or exit
1 with --strict (workflow_dispatch, where the operator named the PR).  Exits
1 (with ::error::) on a mixed PR (release.yaml plus other root/ files) or on
a one-in-flight conflict.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

_RELEASE_YAML_RE = re.compile(r"^root/[^/]+/releases/[^/]+/release\.yaml$")
_CHANGELOG_RE = re.compile(r"^root/[^/]+/releases/[^/]+/CHANGELOG\.md$")


def classify_files(paths: list[str]) -> tuple[str, list[str]]:
    root = [p for p in paths if p.startswith("root/")]
    if not root:
        return "none", []
    under_releases = [p for p in root if re.match(r"^root/[^/]+/releases/", p)]
    release_yamls = sorted({p for p in root if _RELEASE_YAML_RE.match(p)})
    if len(under_releases) != len(root):
        return "mixed", release_yamls
    return "release", release_yamls


def changelog_only(paths: list[str]) -> bool:
    """True when a push changed release CHANGELOG.md files and nothing else."""
    return bool(paths) and all(_CHANGELOG_RE.match(p) for p in paths)


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


def decide(kind: str, release_files: list[str], strict: bool) -> tuple[str, str | None]:
    """Return (kind_out, error) for a classified PR."""
    if not release_files:
        if strict:
            return "none", "this PR changes no release.yaml; nothing to populate"
        return "none", None
    if kind == "mixed":
        return (
            "mixed",
            "release PRs must change only files under root/*/releases/; this PR also changes other root/ files",
        )
    return "release", None


def prerelease_project(pr_rootprj: str, pr_number: int | str, project: str) -> str:
    return f"{pr_rootprj}:pr-{pr_number}:{project}"


def _gh_json(args: list[str]):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"error: gh {' '.join(args)}: {r.stderr.strip()}")
    return json.loads(r.stdout or "null")


def _push_files(repo: str, since: str, head: str) -> list[str] | None:
    """Files changed between *since* and *head*, or None when GitHub cannot say."""
    r = subprocess.run(
        ["gh", "api", f"repos/{repo}/compare/{since}...{head}", "--jq", "[.files[].filename]"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    return json.loads(r.stdout or "null")


def _cli_classify(pr_number: int, strict: bool, since: str | None = None) -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    files = [f["path"] for f in _gh_json(["pr", "view", str(pr_number), "-R", repo, "--json", "files", "--jq", ".files"])]
    kind, release_files = classify_files(files)
    kind, err = decide(kind, release_files, strict)
    if err:
        print(f"::error::{err}")
        sys.exit(1)
    if kind == "none":
        print("::notice::not a release PR (no release.yaml changed); nothing to populate")
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write("kind=none\nrelease_files=[]\nrelease_projects=[]\n")
        return
    open_prs = _gh_json(["pr", "list", "-R", repo, "--state", "open", "--limit", "200", "--json", "number,files"])
    open_prs = [{"number": p["number"], "files": [f["path"] for f in p.get("files") or []]} for p in open_prs]
    conflicts = conflicting_prs(pr_number, release_files, open_prs)
    if conflicts:
        for number, path in conflicts:
            print(f"::error::open PR #{number} already releases {path}; one in-flight release PR per major")
        sys.exit(1)
    if since and not strict:
        head = _gh_json(["pr", "view", str(pr_number), "-R", repo, "--json", "headRefOid", "--jq", ".headRefOid"])
        pushed = _push_files(repo, since, head)
        if pushed is not None and changelog_only(pushed):
            print("::notice::this push changed only release CHANGELOG.md files; the pre-release populated for the previous head stands (populate skipped)")
            kind = "changelog"
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        fh.write(f"kind={kind}\n")
        fh.write(f"release_files={json.dumps(release_files)}\n")
        fh.write(f"release_projects={json.dumps(release_projects(release_files))}\n")


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if a != "--strict"]
    since = None
    if "--since" in argv:
        i = argv.index("--since")
        since = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i : i + 2]
    if len(argv) == 2 and argv[0] == "classify":
        _cli_classify(int(argv[1]), "--strict" in sys.argv[1:], since or None)
    else:
        print(__doc__)
        sys.exit(2)
