import argparse
import concurrent.futures
import datetime
import re
import subprocess
import sys
import urllib.error
import xml.etree.ElementTree as ET
from collections.abc import Sequence
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
    _REPO_DIR,
    _col,
    _ENV_VAR_RE,
    _load_project_config_with_inheritance,
    _print_create,
    _print_ok,
    _print_pending,
    apply_env_substitution,
    auto_rootprj_env,
    build_project_meta,
    find_packages,
    find_projects,
    is_package,
    is_project,
    load_macros,
    load_project_yaml,
    load_yaml,
    load_yaml_with_env,
    parse_env_overrides,
    resolve_project_path,
)
from .cmd_profile import _load_profile, _load_profile_env
from .obs_api import (
    _decode_obs_response,
    _detect_obs_container_info,
    _extract_obs_managed_elements,
    _fetch_all_pkg_archs,
    _fetch_build_containerinfo,
    _fetch_obs_container_images,
    _fetch_obs_download_url,
    _fetch_obs_package_names,
    _fetch_root_project_managed_elements,
    _inject_obs_managed_elements,
    _obs_meta_to_yaml_debuginfo,
    _obs_meta_to_yaml_repos,
    _obs_project_exists,
    _read_project_release_source,
)
from .cmd_build import (
    _fetch_build_results,
    _fetch_pkg_versrel,
    _fetch_versrel_from_history,
)
from .services import _git_head_sha, _git_tag_for_sha

_YAML_FILENAMES = {"project.yaml", "package.yaml"}
_OBS_FILENAMES = {"_service", "_aggregate", "_link"}

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _extract_version_from_service(service_file: Path) -> "str | None":
    """Return the upstream version from an obs/_service file, or None."""
    try:
        text = service_file.read_text("utf-8")
        root_el = ET.fromstring(text)
    except (ET.ParseError, OSError):
        return None

    for svc in root_el.findall("service"):
        if svc.get("name") != "obs_scm":
            continue
        params = {p.get("name"): (p.text or "").strip() for p in svc.findall("param")}
        if params.get("filename") in ("debian", "rpm"):
            continue  # packaging service, not upstream

        version = params.get("version", "")
        versionformat = params.get("versionformat", "")
        revision = params.get("revision", "")

        if version and version != "_none_":
            return version
        if versionformat and versionformat != "@PARENT_TAG@":
            return versionformat
        if versionformat == "@PARENT_TAG@":
            pattern = params.get("versionrewrite-pattern", "")
            if pattern and revision:
                try:
                    m = re.match(pattern, revision)
                    if m and m.lastindex:
                        return m.group(1)
                except re.error:
                    pass
            # revision is a commit SHA — look up the tag that points to it
            if _SHA_RE.match(revision):
                url = params.get("url", "")
                if url and not _ENV_VAR_RE.search(url):
                    tag = _git_tag_for_sha(url, revision)
                    if tag is not None:
                        if pattern:
                            try:
                                m = re.match(pattern, tag)
                                if m and m.lastindex:
                                    return m.group(1)
                            except re.error:
                                pass
                        return tag
            if revision and not _ENV_VAR_RE.search(revision):
                return revision
            return None
        if revision and not _ENV_VAR_RE.search(revision):
            return revision
        return None

    return None


# Matches local aggregate project names: "${OBS_ROOTPRJ}:colon:notation"
_LOCAL_AGGREGATE_RE = re.compile(r"^\$\{OBS_ROOTPRJ\}:(.+)$")


def _resolve_aggregate_source(
    aggregate_file: Path,
) -> "tuple[str, str] | None":
    """Return (local_project_id, pkg_name) for the first resolvable local aggregate.

    Returns None for external aggregates or unparseable files.
    local_project_id uses colon notation (e.g. 'ppg:common:deps:build').
    """
    try:
        root_el = ET.fromstring(aggregate_file.read_text("utf-8"))
    except (ET.ParseError, OSError):
        return None

    for agg in root_el.findall("aggregate"):
        project_attr = (agg.get("project") or "").strip()
        pkg_el = agg.find("package")
        if pkg_el is None:
            continue
        pkg_name = (pkg_el.text or "").strip()
        if not pkg_name:
            continue

        m = _LOCAL_AGGREGATE_RE.match(project_attr)
        if not m:
            continue  # external aggregate

        local_project = m.group(1)
        target_path = REPO_ROOT.joinpath(*local_project.split(":")) / pkg_name
        if not target_path.is_dir():
            continue

        return local_project, pkg_name

    return None


def _follow_aggregate(aggregate_file: Path) -> "str | None":
    """Follow an _aggregate pointer to its source package and return its version.

    Only local aggregates (project="${OBS_ROOTPRJ}:local:path") are followed.
    External aggregates return None.
    """
    src = _resolve_aggregate_source(aggregate_file)
    if src is None:
        return None
    local_project, pkg_name = src
    service_file = (
        REPO_ROOT.joinpath(*local_project.split(":")) / pkg_name / "obs" / "_service"
    )
    if service_file.is_file():
        return _extract_version_from_service(service_file)
    return None


def _package_project_id(package_path: Path) -> str:
    """Return colon-notation project id for a package path (e.g. 'ppg:17')."""
    rel = package_path.parent.relative_to(REPO_ROOT)
    if str(rel) == ".":
        return ""
    return ":".join(rel.parts)


def _is_under_release_project(path: Path) -> bool:
    """True when *path* itself or any ancestor up to REPO_ROOT contains release.yaml."""
    p = path
    while p != REPO_ROOT:
        if (p / "release.yaml").is_file():
            return True
        if p.parent == p:
            break
        p = p.parent
    return False


