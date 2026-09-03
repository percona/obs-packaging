"""Unit tests for percona_obs.cve_scan (best-effort CVE scanner)."""

import json

import percona_obs.cmd_project as cmd_project
from percona_obs.cve_scan import (
    ChangedPackage,
    _derive_tag_template,
    _loose_version_key,
    scan_go_toolchain,
    scan_release_cves,
)


def _fetcher_from_map(url_to_body: "dict[str, str]"):
    def _fetcher(url: str, headers: "dict[str, str] | None" = None) -> str:
        for prefix, body in url_to_body.items():
            if url.startswith(prefix):
                return body
        raise AssertionError(f"unexpected fetch: {url}")

    return _fetcher


# --- 1. _derive_tag_template ---------------------------------------------


def test_derive_tag_template_dot_sep():
    assert _derive_tag_template("v4.1.5", "4.1.5") == "v{v}"


def test_derive_tag_template_path_prefix():
    assert _derive_tag_template("release/2.59.0", "2.59.0") == "release/{v}"


def test_derive_tag_template_underscore_sep():
    assert _derive_tag_template("V4_7_2", "4.7.2") == "V{v}"


def test_derive_tag_template_rel_underscore():
    assert _derive_tag_template("REL_17_11", "17.11") == "REL_{v}"


def test_derive_tag_template_pg_similarity():
    # version "1.0" -> underscore-rewritten "1_0" is a substring of the tag.
    assert _derive_tag_template("pg_similarity_1_0", "1.0") == "pg_similarity_{v}"


def test_derive_tag_template_unmatched():
    assert _derive_tag_template("totally-unrelated", "9.9.9") is None


# --- 2. _loose_version_key ordering --------------------------------------


def test_loose_version_key_ordering():
    assert _loose_version_key("3.5.30") < _loose_version_key("3.5.33")
    assert _loose_version_key("2.8.9") < _loose_version_key("2.8.27")


# --- 3. GitHub path --------------------------------------------------------


def test_scan_github_dedupes_and_excludes_out_of_range(tmp_path):
    pkg = ChangedPackage(
        key="percona-patroni",
        old_version="4.1.3",
        new_version="4.1.5",
        upstream_url="https://github.com/patroni/patroni.git",
        revision="v4.1.5",
    )
    compare_body = json.dumps(
        {
            "commits": [
                {"commit": {"message": "fix: something (CVE-2026-11111)"}},
            ]
        }
    )
    releases_body = json.dumps(
        [
            {
                "tag_name": "v4.1.6",  # out of range (> new_version)
                "body": "should not be counted CVE-2026-99999",
            },
            {
                "tag_name": "v4.1.4",  # in range (old < v <= new)
                "body": "fixes CVE-2026-22222",
            },
            {
                "tag_name": "v4.1.2",  # out of range (<= old_version)
                "body": "should not be counted CVE-2026-33333",
            },
        ]
    )
    fetcher = _fetcher_from_map(
        {
            "https://api.github.com/repos/patroni/patroni/compare/": compare_body,
            "https://api.github.com/repos/patroni/patroni/releases": releases_body,
        }
    )

    result = scan_release_cves([pkg], tmp_path, None, fetcher=fetcher)

    assert len(result.lines) == 1
    line = result.lines[0]
    assert "CVE-2026-11111" in line
    assert "CVE-2026-22222" in line
    assert "CVE-2026-99999" not in line
    assert "CVE-2026-33333" not in line
    # sorted + deduped
    assert line.index("CVE-2026-11111") < line.index("CVE-2026-22222")


# --- 4. PostgreSQL path ----------------------------------------------------


def test_scan_postgres_reports_cve_count(tmp_path):
    pkg = ChangedPackage(
        key="percona-postgresql17",
        old_version="17.10",
        new_version="17.11",
        upstream_url="https://git.postgresql.org/git/postgresql.git",
        revision="REL_17_11",
    )
    html = (
        "<html>Fixes CVE-2026-00001 and CVE-2026-00002 and also CVE-2026-00003</html>"
    )
    fetcher = _fetcher_from_map(
        {"https://www.postgresql.org/docs/release/17.11/": html}
    )

    result = scan_release_cves([pkg], tmp_path, None, fetcher=fetcher)

    assert len(result.lines) == 1
    line = result.lines[0]
    assert "fixes 3 CVEs" in line
    assert "CVE-2026-00001" in line
    assert "CVE-2026-00002" in line
    assert "CVE-2026-00003" in line


# --- 5. Unscannable upstream -----------------------------------------------


def test_unscannable_upstream_reported_as_not_scanned(tmp_path):
    pkg = ChangedPackage(
        key="percona-haproxy",
        old_version="2.8.9",
        new_version="2.8.10",
        upstream_url="http://git.haproxy.org/git/haproxy-2.8.git",
        revision="v2.8.10",
    )

    def _fetcher(url, headers=None):
        raise AssertionError("should not fetch for an unscannable upstream")

    result = scan_release_cves([pkg], tmp_path, None, fetcher=_fetcher)

    assert result.lines == [
        "- Not scanned: percona-haproxy (no scanner for git.haproxy.org)"
    ]
    assert result.unscanned == [("percona-haproxy", "no scanner for git.haproxy.org")]


