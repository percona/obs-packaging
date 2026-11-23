"""Classify a package change between two releases.

A ``versrel`` string is ``<upstream version>-<release>``.  The release holds
a source-commit counter followed by OBS build counters: RPM ``4.2.el9``,
deb ``7.5`` or ``6+7.3.bookworm`` (the text after ``+`` is the counter).
openSUSE Leap puts a distribution tag first: ``lp160.3.1`` has counter ``3``.
"""

import re
from dataclasses import dataclass
from typing import Callable, Literal

ChangeKind = Literal["version", "packaging", "rebuild"]

# openSUSE Leap / Backports release prefix (``lp160.``, ``bp160.``).
_SUSE_DIST_PREFIX_RE = re.compile(r"^(?:lp|bp)\d+\.")


def split_versrel(versrel: str) -> "tuple[str, str | None]":
    """Return ``(upstream version, source-commit counter or None)``."""
    version, sep, release = versrel.partition("-")
    if not sep:
        return version, None
    if "+" in release:
        release = release.rsplit("+", 1)[1]
    release = _SUSE_DIST_PREFIX_RE.sub("", release)
    return version, release.split(".")[0]


def classify_change(old: str, new: str) -> ChangeKind:
    """Version change, packaging change (counter differs) or plain rebuild."""
    old_version, old_counter = split_versrel(old)
    new_version, new_counter = split_versrel(new)
    if old_version != new_version:
        return "version"
    if old_counter != new_counter:
        return "packaging"
    return "rebuild"


@dataclass(frozen=True)
class CommitRef:
    sha: str
    subject: str


RunGit = Callable[["list[str]"], str]
PrLookup = Callable[[str], "tuple[int, str] | None"]


def packaging_commits(
    prev_commit: str, new_commit: str, paths: "list[str]", run_git: RunGit
) -> "list[CommitRef]":
    """Non-merge commits in ``prev_commit..new_commit`` touching ``paths``, oldest first."""
    out = run_git(
        [
            "log",
            "--no-merges",
            "--reverse",
            "--format=%H%x00%s%x1e",
            f"{prev_commit}..{new_commit}",
            "--",
            *paths,
        ]
    )
    commits = []
    for record in out.split("\x1e"):
        if not record.strip():
            continue
        sha, _, subject = record.strip().partition("\x00")
        commits.append(CommitRef(sha, subject))
    return commits


def commit_line(
    commit: CommitRef, repo_slug: "str | None", pr_lookup: "PrLookup | None"
) -> str:
    """One changelog sub-item, linked to the commit's pull request or the commit."""
    line = "  - " + commit.subject.replace("<", "\\<")
    if repo_slug is None or pr_lookup is None:
        return line
    pr = pr_lookup(commit.sha)
    if pr is not None:
        number, url = pr
        return f"{line} ([#{number}]({url}))"
    return (
        f"{line} ([{commit.sha[:7]}]"
        f"(https://github.com/{repo_slug}/commit/{commit.sha}))"
    )