def _apply_containerinfo(record: "dict[str, object]", ci: dict) -> None:
    """Enrich an image record in-place with data from a .containerinfo dict.

    Sets ``version`` from the containerinfo version field (already a versrel
    string such as '18.3-1.1').  Sets ``tags`` to the list of tag-only strings
    (the image-name prefix is stripped because ``image`` is a separate field).
    Removes the stale ``tag`` field (raw Dockerfile template value).
    """
    record["version"] = ci.get("version") or None
    raw_tags: list[str] = ci.get("tags") or []
    record["tags"] = [t.rsplit(":", 1)[1] if ":" in t else t for t in raw_tags]
    record.pop("tag", None)


def _fill_release_online_records(
    args: "argparse.Namespace",
    apiurl: str,
    scope_path: Path,
    records: "list[dict[str, object]]",
) -> None:
    """Populate *records* in-place for an OBS release project.

    Queries OBS for the package list and their built versrels.  Handles the
    main release project and each subproject directory (when args.recursive is True).
    """

    def _repo_arch_pairs_from_yaml(project_path: Path) -> list[tuple[str, str]]:
        """Return [(repo, arch), ...] from a local project.yaml as fallback."""
        data = load_project_yaml(project_path / "project.yaml")
        pairs: list[tuple[str, str]] = []
        for repo in data.get("repositories", []):
            name = repo.get("name", "")
            for arch in repo.get("archs", []):
                if name and arch:
                    pairs.append((name, arch))
        return pairs

    def _versrel(obs_proj: str, repo: str, arch: str, pkg: str) -> "str | None":
        """Try binary listing first (RPM/DEB), then build history (containers)."""
        v = _fetch_pkg_versrel(apiurl, obs_proj, repo, arch, pkg)
        if v is None:
            v = _fetch_versrel_from_history(apiurl, obs_proj, repo, arch, pkg)
        return v

    def _collect(proj_id: str, project_path: Path) -> None:
        obs_proj = f"{args.rootprj}:{proj_id}" if proj_id else args.rootprj
        pkg_names = sorted(_fetch_obs_package_names(apiurl, obs_proj))
        if not pkg_names:
            return
        pkg_archs = _fetch_all_pkg_archs(apiurl, obs_proj)
        fallback_pairs = _repo_arch_pairs_from_yaml(project_path)
        for pkg_name in pkg_names:
            repo_arch = pkg_archs.get(pkg_name)
            version: str | None = None
            if repo_arch:
                repo, arch = repo_arch
                version = _versrel(obs_proj, repo, arch, pkg_name)
            elif fallback_pairs:
                for repo, arch in fallback_pairs:
                    version = _versrel(obs_proj, repo, arch, pkg_name)
                    if version is not None:
                        break
            base: dict[str, object] = {"name": pkg_name, "project": proj_id}
            container_info = _detect_obs_container_info(apiurl, obs_proj, pkg_name)
            if container_info is not None:
                image, tag = container_info
                rec: dict[str, object] = {
                    **base,
                    "type": "image",
                    "image": image,
                    "tag": tag,
                    "version": version,
                }
                if repo_arch:
                    ci = _fetch_build_containerinfo(
                        apiurl, obs_proj, repo_arch[0], repo_arch[1], pkg_name
                    )
                    if ci is not None:
                        _apply_containerinfo(rec, ci)
                records.append(rec)
            else:
                records.append({**base, "type": "package", "version": version})

    _collect(args.project or "", scope_path)

    if getattr(args, "recursive", True):
        for sub_obs_id, sub_path in find_projects(scope_path, args.project or ""):
            if sub_path == scope_path:
                continue  # root already processed above
            _collect(sub_obs_id, sub_path)


def _detect_container_info(
    obs_path: Path,
) -> "tuple[str | None, str | None] | None":
    """Return (image_name, tag) if obs_path contains a container definition, else None.

    Checks for a Dockerfile first, then a *.kiwi file.
    Returns (None, None) when a container file is found but name/tag cannot be parsed.
    Returns None (not a tuple) when no container definition is found.
    """
    # --- Dockerfile ---
    dockerfile = obs_path / "Dockerfile"
    if dockerfile.is_file():
        for line in dockerfile.read_text("utf-8").splitlines():
            line = line.strip()
            if line.startswith("#!BuildTag:"):
                tag_value = line[len("#!BuildTag:") :].strip()
                if ":" in tag_value:
                    image, tag = tag_value.rsplit(":", 1)
                    return image.strip(), tag.strip()
                return tag_value, None
        return None, None  # Dockerfile present but no BuildTag

    # --- KIWI ---
    kiwi_files = sorted(obs_path.glob("*.kiwi"))
    if kiwi_files:
        try:
            root_el = ET.fromstring(kiwi_files[0].read_text("utf-8"))
            cc = root_el.find(".//containerconfig")
            if cc is not None:
                return cc.get("name"), cc.get("tag")
        except ET.ParseError:
            pass
        return None, None  # KIWI present but unparseable

    return None  # not a container image


