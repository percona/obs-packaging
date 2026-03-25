import concurrent.futures
import re
import sys
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

import osc.conf
import osc.core
import yaml

from .common import (
    REPO_ROOT,
    _BOLD,
    _DIM,
    _PROFILES_DIR,
    _RED,
    _col,
    _ENV_VAR_RE,
    _load_project_config_with_inheritance,
    apply_env_substitution,
    build_project_meta,
    find_projects,
    is_package,
    is_project,
    load_yaml,
    parse_env_overrides,
    resolve_project_path,
    _print_ok,
)
from .cmd_profile import _load_profile
from .obs_api import _fetch_obs_download_url
from .services import _git_head_sha

_YAML_FILENAMES = {"project.yaml", "package.yaml"}
_OBS_FILENAMES = {"_service", "_aggregate", "_link"}


def _validate_subproject_refs(root: Path) -> list[tuple[Path, str]]:
    """Check all subproject: references in project.yaml files under ``root``.

    Returns a list of (yaml_path, error_message) for each invalid reference.
    Only validates subproject: entries (relative to rootprj); project: entries
    reference external OBS projects and cannot be validated locally.
    """
    errors: list[tuple[Path, str]] = []
    for yaml_path in sorted(root.rglob("project.yaml")):
        config = load_yaml(yaml_path)
        for repo in config.get("repositories", []):
            for path_info in repo.get("paths", []):
                subproject = path_info.get("subproject")
                if subproject is None:
                    continue
                # subproject uses colon notation: "builddep" → root/builddep/,
                # "ppg:17.9" → root/ppg/17.9/
                target = REPO_ROOT.joinpath(*subproject.split(":"))
                if not target.is_dir():
                    errors.append(
                        (
                            yaml_path,
                            f"subproject '{subproject}' not found "
                            f"(expected {target.relative_to(REPO_ROOT.parent)})",
                        )
                    )
    return errors


def _validate_project_path_refs(
    root: Path,
    env_vars: dict[str, str] | None,
    apiurl: str,
    rootprj: str | None = None,
) -> list[tuple[Path, str]]:
    """Validate project: path entries in project.yaml files against the live OBS.

    For each ``project:`` entry (after env var substitution), verifies that:
    1. The referenced OBS project exists on the server.
    2. The referenced repository name exists in that project.

    Only locally-managed projects (those with a corresponding directory under
    REPO_ROOT) are validated.  External interconnect references such as
    ``openSUSE.org:openSUSE:Factory`` are skipped automatically because they
    will not appear in the local directory tree.

    Entries whose ``project:`` or ``repository:`` value contains unresolvable
    ``${VAR}`` tokens (env_vars is None or var is absent) are skipped.

    Returns a list of (yaml_path, error_message) for each invalid reference.
    The OBS project meta is fetched at most once per unique project name.
    """
    errors: list[tuple[Path, str]] = []

    # Build the set of locally-managed OBS project names by scanning the
    # directory tree under REPO_ROOT.  Only these names are validated against
    # the live OBS instance; everything else is an external interconnect.
    local_obs_project_names: set[str] = set()
    if rootprj:
        root_config = load_yaml(REPO_ROOT / "project.yaml")
        root_obs_name = root_config.get("name") or rootprj
        for obs_name, _ in find_projects(REPO_ROOT, root_obs_name):
            local_obs_project_names.add(obs_name)

    # Collect (yaml_path, resolved_project, resolved_repository) triples.
    triples: list[tuple[Path, str, str]] = []
    for yaml_path in sorted(root.rglob("project.yaml")):
        config = load_yaml(yaml_path)
        for repo in config.get("repositories", []):
            for path_info in repo.get("paths", []):
                raw_project = path_info.get("project")
                if raw_project is None:
                    continue  # subproject: entry, validated by _validate_subproject_refs
                raw_repository = str(path_info.get("repository", ""))

                # Resolve env vars in project name; skip if any var is absent.
                proj_tokens = _ENV_VAR_RE.findall(raw_project)
                if proj_tokens:
                    if env_vars is None or any(t not in env_vars for t in proj_tokens):
                        continue
                    resolved_project = _ENV_VAR_RE.sub(
                        lambda m: env_vars[m.group(1)], raw_project
                    )
                else:
                    resolved_project = raw_project

                # Resolve env vars in repository name; skip if any var is absent.
                repo_tokens = _ENV_VAR_RE.findall(raw_repository)
                if repo_tokens:
                    if env_vars is None or any(t not in env_vars for t in repo_tokens):
                        continue
                    resolved_repository = _ENV_VAR_RE.sub(
                        lambda m: env_vars[m.group(1)], raw_repository
                    )
                else:
                    resolved_repository = raw_repository

                triples.append((yaml_path, resolved_project, resolved_repository))

    # Verify each (project, repository) pair against OBS, caching per project.
    # project_repos[project] = set of repo names, or None if project not found.
    project_repos: dict[str, set[str] | None] = {}
    for yaml_path, project, repository in triples:
        # Skip projects that are not locally managed (external interconnects).
        # When rootprj was provided, only names found in the local directory
        # tree are validated; everything else is skipped silently.
        if local_obs_project_names and project not in local_obs_project_names:
            continue
        if project not in project_repos:
            try:
                raw = osc.core.show_project_meta(apiurl, project)
                meta_bytes = raw if isinstance(raw, bytes) else b"".join(raw)
                root_el = ET.fromstring(meta_bytes)
                project_repos[project] = {
                    r.get("name", "") for r in root_el.findall("repository")
                }
            except urllib.error.HTTPError as e:
                project_repos[project] = None if e.code == 404 else None
            except Exception:
                project_repos[project] = None

        repos = project_repos[project]
        if repos is None:
            errors.append(
                (
                    yaml_path,
                    f"OBS project {project!r} not found — "
                    "check env var values for project: path entries",
                )
            )
        elif repository not in repos:
            errors.append(
                (
                    yaml_path,
                    f"repository {repository!r} not found in OBS project {project!r} — "
                    "check env var values for repository: path entries",
                )
            )

    return errors


