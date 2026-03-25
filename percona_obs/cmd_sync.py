import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import osc.conf
import osc.core

from .cmd_profile import _load_profile, _load_profile_env_strings
from .cmd_project import (
    _validate_obs_scm_revisions,
    _validate_project_path_refs,
    _validate_subproject_refs,
)
from .common import (
    REPO_ROOT,
    _REPO_DIR,
    _build_aggregate_xml,
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
    logger,
    parse_env_overrides,
    resolve_project_path,
)
from .git_utils import (
    _check_git_clean,
    _generate_sync_message,
    _has_non_obs_package_changes_since,
    _has_package_changes_since,
)
from .obs_api import (
    _apply_package_config,
    _apply_project_config,
    _create_project_skeleton,
    _delete_obs_package,
    _delete_obs_project,
    _fetch_combined_depinfo,
    _fetch_obs_file_content,
    _fetch_obs_file_md5s,
    _fetch_obs_package_latest_comment,
    _fetch_obs_package_meaningful_comment,
    _fetch_obs_package_names,
    _fetch_obs_project_repository_names,
    _fetch_obs_subproject_names,
    _obs_project_exists,
    _upload_obs_files,
)
from .services import (
    _get_all_obs_scm_infos,
    _get_packaging_obs_scm_infos,
    _git_head_sha,
    _has_manual_services,
    _run_local_services,
)
from .targets import _iter_project_chain, _resolve_targets

# Matches the standard sync commit message: sync: <branch>@<sha> (<detail>)
_SYNC_MSG_RE = re.compile(r"^sync: [^@]+@([0-9a-f]+) \((.+)\)$")
# Matches a branch aggregate message: branch: <profile> (<obs_project>/<package>)
# Group 1 = profile name, group 2 = source OBS project.
_BRANCH_MSG_RE = re.compile(r"^branch: (\S+) \((.+)/[^/]+\)$")


_OBS_SUBSTITUTABLE = {"_service", "_aggregate", "_link"}


def _copy_with_env_subst(
    src: Path, dst_dir: Path, env_vars: dict[str, str] | None
) -> None:
    """Copy src into dst_dir, substituting ${VAR} tokens for substitutable obs files."""
    if env_vars and src.name in _OBS_SUBSTITUTABLE:
        text = apply_env_substitution(src.read_text("utf-8"), env_vars, source=src)
        (dst_dir / src.name).write_text(text, "utf-8")
    else:
        shutil.copy2(src, dst_dir / src.name)


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


def _multibuild_packages(obs_dir: Path, base_name: str) -> list[str]:
    """Return the OBS package names to use in an _aggregate for base_name.

    For plain packages: [base_name].
    For multibuild packages: ["{base_name}:{flavor}", ...] plus the bare
    base_name if buildemptyflavor is absent or not "false".
    """
    multibuild_file = obs_dir / "_multibuild"
    if not multibuild_file.is_file():
        return [base_name]
    try:
        root = ET.parse(multibuild_file).getroot()
    except ET.ParseError:
        return [base_name]
    flavors = [el.text.strip() for el in root.findall("flavor") if el.text]
    if not flavors:
        return [base_name]
    include_empty = root.get("buildemptyflavor", "true").lower() != "false"
    packages = [f"{base_name}:{flavor}" for flavor in flavors]
    if include_empty:
        packages.append(base_name)
    return packages