def _validate_subproject_refs(root: Path) -> list[tuple[Path, str]]:
    """Check all subproject: references in project.yaml files under ``root``.

    Returns a list of (yaml_path, error_message) for each invalid reference.
    Only validates subproject: entries (relative to rootprj); project: entries
    reference external OBS projects and cannot be validated locally.
    """
    errors: list[tuple[Path, str]] = []
    for yaml_path in sorted(root.rglob("project.yaml")):
        config = load_project_yaml(yaml_path)
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
        root_config = load_project_yaml(REPO_ROOT / "project.yaml", env_vars)
        root_obs_name = root_config.get("name") or rootprj
        for obs_name, _ in find_projects(REPO_ROOT, root_obs_name):
            local_obs_project_names.add(obs_name)

    # Collect (yaml_path, resolved_project, resolved_repository) triples.
    triples: list[tuple[Path, str, str]] = []
    for yaml_path in sorted(root.rglob("project.yaml")):
        config = load_yaml_with_env(
            yaml_path, env_vars, macros=load_macros(yaml_path.parent)
        )
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
    service_files: Sequence[tuple[Path, "dict[str, str] | None"]],
) -> list[tuple[Path, str, str]]:
    """Check that every obs_scm revision in the given _service files exists remotely.

    *service_files* is a list of ``(path, env_vars)`` pairs — each file is
    substituted with its own env_vars before parsing.  This allows callers to
    pass files from multiple packages (each with package-specific variables) in
    a single call so that identical ``(url, revision)`` pairs are deduplicated
    globally rather than validated once per package.

    Revisions that still contain unresolved ``${VAR}`` tokens after substitution
    are silently skipped.

    Returns a list of (service_file, url, revision) for unresolvable revisions.
    """
    # Collect all (url, revision) pairs with the first service file that uses them.
    seen: dict[tuple[str, str], Path] = {}
    for svc_file, file_env in service_files:
        try:
            text = svc_file.read_text("utf-8")
            if file_env:
                text = apply_env_substitution(text, file_env, source=svc_file)
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
    # Auto-inject OBS_ROOTPRJ / OBS_CONTAINER_REGISTRY_ROOTPRJ when rootprj is known so
    # project.yaml entries that reference them validate without forcing
    # users to declare them in every profile.
    env_vars: dict[str, str] | None = None
    if args.profile:
        env_vars = _load_profile_env(args.profile)
    if args.env_overrides:
        overrides = parse_env_overrides(args.env_overrides)
        env_vars = {**(env_vars or {}), **overrides}
    if args.rootprj:
        env_vars = {**auto_rootprj_env(args.rootprj), **(env_vars or {})}

    ref_errors = _validate_subproject_refs(scan_root)
    env_errors = _validate_env_vars(scan_root, env_vars)
    service_files = sorted(scan_root.rglob("obs/_service"))
    scm_errors = _validate_obs_scm_revisions([(f, env_vars) for f in service_files])

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
    # `cmd_project_config` requires --rootprj (validated above) so always inject.
    env_vars = {**auto_rootprj_env(args.rootprj), **(env_vars or {})}

    # When not in offline mode, initialise osc so we can fetch live project meta.
    apiurl: str | None = None
    if not getattr(args, "offline", False):
        if args.apiurl:
            osc.conf.get_config(override_apiurl=args.apiurl)
            apiurl = osc.conf.config["apiurl"]
        elif args.profile:
            profile = _load_profile(args.profile)
            raw_apiurl = profile.get("apiurl", "")
            if raw_apiurl:
                osc.conf.get_config(override_apiurl=raw_apiurl)
                apiurl = osc.conf.config["apiurl"]

    # Always resolve the root OBS project name — needed both for the project
    # list and for inheriting person/group into new subprojects.
    root_config = load_project_yaml(REPO_ROOT / "project.yaml")
    root_obs_name = root_config.get("name") or args.rootprj

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
            publish=project_config.get("publish"),
            build=project_config.get("build"),
        )
        project_config_str = (project_config.get("project-config") or "").strip()

        # When connected to OBS, merge in the live OBS-managed elements so the
        # output reflects what sync would actually upload.
        if apiurl:
            try:
                current_bytes = _decode_obs_response(
                    osc.core.show_project_meta(apiurl, obs_project_name)
                ).encode()
                managed = _extract_obs_managed_elements(current_bytes)
                if managed:
                    meta = _inject_obs_managed_elements(meta, managed)
            except Exception:
                # Project not on OBS yet.  For subprojects, inherit person/group
                # from the root project — matching what _create_project_skeleton
                # does when it first creates the project.
                if obs_project_name != root_obs_name:
                    inherited = _fetch_root_project_managed_elements(
                        apiurl, root_obs_name
                    )
                    meta = _inject_obs_managed_elements(meta, inherited)

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
    """Return 'deb', 'zypper', 'dnf', or 'container' based on the OBS repository name."""
    if repo_name == "images":
        return "container"
    if any(repo_name.startswith(p) for p in _DEB_REPO_PREFIXES):
        return "deb"
    if any(repo_name.startswith(p) for p in _ZYPPER_REPO_PREFIXES):
        return "zypper"
    return "dnf"


def _container_registry_prefix(
    obs_project: str, rootprj: str, env_vars: "dict[str, str] | None"
) -> str:
    """Return the container registry base URL for an OBS project's images repo.

    Example: isv:percona:ppg:releases:18:containers:ubi9 →
      registry.opensuse.org/isv/percona/ppg/releases/18/containers/ubi9/images
    """
    registry_rootprj = (env_vars or {}).get(
        "OBS_CONTAINER_REGISTRY_ROOTPRJ",
        rootprj.replace(":", "/").lower(),
    )
    rel = (
        obs_project[len(rootprj) + 1 :]
        if obs_project.startswith(rootprj + ":")
        else obs_project
    )
    return f"registry.opensuse.org/{registry_rootprj}/{rel.replace(':', '/')}/images"


