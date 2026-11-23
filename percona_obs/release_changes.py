"""Classify a package change between two releases.

A ``versrel`` string is ``<upstream version>-<release>``.  The release holds
a source-commit counter followed by OBS build counters: RPM ``4.2.el9``,
deb ``7.5`` or ``6+7.3.bookworm`` (the text after ``+`` is the counter).
openSUSE Leap puts a distribution tag first: ``lp160.3.1`` has counter ``3``.
"""

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Literal

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
    """Non-merge commits in ``prev_commit..new_commit`` touching ``paths``, oldest first.

    Commits whose subject starts with ``devel:`` are left out: they change the
    devel tier, which shares the staging packaging directories, and say nothing
    about the release.
    """
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
        if subject.startswith("devel:"):
            continue
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


# Container image changelog key: "<image> (<flavor>)", e.g. "img (ubi9)" or
# "img (extras/ubi9)".
_IMAGE_KEY_RE = re.compile(r"^(?P<image>.+) \((?P<flavor>[^()]+)\)$")


def split_image_key(key: str) -> "tuple[str, str]":
    """``"img (ubi9)"`` → ``("img", "ubi9")``; a key without a flavor → ``(key, "")``."""
    m = _IMAGE_KEY_RE.match(key)
    return (m["image"], m["flavor"]) if m else (key, "")


def _natural_key(text: str) -> "list[int | str]":
    """Sort key ordering embedded numbers numerically (``ubi8`` before ``ubi10``)."""
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text)]


def flavor_list(flavors: "Iterable[str]") -> str:
    """``"ubi8, ubi9, ubi10"``: distinct non-empty flavors in natural order."""
    return ", ".join(sorted({f for f in flavors if f}, key=_natural_key))


def group_image_keys(keys: "Iterable[str]") -> "dict[str, list[str]]":
    """Image keys grouped by image name (sorted), flavors in natural order."""
    grouped: "dict[str, list[str]]" = {}
    for key in sorted(keys, key=lambda k: split_image_key(k)[0]):
        grouped.setdefault(split_image_key(key)[0], []).append(key)
    for image_keys in grouped.values():
        image_keys.sort(key=lambda k: _natural_key(split_image_key(k)[1]))
    return grouped


def merge_flavor_items(
    per_flavor: "dict[str, list[tuple[str, str]]]",
) -> "list[str]":
    """Sub-item lines of one image entry, each tagged with its flavors.

    *per_flavor* maps a flavor to its ``(sort name, text)`` items.  Identical
    texts merge into one line ``"  - [ubi8, ubi9] <text>"``; lines are ordered
    by sort name, then by their first flavor, then by text.  An item of a
    flavorless image carries no tag.
    """
    flavors_of: "dict[tuple[str, str], list[str]]" = {}
    for flavor, items in per_flavor.items():
        for item in items:
            flavors_of.setdefault(item, []).append(flavor)

    def order(
        entry: "tuple[tuple[str, str], list[str]]",
    ) -> "tuple[str, list[int | str], str]":
        (name, text), flavors = entry
        first = min((_natural_key(f) for f in flavors), default=[])
        return name, first, text

    lines: "list[str]" = []
    for (_, text), flavors in sorted(flavors_of.items(), key=order):
        tag = flavor_list(flavors)
        lines.append(f"  - [{tag}] {text}" if tag else f"  - {text}")
    return lines
