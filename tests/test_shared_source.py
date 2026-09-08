"""Shared package sources: ``_shared/`` directories and symlinked package dirs.

One copy of a package's packaging lives in ``root/<tier>/_shared/<pkg>/`` and
each per-major subproject holds a relative git symlink to it.  Discovery must
ignore ``_shared/`` itself, follow the symlink for content, and resolve macros
from the symlink's lexical location.  Git change detection must see edits to
the symlink target (git scopes ``diff``/``log``/``status`` to the link blob
otherwise).
"""

import os
import subprocess
from pathlib import Path

import pytest

import percona_obs.common as common
import percona_obs.git_utils as git_utils
from percona_obs.common import (
    SHARED_SOURCE_DIRNAME,
    find_packages,
    find_projects,
    is_shared_source_dir,
    load_macros,
)
from percona_obs.git_utils import (
    _has_non_obs_package_changes_since,
    _has_package_changes_since,
    _has_package_content_changes_since,
    _is_path_dirty,
    _macros_changed_since,
    _package_pathspecs,
)

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(GIT + list(args), cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _commit(repo: Path, msg: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


SHARED_PKG = f"root/ppg/staging/{SHARED_SOURCE_DIRNAME}/pkg"


@pytest.fixture
def tree(monkeypatch, tmp_path):
    """root/ppg/staging/{_shared/pkg, 14/pkg -> link, 17/pkg -> link} in a git repo.

    Returns (repo, sha) with the initial layout committed.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "root/ppg/staging/macros.yaml", "- PG_STAT_MONITOR_VERSION: 2.4.0\n")
    _write(repo, "root/ppg/staging/14/macros.yaml", "- PG_MAJOR_VERSION: 14\n")
    _write(repo, "root/ppg/staging/17/macros.yaml", "- PG_MAJOR_VERSION: 17\n")
    _write(repo, f"{SHARED_PKG}/obs/_service", "<services/>\n")
    _write(repo, f"{SHARED_PKG}/debian/pgversions", "%!{PG_MAJOR_VERSION}\n")
    _write(
        repo,
        f"{SHARED_PKG}/rpm/pkg.spec",
        "%global pgmajorversion %!{PG_MAJOR_VERSION}\n",
    )
    for v in ("14", "17"):
        os.symlink(
            f"../{SHARED_SOURCE_DIRNAME}/pkg", repo / f"root/ppg/staging/{v}/pkg"
        )
    # An ordinary (non-shared) package so discovery still finds real dirs.
    _write(repo, "root/ppg/staging/17/plain/obs/_service", "<services/>\n")
    _commit(repo, "initial")
    sha = _git(repo, "rev-parse", "--short", "HEAD")

    monkeypatch.setattr(common, "REPO_ROOT", repo / "root")
    monkeypatch.setattr(git_utils, "_REPO_DIR", repo)
    monkeypatch.setattr(git_utils, "_REPO_ROOT", repo / "root")
    return repo, sha


# --- discovery ---------------------------------------------------------------


def test_discovery_is_shared_source_dir(tree):
    repo, _ = tree
    assert is_shared_source_dir(repo / "root/ppg/staging" / SHARED_SOURCE_DIRNAME)
    assert not is_shared_source_dir(repo / "root/ppg/staging/17")


def test_discovery_find_packages_skips_shared_and_follows_links(tree):
    repo, _ = tree
    found = list(find_packages(repo / "root/ppg/staging", "X:ppg:staging"))
    projects = {p for p, _ in found}
    assert not any(SHARED_SOURCE_DIRNAME in p for p in projects)
    assert ("X:ppg:staging:14", repo / "root/ppg/staging/14/pkg") in found
    assert ("X:ppg:staging:17", repo / "root/ppg/staging/17/pkg") in found
    assert ("X:ppg:staging:17", repo / "root/ppg/staging/17/plain") in found
    assert not any(SHARED_SOURCE_DIRNAME in path.parts for _, path in found)


def test_discovery_find_projects_skips_shared(tree):
    repo, _ = tree
    names = [
        name for name, _ in find_projects(repo / "root/ppg/staging", "X:ppg:staging")
    ]
    assert "X:ppg:staging:14" in names
    assert "X:ppg:staging:17" in names
    assert not any(SHARED_SOURCE_DIRNAME in n for n in names)


def test_discovery_symlinked_package_resolves_macros_lexically(tree):
    repo, _ = tree
    assert load_macros(repo / "root/ppg/staging/14/pkg")["PG_MAJOR_VERSION"] == "14"
    assert load_macros(repo / "root/ppg/staging/17/pkg")["PG_MAJOR_VERSION"] == "17"
    # Content is reachable through the link.
    assert (repo / "root/ppg/staging/17/pkg/debian/pgversions").is_file()


# --- git change detection ----------------------------------------------------


def test_git_pathspecs_plain_dir(tree):
    repo, _ = tree
    plain = repo / "root/ppg/staging/17/plain"
    assert _package_pathspecs(plain) == [plain]


def test_git_pathspecs_symlink_adds_lexical_target(tree):
    repo, _ = tree
    link = repo / "root/ppg/staging/17/pkg"
    assert _package_pathspecs(link) == [
        link,
        repo / "root/ppg/staging" / SHARED_SOURCE_DIRNAME / "pkg",
    ]


def test_git_no_change_all_false(tree):
    repo, sha = tree
    link = repo / "root/ppg/staging/17/pkg"
    assert _has_package_changes_since(sha, link) is False
    assert _has_package_content_changes_since(sha, link) is False
    assert _has_non_obs_package_changes_since(sha, link) is False
    assert _is_path_dirty(link) is False


def test_git_committed_shared_debian_edit_is_seen_via_link(tree):
    repo, sha = tree
    _write(repo, f"{SHARED_PKG}/debian/pgversions", "%!{PG_MAJOR_VERSION}\n# bump\n")
    _commit(repo, "edit shared debian")
    link = repo / "root/ppg/staging/17/pkg"
    assert _has_package_changes_since(sha, link) is True
    assert _has_package_content_changes_since(sha, link) is True
    assert _has_non_obs_package_changes_since(sha, link) is True


def test_git_committed_shared_obs_only_edit_is_obs_only(tree):
    repo, sha = tree
    _write(repo, f"{SHARED_PKG}/obs/_service", "<services>\n</services>\n")
    _commit(repo, "edit shared obs")
    link = repo / "root/ppg/staging/17/pkg"
    assert _has_package_changes_since(sha, link) is True
    assert _has_non_obs_package_changes_since(sha, link) is False


def test_git_dirty_shared_edit_is_seen_via_link(tree):
    repo, _ = tree
    _write(
        repo,
        f"{SHARED_PKG}/rpm/pkg.spec",
        "%global pgmajorversion %!{PG_MAJOR_VERSION}\n# dirty\n",
    )
    assert _is_path_dirty(repo / "root/ppg/staging/17/pkg") is True
    assert _is_path_dirty(repo / "root/ppg/staging/17/plain") is False


def test_git_macros_changed_since_is_per_subproject(tree):
    repo, sha = tree
    # A macro the package never references: not a change.
    _write(
        repo,
        "root/ppg/staging/17/macros.yaml",
        "- PG_MAJOR_VERSION: 17\n- PG_STAT_MONITOR_VERSION: 2.5.0\n",
    )
    _commit(repo, "bump unreferenced macro on 17")
    assert _macros_changed_since(sha, repo / "root/ppg/staging/17/pkg") is False
    # The referenced macro changes on 17 only.
    _write(repo, "root/ppg/staging/17/macros.yaml", "- PG_MAJOR_VERSION: 170\n")
    _commit(repo, "change referenced macro on 17")
    assert _macros_changed_since(sha, repo / "root/ppg/staging/17/pkg") is True
    assert _macros_changed_since(sha, repo / "root/ppg/staging/14/pkg") is False
