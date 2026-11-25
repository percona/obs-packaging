#!/usr/bin/env python3
"""Check that every server extension package depends on its PostgreSQL server.

A server extension (pg_tde, pgaudit, PostGIS, ...) is useless without the
server, and must be tied to the server of the same major. If the package does
not depend on the server, `apt install percona-pg-tde17` or
`dnf install percona-pg_tde17` succeeds on a machine without PostgreSQL, and
nothing stops the extension from being installed next to an older server.

The check reads the published repository indexes only (no installs). For each
binary package whose name contains the PG major as a number of its own
(percona-pg_tde17, percona-postgresql-17-pgaudit, percona-pgvector_17), minus
the exclude patterns in the config, it follows the package's hard
dependencies (Requires / Depends / Pre-Depends) through the packages of the
same repository and reports it when none of them leads to the server package:

    RPM:    percona-postgresql<major>-server
    Debian: percona-postgresql-<major>

Dependencies on shared libraries (libpq.so.5) do not count: they are also
satisfied by the distribution's own libpq.

Exit status: 0, unless --strict and a package is missing the dependency and
is not in the config's server_dependency.allowed list.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import deque
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "package_dep_parity", Path(__file__).with_name("package_dep_parity.py")
)
pdp = importlib.util.module_from_spec(_spec)
sys.modules.setdefault(_spec.name, pdp)
_spec.loader.exec_module(pdp)


def server_package(fmt: str, major: str) -> str:
    return (
        "percona-postgresql%s-server" % major
        if fmt == "rpm"
        else "percona-postgresql-%s" % major
    )


def is_candidate(name: str, major: str, exclude: list) -> bool:
    if not name.startswith("percona-"):  # not our package (llvm17, ...)
        return False
    if not re.search(r"(?<![0-9])%s(?![0-9])" % re.escape(major), name):
        return False
    return not any(re.search(p.replace("{major}", major), name) for p in exclude)


def reaches_server(binaries: list, fmt: str, major: str) -> dict:
    """{binary name: True/False}: does it lead to the server package?

    A reverse breadth-first search from the server over the "is required by"
    edges: every package found depends on the server, directly or through
    other packages of the repository. Any alternative of an "a | b" group is
    an edge. Dependency cycles (the PG 17 server requires pg_tde, pg_tde would
    require the server) need no special handling, and the result does not
    depend on the order of the packages."""
    provider: dict = {}
    for b in binaries:
        for p in b.provides:
            provider.setdefault(p, set()).add(b.name)
    required_by: dict = {}
    for b in binaries:
        for alts in b.hard:
            for a in alts:
                for target in provider.get(a, ()):
                    required_by.setdefault(target, set()).add(b.name)
    server = server_package(fmt, major)
    reached, queue = {server}, deque([server])
    while queue:
        for dependant in required_by.get(queue.popleft(), ()):
            if dependant not in reached:
                reached.add(dependant)
                queue.append(dependant)
    return {b.name: b.name in reached for b in binaries}


def check(binaries: list, fmt: str, major: str, exclude: list) -> list | None:
    """Names of candidate packages that do not lead to the server package, or
    None when the repository has no server package of this major (nothing
    can be checked: the caller reports the repository as not checked)."""
    names = {b.name for b in binaries}
    if server_package(fmt, major) not in names:
        return None
    reach = reaches_server(binaries, fmt, major)
    return sorted(
        n
        for n in names
        if n != server_package(fmt, major)
        and is_candidate(n, major, exclude)
        and not reach[n]
    )


def allowed(package: str, repo: str, major: str, allowlist: list) -> dict | None:
    for a in allowlist:
        if str(a.get("major", "*")) not in ("*", str(major)):
            continue
        if str(a.get("repo", "*")) not in ("*", repo):
            continue
        if a.get("package", "*") in ("*", package) or re.fullmatch(
            str(a.get("package")), package
        ):
            return a
    return None


NOTHING_CHECKED = '**Nothing was checked**: no repository could be read (see "Not checked" above). This is an error, not a pass.'


def report_markdown(
    project: str, major: str, per_repo: dict, missing: dict, allowlist: list
) -> tuple:
    rows: dict = {}
    for repo, pkgs in per_repo.items():
        for p in pkgs:
            rows.setdefault(p, []).append(repo)
    # hidden only when every repository it was found in is allowlisted: an entry
    # scoped to one repository must not hide the finding in the others
    new = {
        p: r
        for p, r in rows.items()
        if not all(allowed(p, x, major, allowlist) for x in r)
    }
    lines = [
        "### 2. Extensions depend on their server: `%s`" % project,
        "",
        "%d repositories checked; **%d package(s) do not depend on the PG %s server**, %d allowlisted."
        % (len(per_repo), len(new), major, len(rows) - len(new)),
        "",
    ]
    if new:
        lines += [
            "These packages install without `%s` (RPM) / `%s` (Debian):"
            % (server_package("rpm", major), server_package("deb", major)),
            "",
            "| Package | Repositories |",
            "|---|---|",
        ]
        for p, repos in sorted(new.items()):
            lines.append("| %s | %s |" % (p, ", ".join(repos)))
        lines.append("")
    if missing:
        lines.append(
            "Not checked: "
            + ", ".join("%s (%s)" % (r, why) for r, why in sorted(missing.items()))
            + "\n"
        )
    if not per_repo:
        lines.append("%s\n" % NOTHING_CHECKED)
    return "\n".join(lines), new


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--project", required=True, help="OBS project, e.g. isv:percona:ppg:staging:17"
    )
    ap.add_argument(
        "--major", default="", help="PG major; default from the project name"
    )
    ap.add_argument("--rpm-repos", help="comma separated; default from the config")
    ap.add_argument("--deb-repos", help="comma separated; default from the config")
    ap.add_argument("--base-url", default="https://download.opensuse.org")
    ap.add_argument("--config", default=".github/package-deps-qa.yaml")
    ap.add_argument("--json", help="write the full result here")
    ap.add_argument(
        "--summary", help="append the Markdown report here (e.g. $GITHUB_STEP_SUMMARY)"
    )
    ap.add_argument(
        "--strict", action="store_true", help="exit 1 on packages not in the allowlist"
    )
    args = ap.parse_args(argv)
    major = (
        args.major or (re.search(r":(1[0-9])(?::|$)", args.project) or [None, ""])[1]
    )
    if not major:
        ap.error("cannot tell the PG major from %s; give --major" % args.project)
    cfg = pdp.load_qa_config(args.config)
    section = cfg.get("server_dependency") or {}
    repos_cfg = cfg.get("repos") or {}
    rpm_repos = (
        args.rpm_repos.split(",")
        if args.rpm_repos
        else list(repos_cfg.get("rpm") or ["RockyLinux_9"])
    )
    deb_repos = (
        args.deb_repos.split(",")
        if args.deb_repos
        else list(repos_cfg.get("deb") or ["Debian_12"])
    )
    exclude = list(section.get("exclude") or [])
    allowlist = list(section.get("allowed") or [])
    for i, e in enumerate(allowlist, 1):
        # an entry without "package" (only a reason, or a typo) would allow everything
        if "package" not in (e or {}):
            ap.error(
                'server_dependency allowlist entry %d has no package (use "*" for any): %r'
                % (i, e)
            )

    per_repo, missing = {}, {}
    for fmt, repos in (("rpm", rpm_repos), ("deb", deb_repos)):
        for repo in repos:
            url = pdp.repo_url(args.base_url, args.project, repo)
            try:
                binaries = (
                    pdp.load_rpm_repo(url) if fmt == "rpm" else pdp.load_deb_repo(url)
                )
            except SystemExit as e:
                missing[repo] = str(e)
                continue
            found = check(binaries, fmt, major, exclude)
            if found is None:
                missing[repo] = "no %s package in the repository" % server_package(
                    fmt, major
                )
            else:
                per_repo[repo] = found
    md, new = report_markdown(args.project, major, per_repo, missing, allowlist)
    print(md)
    if args.summary:
        with open(args.summary, "a") as f:
            f.write(md + "\n")
    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {"per_repo": per_repo, "missing": missing, "new": new},
                indent=2,
                sort_keys=True,
            )
        )
    if not per_repo:
        return 2  # nothing checked is an error, in report-only mode too
    return 1 if (args.strict and new) else 0


if __name__ == "__main__":
    sys.exit(main())
