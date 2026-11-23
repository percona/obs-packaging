#!/usr/bin/env python3
"""Check that every package of an OBS project can be installed on its OS.

For each repository (OS) of the project, a throw-away container of that OS
gets the OBS repository added, and every package in it (amd64 and
architecture-independent) is checked against the OS repositories plus the
OBS repository. Nothing is really installed:

  EL (Rocky 8/9/10)  dnf repoclosure --check obs, twice:
                       - with EPEL and CRB/PowerTools: what our install docs
                         ask for. A package that fails here is a FAILURE.
                       - with the base OS repositories only: packages that
                         fail only here "need EPEL/CRB" (information, to keep
                         the install docs right).
  Debian / Ubuntu    apt-get install --simulate <package>, for every package.
                     A package that fails is a FAILURE.

A repository the project does not publish is shown as "not published".

Exit status: 0, unless --strict and there are failures not in the config's
installable.allowed list.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs pyyaml
    yaml = None

DEFAULT_IMAGES = {
    "RockyLinux_8": "docker.io/rockylinux/rockylinux:8",
    "RockyLinux_9": "docker.io/rockylinux/rockylinux:9",
    "RockyLinux_10": "docker.io/rockylinux/rockylinux:10",
    "Debian_12": "docker.io/library/debian:12",
    "Debian_13": "docker.io/library/debian:13",
    "Ubuntu_22.04": "docker.io/library/ubuntu:22.04",
    "Ubuntu_24.04": "docker.io/library/ubuntu:24.04",
    "Ubuntu_26.04": "docker.io/library/ubuntu:26.04",
}

# Runs inside the EL container. Prints repoclosure's report, then
# "RESULT <status> checked=<n>".
EL_SCRIPT = r'''
dnf -y -q install dnf-plugins-core >/dev/null 2>&1 || { echo "RESULT base-setup-failed checked=0"; exit 0; }
if [ "$WITH_EPEL" = 1 ]; then
  dnf -y -q install epel-release >/dev/null 2>&1 ||
    dnf -y -q install "https://dl.fedoraproject.org/pub/epel/epel-release-latest-$EL.noarch.rpm" >/dev/null 2>&1
  dnf config-manager --set-enabled crb >/dev/null 2>&1 ||
    dnf config-manager --set-enabled powertools >/dev/null 2>&1 || true
fi
# the install docs disable the distribution's postgresql module on EL8
[ "$EL" = 8 ] && dnf -y -q module disable postgresql >/dev/null 2>&1
printf "[obs]\nname=obs\nbaseurl=%s\nenabled=1\ngpgcheck=0\n" "$URL" > /etc/yum.repos.d/obs.repo
# the OBS repository was found published before the container started, so a
# failure here (ours, or a Rocky/EPEL mirror) is a failure, not "not published"
dnf -q makecache >/tmp/makecache.log 2>&1 || { tail -3 /tmp/makecache.log | sed "s/^/    /"; echo "RESULT repo-unreachable checked=0"; exit 0; }
n=$(dnf -q repoquery --repo obs --latest-limit 1 --arch x86_64,noarch --qf "%{name}" 2>/dev/null | sort -u | wc -l)
[ "$n" -eq 0 ] && { echo "RESULT no-packages checked=0"; exit 0; }
dnf -q repoclosure --check obs --newest --arch x86_64 --arch noarch 2>&1
echo "RESULT ok checked=$n"
'''

# Runs inside the Debian/Ubuntu container. Prints "package: <name>" and the
# indented reason for every package that cannot be installed.
DEB_SCRIPT = r'''
export DEBIAN_FRONTEND=noninteractive
{ apt-get update -qq && apt-get install -y -qq ca-certificates curl gnupg xz-utils; } >/dev/null 2>&1 ||
  { echo "RESULT base-setup-failed checked=0"; exit 0; }
curl -fsSL "$URL/Release.key" | gpg --dearmor -o /usr/share/keyrings/obs.gpg 2>/dev/null ||
  { echo "RESULT repo-unreachable checked=0"; exit 0; }
echo "deb [signed-by=/usr/share/keyrings/obs.gpg] $URL/ /" > /etc/apt/sources.list.d/obs.list
apt-get update -qq >/dev/null 2>&1
{ curl -fsSL "$URL/Packages.gz" | gzip -dc || curl -fsSL "$URL/Packages.xz" | xz -dc; } > /tmp/P 2>/dev/null
awk '/^Package:/{p=$2} /^Architecture:/{a=$2}
     /^$/{if(p!=""&&(a=="amd64"||a=="all"))print p; p="";a=""}
     END{if(p!=""&&(a=="amd64"||a=="all"))print p}' /tmp/P | sort -u > /tmp/pkgs
n=$(wc -l < /tmp/pkgs)
[ "$n" -eq 0 ] && { echo "RESULT no-packages checked=0"; exit 0; }
while read -r p; do
  if ! out=$(apt-get install -s -qq "$p" 2>&1); then
    echo "package: $p"
    echo "$out" | grep -E "Depends:|Breaks:|Conflicts:|Pre-Depends:|not installable|not going to be installed|E: " | sed "s/^/    /"
  fi
done < /tmp/pkgs
echo "RESULT ok checked=$n"
'''


def repo_url(base_url: str, project: str, repo: str) -> str:
    return "%s/repositories/%s/%s" % (base_url.rstrip("/"), project.replace(":", ":/"), repo)


def parse_output(text: str) -> tuple:
    """(status, checked, {package name: [reason lines]}) from a container run."""
    status, checked = "container-failed", 0
    failures: dict = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"RESULT (\S+) checked=(\d+)", line)
        if m:
            status, checked = m.group(1), int(m.group(2))
            continue
        m = re.match(r"package: (\S+)", line)
        if m:
            current = package_name(m.group(1))
            failures.setdefault(current, [])
            continue
        if current and line.startswith("    ") and line.strip():
            failures[current].append(line.strip())
    return status, checked, failures


def package_name(nevra: str) -> str:
    """percona-pgaudit17-llvmjit-1:17.2-2.2.el9.x86_64 -> percona-pgaudit17-llvmjit.
    Debian names (no version) are returned unchanged."""
    m = re.match(r"(.+)-(?:\d+:)?[^-]+-[^-]+\.(?:x86_64|aarch64|noarch)$", nevra)
    return m.group(1) if m else nevra


def run_container(docker: str, image: str, script: str, env: dict, timeout: int = 3600) -> str:
    # the image was pulled once at the start of the run (pull_images)
    cmd = [docker, "run", "--rm", "--pull=never"]
    for k, v in env.items():
        cmd += ["-e", "%s=%s" % (k, v)]
    cmd += [image, "bash", "-c", script]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return "RESULT timeout checked=0"


def is_el(repo: str) -> bool:
    return repo.startswith(("RockyLinux_", "RHEL_", "AlmaLinux_", "OracleLinux_"))


def obs_repo_state(repo: str, url: str, attempts: int = 3) -> str:
    """"published", "not-published" (the index file is a 404: the project does
    not build for this OS) or "obs-unreachable" (anything else: a failure)."""
    index = url + ("/repodata/repomd.xml" if is_el(repo) else "/Release")
    for i in range(attempts):
        try:
            with urllib.request.urlopen(index, timeout=60):
                return "published"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "not-published"
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        if i < attempts - 1:
            time.sleep(5 * (i + 1))
    return "obs-unreachable"


def pull_images(docker: str, images: list, attempts: int = 3) -> dict:
    """Pull each image once per run, newest version: {image: error or ""}.
    One pull per image (not per container) also keeps Docker Hub's anonymous
    rate limit in check when several majors run at once."""
    errors = {}
    for image in sorted(set(images)):
        err = ""
        for i in range(attempts):
            p = subprocess.run([docker, "pull", "-q", image], capture_output=True, text=True)
            err = "" if p.returncode == 0 else (p.stderr.strip().splitlines() or ["pull failed"])[-1]
            if not err:
                break
            time.sleep(10 * (i + 1))
        errors[image] = err
    return errors


def empty_result(status: str, why: str = "") -> dict:
    return {"status": status, "checked": 0, "failures": {}, "needs_epel": {}, "why": why}


def check_repo(repo: str, url: str, image: str, docker: str) -> dict:
    """One repository: {"status", "checked", "failures", "needs_epel"}."""
    state = obs_repo_state(repo, url)
    if state != "published":
        return empty_result(state)
    if is_el(repo):
        el = repo.rsplit("_", 1)[1].split(".")[0]
        full = parse_output(run_container(docker, image, EL_SCRIPT, {"URL": url + "/", "EL": el, "WITH_EPEL": 1}))
        base = parse_output(run_container(docker, image, EL_SCRIPT, {"URL": url + "/", "EL": el, "WITH_EPEL": 0}))
        needs = {p: r for p, r in base[2].items() if p not in full[2]}
        return {"status": full[0], "checked": full[1], "failures": full[2], "needs_epel": needs}
    status, checked, failures = parse_output(run_container(docker, image, DEB_SCRIPT, {"URL": url}))
    return {"status": status, "checked": checked, "failures": failures, "needs_epel": {}}


def check_allowlist(entries, path: str) -> list:
    """The allowlist, refusing entries without "package" (use "*" for any): an
    entry with only a reason, or a typo, would otherwise allow everything."""
    entries = list(entries or [])
    for i, e in enumerate(entries, 1):
        if "package" not in (e or {}):
            raise SystemExit('%s: installable allowlist entry %d has no package (use "*" for any): %r' % (path, i, e))
    return entries


def allowed(package: str, repo: str, major: str, allowlist: list) -> dict | None:
    for a in allowlist:
        if str(a.get("major", "*")) not in ("*", str(major)):
            continue
        if str(a.get("repo", "*")) not in ("*", repo):
            continue
        if a.get("package", "*") == "*" or re.fullmatch(str(a["package"]), package):
            return a
    return None


def report_markdown(project: str, major: str, results: dict, allowlist: list) -> tuple:
    fails: dict = {}
    needs: dict = {}
    for repo, r in results.items():
        for p, why in r["failures"].items():
            fails.setdefault(p, {"repos": [], "why": set()})
            fails[p]["repos"].append(repo)
            fails[p]["why"].update(why)
        for p, why in r["needs_epel"].items():
            needs.setdefault(p, {"repos": [], "why": set()})
            needs[p]["repos"].append(repo)
            needs[p]["why"].update(why)
    new = {p: v for p, v in fails.items() if not all(allowed(p, x, major, allowlist) for x in v["repos"])}
    checked = [r for r in results.values() if r["status"] == "ok"]
    broken = {repo: r["status"] for repo, r in results.items() if r["status"] not in ("ok", "not-published")}
    unpublished = sorted(repo for repo, r in results.items() if r["status"] == "not-published")
    lines = ["### 3. Every package installs: `%s`" % project, "",
             "%d repositories checked (%d packages); **%d package(s) cannot be installed**, %d allowlisted." %
             (len(checked), sum(r["checked"] for r in checked), len(new), len(fails) - len(new)), ""]
    if new:
        lines += ["| Package | Repositories | Missing / conflicting |", "|---|---|---|"]
        for p, v in sorted(new.items()):
            why = "; ".join(sorted(v["why"]))[:300] or "see the job log"
            lines.append("| %s | %s | %s |" % (p, ", ".join(v["repos"]), why.replace("|", "\\|")))
        lines.append("")
    if broken:
        lines.append("**Could not check** (a failure with --strict): " +
                     ", ".join("%s (%s%s)" % (k, v, (": " + results[k]["why"]) if results[k].get("why") else "")
                               for k, v in sorted(broken.items())) + "\n")
    if unpublished:
        lines.append("Not published: " + ", ".join(unpublished) + "\n")
    if not checked:
        lines.append("**Nothing was checked**: no repository could be checked. This is an error, not a pass.\n")
    if needs:
        lines += ["<details><summary>Information: %d package(s) install on EL only with EPEL and CRB/PowerTools "
                  "enabled (the install docs must say so)</summary>" % len(needs), "",
                  "| Package | Repositories | Needs |", "|---|---|---|"]
        for p, v in sorted(needs.items()):
            lines.append("| %s | %s | %s |" % (p, ", ".join(v["repos"]), "; ".join(sorted(v["why"]))[:200]))
        lines += ["", "</details>", ""]
    return "\n".join(lines), new, broken


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, help="OBS project, e.g. isv:percona:ppg:staging:17")
    ap.add_argument("--major", default="")
    ap.add_argument("--repos", help="comma separated; default: repos.rpm + repos.deb from the config")
    ap.add_argument("--base-url", default="https://download.opensuse.org")
    ap.add_argument("--config", default=".github/package-deps-qa.yaml")
    ap.add_argument("--docker", default="docker", help="container engine (docker or podman)")
    ap.add_argument("--jobs", type=int, default=4, help="containers in parallel")
    ap.add_argument("--json", help="write the full result here")
    ap.add_argument("--summary", help="append the Markdown report here (e.g. $GITHUB_STEP_SUMMARY)")
    ap.add_argument("--strict", action="store_true", help="exit 1 on failures not in the allowlist")
    args = ap.parse_args(argv)
    major = args.major or (re.search(r":(1[0-9])(?::|$)", args.project) or [None, ""])[1]
    cfg = {}
    if Path(args.config).is_file() and yaml is not None:
        cfg = yaml.safe_load(Path(args.config).read_text()) or {}
    section = cfg.get("installable") or {}
    images = dict(DEFAULT_IMAGES, **(section.get("images") or {}))
    repos = (args.repos.split(",") if args.repos else
             list((cfg.get("repos") or {}).get("rpm") or []) + list((cfg.get("repos") or {}).get("deb") or []))
    unknown = [r for r in repos if r not in images]
    if unknown:
        ap.error("no container image for %s; add it under installable.images" % ", ".join(unknown))

    pulled = pull_images(args.docker, [images[r] for r in repos])
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {r: pool.submit(check_repo, r, repo_url(args.base_url, args.project, r), images[r], args.docker)
                   for r in repos if not pulled.get(images[r])}
        results = {r: f.result() for r, f in futures.items()}
    for r in repos:
        if pulled.get(images[r]):
            results[r] = empty_result("image-pull-failed", pulled[images[r]])
    md, new, broken = report_markdown(args.project, major, results, check_allowlist(section.get("allowed"), args.config))
    print(md)
    if args.summary:
        with open(args.summary, "a") as f:
            f.write(md + "\n")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2, sort_keys=True, default=sorted))
    if not any(r["status"] == "ok" for r in results.values()):
        return 2  # nothing checked is an error, in report-only mode too
    return 1 if (args.strict and (new or broken)) else 0


if __name__ == "__main__":
    sys.exit(main())
