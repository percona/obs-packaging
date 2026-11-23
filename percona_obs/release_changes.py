"""Classify a package change between two releases.

A ``versrel`` string is ``<upstream version>-<release>``.  The release holds
a source-commit counter followed by OBS build counters: RPM ``4.2.el9``,
deb ``7.5`` or ``6+7.3.bookworm`` (the text after ``+`` is the counter).
"""

from typing import Literal

ChangeKind = Literal["version", "packaging", "rebuild"]


def split_versrel(versrel: str) -> "tuple[str, str | None]":
    """Return ``(upstream version, source-commit counter or None)``."""
    version, sep, release = versrel.partition("-")
    if not sep:
        return version, None
    if "+" in release:
        release = release.rsplit("+", 1)[1]
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
