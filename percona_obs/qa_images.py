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

A PR project may build only some repositories (repository labels narrow its
slice).  An entry whose own image (one without ``project:``, or naming the
lane's project) lives in a repository the lane's OBS project does not have is
outside the slice and is dropped: the PR built nothing there to test.  An
image of another project whose repository is missing falls back, like an
absent package.  An empty repository list (project missing, or the query
failed) narrows nothing.

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
    """The lower-cased registry path Jenkins appends the image name to.

    The registry host is kept as given; rootprj, project and repository are lower-cased.
    """
    return f"{registry}/{_as_path(rootprj)}/{_as_path(project)}/{repository.lower()}"


@dataclasses.dataclass(frozen=True)
class ImageDecision:
    """Which root project one image reference was rendered with, and why."""

    param: str
    image: str
    project: str  # colon notation, without rootprj
    obs_project: str  # the project that was (or would have been) listed
    rootprj: str  # the root project used in ``value``
    reason: str  # "no-fallback" | "present" | "fallback" | "fallback-repo"
    value: str  # rendered registry path


class ImageResolver:
    """Renders image references, choosing the rootprj per image.

    *list_packages* returns the package names of an OBS project (empty on
    404) and *list_repositories* its repository names (empty when unknown);
    each is called at most once per project and only when *fallback_rootprj*
    is set.
    """

    def __init__(
        self,
        registry: str,
        rootprj: str,
        fallback_rootprj: str | None,
        list_packages: Callable[[str], set[str]],
        list_repositories: Callable[[str], set[str]] | None = None,
    ) -> None:
        self.registry = registry
        self.rootprj = rootprj
        self.fallback_rootprj = fallback_rootprj or None
        self._list_packages = list_packages
        self._list_repositories = list_repositories
        self._present: dict[str, set[str]] = {}
        self._repos: dict[str, set[str]] = {}

    def _packages(self, obs_project: str) -> set[str]:
        if obs_project not in self._present:
            self._present[obs_project] = set(self._list_packages(obs_project))
        return self._present[obs_project]

    def _repo_missing(self, obs_project: str, repository: str) -> bool:
        """True when *obs_project* lists repositories and *repository* is not
        one of them (an empty list is unknown and narrows nothing)."""
        if self.fallback_rootprj is None or self._list_repositories is None:
            return False
        if obs_project not in self._repos:
            self._repos[obs_project] = set(self._list_repositories(obs_project))
        repos = self._repos[obs_project]
        return bool(repos) and repository not in repos

    def outside_slice(self, entry: dict[str, Any], lane_project: str) -> str | None:
        """The repository of the first own image reference of *entry* that the
        lane's OBS project does not build, else None."""
        obs_project = f"{self.rootprj}:{lane_project}"
        for value in (entry.get("parameters") or {}).values():
            if not is_image_ref(value):
                continue
            if (value.get("project") or lane_project) != lane_project:
                continue
            if self._repo_missing(obs_project, value["repository"]):
                return value["repository"]
        return None

    def decide(
        self, param: str, ref: dict[str, Any], lane_project: str
    ) -> ImageDecision:
        project = ref.get("project") or lane_project
        image: str = ref["image"]
        obs_project = f"{self.rootprj}:{project}"
        if self.fallback_rootprj is None:
            rootprj, reason = self.rootprj, "no-fallback"
        elif image not in self._packages(obs_project):
            rootprj, reason = self.fallback_rootprj, "fallback"
        elif self._repo_missing(obs_project, ref["repository"]):
            rootprj, reason = self.fallback_rootprj, "fallback-repo"
        else:
            rootprj, reason = self.rootprj, "present"
        return ImageDecision(
            param=param,
            image=image,
            project=project,
            obs_project=obs_project,
            rootprj=rootprj,
            reason=reason,
            value=registry_path(self.registry, rootprj, project, ref["repository"]),
        )


def resolve_entry_images(
    entry: dict[str, Any], lane_project: str, resolver: ImageResolver
) -> list[ImageDecision]:
    """Replace every image reference in ``entry["parameters"]`` with its path.

    Mutates *entry* in place; returns the decisions in parameter order.
    """
    decisions: list[ImageDecision] = []
    params: dict[str, Any] = entry.get("parameters") or {}
    for name, value in list(params.items()):
        if is_image_ref(value):
            decision = resolver.decide(name, value, lane_project)
            params[name] = decision.value
            decisions.append(decision)
    return decisions


def image_ref_errors(
    entry: dict[str, Any],
    lane_project: str,
    project_dir: Callable[[str], Any],
    repositories_of: Callable[[Any], set[str]],
) -> list[str]:
    """Static checks for every image reference of one qa entry.

    *project_dir(project)* returns the tree directory of a colon-notation
    project (a ``pathlib.Path``); *repositories_of(dir)* its configured
    repository names.  A reference whose project is not a directory in the
    tree is skipped: it may exist only on OBS (e.g. a previous major whose
    tree was removed), and ``_validate_repo_path_refs`` applies the same rule.
    """
    errors: list[str] = []
    for name, value in (entry.get("parameters") or {}).items():
        if not is_image_ref(value):
            continue
        project = value.get("project") or lane_project
        pdir = project_dir(project)
        if not (pdir / "project.yaml").is_file():
            continue
        image = value["image"]
        if not (pdir / image).is_dir():
            errors.append(
                f"qa.parameters.{name}: image '{image}' is not a package of "
                f"project '{project}'"
            )
        repository = value["repository"]
        if repository not in repositories_of(pdir):
            errors.append(
                f"qa.parameters.{name}: repository '{repository}' is not defined "
                f"by project '{project}'"
            )
    return errors