def _find_env_var_usages(root: Path) -> dict[str, list[tuple[Path, int]]]:
    """Scan project.yaml, package.yaml, and obs/{_service,_aggregate,_link} files
    under ``root`` for ${VAR} tokens.

    Returns a dict mapping variable name → list of (file_path, line_no).
    """
    usages: dict[str, list[tuple[Path, int]]] = {}

    def _scan(file_path: Path) -> None:
        with file_path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                for m in _ENV_VAR_RE.finditer(line):
                    usages.setdefault(m.group(1), []).append((file_path, lineno))

    for name in sorted(_YAML_FILENAMES):
        for fp in sorted(root.rglob(name)):
            _scan(fp)
    for name in sorted(_OBS_FILENAMES):
        for fp in sorted(root.rglob(f"obs/{name}")):
            _scan(fp)

    return usages


def _validate_env_vars(
    root: Path,
    env_vars: dict[str, str] | None,
) -> list[tuple[Path, int, str, str]]:
    """Check that every ${VAR} token under ``root`` is resolvable.

    ``env_vars`` is the merged dict of profile env + CLI overrides.  Pass
    ``None`` when no profile is active and no -e flags were given — every
    token found will be reported as an error telling the user to supply a
    profile.

    Returns a list of (file_path, line_no, var_name, error_detail).
    """
    usages = _find_env_var_usages(root)
    if not usages:
        return []

    errors: list[tuple[Path, int, str, str]] = []
    for var_name, locations in sorted(usages.items()):
        if env_vars is None:
            detail = "no profile active — re-run with -P <profile> or -e KEY:VALUE"
        elif var_name not in env_vars:
            detail = "undefined in the active profile/env"
        else:
            continue
        for fp, lineno in locations:
            errors.append((fp, lineno, var_name, detail))

    return errors


