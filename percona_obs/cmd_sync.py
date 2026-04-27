import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import osc.conf
import osc.core

from .cmd_profile import _load_profile, _load_profile_env_strings, _load_profile_env
from .cmd_project import (
    _validate_obs_scm_revisions,
    _validate_project_path_refs,
    _validate_subproject_refs,
)
from .common import (
    REPO_ROOT,
    _REPO_DIR,
    _load_project_config_with_inheritance,
    _print_action,
    _print_aggregate,
    _print_ok,
    _print_pending,
    _print_remove,
    _print_same,
    _print_update,
    apply_env_substitution,
    find_projects,
    is_package,
    load_yaml,
    load_yaml_with_env,
    logger,
    parse_env_overrides,
    resolve_project_path,
)
from .git_utils import (
    _generate_sync_message,
    _has_package_changes_since,
)
from .obs_api import (
    _add_release_targets,
    _apply_package_config,
    _apply_project_config,
    _disable_package_builds,
    _create_project_skeleton,
    _copy_project_conf,
    _create_release_project,
    _create_update_subproject,
    check_project_config_changed,
    _delete_obs_package,
    _delete_obs_project,
    _fetch_combined_depinfo,
    _fetch_obs_file_md5s,
    _fetch_obs_package_latest_comment,
    _fetch_obs_package_meaningful_comment,
    _fetch_obs_package_names,
    _fetch_obs_project_repository_names,
    _fetch_obs_subproject_names,
    _obs_project_exists,
    _read_project_release_source,
    _remove_release_targets,
    _fetch_releasetarget_project,
    _upload_obs_files,
)
from .services import (
    _copy_local_packaging,
    _has_runnable_services,
    _run_local_services,
)
from .targets import _iter_project_chain, _resolve_targets, is_dockerfile_image

# Matches the standard sync commit message: sync: <branch>@<sha> (<detail>)
_SYNC_MSG_RE = re.compile(r"^sync: [^@]+@([0-9a-f]+) \((.+)\)$")
# Matches a branch aggregate message: branch: <profile> (<obs_project>/<package>)
# Group 1 = profile name, group 2 = source OBS project.
_BRANCH_MSG_RE = re.compile(r"^branch: (\S+) \((.+)/[^/]+\)$")


_OBS_SUBSTITUTABLE = {"_service", "_aggregate", "_link"}

# Resolve osc relative to the running Python so it works inside a venv even
# when the venv's bin/ directory is not on PATH (e.g. CI runners).
_OSC_BIN = os.path.join(os.path.dirname(sys.executable), "osc")

# Stem of the OBS sub-project that holds per-PR build environments.
# This sub-project is managed exclusively by CI workflows and must never be
# deleted by orphan cleanup or created by sync push.
_PR_SUBPROJECT_STEM = "PR"


def _is_pr_managed_project(obs_project: str, rootprj: str) -> bool:
    """Return True if obs_project is the CI-managed PR sub-project or any child of it.

    These projects are created and destroyed by CI workflows and must be invisible
    to the orphan-deletion logic in sync push.
    """
    pr_root = f"{rootprj}:{_PR_SUBPROJECT_STEM}"
    return obs_project == pr_root or obs_project.startswith(pr_root + ":")


def _copy_with_env_subst(
    src: Path, dst_dir: Path, env_vars: dict[str, str] | None
) -> None:
    """Copy src into dst_dir, substituting ${VAR} tokens for substitutable obs files."""
    if env_vars and src.name in _OBS_SUBSTITUTABLE:
        text = apply_env_substitution(src.read_text("utf-8"), env_vars, source=src)
        (dst_dir / src.name).write_text(text, "utf-8")
    else:
        shutil.copy2(src, dst_dir / src.name)


