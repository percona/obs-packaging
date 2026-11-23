import json
from percona_obs.image_cves import (
    Finding,
    fetch_scans,
    findings_by_repo,
    image_cve_lines,
)

ROW = {
    "repo": "ubi9",
    "arch": "x86_64",
    "scanned_at": "2026-11-23T02:38:50Z",
    "findings": [
        {
            "id": "CVE-1",
            "pkg": "krb5-libs",
            "installed": "1.21-11.el9",
            "fixed": "1.21-11.el9_3.2",
            "severity": "HIGH",
        },
    ],
}


def test_fetch_scans_url():
    seen = []

    def fetcher(url):
        seen.append(url)
        return json.dumps([ROW])

    rows = fetch_scans(
        "https://dash.example/", "ppg:releases:17:containers", "img a", fetcher
    )
    assert rows == [ROW]
    assert seen == [
        "https://dash.example/api/cve/scans?project=ppg%3Areleases%3A17%3Acontainers&package=img+a"
    ]


def test_findings_by_repo_unions_archs_and_keeps_clean_rows():
    other_arch = {
        **ROW,
        "arch": "aarch64",
        "findings": [
            {
                "id": "CVE-2",
                "pkg": "curl",
                "installed": "8.1-1.el9",
                "fixed": "",
                "severity": "critical",
            },
        ],
    }
    clean = {"repo": "ubi8", "arch": "x86_64", "clean_since": "2026-11-20T00:00:00Z"}
    by_repo = findings_by_repo([ROW, other_arch, clean])
    assert by_repo["ubi8"] == set()
    assert by_repo["ubi9"] == {
        Finding("CVE-1", "krb5-libs", "1.21-11.el9", "1.21-11.el9_3.2", "HIGH"),
        Finding("CVE-2", "curl", "8.1-1.el9", "", "CRITICAL"),
    }
    assert "ubi10" not in by_repo


def test_image_cve_lines_fixed_only_and_grouped():
    f1 = Finding("CVE-2", "krb5-libs", "1.21-11.el9", "1.21-11.el9_3.2", "HIGH")
    f2 = Finding("CVE-1", "krb5-libs", "1.21-11.el9", "1.21-11.el9_3.2", "HIGH")
    f3 = Finding("CVE-3", "python3.12-dns", "2.8.0-3.1.el9", "2.9.0", "CRITICAL")
    f4 = Finding("CVE-4", "zlib", "1.2-1.el9", "", "HIGH")
    still_open = Finding("CVE-9", "openssl", "3.0-1.el9", "3.0-2.el9", "HIGH")
    lines = image_cve_lines(
        ["img (ubi9)"],
        {"img (ubi9)": {f1, f2, f3, f4, still_open}},
        {"img (ubi9)": {still_open}},
        {"img (ubi9)": {"python3.12-dns": "2.9.0-3.2.el9"}},
    )
    assert lines == [
        "- img (ubi9) [container image]: fixes 4 CRITICAL/HIGH CVEs\n"
        "  - krb5-libs 1.21-11.el9 (fix: 1.21-11.el9_3.2): CVE-1, CVE-2\n"
        "  - python3.12-dns 2.8.0-3.1.el9 → 2.9.0-3.2.el9: CVE-3\n"
        "  - zlib 1.2-1.el9: CVE-4"
    ]


def test_image_cve_lines_single_cve_is_singular():
    f = Finding("CVE-1", "zlib", "1.2-1.el9", "", "HIGH")
    assert image_cve_lines(["k"], {"k": {f}}, {"k": set()}, {})[0].startswith(
        "- k [container image]: fixes 1 HIGH CVE\n"
    )


def test_image_cve_lines_no_fixes_no_entry():
    f = Finding("CVE-1", "zlib", "1.2-1.el9", "", "HIGH")
    assert image_cve_lines(["k"], {"k": {f}}, {"k": {f}}, {}) == []
    assert image_cve_lines(["k"], {"k": set()}, {"k": set()}, {}) == []


def test_image_cve_lines_missing_scan_side():
    f = Finding("CVE-1", "zlib", "1.2-1.el9", "", "HIGH")
    assert image_cve_lines(["a", "b"], {"a": {f}}, {"b": set()}, {}) == [
        "- Not scanned: a [container image] (no dashboard scan of the candidate image)",
        "- Not scanned: b [container image] (no dashboard scan of the previous image)",
    ]


def test_image_cve_lines_does_not_cross_repos():
    f = Finding("CVE-1", "zlib", "1.2-1.el8", "", "HIGH")
    lines = image_cve_lines(
        ["img (ubi8)", "img (ubi9)"],
        {"img (ubi8)": {f}, "img (ubi9)": set()},
        {"img (ubi8)": set(), "img (ubi9)": set()},
        {},
    )
    assert len(lines) == 1 and lines[0].startswith("- img (ubi8) ")
