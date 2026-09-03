# percona_obs/release_freeze.py
"""Staging freeze helpers for ``sync release``.

``osc release`` copies whatever binaries the source repos hold at that
instant.  To guarantee a release ships a coherent, fully-built snapshot,
``sync release`` wraps the copy in:

  drain (scheduler idle) -> assert green -> freeze (build disable) ->
  osc release -> restore (exact prior meta)

The green assertion MUST run before the freeze: a disabled project reports
``disabled`` for every package, so it can no longer be verified.
"""

import time
import xml.etree.ElementTree as ET

import osc.connection
import osc.core

from .common import _decode_obs_response, _print_pending, _print_same, _print_update
from .obs_api import _edit_project_meta, _fetch_obs_package_names

# Package codes meaning the scheduler is still working on the package.
PENDING_PKG_CODES = frozenset(
    {"building", "scheduled", "dispatching", "blocked", "signing", "finished"}
)
# Repo-level states meaning the repository has not settled yet.
PENDING_REPO_STATES = frozenset(
    {"scheduling", "blocked", "building", "finished", "publishing"}
)
# Package codes accepted as green.
GREEN_PKG_CODES = frozenset({"succeeded", "excluded", "disabled", "locked"})


def fetch_project_results(
    apiurl: str, obs_project: str
) -> "tuple[dict[tuple[str, str, str], str], dict[tuple[str, str], str]]":
    """Return (pkg_codes, repo_states) from the project's _result endpoint.

    pkg_codes:  {(package, repo, arch): code}
    repo_states: {(repo, arch): state}  — state is "dirty" when the result
    carries dirty="true", regardless of the reported state attribute.
    """
    url = osc.core.makeurl(apiurl, ["build", obs_project, "_result"])
    root = ET.fromstring(osc.connection.http_GET(url).read())
    pkg_codes: dict[tuple[str, str, str], str] = {}
    repo_states: dict[tuple[str, str], str] = {}
    for result in root.findall("result"):
        repo = result.get("repository", "")
        arch = result.get("arch", "")
        state = result.get("state", "")
        if result.get("dirty") == "true":
            state = "dirty"
        repo_states[(repo, arch)] = state
        for status in result.findall("status"):
            pkg = status.get("package", "")
            if pkg:
                pkg_codes[(pkg, repo, arch)] = status.get("code", "unknown")
    return pkg_codes, repo_states


def _pending_items(apiurl: str, obs_projects: "list[str]") -> "list[str]":
    """Return human-readable descriptions of everything still pending."""
    pending: list[str] = []
    for prj in obs_projects:
        pkg_codes, repo_states = fetch_project_results(apiurl, prj)
        for (repo, arch), state in sorted(repo_states.items()):
            if state in PENDING_REPO_STATES or state == "dirty":
                pending.append(f"{prj} {repo}/{arch}: repository {state}")
        for (pkg, repo, arch), code in sorted(pkg_codes.items()):
            if code in PENDING_PKG_CODES:
                pending.append(f"{prj}/{pkg} {repo}/{arch}: {code}")
    return pending


