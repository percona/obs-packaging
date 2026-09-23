import sys
from pathlib import Path

from . import common
from .common import (
    REPO_ROOT,
    _is_release_dir,
    _load_project_config_with_inheritance,
    find_packages,
    is_package,
    load_project_yaml,
    load_yaml,
    resolve_project_path,
)
from .project_config import project_in_slice


def _has_direct_packages(path: Path) -> bool:
    """Return True if path directly contains at least one package directory."""
    return any(child.is_dir() and is_package(child) for child in path.iterdir())


def is_dockerfile_image(package_path: Path) -> bool:
    """Return True if package_path is a Dockerfile-based container image package."""
    return (package_path / "obs" / "Dockerfile").is_file()


def image_dep_query_repos(
    package_path: Path,
    env_vars: "dict[str, str] | None" = None,
    cache: "dict[Path, set[str]] | None" = None,
) -> set[str]:
    """Repository names to query for a container image's _buildinfo dep edges.

    The built-image repo name depends on the containers layout: the old
    ":containers:<flavor>" subprojects expose a single repo literally named
    "images", while the restructured single ":containers" subproject names
    its image repos after the flavor (e.g. "ubi8"/"ubi9").  Derive the names
    from the image's own project config rather than assuming "images".

    The repository set is the sliced one (the active profile's filter is
    applied by the loader).  *cache* maps project_path → repo names across
    images in the same project.
    """
    project_path = package_path.parent
    repos = cache.get(project_path) if cache is not None else None
    if repos is None:
        config = _load_project_config_with_inheritance(project_path, env_vars)
        repos = {r["name"] for r in config.get("repositories", []) if r.get("name")}
        if cache is not None:
            cache[project_path] = repos
    return repos


def _resolve_targets(args) -> list[tuple[str, Path]]:
    """Resolve the list of (obs_project, package_path) targets from CLI args.

    args must have: rootprj, project (optional), package (optional).
    """
    recursive = not getattr(args, "non_recursive", False)

    if args.project is None:
        targets = list(find_packages(REPO_ROOT, args.rootprj, recursive=recursive))
        if not targets and recursive:
            print("error: no packages found under root", file=sys.stderr)
            sys.exit(1)
        return targets

    first_path = resolve_project_path(args.project)
    if not first_path.is_dir():
        print(f"error: '{args.project}' not found under root/", file=sys.stderr)
        sys.exit(1)

    if is_package(first_path):
        # First arg is a top-level package, not a project
        if args.package is not None:
            print(
                f"error: '{args.project}' is a package; a sub-package argument cannot be given",
                file=sys.stderr,
            )
            sys.exit(1)
        return [(args.rootprj, first_path)]

    # First arg is a project
    full_obs_project = f"{args.rootprj}:{args.project}"
    if args.package is not None:
        package_path = first_path / args.package
        if not package_path.is_dir():
            print(
                f"error: package directory not found: {package_path}", file=sys.stderr
            )
            sys.exit(1)
        if not is_package(package_path):
            print(
                f"error: '{args.package}' is not a package (no obs/ directory found inside)",
                file=sys.stderr,
            )
            sys.exit(1)
        return [(full_obs_project, package_path)]

    targets = list(find_packages(first_path, full_obs_project, recursive=recursive))
    if not targets:
        print(
            f"error: no packages found under project '{args.project}'", file=sys.stderr
        )
        sys.exit(1)
    return targets


def _iter_project_chain(
    obs_project: str,
    project_path: Path,
    slice_cache: "dict[Path, bool] | None" = None,
):
    """Yield (raw_obs_project, obs_project_name, path) from root down to project_path.

    Walks up from project_path to REPO_ROOT, then yields in reverse (root-first)
    so every ancestor project level is visited before the immediate project.
    Projects that are out of the active slice (``project_in_slice``: excluded
    by the profile, or left with zero repositories) are not yielded: they are
    never created, and a full-tree push deletes them as orphans.

    raw_obs_project is the path-derived key used for deduplication.
    obs_project_name may differ if project.yaml contains a 'name' override.
    *slice_cache* memoises the in-slice decision per project path across calls.
    """
    chain = []
    path = project_path
    proj = obs_project
    while True:
        config = load_project_yaml(path / "project.yaml")
        obs_name = config.get("name") or proj
        chain.append((proj, obs_name, path))
        if path == common.REPO_ROOT:
            break
        if not path.is_relative_to(common.REPO_ROOT):
            break
        path = path.parent
        proj = proj.rsplit(":", 1)[0]
    for proj, obs_name, path in reversed(chain):
        if _is_release_dir(path):
            continue  # release dirs are managed by sync release, not sync push
        if not ((path / "project.yaml").exists() or _has_direct_packages(path)):
            continue
        if not project_in_slice(path, cache=slice_cache):
            continue
        yield proj, obs_name, path
