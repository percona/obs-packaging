"""Best-effort CVE scanner for `project release`.

Produces the ready-to-embed bullet lines for the CHANGELOG ``### Security``
section.  The scan is intentionally best-effort: every package/source is
scanned independently and anything that cannot be resolved (unrecognized
upstream, network failure, unrecognized tag scheme, ...) is *reported* as a
"Not scanned" line rather than silently dropped or allowed to abort the
release cut.  See ``docs/PERCONA_OBS_TOOL.md`` for the user-facing summary.
"""

import json
import os
import re
import subprocess
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .common import REPO_ROOT, _REPO_DIR

CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}")

_Fetcher = Callable[[str, "dict[str, str] | None"], str]
_RunGit = Callable[["list[str]"], str]

_GITHUB_HEADERS_ACCEPT = {"Accept": "application/vnd.github+json"}


@dataclass
class ScanResult:
    lines: (
        "list[str]"  # ready-to-embed changelog bullet lines (may be multi-line strings)
    )
    clean: "list[str]"  # package keys scanned with no CVE mentions
    unscanned: "list[tuple[str, str]]"  # (package key, reason)


@dataclass
class ChangedPackage:
    key: str  # changelog key, e.g. "percona-patroni" or "percona-postgresql (extras)"
    old_version: str  # version part only (no -release), e.g. "4.1.3"
    new_version: str
    upstream_url: str  # from _extract_upstream_info_from_service, may be ""
    revision: (
        str  # the NEW upstream revision/tag from _service (macros already resolved)
    )


def _default_fetcher(url: str, headers: "dict[str, str] | None" = None) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "percona-obs", **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", "replace")