def _local_container_images(project_path: Path) -> "list[tuple[str, list[str]]]":
    """Return [(image_name, [stable_tags]), ...] from Dockerfiles in direct-child packages.

    Stable tags are #!BuildTag: values with no template variables (< or >).
    """
    results: list[tuple[str, list[str]]] = []
    for child in sorted(project_path.iterdir()):
        dockerfile = child / "obs" / "Dockerfile"
        if not child.is_dir() or not dockerfile.is_file():
            continue
        image_name: str | None = None
        stable_tags: list[str] = []
        for line in dockerfile.read_text("utf-8").splitlines():
            line = line.strip()
            if not line.startswith("#!BuildTag:"):
                continue
            tag_value = line[len("#!BuildTag:") :].strip()
            if ":" in tag_value:
                img, tag = tag_value.rsplit(":", 1)
                image_name = img.strip()
                if "<" not in tag and ">" not in tag:
                    stable_tags.append(tag.strip())
            elif not image_name:
                image_name = tag_value
        if image_name and stable_tags:
            results.append((image_name, stable_tags))
    return results


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
    if args.rootprj:
        env_vars = {**auto_rootprj_env(args.rootprj), **(env_vars or {})}

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
        root_config = load_project_yaml(REPO_ROOT / "project.yaml")
        scope_obs_name = root_config.get("name") or args.rootprj

    all_projects = list(find_projects(scope_path, scope_obs_name))
    is_release = _is_under_release_project(scope_path)

    # Filter: skip opt-out projects and projects with no direct packages.
    # Release projects have no local packages (binaries live on OBS), so skip
    # the _has_direct_packages check for them.
    def _has_direct_packages(project_path: Path) -> bool:
        return any(c.is_dir() and is_package(c) for c in project_path.iterdir())

    projects = [
        (obs_name, proj_path)
        for obs_name, proj_path in all_projects
        if load_project_yaml(proj_path / "project.yaml").get("publish") is not False
        and (
            (proj_path / "project.yaml").is_file()
            if is_release
            else _has_direct_packages(proj_path)
        )
    ]

    if not projects:
        raise SystemExit("error: no installable projects found in scope")

    # Build repo_name -> [obs_project_name, ...] mapping and a path lookup.
    repo_entries: dict[str, list[str]] = {}
    obs_name_to_path: dict[str, Path] = {}
    for obs_project_name, project_path in projects:
        obs_name_to_path[obs_project_name] = project_path
        config = _load_project_config_with_inheritance(project_path, env_vars)
        publish_config = config.get("publish")
        for repo in config.get("repositories", []):
            repo_name = repo.get("name", "")
            if not repo_name:
                continue
            if args.repo and repo_name != args.repo:
                continue
            if (
                isinstance(publish_config, dict)
                and publish_config.get(repo_name) is False
            ):
                continue
            repo_entries.setdefault(repo_name, [])
            if obs_project_name not in repo_entries[repo_name]:
                repo_entries[repo_name].append(obs_project_name)

    if not repo_entries:
        if args.repo:
            raise SystemExit(f"error: repository '{args.repo}' not found in scope")
        raise SystemExit("error: no repositories found in scope")

    markdown = getattr(args, "markdown", False)
    if markdown:
        print("# Repository Installation Instructions\n")

    sep = _col(_DIM, "─" * 72)
    ordered_repos = sorted(
        repo_entries, key=lambda r: (1 if _repo_pkg_manager(r) == "container" else 0, r)
    )
    for repo_name in ordered_repos:
        if markdown:
            heading = "Container Images" if repo_name == "images" else repo_name
            print(f"\n### {heading}\n")
        else:
            print(sep)
            print(_col(_BOLD, repo_name))
            print()
        pkg_mgr = _repo_pkg_manager(repo_name)
        proj_list = repo_entries[repo_name]

        for i, obs_project in enumerate(proj_list):
            is_last = i == len(proj_list) - 1

            if markdown:
                print(f"**`{obs_project}`**\n")
            else:
                print(f"# {obs_project}")

            if pkg_mgr == "container":
                registry_prefix = _container_registry_prefix(
                    obs_project, args.rootprj, env_vars
                )
                proj_path = obs_name_to_path.get(obs_project)
                images = _local_container_images(proj_path) if proj_path else []
                if not images:
                    images = _fetch_obs_container_images(apiurl, obs_project)
                if markdown:
                    for image_name, stable_tags in images:
                        print(f"**`{image_name}`**\n\n```bash")
                        for tag in stable_tags:
                            print(f"docker pull {registry_prefix}/{image_name}:{tag}")
                        print("```\n")
                    if not images:
                        print(
                            f"```bash\ndocker pull {registry_prefix}/<image>:<tag>\n```\n"
                        )
                else:
                    for image_name, stable_tags in images:
                        for tag in stable_tags:
                            print(f"docker pull {registry_prefix}/{image_name}:{tag}")
                    if not images:
                        print(f"docker pull {registry_prefix}/<image>:<tag>")
                    print()
            else:
                url_path = _obs_project_url_path(obs_project)
                repo_url = f"{download_url}/{url_path}/{repo_name}/"

                if markdown:
                    print("```bash")

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
                    print(
                        f"zypper addrepo \\\n" f"  {repo_url} \\\n" f"  {obs_project}"
                    )
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

                if markdown and is_last:
                    if pkg_mgr == "deb":
                        print("apt update")
                    elif pkg_mgr == "zypper":
                        print("zypper --gpg-auto-import-keys refresh")

                if markdown:
                    print("```\n")
                else:
                    print()

        if not markdown:
            if pkg_mgr == "deb":
                print("apt update")
                print()
            elif pkg_mgr == "zypper":
                print("zypper --gpg-auto-import-keys refresh")
                print()


