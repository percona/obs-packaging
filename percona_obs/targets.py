import sys
from pathlib import Path

from .common import (
    REPO_ROOT,
    find_packages,
    is_package,
    load_yaml,
    resolve_project_path,
)


def _has_direct_packages(path: Path) -> bool:
    """Return True if path directly contains at least one package directory."""
    return any(child.is_dir() and is_package(child) for child in path.iterdir())


def _resolve_targets(args) -> list[tuple[str, Path]]:
    """Resolve the list of (obs_project, package_path) targets from CLI args.

    args must have: rootprj, project (optional), package (optional).
    """
    recursive = not getattr(args, "non_recursive", False)

    if args.project is None:
        targets = list(find_packages(REPO_ROOT, args.rootprj, recursive=recursive))
        if not targets:
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


def _iter_project_chain(obs_project: str, project_path: Path):
    """Yield (raw_obs_project, obs_project_name, path) from root down to project_path.

    Walks up from project_path to REPO_ROOT, then yields in reverse (root-first)
    so every ancestor project level is visited before the immediate project.

    raw_obs_project is the path-derived key used for deduplication.
    obs_project_name may differ if project.yaml contains a 'name' override.
    """
    chain = []
    path = project_path
    proj = obs_project
    while True:
        config = load_yaml(path / "project.yaml")
        obs_name = config.get("name") or proj
        chain.append((proj, obs_name, path))
        if path == REPO_ROOT:
            break
        if not path.is_relative_to(REPO_ROOT):
            break
        path = path.parent
        proj = proj.rsplit(":", 1)[0]
    for proj, obs_name, path in reversed(chain):
        if (path / "project.yaml").exists() or _has_direct_packages(path):
            yield proj, obs_name, path