def _content_matches_branch(
    apiurl: str,
    branch_project: str,
    package_name: str,
    obs_dir: Path,
    env_vars: dict[str, str] | None = None,
    check_obsinfo: bool = True,
) -> bool:
    """Return True if local obs/ files match what is in branch_project on OBS.

    Two checks are performed:
    1. MD5s of all local obs/ files must match the corresponding files on OBS.
       For files in _OBS_SUBSTITUTABLE (_service, _aggregate, _link), env_vars
       substitution is applied before computing the MD5 so that tokens like
       ${PERCONA_OBS_PACKAGING_BRANCH} compare correctly against the expanded
       content that percona-obs uploaded to OBS.
    2. (Only when ``check_obsinfo`` is True) For every obs_scm service present
       (upstream source and packaging subdirs such as debian/ or rpm/), the
       commit hash recorded in the OBS obsinfo file must match the current
       remote HEAD.

    Used as a fallback when the branch was synced with --dirty (so the revision
    SHA in the commit message cannot be trusted for git-log comparison).

    Pass ``check_obsinfo=False`` when the caller has already verified via
    git-log that the only file-level changes are cosmetic (e.g. env-var
    substitutions).  In that case the obsinfo comparison would produce false
    positives whenever the remote branch has advanced without touching the
    package's actual content.
    """
    obs_md5s = _fetch_obs_file_md5s(apiurl, branch_project, package_name, expanded=True)
    if not obs_md5s:
        logger.debug(f"content check: no files in {branch_project}/{package_name}")
        return False

    for filepath in sorted(obs_dir.iterdir()):
        if not filepath.is_file():
            continue
        if env_vars and filepath.name in _OBS_SUBSTITUTABLE:
            content = apply_env_substitution(
                filepath.read_text("utf-8"), env_vars, source=filepath
            ).encode("utf-8")
        else:
            content = filepath.read_bytes()
        local_md5 = hashlib.md5(content).hexdigest()
        if obs_md5s.get(filepath.name) != local_md5:
            logger.debug(
                f"content check: {filepath.name} differs  {branch_project}/{package_name}"
            )
            return False

    if not check_obsinfo:
        return True

    service_file = obs_dir / "_service"
    if not service_file.is_file():
        return True

    scm_infos = _get_all_obs_scm_infos(service_file, env_vars)
    if not scm_infos:
        return True  # no obs_scm services; file MD5 match is sufficient

    for filename_prefix, scm_url, scm_revision, _subdir in scm_infos:
        head_sha = _git_head_sha(scm_url, scm_revision)
        if not head_sha:
            logger.debug(
                f"content check: cannot resolve remote HEAD for {scm_url}@{scm_revision}"
            )
            return False  # conservative: can't verify → treat as changed

        # OBS stores service-generated files with a "_service:<name>:" prefix when
        # the service runs server-side; match both the bare name and that prefix.
        _obs_scm_prefix = f"_service:obs_scm:{filename_prefix}"
        obsinfo_name = next(
            (
                name
                for name in obs_md5s
                if (
                    name.startswith(filename_prefix) or name.startswith(_obs_scm_prefix)
                )
                and name.endswith(".obsinfo")
            ),
            None,
        )
        if not obsinfo_name:
            logger.debug(
                f"content check: no obsinfo for {filename_prefix!r} "
                f"in {branch_project}/{package_name}"
            )
            return False

        obsinfo_bytes = _fetch_obs_file_content(
            apiurl, branch_project, package_name, obsinfo_name, expanded=True
        )
        if not obsinfo_bytes:
            return False

        obs_commit: str | None = None
        for line in obsinfo_bytes.decode("utf-8", errors="replace").splitlines():
            if line.startswith("commit:"):
                obs_commit = line.split(":", 1)[1].strip() or None
                break

        if obs_commit != head_sha:
            logger.debug(
                f"content check: obs_scm commit mismatch for {filename_prefix!r} "
                f"(OBS={obs_commit!r}, remote={head_sha!r})  {branch_project}/{package_name}"
            )
            # Before treating this as changed, check whether any commits in
            # the range actually touch this subdir.  Only applies to
            # packaging subdirs (e.g. root/.../debian, root/.../rpm) which
            # are tracked in the local repo; upstream obs_scm services have
            # an empty subdir and remain conservatively strict.
            if _subdir and obs_commit:
                try:
                    git_result = subprocess.run(
                        [
                            "git",
                            "log",
                            "--oneline",
                            f"{obs_commit}..{head_sha}",
                            "--",
                            _subdir,
                        ],
                        capture_output=True,
                        text=True,
                        cwd=_REPO_DIR,
                        timeout=15,
                    )
                    if git_result.returncode == 0 and not git_result.stdout.strip():
                        logger.debug(
                            f"content check: no commits touch {_subdir!r} in range; "
                            f"treating as match  {branch_project}/{package_name}"
                        )
                        continue  # this scm service matches; check the next one
                except (subprocess.TimeoutExpired, OSError):
                    pass  # cannot verify locally — fall through to conservative behaviour
            return False

    return True


