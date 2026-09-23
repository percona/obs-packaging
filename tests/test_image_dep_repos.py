"""Unit tests for image_dep_query_repos (percona_obs.targets).

Reproduces the percona/obs-packaging PR #4 bug: after the containers
restructure, the single ":containers" subproject names its built-image
repos after the flavor (e.g. "ubi8"/"ubi9") instead of the old layout's
literal "images" repo.  The dep-cascade _buildinfo queries hardcoded
"images", so for new-layout projects they 404ed, no Dockerfile-image → RPM
edges were found, and container images were never dep-promoted when a
package they install (percona-pg_tde) was promoted.

Repository selection comes from the process-default RepositoryFilter (the
active profile's slice).
"""

from pathlib import Path

import percona_obs.common as common
from percona_obs.project_config import RepositoryFilter
from percona_obs.targets import image_dep_query_repos

NEW_LAYOUT_YAML = """\
name: isv:percona:ppg:staging:18:containers
repositories:
  - name: ubi8
    archs: [x86_64, aarch64]
  - name: ubi9
    archs: [x86_64, aarch64]
"""

OLD_LAYOUT_YAML = """\
name: isv:percona:ppg:staging:17:containers:ubi9
repositories:
  - name: images
    archs: [x86_64, aarch64]
"""


def _make_image_pkg(tmp_path: Path, project_yaml: str) -> Path:
    project = tmp_path / "containers"
    obs_dir = project / "percona-distribution-postgresql" / "obs"
    obs_dir.mkdir(parents=True)
    (obs_dir / "Dockerfile").write_text("FROM scratch\n")
    (project / "project.yaml").write_text(project_yaml)
    return obs_dir.parent


def test_new_layout_all_repos(tmp_path):
    pkg = _make_image_pkg(tmp_path, NEW_LAYOUT_YAML)
    assert image_dep_query_repos(pkg) == {"ubi8", "ubi9"}


def test_default_filter_slices_image_repos(tmp_path):
    pkg = _make_image_pkg(tmp_path, NEW_LAYOUT_YAML)
    common.set_default_repository_filter(RepositoryFilter(include_repos=("ubi9",)))
    try:
        assert image_dep_query_repos(pkg) == {"ubi9"}
        common.set_default_repository_filter(RepositoryFilter(include_repos=("UBI_8",)))
        assert image_dep_query_repos(pkg) == set()
    finally:
        common.set_default_repository_filter(None)


def test_cache_is_populated_and_reused(tmp_path):
    pkg = _make_image_pkg(tmp_path, NEW_LAYOUT_YAML)
    cache: dict[Path, set[str]] = {}
    assert image_dep_query_repos(pkg, cache=cache) == {"ubi8", "ubi9"}
    assert cache == {pkg.parent: {"ubi8", "ubi9"}}
    # A warm cache is authoritative: the loader must not run again.
    cache[pkg.parent] = {"sentinel"}
    assert image_dep_query_repos(pkg, cache=cache) == {"sentinel"}