def cmd_project_versions(args) -> None:
    """List all packages with their upstream version (YAML to stdout)."""
    package_name: str | None = getattr(args, "package", None)

    if package_name and not args.project:
        raise SystemExit(
            "error: a project argument is required when specifying a package"
        )

    if args.project:
        scope_path = resolve_project_path(args.project)
        if not scope_path.is_dir():
            raise SystemExit(
                f"error: project '{args.project}' not found "
                f"(expected {scope_path.relative_to(REPO_ROOT.parent)})"
            )
        if not is_project(scope_path):
            raise SystemExit(f"error: '{args.project}' is a package, not a project")
    else:
        scope_path = REPO_ROOT

    is_release = _is_under_release_project(scope_path)

    if package_name:
        package_path = scope_path / package_name
        if not package_path.is_dir() or not is_package(package_path):
            raise SystemExit(
                f"error: package '{package_name}' not found under '{args.project}'"
            )
        package_paths = [package_path]
    else:
        package_paths = (
            []
            if is_release
            else [p for _, p in find_packages(scope_path, "", recursive=args.recursive)]
        )

    records: list[dict[str, object]] = []
    for package_path in package_paths:
        obs_path = package_path / "obs"
        container_info = _detect_container_info(obs_path) if obs_path.is_dir() else None
        base = {"name": package_path.name, "project": _package_project_id(package_path)}
        if container_info is not None:
            image, tag = container_info
            records.append({**base, "type": "image", "image": image, "tag": tag})
        else:
            service_file = obs_path / "_service"
            aggregate_file = obs_path / "_aggregate"
            version: str | None = None
            if service_file.is_file():
                version = _extract_version_from_service(service_file)
            elif aggregate_file.is_file():
                version = _follow_aggregate(aggregate_file)
                agg_src = _resolve_aggregate_source(aggregate_file)
                if agg_src:
                    base["_agg_src_project"] = agg_src[0]
                    base["_agg_src_pkg"] = agg_src[1]
            records.append({**base, "type": "package", "version": version})

    if getattr(args, "online", False):
        if not args.apiurl or not args.rootprj:
            raise SystemExit(
                "error: --online requires an OBS connection; "
                "supply -P/--profile or both -A/--apiurl and -R/--rootprj"
            )
        osc.conf.get_config(override_apiurl=args.apiurl)
        apiurl = osc.conf.config["apiurl"]

        if is_release and not package_name:
            # Release projects have no local package trees; fetch list and
            # versions directly from OBS (builds are disabled but released
            # binaries are still accessible via the build binary endpoint).
            _fill_release_online_records(args, apiurl, scope_path, records)
        else:
            # Group all records by OBS project to batch _fetch_build_results calls.
            # Aggregate packages are looked up in their source project, not the
            # aggregate project, because the actual build happens in the source.
            obs_project_records: dict[str, list[tuple[dict[str, object], str]]] = {}
            for record in records:
                if "_agg_src_project" in record:
                    src_proj = str(record["_agg_src_project"])
                    src_pkg = str(record["_agg_src_pkg"])
                    obs_proj = f"{args.rootprj}:{src_proj}"
                else:
                    project_id = str(record["project"])
                    obs_proj = (
                        f"{args.rootprj}:{project_id}" if project_id else args.rootprj
                    )
                    src_pkg = str(record["name"])
                obs_project_records.setdefault(obs_proj, []).append((record, src_pkg))

            for obs_proj, pkg_record_pairs in obs_project_records.items():
                _, succeeded_archs = _fetch_build_results(apiurl, obs_proj)
                for record, pkg_name in pkg_record_pairs:
                    repo_map = succeeded_archs.get(pkg_name)
                    if not repo_map:
                        record["version"] = None
                        continue
                    repo, (arch, _) = next(iter(sorted(repo_map.items())))
                    if record["type"] == "package":
                        record["version"] = _fetch_pkg_versrel(
                            apiurl, obs_proj, repo, arch, pkg_name
                        )
                    else:  # image
                        ci = _fetch_build_containerinfo(
                            apiurl, obs_proj, repo, arch, pkg_name
                        )
                        if ci is not None:
                            _apply_containerinfo(record, ci)
                        else:
                            record["version"] = _fetch_versrel_from_history(
                                apiurl, obs_proj, repo, arch, pkg_name
                            )

    for record in records:
        record.pop("_agg_src_project", None)
        record.pop("_agg_src_pkg", None)

    if getattr(args, "markdown", False):
        packages = [r for r in records if r["type"] == "package"]
        images = [r for r in records if r["type"] == "image"]
        md_lines: list[str] = []

        if packages:
            md_lines += [
                "## Packages",
                "",
                "| Package | Project | Version |",
                "| ------- | ------- | ------- |",
            ]
            for r in packages:
                ver = r.get("version") or "(none)"
                md_lines.append(f"| {r['name']} | {r['project']} | {ver} |")
            md_lines.append("")

        if images:
            online = getattr(args, "online", False)
            if online:
                md_lines += [
                    "## Container Images",
                    "",
                    "| Package | Project | Image | Version | Tags |",
                    "| ------- | ------- | ----- | ------- | ---- |",
                ]
                for r in images:
                    img = r.get("image") or "(none)"
                    ver = r.get("version") or "(none)"
                    tags: list = r.get("tags") or []  # type: ignore[assignment]
                    if tags:
                        tags_str = " ".join(f"`{t}`" for t in tags)
                    else:
                        fallback = r.get("tag")
                        tags_str = f"`{fallback}`" if fallback else "(none)"
                    md_lines.append(
                        f"| {r['name']} | {r['project']} | {img} | {ver} | {tags_str} |"
                    )
            else:
                md_lines += [
                    "## Container Images",
                    "",
                    "| Package | Project | Image | Tag |",
                    "| ------- | ------- | ----- | --- |",
                ]
                for r in images:
                    img = r.get("image") or "(none)"
                    tag = r.get("tag") or "(none)"
                    md_lines.append(f"| {r['name']} | {r['project']} | {img} | {tag} |")
            md_lines.append("")

        print("\n".join(md_lines), end="")
    else:
        print(yaml.dump(records, default_flow_style=False, allow_unicode=True), end="")


