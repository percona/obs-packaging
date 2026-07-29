"""Unit tests for image_dep_query_repos (percona_obs.targets).

Reproduces the percona/obs-packaging PR #4 bug: after the containers
restructure, the single ":containers" subproject names its built-image
repos after the flavor (e.g. "ubi8"/"ubi9") instead of the old layout's
literal "images" repo.  The dep-cascade _buildinfo queries hardcoded
"images", so for new-layout projects they 404ed, no Dockerfile-image → RPM
edges were found, and container images were never dep-promoted when a
package they install (percona-pg_tde) was promoted.
"""

from pathlib import Path

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

# What --only-repos ubi9-images,UBI_9 expands to (old + new layout candidates).
UBI9_ONLY_REPOS = {"images", "ubi9", "UBI_9"}


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


def test_new_layout_only_repos_filter(tmp_path):
    pkg = _make_image_pkg(tmp_path, NEW_LAYOUT_YAML)
    assert image_dep_query_repos(pkg, only_repos=UBI9_ONLY_REPOS) == {"ubi9"}


def test_old_layout_only_repos_filter(tmp_path):
    pkg = _make_image_pkg(tmp_path, OLD_LAYOUT_YAML)
    assert image_dep_query_repos(pkg, only_repos=UBI9_ONLY_REPOS) == {"images"}


def test_filter_excluding_all_repos(tmp_path):
    pkg = _make_image_pkg(tmp_path, NEW_LAYOUT_YAML)
    assert image_dep_query_repos(pkg, only_repos={"UBI_8"}) == set()


def test_cache_is_populated_and_reused(tmp_path):
    pkg = _make_image_pkg(tmp_path, NEW_LAYOUT_YAML)
    cache: dict[Path, set[str]] = {}
    assert image_dep_query_repos(pkg, cache=cache) == {"ubi8", "ubi9"}
    assert cache == {pkg.parent: {"ubi8", "ubi9"}}
    # A warm cache is authoritative: the loader must not run again.
    cache[pkg.parent] = {"sentinel"}
    assert image_dep_query_repos(pkg, cache=cache) == {"sentinel"}
