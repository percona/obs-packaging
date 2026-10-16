"""``release.yaml`` ``releases:`` entries.

Two entry forms coexist: the plain tag string (``- ppg/18.4-1``, all
historical entries) and the mapping form written by ``project release``
since the pre-release flow (``- {tag: ppg/18.7-1, source_commit: <sha>}``).
``source_commit`` is the full SHA of ``main`` whose staging tree the
release's binaries were built from.  The legacy single ``revision:`` field
is still read as a one-element list.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReleaseEntry:
    tag: str
    source_commit: "str | None" = None


def parse_release_entries(data: Any) -> "list[ReleaseEntry]":
    """Return the ``releases:`` list of a loaded release.yaml as entries.

    Raises SystemExit naming the offending item for anything that is neither
    a string nor a mapping with a string ``tag``.
    """
    if not isinstance(data, dict):
        return []
    raw = data.get("releases")
    if not raw and data.get("revision"):
        return [ReleaseEntry(str(data["revision"]))]
    if not isinstance(raw, list):
        return []
    entries: list[ReleaseEntry] = []
    for item in raw:
        if isinstance(item, str):
            entries.append(ReleaseEntry(item))
        elif isinstance(item, dict) and isinstance(item.get("tag"), str):
            sc = item.get("source_commit")
            entries.append(ReleaseEntry(item["tag"], str(sc) if sc else None))
        else:
            raise SystemExit(
                f"error: release.yaml: unrecognised releases entry {item!r} "
                "(expected a tag string or {tag: ..., source_commit: ...})"
            )
    return entries


def release_tags(data: Any) -> "list[str]":
    return [e.tag for e in parse_release_entries(data)]


def current_release(data: Any) -> "ReleaseEntry | None":
    """The last entry is the release in flight (or just shipped)."""
    entries = parse_release_entries(data)
    return entries[-1] if entries else None


def release_id_from_tag(tag: str) -> str:
    """The release id a tag names: ``ppg/18.7-1`` → ``18.7-1``,
    ``ppg/common-1`` → ``common-1``.

    Written as ``release_id: <id>`` into every release project description,
    so it must be well formed: a product prefix, a slash and a non-empty id.
    """
    product, sep, release_id = tag.partition("/")
    if not sep or not product or not release_id or "/" in release_id:
        raise SystemExit(
            f"error: cannot derive a release id from tag {tag!r} "
            "(expected <product>/<id>, e.g. ppg/18.7-1)"
        )
    return release_id


def dump_release_entry(entry: ReleaseEntry) -> "str | dict[str, str]":
    """YAML-ready value: a bare tag when there is nothing else to record."""
    if entry.source_commit is None:
        return entry.tag
    return {"tag": entry.tag, "source_commit": entry.source_commit}
