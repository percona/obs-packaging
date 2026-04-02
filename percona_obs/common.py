import contextlib
import io
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

logger = logging.getLogger("percona-obs")

# ---------------------------------------------------------------------------
# Paths — all derived from the repo root (two levels up from this file)
# ---------------------------------------------------------------------------
_REPO_DIR = Path(__file__).parent.parent
REPO_ROOT = _REPO_DIR / "root"
_PROFILES_DIR = _REPO_DIR / ".profile"

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
# Colours are disabled when stdout is not a TTY or when NO_COLOR is set
# (https://no-color.org/).
_USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_ERASE_LINE = "\033[K"  # erase from cursor to end of line


def _col(code: str, text: str) -> str:
    """Wrap *text* in an ANSI escape sequence when colour output is enabled."""
    return f"{code}{text}{_RESET}" if _USE_COLOR else text


def _erase() -> str:
    """Return the ANSI erase-line sequence when colour output is enabled.

    Prepended to every final status line so that a pending '⌛' line written
    with a bare carriage return is cleanly overwritten by the status line.
    """
    return _ERASE_LINE if _USE_COLOR else ""


def _print_pending(text: str) -> None:
    """Print '  ⌛ <text>' as a transient indicator of an in-progress OBS call.

    Ends with a bare carriage return (no newline) so the next _print_* call
    overwrites it in place.  No-op when stdout is not a TTY or NO_COLOR is set.
    """
    if _USE_COLOR:
        print(f"  ⌛ {text}", end="\r", flush=True)


def _print_create(text: str) -> None:
    """Print a '  + ...' line for a resource being created."""
    print(f"{_erase()}  {_col(_GREEN, '+')} {text}")


def _print_update(text: str) -> None:
    """Print a '  ~ ...' line for a resource being updated."""
    print(f"{_erase()}  {_col(_YELLOW, '~')} {text}")


def _print_same(text: str) -> None:
    """Print a '  = ...' line for an unchanged resource."""
    print(f"{_erase()}  {_col(_DIM, '=')} {text}")


def _print_action(text: str) -> None:
    """Print a '  > ...' line for a triggered action."""
    print(f"{_erase()}  {_col(_CYAN, '>')} {text}")


def _print_ok(text: str) -> None:
    """Print a '  ✔  ...' success line."""
    print(f"{_erase()}  {_col(_GREEN + _BOLD, '✔')}  {text}")


def _print_remove(text: str) -> None:
    """Print a '  - ...' line for a resource being deleted."""
    print(f"{_erase()}  {_col(_RED, '-')} {text}")


def _print_aggregate(text: str) -> None:
    """Print a '  @ ...' line for a package being aggregated from a branch source."""
    print(f"{_erase()}  {_col(_CYAN, '@')} {text}")


def _silence_stdout() -> contextlib.AbstractContextManager:
    """Context manager that swallows any stdout written inside the block.

    Used to suppress chatty osc library output such as 'Sending meta data...'
    and 'Done.' that is hardcoded in osc.core.metafile.sync().
    """
    return contextlib.redirect_stdout(io.StringIO())


def resolve_project_path(project: str) -> Path:
    """Convert OBS colon notation (prjA:prjB) to a filesystem path (root/prjA/prjB)."""
    return REPO_ROOT.joinpath(*project.split(":"))


def is_package(path: Path) -> bool:
    """A directory is a package if it contains an obs/ subdirectory or a package.yaml file."""
    return (path / "obs").is_dir() or (path / "package.yaml").exists()


def is_project(path: Path) -> bool:
    """A directory is a project if it contains a project.yaml file or is not a package."""
    return (path / "project.yaml").exists() or not is_package(path)


def find_packages(project_path: Path, obs_project: str, recursive: bool = True):
    """Recursively yield (obs_project, package_path) for all packages under a directory.

    obs_project is the full OBS project name (e.g. 'home:Admin:ppg:17.9').
    Subdirectories that are themselves projects (no obs/) are treated as
    subprojects and descended into, extending obs_project with the child name.
    When recursive=False, only direct-child packages are yielded; subproject
    directories are not descended into.
    """
    for child in sorted(project_path.iterdir()):
        if not child.is_dir():
            continue
        if is_package(child):
            yield obs_project, child
        elif recursive:
            yield from find_packages(child, f"{obs_project}:{child.name}")


