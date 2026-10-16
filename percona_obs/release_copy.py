"""Shared mechanics of the two release hops.

Hop 1 (``sync prerelease``): staging → per-PR pre-release project.
Hop 2 (``sync release --from``): pre-release → release project.
Both apply mirror project.yaml meta to the target tree, copy binaries with
``osc release`` and verify the copy landed.  The legacy single-hop
``sync release`` (no ``--from``) uses the same primitives.

``osc release`` requires ``<releasetarget trigger="manual">`` entries on the
source, so a copy adds them, runs ``osc release`` and removes
them again in a ``finally`` — the source meta is unchanged at rest.
"""

import os
import subprocess
import sys
from pathlib import Path

from .common import (
    _REPO_DIR,
    _print_ok,
    _print_pending,
    find_projects,
    resolve_project_path,
)
from .obs_api import (
    _add_release_targets,
    _apply_project_config,
    _disable_project_builds,
    _fetch_obs_project_repository_names,
    _fetch_obs_subproject_names,
    _read_project_release_source,
    _remove_release_targets,
    set_project_description_marker,
)
from .project_config import project_in_slice
from .release_freeze import verify_release_landed

_OSC_BIN = os.path.join(os.path.dirname(sys.executable), "osc")


def collect_release_subprojects(
    source_project_id: str,
    release_path: Path,
) -> "tuple[list[tuple[str, Path]], list[str]]":
    """Map source subprojects to their release-mirror directories.

    Returns (pairs, missing):
      pairs   — [(subproject_name, release_sub_path)] for every source
                subproject whose mirror project.yaml exists.
      missing — subproject names with no mirror project.yaml.  Full-snapshot
                releases require a mirror for every subproject; callers must
                treat a non-empty list as a hard error.

    Subprojects out of the active slice are skipped on both sides; `missing`
    lists only in-slice source subprojects without a mirror.
    """
    source_path = resolve_project_path(source_project_id)
    pairs: list[tuple[str, Path]] = []
    missing: list[str] = []
    for sub_obs_id, sub_path in find_projects(source_path, source_project_id):
        if sub_obs_id == source_project_id:
            continue
        if not (sub_path / "project.yaml").is_file():
            continue  # intermediate directory, not a real OBS project
        subproject_name = sub_obs_id[len(source_project_id) + 1 :]
        release_sub_path = release_path / Path(*subproject_name.split(":"))
        if (release_sub_path / "project.yaml").is_file():
            if project_in_slice(release_sub_path):
                pairs.append((subproject_name, release_sub_path))
            # else: this instance does not hold the subproject — nothing to release
        elif project_in_slice(sub_path):
            missing.append(subproject_name)
        # else: source out of slice too; a missing mirror is irrelevant here
    return pairs, missing


def filter_release_repo_names(
    apiurl: str,
    source_repo_names: "list[str]",
    release_obs_project: str,
) -> "list[str]":
    """Keep only source repos that exist in the release project.

    Adding a <releasetarget> for a repo the target lacks makes osc release
    fail or drop binaries; a mismatch here means the mirror regeneration and
    the live release project disagree, which is worth a loud warning but not
    an abort (the mirror was just applied — a leftover mismatch is repo
    removal pending on OBS's side).
    """
    target = _fetch_obs_project_repository_names(apiurl, release_obs_project)
    kept = [r for r in source_repo_names if r in target]
    for r in source_repo_names:
        if r not in target:
            print(
                f"warning: source repo {r} has no counterpart in "
                f"{release_obs_project}; skipped",
                flush=True,
            )
    return kept


def apply_mirror_meta(
    apiurl: str,
    target_obs_project: str,
    mirror_path: Path,
    rootprj: str,
    env_vars: "dict[str, str]",
    *,
    publish_override: "dict[str, bool] | bool | None" = None,
    branch_rootprj: "str | None" = None,
    active_projects: "set[str] | None" = None,
    branch_fallbacks: bool = True,
) -> None:
    """Create or update *target_obs_project* from the mirror project.yaml and
    make sure builds are disabled.  Two passes when OBS stripped paths.

    ``branch_rootprj``/``active_projects`` enable the same path redirection
    ``sync push --branch-from`` uses: a ``subproject:`` path whose project is
    not in ``active_projects`` is rewritten to ``<branch_rootprj>:<subproject>``
    (hop 1: the pre-release tree is the active set, production is the branch
    root).
    """
    paths_stripped, _ = _apply_project_config(
        apiurl,
        target_obs_project,
        mirror_path,
        rootprj,
        env_vars=env_vars,
        publish_override=publish_override,
        branch_rootprj=branch_rootprj,
        active_projects=active_projects,
        branch_fallbacks=branch_fallbacks,
    )
    if paths_stripped:
        _apply_project_config(
            apiurl,
            target_obs_project,
            mirror_path,
            rootprj,
            env_vars=env_vars,
            publish_override=publish_override,
            branch_rootprj=branch_rootprj,
            active_projects=active_projects,
            branch_fallbacks=branch_fallbacks,
        )
    _disable_project_builds(apiurl, target_obs_project)


