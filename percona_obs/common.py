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


def _is_release_dir(path: Path) -> bool:
    """Return True if *path* is a release directory (contains release.yaml)."""
    return (path / "release.yaml").is_file()


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
        if _is_release_dir(child):
            continue
        if is_package(child):
            yield obs_project, child
        elif recursive:
            yield from find_packages(child, f"{obs_project}:{child.name}")


_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_MACRO_RE = re.compile(r"%!\{([A-Za-z_][A-Za-z0-9_]*)\}")
# Matches a single entry line in macros.yaml: "- KEY: value"
# Values may contain %!{...} references which PyYAML cannot parse unquoted.
_MACROS_ENTRY_RE = re.compile(r"^-\s+([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)\s*$")


def apply_macro_substitution(
    text: str, macros: dict[str, str], source: Path | None = None
) -> str:
    """Replace every ``%!{VAR}`` token in *text* with the value from *macros*.

    Raises ``SystemExit`` if any token has no corresponding entry in *macros*.
    *source* is used only for the error message.
    """

    def _replace(m: re.Match) -> str:
        var = m.group(1)
        if var not in macros:
            loc = f"{source}: " if source else ""
            raise SystemExit(
                f"error: {loc}undefined macro %!{{{var}}} — " "define it in macros.yaml"
            )
        return macros[var]

    return _MACRO_RE.sub(_replace, text)


def load_macros(project_path: Path) -> dict[str, str]:
    """Load and resolve macros from macros.yaml files in the directory hierarchy.

    Walks from REPO_ROOT down to *project_path*, collecting macros.yaml files.
    Entries are processed in declaration order; inner directories override outer
    ones by redefining the same key.  ``%!{VAR}`` references in values are
    resolved against previously-declared macros so forward references within a
    single file work as long as the referenced macro was declared earlier.
    """
    chain: list[Path] = []
    p = project_path
    while True:
        chain.append(p)
        if p == REPO_ROOT or not p.is_relative_to(REPO_ROOT):
            break
        p = p.parent
    chain.reverse()  # outermost (REPO_ROOT) first

    entries: list[tuple[str, str, Path]] = []
    for path in chain:
        macro_file = path / "macros.yaml"
        if not macro_file.exists():
            continue
        # Parse with a simple line scanner instead of yaml.safe_load because
        # values may contain %!{...} references and PyYAML rejects bare % at
        # the start of a scalar (it is reserved for YAML directives).
        for lineno, line in enumerate(
            macro_file.read_text("utf-8").splitlines(), start=1
        ):
            line = line.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            m = _MACROS_ENTRY_RE.match(line)
            if not m:
                raise SystemExit(
                    f"error: {macro_file}:{lineno}: expected '- KEY: value', got: {line!r}"
                )
            entries.append((m.group(1), m.group(2), macro_file))

    resolved: dict[str, str] = {}
    for key, raw_value, source_file in entries:
        resolved[key] = apply_macro_substitution(
            raw_value, resolved, source=source_file
        )
    return resolved


def load_yaml(path: Path) -> dict:
    """Load a YAML file and return its contents, or an empty dict if the file does not exist."""
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_project_yaml(
    path: Path,
    env_vars: dict[str, str] | None = None,
) -> dict:
    """Load a project.yaml with macro substitution resolved from the directory hierarchy.

    Equivalent to ``load_yaml_with_env(path, env_vars, macros=load_macros(path.parent))``.
    Use this instead of ``load_yaml`` for all ``project.yaml`` files so that
    ``%!{VAR}`` tokens are expanded before the YAML parser sees them.
    """
    return load_yaml_with_env(path, env_vars, macros=load_macros(path.parent))


