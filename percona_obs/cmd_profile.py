import argparse
import sys

import yaml

from .common import (
    _BOLD,
    _DIM,
    _PROFILES_DIR,
    _RED,
    _col,
    _print_create,
    _print_ok,
    _print_update,
    parse_env_overrides,
)
from .project_config import RepositoryFilter


def _load_profile(name: str) -> dict[str, str]:
    """Load OBS connection settings from .profile/<name>.yaml.

    Returns a dict with keys matching the CLI long option names (e.g.
    ``apiurl``, ``rootprj``).  Raises SystemExit if the file is missing.
    """
    path = _PROFILES_DIR / f"{name}.yaml"
    if not path.is_file():
        available: list[str] = (
            sorted(p.stem for p in _PROFILES_DIR.glob("*.yaml"))
            if _PROFILES_DIR.is_dir()
            else []
        )
        hint = (
            f"  Available profiles: {', '.join(available)}"
            if available
            else "  No profiles found in .profile/ — create one first."
        )
        raise SystemExit(f"error: profile {name!r} not found: {path}\n{hint}")
    with path.open(encoding="utf-8") as fh:
        data: object = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise SystemExit(f"error: profile {path} is empty or not a YAML mapping")
    return {
        k: str(v)
        for k, v in data.items()
        if v is not None and not isinstance(v, (list, dict))
    }


def _load_profile_filter(name: str) -> RepositoryFilter:
    """The slice declared in .profile/<name>.yaml (``include-repositories`` …).

    A missing profile or one without filter keys is unfiltered.  Malformed
    lists exit with an error naming the file.
    """
    path = _PROFILES_DIR / f"{name}.yaml"
    if not path.is_file():
        return RepositoryFilter.EMPTY
    with path.open(encoding="utf-8") as fh:
        data: object = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return RepositoryFilter.EMPTY
    f = RepositoryFilter.from_profile(data, source=str(path))
    return RepositoryFilter.EMPTY if f.is_empty else f


def _split_globs(values: list[str]) -> tuple[str, ...]:
    """``["a,b", "c"]`` → ``("a", "b", "c")`` (profile create flag values)."""
    return tuple(x.strip() for v in values for x in v.split(",") if x.strip())


def _load_profile_env_strings(name: str) -> list[str]:
    """Return the ``env`` section of .profile/<name>.yaml as ``KEY:VALUE`` strings.

    Returns an empty list if the profile has no ``env`` section or does not exist.
    Used by ``main()`` to prepend profile env into ``args.env_overrides`` so that
    explicit ``-e`` flags always take precedence.
    """
    path = _PROFILES_DIR / f"{name}.yaml"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as fh:
        data: object = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return []
    return [
        f"{item['name']}:{item['value'] if item.get('value') is not None else ''}"
        for item in (data.get("env") or [])
        if isinstance(item, dict) and "name" in item
    ]


def _load_profile_env(profile_name: str) -> dict[str, str]:
    """Return the env dict from .profile/<profile_name>.yaml, or exit on error."""
    profile_path = _PROFILES_DIR / f"{profile_name}.yaml"
    if not profile_path.is_file():
        raise SystemExit(f"error: profile {profile_name!r} not found: {profile_path}")
    with profile_path.open(encoding="utf-8") as fh:
        data: object = yaml.safe_load(fh) or {}
    env_list = data.get("env", []) if isinstance(data, dict) else []
    return {
        item["name"]: item["value"] if item.get("value") is not None else ""
        for item in (env_list if isinstance(env_list, list) else [])
        if isinstance(item, dict) and "name" in item
    }


def cmd_profile_create(args: argparse.Namespace) -> None:
    if not args.apiurl:
        raise SystemExit("error: -A/--apiurl is required for 'profile create'")
    if not args.rootprj:
        raise SystemExit("error: -R/--rootprj is required for 'profile create'")
    _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    path = _PROFILES_DIR / f"{args.name}.yaml"
    exists = path.is_file()

    env_vars = parse_env_overrides(args.env_overrides)
    repo_filter = RepositoryFilter(
        include_repos=_split_globs(getattr(args, "include_repos", []) or []),
        exclude_repos=_split_globs(getattr(args, "exclude_repos", []) or []),
        include_projects=_split_globs(getattr(args, "include_projects", []) or []),
        exclude_projects=_split_globs(getattr(args, "exclude_projects", []) or []),
    )
    # `-P name profile create name` without filter flags re-creates the
    # profile from its current state (like -e does for env): keep its slice.
    if repo_filter.is_empty and getattr(args, "profile", None):
        repo_filter = _load_profile_filter(args.profile)
    narrow = _split_globs(getattr(args, "narrow_repos", []) or [])
    if narrow:
        kept = tuple(n for n in narrow if repo_filter.repo_matches(n))
        if not kept:
            print(
                "error: --narrow-repos leaves no repository for this profile "
                f"(narrowed to {', '.join(narrow)}; profile rules: {repo_filter.to_profile()})",
                file=sys.stderr,
            )
            raise SystemExit(3)
        repo_filter = RepositoryFilter(
            include_repos=kept,
            exclude_repos=repo_filter.exclude_repos,
            include_projects=repo_filter.include_projects,
            exclude_projects=repo_filter.exclude_projects,
        )
    data: dict[str, object] = {"apiurl": args.apiurl, "rootprj": args.rootprj}
    if env_vars:
        data["env"] = [{"name": k, "value": v} for k, v in sorted(env_vars.items())]
    data.update(repo_filter.to_profile())

    with path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)
    label = f"{args.name}  ({path})"
    if exists:
        _print_update(label)
    else:
        _print_create(label)
    _print_ok(f"profile create: {args.name}")


def cmd_profile_list(args: argparse.Namespace) -> None:
    if not _PROFILES_DIR.is_dir():
        print(
            "  No profiles found. "
            "Create one with: percona-obs -A <url> -R <prj> profile create <name>"
        )
        return
    profiles = sorted(_PROFILES_DIR.glob("*.yaml"))
    if not profiles:
        print(
            "  No profiles found. "
            "Create one with: percona-obs -A <url> -R <prj> profile create <name>"
        )
        return
    for path in profiles:
        print(f"  {_col(_BOLD, path.stem)}")
        try:
            with path.open(encoding="utf-8") as fh:
                data: object = yaml.safe_load(fh)
            if isinstance(data, dict):
                for key, val in data.items():
                    shown = (
                        ", ".join(map(str, val))
                        if isinstance(val, list) and key != "env"
                        else val
                    )
                    print(f"    {_col(_DIM, key + ':')}  {shown}")
        except Exception:
            print(f"    {_col(_RED, '(error reading file)')}")