def copy_project_binaries(
    apiurl: str, source_obs_project: str, target_obs_project: str
) -> None:
    """``osc release`` every repo of *source* that exists in *target*."""
    # Self-heal leftovers of a killed earlier run before reading the meta.
    _remove_release_targets(apiurl, source_obs_project, target_obs_project)
    repo_elems, _ = _read_project_release_source(apiurl, source_obs_project)
    repo_names = filter_release_repo_names(
        apiurl,
        [r.get("name", "") for r in repo_elems if r.get("name")],
        target_obs_project,
    )
    _add_release_targets(apiurl, source_obs_project, target_obs_project, repo_names)
    try:
        _print_pending(f"releasing {source_obs_project} → {target_obs_project}")
        subprocess.run(
            [
                _OSC_BIN,
                "-A",
                apiurl,
                "release",
                source_obs_project,
                "--no-delay",
            ],
            check=True,
        )
    finally:
        _remove_release_targets(apiurl, source_obs_project, target_obs_project)
    _print_ok(f"released  {source_obs_project} → {target_obs_project}")


def warn_orphans(
    apiurl: str,
    target_obs_project: str,
    pairs: "list[tuple[str, Path]]",
    rootprj: str,
) -> None:
    """Report target-tier OBS subprojects with no local mirror (never deleted)."""
    local_names = {name for name, _ in pairs}
    for obs_sub in sorted(_fetch_obs_subproject_names(apiurl, target_obs_project)):
        sub_name = obs_sub[len(target_obs_project) + 1 :]
        if sub_name not in local_names:
            print(
                f"warning: orphaned release subproject on OBS: {obs_sub} "
                "(no local mirror) — remove manually with "
                f"'percona-obs sync delete {obs_sub[len(rootprj) + 1 :]}'",
                flush=True,
            )


def release_tree(
    apiurl: str,
    source_obs_project: str,
    target_obs_project: str,
    pairs: "list[tuple[str, Path]]",
    rootprj: str,
    env_vars: "dict[str, str]",
    *,
    publish_override: "dict[str, bool] | bool | None" = None,
    verify_timeout: int = 600,
    branch_rootprj: "str | None" = None,
    active_projects: "set[str] | None" = None,
    branch_fallbacks: bool = True,
    release_id: "str | None" = None,
) -> None:
    """Copy the top project and every (subproject, mirror) pair, then verify.

    The caller has already applied the top project's meta (that happens
    before any freeze); subproject meta is applied here, right before each
    subproject's copy, exactly as the single-hop release always did.

    With *release_id*, every target project gets ``release_id: <id>`` as the
    last description line after its meta is applied and before its
    ``osc release``, so the description already names the release when the
    binaries land.
    """
    if release_id:
        set_project_description_marker(
            apiurl, target_obs_project, "release_id", release_id
        )
    copy_project_binaries(apiurl, source_obs_project, target_obs_project)
    for subproject_name, mirror_path in pairs:
        target_sub = f"{target_obs_project}:{subproject_name}"
        apply_mirror_meta(
            apiurl,
            target_sub,
            mirror_path,
            rootprj,
            env_vars,
            publish_override=publish_override,
            branch_rootprj=branch_rootprj,
            active_projects=active_projects,
            branch_fallbacks=branch_fallbacks,
        )
        if release_id:
            set_project_description_marker(apiurl, target_sub, "release_id", release_id)
        copy_project_binaries(
            apiurl, f"{source_obs_project}:{subproject_name}", target_sub
        )
    if verify_timeout > 0:
        verify_release_landed(
            apiurl, source_obs_project, target_obs_project, timeout_s=verify_timeout
        )
        for subproject_name, _ in pairs:
            verify_release_landed(
                apiurl,
                f"{source_obs_project}:{subproject_name}",
                f"{target_obs_project}:{subproject_name}",
                timeout_s=verify_timeout,
            )
    warn_orphans(apiurl, target_obs_project, pairs, rootprj)
