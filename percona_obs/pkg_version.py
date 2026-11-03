"""Upstream version of a package as OBS computes it, and the PKG_REVISION floor.

``extract_version_from_service_text`` mirrors obs_scm/tar_scm and
set_version: an explicit obs_scm ``version`` wins; a literal
``versionformat`` is returned as is; ``@PARENT_TAG@`` applies
``versionrewrite-pattern``/``-replacement`` to ``revision`` exactly like
tar_scm (``re.sub(pattern, replacement or r"\\1", tag)``); a bare commit SHA
needs a tag lookup, which the caller may provide through *resolve_tag* (the
tool's computed macros never do: they must stay offline).  With no obs_scm
version the set_version service names it (``version`` param, or the
``basename`` + download_url file name).

``PKG_REVISION_FLOORS`` carries the repo.percona.com counters forward across
the OBS migration.  Keyed by OBS project, package directory name and
upstream version (no epoch); the value is max(deb revision, rpm release)
over every production vault, codename and EL major, from the index dump of
2026-11-02/03.  An entry is dead once the package ships another upstream
version; delete the table when every entry is dead.  The table is code, so
a commit that only edits a seed is invisible to the sync content check: re-push
the affected packages with a forced sync (sync-main force, or sync push --force).  See
docs/superpowers/specs/2026-11-02-deb-revision-counter-design.md.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

_ARCHIVE_SUFFIX_RE = re.compile(r"\.(tar\.(gz|bz2|xz|zst)|tgz|tbz2|txz|zip)$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

TagResolver = Callable[[str, str], "str | None"]


def _params(svc: ET.Element) -> dict[str, str]:
    return {p.get("name", ""): (p.text or "").strip() for p in svc.findall("param")}


def version_from_set_version(root_el: ET.Element) -> "str | None":
    """Version that a set_version service gives the package, or None.

    An explicit ``version`` param wins; otherwise the version is read from a
    downloaded file named ``<basename>-<version>`` plus an archive suffix,
    here the ``filename`` (or URL basename) of a download_url service.
    Macros (``%!{VAR}``) are returned unresolved for the caller to substitute.
    """
    for svc in root_el.findall("service"):
        if svc.get("name") != "set_version":
            continue
        params = _params(svc)
        if params.get("version"):
            return params["version"]
        basename = params.get("basename", "")
        if not basename:
            return None
        for dl in root_el.findall("service"):
            if dl.get("name") != "download_url":
                continue
            dl_params = _params(dl)
            filename = (
                dl_params.get("filename") or dl_params.get("url", "").rsplit("/", 1)[-1]
            )
            if filename.startswith(basename + "-"):
                version = _ARCHIVE_SUFFIX_RE.sub("", filename[len(basename) + 1 :])
                if version:
                    return version
        return None
    return None


def _rewrite(pattern: str, replacement: str, value: str) -> "str | None":
    """tar_scm's versionrewrite: re.sub with ``\\1`` as the default replacement."""
    try:
        if not re.search(pattern, value):
            return None
        return re.sub(pattern, replacement or r"\1", value)
    except re.error:
        return None


def extract_version_from_service_text(
    text: str, resolve_tag: "TagResolver | None" = None
) -> "str | None":
    """Return the upstream version an obs/_service file yields, or None."""
    try:
        root_el = ET.fromstring(text)
    except ET.ParseError:
        return None

    for svc in root_el.findall("service"):
        if svc.get("name") != "obs_scm":
            continue
        params = _params(svc)
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
            replacement = params.get("versionrewrite-replacement", "")
            if _ENV_VAR_RE.search(revision):
                return None
            if pattern and revision:
                rewritten = _rewrite(pattern, replacement, revision)
                if rewritten is not None:
                    return rewritten
            if _SHA_RE.match(revision):
                url = params.get("url", "")
                if resolve_tag is None or not url or _ENV_VAR_RE.search(url):
                    return None
                tag = resolve_tag(url, revision)
                if tag is None:
                    return None
                if pattern:
                    rewritten = _rewrite(pattern, replacement, tag)
                    if rewritten is not None:
                        return rewritten
                return tag
            return revision or None
        if revision and not _ENV_VAR_RE.search(revision):
            return revision
        return None

    return version_from_set_version(root_el)


def extract_version_from_service(
    service_file: Path, resolve_tag: "TagResolver | None" = None
) -> "str | None":
    """``extract_version_from_service_text`` over a file; unreadable → None."""
    try:
        text = service_file.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return extract_version_from_service_text(text, resolve_tag=resolve_tag)


