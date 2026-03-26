import copy
import hashlib
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

import osc.conf
import osc.connection
import osc.core
import osc.oscerr

from .common import (
    _YELLOW,
    _GREEN,
    _RED,
    _col,
    _decode_obs_response,
    _load_project_config_with_inheritance,
    _print_create,
    _print_pending,
    _print_remove,
    _print_same,
    _print_update,
    _silence_stdout,
    build_package_meta,
    build_project_meta,
    load_yaml,
    logger,
)


def _obs_api_error(
    e: urllib.error.HTTPError, context: str, body: bytes | None = None
) -> None:
    """Read the OBS HTTP error response body, log it, and exit with a friendly message.

    Parses the OBS XML error envelope (``<status code="..."><summary>...</summary></status>``)
    to show the OBS error code and summary instead of a raw traceback.  Adds an
    actionable hint for well-known error codes such as ``repo_dependency``.

    If *body* is supplied (pre-read bytes), it is used directly instead of reading
    from *e* again (which would fail since the response stream is already consumed).
    """
    if body is None:
        try:
            body = e.read()
        except Exception:
            body = b""
    decoded = body.decode("utf-8", errors="replace") if body else ""
    logger.debug(f"OBS error response body: {decoded!r}")
    code = ""
    summary = f"HTTP {e.code}: {e.reason}"
    if decoded:
        try:
            root = ET.fromstring(decoded)
            code = root.get("code", "")
            summary = (root.findtext("summary") or "").strip() or summary
        except ET.ParseError:
            summary = decoded.strip() or summary
    msg = f"{code}: {summary}" if code else summary
    raise SystemExit(f"error {context}:\n  {msg}")


def _obs_project_exists(apiurl: str, obs_project_name: str) -> bool:
    """Return True if the OBS project already exists, False on any error (e.g. 404)."""
    try:
        osc.core.show_project_meta(apiurl, obs_project_name)
        return True
    except Exception:
        return False


def _fetch_obs_package_latest_comment(
    apiurl: str, obs_project_name: str, package_name: str
) -> str | None:
    """Return the comment from the most recent source revision of an OBS package.

    Returns None if the package does not exist, has no revisions, or on any error.
    """
    logger.debug(f"fetching revision history: {obs_project_name}/{package_name}")
    url = osc.core.makeurl(
        apiurl, ["source", obs_project_name, package_name, "_history"]
    )
    try:
        response = osc.connection.http_GET(url)
        root = ET.fromstring(response.read())
        revisions = root.findall("revision")
        if not revisions:
            return None
        last = revisions[-1]
        comment = last.findtext("comment")
        return comment.strip() if comment else None
    except Exception:
        return None


_TRIGGER_SERVICE_COMMENT = "trigger service run"


def _fetch_obs_package_meaningful_comment(
    apiurl: str, obs_project_name: str, package_name: str
) -> str | None:
    """Return the most recent revision comment that is not 'trigger service run'.

    Walks the revision history from newest to oldest, skipping any revision
    whose comment is exactly 'trigger service run' (case-insensitive).  This
    allows the fast-path SHA comparison in --branch-from to work even when OBS
    has created one or more 'trigger service run' revisions on top of the last
    percona-obs sync.

    Returns None if no meaningful comment exists, if the package does not
    exist, or on any error.
    """
    logger.debug(f"fetching revision history: {obs_project_name}/{package_name}")
    url = osc.core.makeurl(
        apiurl, ["source", obs_project_name, package_name, "_history"]
    )
    try:
        response = osc.connection.http_GET(url)
        root = ET.fromstring(response.read())
        for rev in reversed(root.findall("revision")):
            comment = rev.findtext("comment")
            if comment and comment.strip().lower() != _TRIGGER_SERVICE_COMMENT:
                return comment.strip()
        return None
    except Exception:
        return None