def load_yaml_with_env(
    path: Path,
    env_vars: dict[str, str] | None,
    macros: dict[str, str] | None = None,
) -> dict:
    """Load a YAML file with optional macro and ${VAR} substitution before parsing.

    Macros (``%!{VAR}``) are resolved first, then environment variables
    (``${VAR}``).  Either or both substitution passes may be skipped by passing
    ``None`` for the corresponding argument.
    Raises ``SystemExit`` if the file contains an unresolvable token.
    """
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        text = f.read()
    if macros:
        text = apply_macro_substitution(text, macros, source=path)
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
    # Normalise {disable: true} / {enable: false} shorthand to a plain bool.
    if isinstance(flags, dict) and set(flags.keys()) <= {"disable", "enable"}:
        flags = not flags.get("disable", False)
    sec = ET.SubElement(parent, tag)
    if flags is False:
        ET.SubElement(sec, "disable")
    elif flags is True:
        ET.SubElement(sec, "enable")
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
    existing_branch_projects: "set[str] | None" = None,
) -> str:
    """Build OBS project metadata XML from project.yaml fields.

    Only the paths explicitly listed in each repository's 'paths' list are
    emitted. No automatic ancestor-project paths are injected.

    When ``active_projects`` and ``branch_rootprj`` are provided (i.e. during a
    ``--branch-from`` sync that skips pass-through projects), any ``subproject:``
    path entry that would resolve to a project not present in ``active_projects``
    is redirected to the corresponding branch-source project
    (``branch_rootprj:X``) instead.

    Additionally, each repository gets a leading ``<path>`` entry pointing to
    the branch counterpart of ``obs_project_name`` itself.  This ensures that
    non-promoted packages (absent from the target project) remain visible as
    build dependencies when building promoted packages in the same project.

    When ``existing_branch_projects`` is provided, every emitted ``<path>``
    entry that would point at a branch-source project (``branch_rootprj:...``)
    is gated on membership in this set.  Paths to branch-source projects that
    do not exist on OBS are silently dropped rather than being emitted (and
    later causing OBS to reject the meta with ``repository_access_failure``,
    which would otherwise trigger a strip-and-retry that loses all paths for
    the repository).  PR-side paths and external (``project:``) paths are
    unaffected.  Pass ``None`` to disable filtering.
    """
    root = ET.Element("project", name=obs_project_name)
    ET.SubElement(root, "title").text = title
    ET.SubElement(root, "description").text = description
    _emit_flag_section(root, "publish", publish)
    _emit_flag_section(root, "build", build)
    _emit_flag_section(root, "debuginfo", debuginfo)
    # When --branch-from is active, compute the branch counterpart of this
    # project so that non-promoted packages (absent from the target) remain
    # visible as build dependencies via a leading <path> entry.
    self_branch_proj: str | None = None
    if branch_rootprj is not None:
        if obs_project_name == rootprj:
            self_branch_proj = branch_rootprj
        elif obs_project_name.startswith(rootprj + ":"):
            self_branch_proj = branch_rootprj + obs_project_name[len(rootprj) :]
        if (
            self_branch_proj is not None
            and existing_branch_projects is not None
            and self_branch_proj not in existing_branch_projects
        ):
            self_branch_proj = None
    for repo in repositories:
        repo_elem = ET.SubElement(root, "repository", name=repo["name"])
        # Each entry may use 'project:' for an absolute OBS project name, or
        # 'subproject:' for a name relative to rootprj (e.g. 'builddep' → '<rootprj>:builddep').
        # Skip a path only when it resolves to the exact same project+repository
        # as the one being defined — a repository cannot list itself as its own
        # path (e.g. builddep inheriting a 'subproject: builddep' entry from the
        # root project.yaml).  A different repository within the same project is
        # valid (e.g. 'images' depending on 'RockyLinux_9' of the same project).
        #
        # When --branch-from is active the path order for each repository must be:
        #   1. PR subproject paths (active subprojects, so promoted builds are seen first)
        #   2. Production/branch subproject paths (fallback for non-promoted packages)
        #   3. self_branch_proj (production counterpart of this project — fallback for
        #      same-project non-promoted packages; always after PR subproject paths)
        #   4. Remaining paths (redirected-to-production inactive subprojects, external)
        #
        # Paths pointing to PR projects must come before production paths so that OBS
        # resolves promoted PR packages before stale production packages when computing
        # build dependencies.
        pr_paths: list[tuple[str, str]] = (
            []
        )  # (project, repository) for active PR subprojects
        prod_paths: list[tuple[str, str]] = (
            []
        )  # production fallbacks for those same subprojects
        tail_paths: list[tuple[str, str]] = []  # redirected inactive + external paths

        for path_info in repo.get("paths", []):
            if "subproject" in path_info:
                proj = f"{rootprj}:{path_info['subproject']}"
                if active_projects is not None and branch_rootprj is not None:
                    if proj not in active_projects:
                        # Pass-through project skipped: redirect to branch source.
                        redirected = f"{branch_rootprj}:{path_info['subproject']}"
                        if (
                            existing_branch_projects is None
                            or redirected in existing_branch_projects
                        ) and not (
                            redirected == obs_project_name
                            and path_info["repository"] == repo["name"]
                        ):
                            tail_paths.append((redirected, path_info["repository"]))
                    else:
                        # Active PR subproject: PR path first, production fallback second.
                        branch_proj = f"{branch_rootprj}:{path_info['subproject']}"
                        repo_name = path_info["repository"]
                        if not (proj == obs_project_name and repo_name == repo["name"]):
                            pr_paths.append((proj, repo_name))
                        # Skip production fallback if it duplicates self_branch_proj
                        # (avoids a redundant path when the subproject reference points
                        # to the project being configured itself), or if the branch
                        # counterpart project does not exist on OBS yet (e.g. a
                        # subproject newly added by this PR has no production peer).
                        if (
                            (
                                existing_branch_projects is None
                                or branch_proj in existing_branch_projects
                            )
                            and not (
                                branch_proj == obs_project_name
                                and repo_name == repo["name"]
                            )
                            and not (
                                branch_proj == self_branch_proj
                                and repo_name == repo["name"]
                            )
                        ):
                            prod_paths.append((branch_proj, repo_name))
                    continue
            else:
                proj = path_info["project"]
            if proj == obs_project_name and path_info["repository"] == repo["name"]:
                continue
            tail_paths.append((proj, path_info["repository"]))

        # Emit in priority order: PR subprojects → production fallbacks →
        # self_branch_proj → remaining (inactive redirects + external).
        for _proj, _repo in pr_paths:
            ET.SubElement(repo_elem, "path", project=_proj, repository=_repo)
        for _proj, _repo in prod_paths:
            ET.SubElement(repo_elem, "path", project=_proj, repository=_repo)
        if self_branch_proj:
            ET.SubElement(
                repo_elem, "path", project=self_branch_proj, repository=repo["name"]
            )
        for _proj, _repo in tail_paths:
            ET.SubElement(repo_elem, "path", project=_proj, repository=_repo)
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
    config = load_project_yaml(path / "project.yaml")
    obs_project_name = config.get("name") or obs_project
    yield obs_project_name, path
    for child in sorted(path.iterdir()):
        if child.is_dir() and not _is_release_dir(child) and is_project(child):
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

    ``%!{VAR}`` macro tokens (from macros.yaml in the hierarchy) are resolved
    first, then ``${VAR}`` env-var tokens are substituted.
    """
    macros = load_macros(project_path)
    config = load_yaml_with_env(project_path / "project.yaml", env_vars, macros)

    # Collect ancestor configs from nearest parent up to (and including) REPO_ROOT
    ancestor_configs: list[dict] = []
    path = project_path.parent
    while True:
        ancestor_macros = load_macros(path)
        ancestor_configs.append(
            load_yaml_with_env(path / "project.yaml", env_vars, ancestor_macros)
        )
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


def auto_rootprj_env(rootprj: str) -> dict[str, str]:
    """Auto-injected env vars derived from the OBS root project name.

    Used as the base of every YAML-substitution env dict so that project.yaml
    files can reference ``${OBS_ROOTPRJ}`` (e.g. for sibling subprojects in
    _aggregate files) and ``${OBS_CONTAINER_REGISTRY_ROOTPRJ}`` (e.g. for registry URL
    paths) consistently across all commands.
    """
    return {
        "OBS_ROOTPRJ": rootprj,
        "OBS_CONTAINER_REGISTRY_ROOTPRJ": rootprj.replace(":", "/").lower(),
    }


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