def _validate_obs_scm_revisions(
    service_files: list[Path],
    env_vars: dict[str, str] | None = None,
) -> list[tuple[Path, str, str]]:
    """Check that every obs_scm revision in the given _service files exists remotely.

    Deduplicates by (url, revision) so shared repos only trigger one network call.
    If *env_vars* is provided, ``${VAR}`` tokens in the file are substituted before
    parsing.  Revisions that still contain unresolved ``${VAR}`` tokens after
    substitution (because *env_vars* is None or incomplete) are silently skipped.

    Returns a list of (service_file, url, revision) for unresolvable revisions.
    """
    # Collect all (url, revision) pairs with the first service file that uses them.
    seen: dict[tuple[str, str], Path] = {}
    for svc_file in service_files:
        try:
            text = svc_file.read_text("utf-8")
            if env_vars:
                text = apply_env_substitution(text, env_vars, source=svc_file)
            root = ET.fromstring(text)
        except (ET.ParseError, OSError, SystemExit):
            continue
        for svc in root.findall("service"):
            if svc.get("name") != "obs_scm":
                continue
            url = next(
                (
                    (p.text or "").strip()
                    for p in svc.findall("param")
                    if p.get("name") == "url"
                ),
                "",
            )
            revision = next(
                (
                    (p.text or "").strip()
                    for p in svc.findall("param")
                    if p.get("name") == "revision"
                ),
                "HEAD",
            )
            if not url:
                continue
            key = (url, revision)
            if key not in seen:
                seen[key] = svc_file

    to_check = [
        (url, revision, svc_file)
        for (url, revision), svc_file in seen.items()
        if revision.upper() != "HEAD" and not _ENV_VAR_RE.search(revision)
    ]

    if not to_check:
        return []

    print(f"  · validating {len(to_check)} obs_scm revision(s)…", flush=True)

    errors: list[tuple[Path, str, str]] = []

    def _check(item: tuple[str, str, Path]) -> tuple[Path, str, str] | None:
        url, revision, svc_file = item
        sha = _git_head_sha(url, revision)
        return None if sha is not None else (svc_file, url, revision)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for result in pool.map(_check, to_check):
            if result is not None:
                errors.append(result)

    return errors


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


def cmd_project_verify(args) -> None:
    # Resolve scan root from optional project/package scope arguments.
    if args.project:
        scan_root = resolve_project_path(args.project)
        if not scan_root.is_dir():
            print(
                f"error: project '{args.project}' not found "
                f"(expected {scan_root.relative_to(REPO_ROOT.parent)})",
                file=sys.stderr,
            )
            sys.exit(1)
        if getattr(args, "package", None):
            scan_root = scan_root / args.package
            if not scan_root.is_dir():
                print(
                    f"error: package '{args.package}' not found under '{args.project}'",
                    file=sys.stderr,
                )
                sys.exit(1)
    else:
        if getattr(args, "package", None):
            print(
                "error: a project argument is required when specifying a package",
                file=sys.stderr,
            )
            sys.exit(1)
        scan_root = REPO_ROOT

    # Build env_vars from -P profile (if any), then apply -e overrides.
    env_vars: dict[str, str] | None = None
    if args.profile:
        env_vars = _load_profile_env(args.profile)
    if args.env_overrides:
        overrides = parse_env_overrides(args.env_overrides)
        env_vars = {**(env_vars or {}), **overrides}

    ref_errors = _validate_subproject_refs(scan_root)
    env_errors = _validate_env_vars(scan_root, env_vars)
    service_files = sorted(scan_root.rglob("obs/_service"))
    scm_errors = _validate_obs_scm_revisions(service_files, env_vars=env_vars)

    # Validate project: path entries against the live OBS instance when a
    # profile is available (provides the apiurl and env var values).
    path_ref_errors: list[tuple[Path, str]] = []
    if args.profile:
        profile = _load_profile(args.profile)
        apiurl = profile.get("apiurl", "")
        if apiurl:
            osc.conf.get_config(override_apiurl=apiurl)
            path_ref_errors = _validate_project_path_refs(
                scan_root, env_vars, apiurl, rootprj=getattr(args, "rootprj", None)
            )

    for yaml_path, msg in ref_errors:
        rel = yaml_path.relative_to(REPO_ROOT.parent)
        print(f"error: {rel}: {msg}", file=sys.stderr)

    for file_path, lineno, var_name, detail in env_errors:
        rel = file_path.relative_to(REPO_ROOT.parent)
        print(f"error: {rel}:{lineno}: ${{{var_name}}}: {detail}", file=sys.stderr)

    for svc_file, url, revision in scm_errors:
        rel = svc_file.relative_to(REPO_ROOT.parent)
        print(
            f"error: {rel}: obs_scm revision '{revision}' not found in {url}",
            file=sys.stderr,
        )

    for yaml_path, msg in path_ref_errors:
        rel = yaml_path.relative_to(REPO_ROOT.parent)
        print(f"error: {rel}: {msg}", file=sys.stderr)

    if ref_errors or env_errors or scm_errors or path_ref_errors:
        sys.exit(1)
    _print_ok("project verify: all checks passed")