# (OBS project, package directory name, upstream version) -> production counter.
PKG_REVISION_FLOORS: dict[tuple[str, str, str], int] = {
    # pgaudit: 14/15 rpm counter ahead of deb (7 vs 4)
    ("ppg:staging:14", "percona-pgaudit", "1.6.3"): 7,
    ("ppg:staging:15", "percona-pgaudit", "1.7.1"): 7,
    ("ppg:staging:16", "percona-pgaudit", "16.1"): 4,
    ("ppg:staging:17", "percona-pgaudit", "17.1"): 4,
    ("ppg:staging:18", "percona-pgaudit", "18.0"): 4,
    # set_user
    ("ppg:staging:14", "percona-pgaudit_set_user", "4.2.0"): 4,
    ("ppg:staging:15", "percona-pgaudit_set_user", "4.2.0"): 4,
    ("ppg:staging:16", "percona-pgaudit_set_user", "4.2.0"): 4,
    ("ppg:staging:17", "percona-pgaudit_set_user", "4.2.0"): 6,
    ("ppg:staging:18", "percona-pgaudit_set_user", "4.2.0"): 4,
    # pg_repack: 14-17 at 5, 18 at 4 -> global max
    ("ppg:staging:14", "percona-pg_repack", "1.5.3"): 5,
    ("ppg:staging:15", "percona-pg_repack", "1.5.3"): 5,
    ("ppg:staging:16", "percona-pg_repack", "1.5.3"): 5,
    ("ppg:staging:17", "percona-pg_repack", "1.5.3"): 5,
    ("ppg:staging:18", "percona-pg_repack", "1.5.3"): 5,
    # pg-telemetry: not in the 18 vault
    ("ppg:staging:14", "percona-pg-telemetry", "1.2.0"): 3,
    ("ppg:staging:15", "percona-pg-telemetry", "1.2.0"): 3,
    ("ppg:staging:16", "percona-pg-telemetry", "1.2.0"): 3,
    ("ppg:staging:17", "percona-pg-telemetry", "1.2.0"): 3,
    # pg_gather: rpm name has no major, shared across majors
    ("ppg:staging:14", "percona-pg_gather", "33"): 3,
    ("ppg:staging:15", "percona-pg_gather", "33"): 3,
    ("ppg:staging:16", "percona-pg_gather", "33"): 3,
    ("ppg:staging:17", "percona-pg_gather", "33"): 3,
    ("ppg:staging:18", "percona-pg_gather", "33"): 3,
    ("ppg:staging:19", "percona-pg_gather", "33"): 3,
    # postgis: 14-17 at 2, 18 at 3 -> global max
    ("ppg:staging:14", "percona-postgis", "3.5.7"): 3,
    ("ppg:staging:15", "percona-postgis", "3.5.7"): 3,
    ("ppg:staging:16", "percona-postgis", "3.5.7"): 3,
    ("ppg:staging:17", "percona-postgis", "3.5.7"): 3,
    ("ppg:staging:18", "percona-postgis", "3.5.7"): 3,
    # pgpool-II: deb 2 ahead of rpm 1
    ("ppg:staging:14", "percona-pgpool-II", "4.7.2"): 2,
    ("ppg:staging:15", "percona-pgpool-II", "4.7.2"): 2,
    ("ppg:staging:16", "percona-pgpool-II", "4.7.2"): 2,
    ("ppg:staging:17", "percona-pgpool-II", "4.7.2"): 2,
    ("ppg:staging:18", "percona-pgpool-II", "4.7.2"): 2,
    ("ppg:staging:19", "percona-pgpool-II", "4.7.2"): 2,
    # shared tools and deps
    ("ppg:staging:common:tools", "percona-pgbadger", "13.2"): 3,
    ("ppg:staging:common:tools", "percona-patroni", "4.1.5"): 1,
    ("ppg:common:deps", "ydiff", "1.4.2"): 3,
    # production counter 1: deb "V-1+..." sorts below "V-1.codename"
    ("ppg:staging:14", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:15", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:16", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:17", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:18", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:19", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:14", "percona-pg_cron", "1.6.8"): 1,
    ("ppg:staging:15", "percona-pg_cron", "1.6.8"): 1,
    ("ppg:staging:16", "percona-pg_cron", "1.6.8"): 1,
    ("ppg:staging:17", "percona-pg_cron", "1.6.8"): 1,
    ("ppg:staging:18", "percona-pg_cron", "1.6.8"): 1,
    ("ppg:staging:17", "percona-pg_tde", "2.2.2"): 1,
    ("ppg:staging:18", "percona-pg_tde", "2.2.2"): 1,
    ("ppg:staging:18", "percona-pg_oidc_validator", "1.1.0"): 1,
}


def compute_pkg_revision(project: str, package: str, version: str) -> str:
    """``floor(project, package, version) + 1`` as a string; 1 when unseeded."""
    return str(PKG_REVISION_FLOORS.get((project, package, version), 0) + 1)
