"""Tests for .github/scripts/package_server_dep.py.

The fixtures are the real dependencies found on ppg:staging:17-19 on
2026-11-21 (dependency audit, QA ticket 1.1).
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "package_server_dep.py"
spec = importlib.util.spec_from_file_location("package_server_dep", SCRIPT)
psd = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = psd
spec.loader.exec_module(psd)
pdp = psd.pdp

import pytest  # noqa: E402
import yaml  # noqa: E402

EXCLUDE = yaml.safe_load((ROOT / ".github" / "package-deps-qa.yaml").read_text())[
    "server_dependency"
]["exclude"]


def deb(*stanzas):
    return pdp.parse_deb_packages("\n\n".join(stanzas))


DEB_17 = deb(
    "Package: percona-postgresql-17\nSource: percona-postgresql-17\nDepends: percona-postgresql-client-17, "
    "percona-pg-tde17, libpq5 (>= 14~~)\nProvides: postgresql-17 (= 2:17.12-1)",
    "Package: percona-postgresql-client-17\nSource: percona-postgresql-17\nDepends: libpq5",
    "Package: libpq5\nSource: percona-postgresql-17",
    # bug: ${postgresql:Depends} came out empty
    "Package: percona-pg-tde17\nSource: percona-pg-tde17\nDepends: libc6 (>= 2.34), libcurl4t64, libpq5 (>= 14~beta2)",
    "Package: percona-pg-tde17-client\nSource: percona-pg-tde17\nDepends: percona-pg-tde17 (= 1:2.2.2-2)",
    # fine: through the virtual name the server provides
    "Package: percona-pg-telemetry17\nSource: percona-pg-telemetry17\nDepends: postgresql-17 (>> 17.12), libc6",
    # fine: through PostGIS, which depends on the server
    "Package: percona-postgresql-17-postgis-3\nSource: percona-postgis\nDepends: percona-postgresql-17 | postgresql-17",
    "Package: percona-postgresql-17-postgis-tiger-geocoder\nSource: percona-postgis-tiger\n"
    "Depends: percona-postgresql-17-postgis-3",
    "Package: percona-postgresql-17-pgaudit-dbgsym\nSource: percona-pgaudit17\nDepends: libc6",
    "Package: percona-postgresql-server-dev-17\nSource: percona-postgresql-17\nDepends: libpq-dev",
)


def rpm(*pkgs):
    ent = lambda items: "".join('<rpm:entry name="%s"/>' % i for i in items)
    body = "".join(
        '<package type="rpm"><name>%s</name><arch>x86_64</arch><format><rpm:sourcerpm>%s-1-1.el9.src.rpm'
        "</rpm:sourcerpm><rpm:provides>%s</rpm:provides><rpm:requires>%s</rpm:requires></format></package>"
        % (n, n, ent((n,) + tuple(prov)), ent(req))
        for n, prov, req in pkgs
    )
    return pdp.parse_rpm_primary(
        (
            '<?xml version="1.0"?><metadata xmlns="http://linux.duke.edu/metadata/common" '
            'xmlns:rpm="http://linux.duke.edu/metadata/rpm">%s</metadata>' % body
        ).encode()
    )


RPM_18 = rpm(
    (
        "percona-postgresql18-server",
        ("postgresql18-server",),
        ("percona-postgresql18-libs",),
    ),
    ("percona-postgresql18", (), ("percona-postgresql18-libs",)),
    ("percona-postgresql18-libs", ("libpq.so.5()(64bit)",), ()),
    # bug: only libpq.so.5 (RHEL's own libpq provides it too)
    ("percona-pg_tde18", (), ("libpq.so.5()(64bit)", "json-c", "curl")),
    # bug: requires the client package, not the server
    ("percona-pg_oidc_validator18", (), ("percona-postgresql18", "libcurl")),
    # fine: virtual name provided by the server
    ("percona-pgaudit18", ("percona-pgaudit18(x86-64)",), ("postgresql18-server",)),
    # the version (with the missing epoch) is an attribute in primary.xml, not
    # part of the name: that bug is the installability check's to find
    ("percona-pgaudit18-llvmjit", (), ("percona-pgaudit18(x86-64)",)),
    ("percona-pgpool-II-pg18", (), ("libpq.so.5()(64bit)",)),  # excluded: a proxy
    ("percona-postgis35_18-client", (), ()),  # excluded: client tools
    ("percona-pg_tde18-debuginfo", (), ()),  # excluded: debug symbols
    ("llvm18-libs", (), ()),  # not ours
)


def test_debian_extensions_without_the_server_are_found():
    assert psd.check(DEB_17, "deb", "17", EXCLUDE) == ["percona-pg-tde17"]


def test_rpm_extensions_without_the_server_are_found():
    assert psd.check(RPM_18, "rpm", "18", EXCLUDE) == [
        "percona-pg_oidc_validator18",
        "percona-pg_tde18",
    ]


def test_indirect_and_virtual_dependencies_count():
    reach = psd.reaches_server(DEB_17, "deb", "17")
    assert (
        reach["percona-pg-telemetry17"]
        and reach["percona-postgresql-17-postgis-tiger-geocoder"]
    )
    rpm_reach = psd.reaches_server(RPM_18, "rpm", "18")
    assert rpm_reach["percona-pgaudit18"] and rpm_reach["percona-pgaudit18-llvmjit"]


def test_candidates_need_the_major_as_a_number_of_its_own():
    c = lambda n, m="17": psd.is_candidate(n, m, EXCLUDE)
    assert (
        c("percona-pg_tde17")
        and c("percona-postgresql-17-pgaudit")
        and c("percona-pgvector_17")
    )
    assert (
        not c("percona-pgbackrest")
        and not c("percona-postgis35_17-client")
        and not c("geos317")
    )
    assert not c("percona-postgresql17", "17") and not c("percona-pgpool-II-pg17")
    assert c("percona-pgpool-II-pg17-extensions")


def test_repository_without_this_server_is_not_checked():
    # None, not []: an empty list would read as "checked, nothing wrong"
    assert psd.check(DEB_17, "deb", "18", EXCLUDE) is None


def test_allowlist_and_report():
    md, new = psd.report_markdown(
        "isv:percona:ppg:staging:18",
        "18",
        {
            "RockyLinux_9": ["percona-pg_tde18"],
            "RockyLinux_8": ["percona-pg_tde18"],
            "Debian_12": ["percona-pg-oidc-validator18"],
        },
        {"Debian_13": "no Debian Packages index"},
        [{"package": "percona-pg-oidc-.*", "reason": "test"}],
    )
    assert list(new) == ["percona-pg_tde18"]
    assert "**1 package(s) do not depend on the PG 18 server**, 1 allowlisted" in md
    assert "| percona-pg_tde18 | RockyLinux_9, RockyLinux_8 |" in md
    assert "Not checked: Debian_13 (no Debian Packages index)" in md


def test_end_to_end_with_a_served_repository(tmp_path, monkeypatch):
    monkeypatch.setattr(pdp, "load_deb_repo", lambda url: DEB_17)
    monkeypatch.setattr(
        pdp,
        "load_rpm_repo",
        lambda url: (_ for _ in ()).throw(SystemExit("no RPM repository")),
    )
    out = tmp_path / "r.json"
    rc = psd.main(
        [
            "--project",
            "isv:percona:ppg:staging:17",
            "--config",
            str(ROOT / ".github/package-deps-qa.yaml"),
            "--rpm-repos",
            "RockyLinux_9",
            "--deb-repos",
            "Debian_12",
            "--json",
            str(out),
            "--strict",
        ]
    )
    assert rc == 1
    data = json.loads(out.read_text())
    assert (
        data["new"] == {"percona-pg-tde17": ["Debian_12"]}
        and "RockyLinux_9" in data["missing"]
    )


def _bins(*specs):
    """(name, provides, [[alternatives], ...]) -> Binary objects."""
    return [
        pdp.Binary(
            name=n, source=n, provides={n, *prov}, hard=[list(g) for g in hard], weak=[]
        )
        for n, prov, hard in specs
    ]


def test_dependency_cycles_do_not_depend_on_package_order():
    # foo -> bar and foo -> server; bar -> foo (a cycle). Both reach the server,
    # whichever of them comes first (a memoised depth-first walk reported bar
    # when foo was walked first).
    specs = [
        ("percona-foo17", (), [["percona-bar17"], ["percona-postgresql17-server"]]),
        ("percona-bar17", (), [["percona-foo17"]]),
        ("percona-postgresql17-server", (), []),
    ]
    for order in (specs, specs[::-1], [specs[1], specs[0], specs[2]]):
        assert psd.check(_bins(*order), "rpm", "17", EXCLUDE) == []


def test_server_requiring_an_extension_does_not_count_the_other_way_round():
    # the PG 17 RPM server requires pg_tde; pg_tde itself does not require the server
    bins = _bins(
        ("percona-postgresql17-server", (), [["percona-pg_tde17"]]),
        ("percona-pg_tde17", (), [["json-c"]]),
    )
    assert psd.check(bins, "rpm", "17", EXCLUDE) == ["percona-pg_tde17"]


def test_static_libraries_are_not_extensions():
    assert not psd.is_candidate("percona-postgresql17-static", "17", EXCLUDE)


def test_a_run_that_checks_nothing_fails_even_in_report_only_mode(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(pdp, "load_deb_repo", lambda url: DEB_17)  # has no PG 18 server
    monkeypatch.setattr(
        pdp,
        "load_rpm_repo",
        lambda url: (_ for _ in ()).throw(SystemExit("no RPM repository")),
    )
    summary = tmp_path / "s.md"
    rc = psd.main(
        [
            "--project",
            "isv:percona:ppg:staging:18",
            "--config",
            str(ROOT / ".github/package-deps-qa.yaml"),
            "--rpm-repos",
            "RockyLinux_9",
            "--deb-repos",
            "Debian_12",
            "--summary",
            str(summary),
        ]
    )
    assert rc == 2
    md = summary.read_text()
    assert "Debian_12 (no percona-postgresql-18 package in the repository)" in md
    assert "**Nothing was checked**" in md


def test_an_allowlist_entry_for_one_repository_does_not_hide_the_others():
    per_repo = {"RockyLinux_8": ["percona-x17"], "Debian_12": ["percona-x17"]}
    md, new = psd.report_markdown(
        "p",
        "17",
        per_repo,
        {},
        [{"package": "percona-x17", "repo": "RockyLinux_8", "reason": "test"}],
    )
    assert new == {"percona-x17": ["RockyLinux_8", "Debian_12"]}
    md, new = psd.report_markdown(
        "p", "17", per_repo, {}, [{"package": "percona-x17", "reason": "test"}]
    )
    assert new == {}


def test_allowlist_entry_without_package_is_refused(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("server_dependency:\n  allowed:\n    - reason: forgot the package\n")
    monkeypatch.setattr(pdp, "load_deb_repo", lambda url: DEB_17)
    with pytest.raises(SystemExit):
        psd.main(
            [
                "--project",
                "isv:percona:ppg:staging:17",
                "--config",
                str(cfg),
                "--rpm-repos",
                "",
                "--deb-repos",
                "Debian_12",
            ]
        )


def test_configured_allowlist_covers_the_intended_cases_only():
    cfg = yaml.safe_load((ROOT / ".github" / "package-deps-qa.yaml").read_text())
    allow = cfg["server_dependency"]["allowed"]
    assert all(e.get("reason") for e in allow)
    for pkg, repo in [
        ("percona-pg-telemetry17", "RockyLinux_9"),
        ("percona-pg-telemetry14", "Debian_12"),
        ("percona-postgresql-17-postgis-3-scripts", "Ubuntu_24.04"),
    ]:
        assert psd.allowed(pkg, repo, "17", allow), pkg
    # real bugs stay visible
    for pkg in [
        "percona-pg_tde17",
        "percona-pg-tde17",
        "percona-pg_stat_monitor17",
        "percona-postgresql-17-postgis-3",
    ]:
        assert not psd.allowed(pkg, "Debian_12", "17", allow), pkg
