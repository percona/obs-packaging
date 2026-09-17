"""Unit tests for tool-computed macros (percona_obs.common)."""

from pathlib import Path

import percona_obs.common as common
import percona_obs.git_utils as git_utils
from percona_obs.common import compute_ppg_release, inject_computed_macros

RELEASE_YAML = """\
project: ppg:staging:18
releases:
- ppg/18.3-1
- ppg/18.3-2
- ppg/18.4-1
repository: ${PERCONA_OBS_PACKAGING_REPO}
"""


def test_compute_counts_only_matching_pg_version():
    assert compute_ppg_release("ppg", "18.3", RELEASE_YAML) == "3"
    assert compute_ppg_release("ppg", "18.4", RELEASE_YAML) == "2"


def test_compute_resets_to_one_for_unreleased_version():
    # This is the forgot-to-reset case: bumping PG_MINOR_VERSION to 18.5 makes
    # the counter 1 with no human action.
    assert compute_ppg_release("ppg", "18.5", RELEASE_YAML) == "1"


def test_compute_tolerates_missing_and_broken_input():
    assert compute_ppg_release("ppg", "18.4", None) == "1"
    assert compute_ppg_release("ppg", "18.4", "") == "1"
    assert compute_ppg_release("ppg", "18.4", "{{{ not yaml") == "1"
    assert compute_ppg_release("ppg", "18.4", "project: x\n") == "1"


def test_compute_honours_legacy_revision_field():
    assert compute_ppg_release("ppg", "18.4", "revision: ppg/18.4-1\n") == "2"


def test_compute_does_not_match_other_products_or_prefixes():
    data = "releases:\n- psmdb/18.4-1\n- ppg/118.4-1\n"
    assert compute_ppg_release("ppg", "18.4", data) == "1"


def _tree(tmp_path: Path) -> Path:
    """staging/18 project plus a releases/18/release.yaml."""
    root = tmp_path / "root"
    proj = root / "ppg" / "staging" / "18"
    proj.mkdir(parents=True)
    (root / "ppg" / "staging" / "macros.yaml").write_text("- PG_MAJOR_VERSION: 0\n")
    (proj / "macros.yaml").write_text(
        "- PG_MAJOR_VERSION: 18\n- PG_MINOR_VERSION: 4\n"
        "- PG_VERSION: %!{PG_MAJOR_VERSION}.%!{PG_MINOR_VERSION}\n"
    )
    rel = root / "ppg" / "releases" / "18"
    rel.mkdir(parents=True)
    (rel / "release.yaml").write_text(RELEASE_YAML)
    return root


def test_load_macros_injects_computed_value(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    macros = common.load_macros(root / "ppg" / "staging" / "18")
    assert macros["PG_VERSION"] == "18.4"
    assert macros["PPG_RELEASE"] == "2"


def test_load_macros_resets_on_minor_bump(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    proj = root / "ppg" / "staging" / "18"
    (proj / "macros.yaml").write_text(
        "- PG_MAJOR_VERSION: 18\n- PG_MINOR_VERSION: 5\n"
        "- PG_VERSION: %!{PG_MAJOR_VERSION}.%!{PG_MINOR_VERSION}\n"
    )
    assert common.load_macros(proj)["PPG_RELEASE"] == "1"


def test_load_macros_without_pg_version_has_no_counter(tmp_path, monkeypatch):
    root = tmp_path / "root"
    proj = root / "ppg" / "common" / "deps"
    proj.mkdir(parents=True)
    (proj / "macros.yaml").write_text("- GEOS_VERSION: 3.13.1\n")
    monkeypatch.setattr(common, "REPO_ROOT", root)
    assert "PPG_RELEASE" not in common.load_macros(proj)


def test_explicit_declaration_wins(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    proj = root / "ppg" / "staging" / "18"
    (proj / "macros.yaml").write_text(
        (proj / "macros.yaml").read_text() + "- PPG_RELEASE: 9\n"
    )
    assert common.load_macros(proj)["PPG_RELEASE"] == "9"


def test_inject_is_pure_in_its_reader():
    macros = {"PG_VERSION": "18.4"}
    out = inject_computed_macros(
        macros,
        Path("/repo/root/ppg/staging/18"),
        lambda p: RELEASE_YAML,
        repo_root=Path("/repo/root"),
    )
    assert out["PPG_RELEASE"] == "2"
    assert "PPG_RELEASE" not in macros  # input dict not mutated


def _macros_check_fixture(monkeypatch, tmp_path, then_release: str, now_release: str):
    """Wire _macros_changed_since onto a fixture tree with fake git reads."""
    root = _tree(tmp_path)
    (root / "ppg" / "releases" / "18" / "release.yaml").write_text(now_release)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(git_utils, "_REPO_DIR", root.parent)
    monkeypatch.setattr(git_utils, "_commit_exists", lambda sha: True)
    monkeypatch.setattr(
        git_utils, "_referenced_macros", lambda p: {"PG_VERSION", "PPG_RELEASE"}
    )

    def _show(sha: str, rel_path: str) -> "str | None":
        if rel_path.endswith("releases/18/release.yaml"):
            return then_release
        blob = root.parent / rel_path
        return blob.read_text("utf-8") if blob.exists() else None

    monkeypatch.setattr(git_utils, "_git_show_at", _show)
    return root / "ppg" / "staging" / "18"


def test_macros_unchanged_when_release_state_identical(monkeypatch, tmp_path):
    pkg = _macros_check_fixture(monkeypatch, tmp_path, RELEASE_YAML, RELEASE_YAML)
    assert git_utils._macros_changed_since("abc1234", pkg) is False


def test_macros_changed_when_release_added(monkeypatch, tmp_path):
    after = RELEASE_YAML + "- ppg/18.4-2\n"
    pkg = _macros_check_fixture(monkeypatch, tmp_path, RELEASE_YAML, after)
    assert git_utils._macros_changed_since("abc1234", pkg) is True