def _fetch_obs_file_md5s(
    apiurl: str, obs_project_name: str, package_name: str, expanded: bool = False
) -> dict[str, str]:
    """Return {filename: md5} for files currently stored in the OBS package source.

    Returns an empty dict if the package does not yet exist or on any error,
    which causes all local files to be uploaded unconditionally.
    """
    logger.debug(f"fetching file list: {obs_project_name}/{package_name}")
    url = osc.core.makeurl(
        apiurl,
        ["source", obs_project_name, package_name],
        query={"expand": "1"} if expanded else None,
    )
    try:
        response = osc.connection.http_GET(url)
        root = ET.fromstring(response.read())
        return {
            entry.get("name", ""): entry.get("md5", "")
            for entry in root.findall("entry")
            if entry.get("name")
        }
    except Exception:
        return {}


def _fetch_obs_file_content(
    apiurl: str,
    obs_project_name: str,
    package_name: str,
    filename: str,
    expanded: bool = False,
) -> bytes | None:
    """Fetch the raw bytes of a single file from an OBS package source.

    Returns None if the package or file does not exist or on any error.
    """
    logger.debug(f"fetching file content: {obs_project_name}/{package_name}/{filename}")
    url = osc.core.makeurl(
        apiurl,
        ["source", obs_project_name, package_name, filename],
        query={"expand": "1"} if expanded else None,
    )
    try:
        response = osc.connection.http_GET(url)
        return response.read()
    except Exception as exc:
        logger.debug(
            f"fetching file content failed: {obs_project_name}/{package_name}/{filename}: {exc}"
        )
        return None


def _fetch_obs_package_names(apiurl: str, obs_project_name: str) -> set[str]:
    """Return the set of package names currently in an OBS project.

    Returns an empty set if the project does not exist or on any error.
    """
    try:
        return {p for p in osc.core.meta_get_packagelist(apiurl, obs_project_name) if p}
    except Exception:
        return set()


def _fetch_obs_subproject_names(apiurl: str, rootprj: str) -> set[str]:
    """Return all OBS project names that are direct or indirect subprojects of rootprj.

    A subproject is any project whose name starts with '<rootprj>:'.
    Returns an empty set on any error.
    """
    try:
        prefix = rootprj + ":"
        return {
            p for p in osc.core.meta_get_project_list(apiurl) if p.startswith(prefix)
        }
    except Exception:
        return set()


def _fetch_obs_project_repository_names(apiurl: str, obs_project: str) -> set[str]:
    """Return the repository names configured for an OBS project.

    Uses the /build/{project} endpoint which lists only repositories that are
    actually configured (unlike /source/{project}/_meta which may include
    disabled repositories in a different form).  Returns an empty set if the
    project does not exist or on any error.
    """
    try:
        url = osc.core.makeurl(apiurl, ["build", obs_project])
        root = ET.fromstring(osc.connection.http_GET(url).read())
        return {e.get("name", "") for e in root.findall("entry") if e.get("name")}
    except Exception as exc:
        logger.debug(
            f"_fetch_obs_project_repository_names: failed for {obs_project!r}: {exc}"
        )
        return set()


def _fetch_combined_depinfo(
    apiurl: str, branch_projects: set[str], local_pkg_names: set[str]
) -> dict[str, set[str]]:
    """Return a forward build-dependency map across multiple OBS branch projects.

    Queries _builddepinfo for each project in branch_projects, merges the
    provided_by maps (binary → source package), then builds a forward dep map:
    fwd_deps[A] = set of source packages that A build-depends on, filtered to
    packages whose names appear in local_pkg_names.

    Because OBS _builddepinfo for a project includes packages inherited via
    <path> entries, querying branch projects gives the full cross-project dep
    graph.  Returns {} if no project has build results yet or on any error.
    """
    # Collect provided_by and all <package> elements from all branch projects.
    provided_by: dict[str, str] = {}  # binary_name → source_pkg
    all_pkg_elems: list[tuple[ET.Element, str]] = []

    for obs_project in branch_projects:
        try:
            repo_url = osc.core.makeurl(apiurl, ["build", obs_project])
            repo_root = ET.fromstring(osc.connection.http_GET(repo_url).read())
            repos = [
                e.get("name", "") for e in repo_root.findall("entry") if e.get("name")
            ]
            if not repos:
                continue
            arch_url = osc.core.makeurl(apiurl, ["build", obs_project, repos[0]])
            arch_root = ET.fromstring(osc.connection.http_GET(arch_url).read())
            archs = [
                e.get("name", "") for e in arch_root.findall("entry") if e.get("name")
            ]
            if not archs:
                continue
            dep_url = osc.core.makeurl(
                apiurl, ["build", obs_project, repos[0], archs[0], "_builddepinfo"]
            )
            dep_root = ET.fromstring(osc.connection.http_GET(dep_url).read())
        except Exception as exc:
            logger.debug(
                f"_fetch_combined_depinfo: error fetching {obs_project}: {exc}"
            )
            continue

        for pkg_elem in dep_root.findall("package"):
            raw_src = pkg_elem.get("name", "")
            if not raw_src:
                continue
            # Strip multibuild flavor suffix (e.g. "pkg:flavor" → "pkg") so
            # that dep lookups always use the base package name.
            src = raw_src.split(":")[0]
            all_pkg_elems.append((pkg_elem, src))
            for subpkg in pkg_elem.findall("subpkg"):
                binary = (subpkg.text or "").strip()
                if binary:
                    provided_by[binary] = src

    # Build forward dep map: fwd_deps[A] = {local packages A depends on}.
    fwd_deps: dict[str, set[str]] = {}
    for pkg_elem, src in all_pkg_elems:
        if not src:
            continue
        for pkgdep in pkg_elem.findall("pkgdep"):
            binary = (pkgdep.text or "").strip()
            provider = provided_by.get(binary)
            if provider and provider != src and provider in local_pkg_names:
                fwd_deps.setdefault(src, set()).add(provider)

    return fwd_deps