def cmd_project_config(args) -> None:
    if not args.rootprj:
        raise SystemExit(
            "error: --rootprj is required for 'project config' "
            "(supply -R/--rootprj or use -P/--profile)"
        )

    # Build env_vars (same precedence as all other commands).
    # None means no substitution — ${VAR} tokens are shown as-is.
    env_vars: dict[str, str] | None = None
    if args.profile:
        env_vars = _load_profile_env(args.profile)
    if args.env_overrides:
        overrides = parse_env_overrides(args.env_overrides)
        env_vars = {**(env_vars or {}), **overrides}

    # Resolve scope: a single project or the whole tree.
    if args.project:
        scope_path = resolve_project_path(args.project)
        if not scope_path.is_dir():
            raise SystemExit(
                f"error: project '{args.project}' not found "
                f"(expected {scope_path.relative_to(REPO_ROOT.parent)})"
            )
        if not is_project(scope_path):
            raise SystemExit(f"error: '{args.project}' is a package, not a project")
        scope_obs_name = f"{args.rootprj}:{args.project}"
        projects = list(find_projects(scope_path, scope_obs_name))
    else:
        root_config = load_yaml(REPO_ROOT / "project.yaml")
        root_obs_name = root_config.get("name") or args.rootprj
        projects = list(find_projects(REPO_ROOT, root_obs_name))

    sep = _col(_DIM, "─" * 60)
    for obs_project_name, project_path in projects:
        project_config = _load_project_config_with_inheritance(project_path, env_vars)
        meta = build_project_meta(
            obs_project_name,
            project_config.get("title", ""),
            project_config.get("description", ""),
            project_config.get("repositories", []),
            args.rootprj,
        )
        project_config_str = (project_config.get("project-config") or "").strip()

        print(sep)
        print(_col(_BOLD, f"project meta  {obs_project_name}"))
        print(meta)
        print()
        print(_col(_BOLD, f"project config  {obs_project_name}"))
        print(project_config_str if project_config_str else _col(_DIM, "(empty)"))
        print()


_DEB_REPO_PREFIXES = ("Debian_", "xUbuntu_", "Ubuntu_", "Mint_")
_ZYPPER_REPO_PREFIXES = ("openSUSE_", "SLE_", "SLES_")


def _repo_pkg_manager(repo_name: str) -> str:
    """Return 'deb', 'zypper', or 'dnf' based on the OBS repository name."""
    if any(repo_name.startswith(p) for p in _DEB_REPO_PREFIXES):
        return "deb"
    if any(repo_name.startswith(p) for p in _ZYPPER_REPO_PREFIXES):
        return "zypper"
    return "dnf"


def _obs_project_url_path(obs_project: str) -> str:
    """Convert an OBS project name to its download URL path segment.

    "home:a:b:c" -> "home:/a:/b:/c"
    """
    return ":/".join(obs_project.split(":"))