_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def load_yaml(path: Path) -> dict:
    """Load a YAML file and return its contents, or an empty dict if the file does not exist."""
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_yaml_with_env(path: Path, env_vars: dict[str, str] | None) -> dict:
    """Load a YAML file with optional ${VAR} substitution before parsing.

    If ``env_vars`` is None or empty, behaves identically to ``load_yaml``.
    Raises ``SystemExit`` if the file contains an unresolvable ``${VAR}`` token.
    """
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        text = f.read()
    if env_vars:
        text = apply_env_substitution(text, env_vars, source=path)
    return yaml.safe_load(text) or {}


def apply_env_substitution(
    text: str, env_vars: dict[str, str], source: Path | None = None
) -> str:
    """Replace every ``${VAR}`` token in *text* with the value from *env_vars*.

    Raises ``SystemExit`` if any token has no corresponding entry in *env_vars*.
    *source* is used only for the error message.
    """

    def _replace(m: re.Match) -> str:
        var = m.group(1)
        if var not in env_vars:
            loc = f"{source}: " if source else ""
            raise SystemExit(
                f"error: {loc}undefined variable ${{{var}}} — "
                "define it with -e or in the active profile"
            )
        return env_vars[var]

    return _ENV_VAR_RE.sub(_replace, text)


def _emit_flag_section(
    parent: ET.Element,
    tag: str,
    flags: "dict[str, bool] | bool | None",
) -> None:
    """Append a <publish> or <build> XML section to *parent* based on *flags*.

    flags=None        → no section emitted
    flags=False       → <tag><disable/></tag>  (blanket, no repository attr)
    flags={repo: bool}→ one <enable>/<disable repository="repo"> per entry
    """
    if flags is None:
        return
    sec = ET.SubElement(parent, tag)
    if flags is False:
        ET.SubElement(sec, "disable")
    elif isinstance(flags, dict):
        for repo, enabled in flags.items():
            ET.SubElement(sec, "enable" if enabled else "disable", repository=repo)


def build_project_meta(
    obs_project_name: str,
    title: str,
    description: str,
    repositories: list,
    rootprj: str,
    publish: "dict[str, bool] | bool | None" = None,
    build: "dict[str, bool] | None" = None,
    debuginfo: "dict[str, bool] | bool | None" = None,
    active_projects: "set[str] | None" = None,
    branch_rootprj: str | None = None,
) -> str:
    """Build OBS project metadata XML from project.yaml fields.

    Only the paths explicitly listed in each repository's 'paths' list are
    emitted. No automatic ancestor-project paths are injected.

    When ``active_projects`` and ``branch_rootprj`` are provided (i.e. during a
    ``--branch-from`` sync that skips pass-through projects), any ``subproject:``
    path entry that would resolve to a PR sub-project not present in
    ``active_projects`` is redirected to the corresponding branch-source project
    (``branch_rootprj:X``) instead.
    """
    root = ET.Element("project", name=obs_project_name)
    ET.SubElement(root, "title").text = title
    ET.SubElement(root, "description").text = description
    _emit_flag_section(root, "publish", publish)
    _emit_flag_section(root, "build", build)
    _emit_flag_section(root, "debuginfo", debuginfo)
    for repo in repositories:
        repo_elem = ET.SubElement(root, "repository", name=repo["name"])
        # Each entry may use 'project:' for an absolute OBS project name, or
        # 'subproject:' for a name relative to rootprj (e.g. 'builddep' → '<rootprj>:builddep').
        # Skip a path only when it resolves to the exact same project+repository
        # as the one being defined — a repository cannot list itself as its own
        # path (e.g. builddep inheriting a 'subproject: builddep' entry from the
        # root project.yaml).  A different repository within the same project is
        # valid (e.g. 'images' depending on 'RockyLinux_9' of the same project).
        for path_info in repo.get("paths", []):
            if "subproject" in path_info:
                proj = f"{rootprj}:{path_info['subproject']}"
                # When a --branch-from sync skips pass-through projects, redirect
                # any subproject path that wasn't created to the branch source.
                if (
                    active_projects is not None
                    and proj not in active_projects
                    and branch_rootprj is not None
                ):
                    proj = f"{branch_rootprj}:{path_info['subproject']}"
            else:
                proj = path_info["project"]
            if proj == obs_project_name and path_info["repository"] == repo["name"]:
                continue
            ET.SubElement(
                repo_elem,
                "path",
                project=proj,
                repository=path_info["repository"],
            )
        for arch in repo.get("archs", []):
            ET.SubElement(repo_elem, "arch").text = arch
    ET.indent(root)
    return ET.tostring(root, encoding="unicode")


