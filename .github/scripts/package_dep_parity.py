#!/usr/bin/env python3
"""Compare Percona package dependencies between the RPM and Debian builds.

The same product is packaged twice, as RPM (rpm/*.spec) and as Debian
packages (debian/control), in separate files. A mistake usually lands in only
one of them: e.g. PG 17's RPM server package requires pg_tde, the Debian one
did not. This check finds such differences from the published repository
indexes alone (no installs, no history needed):

  for each source package, the set of OTHER source packages in the same OBS
  repository that its binaries depend on (hard: Requires / Depends /
  Pre-Depends; weak: Recommends), compared between one RPM and one Debian
  repository of the same project.

Dependencies on packages that are not in the repository (system libraries,
distribution packages) are ignored, so the comparison is between Percona's own
packages only. Source names differ between the formats (percona-pg_tde17,
percona-pg-tde-17, ...); they are compared after normalising: lowercase,
letters and digits only, the PG major removed. Intended differences go in the
allowlist (--allowlist), each with a reason.

Exit status: 0, unless --strict and there are differences not in the allowlist.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import lzma
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs pyyaml
    yaml = None

RPM_NS = {
    "c": "http://linux.duke.edu/metadata/common",
    "rpm": "http://linux.duke.edu/metadata/rpm",
    "r": "http://linux.duke.edu/metadata/repo",
}


# ----------------------------------------------------------------- fetching


def fetch(url: str, attempts: int = 4) -> bytes | None:
    """GET url; None on 404. Retries transient errors."""
    for i in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if i == attempts - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if i == attempts - 1:
                raise
        time.sleep(5 * (i + 1))
    return None


def decompress(data: bytes, name: str) -> bytes:
    if name.endswith(".gz"):
        return gzip.decompress(data)
    if name.endswith(".xz"):
        return lzma.decompress(data)
    if name.endswith(".zst"):
        try:
            import zstandard  # type: ignore

            return zstandard.ZstdDecompressor().decompressobj().decompress(data)
        except ImportError:
            return subprocess.run(
                ["zstd", "-dc"], input=data, capture_output=True, check=True
            ).stdout
    return data


def repo_url(base_url: str, project: str, repo: str) -> str:
    return "%s/repositories/%s/%s/" % (
        base_url.rstrip("/"),
        project.replace(":", ":/"),
        repo,
    )


# ----------------------------------------------------------------- parsing


@dataclass
class Binary:
    name: str
    source: str
    provides: set = field(default_factory=set)
    hard: list = field(
        default_factory=list
    )  # list of alternatives: [["a", "b"], ["c"]]
    weak: list = field(default_factory=list)


def _rpm_dep_names(entry_name: str) -> list:
    """Names in an rpm dependency; rich deps '(a or b)' give several."""
    if entry_name.startswith("("):
        words = re.findall(r"[A-Za-z0-9_.+-]+", entry_name)
        return [
            w
            for w in words
            if w not in ("or", "and", "if", "else", "with", "without", "unless")
            and not re.fullmatch(r"[0-9.:~+-]+", w)
        ]
    return [entry_name]


def parse_rpm_primary(xml_bytes: bytes) -> list:
    root = ET.fromstring(xml_bytes)
    out = []
    for pkg in root.findall("c:package", RPM_NS):
        if pkg.get("type") != "rpm":
            continue
        name = pkg.findtext("c:name", default="", namespaces=RPM_NS)
        if pkg.findtext("c:arch", default="", namespaces=RPM_NS) == "src":
            continue
        fmt = pkg.find("c:format", RPM_NS)
        srpm = (
            fmt.findtext("rpm:sourcerpm", default="", namespaces=RPM_NS)
            if fmt is not None
            else ""
        )
        source = (
            srpm[: -len(".src.rpm")].rsplit("-", 2)[0]
            if srpm.endswith(".src.rpm")
            else name
        )
        b = Binary(name=name, source=source, provides={name})
        if fmt is not None:
            for e in fmt.findall("rpm:provides/rpm:entry", RPM_NS):
                b.provides.add(e.get("name"))
            for tag, target in (("requires", b.hard), ("recommends", b.weak)):
                for e in fmt.findall("rpm:%s/rpm:entry" % tag, RPM_NS):
                    n = e.get("name") or ""
                    # rpmlib()/file/shared-library deps say nothing about
                    # which Percona package is needed; user()/group() are the
                    # accounts EL10 generates, provided by several packages.
                    if n.startswith(("rpmlib(", "/", "user(", "group(")) or ".so" in n:
                        continue
                    target.append(_rpm_dep_names(n))
        out.append(b)
    return out


def _deb_field_alternatives(value: str) -> list:
    groups = []
    for part in value.split(","):
        alts = []
        for alt in part.split("|"):
            alt = re.sub(r"\(.*?\)|\[.*?\]|<.*?>", "", alt).strip()
            alt = alt.split(":")[0].strip()  # foo:any
            if alt:
                alts.append(alt)
        if alts:
            groups.append(alts)
    return groups


def parse_deb_packages(text: str) -> list:
    out = []
    for stanza in re.split(r"\n\s*\n", text.strip()):
        fields, last = {}, None
        for line in stanza.splitlines():
            if line[:1] in (" ", "\t") and last:
                fields[last] += " " + line.strip()
            elif ":" in line:
                last, _, v = line.partition(":")
                fields[last.strip()] = v.strip()
        name = fields.get("Package")
        if not name:
            continue
        source = (fields.get("Source") or name).split("(")[0].strip()
        b = Binary(name=name, source=source, provides={name})
        for alts in _deb_field_alternatives(fields.get("Provides", "")):
            b.provides.update(alts)
        b.hard = _deb_field_alternatives(
            fields.get("Depends", "")
        ) + _deb_field_alternatives(fields.get("Pre-Depends", ""))
        b.weak = _deb_field_alternatives(fields.get("Recommends", ""))
        out.append(b)
    return out


def load_rpm_repo(url: str) -> list:
    repomd = fetch(url + "repodata/repomd.xml")
    if repomd is None:
        raise SystemExit("no RPM repository at %s" % url)
    root = ET.fromstring(repomd)
    for data in root.findall("r:data", RPM_NS):
        if data.get("type") == "primary":
            href = data.find("r:location", RPM_NS).get("href")
            primary = fetch(url + href)
            if primary is None:
                # repomd.xml names a primary file that is not there (yet): OBS is
                # republishing, or the mirror we were sent to is behind
                raise SystemExit(
                    "no %s at %s (repository is being republished?)" % (href, url)
                )
            return parse_rpm_primary(decompress(primary, href))
    raise SystemExit("no primary metadata in %srepodata/repomd.xml" % url)


def load_deb_repo(url: str) -> list:
    for name in ("Packages.xz", "Packages.gz", "Packages"):
        data = fetch(url + name)
        if data is not None:
            return parse_deb_packages(decompress(data, name).decode("utf-8", "replace"))
    raise SystemExit("no Debian Packages index at %s" % url)


# ----------------------------------------------------------------- comparison


def normalise(source: str, major: str) -> str:
    s = re.sub(r"[^a-z0-9]", "", source.lower())
    if major:
        s = (
            re.sub(
                r"(?<![0-9])%s(?![0-9])" % re.escape(major),
                "",
                re.sub(r"[^a-z0-9]+", " ", source.lower()),
            ).replace(" ", "")
            or s
        )
    return s


def dependency_graph(binaries: list, major: str) -> dict:
    """{normalised source: {"hard": set(normalised sources), "weak": set(...), "name": original}}"""
    provider = {}
    for b in binaries:
        for p in b.provides:
            provider.setdefault(p, set()).add(b.source)
    graph = {}
    for b in binaries:
        src = normalise(b.source, major)
        node = graph.setdefault(src, {"hard": set(), "weak": set(), "name": b.source})
        for kind in ("hard", "weak"):
            for alts in getattr(b, kind):
                targets = set()
                for a in alts:
                    targets |= {normalise(s, major) for s in provider.get(a, ())}
                targets.discard(src)
                if targets:
                    node[kind].add("|".join(sorted(targets)))
    return graph


def apply_aliases(graph: dict, aliases: dict) -> dict:
    """Rename sources that are the same product under another name in one
    format (e.g. perconapostgis35 -> perconapostgis), keys and targets."""
    if not aliases:
        return graph
    ren = lambda n: aliases.get(n, n)
    out = {}
    for src, node in graph.items():
        dst = out.setdefault(
            ren(src), {"hard": set(), "weak": set(), "name": node["name"]}
        )
        for kind in ("hard", "weak"):
            for dep in node[kind]:
                renamed = "|".join(sorted({ren(t) for t in dep.split("|")}))
                if renamed != ren(src):
                    dst[kind].add(renamed)
    return out


def _comparable(dep: str, common: set):
    """A dependency restricted to sources that exist in both formats; None
    if none does (e.g. RPM-only python312-* packages): it cannot be compared."""
    kept = sorted(t for t in dep.split("|") if t in common)
    return "|".join(kept) if kept else None


def compare(rpm: dict, deb: dict) -> dict:
    common = set(rpm) & set(deb)
    both = sorted(common)
    diffs = []
    for src in both:
        for kind in ("hard", "weak"):
            r = {d for d in (_comparable(x, common) for x in rpm[src][kind]) if d}
            b = {d for d in (_comparable(x, common) for x in deb[src][kind]) if d}
            only_rpm = sorted(r - b)
            only_deb = sorted(b - r)
            for dep in only_rpm:
                diffs.append(
                    {"source": src, "kind": kind, "dep": dep, "only_in": "rpm"}
                )
            for dep in only_deb:
                diffs.append(
                    {"source": src, "kind": kind, "dep": dep, "only_in": "deb"}
                )
    return {
        "diffs": diffs,
        "only_rpm_sources": sorted(set(rpm) - set(deb)),
        "only_deb_sources": sorted(set(deb) - set(rpm)),
        "compared_sources": len(both),
    }


def load_qa_config(path: str | None):
    """The parsed config file (.github/package-deps-qa.yaml), shared by all
    the package-deps checks; {} when there is no such file. Stops with a clear
    error when pyyaml is missing, instead of silently using an empty config."""
    if not path or not Path(path).is_file():
        return {}
    if yaml is None:
        raise SystemExit("pyyaml is needed to read %s: pip install pyyaml" % path)
    return yaml.safe_load(Path(path).read_text()) or {}


def load_config(path: str | None) -> tuple:
    """(aliases, allowed) from the allowlist file: either a list of allowed
    entries, or {aliases: {name: name}, allowed: [entries]}."""
    data = load_qa_config(path) or []
    if isinstance(data, dict) and "parity" in data:  # .github/package-deps-qa.yaml
        data = data["parity"] or {}
    if isinstance(data, dict):
        aliases, entries = dict(data.get("aliases") or {}), list(
            data.get("allowed") or []
        )
    else:
        aliases, entries = {}, list(data)
    for i, e in enumerate(entries, 1):
        # an entry without source/dep (only a reason, or a typo such as
        # "sources:") would otherwise allow every difference
        missing = [k for k in ("source", "dep") if k not in (e or {})]
        if missing:
            raise SystemExit(
                '%s: parity allowlist entry %d has no %s (use "*" for any): %r'
                % (path, i, " or ".join(missing), e)
            )
    return aliases, entries


def load_allowlist(path: str | None) -> list:
    return load_config(path)[1]


def allowed(diff: dict, major: str, allowlist: list) -> dict | None:
    """The allowlist entry covering diff, if any. Any field may be '*'."""
    for a in allowlist:
        if str(a.get("major", "*")) not in ("*", str(major)):
            continue
        if all(
            str(a[k]) in ("*", str(diff[k]))
            for k in ("source", "dep", "kind", "only_in")
            if k in a
        ):
            return a
    return None


def report_markdown(
    project: str,
    rpm_repo: str,
    deb_repo: str,
    result: dict,
    major: str,
    allowlist: list,
) -> str:
    new = [d for d in result["diffs"] if not allowed(d, major, allowlist)]
    known = [d for d in result["diffs"] if allowed(d, major, allowlist)]
    lines = [
        "### Package dependency parity: `%s` (%s vs %s)"
        % (project, rpm_repo, deb_repo),
        "",
        "%d source packages compared; **%d difference(s) to review**, %d allowlisted."
        % (result["compared_sources"], len(new), len(known)),
        "",
    ]
    if new:
        lines += [
            "Each row is one dependency, read left to right: **package** depends on **dependency**,",
            "declared in one format and missing in the other.",
            "",
            "| Package | depends on | Dependency | RPM | Debian |",
            "|---|---|---|---|---|",
        ]
        for d in new:
            rel = "requires" if d["kind"] == "hard" else "recommends"
            in_rpm, in_deb = (
                ("✓", "✗ missing") if d["only_in"] == "rpm" else ("✗ missing", "✓")
            )
            lines.append(
                "| %s | %s | %s | %s | %s |"
                % (d["source"], rel, d["dep"], in_rpm, in_deb)
            )
        lines.append("")
    for label, key in (
        ("Only in RPM", "only_rpm_sources"),
        ("Only in Debian", "only_deb_sources"),
    ):
        if result[key]:
            lines.append(
                "<details><summary>%s: %d source package(s) (not compared)</summary>\n\n%s\n\n</details>\n"
                % (label, len(result[key]), ", ".join(result[key]))
            )
    return "\n".join(lines)


def _config_pairs(path: str | None) -> list:
    data = load_qa_config(path)
    return list(
        ((data.get("parity") or {}) if isinstance(data, dict) else {}).get("pairs")
        or []
    )


def merge_results(per_pair: dict) -> list:
    """One row per difference, with the repository pairs it was seen in."""
    rows = {}
    for pair, result in per_pair.items():
        for d in result["diffs"]:
            key = (d["source"], d["kind"], d["dep"], d["only_in"])
            rows.setdefault(
                key,
                {
                    "source": d["source"],
                    "kind": d["kind"],
                    "dep": d["dep"],
                    "only_in": d["only_in"],
                    "pairs": [],
                },
            )["pairs"].append(pair)
    return sorted(rows.values(), key=lambda r: (r["source"], r["kind"], r["dep"]))


NOTHING_CHECKED = '**Nothing was checked**: no repository could be read (see "Not checked" above). This is an error, not a pass.'


def report_pairs_markdown(
    project: str, per_pair: dict, missing: dict, major: str, allowlist: list
) -> tuple:
    rows = merge_results(per_pair)
    new = [r for r in rows if not allowed(r, major, allowlist)]
    lines = [
        "### 1. RPM vs Debian dependency parity: `%s`" % project,
        "",
        "%d repository pair(s) compared; **%d difference(s) to review**, %d allowlisted."
        % (len(per_pair), len(new), len(rows) - len(new)),
        "",
    ]
    if new:
        lines += [
            "Read each row left to right: **package** requires (or recommends) **dependency** in one format "
            'but not in the other. *Seen in* lists the RPM:Debian pairs; "all" means every pair, i.e. '
            "a difference between the formats rather than one distribution.",
            "",
            "| Package | depends on | Dependency | Declared in | Missing in | Seen in |",
            "|---|---|---|---|---|---|",
        ]
        for r in new:
            rel = "requires" if r["kind"] == "hard" else "recommends"
            has, lacks = (
                ("RPM", "Debian") if r["only_in"] == "rpm" else ("Debian", "RPM")
            )
            seen = "all" if len(r["pairs"]) == len(per_pair) else ", ".join(r["pairs"])
            lines.append(
                "| %s | %s | %s | %s | %s | %s |"
                % (r["source"], rel, r["dep"], has, lacks, seen)
            )
        lines.append("")
    if missing:
        lines.append(
            "Not compared: "
            + ", ".join("%s (%s)" % (p, why) for p, why in sorted(missing.items()))
            + "\n"
        )
    if not per_pair:
        lines.append("%s\n" % NOTHING_CHECKED)
    return "\n".join(lines), new, rows


def main_pairs(args, major: str) -> int:
    aliases, allowlist = load_config(args.allowlist)
    pairs = [
        p.strip()
        for p in (
            args.pairs.split(",") if args.pairs else _config_pairs(args.allowlist)
        )
        if p.strip()
    ]
    graphs, per_pair, missing = {}, {}, {}

    def graph(kind: str, repo: str):
        if (kind, repo) not in graphs:
            url = repo_url(args.base_url, args.project, repo)
            try:
                loaded = load_rpm_repo(url) if kind == "rpm" else load_deb_repo(url)
                graphs[(kind, repo)] = apply_aliases(
                    dependency_graph(loaded, major), aliases
                )
            except SystemExit as e:
                graphs[(kind, repo)] = str(e)
        return graphs[(kind, repo)]

    for pair in pairs:
        r, d = pair.split(":", 1)
        rg, dg = graph("rpm", r), graph("deb", d)
        if isinstance(rg, str) or isinstance(dg, str):
            # the loader's own message: not published, or e.g. being republished
            missing[pair] = rg if isinstance(rg, str) else dg
            continue
        per_pair[pair] = compare(rg, dg)
    md, new, rows = report_pairs_markdown(
        args.project, per_pair, missing, major, allowlist
    )
    print(md)
    if args.summary:
        with open(args.summary, "a") as f:
            f.write(md + "\n")
    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "pairs": per_pair,
                    "missing": missing,
                    "differences": rows,
                    "new": new,
                },
                indent=2,
                sort_keys=True,
            )
        )
    if not per_pair:
        return 2  # nothing compared is an error, in report-only mode too
    return 1 if (args.strict and new) else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--project", default="", help="OBS project, e.g. isv:percona:ppg:staging:17"
    )
    ap.add_argument(
        "--major",
        default="",
        help="PG major (removed from names before comparing), e.g. 17",
    )
    ap.add_argument(
        "--rpm-repo", default=None, help="one RPM repository (default RockyLinux_9)"
    )
    ap.add_argument(
        "--deb-repo", default=None, help="one Debian repository (default Debian_12)"
    )
    ap.add_argument("--base-url", default="https://download.opensuse.org")
    ap.add_argument(
        "--rpm-url",
        help="RPM repository address (directory with repodata/) instead of an OBS "
        "project, e.g. https://repo.percona.com/ppg-17.10/yum/release/9/RPMS/x86_64/",
    )
    ap.add_argument(
        "--deb-url",
        help="Debian repository directory with Packages(.xz|.gz) instead of an OBS project, "
        "e.g. https://repo.percona.com/ppg-17.10/apt/dists/bookworm/main/binary-amd64/",
    )
    ap.add_argument(
        "--pairs",
        help="several RPM:DEB repository pairs, comma separated, compared in one report "
        "(e.g. RockyLinux_9:Debian_12,RockyLinux_8:Debian_12); default from the config",
    )
    ap.add_argument(
        "--allowlist",
        "--config",
        dest="allowlist",
        default=".github/package-deps-qa.yaml",
    )
    ap.add_argument("--json", help="write the full result here")
    ap.add_argument(
        "--summary", help="append the Markdown report here (e.g. $GITHUB_STEP_SUMMARY)"
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 on differences not in the allowlist",
    )
    args = ap.parse_args(argv)
    if not args.project and not (args.rpm_url and args.deb_url):
        ap.error("give --project, or both --rpm-url and --deb-url")
    major = (
        args.major or (re.search(r":(1[0-9])(?::|$)", args.project) or [None, ""])[1]
    )
    if args.pairs or (
        args.project
        and not args.rpm_url
        and _config_pairs(args.allowlist)
        and args.rpm_repo is None
        and args.deb_repo is None
    ):
        return main_pairs(args, major)
    args.rpm_repo = args.rpm_repo or "RockyLinux_9"
    args.deb_repo = args.deb_repo or "Debian_12"
    rpm_url = (
        args.rpm_url.rstrip("/") + "/"
        if args.rpm_url
        else repo_url(args.base_url, args.project, args.rpm_repo)
    )
    deb_url = (
        args.deb_url.rstrip("/") + "/"
        if args.deb_url
        else repo_url(args.base_url, args.project, args.deb_repo)
    )
    label = args.project or "%s vs %s" % (rpm_url, deb_url)
    aliases, allowlist = load_config(args.allowlist)
    rpm = apply_aliases(dependency_graph(load_rpm_repo(rpm_url), major), aliases)
    deb = apply_aliases(dependency_graph(load_deb_repo(deb_url), major), aliases)
    result = compare(rpm, deb)
    md = report_markdown(
        label,
        args.rpm_url and "RPM" or args.rpm_repo,
        args.deb_url and "Debian" or args.deb_repo,
        result,
        major,
        allowlist,
    )
    print(md)
    if args.summary:
        with open(args.summary, "a") as f:
            f.write(md + "\n")
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, sort_keys=True))
    new = [d for d in result["diffs"] if not allowed(d, major, allowlist)]
    return 1 if (args.strict and new) else 0


if __name__ == "__main__":
    sys.exit(main())