def _rewrite_subproject_paths(
    repos: list[dict],
    source_project_id: str,
    release_project_id: str,
    skip_subproject: str | None = None,
) -> list[dict]:
    """Rewrite subproject: path entries for a release subproject yaml.

    Rules applied to each path entry:
      subproject == source_project_id             →  single entry: release_project_id
      subproject starts with source_project_id:   →  replace prefix with release_project_id;
                                                       skip if the result equals skip_subproject
      everything else (project:, external)        →  unchanged

    skip_subproject: if set, any rewritten subproject entry that resolves to this
    value is dropped.  Used to remove self-referencing paths from release subprojects
    (e.g. containers referencing itself).
    """
    result = []
    for repo in repos:
        new_paths = []
        for path_entry in repo.get("paths", []):
            subprj = path_entry.get("subproject")
            if subprj is not None:
                if subprj == source_project_id:
                    repo_name = path_entry.get("repository")
                    new_paths.append(
                        {"subproject": release_project_id, "repository": repo_name}
                    )
                    continue
                elif subprj.startswith(source_project_id + ":"):
                    tail = subprj[len(source_project_id) :]
                    rewritten = release_project_id + tail
                    if skip_subproject and rewritten == skip_subproject:
                        continue
                    path_entry = {**path_entry, "subproject": rewritten}
            new_paths.append(path_entry)
        result.append({**repo, "paths": new_paths})
    return result


def _extract_upstream_info_from_service(
    service_file: Path,
) -> "tuple[str, str] | None":
    """Return (url, revision) from the upstream obs_scm in an _service file, or None."""
    try:
        text = service_file.read_text("utf-8")
        root_el = ET.fromstring(text)
    except (ET.ParseError, OSError):
        return None
    for svc in root_el.findall("service"):
        if svc.get("name") != "obs_scm":
            continue
        params = {p.get("name"): (p.text or "").strip() for p in svc.findall("param")}
        if params.get("filename") in ("debian", "rpm"):
            continue
        if params.get("subdir") in ("debian", "rpm"):
            continue
        url = params.get("url", "")
        revision = params.get("revision", "")
        if url:
            return url, revision
    return None


def _build_upstream_release_url(
    url: str, revision: str, pkg_version: str
) -> "str | None":
    """Build an upstream release URL from obs_scm url/revision."""
    if not url:
        return None
    if "github.com" in url:
        clean = url.rstrip("/")
        if clean.endswith(".git"):
            clean = clean[:-4]
        if revision:
            return f"{clean}/releases/tag/{revision}"
        return clean
    if "git.postgresql.org" in url:
        parts = pkg_version.split(".")
        if len(parts) >= 2:
            return f"https://www.postgresql.org/docs/release/{parts[0]}.{parts[1]}/"
    return url


def _fetch_project_pkg_versions(apiurl: str, obs_project: str) -> "dict[str, str]":
    """Return {pkg_name: versrel} for all packages in obs_project."""
    pkg_names = sorted(_fetch_obs_package_names(apiurl, obs_project))
    if not pkg_names:
        return {}
    pkg_archs = _fetch_all_pkg_archs(apiurl, obs_project)
    result: dict[str, str] = {}
    for pkg in pkg_names:
        repo_arch = pkg_archs.get(pkg)
        if not repo_arch:
            continue
        repo, arch = repo_arch
        versrel = _fetch_pkg_versrel(apiurl, obs_project, repo, arch, pkg)
        if versrel:
            result[pkg] = versrel
    return result


def _build_changelog_section(
    release_id: str,
    source_versions: "dict[str, str]",
    release_versions: "dict[str, str] | None",
    source_path: Path,
) -> str:
    """Build a keep-a-changelog section for a release."""
    today = datetime.date.today().isoformat()
    added: list[str] = []
    changed: list[str] = []
    removed: list[str] = []

    all_pkgs = set(source_versions.keys())
    if release_versions:
        all_pkgs |= set(release_versions.keys())

    for pkg in sorted(all_pkgs):
        src_ver = source_versions.get(pkg)
        rel_ver = release_versions.get(pkg) if release_versions else None

        if src_ver is None:
            ver = rel_ver.split("-")[0] if rel_ver else "?"
            removed.append(f"- {pkg}: removed (was {ver})")
            continue

        pkg_version = src_ver.split("-")[0]

        url_str = ""
        service_file = source_path / pkg / "obs" / "_service"
        if service_file.is_file():
            info = _extract_upstream_info_from_service(service_file)
            if info:
                upstream_url, revision = info
                release_url = _build_upstream_release_url(
                    upstream_url, revision, pkg_version
                )
                if release_url:
                    url_str = f" ({release_url})"

        if release_versions is None or rel_ver is None:
            added.append(f"- {pkg}: add upstream version {pkg_version}{url_str}")
        elif src_ver.split("-")[0] != rel_ver.split("-")[0]:
            changed.append(f"- {pkg}: update upstream version {pkg_version}{url_str}")

    if not source_versions:
        todo = "<!-- TODO: fill in manually -->"
        added = [todo]
        changed = [todo]

    lines: list[str] = [f"## [{release_id}] - {today}", ""]
    lines += ["### Added"] + added + [""]
    lines += ["### Changed"] + changed + [""]
    lines += ["### Fixed", ""]

    return "\n".join(lines)


