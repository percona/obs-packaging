#!/usr/bin/env python3
"""Find percona-distribution-postgresql container images in an OBS PR project.

Traverses all subprojects of OBS_PR_PROJECT, finds any that have an 'images'
repository, then checks each package for a Dockerfile or .kiwi file with a
BuildTag matching percona-distribution-postgresql*.

Required environment variables:
  OBS_APIURL        OBS API URL
  OBS_PR_PROJECT    PR root project (e.g. isv:percona:PR:pr-42)
  GITHUB_OUTPUT     Path to write GitHub Actions step outputs
"""

import os
import re
import sys

import osc.conf

from percona_obs.obs_api import (
    _detect_obs_container_info,
    _fetch_obs_package_names,
    _fetch_obs_project_repository_names,
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
    repos = _fetch_obs_project_repository_names(apiurl, project)
    if "images" not in repos:
        continue
    print(f"  {project!r} has 'images' repository — scanning packages", flush=True)
    packages = _fetch_obs_package_names(apiurl, project)

    base_tag: str | None = None
    has_postgis = False

    for pkg in sorted(packages):
        info = _detect_obs_container_info(apiurl, project, pkg)
        if info is None:
            continue
        image_name, tag = info
        if not image_name or "percona-distribution-postgresql" not in image_name:
            continue
        print(f"    Found container image: {image_name}:{tag}", flush=True)
        if base_tag is None:
            base_tag = tag
        if "postgis" in image_name.lower():
            has_postgis = True

    if base_tag is None:
        continue

    registry_path = project.lower().replace(":", "/")
    registry_url = f"registry.opensuse.org/{registry_path}/images"
    docker_tag = ""
    m = re.search(r"(\d+\.\d+)", base_tag)
    if m:
        docker_tag = m.group(1)

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
