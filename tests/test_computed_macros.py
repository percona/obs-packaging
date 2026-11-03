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


def test_prev_major_is_computed_from_major():
    macros = inject_computed_macros(
        {"PG_MAJOR_VERSION": "18"}, Path("/nowhere"), lambda _p: None
    )
    assert macros["PG_PREV_MAJOR_VERSION"] == "17"


def test_prev_major_explicit_declaration_wins():
    macros = inject_computed_macros(
        {"PG_MAJOR_VERSION": "18", "PG_PREV_MAJOR_VERSION": "16"},
        Path("/nowhere"),
        lambda _p: None,
    )
    assert macros["PG_PREV_MAJOR_VERSION"] == "16"


def test_prev_major_absent_without_a_numeric_major():
    assert "PG_PREV_MAJOR_VERSION" not in inject_computed_macros(
        {}, Path("/nowhere"), lambda _p: None
    )
    assert "PG_PREV_MAJOR_VERSION" not in inject_computed_macros(
        {"PG_MAJOR_VERSION": "%!{X}"}, Path("/nowhere"), lambda _p: None
    )


def test_load_macros_injects_prev_major(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    assert common.load_macros(root / "ppg/staging/18")["PG_PREV_MAJOR_VERSION"] == "17"


MAPPING_RELEASE_YAML = """\
project: ppg:staging:18
releases:
- ppg/18.3-1
- tag: ppg/18.4-1
  source_commit: 9e9d9738c0ffee
"""


def test_compute_counts_mapping_entries():
    assert compute_ppg_release("ppg", "18.4", MAPPING_RELEASE_YAML) == "2"
    assert compute_ppg_release("ppg", "18.3", MAPPING_RELEASE_YAML) == "2"


def test_compute_tolerates_garbage_entries():
    assert compute_ppg_release("ppg", "18.4", "releases: [{x: 1}]\n") == "1"


import percona_obs.pkg_version as pkg_version

SERVICE = """<services>
  <service name="obs_scm">
    <param name="url">https://github.com/pgaudit/pgaudit.git</param>
    <param name="revision">%!{PGAUDIT_VERSION}</param>
    <param name="version">%!{PGAUDIT_VERSION}</param>
    <param name="filename">percona-pgaudit</param>
  </service>
</services>
"""


def _pkg_tree(
    tmp_path: Path, version_line: str = "- PGAUDIT_VERSION: 17.1\n"
) -> tuple[Path, Path]:
    root = tmp_path / "root"
    proj = root / "ppg" / "staging" / "17"
    pkg = proj / "percona-pgaudit"
    (pkg / "obs").mkdir(parents=True)
    (proj / "macros.yaml").write_text(version_line)
    (pkg / "obs" / "_service").write_text(SERVICE)
    return root, pkg


def _read(p: Path):
    return common._read_worktree_file(p)


def test_pkg_revision_injected_from_seed(tmp_path, monkeypatch):
    root, pkg = _pkg_tree(tmp_path)
    monkeypatch.setitem(
        pkg_version.PKG_REVISION_FLOORS,
        ("ppg:staging:17", "percona-pgaudit", "17.1"),
        4,
    )
    out = inject_computed_macros(
        {"PGAUDIT_VERSION": "17.1"}, pkg, _read, repo_root=root
    )
    assert out["PKG_REVISION"] == "5"


def test_pkg_revision_resets_on_upstream_bump(tmp_path):
    root, pkg = _pkg_tree(tmp_path, "- PGAUDIT_VERSION: 17.2\n")
    out = inject_computed_macros(
        {"PGAUDIT_VERSION": "17.2"}, pkg, _read, repo_root=root
    )
    assert out["PKG_REVISION"] == "1"


def test_pkg_revision_without_pg_version_in_chain(tmp_path):
    # ppg:common:deps has no PG_VERSION; PKG_REVISION must still appear.
    root = tmp_path / "root"
    pkg = root / "ppg" / "common" / "deps" / "ydiff"
    (pkg / "obs").mkdir(parents=True)
    (pkg / "obs" / "_service").write_text(
        '<services><service name="obs_scm"><param name="version">1.4.2</param>'
        '<param name="filename">ydiff</param></service></services>'
    )
    out = inject_computed_macros({}, pkg, _read, repo_root=root)
    assert out["PKG_REVISION"] == str(
        pkg_version.PKG_REVISION_FLOORS[("ppg:common:deps", "ydiff", "1.4.2")] + 1
    )
    assert "PPG_RELEASE" not in out


def test_pkg_revision_not_injected_without_service(tmp_path):
    root = tmp_path / "root"
    pkg = root / "ppg" / "staging" / "17" / "percona-postgresql-tarball"
    (pkg / "obs").mkdir(parents=True)
    (pkg / "obs" / "_aggregate").write_text("<aggregatelist/>")
    out = inject_computed_macros({"PG_VERSION": "17.11"}, pkg, _read, repo_root=root)
    assert "PKG_REVISION" not in out


def test_pkg_revision_not_injected_for_project_path(tmp_path):
    root, pkg = _pkg_tree(tmp_path)
    out = inject_computed_macros(
        {"PGAUDIT_VERSION": "17.1"}, pkg.parent, _read, repo_root=root
    )
    assert "PKG_REVISION" not in out


def test_pkg_revision_not_injected_when_version_unresolved_and_no_source_files(
    tmp_path,
):
    root, pkg = _pkg_tree(tmp_path)
    # PGAUDIT_VERSION missing from the chain: V renders to "%!{PGAUDIT_VERSION}".
    out = inject_computed_macros({}, pkg, _read, repo_root=root)
    assert "PKG_REVISION" not in out
    (pkg / "obs" / "_service").write_text(
        SERVICE.replace("%!{PGAUDIT_VERSION}", "${PGAUDIT_REF}")
    )
    out = inject_computed_macros({}, pkg, _read, repo_root=root)
    assert "PKG_REVISION" not in out


def test_declared_pkg_revision_wins(tmp_path):
    root, pkg = _pkg_tree(tmp_path)
    out = inject_computed_macros(
        {"PGAUDIT_VERSION": "17.1", "PKG_REVISION": "42"}, pkg, _read, repo_root=root
    )
    assert out["PKG_REVISION"] == "42"


def test_pkg_revision_computed_identically_from_git_reader(tmp_path):
    # The git side passes a reader over "git show"; the same text must give the
    # same value.  Simulate with a dict-backed reader.
    root, pkg = _pkg_tree(tmp_path)
    blobs = {pkg / "obs" / "_service": SERVICE}
    out = inject_computed_macros(
        {"PGAUDIT_VERSION": "17.1"}, pkg, lambda p: blobs.get(p), repo_root=root
    )
    assert (
        out["PKG_REVISION"]
        == inject_computed_macros(
            {"PGAUDIT_VERSION": "17.1"}, pkg, _read, repo_root=root
        )["PKG_REVISION"]
    )


def test_pkg_revision_is_one_for_source_package_without_version(tmp_path):
    root, pkg = _pkg_tree(tmp_path)
    (pkg / "rpm").mkdir()
    (pkg / "rpm" / "x.spec").write_text(
        "Name: x\nVersion: 1.1.10\nRelease: %!{PKG_REVISION}%{?dist}\n"
    )
    # download_url-only _service: no version derivable
    (pkg / "obs" / "_service").write_text(
        '<services><service name="download_url"><param name="url">https://x/y-1.1.10.tar.gz</param></service></services>'
    )
    assert inject_computed_macros({}, pkg, _read, repo_root=root)["PKG_REVISION"] == "1"


def test_pkg_revision_is_one_for_package_without_service_but_with_dsc(tmp_path):
    root = tmp_path / "root"
    pkg = root / "ppg" / "staging" / "17" / "percona-ppg-server"
    (pkg / "debian").mkdir(parents=True)
    (pkg / "debian" / "debian.dsc").write_text(
        "Version: 1:%!{PG_VERSION}-%!{PKG_REVISION}\n"
    )
    out = inject_computed_macros({"PG_VERSION": "17.12"}, pkg, _read, repo_root=root)
    assert out["PKG_REVISION"] == "1"


def test_every_seed_package_still_derives_a_version():
    # A seeded package that stopped deriving a version would silently render 1
    # and lose to production.  A dead seed (the package moved to another
    # upstream version) is expected, not an error, so only "derives" is checked.
    from percona_obs.common import REPO_ROOT, apply_macro_substitution, load_macros
    from percona_obs.pkg_version import (
        PKG_REVISION_FLOORS,
        extract_version_from_service_text,
    )

    for project, package, _seed in PKG_REVISION_FLOORS:
        pkg = REPO_ROOT.joinpath(*project.split(":")) / package
        service = pkg / "obs" / "_service"
        assert service.is_file(), (project, package)
        chain = {k: v for k, v in load_macros(pkg).items() if k != "PKG_REVISION"}
        rendered = apply_macro_substitution(
            service.read_text("utf-8"), chain, strict=False
        )
        derived = extract_version_from_service_text(rendered)
        assert derived and "%!{" not in derived and "${" not in derived, (
            project,
            package,
            derived,
        )