_CHANGELOG_HEADER = (
    "# Changelog\n\n"
    "All notable changes to this project will be documented in this file.\n\n"
    "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).\n\n"
)


def cmd_project_release(args: argparse.Namespace) -> None:
    """Create or update a release: release.yaml, CHANGELOG.md, project.yaml, commit, and open a PR."""
    product = args.project.split(":")[0]
    major = args.project.split(":")[-1]

    source_path = resolve_project_path(args.project)
    if not source_path.is_dir():
        raise SystemExit(
            f"error: source project directory does not exist: {source_path}"
        )

    if not args.rootprj:
        raise SystemExit(
            "error: rootprj is required for 'project release': "
            "supply -R/--rootprj or -P/--profile"
        )
    osc.conf.get_config(override_apiurl=args.apiurl)
    apiurl: str = osc.conf.config["apiurl"]

    release_name: str = args.release_name or major
    release_dir = REPO_ROOT / product / "releases" / release_name
    release_project = f"{product}:releases:{release_name}"
    source_obs_project = f"{args.rootprj}:{args.project}"
    release_obs_project = f"{args.rootprj}:{release_project}"

    is_first_release = not release_dir.is_dir()

    # Load existing release list if updating.
    existing_releases: list[str] = []
    if not is_first_release:
        existing_data = load_yaml(release_dir / "release.yaml")
        raw = existing_data.get("releases")
        if isinstance(raw, list):
            existing_releases = [str(r) for r in raw]
        elif existing_data.get("revision"):
            existing_releases = [str(existing_data["revision"])]

    # Auto-derive release-id from OBS if not provided.
    release_id: str = args.release_id or ""
    if not release_id:
        pg_pkg = f"percona-postgresql{major}"
        pkg_archs = _fetch_all_pkg_archs(apiurl, source_obs_project)
        repo_arch = pkg_archs.get(pg_pkg)
        if not repo_arch:
            raise SystemExit(
                f"error: package {pg_pkg} not found in {source_obs_project}; "
                "use --release-id to specify manually"
            )
        repo, arch = repo_arch
        versrel = _fetch_pkg_versrel(apiurl, source_obs_project, repo, arch, pg_pkg)
        if not versrel:
            raise SystemExit(
                f"error: could not get built version of {pg_pkg} from {source_obs_project}; "
                "use --release-id to specify manually"
            )
        ver_parts = versrel.split("-")[0].split(".")
        major_minor = ".".join(ver_parts[:2])
        matching_count = sum(1 for t in existing_releases if f"/{major_minor}-" in t)
        release_id = f"{major_minor}-{matching_count + 1}"

    tag = f"{product}/{release_id}"

    if tag in existing_releases:
        raise SystemExit(f"error: release tag {tag} is already present in release.yaml")

    # Fetch source project topology from OBS.
    raw_meta = _decode_obs_response(
        osc.core.show_project_meta(apiurl, source_obs_project)
    )
    meta_root = ET.fromstring(raw_meta)
    source_repo_elems, _ = _read_project_release_source(apiurl, source_obs_project)
    source_repos = _obs_meta_to_yaml_repos(source_repo_elems, args.rootprj)
    source_debuginfo = _obs_meta_to_yaml_debuginfo(meta_root)
    try:
        source_prjconf = _decode_obs_response(
            osc.core.show_project_conf(apiurl, source_obs_project)
        ).strip()
    except urllib.error.HTTPError:
        source_prjconf = ""

    # Build CHANGELOG section by diffing source vs release OBS package versions.
    _print_pending("fetching package versions for CHANGELOG")
    source_versions = _fetch_project_pkg_versions(apiurl, source_obs_project)
    release_versions: dict[str, str] | None = None
    if not is_first_release and _obs_project_exists(apiurl, release_obs_project):
        release_versions = _fetch_project_pkg_versions(apiurl, release_obs_project)
    changelog_section = _build_changelog_section(
        release_id, source_versions, release_versions, source_path
    )

    # Build release.yaml content.
    new_releases_list = existing_releases + [tag]
    release_data: dict = {
        "repository": "${PERCONA_OBS_PACKAGING_REPO}",
        "project": args.project,
        "releases": new_releases_list,
    }

    # Build project.yaml for the release directory.
    project_data: dict = {
        "title": f"{product} releases {release_name}",
        "description": (
            f"Release project for {args.project} (OBS project {release_project}).\n"
            "Binaries are populated by osc release and builds are disabled.\n"
            "This project is read-only — do not add or edit packages directly.\n"
        ),
        "build": False,
        "repositories": source_repos,
    }
    if source_debuginfo:
        project_data["debuginfo"] = source_debuginfo
    if source_prjconf:
        project_data["project-config"] = source_prjconf

    if is_first_release:
        commit_msg = f"Release {release_project} ({release_id})"
    else:
        commit_msg = f"Update release {release_project} ({release_id})"

    release_counter = release_id.rsplit("-", 1)[-1]

    macros_file = source_path / "macros.yaml"
    _macros_text = ""
    _ppg_release_in_macros = False
    if macros_file.is_file():
        _macros_text = macros_file.read_text("utf-8")
        _ppg_release_in_macros = bool(
            re.search(r"^- PPG_RELEASE:\s*\S+", _macros_text, re.MULTILINE)
        )

    # Preview and confirm.
    print(f"{'First' if is_first_release else 'Update'} release: {release_project}")
    print(f"  Tag:         {tag}")
    print(f"  Directory:   {release_dir.relative_to(_REPO_DIR)}/")
    if _ppg_release_in_macros:
        print(f"  macros.yaml: PPG_RELEASE → {release_counter}")
    print()
    print("  CHANGELOG section preview:")
    for line in changelog_section.splitlines()[:10]:
        print(f"    {line}")
    if changelog_section.count("\n") > 10:
        print("    ...")
    print()
    print(f"  Commit message: {commit_msg}")
    print()

    try:
        answer = (
            input(
                "Create release? [y/N] "
                if is_first_release
                else "Update release? [y/N] "
            )
            .strip()
            .lower()
        )
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit("Aborted.")
    if answer not in ("y", "yes"):
        raise SystemExit("Aborted.")

    # Write files.
    committed_paths: list[str] = []

    if _ppg_release_in_macros:
        new_text, _ = re.subn(
            r"^(- PPG_RELEASE:)\s*\S+",
            rf"\g<1> {release_counter}",
            _macros_text,
            count=1,
            flags=re.MULTILINE,
        )
        macros_file.write_text(new_text, "utf-8")
        _print_create(str(macros_file.relative_to(_REPO_DIR)))
        committed_paths.append(str(macros_file.relative_to(_REPO_DIR)))

    if is_first_release:
        release_dir.mkdir(parents=True, exist_ok=True)

        release_file = release_dir / "release.yaml"
        with release_file.open("w") as f:
            yaml.dump(release_data, f, default_flow_style=False, allow_unicode=True)
        _print_create(str(release_file.relative_to(_REPO_DIR)))
        committed_paths.append(str(release_file.relative_to(_REPO_DIR)))

        project_file = release_dir / "project.yaml"
        with project_file.open("w") as f:
            yaml.dump(project_data, f, default_flow_style=False, allow_unicode=True)
        _print_create(str(project_file.relative_to(_REPO_DIR)))
        committed_paths.append(str(project_file.relative_to(_REPO_DIR)))

        changelog_file = release_dir / "CHANGELOG.md"
        changelog_file.write_text(
            _CHANGELOG_HEADER + changelog_section + "\n", encoding="utf-8"
        )
        _print_create(str(changelog_file.relative_to(_REPO_DIR)))
        committed_paths.append(str(changelog_file.relative_to(_REPO_DIR)))

        # Walk source subprojects and generate release subproject project.yaml files.
        for sub_obs_id, sub_path in find_projects(source_path, args.project):
            if sub_obs_id == args.project:
                continue
            if not (sub_path / "project.yaml").is_file():
                continue  # intermediate directory, not a real OBS project
            subproject_name = sub_obs_id[len(args.project) + 1 :]
            source_sub_config = load_project_yaml(sub_path / "project.yaml")
            rewritten_repos = _rewrite_subproject_paths(
                source_sub_config.get("repositories", []),
                args.project,
                release_project,
                skip_subproject=f"{release_project}:{subproject_name}",
            )
            sub_data: dict = {
                "title": f"{product} releases {release_name} — {subproject_name}",
                "description": (
                    f"{subproject_name.capitalize()} subproject for {release_project}.\n"
                    "Builds are disabled; binaries are copied via osc release.\n"
                ),
                "build": False,
                "repositories": rewritten_repos,
            }
            for key in ("debuginfo", "publish", "project-config"):
                if key in source_sub_config:
                    sub_data[key] = source_sub_config[key]
            release_sub_dir = release_dir / Path(*subproject_name.split(":"))
            release_sub_dir.mkdir(parents=True, exist_ok=True)
            release_sub_file = release_sub_dir / "project.yaml"
            with release_sub_file.open("w") as f:
                yaml.dump(sub_data, f, default_flow_style=False, allow_unicode=True)
            _print_create(str(release_sub_file.relative_to(_REPO_DIR)))
            committed_paths.append(str(release_sub_file.relative_to(_REPO_DIR)))

    else:
        # Update path: append tag to releases list and prepend changelog section.
        release_file = release_dir / "release.yaml"
        with release_file.open("w") as f:
            yaml.dump(release_data, f, default_flow_style=False, allow_unicode=True)
        _print_create(str(release_file.relative_to(_REPO_DIR)))
        committed_paths.append(str(release_file.relative_to(_REPO_DIR)))

        changelog_file = release_dir / "CHANGELOG.md"
        if changelog_file.is_file():
            existing_changelog = changelog_file.read_text("utf-8")
            m = re.search(r"\n(## \[)", existing_changelog)
            if m:
                insert_pos = m.start() + 1
                new_content = (
                    existing_changelog[:insert_pos]
                    + changelog_section
                    + "\n"
                    + existing_changelog[insert_pos:]
                )
            else:
                new_content = (
                    existing_changelog.rstrip() + "\n\n" + changelog_section + "\n"
                )
        else:
            new_content = _CHANGELOG_HEADER + changelog_section + "\n"
        changelog_file.write_text(new_content, encoding="utf-8")
        _print_create(str(changelog_file.relative_to(_REPO_DIR)))
        committed_paths.append(str(changelog_file.relative_to(_REPO_DIR)))

    # Commit.
    subprocess.run(["git", "add", "--", *committed_paths], cwd=_REPO_DIR, check=True)
    subprocess.run(
        ["git", "commit", "-s", "-m", commit_msg, "--", *committed_paths],
        cwd=_REPO_DIR,
        check=True,
    )
    _print_ok(commit_msg)