def _create_project_skeleton(
    apiurl: str,
    obs_project_name: str,
    project_path: Path,
    rootprj: str = "",
    dry_run: bool = False,
    env_vars: dict[str, str] | None = None,
) -> None:
    """Create a bare OBS project (no repositories) if it does not already exist.

    This is Stage 1 of a two-stage project creation process.  Creating projects
    without repository entries avoids repository_access_failure errors caused by
    forward references to sibling or child projects that have not been created
    yet.  Stage 2 (_apply_project_config) fills in the full repository config
    once every project in the tree exists.

    When *rootprj* is given and the project does not yet exist, person/group
    elements are copied from the root project so that new subprojects inherit
    the same access rights from the moment they are created.

    If the project already exists, this is a no-op.
    """
    try:
        osc.core.show_project_meta(apiurl, obs_project_name)
        return  # project already exists
    except urllib.error.HTTPError as e:
        if e.code != 404:
            _obs_api_error(e, f"checking project {obs_project_name}")
        # 404 → project does not exist, fall through to create it

    project_config = _load_project_config_with_inheritance(project_path, env_vars)
    root_el = ET.Element("project", name=obs_project_name)
    ET.SubElement(root_el, "title").text = project_config.get("title", "")
    ET.SubElement(root_el, "description").text = project_config.get("description", "")
    ET.indent(root_el)
    skeleton_meta = ET.tostring(root_el, encoding="unicode")

    # Propagate person/group from the root project to new subprojects.
    if rootprj and rootprj != obs_project_name:
        inherited = _fetch_root_project_managed_elements(apiurl, rootprj)
        skeleton_meta = _inject_obs_managed_elements(skeleton_meta, inherited)

    logger.debug(f"creating skeleton project: {obs_project_name}")
    _print_pending(f"project  {obs_project_name}")
    if not dry_run:
        try:
            with _silence_stdout():
                osc.core.edit_meta(
                    metatype="prj",
                    path_args=(obs_project_name,),
                    data=[skeleton_meta],
                    force=False,
                    apiurl=apiurl,
                )
        except urllib.error.HTTPError as e:
            _obs_api_error(e, f"creating skeleton for {obs_project_name}")
    _print_create(f"project  {obs_project_name}")


def _fetch_obs_download_url(apiurl: str) -> str | None:
    """Return the download base URL configured on the OBS instance.

    Fetches GET /configuration and reads the <download_url> element.
    Returns None on any error or if the element is absent.
    """
    url = osc.core.makeurl(apiurl, ["configuration"])
    try:
        root = ET.fromstring(osc.connection.http_GET(url).read())
        value = root.findtext("download_url")
        return value.rstrip("/") if value else None
    except Exception:
        return None


