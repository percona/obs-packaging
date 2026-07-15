"""Unit tests for the --branch-from package-meta flag check (percona_obs.cmd_sync).

Reproduces the llvm-21 / Debian_12 miss: a package.yaml change that only flips
per-repo ``build:`` flags produces no source-file diff, so the content check
reported "content matches" and the package was aggregated from the branch
project — whose package has the repo build-disabled and therefore provides no
binaries for it.  The branch decision must also compare the build/publish
flags derived from the local package.yaml against the branch package's meta
and promote when they differ.
"""

import percona_obs.cmd_sync as cmd_sync
from percona_obs.cmd_sync import _package_meta_flags_match, _resolve_branch_decision


def _meta(flags: str = "", title: str = "LLVM 21 toolchain") -> bytes:
    return (
        f'<package name="llvm-21" project="prod:common:deps:build">\n'
        f"  <title>{title}</title>\n"
        f"  <description>desc</description>\n"
        f"{flags}"
        f"</package>\n"
    ).encode()


DISABLE_D12_D13 = (
    "  <build>\n"
    '    <disable repository="Debian_12"/>\n'
    '    <disable repository="Debian_13"/>\n'
    "  </build>\n"
)
DISABLE_D13 = '  <build>\n    <disable repository="Debian_13"/>\n  </build>\n'


# --- _package_meta_flags_match ------------------------------------------------


def test_match_when_flags_identical():
    config = {"build": {"Debian_12": False, "Debian_13": False}}
    assert _package_meta_flags_match(_meta(DISABLE_D12_D13), config)


def test_mismatch_when_repo_enable_flipped():
    # The llvm-21 scenario: local package.yaml no longer disables Debian_12,
    # but the branch package meta still does.
    config = {"build": {"Debian_13": False}}
    assert not _package_meta_flags_match(_meta(DISABLE_D12_D13), config)


def test_mismatch_when_repo_disabled_locally():
    # Reverse direction: local disables a repo the branch has enabled.
    config = {"build": {"Debian_12": False, "Debian_13": False}}
    assert not _package_meta_flags_match(_meta(DISABLE_D13), config)


def test_title_only_change_still_matches():
    # Title/description changes do not affect binaries and must not force
    # a promotion.
    config = {"build": {"Debian_13": False}}
    assert _package_meta_flags_match(_meta(DISABLE_D13, title="new title"), config)


def test_match_when_no_flags_anywhere():
    assert _package_meta_flags_match(_meta(), {})


def test_mismatch_on_publish_flags():
    config = {"publish": {"Debian_13": False}}
    assert not _package_meta_flags_match(_meta(), config)


def test_mismatch_on_unparseable_meta():
    assert not _package_meta_flags_match(b"not xml <<", {})


# --- _resolve_branch_decision wiring -------------------------------------------


def _make_package(tmp_path, build_yaml: str):
    pkg = tmp_path / "llvm-21"
    (pkg / "obs").mkdir(parents=True)
    (pkg / "package.yaml").write_text(
        "title: t\ndescription: d\n" + build_yaml, encoding="utf-8"
    )
    return pkg


def test_decision_promotes_on_meta_only_change(monkeypatch, tmp_path):
    # Content matches the branch, but the local package.yaml enables
    # Debian_12 while the branch package meta still disables it → promote.
    pkg = _make_package(tmp_path, "build:\n  Debian_13: false\n")
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_package_meaningful_comment", lambda *a: None
    )
    monkeypatch.setattr(cmd_sync, "_content_matches_branch", lambda *a, **k: True)
    monkeypatch.setattr(
        cmd_sync,
        "_fetch_obs_package_meta_bytes",
        lambda *a: _meta(DISABLE_D12_D13),
    )
    assert (
        _resolve_branch_decision("http://obs", "prod:common:deps:build", "llvm-21", pkg)
        is False
    )


def test_decision_aggregates_when_meta_flags_match(monkeypatch, tmp_path):
    pkg = _make_package(tmp_path, "build:\n  Debian_13: false\n")
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_package_meaningful_comment", lambda *a: None
    )
    monkeypatch.setattr(cmd_sync, "_content_matches_branch", lambda *a, **k: True)
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_package_meta_bytes", lambda *a: _meta(DISABLE_D13)
    )
    assert (
        _resolve_branch_decision("http://obs", "prod:common:deps:build", "llvm-21", pkg)
        is True
    )


def test_decision_promotes_when_branch_meta_unavailable(monkeypatch, tmp_path):
    # If the branch package meta cannot be fetched the flags cannot be
    # verified — promote (build from source) is the safe direction.
    pkg = _make_package(tmp_path, "")
    monkeypatch.setattr(
        cmd_sync, "_fetch_obs_package_meaningful_comment", lambda *a: None
    )
    monkeypatch.setattr(cmd_sync, "_content_matches_branch", lambda *a, **k: True)
    monkeypatch.setattr(cmd_sync, "_fetch_obs_package_meta_bytes", lambda *a: None)
    assert (
        _resolve_branch_decision("http://obs", "prod:common:deps:build", "llvm-21", pkg)
        is False
    )
