"""Image references in ``qa:`` parameters.

A parameter whose value is a mapping with an ``image:`` key names a container
image by its OBS package instead of spelling the registry path::

    REPOSITORY:
      image: percona-pgbouncer          # OBS package name of the image
      repository: ubi9                  # OBS repository, last path segment
      project: ppg:staging:18:containers   # optional, defaults to the lane's project

The tool renders ``<registry>/<rootprj>/<project>/<repository>`` and decides
which root project the image lives under: the one ``qa show`` / ``qa run``
are run against when that project holds the package on OBS (it was promoted
and built there), else the fallback root project (profile key
``image-fallback-rootprj``; the production root in PR runs).  Without a
fallback the current root is always used and OBS is never queried.

Resolution is keyed on the value, never on the parameter name: pipelines
name their parameters differently (``REPOSITORY``, ``OLD_DOCKER_REPOSITORY``).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

IMAGE_REF_KEYS = frozenset({"image", "repository", "project"})


def is_image_ref(value: Any) -> bool:
    """True for a mapping carrying an ``image`` key (shape is checked separately)."""
    return isinstance(value, dict) and "image" in value


def validate_image_ref(value: dict[str, Any], where: str, param: str) -> None:
    """Reject a malformed image reference with a message naming *where*/*param*."""
    prefix = f"error: {where}: qa.parameters.{param}"
    unknown = sorted(set(value) - IMAGE_REF_KEYS)
    if unknown:
        raise SystemExit(
            f"{prefix}: unknown key(s) {', '.join(unknown)}; an image reference "
            "takes image, repository and optionally project"
        )
    for key in ("image", "repository"):
        v = value.get(key)
        if not isinstance(v, str) or not v:
            raise SystemExit(f"{prefix}: {key} must be a non-empty string")
    project = value.get("project")
    if project is not None and (not isinstance(project, str) or not project):
        raise SystemExit(f"{prefix}: project must be a non-empty string when set")


def _as_path(obs_name: str) -> str:
    """``isv:percona:PR:pr-1`` → ``isv/percona/pr/pr-1`` (OBS registry path form)."""
    return obs_name.replace(":", "/").lower()


def registry_path(registry: str, rootprj: str, project: str, repository: str) -> str:
    """The registry path Jenkins appends the image name to."""
    return f"{registry}/{_as_path(rootprj)}/{_as_path(project)}/{repository}"