# --- 6. Fetcher raising never propagates -----------------------------------


def test_fetcher_raising_lands_in_unscanned_never_raises(tmp_path):
    pkg = ChangedPackage(
        key="percona-pg_tde",
        old_version="2.2.1",
        new_version="2.2.2",
        upstream_url="https://github.com/percona/pg_tde.git",
        revision="2.2.2",
    )

    def _fetcher(url, headers=None):
        raise RuntimeError("network is down")

    result = scan_release_cves([pkg], tmp_path, None, fetcher=_fetcher)

    assert result.lines  # a "Not scanned" trailer line was produced
    assert any(key == "percona-pg_tde" for key, _ in result.unscanned)


# --- 7. scan_go_toolchain ---------------------------------------------------


def test_scan_go_toolchain_finds_cve_and_version_range(tmp_path):
    repo_root = tmp_path / "root"
    repo_root.mkdir()
    (repo_root / "macros.yaml").write_text("- GOLANG_VERSION: 1.26.6\n")
    build_dir = (
        repo_root / "common" / "deps" / "runtime" / "percona-telemetry-agent" / "obs"
    )
    build_dir.mkdir(parents=True)
    (build_dir / "_service").write_text(
        '<services><service name="go_modules"/></services>'
    )

    def _run_git(args):
        assert args == ["show", "prevtag:root/macros.yaml"]
        return "- GOLANG_VERSION: 1.26.3\n"

    search_bodies = {
        "Go1.26.4": json.dumps({"items": []}),
        "Go1.26.5": json.dumps(
            {"items": [{"title": "os: some race condition (CVE-2026-39822)"}]}
        ),
        "Go1.26.6": json.dumps({"items": []}),
    }

    def _fetcher(url, headers=None):
        for marker, body in search_bodies.items():
            if marker in url:
                return body
        raise AssertionError(f"unexpected fetch: {url}")

    line, reason = scan_go_toolchain(repo_root, "prevtag", _fetcher, _run_git)

    assert reason is None
    assert line is not None
    assert "CVE-2026-39822" in line
    assert "1.26.3" in line and "1.26.6" in line
    assert "os" in line


def test_scan_go_toolchain_equal_versions_is_noop(tmp_path):
    repo_root = tmp_path / "root"
    repo_root.mkdir()
    (repo_root / "macros.yaml").write_text("- GOLANG_VERSION: 1.26.6\n")

    def _run_git(args):
        return "- GOLANG_VERSION: 1.26.6\n"

    def _fetcher(url, headers=None):
        raise AssertionError("should not fetch when versions are equal")

    line, reason = scan_go_toolchain(repo_root, "prevtag", _fetcher, _run_git)

    assert line is None
    assert reason is None


def test_scan_go_toolchain_missing_prev_tag_is_noop(tmp_path):
    repo_root = tmp_path / "root"
    repo_root.mkdir()
    (repo_root / "macros.yaml").write_text("- GOLANG_VERSION: 1.26.6\n")

    def _run_git(args):
        raise AssertionError("should not be called with no prev tag")

    def _fetcher(url, headers=None):
        raise AssertionError("should not fetch with no prev tag")

    line, reason = scan_go_toolchain(repo_root, None, _fetcher, _run_git)

    assert line is None
    assert reason is None


# --- 8. _build_changelog_section wiring + Fixed regression -----------------


def test_build_changelog_section_security_present_after_changed(tmp_path):
    section = cmd_project._build_changelog_section(
        "17.11-1",
        {"percona-postgresql": "17.11-1"},
        {"percona-postgresql": "17.10-1"},
        tmp_path,
        security_lines=[
            "- percona-postgresql: PostgreSQL 17.11 fixes 1 CVEs: CVE-2026-1"
        ],
    )

    assert "### Fixed" not in section
    changed_idx = section.index("### Changed")
    security_idx = section.index("### Security")
    assert changed_idx < security_idx
    assert "CVE-2026-1" in section


def test_build_changelog_section_no_security_when_none(tmp_path):
    section = cmd_project._build_changelog_section(
        "17.11-1",
        {"percona-postgresql": "17.11-1"},
        {"percona-postgresql": "17.10-1"},
        tmp_path,
        security_lines=None,
    )

    assert "### Security" not in section
    assert "### Fixed" not in section


def test_build_changelog_section_no_security_when_empty_list(tmp_path):
    section = cmd_project._build_changelog_section(
        "17.11-1",
        {"percona-postgresql": "17.11-1"},
        {"percona-postgresql": "17.10-1"},
        tmp_path,
        security_lines=[],
    )

    assert "### Security" not in section
