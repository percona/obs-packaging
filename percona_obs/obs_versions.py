"""Package versions as OBS built them.

One ``GET /build/<project>/_result?view=binarylist`` lists every package's
binaries in every repository of a project; the version-release of a package
in a repository is read from a binary file name (source artifacts preferred,
their names are the package's own).  Callers decide what to do with
disagreeing repositories: ``agreed_version`` (qa) or ``first_versrel``
(``project versions --online``).
"""

from __future__ import annotations

import urllib.error
import xml.etree.ElementTree as ET

import osc.connection
import osc.core

from .cmd_build import _version_from_binary
from .project_config import RepositoryFilter

PerRepo = dict[tuple[str, str], str]
ProjectVersions = dict[str, PerRepo]

_cache: dict[tuple[str, str, str], "ProjectVersions | None"] = {}


def clear_cache() -> None:
    _cache.clear()


def _pick_versrel(filenames: list[str]) -> "str | None":
    names = sorted(filenames)
    for name in names:
        if name.endswith((".src.rpm", ".dsc")):
            versrel = _version_from_binary(name)
            if versrel:
                return versrel
    for name in names:
        versrel = _version_from_binary(name)
        if versrel:
            return versrel
    return None


def project_binary_versions(
    apiurl: str, obs_project: str, repo_filter: "RepositoryFilter | None" = None
) -> "ProjectVersions | None":
    """``{package: {(repo, arch): versrel}}`` for *obs_project*, or None when
    the project does not exist.  A package listed without a readable binary
    in a repository has no entry for it (an empty dict when it has none
    anywhere).  Repositories rejected by *repo_filter* are skipped."""
    key = (apiurl, obs_project, repr(repo_filter.to_profile()) if repo_filter else "")
    if key in _cache:
        return _cache[key]
    url = osc.core.makeurl(
        apiurl, ["build", obs_project, "_result"], query={"view": "binarylist"}
    )
    try:
        root = ET.fromstring(osc.connection.http_GET(url).read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _cache[key] = None
            return None
        raise SystemExit(
            f"error: cannot list the binaries of {obs_project}: HTTP {exc.code} {exc.reason}"
        )
    except (urllib.error.URLError, ET.ParseError, OSError) as exc:
        raise SystemExit(f"error: cannot list the binaries of {obs_project}: {exc}")
    versions: ProjectVersions = {}
    for result in root.findall("result"):
        repo = result.get("repository", "")
        arch = result.get("arch", "")
        if repo_filter is not None and not repo_filter.repo_matches(repo):
            continue
        for binarylist in result.findall("binarylist"):
            package = binarylist.get("package", "")
            if not package:
                continue
            per_repo = versions.setdefault(package, {})
            versrel = _pick_versrel(
                [b.get("filename", "") for b in binarylist.findall("binary")]
            )
            if versrel:
                per_repo[(repo, arch)] = versrel
    _cache[key] = versions
    return versions


def upstream_version(versrel: str) -> str:
    """'2.60.0-1.1' -> '2.60.0': the version without the release."""
    return versrel.rsplit("-", 1)[0]


class VersionConflict(Exception):
    def __init__(self, package: str, by_version: "dict[str, list[tuple[str, str]]]"):
        self.package = package
        self.by_version = by_version
        listing = ", ".join(
            f"{version} ({', '.join(f'{r}/{a}' for r, a in sorted(repos))})"
            for version, repos in sorted(by_version.items())
        )
        super().__init__(f"{package}: OBS builds disagree on the version: {listing}")


def agreed_version(package: str, per_repo: PerRepo) -> str:
    """The upstream version every repository agrees on."""
    by_version: dict[str, list[tuple[str, str]]] = {}
    for repo_arch, versrel in per_repo.items():
        by_version.setdefault(upstream_version(versrel), []).append(repo_arch)
    if len(by_version) != 1:
        raise VersionConflict(package, by_version)
    return next(iter(by_version))


def first_versrel(per_repo: PerRepo) -> str:
    """The versrel of the first (repo, arch) in sorted order."""
    return per_repo[min(per_repo)]