def _default_run_git(args: "list[str]") -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=_REPO_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _github_headers() -> "dict[str, str]":
    headers = dict(_GITHUB_HEADERS_ACCEPT)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _wrap_bullet(line: str, width: int = 100) -> str:
    """Wrap a changelog bullet to ~width cols, continuation lines indented two spaces."""
    return textwrap.fill(
        line,
        width=width,
        subsequent_indent="  ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def _loose_version_key(version: str) -> "tuple[int, ...]":
    """Split a version string on non-digit runs and return a tuple of ints for ordering."""
    return tuple(int(x) for x in re.findall(r"\d+", version))


def _tag_template_and_sep(revision: str, version: str) -> "tuple[str, str] | None":
    """Return (template, separator) for a GitHub tag scheme, or None if unrecognized.

    ``template`` has ``{v}`` where the (separator-rewritten) version appears in
    ``revision``; e.g. revision="v4.1.5", version="4.1.5" -> ("v{v}", ".").
    """
    for sep in (".", "_", "-"):
        cand = version.replace(".", sep)
        if cand and cand in revision:
            template = revision.replace(cand, "{v}", 1)
            return template, sep
    return None


def _derive_tag_template(revision: str, version: str) -> "str | None":
    """Return a format template with {v} where the version appears in the tag.

    Handles separator rewrites: v4.1.5/4.1.5 -> "v{v}"; release/2.59.0 ->
    "release/{v}"; V4_7_2 (version 4.7.2) -> "V{v}" with '_' separators;
    REL_17_11 (version 17.11) -> "REL_{v}" with '_' separators.  Returns None
    when the version (under any separator rewrite) is not a substring of the
    revision.
    """
    result = _tag_template_and_sep(revision, version)
    return result[0] if result else None


def _tag_to_version(tag_name: str, template: str, sep: str) -> "str | None":
    """Invert a tag template: recover the dotted version from a tag_name, or None."""
    prefix, marker, suffix = template.partition("{v}")
    if not marker:
        return None
    if not tag_name.startswith(prefix) or not tag_name.endswith(suffix):
        return None
    middle = tag_name[
        len(prefix) : len(tag_name) - len(suffix) if suffix else len(tag_name)
    ]
    if not middle:
        return None
    return middle.replace(sep, ".")


_PG_GITHUB_RE = re.compile(r"github\.com/(?:percona|postgres)/postgres(?:\.git)?/?$")
_GITHUB_URL_RE = re.compile(r"github\.com/([^/\s]+)/([^/.\s]+?)(?:\.git)?/?$")


def _is_postgres_upstream(url: str) -> bool:
    if not url:
        return False
    if "git.postgresql.org" in url:
        return True
    return bool(_PG_GITHUB_RE.search(url))


def _scan_postgres(
    pkg: ChangedPackage, fetcher: _Fetcher
) -> "tuple[str | None, bool, str | None]":
    """Scan PostgreSQL release notes for CVE mentions across the version range."""
    new_parts = pkg.new_version.split(".")
    old_parts = pkg.old_version.split(".") if pkg.old_version else []
    if len(new_parts) < 2:
        return None, False, f"unrecognized PostgreSQL version {pkg.new_version!r}"
    major = new_parts[0]
    try:
        new_minor = int(new_parts[1])
        old_minor = int(old_parts[1]) if len(old_parts) > 1 else new_minor - 1
    except ValueError:
        return (
            None,
            False,
            f"unrecognized PostgreSQL version {pkg.old_version!r}->{pkg.new_version!r}",
        )

    minors = (
        range(old_minor + 1, new_minor + 1) if new_minor > old_minor else [new_minor]
    )

    cves: "set[str]" = set()
    fetched_any = False
    for minor in minors:
        url = f"https://www.postgresql.org/docs/release/{major}.{minor}/"
        try:
            html = fetcher(url, None)
        except Exception:
            continue
        fetched_any = True
        cves.update(CVE_RE.findall(html))

    if not fetched_any:
        return (
            None,
            False,
            f"PostgreSQL release notes unreachable for {major}.{new_minor}",
        )

    if not cves:
        return None, True, None

    new_url = f"https://www.postgresql.org/docs/release/{major}.{new_minor}/"
    sorted_cves = sorted(cves)
    line = (
        f"- {pkg.key}: PostgreSQL {pkg.new_version} fixes {len(sorted_cves)} CVEs "
        f"({new_url}): " + ", ".join(sorted_cves)
    )
    return _wrap_bullet(line), False, None


def _scan_github(
    pkg: ChangedPackage, fetcher: _Fetcher
) -> "tuple[str | None, bool, str | None]":
    """Scan a GitHub upstream's compare diff + releases for CVE mentions."""
    m = _GITHUB_URL_RE.search(pkg.upstream_url)
    if not m:
        return None, False, f"unrecognized GitHub URL {pkg.upstream_url!r}"
    owner, repo = m.group(1), m.group(2)

    tpl = _tag_template_and_sep(pkg.revision, pkg.new_version)
    if tpl is None:
        return None, False, f"unrecognized tag scheme {pkg.revision!r}"
    template, sep = tpl
    old_tag = template.format(v=pkg.old_version.replace(".", sep))
    new_tag = pkg.revision
    headers = _github_headers()

    compare_cves: "set[str]" = set()
    compare_ok = False
    compare_url = (
        f"https://api.github.com/repos/{owner}/{repo}/compare/{old_tag}...{new_tag}"
    )
    try:
        data = json.loads(fetcher(compare_url, headers))
        for commit in data.get("commits", []) or []:
            message = (commit.get("commit") or {}).get("message") or ""
            compare_cves.update(CVE_RE.findall(message))
        compare_ok = True
    except Exception:
        compare_ok = False

    release_cves: "set[str]" = set()
    releases_ok = False
    releases_api_url = (
        f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=100"
    )
    try:
        entries = json.loads(fetcher(releases_api_url, headers))
        old_key = _loose_version_key(pkg.old_version)
        new_key = _loose_version_key(pkg.new_version)
        for entry in entries or []:
            tag_name = entry.get("tag_name") or ""
            version = _tag_to_version(tag_name, template, sep)
            if version is None:
                continue
            version_key = _loose_version_key(version)
            if old_key < version_key <= new_key:
                release_cves.update(CVE_RE.findall(entry.get("body") or ""))
        releases_ok = True
    except Exception:
        releases_ok = False

    all_cves = compare_cves | release_cves
    if all_cves:
        releases_page_url = f"https://github.com/{owner}/{repo}/releases"
        line = (
            f"- {pkg.key}: {pkg.old_version}→{pkg.new_version} fixes "
            + ", ".join(sorted(all_cves))
            + f" ({releases_page_url})"
        )
        return _wrap_bullet(line), False, None

    if compare_ok or releases_ok:
        return None, True, None

    return (
        None,
        False,
        f"GitHub API unreachable for {owner}/{repo} (partial coverage: "
        "compare and releases both failed)",
    )


def _scan_other(pkg: ChangedPackage) -> "tuple[None, bool, str]":
    host = urllib.parse.urlparse(pkg.upstream_url).netloc if pkg.upstream_url else ""
    return None, False, f"no scanner for {host or 'unknown upstream'}"


def _scan_package(
    pkg: ChangedPackage, fetcher: _Fetcher
) -> "tuple[str | None, bool, str | None]":
    url = pkg.upstream_url or ""
    if _is_postgres_upstream(url):
        return _scan_postgres(pkg, fetcher)
    if "github.com" in url:
        return _scan_github(pkg, fetcher)
    return _scan_other(pkg)


_GOLANG_VERSION_RE = re.compile(r"^-\s*GOLANG_VERSION:\s*(\S+)", re.MULTILINE)
_GO_TAR_VERSION_RE = re.compile(r"go(\d+\.\d+\.\d+)")
_GOLANG_BUILD_DIRS = ("golang-1.26", "golang-1.25")


def _go_built_packages(repo_root: Path) -> "list[str]":
    """Package-dir names under repo_root whose obs/_service uses go_modules, plus gosu."""
    names: "set[str]" = set()
    for svc in repo_root.rglob("_service"):
        if ".git" in svc.parts:
            continue
        try:
            text = svc.read_text("utf-8")
        except OSError:
            continue
        if "go_modules" in text:
            names.add(svc.parent.parent.name)
    if any(p.is_dir() and ".git" not in p.parts for p in repo_root.rglob("gosu")):
        names.add("gosu")
    return sorted(names)


def _old_go_version(
    repo_root: Path, prev_tag: "str | None", run_git: _RunGit
) -> "str | None":
    if not prev_tag:
        return None
    try:
        old_text = run_git(["show", f"{prev_tag}:root/macros.yaml"])
    except Exception:
        old_text = ""
    m = _GOLANG_VERSION_RE.search(old_text)
    if m:
        return m.group(1)

    # Older layout: no GOLANG_VERSION macro yet — fall back to the golang
    # build package's obs/_service download_url at that tag.
    for golang_dir in _GOLANG_BUILD_DIRS:
        try:
            svc_text = run_git(
                ["show", f"{prev_tag}:root/common/deps/build/{golang_dir}/obs/_service"]
            )
        except Exception:
            continue
        m2 = _GO_TAR_VERSION_RE.search(svc_text)
        if m2:
            return m2.group(1)
    return None


def scan_go_toolchain(
    repo_root: Path,
    prev_tag: "str | None",
    fetcher: _Fetcher,
    run_git: _RunGit,
) -> "tuple[str | None, str | None]":
    """Return (security_line, unscanned_reason)."""
    macros_file = repo_root / "macros.yaml"
    if not macros_file.is_file():
        return None, "root/macros.yaml not found"
    m = _GOLANG_VERSION_RE.search(macros_file.read_text("utf-8"))
    if not m:
        return None, "GOLANG_VERSION not found in root/macros.yaml"
    new_version = m.group(1)

    old_version = _old_go_version(repo_root, prev_tag, run_git)
    if old_version is None:
        return None, None
    if old_version == new_version:
        return None, None

    old_parts = old_version.split(".")
    new_parts = new_version.split(".")
    if old_parts[:2] != new_parts[:2]:
        return None, f"Go minor jumped {old_version}→{new_version}, scan manually"

    try:
        old_patch = int(old_parts[2])
        new_patch = int(new_parts[2])
    except (IndexError, ValueError):
        return None, f"unrecognized Go version format {old_version}->{new_version}"

    major_minor = ".".join(new_parts[:2])
    headers = _github_headers()
    all_cves: "set[str]" = set()
    components: "set[str]" = set()

    for patch in range(old_patch + 1, new_patch + 1):
        ver = f"{major_minor}.{patch}"
        url = (
            "https://api.github.com/search/issues?q="
            f"repo:golang/go+milestone:Go{ver}+label:Security"
        )
        try:
            data = json.loads(fetcher(url, headers))
        except Exception:
            continue
        for item in data.get("items", []) or []:
            title = item.get("title") or ""
            all_cves.update(CVE_RE.findall(title))
            if ":" in title:
                components.add(title.split(":", 1)[0].strip())

    names = _go_built_packages(repo_root)
    names_str = ", ".join(names) if names else "(none)"
    cve_str = ", ".join(sorted(all_cves)) if all_cves else "no CVE ids published"
    comp_str = ", ".join(sorted(components)) if components else "none"
    line = (
        f"- Go toolchain {old_version} → {new_version} (rebuilds of {names_str}): "
        f"fixes {cve_str}, plus security fixes in {comp_str} "
        "(https://go.dev/doc/devel/release)"
    )
    return _wrap_bullet(line), None


def scan_release_cves(
    changed: "list[ChangedPackage]",
    source_path: Path,
    prev_tag: "str | None",
    *,
    fetcher: "_Fetcher | None" = None,
    has_container_images: bool = False,
) -> ScanResult:
    """Best-effort CVE scan across changed packages + the Go toolchain delta.

    Never raises: every per-package and per-source failure degrades to a
    "not scanned" note in the result rather than propagating.  *source_path*
    is the staging project directory (unused directly — the Go toolchain
    scan reads the single repo-wide ``root/macros.yaml`` via ``REPO_ROOT``,
    and per-package scans use only the data already carried on each
    ``ChangedPackage``); it is accepted to keep the call site symmetrical
    with the rest of the changelog-building code, which is keyed off the
    same staging project path.
    """
    active_fetcher: _Fetcher = fetcher or _default_fetcher
    lines: "list[str]" = []
    clean: "list[str]" = []
    unscanned: "list[tuple[str, str]]" = []

    for pkg in changed:
        try:
            line, is_clean, reason = _scan_package(pkg, active_fetcher)
        except (
            Exception
        ) as exc:  # belt and braces: one package must never sink the scan
            line, is_clean, reason = None, False, f"scan error: {exc}"
        if line:
            lines.append(line)
        elif is_clean:
            clean.append(pkg.key)
        else:
            unscanned.append((pkg.key, reason or "unknown error"))

    try:
        go_line, go_reason = scan_go_toolchain(
            REPO_ROOT, prev_tag, active_fetcher, _default_run_git
        )
    except Exception as exc:
        go_line, go_reason = None, f"scan error: {exc}"
    if go_line:
        lines.append(go_line)
    elif go_reason:
        unscanned.append(("Go toolchain", go_reason))

    if clean:
        lines.append(
            "- No CVE fixes mentioned upstream for: "
            + ", ".join(clean)
            + " (release notes and commit logs scanned for the version range)."
        )
    for key, reason in unscanned:
        lines.append(f"- Not scanned: {key} ({reason})")
    if has_container_images:
        lines.append("- UBI base-image package CVEs are not covered by this scan.")

    return ScanResult(lines=lines, clean=clean, unscanned=unscanned)