def wait_for_quiesce(
    apiurl: str,
    obs_projects: "list[str]",
    timeout_s: int = 3600,
    poll_interval_s: int = 30,
) -> None:
    """Block until no project has pending builds or unsettled repositories.

    Raises SystemExit when *timeout_s* elapses first — a source tree that
    never quiesces must be fixed, not released around.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        pending = _pending_items(apiurl, obs_projects)
        if not pending:
            _print_same("source projects quiescent")
            return
        if time.monotonic() >= deadline:
            listing = "\n".join(f"  {p}" for p in pending[:30])
            raise SystemExit(
                f"error: source projects did not quiesce within {timeout_s}s; "
                f"still pending:\n{listing}"
            )
        _print_pending(
            f"waiting for scheduler to drain ({len(pending)} pending, "
            f"retry in {poll_interval_s}s)"
        )
        time.sleep(poll_interval_s)


def assert_all_green(apiurl: str, obs_projects: "list[str]") -> "list[str]":
    """Return [] when every package is green, else the list of problems.

    Anything not in GREEN_PKG_CODES is a problem — including pending codes,
    which should not appear after wait_for_quiesce.
    """
    problems: list[str] = []
    for prj in obs_projects:
        pkg_codes, _ = fetch_project_results(apiurl, prj)
        for (pkg, repo, arch), code in sorted(pkg_codes.items()):
            if code not in GREEN_PKG_CODES:
                problems.append(f"{prj}/{pkg} {repo}/{arch}: {code}")
    return problems


def freeze_builds(apiurl: str, obs_projects: "list[str]") -> "dict[str, str]":
    """Disable builds on every project; return {project: prior_meta_xml}.

    The snapshot is the exact meta XML fetched before modification, so
    restore_builds round-trips per-repo flags (publish, debuginfo, partial
    build enables) without reconstructing them.

    If freezing any project fails partway through, every project frozen so
    far is restored before the exception propagates — otherwise the earlier
    projects would stay build-disabled forever (the caller never receives
    the snapshots dict on an exception).
    """
    snapshots: dict[str, str] = {}
    try:
        for prj in obs_projects:
            raw = _decode_obs_response(osc.core.show_project_meta(apiurl, prj))
            root = ET.fromstring(raw)
            for build_elem in root.findall("build"):
                root.remove(build_elem)
            build_elem = ET.SubElement(root, "build")
            ET.SubElement(build_elem, "disable")
            ET.indent(root, space="  ")
            _edit_project_meta(
                apiurl, prj, ET.tostring(root, encoding="unicode"), force=True
            )
            snapshots[prj] = raw
            _print_update(f"{prj}  (builds frozen)")
    except Exception:
        if snapshots:
            restore_builds(apiurl, snapshots)
        raise
    return snapshots


def restore_builds(apiurl: str, snapshots: "dict[str, str]") -> None:
    """Push snapshotted meta back verbatim.  Never raises: a restore failure
    is printed as a warning so the caller's finally-block does not mask the
    primary exception, and the remaining projects are still restored."""
    for prj, meta in snapshots.items():
        try:
            _edit_project_meta(apiurl, prj, meta, force=True)
            _print_update(f"{prj}  (builds restored)")
        except Exception as exc:
            print(f"warning: failed to restore build flags on {prj}: {exc}", flush=True)


def verify_release_landed(
    apiurl: str,
    source_obs_project: str,
    release_obs_project: str,
    timeout_s: int = 600,
    poll_interval_s: int = 15,
) -> None:
    """Poll until the release project's package set covers the source's.

    ``osc release`` creates one target package per released source package;
    package-set coverage is therefore the observable that the copy landed.
    Raises SystemExit (listing missing packages) on timeout — the run is
    recoverable by re-running ``sync release``, which is idempotent.
    """
    expected = _fetch_obs_package_names(apiurl, source_obs_project)
    if not expected:
        _print_same(f"{source_obs_project}: no packages to verify")
        return
    deadline = time.monotonic() + timeout_s
    while True:
        got = _fetch_obs_package_names(apiurl, release_obs_project)
        missing = sorted(expected - got)
        if not missing:
            _print_same(f"{release_obs_project}: all {len(expected)} packages landed")
            return
        if time.monotonic() >= deadline:
            listing = "\n".join(f"  {m}" for m in missing[:30])
            raise SystemExit(
                f"error: release verification timed out after {timeout_s}s; "
                f"packages missing in {release_obs_project}:\n{listing}\n"
                "Re-run 'sync release' to retry (idempotent)."
            )
        _print_pending(
            f"waiting for {len(missing)} package(s) to land in "
            f"{release_obs_project} (retry in {poll_interval_s}s)"
        )
        time.sleep(poll_interval_s)