def cmd_project_install(args) -> None:
    """Print repository installation instructions for the packages in scope."""
    if not args.rootprj:
        raise SystemExit(
            "error: --rootprj is required for 'project install' "
            "(supply -R/--rootprj or use -P/--profile)"
        )

    osc.conf.get_config(override_apiurl=args.apiurl)
    apiurl = osc.conf.config["apiurl"]

    download_url = _fetch_obs_download_url(apiurl)
    if not download_url:
        raise SystemExit(
            f"error: could not retrieve download URL from OBS instance ({apiurl})"
        )

    # Build env_vars from profile + -e overrides.
    env_vars: dict[str, str] | None = None
    if args.profile:
        env_vars = _load_profile_env(args.profile)
    if args.env_overrides:
        overrides = parse_env_overrides(args.env_overrides)
        env_vars = {**(env_vars or {}), **overrides}

    # Resolve scope.
    if args.project:
        scope_path = resolve_project_path(args.project)
        if not scope_path.is_dir():
            raise SystemExit(
                f"error: project '{args.project}' not found "
                f"(expected {scope_path.relative_to(REPO_ROOT.parent)})"
            )
        if not is_project(scope_path):
            raise SystemExit(f"error: '{args.project}' is a package, not a project")
        scope_obs_name = f"{args.rootprj}:{args.project}"
    else:
        scope_path = REPO_ROOT
        root_config = load_yaml(REPO_ROOT / "project.yaml")
        scope_obs_name = root_config.get("name") or args.rootprj

    all_projects = list(find_projects(scope_path, scope_obs_name))

    # Filter: skip opt-out projects and projects with no direct packages.
    def _has_direct_packages(project_path: Path) -> bool:
        return any(c.is_dir() and is_package(c) for c in project_path.iterdir())

    projects = [
        (obs_name, proj_path)
        for obs_name, proj_path in all_projects
        if load_yaml(proj_path / "project.yaml").get("publish") is not False
        and _has_direct_packages(proj_path)
    ]

    if not projects:
        raise SystemExit("error: no installable projects found in scope")

    # Build repo_name -> [obs_project_name, ...] mapping.
    repo_entries: dict[str, list[str]] = {}
    for obs_project_name, project_path in projects:
        config = _load_project_config_with_inheritance(project_path, env_vars)
        for repo in config.get("repositories", []):
            repo_name = repo.get("name", "")
            if not repo_name:
                continue
            if args.repo and repo_name != args.repo:
                continue
            repo_entries.setdefault(repo_name, [])
            if obs_project_name not in repo_entries[repo_name]:
                repo_entries[repo_name].append(obs_project_name)

    if not repo_entries:
        if args.repo:
            raise SystemExit(f"error: repository '{args.repo}' not found in scope")
        raise SystemExit("error: no repositories found in scope")

    sep = _col(_DIM, "─" * 72)
    for repo_name in sorted(repo_entries):
        print(sep)
        print(_col(_BOLD, repo_name))
        print()
        pkg_mgr = _repo_pkg_manager(repo_name)
        proj_list = repo_entries[repo_name]

        for obs_project in proj_list:
            url_path = _obs_project_url_path(obs_project)
            repo_url = f"{download_url}/{url_path}/{repo_name}/"
            print(f"# {obs_project}")

            if pkg_mgr == "deb":
                list_file = f"{obs_project}.list"
                gpg_file = re.sub(r"[:.]+", "_", obs_project) + ".gpg"
                print(
                    f"echo 'deb {repo_url} /' \\\n"
                    f"  | tee /etc/apt/sources.list.d/{list_file}"
                )
                print(
                    f"curl -fsSL {repo_url}Release.key \\\n"
                    f"  | gpg --dearmor"
                    f" | tee /etc/apt/trusted.gpg.d/{gpg_file} > /dev/null"
                )
            elif pkg_mgr == "zypper":
                print(f"zypper addrepo \\\n" f"  {repo_url} \\\n" f"  {obs_project}")
            else:  # dnf
                repo_file = re.sub(r"[:.]+", "_", obs_project)
                print(f"rpm --import {repo_url}repodata/repomd.xml.key")
                print(
                    f"tee /etc/yum.repos.d/{repo_file}.repo << 'EOF'\n"
                    f"[{obs_project}]\n"
                    f"name={obs_project} - {repo_name}\n"
                    f"baseurl={repo_url}\n"
                    f"enabled=1\n"
                    f"gpgcheck=0\n"
                    f"EOF"
                )
            print()

        if pkg_mgr == "deb":
            print("apt update")
            print()
        elif pkg_mgr == "zypper":
            print("zypper --gpg-auto-import-keys refresh")
            print()