def _packaging_scm_has_updates(
    apiurl: str,
    obs_project: str,
    package_name: str,
    service_file: Path,
    env_vars: dict[str, str] | None,
) -> bool:
    """Return True if any packaging obs_scm service has new commits vs OBS.

    Fetches the .obsinfo for each packaging obs_scm service (debian/ or rpm/)
    and compares the recorded commit hash against the current remote HEAD.
    Returns False when remote HEAD cannot be resolved (conservative: no spurious
    triggers) or when no packaging obs_scm services are present.
    """
    packaging_infos = _get_packaging_obs_scm_infos(service_file, env_vars)
    if not packaging_infos:
        return False
    obs_md5s = _fetch_obs_file_md5s(apiurl, obs_project, package_name, expanded=True)
    for filename_prefix, scm_url, scm_revision, subdir in packaging_infos:
        head_sha = _git_head_sha(scm_url, scm_revision)
        if not head_sha:
            logger.debug(
                f"packaging scm check: cannot resolve remote HEAD "
                f"for {scm_url}@{scm_revision}, skipping trigger"
            )
            continue
        _obs_scm_prefix = f"_service:obs_scm:{filename_prefix}"
        obsinfo_name = next(
            (
                name
                for name in obs_md5s
                if (
                    name.startswith(filename_prefix) or name.startswith(_obs_scm_prefix)
                )
                and name.endswith(".obsinfo")
            ),
            None,
        )
        if not obsinfo_name:
            continue
        obsinfo_bytes = _fetch_obs_file_content(
            apiurl, obs_project, package_name, obsinfo_name, expanded=True
        )
        if not obsinfo_bytes:
            continue
        obs_commit: str | None = None
        for line in obsinfo_bytes.decode("utf-8", errors="replace").splitlines():
            if line.startswith("commit:"):
                obs_commit = line.split(":", 1)[1].strip() or None
                break
        if obs_commit != head_sha:
            # The remote HEAD moved since OBS last fetched.  If we have the
            # subdir, do a local git log check to see whether any of those
            # commits actually touch that directory.  If git log returns empty,
            # there are no packaging changes and no trigger is needed.
            if subdir and obs_commit:
                try:
                    git_result = subprocess.run(
                        [
                            "git",
                            "log",
                            "--oneline",
                            f"{obs_commit}..{head_sha}",
                            "--",
                            subdir,
                        ],
                        capture_output=True,
                        text=True,
                        cwd=_REPO_DIR,
                        timeout=15,
                    )
                    if git_result.returncode == 0 and not git_result.stdout.strip():
                        logger.debug(
                            f"packaging scm: {filename_prefix!r} HEAD moved but "
                            f"no commits touch {subdir!r}, skipping trigger  "
                            f"{obs_project}/{package_name}"
                        )
                        continue
                except (subprocess.TimeoutExpired, OSError):
                    pass  # can't verify locally — fall through to trigger
            logger.debug(
                f"packaging scm: {filename_prefix!r} has new commits "
                f"(OBS={obs_commit!r}, remote={head_sha!r})  {obs_project}/{package_name}"
            )
            return True
    return False


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
    no message, non-sync format, or a dirty sync — compare obs/ file MD5s and
    the upstream obs_scm commit hash against what OBS currently holds.

    ``branch_env_vars`` are the env vars of the branch-from profile.  They
    are used for content comparison so that substitutable tokens (e.g.
    ``${PERCONA_OBS_PACKAGING_BRANCH}``) are expanded the same way they were
    when the branch project was last synced, rather than with the current
    profile's values.  Falls back to ``env_vars`` when not provided.
    """
    check_env_vars = branch_env_vars if branch_env_vars is not None else env_vars

    def _content_check(reason: str, check_obsinfo: bool = True) -> bool:
        logger.debug(f"branch decision: content check  {label}  ({reason})")
        obs_dir = package_path / "obs"
        matches = _content_matches_branch(
            apiurl,
            branch_project,
            package_name,
            obs_dir,
            check_env_vars,
            check_obsinfo=check_obsinfo,
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
    # Git-log found commits since the last sync.  Determine whether the
    # changes touch packaging files (rpm/, debian/, etc.) or only obs/ files.
    #
    # If only obs/ files changed (e.g. a cosmetic env-var rewrite), the
    # obsinfo check would produce a false positive: HEAD advanced but the
    # packaging content fetched by OBS at build time is unchanged.  Skip it.
    #
    # If packaging files changed, the obsinfo check correctly catches the
    # mismatch between OBS's cached commit and the current remote HEAD, so
    # enable it.
    has_packaging_changes = _has_non_obs_package_changes_since(short_sha, package_path)
    return _content_check(
        f"git changes since {short_sha}",
        check_obsinfo=has_packaging_changes,
    )


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

    if not args.dirty:
        _check_git_clean()
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
    path_ref_errors = _validate_project_path_refs(REPO_ROOT, env_vars, apiurl)
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
            parse_env_overrides(_branch_env_strings) if _branch_env_strings else None
        )
    seen_projects: set = set()
    local_project_names: set[str] = set()
    local_packages_by_project: dict[str, set[str]] = {}
    dry_run_obs = args.dry_run or args.dry_run_remote
    # Cache of branch-project → set of repository names, populated lazily in
    # Phase 1.  Avoids a redundant API call per package for the same project.
    _branch_repo_cache: dict[str, set[str]] = {}
    # Cache of project_path → set of target repository names derived from
    # project.yaml.  Avoids repeated YAML parsing for packages in the same
    # project.
    _target_repos_cache: dict[Path, set[str]] = {}

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
                local_project_names.add(prj_name)
                if raw_proj not in all_projects:
                    all_projects[raw_proj] = (prj_name, proj_path)
        sorted_projs = sorted(all_projects.items(), key=lambda kv: kv[1][0].count(":"))
        for _raw, (prj_name, proj_path) in sorted_projs:
            _create_project_skeleton(
                apiurl, prj_name, proj_path, dry_run=dry_run_obs, env_vars=env_vars
            )
        # Stage 2 pass 1: configure all projects.  Projects whose <path>
        # elements reference sibling/child projects that are still skeletons
        # will have those paths stripped and need a second pass.
        needs_reconfig: list[tuple[str, str, Path]] = []
        for raw_proj, (prj_name, proj_path) in sorted_projs:
            stripped = _apply_project_config(
                apiurl,
                prj_name,
                proj_path,
                args.rootprj,
                force=args.force,
                dry_run=dry_run_obs,
                env_vars=env_vars,
            )
            if stripped:
                needs_reconfig.append((raw_proj, prj_name, proj_path))
            seen_projects.add(raw_proj)
        # Stage 2 pass 2: re-apply config for projects that had paths stripped.
        # By now all sibling/child projects have their repositories configured,
        # so OBS will accept the full meta.  Projects already correctly
        # configured are detected by _project_meta_subset_equal and skipped.
        for raw_proj, prj_name, proj_path in needs_reconfig:
            _apply_project_config(
                apiurl,
                prj_name,
                proj_path,
                args.rootprj,
                force=args.force,
                dry_run=dry_run_obs,
                env_vars=env_vars,
            )

    if args.project_only:
        if args.dry_run:
            suffix = " (dry run)"
        elif args.dry_run_remote:
            suffix = " (dry run: remote)"
        else:
            suffix = ""
        _print_ok(f"sync successful{suffix}")
        return

    # --- Phase 1: compute branch/promote decisions upfront ---
    # decisions[(obs_project_name, pkg_name)]:
    #   "aggregate"   — upload _aggregate pointing to branch_project_for[key]
    #   "skip_branch" — leave existing aggregate on OBS unchanged (no upload)
    #   "promote"     — upload full obs/ sources
    decisions: dict[tuple[str, str], str] = {}
    branch_project_for: dict[tuple[str, str], str] = {}
    # profile that was used in the branch: comment (plain-push path only).
    branch_profile_for: dict[tuple[str, str], str] = {}
    # pkg_key_by_name[(pkg_name)] → key, used for dep propagation lookups.
    pkg_key_by_name: dict[str, tuple[str, str]] = {}
    # Cache of loaded profiles to avoid repeated file reads within Phase 1.
    _profile_apiurl_cache: dict[str, str] = {}

    _print_action("planning: checking sync decisions")
    for obs_project, package_path in targets:
        obs_dir = package_path / "obs"
        if not obs_dir.is_dir():
            continue
        project_path = package_path.parent
        project_config = load_yaml(project_path / "project.yaml")
        obs_project_name = project_config.get("name") or obs_project
        key: tuple[str, str] = (obs_project_name, package_path.name)
        pkg_key_by_name[package_path.name] = key

        if branch_rootprj:
            branch_project = _compute_branch_project(
                obs_project_name, args.rootprj, branch_rootprj
            )
            use_aggregate = _resolve_branch_decision(
                apiurl,
                branch_project,
                package_path.name,
                package_path,
                env_vars,
                branch_env_vars=branch_env_vars,
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
                    decisions[key] = "promote"
                else:
                    decisions[key] = "aggregate"
                    branch_project_for[key] = branch_project
            else:
                decisions[key] = "promote"
        else:
            # Without --branch-from the package may still hold a _aggregate from
            # a prior --branch-from sync.  Check whether content still matches.
            prior_comment = _fetch_obs_package_latest_comment(
                apiurl, obs_project_name, package_path.name
            )
            if prior_comment:
                bm = _BRANCH_MSG_RE.match(prior_comment)
                if bm:
                    branch_profile_name = bm.group(1)
                    src_proj = bm.group(2)
                    # Resolve the apiurl for this branch profile; it may be on a
                    # different OBS instance (cross-instance branching).
                    if branch_profile_name not in _profile_apiurl_cache:
                        try:
                            bp = _load_profile(branch_profile_name)
                            _profile_apiurl_cache[branch_profile_name] = (
                                bp.get("apiurl") or apiurl or ""
                            )
                        except SystemExit:
                            logger.debug(
                                f"branch profile {branch_profile_name!r} not found,"
                                f" falling back to target apiurl for {src_proj}"
                            )
                            _profile_apiurl_cache[branch_profile_name] = apiurl or ""
                    src_apiurl = _profile_apiurl_cache[branch_profile_name]
                    if _content_matches_branch(
                        src_apiurl, src_proj, package_path.name, obs_dir, env_vars
                    ):
                        decisions[key] = "skip_branch"
                    else:
                        decisions[key] = "promote"
                    # Always record the source project and profile so that Phase 2
                    # dep queries use the correct OBS instance.
                    branch_project_for[key] = src_proj
                    branch_profile_for[key] = branch_profile_name
                else:
                    decisions[key] = "promote"
            else:
                decisions[key] = "promote"

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
                src_apiurl = _profile_apiurl_cache.get(profile_name) or apiurl or ""
                src_projects_by_apiurl.setdefault(src_apiurl, set()).add(src_proj)
            dep_projects = {key[0] for key in decisions} | set(
                branch_project_for.values()
            )
        _print_action(
            f"planning: checking build dependencies ({len(dep_projects)} project(s))"
        )
        if branch_rootprj:
            fwd_deps = _fetch_combined_depinfo(
                branch_apiurl, dep_projects, local_pkg_names
            )
        else:
            all_fwd_deps: dict[str, set[str]] = {}
            for q_apiurl, q_projects in src_projects_by_apiurl.items():
                partial = _fetch_combined_depinfo(q_apiurl, q_projects, local_pkg_names)
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
                        ):
                            _print_action(
                                f"dep-promote: {dep_key[0]}/{dep_key[1]}"
                                f"  (depends on promoted {pkg_name})"
                            )
                            decisions[dep_key] = "promote"
                            changed = True

    # --- Phase 3: execute uploads based on decisions ---
    for obs_project, package_path in targets:
        project_path = package_path.parent
        project_config = load_yaml(project_path / "project.yaml")
        obs_project_name = project_config.get("name") or obs_project

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
                            dry_run=dry_run_obs,
                            env_vars=env_vars,
                        )
                chain_needs_reconfig: list[tuple[str, str, Path]] = []
                for raw_proj, (prj_name, proj_path) in sorted_chain:
                    if raw_proj not in seen_projects:
                        stripped = _apply_project_config(
                            apiurl,
                            prj_name,
                            proj_path,
                            args.rootprj,
                            force=args.force,
                            dry_run=dry_run_obs,
                            env_vars=env_vars,
                        )
                        if stripped:
                            chain_needs_reconfig.append((raw_proj, prj_name, proj_path))
                        seen_projects.add(raw_proj)
                for raw_proj, prj_name, proj_path in chain_needs_reconfig:
                    _apply_project_config(
                        apiurl,
                        prj_name,
                        proj_path,
                        args.rootprj,
                        force=args.force,
                        dry_run=dry_run_obs,
                        env_vars=env_vars,
                    )

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

        obs_dir = package_path / "obs"
        if not obs_dir.is_dir():
            continue

        pkg_vars = {**env_vars, **_pkg_env_vars(package_path)}
        key = (obs_project_name, package_path.name)
        decision = decisions.get(key, "promote")

        if decision == "aggregate":
            bp = branch_project_for[key]
            agg_message = f"branch: {args.branch_from} ({bp}/{package_path.name})"
            pkg_names = _multibuild_packages(obs_dir, package_path.name)
            agg_xml = _build_aggregate_xml(bp, pkg_names)
            agg_dir = Path(tempfile.mkdtemp(prefix="percona-obs-agg-"))
            try:
                (agg_dir / "_aggregate").write_text(agg_xml, encoding="utf-8")
                _upload_obs_files(
                    apiurl,
                    obs_project_name,
                    package_path.name,
                    agg_dir,
                    message=agg_message,
                    dry_run=dry_run_obs,
                )
            finally:
                shutil.rmtree(agg_dir, ignore_errors=True)
            for pkg_name in pkg_names:
                _print_aggregate(f"{obs_project_name}/{pkg_name}  → {bp}/{pkg_name}")
        elif decision == "skip_branch":
            _print_same(f"files  {obs_project_name}/{package_path.name}")
        else:  # "promote"
            message = args.message or _generate_sync_message(args.dirty)
            service_file = obs_dir / "_service"
            run_services = (
                not args.no_services
                and service_file.is_file()
                and _has_manual_services(service_file)
            )
            files_changed = False
            if run_services:
                if args.dry_run and not args.dry_run_remote:
                    # Pure dry-run: cannot run services; show service names and
                    # report obs/ diff as-is.
                    svc_root = ET.parse(service_file).getroot()
                    for svc in svc_root.findall("service"):
                        if svc.get("mode") == "manual":
                            svc_name = svc.get("name", "?")
                            _print_update(
                                f"service {svc_name}  {obs_project_name}/{package_path.name}"
                            )
                    files_changed = _upload_obs_files(
                        apiurl,
                        obs_project_name,
                        package_path.name,
                        obs_dir,
                        message=message,
                        dry_run=True,
                    )
                else:
                    workdir, manual_artifacts = _run_local_services(
                        obs_dir,
                        pkg_label=f"{obs_project_name}/{package_path.name}",
                        cache=not args.no_cache,
                        env_vars=pkg_vars,
                    )
                    try:
                        combined = Path(tempfile.mkdtemp(prefix="percona-obs-upload-"))
                        try:
                            for f in obs_dir.iterdir():
                                if f.is_file():
                                    _copy_with_env_subst(f, combined, pkg_vars)
                            for art_name in manual_artifacts:
                                shutil.copy2(workdir / art_name, combined / art_name)
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
                    for f in obs_dir.iterdir():
                        if f.is_file():
                            _copy_with_env_subst(f, sub_dir, pkg_vars)
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
            # If obs/ files are unchanged but packaging files (debian/ or rpm/)
            # may have been pushed to the repo, trigger an OBS service run so
            # OBS re-fetches those subtrees and queues a rebuild.
            if not files_changed and service_file.is_file():
                if _packaging_scm_has_updates(
                    apiurl,
                    obs_project_name,
                    package_path.name,
                    service_file,
                    pkg_vars,
                ):
                    _print_pending(f"trigger  {obs_project_name}/{package_path.name}")
                    if dry_run_obs:
                        _print_ok(
                            f"trigger  {obs_project_name}/{package_path.name}  [dry-run]"
                        )
                    else:
                        osc.core.runservice(apiurl, obs_project_name, package_path.name)
                        _print_ok(f"trigger  {obs_project_name}/{package_path.name}")

    # --- orphan cleanup ---
    # Remove packages on OBS that no longer exist locally, but only when the
    # full package set of a project was processed (not a single-package sync).
    if args.package is None:
        for proj_name, local_pkgs in local_packages_by_project.items():
            obs_pkgs = _fetch_obs_package_names(apiurl, proj_name)
            for orphan in sorted(obs_pkgs - local_pkgs):
                _delete_obs_package(apiurl, proj_name, orphan, dry_run_obs)

    # Remove subprojects on OBS that no longer exist locally, but only when
    # the full tree was processed (not a single-project or single-package sync).
    # Delete deepest subprojects first so parents are empty before deletion.
    if args.project is None:
        obs_subprojects = _fetch_obs_subproject_names(apiurl, args.rootprj)
        orphan_projects = obs_subprojects - local_project_names
        for orphan_proj in sorted(orphan_projects, key=lambda x: -x.count(":")):
            _delete_obs_project(apiurl, orphan_proj, dry_run_obs, recursive=True)

    if args.dry_run:
        suffix = " (dry run)"
    elif args.dry_run_remote:
        suffix = " (dry run: remote)"
    else:
        suffix = ""
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
    if not args.dirty:
        _check_git_clean()

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
        message = args.message or _generate_sync_message(args.dirty)
        service_file = obs_dir / "_service"
        run_services = (
            not args.no_services
            and service_file.is_file()
            and _has_manual_services(service_file)
        )
        if run_services and not dry_run:
            workdir, manual_artifacts = _run_local_services(
                obs_dir,
                pkg_label=f"{obs_project_name}/{package_path.name}",
                cache=not args.no_cache,
                env_vars=pkg_vars,
            )
            try:
                combined = Path(tempfile.mkdtemp(prefix="percona-obs-upload-"))
                try:
                    for f in obs_dir.iterdir():
                        if f.is_file():
                            _copy_with_env_subst(f, combined, pkg_vars)
                    for art_name in manual_artifacts:
                        shutil.copy2(workdir / art_name, combined / art_name)
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