def _rewrite_aggregate_for_branch(
    content: str,
    rootprj: str,
    branch_rootprj: str,
    active_projects: "set[str] | None",
) -> str:
    """Rewrite _aggregate XML so references to inactive PR subprojects point to branch_rootprj.

    When a package in a PR project aggregates from a sibling subproject that
    was NOT promoted (not in active_projects), the sibling doesn't exist on
    OBS under rootprj.  Redirect those aggregate references to branch_rootprj
    so OBS pulls the binaries from the production counterpart instead.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return content
    changed = False
    for agg in root.findall("aggregate"):
        proj = agg.get("project", "")
        if proj == rootprj or proj.startswith(rootprj + ":"):
            if active_projects is None or proj not in active_projects:
                suffix = proj[len(rootprj) :]  # "" or ":sub:project"
                new_proj = branch_rootprj + suffix
                agg.set("project", new_proj)
                changed = True
    if not changed:
        return content
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _rewrite_aggregates_in_dir(
    directory: Path,
    rootprj: str,
    branch_rootprj: str,
    active_projects: "set[str] | None",
) -> None:
    """Rewrite all _aggregate files in directory in-place for branch mode."""
    agg_file = directory / "_aggregate"
    if agg_file.is_file():
        original = agg_file.read_text("utf-8")
        rewritten = _rewrite_aggregate_for_branch(
            original, rootprj, branch_rootprj, active_projects
        )
        if rewritten != original:
            agg_file.write_text(rewritten, "utf-8")


def _pkg_env_vars(package_path: Path) -> dict[str, str]:
    """Per-package env vars auto-injected into ${VAR} substitution.

    DEBIAN_PACKAGE_DIRECTORY — path to the package's debian/ subdir relative
    to the repo root (e.g. root/ppg/17/percona-haproxy/debian).
    RPM_PACKAGE_DIRECTORY    — same for rpm/.
    """
    rel = package_path.relative_to(REPO_ROOT.parent)
    return {
        "DEBIAN_PACKAGE_DIRECTORY": (rel / "debian").as_posix(),
        "RPM_PACKAGE_DIRECTORY": (rel / "rpm").as_posix(),
    }


def _content_matches_branch(
    apiurl: str,
    branch_project: str,
    package_name: str,
    obs_dir: Path,
    branch_env_vars: dict[str, str] | None = None,
    env_vars: dict[str, str] | None = None,
) -> bool:
    """Return True if what sync push would upload matches what is in branch_project on OBS.

    Builds the same combined directory that sync push would produce — obs/ files
    plus service artifacts plus packaging files — then compares it bidirectionally
    against the files currently on OBS.

    For packages with runnable services the services are executed locally (with
    caching) to obtain tarballs, obsinfo, and packaging artifacts.  For packages
    without runnable services only _copy_local_packaging is called to produce
    packaging artifacts alongside the obs/ files.

    ``branch_env_vars`` are the env vars of the branch-from profile and are used
    for ${VAR} substitution in substitutable files (_aggregate, _link) so that the
    comparison reproduces what was uploaded when the branch project was last synced.
    Falls back to ``env_vars`` when not provided.
    """
    obs_md5s = _fetch_obs_file_md5s(apiurl, branch_project, package_name, expanded=True)
    if not obs_md5s:
        logger.debug(f"content check: no files in {branch_project}/{package_name}")
        return False

    check_vars = branch_env_vars if branch_env_vars is not None else env_vars
    service_file = obs_dir / "_service"
    run_services = service_file.is_file() and _has_runnable_services(service_file)

    combined = Path(tempfile.mkdtemp(prefix="percona-obs-check-"))
    workdir: Path | None = None
    try:
        if run_services:
            try:
                workdir = _run_local_services(
                    obs_dir,
                    pkg_label=f"{branch_project}/{package_name}",
                    cache=True,
                    env_vars=check_vars,
                )
            except SystemExit:
                logger.debug(
                    f"content check: service run failed  {branch_project}/{package_name}"
                )
                return False
            for f in obs_dir.iterdir():
                if f.is_file() and f.name != "_service":
                    _copy_with_env_subst(f, combined, check_vars)
            for f in workdir.iterdir():
                if f.is_file():
                    shutil.copy2(f, combined / f.name)
        else:
            for f in obs_dir.iterdir():
                if f.is_file():
                    _copy_with_env_subst(f, combined, check_vars)
            _copy_local_packaging(
                obs_dir,
                combined,
                pkg_label=f"{branch_project}/{package_name}",
            )

        local_md5s: dict[str, str] = {}
        for f in combined.iterdir():
            if f.is_file():
                local_md5s[f.name] = hashlib.md5(f.read_bytes()).hexdigest()

        for fname, local_md5 in sorted(local_md5s.items()):
            if obs_md5s.get(fname) != local_md5:
                logger.debug(
                    f"content check: {fname} differs  {branch_project}/{package_name}"
                )
                return False

        for fname in obs_md5s:
            if fname not in local_md5s:
                logger.debug(
                    f"content check: {fname} in OBS but not local  {branch_project}/{package_name}"
                )
                return False

        return True
    finally:
        shutil.rmtree(combined, ignore_errors=True)
        if workdir is not None:
            shutil.rmtree(workdir, ignore_errors=True)


def _resolve_branch_decision(
    apiurl: str,
    branch_project: str,
    package_name: str,
    package_path: Path,
    env_vars: dict[str, str] | None = None,
    branch_env_vars: dict[str, str] | None = None,
) -> bool:
    """Return True if the package should be aggregated from branch_project.

    Primary path: the branch has a clean 'sync:' revision message with a
    known git SHA and no local commits since that SHA.

    Fallback (content check): when the revision message cannot be trusted —
    no message, non-sync format, or a dirty sync — build the combined upload
    directory locally and compare it against what OBS currently holds.

    ``branch_env_vars`` are the env vars of the branch-from profile.  They
    are used for content comparison so that substitutable tokens (e.g.
    ``${PERCONA_OBS_PACKAGING_BRANCH}``) are expanded the same way they were
    when the branch project was last synced, rather than with the current
    profile's values.  Falls back to ``env_vars`` when not provided.
    """

    def _content_check(reason: str) -> bool:
        logger.debug(f"branch decision: content check  {label}  ({reason})")
        obs_dir = package_path / "obs"
        matches = _content_matches_branch(
            apiurl,
            branch_project,
            package_name,
            obs_dir,
            branch_env_vars,
            env_vars,
        )
        if matches:
            logger.debug(f"branch decision: aggregate  {label}  (content matches)")
        else:
            logger.debug(f"branch decision: sync  {label}  (content differs)")
        return matches

    label = f"{branch_project}/{package_name}"
    comment = _fetch_obs_package_meaningful_comment(
        apiurl, branch_project, package_name
    )
    if not comment:
        return _content_check("no revision comment in branch project")

    m = _SYNC_MSG_RE.match(comment)
    if not m:
        return _content_check(f"comment is not a sync message: {comment!r}")

    short_sha = m.group(1)
    details = m.group(2)
    if details.startswith("local changes on"):
        return _content_check(f"branch was synced dirty at {short_sha}")

    changed = _has_package_changes_since(short_sha, package_path)
    if not changed:
        logger.debug(
            f"branch decision: aggregate  {label}  (no changes since {short_sha})"
        )
        return True
    return _content_check(f"git changes since {short_sha}")


def _compute_branch_project(
    obs_project_name: str, rootprj: str, branch_rootprj: str
) -> str:
    """Return the branch project name that corresponds to obs_project_name.

    Substitutes the branch rootprj prefix for the current rootprj prefix.
    If obs_project_name does not match rootprj (unexpected), returns it unchanged.
    """
    if obs_project_name == rootprj:
        return branch_rootprj
    if obs_project_name.startswith(rootprj + ":"):
        return branch_rootprj + obs_project_name[len(rootprj) :]
    return obs_project_name


def cmd_sync(args):
    """Sync local packaging files to OBS, creating or updating projects and packages.

    Supported call forms:
      sync                        — sync everything under root/
      sync <project>              — sync all packages under a project
      sync <top-level-package>    — sync a single package with no project grouping
      sync <project> <package>    — sync a single package under a project
    """
    if args.project_only and args.package is not None:
        print(
            "error: --project-only cannot be combined with a package argument",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate local project configuration before making any API calls.
    ref_errors = _validate_subproject_refs(REPO_ROOT)
    if ref_errors:
        for yaml_path, msg in ref_errors:
            rel = yaml_path.relative_to(REPO_ROOT.parent)
            print(f"error: {rel}: {msg}", file=sys.stderr)
        sys.exit(1)

    targets = _resolve_targets(args)

    # Build env_vars from profile env + -e overrides (already merged by main()).
    # OBS_ROOTPRJ is always injected automatically so that _aggregate files can
    # reference sibling subprojects (e.g. ${OBS_ROOTPRJ}:common:deps:runtime).
    env_vars: dict[str, str] = {
        **(parse_env_overrides(args.env_overrides) if args.env_overrides else {}),
        "OBS_ROOTPRJ": args.rootprj,
    }

    # Collect all _service files with their per-package env vars, then validate
    # in one pass so identical (url, revision) pairs are deduplicated globally.
    scm_inputs = [
        (pkg_path / "obs" / "_service", {**env_vars, **_pkg_env_vars(pkg_path)})
        for _, pkg_path in targets
        if (pkg_path / "obs" / "_service").is_file()
    ]
    if not args.no_scm_validate:
        scm_errors = _validate_obs_scm_revisions(scm_inputs)
        if scm_errors:
            for svc_file, url, revision in scm_errors:
                rel = svc_file.relative_to(REPO_ROOT.parent)
                print(
                    f"error: {rel}: obs_scm revision '{revision}' not found in {url}",
                    file=sys.stderr,
                )
            sys.exit(1)

    apiurl = osc.conf.config["apiurl"]

    # Validate project: path entries against the live OBS instance.  This
    # catches mismatches like a missing trailing ':' in an env var value
    # (e.g. REMOTE_OBS_ORG_INTERCONNECT=openSUSE.org instead of openSUSE.org:)
    # before any projects or packages are created or modified.
    # Scope the scan to the target project subtree when a specific project is
    # given, so unrelated project.yaml files (e.g. releases/*/Updates) that
    # reference OBS projects not yet created are not validated.
    _path_ref_root = resolve_project_path(args.project) if args.project else REPO_ROOT
    path_ref_errors = _validate_project_path_refs(
        _path_ref_root, env_vars, apiurl, rootprj=args.rootprj
    )
    if path_ref_errors:
        for yaml_path, msg in path_ref_errors:
            rel = yaml_path.relative_to(REPO_ROOT.parent)
            print(f"error: {rel}: {msg}", file=sys.stderr)
        sys.exit(1)

    # Resolve --branch-from profile.
    branch_apiurl: str = apiurl  # defaults to the target OBS instance
    branch_rootprj: str | None = None
    branch_env_vars: dict[str, str] | None = None
    if args.branch_from:
        branch_profile = _load_profile(args.branch_from)
        _raw_branch_apiurl = branch_profile.get("apiurl", "")
        if _raw_branch_apiurl:
            branch_apiurl = _raw_branch_apiurl
        branch_rootprj = branch_profile.get("rootprj", "")
        _branch_env_strings = _load_profile_env_strings(args.branch_from)
        branch_env_vars = (
            parse_env_overrides(_branch_env_strings) if _branch_env_strings else {}
        )
        if branch_rootprj:
            branch_env_vars["OBS_ROOTPRJ"] = branch_rootprj
    seen_projects: set = set()
    local_project_names: set[str] = set()
    local_packages_by_project: dict[str, set[str]] = {}
    dry_run_obs = args.dry_run
    # Cache of branch-project → set of repository names, populated lazily in
    # Phase 1.  Avoids a redundant API call per package for the same project.
    _branch_repo_cache: dict[str, set[str]] = {}
    # Cache of project_path → set of target repository names derived from
    # project.yaml.  Avoids repeated YAML parsing for packages in the same
    # project.
    _target_repos_cache: dict[Path, set[str]] = {}

    # --- Phase 1: compute branch/promote decisions upfront ---
    # Running this before the project pre-pass lets us know which projects
    # actually need to be created when --branch-from is active.
    # decisions[(obs_project_name, pkg_name)]:
    #   "aggregate"   — skip package; served via project PATH from branch_project_for[key]
    #   "skip_branch" — (reserved) leave unchanged
    #   "promote"     — upload full obs/ sources
    decisions: dict[tuple[str, str], str] = {}
    branch_project_for: dict[tuple[str, str], str] = {}
    # profile that was used in the branch: comment (plain-push path only).
    branch_profile_for: dict[tuple[str, str], str] = {}
    # pkg_key_by_name[(pkg_name)] → key, used for dep propagation lookups.
    pkg_key_by_name: dict[str, tuple[str, str]] = {}
    # Cache of loaded profiles to avoid repeated file reads within Phase 1.
    _profile_cache: dict[str, dict[str, str]] = {}
    _profile_env_vars_cache: dict[str, dict[str, str]] = {}

    _print_action("planning: checking sync decisions")

    # Per-package decision function run in parallel via a thread pool.
    # All closures over outer-scope variables are read-only except for the
    # shared caches (_branch_repo_cache, _target_repos_cache,
    # _profile_cache), which are plain dicts.  Under CPython's GIL
    # individual dict reads/writes are atomic, so concurrent cache misses that
    # trigger duplicate HTTP calls are benign — both threads obtain the same
    # result and one silently overwrites the other.
    def _decide_package(
        obs_project: str, package_path: Path
    ) -> "tuple[tuple[str, str], str, str | None, str | None] | None":
        obs_dir = package_path / "obs"
        project_path = package_path.parent
        project_config = load_yaml(project_path / "project.yaml")
        obs_project_name = project_config.get("name") or obs_project
        key: tuple[str, str] = (obs_project_name, package_path.name)

        if branch_rootprj:
            branch_project = _compute_branch_project(
                obs_project_name, args.rootprj, branch_rootprj
            )
            pkg_env = _pkg_env_vars(package_path)
            use_aggregate = _resolve_branch_decision(
                apiurl,
                branch_project,
                package_path.name,
                package_path,
                {**env_vars, **pkg_env},
                branch_env_vars=(
                    {**branch_env_vars, **pkg_env}
                    if branch_env_vars is not None
                    else None
                ),
            )
            if use_aggregate:
                # Guard: only aggregate when the branch project has every
                # repository the target project requires.  If a new repository
                # was added locally but doesn't exist in the branch project yet,
                # an aggregate would produce no binaries for that repo.  Fall
                # back to promote so OBS builds from source instead.
                if branch_project not in _branch_repo_cache:
                    logger.debug(
                        f"branch decision: fetching repo list: {branch_project}"
                    )
                    _branch_repo_cache[branch_project] = (
                        _fetch_obs_project_repository_names(
                            branch_apiurl, branch_project
                        )
                    )
                branch_repos = _branch_repo_cache[branch_project]
                proj_path = package_path.parent
                if proj_path not in _target_repos_cache:
                    target_config = _load_project_config_with_inheritance(
                        proj_path, env_vars
                    )
                    _target_repos_cache[proj_path] = {
                        r["name"]
                        for r in target_config.get("repositories", [])
                        if r.get("name")
                    }
                target_repos = _target_repos_cache[proj_path]
                missing_repos = target_repos - branch_repos
                if missing_repos:
                    logger.debug(
                        f"branch decision: promote  {obs_project_name}/{package_path.name}"
                        f"  (repos missing from branch: {sorted(missing_repos)})"
                    )
                    return key, "promote", None, None
                else:
                    return key, "aggregate", branch_project, None
            else:
                return key, "promote", None, None
        else:
            # Without --branch-from, always promote.  The upload function
            # compares file MD5s against OBS and only uploads what changed,
            # so unchanged packages are effectively skipped at upload time.
            return key, "promote", None, None

    with ThreadPoolExecutor(max_workers=16) as _pool:
        _futures = [_pool.submit(_decide_package, op, pp) for op, pp in targets]
        for _fut in _futures:
            _result = _fut.result()
            if _result is None:
                continue
            _key, _decision, _bp, _profile = _result
            pkg_key_by_name[_key[1]] = _key
            decisions[_key] = _decision
            if _bp is not None:
                branch_project_for[_key] = _bp
            if _profile is not None:
                branch_profile_for[_key] = _profile

    # --- Phase 2: dep-triggered promotion (forward fixed-point) ---
    # If a package is being promoted (full sources), any package that depends
    # on it must also be promoted so it is rebuilt against the new binaries.
    has_promotes = any(d == "promote" for d in decisions.values())
    has_branches = any(d in ("aggregate", "skip_branch") for d in decisions.values())
    if has_promotes and has_branches:
        # When --branch-from is active, build dep info lives in the branch (dev)
        # OBS instance; query only those projects.  Target projects (test) may
        # not exist yet (first sync) and their build results are not meaningful
        # for dep-promotion decisions.
        # Without --branch-from, query the target projects on the target OBS.
        local_pkg_names = set(pkg_key_by_name.keys())
        src_projects_by_apiurl: dict[str, set[str]] = {}
        if branch_rootprj:
            # Include all branch projects, not just those with aggregate decisions.
            # Packages that are "promote" may live in a branch project (e.g. builddep)
            # whose builddepinfo is needed to detect binaries they provide.
            dep_projects = {
                _compute_branch_project(key[0], args.rootprj, branch_rootprj)
                for key in decisions
            }
        else:
            # Source projects may live on a different OBS instance (cross-instance
            # branching).  Group them by the apiurl resolved from the branch profile
            # recorded in Phase 1, and query each OBS instance separately.
            # Target projects (which may have real source uploads) are queried at
            # the target apiurl.
            src_projects_by_apiurl = {apiurl or "": {key[0] for key in decisions}}
            for key, src_proj in branch_project_for.items():
                profile_name = branch_profile_for.get(key, "")
                src_apiurl = (
                    _profile_cache.get(profile_name, {}).get("apiurl") or apiurl or ""
                )
                src_projects_by_apiurl.setdefault(src_apiurl, set()).add(src_proj)
            dep_projects = {key[0] for key in decisions} | set(
                branch_project_for.values()
            )
        _print_action(
            f"planning: checking build dependencies ({len(dep_projects)} project(s))"
        )
        if branch_rootprj:
            image_pkgs: dict[str, tuple[str, str, str]] = {
                pkg_path.name: (
                    _compute_branch_project(obs_project, args.rootprj, branch_rootprj),
                    "images",
                    "x86_64",
                )
                for obs_project, pkg_path in targets
                if is_dockerfile_image(pkg_path)
            }
            fwd_deps = _fetch_combined_depinfo(
                branch_apiurl,
                dep_projects,
                local_pkg_names,
                image_pkgs=image_pkgs or None,
            )
        else:
            # Build a per-apiurl image_pkgs map so _fetch_combined_depinfo can
            # enrich the fwd-dep map with Dockerfile-image -> RPM edges.
            # Each image package is routed to the same OBS instance as its
            # source project (branch instance for aggregates, target for others).
            image_pkg_by_apiurl_sync: dict[str, dict[str, tuple[str, str, str]]] = {}
            for obs_project, pkg_path in targets:
                if not is_dockerfile_image(pkg_path):
                    continue
                _key = (obs_project, pkg_path.name)
                if _key in branch_project_for:
                    _profile_name = branch_profile_for.get(_key, "")
                    _ia = (
                        _profile_cache.get(_profile_name, {}).get("apiurl")
                        or apiurl
                        or ""
                    )
                    _proj = branch_project_for[_key]
                else:
                    _ia = apiurl or ""
                    _proj = obs_project
                image_pkg_by_apiurl_sync.setdefault(_ia, {})[pkg_path.name] = (
                    _proj,
                    "images",
                    "x86_64",
                )
            all_fwd_deps: dict[str, set[str]] = {}
            for q_apiurl, q_projects in src_projects_by_apiurl.items():
                _img = image_pkg_by_apiurl_sync.get(q_apiurl, {})
                partial = _fetch_combined_depinfo(
                    q_apiurl,
                    q_projects,
                    local_pkg_names,
                    image_pkgs=_img or None,
                )
                for pkg, deps in partial.items():
                    all_fwd_deps.setdefault(pkg, set()).update(deps)
            fwd_deps = all_fwd_deps
        logger.debug(
            f"dep-promote: builddepinfo covers {len(fwd_deps)} local packages"
            f" with known local build deps; local_pkg_names={local_pkg_names}"
        )
        if not fwd_deps:
            _print_action(
                "dep-promote: no build dep info available"
                " (branch projects may not have build results yet)"
            )
        else:
            # Build reverse map: rdeps[A] = {packages that depend on A}.
            rdeps: dict[str, set[str]] = {}
            for pkg, deps in fwd_deps.items():
                for dep in deps:
                    rdeps.setdefault(dep, set()).add(pkg)
            # Iterate until no new promotions are triggered.
            changed = True
            while changed:
                changed = False
                for key, decision in list(decisions.items()):
                    if decision != "promote":
                        continue
                    _, pkg_name = key
                    # Forward: promote packages that depend on this one.
                    for dependent in rdeps.get(pkg_name, set()):
                        dep_key = pkg_key_by_name.get(dependent)
                        if dep_key and decisions.get(dep_key) in (
                            "aggregate",
                            "skip_branch",
                            "skip",
                        ):
                            _print_action(
                                f"dep-promote: {dep_key[0]}/{dep_key[1]}"
                                f"  (depends on promoted {pkg_name})"
                            )
                            decisions[dep_key] = "promote"
                            changed = True

    # --- Phase 2.5: detect projects whose config changed on OBS (read-only) ---
    # Runs after Phase 1 + Phase 2 so a preliminary active_projects (projects
    # with at least one promote decision) is known and can be passed to
    # build_project_meta via check_project_config_changed.  Without it, the
    # desired meta would use raw subproject paths while the meta on OBS has
    # them redirected to branch_rootprj, producing a false "config changed"
    # verdict that would flip every aggregate to a promote on re-sync.
    config_changed_projects: set[str] = set()
    if targets:
        _preliminary_active: set[str] | None = None
        if branch_rootprj and args.package is None:
            _preliminary_active = {
                obs_project
                for (obs_project, _), d in decisions.items()
                if d == "promote"
            }
            _preliminary_active.add(args.rootprj)

        _unique_proj_paths: dict[str, tuple[str, Path]] = {}
        for _op, _pp in targets:
            _proj_path = _pp.parent
            _proj_cfg = load_yaml(_proj_path / "project.yaml")
            _proj_name = _proj_cfg.get("name") or _op
            if _proj_name not in _unique_proj_paths:
                _unique_proj_paths[_proj_name] = (_op, _proj_path)

        def _check_proj_changed(
            item: "tuple[str, tuple[str, Path]]",
        ) -> "tuple[str, bool, bool]":
            _pname, (_op2, _ppath) = item
            # In --branch-from mode always compare local desired config against
            # the PRODUCTION project, not the PR project's current state on OBS.
            # The PR project may have stale meta from a previous sync (e.g. old
            # path order) which would produce a false "config changed" verdict
            # and promote packages that haven't actually changed.
            if branch_rootprj:
                _prod_name = _compute_branch_project(
                    _pname, args.rootprj, branch_rootprj
                )
                _prod_changed, _prod_is_new = check_project_config_changed(
                    branch_apiurl,
                    _prod_name,
                    _ppath,
                    branch_rootprj,
                    env_vars=branch_env_vars,
                    active_projects=None,
                    branch_rootprj=None,
                )
                if _prod_is_new:
                    # Production project doesn't exist yet — treat as new (no
                    # config-triggered promotion needed; Phase 1 covers it).
                    return _pname, False, True
                return _pname, _prod_changed, False
            _changed, _is_new = check_project_config_changed(
                apiurl,
                _pname,
                _ppath,
                args.rootprj,
                env_vars=env_vars,
                active_projects=_preliminary_active,
                branch_rootprj=branch_rootprj,
            )
            return _pname, _changed, _is_new

        with ThreadPoolExecutor(max_workers=8) as _proj_pool:
            for _pname, _changed, _is_new in _proj_pool.map(
                _check_proj_changed, _unique_proj_paths.items()
            ):
                if not _is_new and _changed:
                    config_changed_projects.add(_pname)

    # --- Config-triggered promotion (--branch-from only) ---
    # Packages in a project whose config changed must be promoted to the target
    # OBS so they are rebuilt with the new config, even if their source files
    # didn't change (they would otherwise stay as aggregate/skip).
    if branch_rootprj and config_changed_projects:
        for _key, _decision in list(decisions.items()):
            if _key[0] in config_changed_projects and _decision in (
                "aggregate",
                "skip",
                "skip_branch",
            ):
                _print_action(
                    f"config-promote: {_key[0]}/{_key[1]}" f"  (project config changed)"
                )
                decisions[_key] = "promote"

    # Compute the set of OBS projects that actually need to be created.
    # When --branch-from is active on a full-tree sync, only projects with at
    # least one promoted package are created; projects whose packages are all
    # aggregated are skipped and their subproject path references are redirected
    # to the branch-source equivalents.  The root project is always included as
    # a CI namespace anchor.
    active_projects: set[str] | None = None
    if branch_rootprj and args.package is None:
        active_projects = {
            obs_project for (obs_project, _), d in decisions.items() if d == "promote"
        }
        active_projects.add(args.rootprj)

    # Pre-pass: two-stage project creation to handle OBS path-reference cycles.
    #
    # Stage 1 — create bare skeleton projects (no <repository> elements) for any
    #   project that does not yet exist on OBS.  Projects are processed
    #   shallowest-first (fewest ':' in the OBS name) so OBS parent projects
    #   always exist before their children, regardless of path dependencies.
    #
    # Stage 2 — apply the full project config (repos, paths, build config) once
    #   every project in the tree exists.  Because all projects are already
    #   present by this point, OBS never raises repository_access_failure.
    if args.package is None:
        all_projects: dict[str, tuple[str, Path]] = {}
        for obs_project, package_path in targets:
            for raw_proj, prj_name, proj_path in _iter_project_chain(
                obs_project, package_path.parent
            ):
                # With --branch-from, skip projects with no promoted packages.
                if active_projects is not None and prj_name not in active_projects:
                    continue
                local_project_names.add(prj_name)
                if raw_proj not in all_projects:
                    all_projects[raw_proj] = (prj_name, proj_path)
        sorted_projs = sorted(all_projects.items(), key=lambda kv: kv[1][0].count(":"))
        for _raw, (prj_name, proj_path) in sorted_projs:
            _create_project_skeleton(
                apiurl,
                prj_name,
                proj_path,
                args.rootprj,
                dry_run=dry_run_obs,
                env_vars=env_vars,
            )
        # Give OBS a moment to settle after creating skeleton projects
        # before applying the full configuration.
        if sorted_projs and not dry_run_obs:
            time.sleep(5)
        # Stage 2 pass 1: configure all projects.  Projects whose <path>
        # elements reference sibling/child projects that are still skeletons
        # will have those paths stripped and need a second pass.
        needs_reconfig: list[tuple[str, str, Path]] = []
        for raw_proj, (prj_name, proj_path) in sorted_projs:
            stripped, _ = _apply_project_config(
                apiurl,
                prj_name,
                proj_path,
                args.rootprj,
                force=args.force,
                dry_run=dry_run_obs,
                env_vars=env_vars,
                active_projects=active_projects,
                branch_rootprj=branch_rootprj,
            )
            if stripped:
                needs_reconfig.append((raw_proj, prj_name, proj_path))
            seen_projects.add(raw_proj)
        # Stage 2 pass 2: re-apply config for projects that had paths stripped.
        # By now all sibling/child projects have their repositories configured,
        # so OBS will accept the full meta.  Projects already correctly
        # configured are detected by _project_meta_subset_equal and skipped.
        for raw_proj, prj_name, proj_path in needs_reconfig:
            _, _ = _apply_project_config(
                apiurl,
                prj_name,
                proj_path,
                args.rootprj,
                force=args.force,
                dry_run=dry_run_obs,
                env_vars=env_vars,
                active_projects=active_projects,
                branch_rootprj=branch_rootprj,
            )

    if args.project_only:
        suffix = " (dry run)" if args.dry_run else ""
        _print_ok(f"sync successful{suffix}")
        return

    # --- Phase 3: execute uploads based on decisions ---
    # Track packages that were triggered by file changes so the config-triggered
    # rebuild sweep below doesn't double-trigger them.

    for obs_project, package_path in targets:
        project_path = package_path.parent
        project_config = load_yaml(project_path / "project.yaml")
        obs_project_name = project_config.get("name") or obs_project

        # With --branch-from on a full-tree sync, skip projects that were not
        # created because all their packages are aggregated from the branch source.
        if active_projects is not None and obs_project_name not in active_projects:
            continue

        if args.package is not None:
            # Single-package target: ensure the project hierarchy exists on OBS
            # using the same two-stage approach as the full-tree pre-pass.
            if not _obs_project_exists(apiurl, obs_project_name):
                chain: dict[str, tuple[str, Path]] = {}
                for raw_proj, prj_name, proj_path in _iter_project_chain(
                    obs_project, project_path
                ):
                    local_project_names.add(prj_name)
                    if raw_proj not in chain:
                        chain[raw_proj] = (prj_name, proj_path)
                sorted_chain = sorted(chain.items(), key=lambda kv: kv[1][0].count(":"))
                for _raw, (prj_name, proj_path) in sorted_chain:
                    if _raw not in seen_projects:
                        _create_project_skeleton(
                            apiurl,
                            prj_name,
                            proj_path,
                            args.rootprj,
                            dry_run=dry_run_obs,
                            env_vars=env_vars,
                        )
                if (
                    any(_raw not in seen_projects for _raw, _ in sorted_chain)
                    and not dry_run_obs
                ):
                    time.sleep(5)
                chain_needs_reconfig: list[tuple[str, str, Path]] = []
                for raw_proj, (prj_name, proj_path) in sorted_chain:
                    if raw_proj not in seen_projects:
                        stripped, _ = _apply_project_config(
                            apiurl,
                            prj_name,
                            proj_path,
                            args.rootprj,
                            force=args.force,
                            dry_run=dry_run_obs,
                            env_vars=env_vars,
                            active_projects=active_projects,
                            branch_rootprj=branch_rootprj,
                        )
                        if stripped:
                            chain_needs_reconfig.append((raw_proj, prj_name, proj_path))
                        seen_projects.add(raw_proj)
                for raw_proj, prj_name, proj_path in chain_needs_reconfig:
                    _, _ = _apply_project_config(
                        apiurl,
                        prj_name,
                        proj_path,
                        args.rootprj,
                        force=args.force,
                        dry_run=dry_run_obs,
                        env_vars=env_vars,
                        active_projects=active_projects,
                        branch_rootprj=branch_rootprj,
                    )

        obs_dir = package_path / "obs"
        key = (obs_project_name, package_path.name)
        decision = decisions.get(key, "promote")

        if decision != "promote":
            _print_aggregate(f"files  {obs_project_name}/{package_path.name}")
            continue

        _apply_package_config(
            apiurl,
            obs_project_name,
            package_path.name,
            package_path,
            force=args.force,
            dry_run=dry_run_obs,
        )
        local_packages_by_project.setdefault(obs_project_name, set()).add(
            package_path.name
        )

        pkg_vars = {**env_vars, **_pkg_env_vars(package_path)}
        message = args.message or _generate_sync_message()
        service_file = obs_dir / "_service"
        run_services = (
            not args.no_services
            and service_file.is_file()
            and _has_runnable_services(service_file)
        )
        files_changed = False
        if run_services:
            workdir = _run_local_services(
                obs_dir,
                pkg_label=f"{obs_project_name}/{package_path.name}",
                cache=not args.no_cache,
                env_vars=pkg_vars,
            )
            try:
                combined = Path(tempfile.mkdtemp(prefix="percona-obs-upload-"))
                try:
                    # Copy obs/ files excluding _service.
                    for f in obs_dir.iterdir():
                        if f.is_file() and f.name != "_service":
                            _copy_with_env_subst(f, combined, pkg_vars)
                    # Copy all service artifacts (cleanup already done).
                    for f in workdir.iterdir():
                        if f.is_file():
                            shutil.copy2(f, combined / f.name)
                    if branch_rootprj:
                        _rewrite_aggregates_in_dir(
                            combined, args.rootprj, branch_rootprj, active_projects
                        )
                    files_changed = _upload_obs_files(
                        apiurl,
                        obs_project_name,
                        package_path.name,
                        combined,
                        message=message,
                        dry_run=dry_run_obs,
                    )
                finally:
                    shutil.rmtree(combined, ignore_errors=True)
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
        else:
            sub_dir = Path(tempfile.mkdtemp(prefix="percona-obs-upload-"))
            try:
                if obs_dir.is_dir():
                    for f in obs_dir.iterdir():
                        if f.is_file():
                            _copy_with_env_subst(f, sub_dir, pkg_vars)
                # Copy local debian/ and rpm/ packaging for service-less
                # packages (e.g. metapackages with hardcoded versions).
                _copy_local_packaging(
                    obs_dir,
                    sub_dir,
                    pkg_label=f"{obs_project_name}/{package_path.name}",
                )
                if branch_rootprj:
                    _rewrite_aggregates_in_dir(
                        sub_dir, args.rootprj, branch_rootprj, active_projects
                    )
                files_changed = _upload_obs_files(
                    apiurl,
                    obs_project_name,
                    package_path.name,
                    sub_dir,
                    message=message,
                    dry_run=dry_run_obs,
                )
            finally:
                shutil.rmtree(sub_dir, ignore_errors=True)

    # --- orphan cleanup ---
    # Remove packages on OBS that no longer exist locally, but only when the
    # full package set of a project was processed (not a single-package sync).
    if args.package is None:
        # Ensure the root project is included even when --non-recursive produces
        # zero local packages (e.g. root/ has no direct-child packages).
        if args.project is None:
            root_config = load_yaml(REPO_ROOT / "project.yaml")
            root_obs_name = root_config.get("name") or args.rootprj
            local_packages_by_project.setdefault(root_obs_name, set())
        for proj_name, local_pkgs in local_packages_by_project.items():
            obs_pkgs = _fetch_obs_package_names(apiurl, proj_name)
            for orphan in sorted(obs_pkgs - local_pkgs):
                _delete_obs_package(apiurl, proj_name, orphan, dry_run_obs)

    # Remove subprojects on OBS that no longer exist locally, but only when
    # the full tree was processed (not a single-project or single-package sync).
    # Skip when --non-recursive is active: sub-project directories were not
    # scanned so local_project_names is incomplete and would incorrectly mark
    # every sub-project as orphaned.
    # Delete deepest subprojects first so parents are empty before deletion.
    if args.project is None and not getattr(args, "non_recursive", False):
        obs_subprojects = _fetch_obs_subproject_names(apiurl, args.rootprj)
        orphan_projects = {
            p
            for p in obs_subprojects - local_project_names
            if not _is_pr_managed_project(p, args.rootprj)
        }
        for orphan_proj in sorted(orphan_projects, key=lambda x: -x.count(":")):
            _delete_obs_project(apiurl, orphan_proj, dry_run_obs, recursive=True)

    suffix = " (dry run)" if args.dry_run else ""
    _print_ok(f"sync successful{suffix}")


def cmd_sync_delete(args) -> None:
    """Delete OBS projects (and sub-projects) or a single package.

    Supported call forms:
      sync delete                         — delete full project tree under rootprj
      sync delete <project>               — delete a project and all its sub-projects
      sync delete <project> <package>     — delete a single package
    """
    apiurl = osc.conf.config["apiurl"]
    dry_run: bool = args.dry_run

    if args.package:
        # ── Single package ────────────────────────────────────────────────
        proj_path = resolve_project_path(args.project)
        project_config = load_yaml(proj_path / "project.yaml")
        obs_project_name = (
            project_config.get("name") or f"{args.rootprj}:{args.project}"
        )
        label = f"{obs_project_name}/{args.package}"
        if dry_run:
            _print_remove(f"package  {label}")
            _print_ok("delete done (dry run)")
            return
        print(f"  {label}")
        if not args.yes:
            try:
                answer = input("\nDelete 1 package? [y/N] ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                raise SystemExit("\nAborted.")
            if answer not in ("y", "yes"):
                raise SystemExit("Aborted.")
        _delete_obs_package(apiurl, obs_project_name, args.package, dry_run=False)
    else:
        # ── Project tree ──────────────────────────────────────────────────
        if args.project:
            root_path = resolve_project_path(args.project)
            if not root_path.is_dir() or is_package(root_path):
                raise SystemExit(f"error: {args.project!r} is not a project directory")
            root_obs = f"{args.rootprj}:{args.project}"
        else:
            root_path = REPO_ROOT
            root_obs = args.rootprj

        projects = list(find_projects(root_path, root_obs))
        # Delete deepest sub-projects first so parents are empty before deletion.
        projects_sorted = sorted(projects, key=lambda x: x[0].count(":"), reverse=True)

        if dry_run:
            for obs_name, _ in projects_sorted:
                _print_remove(f"project  {obs_name}")
            _print_ok("delete done (dry run)")
            return

        for obs_name, _ in projects_sorted:
            print(f"  {obs_name}")
        n = len(projects_sorted)
        kind = "project" if n == 1 else "projects"
        if not args.yes:
            try:
                answer = input(f"\nDelete {n} {kind}? [y/N] ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                raise SystemExit("\nAborted.")
            if answer not in ("y", "yes"):
                raise SystemExit("Aborted.")
        for obs_name, _ in projects_sorted:
            _delete_obs_project(
                apiurl, obs_name, dry_run=False, recursive=args.recursive
            )

    _print_ok("delete done")


def cmd_sync_promote(args) -> None:
    """Promote branch packages to full source syncs.

    For each package in the given scope that currently holds a _aggregate
    (created by a prior --branch-from sync), replace it with the local obs/
    source files.  Packages that are already sourced are skipped.

    Supported call forms:
      sync promote                        — promote all packages
      sync promote <project>              — promote all packages under a project
      sync promote <project> <package>    — promote a single package
    """
    targets = _resolve_targets(args)
    apiurl = osc.conf.config["apiurl"]
    dry_run = args.dry_run
    promoted = 0
    skipped = 0

    env_vars: dict[str, str] = {
        **(parse_env_overrides(args.env_overrides) if args.env_overrides else {}),
        "OBS_ROOTPRJ": args.rootprj,
    }

    for obs_project, package_path in targets:
        project_path = package_path.parent
        project_config = load_yaml(project_path / "project.yaml")
        obs_project_name = project_config.get("name") or obs_project

        obs_dir = package_path / "obs"
        if not obs_dir.is_dir():
            skipped += 1
            continue

        pkg_vars = {**env_vars, **_pkg_env_vars(package_path)}

        # Check if the OBS package is currently a branch aggregate.
        latest_comment = _fetch_obs_package_latest_comment(
            apiurl, obs_project_name, package_path.name
        )
        if not latest_comment or not _BRANCH_MSG_RE.match(latest_comment):
            _print_same(f"files  {obs_project_name}/{package_path.name}")
            skipped += 1
            continue

        # It's a branch — promote to full sources.
        message = args.message or _generate_sync_message()
        service_file = obs_dir / "_service"
        run_services = (
            not args.no_services
            and service_file.is_file()
            and _has_runnable_services(service_file)
        )
        if run_services and not dry_run:
            workdir = _run_local_services(
                obs_dir,
                pkg_label=f"{obs_project_name}/{package_path.name}",
                cache=not args.no_cache,
                env_vars=pkg_vars,
            )
            try:
                combined = Path(tempfile.mkdtemp(prefix="percona-obs-upload-"))
                try:
                    for f in obs_dir.iterdir():
                        if f.is_file() and f.name != "_service":
                            _copy_with_env_subst(f, combined, pkg_vars)
                    for f in workdir.iterdir():
                        if f.is_file():
                            shutil.copy2(f, combined / f.name)
                    _upload_obs_files(
                        apiurl,
                        obs_project_name,
                        package_path.name,
                        combined,
                        message=message,
                        dry_run=False,
                    )
                finally:
                    shutil.rmtree(combined, ignore_errors=True)
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
        else:
            sub_dir = Path(tempfile.mkdtemp(prefix="percona-obs-upload-"))
            try:
                for f in obs_dir.iterdir():
                    if f.is_file():
                        _copy_with_env_subst(f, sub_dir, pkg_vars)
                _upload_obs_files(
                    apiurl,
                    obs_project_name,
                    package_path.name,
                    sub_dir,
                    message=message,
                    dry_run=dry_run,
                )
            finally:
                shutil.rmtree(sub_dir, ignore_errors=True)
        promoted += 1

    suffix = " (dry run)" if dry_run else ""
    _print_ok(f"promote successful{suffix}  ({promoted} promoted, {skipped} skipped)")


def _sync_release_subprojects(
    apiurl: str,
    args,
    source_project_id: str,
    release_obs_project: str,
    release_path: Path,
    env_vars: dict[str, str],
) -> None:
    """Create and populate OBS subprojects for a release (e.g. containers).

    Walks the local source project directory for subprojects that have a
    corresponding project.yaml under the release tree.  For each one:
      - Applies the project config to OBS (creating the project if absent).
      - Adds releasetargets to the source subproject, runs osc release, then
        removes the releasetargets.

    Subprojects without a matching release project.yaml are silently skipped.
    """
    source_path = resolve_project_path(source_project_id)
    for sub_obs_id, _sub_path in find_projects(source_path, source_project_id):
        if sub_obs_id == source_project_id:
            continue
        subproject_name = sub_obs_id[len(source_project_id) + 1 :]
        release_sub_obs = f"{release_obs_project}:{subproject_name}"
        release_sub_path = release_path / subproject_name

        if not (release_sub_path / "project.yaml").is_file():
            continue

        _apply_project_config(
            apiurl,
            release_sub_obs,
            release_sub_path,
            args.rootprj,
            env_vars=env_vars,
        )

        source_sub_obs = f"{args.rootprj}:{sub_obs_id}"
        source_sub_repo_elems, _ = _read_project_release_source(apiurl, source_sub_obs)
        source_sub_repo_names = [
            r.get("name", "") for r in source_sub_repo_elems if r.get("name")
        ]
        _add_release_targets(
            apiurl, source_sub_obs, release_sub_obs, source_sub_repo_names
        )
        try:
            _print_pending(f"releasing {source_sub_obs} → {release_sub_obs}")
            subprocess.run(
                [_OSC_BIN, "-A", apiurl, "release", source_sub_obs, "--no-delay"],
                check=True,
            )
        finally:
            _remove_release_targets(apiurl, source_sub_obs, release_sub_obs)
        _print_ok(f"released  {source_sub_obs} → {release_sub_obs}")

        # Disable builds for non-container-image packages.
        # osc release copies binaries but not package _meta; packages without
        # a Dockerfile are dependency RPMs that must not build in the release.
        source_sub_local_path = resolve_project_path(sub_obs_id)
        for pkg_name in osc.core.meta_get_packagelist(apiurl, release_sub_obs):
            if not pkg_name:
                continue
            local_pkg = source_sub_local_path / pkg_name
            if (local_pkg / "obs" / "Dockerfile").is_file():
                continue
            _disable_package_builds(
                apiurl,
                release_sub_obs,
                pkg_name,
                force=args.force,
                dry_run=getattr(args, "dry_run", False),
            )


def cmd_sync_release(args) -> None:
    """Release packages from an OBS source project to a release target.

    Reads the release.yaml for the given release project identifier,
    checks that the source project is up-to-date, creates the release
    target project on OBS, configures releasetarget entries on the source
    project, runs ``osc release``, then restores the source project's
    repository configuration.
    """
    release_path = resolve_project_path(args.project)
    release_file = release_path / "release.yaml"
    if not release_file.is_file():
        raise SystemExit(
            f"error: release.yaml not found at {release_path.relative_to(_REPO_DIR)}"
        )

    env_vars = parse_env_overrides(args.env_overrides) if args.env_overrides else {}
    release_data = load_yaml_with_env(release_file, env_vars)

    source_project_id = release_data.get("project")
    if not source_project_id:
        raise SystemExit(f"error: release.yaml missing 'project' field: {release_file}")

    apiurl: str = osc.conf.config["apiurl"]
    source_obs_project = f"{args.rootprj}:{source_project_id}"
    release_obs_project = f"{args.rootprj}:{args.project}"

    # Idempotency: if the release project already exists the release has
    # already been done.  Clean up any stale releasetarget entries that may
    # have been left behind by a partial previous run, then exit.
    _print_pending(f"checking release project {release_obs_project}")
    updates_obs_project = f"{release_obs_project}:Updates"
    if _obs_project_exists(apiurl, release_obs_project):
        _remove_release_targets(apiurl, source_obs_project, release_obs_project)
        if not _obs_project_exists(apiurl, updates_obs_project):
            source_repo_elems, _ = _read_project_release_source(
                apiurl, source_obs_project
            )
            _create_update_subproject(
                apiurl,
                updates_obs_project,
                release_obs_project,
                source_repo_elems,
            )
        _sync_release_subprojects(
            apiurl,
            args,
            source_project_id,
            release_obs_project,
            release_path,
            env_vars={
                **(
                    parse_env_overrides(args.env_overrides)
                    if args.env_overrides
                    else {}
                ),
                "OBS_ROOTPRJ": args.rootprj,
            },
        )
        _print_same(f"release  {release_obs_project}  (already exists)")
        return

    # Validate that the source project has not diverged since the release tag.
    if not args.force:
        # Check 1: git-level divergence since the release tag.
        tag = release_data.get("revision", "")
        source_path = resolve_project_path(source_project_id)
        if tag and getattr(args, "skip_tag_check", False):
            _print_same(f"skipping tag divergence check for {tag} (--skip-tag-check)")
        elif tag:
            _print_pending(
                f"checking for changes in {source_project_id} since tag {tag}"
            )
            result = subprocess.run(
                [
                    "git",
                    "diff",
                    "--name-only",
                    f"{tag}..HEAD",
                    "--",
                    str(source_path),
                ],
                capture_output=True,
                text=True,
                cwd=_REPO_DIR,
            )
            if result.returncode != 0:
                print(result.stderr, end="", file=sys.stderr)
                raise SystemExit(
                    f"error: git diff failed — is the tag '{tag}' present locally?"
                )
            changed_files = [
                line.strip() for line in result.stdout.splitlines() if line.strip()
            ]
            if changed_files:
                print(
                    f"error: source project {source_project_id} has changed since "
                    f"tag {tag}:",
                    file=sys.stderr,
                )
                for f in changed_files:
                    print(f"  {f}", file=sys.stderr)
                raise SystemExit(
                    "The source project has diverged from the release tag. "
                    "Use --force to skip this check."
                )

        # Check 2: OBS-level divergence (external edits directly in OBS).
        _print_pending(f"validating source project {source_obs_project} is up-to-date")
        cmd = [
            sys.executable,
            "-m",
            "percona_obs",
        ]
        if args.profile:
            cmd += ["-P", args.profile]
        else:
            cmd += ["-A", apiurl, "-R", args.rootprj]
        cmd += [
            "sync",
            "push",
            "--dry-run",
            "--no-scm-validate",
            source_project_id,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=_REPO_DIR)
        if result.returncode != 0:
            print(result.stderr, end="", file=sys.stderr)
            raise SystemExit(
                f"error: sync push --dry-run failed for {source_project_id}"
            )
        # Check for promote indicators in the output.  Promoted packages
        # produce lines starting with "  + " (new files) or "  ~ " (updated).
        pending_lines = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("  + ") or line.startswith("  ~ ")
        ]
        if pending_lines:
            print(
                f"error: source project {source_project_id} has pending changes:",
                file=sys.stderr,
            )
            for line in pending_lines:
                print(f"  {line}", file=sys.stderr)
            raise SystemExit(
                "Sync the source project before releasing: "
                f"percona-obs sync push {source_project_id}"
            )

    # Create the release target project on OBS (build disabled, same repos as source).
    source_repo_elems = _create_release_project(
        apiurl, source_obs_project, release_obs_project
    )
    repo_names = [r.get("name", "") for r in source_repo_elems if r.get("name")]

    # Copy the source project's prjconf (Prefer/Ignore/ExpandFlags rules) to
    # the release project so it is a faithful snapshot of source build rules.
    _copy_project_conf(apiurl, source_obs_project, release_obs_project)

    # Add releasetarget entries to the source project repositories, then
    # run osc release.  Always restore the source project afterwards.
    _add_release_targets(apiurl, source_obs_project, release_obs_project, repo_names)
    try:
        _print_pending(f"releasing {source_obs_project} → {release_obs_project}")
        subprocess.run(
            [_OSC_BIN, "-A", apiurl, "release", source_obs_project, "--no-delay"],
            check=True,
        )
    finally:
        _remove_release_targets(apiurl, source_obs_project, release_obs_project)

    # Create the Updates subproject with builds disabled; repos inherit the
    # source's <path> chain with the base release project prepended.
    _create_update_subproject(
        apiurl,
        updates_obs_project,
        release_obs_project,
        source_repo_elems,
    )

    # Create and populate release subprojects that mirror the source project's
    # subprojects (e.g. containers).  These have builds enabled so that container
    # images rebuild automatically when packages are updated via Updates.
    _sync_release_subprojects(
        apiurl,
        args,
        source_project_id,
        release_obs_project,
        release_path,
        env_vars={
            **(parse_env_overrides(args.env_overrides) if args.env_overrides else {}),
            "OBS_ROOTPRJ": args.rootprj,
        },
    )

    _print_ok(f"release  {source_obs_project} → {release_obs_project}")


def cmd_sync_release_pr(args) -> None:
    """Run osc release on all OBS projects in a PR tree.

    Called on PR merge, before sync delete, to publish built packages from
    the PR project into the corresponding production projects via the
    <releasetarget> entries added by sync push --branch-from.

    Before releasing, syncs the production project configs so that any repo
    or arch changes introduced by the PR (e.g. adding aarch64) are applied
    to the release targets before osc release runs.
    """
    apiurl: str = osc.conf.config["apiurl"]

    root_path = REPO_ROOT
    root_obs = args.rootprj

    projects = list(find_projects(root_path, root_obs))
    if not projects:
        _print_ok("release-pr: no projects found")
        return

    # Discover production project counterparts by reading <releasetarget>
    # elements from each PR project's live OBS meta.  Sync those production
    # project configs before releasing so that any repo or arch changes
    # introduced by the PR are applied to the release targets first.
    prod_to_path: dict[str, Path] = {}
    for pr_obs_name, proj_path in projects:
        if not _obs_project_exists(apiurl, pr_obs_name):
            continue
        prod_proj = _fetch_releasetarget_project(apiurl, pr_obs_name)
        if prod_proj:
            prod_to_path[prod_proj] = proj_path

    if prod_to_path:
        # production_rootprj is the shallowest project (fewest ':' separators).
        production_rootprj = min(prod_to_path, key=lambda x: x.count(":"))
        # Seed from profile/CLI env vars (already merged into args.env_overrides
        # by cli.py) so that variables like REMOTE_OBS_ORG_INTERCONNECT are
        # defined, then override OBS_ROOTPRJ with the production rootprj.
        env_vars: dict[str, str] = {
            **(parse_env_overrides(args.env_overrides) if args.env_overrides else {}),
            "OBS_ROOTPRJ": production_rootprj,
        }
        _print_action("release-pr: syncing production project configs")
        for prod_obs_name, proj_path in prod_to_path.items():
            _apply_project_config(
                apiurl,
                prod_obs_name,
                proj_path,
                production_rootprj,
                env_vars=env_vars,
            )

    released = 0
    skipped = 0
    for obs_name, _ in projects:
        if not _obs_project_exists(apiurl, obs_name):
            skipped += 1
            continue
        _print_pending(f"osc release  {obs_name}")
        result = subprocess.run(
            [_OSC_BIN, "-A", apiurl, "release", obs_name, "--no-delay"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"warning: osc release {obs_name} exited {result.returncode}: "
                f"{result.stderr.strip()}",
                flush=True,
            )
        else:
            released += 1
            _print_ok(f"released  {obs_name}")

    suffix = f"({released} released, {skipped} skipped — not on OBS)"
    _print_ok(f"release-pr done  {suffix}")
