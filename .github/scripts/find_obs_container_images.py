#!/usr/bin/env python3
"""Find percona-distribution-postgresql container images in an OBS PR project.

Traverses all subprojects of OBS_PR_PROJECT, finds any that have an 'images'
repository, then checks each package for a .containerinfo build artifact with
a tag matching percona-distribution-postgresql*.

Required environment variables:
  OBS_APIURL        OBS API URL
  OBS_PR_PROJECT    PR root project (e.g. isv:percona:PR:pr-42)
  GITHUB_OUTPUT     Path to write GitHub Actions step outputs
"""

import os
import sys

import osc.conf

from percona_obs.obs_api import (
    _fetch_all_pkg_archs,
    _fetch_build_containerinfo,
    _fetch_obs_package_names,
    _fetch_obs_subproject_names,
)

apiurl = os.environ["OBS_APIURL"]
pr_project = os.environ["OBS_PR_PROJECT"]
github_output = os.environ.get("GITHUB_OUTPUT", "")

osc.conf.get_config(override_apiurl=apiurl)

subprojects = _fetch_obs_subproject_names(apiurl, pr_project)
print(f"Found {len(subprojects)} subproject(s) under {pr_project!r}", flush=True)


def _write_output(**kwargs: str) -> None:
    if not github_output:
        return
    with open(github_output, "a") as fh:
        for key, value in kwargs.items():
            fh.write(f"{key}={value}\n")


for project in sorted(subprojects):
    packages = _fetch_obs_package_names(apiurl, project)
    if not packages:
        continue
    print(f"  Scanning {len(packages)} package(s) in {project!r}", flush=True)
    pkg_archs = _fetch_all_pkg_archs(apiurl, project)

    container_version: str | None = None
    base_tag: str | None = None
    has_postgis = False

    for pkg in sorted(packages):
        repo_arch = pkg_archs.get(pkg)
        if not repo_arch:
            continue
        repo, arch = repo_arch
        ci = _fetch_build_containerinfo(apiurl, project, repo, arch, pkg)
        if ci is None:
            continue
        tags_list: list[str] = ci.get("tags") or []
        if not any("percona-distribution-postgresql" in t for t in tags_list):
            continue

        print(f"    Found container image tags: {tags_list}", flush=True)

        if container_version is None:
            container_version = ci.get("version") or ""
            # Pick the most specific tag (longest, e.g. "18.3-1") as base_tag.
            for full_tag in tags_list:
                if "percona-distribution-postgresql" not in full_tag:
                    continue
                tag_part = full_tag.rsplit(":", 1)[1] if ":" in full_tag else full_tag
                if base_tag is None or len(tag_part) > len(base_tag):
                    base_tag = tag_part

        if "postgis" in pkg.lower() or any("postgis" in t.lower() for t in tags_list):
            has_postgis = True

    if base_tag is None:
        continue

    registry_path = project.lower().replace(":", "/")
    registry_url = f"registry.opensuse.org/{registry_path}/images"
    docker_tag = container_version or base_tag

    _write_output(
        has_images="true",
        has_postgis_images="true" if has_postgis else "false",
        container_project=project,
        registry_url=registry_url,
        docker_tag=docker_tag,
        server_version=docker_tag,
    )
    sys.exit(0)

print("No percona-distribution-postgresql container images found in PR project")
_write_output(has_images="false")
sys.exit(0)