def build_package_meta(
    obs_project_name: str,
    package_name: str,
    title: str,
    description: str,
    build: "dict[str, bool] | None" = None,
    publish: "dict[str, bool] | None" = None,
) -> str:
    """Build OBS package metadata XML from package.yaml fields."""
    root = ET.Element("package", name=package_name, project=obs_project_name)
    ET.SubElement(root, "title").text = title
    ET.SubElement(root, "description").text = description
    _emit_flag_section(root, "build", build)
    _emit_flag_section(root, "publish", publish)
    ET.indent(root)
    return ET.tostring(root, encoding="unicode")


def _build_aggregate_xml(source_project: str, packages: list[str]) -> str:
    """Build an OBS _aggregate XML that pulls binaries from source_project.

    packages is the list of OBS package names to aggregate; for plain packages
    this is [package_name], for multibuild it includes flavored entries
    (e.g. ['percona-pg-telemetry:17']) and optionally the bare name.
    """
    root = ET.Element("aggregatelist")
    agg = ET.SubElement(root, "aggregate", project=source_project)
    for pkg in packages:
        ET.SubElement(agg, "package").text = pkg
    ET.indent(root)
    return ET.tostring(root, encoding="unicode")


def find_projects(path: Path, obs_project: str):
    """Recursively yield (obs_project_name, project_path) for project directories.

    obs_project_name is derived from the directory hierarchy unless overridden by
    the 'name' field in project.yaml. Only directories that are projects (no obs/)
    are descended into; package directories are skipped.
    """
    config = load_yaml(path / "project.yaml")
    obs_project_name = config.get("name") or obs_project
    yield obs_project_name, path
    for child in sorted(path.iterdir()):
        if child.is_dir() and is_project(child):
            yield from find_projects(child, f"{obs_project}:{child.name}")


def _load_project_config_with_inheritance(
    project_path: Path,
    env_vars: dict[str, str] | None = None,
) -> dict:
    """Load project.yaml, inheriting repositories and project-config from ancestors.

    Walks up the directory tree from project_path to REPO_ROOT. For each of
    'repositories' and 'project-config', if the field is absent or empty in
    the project's own project.yaml, the value from the nearest ancestor that
    defines it is used.

    'title', 'description', and 'name' are never inherited.

    If *env_vars* is provided, ``${VAR}`` tokens in every loaded file are
    substituted before YAML parsing.
    """
    config = load_yaml_with_env(project_path / "project.yaml", env_vars)

    # Collect ancestor configs from nearest parent up to (and including) REPO_ROOT
    ancestor_configs: list[dict] = []
    path = project_path.parent
    while True:
        ancestor_configs.append(load_yaml_with_env(path / "project.yaml", env_vars))
        if path == REPO_ROOT:
            break
        if not path.is_relative_to(REPO_ROOT):
            break
        path = path.parent

    for field in ("repositories", "project-config"):
        if not config.get(field):
            for ancestor in ancestor_configs:
                if ancestor.get(field):
                    config[field] = ancestor[field]
                    break

    return config


def _decode_obs_response(raw) -> str:
    """Normalise the various return types osc functions use (bytes, list[bytes], str)."""
    if isinstance(raw, (list, tuple)):
        raw = b"".join(raw) if raw and isinstance(raw[0], bytes) else "".join(raw)
    if isinstance(raw, bytes):
        return raw.decode()
    return str(raw) if raw else ""


def parse_env_overrides(entries: list[str]) -> dict[str, str]:
    """Parse a list of ``KEY:VALUE`` strings from ``-e`` flags.

    Splits on the first ``:`` so values containing colons (e.g. ``openSUSE.org:``)
    are preserved correctly.  Raises ``SystemExit`` on malformed entries.
    """
    result: dict[str, str] = {}
    for entry in entries:
        key, sep, val = entry.partition(":")
        if not sep:
            raise SystemExit(f"error: -e {entry!r}: expected KEY:VALUE format")
        result[key.strip()] = val
    return result
