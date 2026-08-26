"""Unit tests for ``_macros_changed_since`` (percona_obs.git_utils).

Reproduces the fallback storm after commit 146694c ("dedup common version
macros"): macros were moved between ``staging/17/extras/macros.yaml``,
``staging/17/macros.yaml`` and ``staging/macros.yaml`` with identical rendered
values, yet the file-level ``git diff --name-only`` reported "inherited macros
changed" for ~120 packages, sending them all through the service-running
content check.  The check must compare the *rendered values of the macros the
package actually references* between the synced SHA and the working tree.

Uses a real temporary git repository so the SHA-tree resolution is exercised
end to end (no mocking of git).
"""

import subprocess
from pathlib import Path

import pytest

import percona_obs.common as common
import percona_obs.git_utils as git_utils
from percona_obs.git_utils import _macros_changed_since

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(GIT + list(args), cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def repo(monkeypatch, tmp_path):
    """A git repo with the pre-dedup macros layout committed; returns (repo, sha, pkg)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "root/ppg/staging/macros.yaml", "- PG_TELEMETRY_VERSION: 1.0\n")
    _write(repo, "root/ppg/staging/17/macros.yaml", "- PG_MAJOR_VERSION: 17\n")
    _write(
        repo,
        "root/ppg/staging/17/extras/macros.yaml",
        "- PGAUDIT_VERSION: 17.1\n- PGVECTOR_VERSION: 0.8.0\n",
    )
    pkg = repo / "root/ppg/staging/17/extras/percona-pgaudit"
    _write(repo, f"{pkg.relative_to(repo)}/package.yaml", "name: percona-pgaudit\n")
    _write(repo, f"{pkg.relative_to(repo)}/obs/_service", "<services/>\n")
    _write(
        repo,
        f"{pkg.relative_to(repo)}/rpm/percona-pgaudit.spec",
        "Version: %!{PGAUDIT_VERSION}\n"
        "%define pgmajor %!{PG_MAJOR_VERSION}\n"
        "* %!{FILE_MODIFY_DATE} builder\n",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial")
    sha = _git(repo, "rev-parse", "--short", "HEAD")

    monkeypatch.setattr(git_utils, "_REPO_DIR", repo)
    monkeypatch.setattr(git_utils, "_REPO_ROOT", repo / "root")
    monkeypatch.setattr(common, "REPO_ROOT", repo / "root")
    return repo, sha, pkg


def _commit(repo: Path, msg: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def test_moving_macros_between_files_with_same_values_is_unchanged(repo):
    repo_dir, sha, pkg = repo
    # Hoist the extras macros into the shared staging file (commit 146694c).
    (repo_dir / "root/ppg/staging/17/extras/macros.yaml").unlink()
    _write(
        repo_dir,
        "root/ppg/staging/macros.yaml",
        "- PG_TELEMETRY_VERSION: 1.0\n- PGAUDIT_VERSION: 17.1\n- PGVECTOR_VERSION: 0.8.0\n",
    )
    _commit(repo_dir, "dedup macros")

    assert _macros_changed_since(sha, pkg) is False


def test_referenced_value_change_is_detected(repo):
    repo_dir, sha, pkg = repo
    _write(
        repo_dir,
        "root/ppg/staging/17/extras/macros.yaml",
        "- PGAUDIT_VERSION: 17.2\n- PGVECTOR_VERSION: 0.8.0\n",
    )
    _commit(repo_dir, "bump pgaudit")

    assert _macros_changed_since(sha, pkg) is True


def test_unreferenced_value_change_is_ignored(repo):
    repo_dir, sha, pkg = repo
    _write(
        repo_dir,
        "root/ppg/staging/17/extras/macros.yaml",
        "- PGAUDIT_VERSION: 17.1\n- PGVECTOR_VERSION: 0.8.1\n",
    )
    _commit(repo_dir, "bump pgvector")

    assert _macros_changed_since(sha, pkg) is False


def test_referenced_macro_removed_is_detected(repo):
    repo_dir, sha, pkg = repo
    _write(
        repo_dir,
        "root/ppg/staging/17/extras/macros.yaml",
        "- PGVECTOR_VERSION: 0.8.0\n",
    )
    _commit(repo_dir, "drop pgaudit macro")

    assert _macros_changed_since(sha, pkg) is True


def test_uncommitted_referenced_value_change_is_detected(repo):
    repo_dir, sha, pkg = repo
    _write(
        repo_dir,
        "root/ppg/staging/17/macros.yaml",
        "- PG_MAJOR_VERSION: 18\n",
    )
    # No commit: the upload is built from the working tree.

    assert _macros_changed_since(sha, pkg) is True


def test_unknown_sha_is_treated_as_changed(repo):
    _repo_dir, _sha, pkg = repo
    assert _macros_changed_since("0000000", pkg) is True


def test_package_without_macro_references_never_changes(repo):
    repo_dir, sha, pkg = repo
    (pkg / "rpm/percona-pgaudit.spec").write_text("Version: 1.0\n")
    _commit(repo_dir, "drop references")
    _write(repo_dir, "root/ppg/staging/17/macros.yaml", "- PG_MAJOR_VERSION: 18\n")
    _commit(repo_dir, "bump major")

    assert _macros_changed_since(sha, pkg) is False
