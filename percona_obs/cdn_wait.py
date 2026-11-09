"""``qa wait-cdn``: wait until the download CDN serves what OBS published.

Arch-independent binaries (``_all.deb``, ``noarch.rpm``) keep their file
name when the published copy changes (another arch's build wins the
publish), and the download CDN keeps serving the old bytes until its cache
entry expires.  apt/dnf then fail with "File has unexpected size" or a
checksum mismatch.  This gate compares every such file's origin headers
with the CDN's before QA starts.

The CDN caches each URL spelling separately, so a ``+`` in a file name is
checked both raw and percent-encoded (apt and dnf do not agree on it).
"""

import argparse
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import osc.connection
import osc.core

from .common import _print_ok, _print_pending
from .obs_api import _fetch_obs_subproject_names

# Directories of a published repo that hold arch-independent binaries.
_ARCH_INDEPENDENT_DIRS = ("all", "noarch")


def _published_entries(apiurl: str, *path: str) -> "list[str]":
    url = osc.core.makeurl(apiurl, ["published", *path])
    try:
        root = ET.fromstring(osc.connection.http_GET(url).read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    return [e.get("name", "") for e in root.findall("entry") if e.get("name")]


def arch_independent_files(apiurl: str, obs_project: str) -> "list[str]":
    """Repository-relative paths (``<project>/<repo>/<dir>/<file>``) of every
    published arch-independent binary of *obs_project*."""
    files = []
    for repo in _published_entries(apiurl, obs_project):
        entries = set(_published_entries(apiurl, obs_project, repo))
        for d in _ARCH_INDEPENDENT_DIRS:
            if d in entries:
                files += [
                    f"{obs_project}/{repo}/{d}/{name}"
                    for name in _published_entries(apiurl, obs_project, repo, d)
                    if name.endswith((".deb", ".rpm"))
                ]
    return files


def url_spellings(host: str, path: str) -> "list[str]":
    """Download URLs of *path* (``a:b:c/repo/dir/file``) on *host*, one per
    spelling the CDN caches separately."""
    project, rest = path.split("/", 1)
    base = f"https://{host}/repositories/{project.replace(':', ':/')}/"
    raw = base + urllib.parse.quote(rest, safe="/+")
    encoded = base + urllib.parse.quote(rest, safe="/")
    return [raw] if raw == encoded else [raw, encoded]


def _head(url: str) -> "tuple[str, str]":
    """(ETag, Content-Length) of *url*; ("", "") when unreachable."""
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.headers.get("ETag", ""), resp.headers.get("Content-Length", "")
    except (urllib.error.URLError, OSError):
        return "", ""


def stale_files(paths: "list[str]", origin: str, cdn: str) -> "list[str]":
    """CDN URLs whose headers differ from the origin's (or are unreachable)."""
    pairs = [
        (o, c)
        for p in paths
        for o, c in zip(url_spellings(origin, p), url_spellings(cdn, p))
    ]
    with ThreadPoolExecutor(max_workers=16) as pool:
        heads = list(pool.map(lambda pair: (_head(pair[0]), _head(pair[1])), pairs))
    return [
        c for (_, c), (want, got) in zip(pairs, heads) if not want[0] or want != got
    ]


def cmd_qa_wait_cdn(args: argparse.Namespace) -> None:
    obs_projects = []
    for project in args.projects:
        top = f"{args.rootprj}:{project}"
        obs_projects += [top, *sorted(_fetch_obs_subproject_names(args.apiurl, top))]
    paths = [
        p for prj in obs_projects for p in arch_independent_files(args.apiurl, prj)
    ]
    if not paths:
        _print_ok("no published arch-independent binaries to check")
        return
    deadline = time.monotonic() + args.timeout * 60
    while True:
        stale = stale_files(paths, args.origin, args.cdn)
        if not stale:
            _print_ok(f"{args.cdn} serves all {len(paths)} arch-independent files")
            return
        if time.monotonic() >= deadline:
            listing = "\n".join(f"  {u}" for u in stale)
            print(
                f"error: {len(stale)} CDN URL(s) still differ from {args.origin} "
                f"after {args.timeout} min:\n{listing}",
                file=sys.stderr,
            )
            sys.exit(1)
        _print_pending(
            f"{len(stale)} of {len(paths)} file(s) stale on {args.cdn} "
            f"(retry in {args.interval} min)"
        )
        time.sleep(args.interval * 60)