def _delete_obs_package(
    apiurl: str, obs_project_name: str, package_name: str, dry_run: bool
) -> None:
    """Delete a package from OBS, or report the deletion in dry-run mode."""
    label = f"package  {obs_project_name}/{package_name}"
    if not dry_run:
        try:
            osc.core.delete_package(apiurl, obs_project_name, package_name)
        except urllib.error.HTTPError as e:
            _obs_api_error(e, f"deleting package {obs_project_name}/{package_name}")
    _print_remove(label)


def _delete_obs_project(
    apiurl: str, obs_project_name: str, dry_run: bool, recursive: bool = False
) -> None:
    """Delete an OBS project (OBS automatically removes all packages within it).

    When recursive=True, passes the recursive flag to OBS so that projects
    containing packages are deleted without first emptying them.
    In dry-run mode, reports what would be deleted without making any changes.
    """
    if not dry_run:
        try:
            osc.core.delete_project(
                apiurl, obs_project_name, force=True, recursive=recursive
            )
        except osc.oscerr.ProjectError as e:
            raise SystemExit(
                f"error deleting project {obs_project_name}:\n  {e}\n"
                "  hint: use --recursive to delete projects that still contain packages"
            ) from None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.debug(f"project not found, skipping: {obs_project_name}")
                return
            _obs_api_error(e, f"deleting project {obs_project_name}")
    _print_remove(f"project  {obs_project_name}")


# OBS-managed project meta elements that we must never overwrite.
# 'person' and 'group' grant access rights; 'lock' freezes the project;
# 'link' connects linked projects.
_OBS_MANAGED_ELEMS = {"person", "group", "lock", "link"}


def _child_text(elem: ET.Element, tag: str) -> str:
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _extract_obs_managed_elements(xml_bytes: bytes) -> list[ET.Element]:
    """Return deep copies of OBS-managed children (person/group/lock/link) from project XML."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    return [copy.deepcopy(child) for child in root if child.tag in _OBS_MANAGED_ELEMS]


def _inject_obs_managed_elements(meta_xml: str, elements: list[ET.Element]) -> str:
    """Insert OBS-managed elements into a locally-generated project meta XML string.

    Elements are inserted after <description> (or <title> if no <description>
    is present) and before any <publish>/<build>/<repository> elements, which
    is the standard OBS element ordering.
    Returns the original XML unchanged when *elements* is empty.
    """
    if not elements:
        return meta_xml
    try:
        root = ET.fromstring(meta_xml)
    except ET.ParseError:
        return meta_xml
    # Find insertion index: after the last title/description child.
    insert_at = 0
    for i, child in enumerate(root):
        if child.tag in ("title", "description"):
            insert_at = i + 1
    for offset, elem in enumerate(elements):
        root.insert(insert_at + offset, elem)
    ET.indent(root)
    return ET.tostring(root, encoding="unicode")


def _fetch_root_project_managed_elements(apiurl: str, rootprj: str) -> list[ET.Element]:
    """Return person/group elements from the root OBS project for propagation to new subprojects.

    Only 'person' and 'group' are returned — 'lock' and 'link' are
    project-specific and must not be inherited by child projects.
    Returns an empty list when the root project does not yet exist or on any error.
    """
    try:
        raw = _decode_obs_response(osc.core.show_project_meta(apiurl, rootprj))
    except Exception:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    return [copy.deepcopy(child) for child in root if child.tag in ("person", "group")]


def _flag_entries(elem: ET.Element, section: str) -> set[tuple[str, str]]:
    """Return the set of (tag, repository-attr) pairs inside an OBS flag section.

    Used to compare <publish> and <build> sections in project and package meta.
    """
    sec = elem.find(section)
    if sec is None:
        return set()
    return {(child.tag, child.get("repository", "")) for child in sec}


def _project_meta_subset_equal(current_bytes: bytes, desired_xml: str) -> bool:
    """Return True if the title, description, repositories, and publish/build flags we manage are identical.

    Ignores OBS-managed elements (person, group, lock, link) so that ACL entries
    added via the web UI do not cause spurious updates.
    """
    try:
        current = ET.fromstring(current_bytes)
        desired = ET.fromstring(desired_xml)
    except ET.ParseError:
        return False

    if _child_text(current, "title") != _child_text(desired, "title"):
        return False
    if _child_text(current, "description") != _child_text(desired, "description"):
        return False

    if _flag_entries(current, "publish") != _flag_entries(desired, "publish"):
        return False
    if _flag_entries(current, "build") != _flag_entries(desired, "build"):
        return False

    current_repos = {r.get("name"): r for r in current.findall("repository")}
    desired_repos = {r.get("name"): r for r in desired.findall("repository")}
    if set(current_repos) != set(desired_repos):
        return False

    for name, d_repo in desired_repos.items():
        c_repo = current_repos[name]
        d_paths = [
            (p.get("project"), p.get("repository")) for p in d_repo.findall("path")
        ]
        c_paths = [
            (p.get("project"), p.get("repository")) for p in c_repo.findall("path")
        ]
        if d_paths != c_paths:
            return False
        if [a.text for a in d_repo.findall("arch")] != [
            a.text for a in c_repo.findall("arch")
        ]:
            return False

    return True


def _package_meta_subset_equal(current_bytes: bytes, desired_xml: str) -> bool:
    """Return True if the fields we manage are identical to what OBS has.

    Compares title, description, build flags, and publish flags.
    """
    try:
        current = ET.fromstring(current_bytes)
        desired = ET.fromstring(desired_xml)
    except ET.ParseError:
        return False

    if _child_text(current, "title") != _child_text(desired, "title"):
        return False
    if _child_text(current, "description") != _child_text(desired, "description"):
        return False

    return _flag_entries(current, "build") == _flag_entries(
        desired, "build"
    ) and _flag_entries(current, "publish") == _flag_entries(desired, "publish")


def _edit_project_meta(
    apiurl: str, obs_project_name: str, meta: str, force: bool
) -> bool:
    """Call osc.core.edit_meta for a project, auto-retrying with paths stripped on
    repository_access_failure.

    Returns True if paths had to be stripped (meaning the project needs a second
    pass once sibling/child projects have their repositories configured).
    Returns False when the full meta was accepted without modification.

    During first-time bootstrapping, repository paths may reference sibling
    projects whose repositories have not yet been configured on OBS.  Stripping
    the paths lets OBS accept the meta; a second Stage-2 pass later re-applies
    the full config once every project in the tree has its repositories set up.
    The retry is only attempted when force is False on the first call — if the
    caller already requested force=True the error is surfaced immediately.
    """
    try:
        with _silence_stdout():
            osc.core.edit_meta(
                metatype="prj",
                path_args=(obs_project_name,),
                data=[meta],
                force=force,
                apiurl=apiurl,
            )
        return False
    except urllib.error.HTTPError as e:
        err_body: bytes = b""
        try:
            err_body = e.read()
        except Exception:
            pass
        err_code = ""
        if err_body:
            try:
                err_code = ET.fromstring(err_body).get("code", "")
            except ET.ParseError:
                pass
        if not force and err_code in (
            "repository_access_failure",
            "project_save_error",
        ):
            # OBS rejects the meta because a referenced project doesn't have
            # its repositories configured yet.  Strip <path> elements and
            # retry so OBS accepts the skeleton; a second Stage-2 pass will
            # re-apply the full config once all projects have their repos set.
            logger.debug(
                f"repository_access_failure on create, stripping paths and retrying: {obs_project_name}"
            )
            try:
                root_el = ET.fromstring(meta)
                for repo_el in root_el.findall("repository"):
                    for path_el in repo_el.findall("path"):
                        repo_el.remove(path_el)
                stripped = ET.tostring(root_el, encoding="unicode")
            except ET.ParseError:
                stripped = meta
            try:
                with _silence_stdout():
                    osc.core.edit_meta(
                        metatype="prj",
                        path_args=(obs_project_name,),
                        data=[stripped],
                        force=False,
                        apiurl=apiurl,
                    )
            except urllib.error.HTTPError as e2:
                _obs_api_error(e2, f"writing project meta for {obs_project_name}")
            return True  # paths were stripped; caller must schedule a retry
        elif err_code == "repo_dependency":
            # OBS refuses to remove a repository because another project's
            # repository still lists it as a path dependency.  This happens
            # during a rename (e.g. xUbuntu_24.04 → Ubuntu_24.04) when the
            # dependent project hasn't been updated yet.  Retry with force=True
            # so OBS accepts the change; the dependency resolves once the
            # dependent project is synced.
            logger.debug(
                f"repo_dependency on update, retrying with force=True: {obs_project_name}"
            )
            try:
                with _silence_stdout():
                    osc.core.edit_meta(
                        metatype="prj",
                        path_args=(obs_project_name,),
                        data=[meta],
                        force=True,
                        apiurl=apiurl,
                    )
            except urllib.error.HTTPError as e2:
                _obs_api_error(e2, f"writing project meta for {obs_project_name}")
            return False
        else:
            _obs_api_error(
                e, f"writing project meta for {obs_project_name}", body=err_body
            )
    return False  # unreachable; _obs_api_error always raises


def _apply_project_config(
    apiurl: str,
    obs_project_name: str,
    project_path: Path,
    rootprj: str,
    force: bool = False,
    dry_run: bool = False,
    env_vars: dict[str, str] | None = None,
) -> bool:
    """Create or update OBS project metadata and build config from project.yaml.

    Returns True if the project meta had repository <path> elements stripped
    due to repository_access_failure (meaning a second pass is needed once all
    sibling/child projects have their repositories configured on OBS).
    Returns False when the full meta was accepted without modification, or when
    in dry-run mode (no actual writes happen).

    Skips the API call when the content already matches what OBS has, unless
    --force is given (which bypasses both the local comparison and OBS conflict checks).
    With --dry-run, read-only OBS calls are made to compute the diff but no
    changes are written.

    OBS-managed elements (person, group, lock, link) that exist on OBS are
    always preserved: they are extracted from the current project meta and
    re-injected into the locally-generated XML before uploading.  For new
    projects, person/group elements are inherited from the root project.

    Prints '+' for creates, '~' for updates, '=' for unchanged resources.
    """
    project_config = _load_project_config_with_inheritance(project_path, env_vars)
    meta = build_project_meta(
        obs_project_name,
        project_config.get("title", ""),
        project_config.get("description", ""),
        project_config.get("repositories", []),
        rootprj,
        publish=project_config.get("publish"),
        build=project_config.get("build"),
    )

    # --- project meta ---
    logger.debug(f"  meta XML:\n{meta}")
    current = b""
    project_meta_exists = True
    paths_stripped = False
    _print_pending(f"project meta  {obs_project_name}")
    try:
        logger.debug(f"fetching project meta: {obs_project_name}")
        current = _decode_obs_response(
            osc.core.show_project_meta(apiurl, obs_project_name)
        ).encode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            project_meta_exists = False
        else:
            _obs_api_error(e, f"fetching project meta for {obs_project_name}")

    if not project_meta_exists:
        logger.debug(f"creating project meta: {obs_project_name}")
        # New project: inherit person/group from the root project.
        if rootprj != obs_project_name:
            inherited = _fetch_root_project_managed_elements(apiurl, rootprj)
            meta_to_upload = _inject_obs_managed_elements(meta, inherited)
        else:
            meta_to_upload = meta
        if not dry_run:
            paths_stripped = _edit_project_meta(
                apiurl, obs_project_name, meta_to_upload, force=False
            )
        _print_create(f"project meta  {obs_project_name}")
    elif force or not _project_meta_subset_equal(current, meta):
        logger.debug(f"updating project meta: {obs_project_name}")
        # Existing project: preserve all OBS-managed elements (person/group/lock/link).
        managed = _extract_obs_managed_elements(current)
        meta_to_upload = _inject_obs_managed_elements(meta, managed)
        if not dry_run:
            paths_stripped = _edit_project_meta(
                apiurl, obs_project_name, meta_to_upload, force=force
            )
        _print_update(f"project meta  {obs_project_name}")
    else:
        logger.debug(f"project meta unchanged: {obs_project_name}")
        _print_same(f"project meta  {obs_project_name}")

    # --- project config ---
    project_config_str = project_config.get("project-config") or ""
    current_conf = ""
    project_conf_exists = True
    _print_pending(f"project config  {obs_project_name}")
    try:
        logger.debug(f"fetching project config: {obs_project_name}")
        current_conf = _decode_obs_response(
            osc.core.show_project_conf(apiurl, obs_project_name)
        )
    except urllib.error.HTTPError as e:
        if e.code == 404:
            project_conf_exists = False
        else:
            _obs_api_error(e, f"fetching project config for {obs_project_name}")

    if not project_conf_exists:
        logger.debug(f"creating project config: {obs_project_name}")
        if not dry_run:
            try:
                with _silence_stdout():
                    osc.core.edit_meta(
                        metatype="prjconf",
                        path_args=(obs_project_name,),
                        data=[project_config_str],
                        force=False,
                        apiurl=apiurl,
                    )
            except urllib.error.HTTPError as e:
                _obs_api_error(e, f"creating project config for {obs_project_name}")
        _print_create(f"project config  {obs_project_name}")
    elif force or current_conf.strip() != project_config_str.strip():
        logger.debug(f"updating project config: {obs_project_name}")
        if not dry_run:
            try:
                with _silence_stdout():
                    osc.core.edit_meta(
                        metatype="prjconf",
                        path_args=(obs_project_name,),
                        data=[project_config_str],
                        force=force,
                        apiurl=apiurl,
                    )
            except urllib.error.HTTPError as e:
                _obs_api_error(e, f"updating project config for {obs_project_name}")
        _print_update(f"project config  {obs_project_name}")
    else:
        logger.debug(f"project config unchanged: {obs_project_name}")
        _print_same(f"project config  {obs_project_name}")

    return paths_stripped


def _apply_package_config(
    apiurl: str,
    obs_project_name: str,
    package_name: str,
    package_path: Path,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """Create or update OBS package metadata from package.yaml.

    Skips the API call when the content already matches what OBS has, unless
    --force is given.  With --dry-run, read-only OBS calls are made to compute
    the diff but no changes are written.

    Prints '+' for creates, '~' for updates, '=' for unchanged resources.
    """
    package_config = load_yaml(package_path / "package.yaml")
    build_flags: dict[str, bool] | None = package_config.get("build") or None
    publish_flags: dict[str, bool] | None = package_config.get("publish") or None
    meta = build_package_meta(
        obs_project_name,
        package_name,
        package_config.get("title", ""),
        package_config.get("description", ""),
        build=build_flags,
        publish=publish_flags,
    )

    logger.debug(f"  package meta XML:\n{meta}")
    package_exists = True
    current = b""
    _print_pending(f"package  {obs_project_name}/{package_name}")
    try:
        logger.debug(f"fetching package meta: {obs_project_name}/{package_name}")
        current = _decode_obs_response(
            osc.core.show_package_meta(apiurl, obs_project_name, package_name)
        ).encode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            package_exists = False
        else:
            _obs_api_error(
                e,
                f"fetching package meta for {obs_project_name}/{package_name}",
            )

    if not package_exists:
        logger.debug(f"creating package meta: {obs_project_name}/{package_name}")
        if not dry_run:
            try:
                with _silence_stdout():
                    osc.core.edit_meta(
                        metatype="pkg",
                        path_args=(obs_project_name, package_name),
                        data=[meta],
                        force=False,
                        apiurl=apiurl,
                    )
            except urllib.error.HTTPError as e:
                _obs_api_error(
                    e, f"creating package meta for {obs_project_name}/{package_name}"
                )
        _print_create(f"package  {obs_project_name}/{package_name}")
    elif force or not _package_meta_subset_equal(current, meta):
        logger.debug(f"updating package meta: {obs_project_name}/{package_name}")
        if not dry_run:
            try:
                with _silence_stdout():
                    osc.core.edit_meta(
                        metatype="pkg",
                        path_args=(obs_project_name, package_name),
                        data=[meta],
                        force=force,
                        apiurl=apiurl,
                    )
            except urllib.error.HTTPError as e:
                _obs_api_error(
                    e, f"updating package meta for {obs_project_name}/{package_name}"
                )
        _print_update(f"package  {obs_project_name}/{package_name}")
    else:
        logger.debug(f"package meta unchanged: {obs_project_name}/{package_name}")
        _print_same(f"package  {obs_project_name}/{package_name}")


def _upload_obs_files(
    apiurl: str,
    obs_project_name: str,
    package_name: str,
    obs_dir: Path,
    message: str = "",
    dry_run: bool = False,
) -> bool:
    """Upload changed files from obs_dir to OBS as a single committed revision.

    Each changed file is staged with ?rev=upload (no revision created yet).
    Files present on OBS but absent locally are deleted with ?rev=upload.
    After all files are staged/deleted, a single commit is issued, optionally
    with a message. This produces one OBS source revision per sync instead of
    one per file, and skips the commit entirely when nothing changed.
    With --dry-run, read-only OBS calls are made to compute the diff but no
    files are uploaded or committed.

    Prints '=' when no files changed, '~' with a per-file breakdown for
    certain changes. In dry-run mode, OBS-only files are shown with '!' rather
    than '-' because they may be service-generated artifacts whose fate cannot
    be determined without running the services.

    Returns True if any files were uploaded/committed, False if nothing changed.
    """
    _print_pending(f"files  {obs_project_name}/{package_name}")
    obs_md5s = _fetch_obs_file_md5s(apiurl, obs_project_name, package_name)
    new_files: list[str] = []
    updated_files: list[str] = []
    removed: list[str] = []
    uncertain: list[str] = []
    local_files: set[str] = set()

    for filepath in sorted(obs_dir.iterdir()):
        if not filepath.is_file():
            continue
        local_files.add(filepath.name)
        local_md5 = hashlib.md5(filepath.read_bytes()).hexdigest()
        if obs_md5s.get(filepath.name) == local_md5:
            logger.debug(f"{filepath.name} unchanged (md5 match)")
            continue
        if filepath.name in obs_md5s:
            updated_files.append(filepath.name)
        else:
            new_files.append(filepath.name)
        if not dry_run:
            logger.debug(f"staging {filepath.name} → {obs_project_name}/{package_name}")
            url = osc.core.makeurl(
                apiurl,
                ["source", obs_project_name, package_name, filepath.name],
                query={"rev": "upload"},
            )
            try:
                osc.connection.http_PUT(url, file=str(filepath))
            except urllib.error.HTTPError as e:
                if e.code == 400:
                    raise SystemExit(
                        f"error: OBS rejected {filepath.name} for "
                        f"{obs_project_name}/{package_name} (HTTP 400 Bad Request).\n"
                        f"       The file may use features unsupported by this OBS instance."
                    ) from None
                raise

    for obs_name in sorted(obs_md5s.keys() - local_files):
        if dry_run:
            # In dry-run mode services were not run, so OBS-only files may be
            # service-generated artifacts rather than genuine deletions.
            uncertain.append(obs_name)
        else:
            removed.append(obs_name)
            logger.debug(f"deleting {obs_name} → {obs_project_name}/{package_name}")
            url = osc.core.makeurl(
                apiurl,
                ["source", obs_project_name, package_name, obs_name],
                query={"rev": "upload"},
            )
            osc.connection.http_DELETE(url)

    certain = new_files + updated_files + removed
    if not certain and not uncertain:
        logger.debug(f"no files changed: {obs_project_name}/{package_name}")
        _print_same(f"{len(local_files)} files  {obs_project_name}/{package_name}")
        return False

    if not dry_run:
        commit_query: dict = {"cmd": "commit"}
        if message:
            commit_query["comment"] = message
        logger.debug(
            f"committing {len(new_files)} new, {len(updated_files)} updated, "
            f"{len(removed)} deleted: {obs_project_name}/{package_name}"
        )
        url = osc.core.makeurl(
            apiurl, ["source", obs_project_name, package_name], query=commit_query
        )
        osc.connection.http_POST(url)

    total = len(certain) + len(uncertain)
    label = f"{total} files  {obs_project_name}/{package_name}"
    if certain:
        _print_update(label)
    else:
        # Only uncertain files: package is probably unchanged but service
        # outputs on OBS cannot be verified without running the services.
        print(f"  {_col(_YELLOW, '!')} {label}")
    for name in new_files:
        print(f"      |_ {_col(_GREEN, '+')} {name}")
    for name in updated_files:
        print(f"      |_ {_col(_YELLOW, '~')} {name}")
    for name in removed:
        print(f"      |_ {_col(_RED, '-')} {name}")
    for name in uncertain:
        print(
            f"      |_ {_col(_YELLOW, '!')} {name}  (service output, skipped in dry-run)"
        )
    return True
