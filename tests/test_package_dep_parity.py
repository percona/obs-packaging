"""Tests for .github/scripts/package_dep_parity.py."""

import gzip
import http.server
import importlib.util
import json
import lzma
import sys
import threading
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "package_dep_parity.py"
spec = importlib.util.spec_from_file_location("package_dep_parity", SCRIPT)
pdp = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pdp  # dataclasses look the module up while loading
spec.loader.exec_module(pdp)


def rpm_pkg(name, srpm, provides=(), requires=(), recommends=(), arch="x86_64"):
    ent = lambda items: "".join('<rpm:entry name="%s"/>' % i for i in items)
    return ('<package type="rpm"><name>%s</name><arch>%s</arch><format>'
            "<rpm:sourcerpm>%s</rpm:sourcerpm>"
            "<rpm:provides>%s</rpm:provides><rpm:requires>%s</rpm:requires>"
            "<rpm:recommends>%s</rpm:recommends></format></package>"
            % (name, arch, srpm, ent((name,) + tuple(provides)), ent(requires), ent(recommends)))


def primary_xml(*pkgs):
    return ('<?xml version="1.0"?><metadata xmlns="http://linux.duke.edu/metadata/common" '
            'xmlns:rpm="http://linux.duke.edu/metadata/rpm" packages="%d">%s</metadata>' % (len(pkgs), "".join(pkgs)))


# PG 17 as the build team reported it: the RPM server requires pg_tde, the Debian one does not.
RPM_PG17 = primary_xml(
    rpm_pkg("percona-postgresql17-server", "percona-postgresql17-17.11-1.el9.src.rpm",
            requires=("percona-postgresql17", "percona-postgresql17-libs", "percona-pg_tde17",
                      "percona-postgresql-common", "libc.so.6()(64bit)", "/bin/sh", "rpmlib(CompressedFileNames)"),
            recommends=("percona-pg-telemetry17",)),
    rpm_pkg("percona-postgresql17", "percona-postgresql17-17.11-1.el9.src.rpm", requires=("percona-postgresql17-libs",)),
    rpm_pkg("percona-postgresql17-libs", "percona-postgresql17-17.11-1.el9.src.rpm"),
    rpm_pkg("percona-postgresql17", "percona-postgresql17-17.11-1.el9.src.rpm", arch="src"),
    rpm_pkg("percona-pg_tde17", "percona-pg_tde17-2.2.2-1.el9.src.rpm", requires=("percona-postgresql17-server",)),
    rpm_pkg("percona-postgresql-common", "percona-postgresql-common-293-1.el9.src.rpm"),
    rpm_pkg("percona-pg-telemetry17", "percona-pg-telemetry17-1.2.0-1.el9.src.rpm"),
    rpm_pkg("percona-pgaudit17", "percona-pgaudit17-17.1-1.el9.src.rpm",
            requires=("(percona-postgresql17-server or postgresql17-server)",)),
)

DEB_PG17 = """Package: percona-postgresql-17
Source: percona-postgresql-17
Version: 3:17.11.1-1.bookworm
Depends: locales | locales-all, percona-postgresql-client-17,
 percona-postgresql-common (>= 182~), ssl-cert, tzdata, libc6 (>= 2.34)
Recommends: sysstat, percona-pg-telemetry17

Package: percona-postgresql-client-17
Source: percona-postgresql-17
Version: 3:17.11.1-1.bookworm
Depends: libpq5 (>= 17~~)

Package: libpq5
Source: percona-postgresql-17
Version: 3:17.11.1-1.bookworm

Package: percona-pg-tde17
Source: percona-pg-tde17 (2.2.2-1)
Version: 2.2.2-1.bookworm
Depends: percona-postgresql-17

Package: percona-postgresql-common
Version: 1:293-1.bookworm

Package: percona-pg-telemetry17
Source: percona-pg-telemetry17
Version: 1:1.2.0-1.bookworm

Package: percona-postgresql-17-pgaudit
Source: percona-pgaudit17
Version: 17.1-1.bookworm
Depends: percona-postgresql-17 | postgresql-17
"""


class _Server:
    def __init__(self, files):
        self.files = files

    def __enter__(self):
        files = self.files

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = files.get(self.path)
                self.send_response(200 if body is not None else 404)
                self.end_headers()
                if body is not None:
                    self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def __exit__(self, *a):
        self.httpd.shutdown()


def repo_files(rpm_primary, deb_packages, project="isv:percona:ppg:staging:17"):
    p = "/repositories/%s" % project.replace(":", ":/")
    repomd = ('<?xml version="1.0"?><repomd xmlns="http://linux.duke.edu/metadata/repo">'
              '<data type="primary"><location href="repodata/abc-primary.xml.gz"/></data></repomd>')
    return {p + "/RockyLinux_9/repodata/repomd.xml": repomd.encode(),
            p + "/RockyLinux_9/repodata/abc-primary.xml.gz": gzip.compress(rpm_primary.encode()),
            p + "/Debian_12/Packages.xz": lzma.compress(deb_packages.encode())}


def test_end_to_end_finds_the_missing_pg_tde_dependency(tmp_path):
    out, summary = tmp_path / "r.json", tmp_path / "s.md"
    with _Server(repo_files(RPM_PG17, DEB_PG17)) as url:
        rc = pdp.main(["--project", "isv:percona:ppg:staging:17", "--base-url", url, "--allowlist", "none",
                       "--json", str(out), "--summary", str(summary)])
    assert rc == 0                                   # report-only by default
    result = json.loads(out.read_text())
    assert result["diffs"] == [{"source": "perconapostgresql", "kind": "hard", "dep": "perconapgtde", "only_in": "rpm"}]
    md = summary.read_text()
    assert "**1 difference(s) to review**" in md and "| perconapostgresql | requires | perconapgtde | ✓ | ✗ missing |" in md


def test_same_dependencies_in_both_formats_are_not_reported():
    rpm = pdp.dependency_graph(pdp.parse_rpm_primary(RPM_PG17.encode()), "17")
    deb = pdp.dependency_graph(pdp.parse_deb_packages(DEB_PG17), "17")
    # common (hard) and telemetry (weak) are in both; pgaudit -> server in both (rich dep / alternative)
    assert "perconapostgresqlcommon" in rpm["perconapostgresql"]["hard"] & deb["perconapostgresql"]["hard"]
    assert rpm["perconapostgresql"]["weak"] == deb["perconapostgresql"]["weak"] == {"perconapgtelemetry"}
    assert rpm["perconapgaudit"]["hard"] == deb["perconapgaudit"]["hard"] == {"perconapostgresql"}


def test_dependencies_within_a_source_and_on_system_packages_are_ignored():
    deb = pdp.dependency_graph(pdp.parse_deb_packages(DEB_PG17), "17")
    assert "perconapostgresql" not in deb["perconapostgresql"]["hard"]     # client-17, libpq5: same source
    assert not any("ssl" in d or "locales" in d for d in deb["perconapostgresql"]["hard"])


def test_strict_fails_on_new_differences_and_allowlist_accepts_them(tmp_path):
    allow = tmp_path / "allow.yaml"
    with _Server(repo_files(RPM_PG17, DEB_PG17)) as url:
        args = ["--project", "isv:percona:ppg:staging:17", "--base-url", url, "--strict"]
        assert pdp.main(args + ["--allowlist", "none"]) == 1
        allow.write_text("- major: 17\n  source: perconapostgresql\n  dep: perconapgtde\n  kind: hard\n"
                         "  only_in: rpm\n  reason: under review\n")
        assert pdp.main(args + ["--allowlist", str(allow)]) == 0


def test_name_normalisation_matches_the_two_formats():
    n = lambda s: pdp.normalise(s, "17")
    assert n("percona-pg_tde17") == n("percona-pg-tde17") == n("percona-pg-tde-17") == "perconapgtde"
    assert n("percona-postgresql17") == n("percona-postgresql-17") == "perconapostgresql"
    assert n("percona-postgis35_17") == "perconapostgis35"       # other digits are kept
    assert pdp.normalise("percona-postgresql-common", "17") == "perconapostgresqlcommon"


def test_deb_parsing_details():
    b = pdp.parse_deb_packages("Package: x\nSource: y (1.0)\nDepends: a (>= 1) | b:any [amd64], c\nPre-Depends: d\n"
                               "Provides: x-virtual (= 1)\n")[0]
    assert b.source == "y" and b.hard == [["a", "b"], ["c"], ["d"]] and "x-virtual" in b.provides


def test_missing_repository_is_a_clear_error():
    with _Server({}) as url, pytest.raises(SystemExit, match="no RPM repository"):
        pdp.main(["--project", "isv:percona:ppg:staging:17", "--base-url", url, "--allowlist", "none"])


# --- refinements from the first real run (PG 17, RockyLinux_9 vs Debian_12) ---

RPM_REFINE = primary_xml(
    rpm_pkg("percona-patroni", "percona-patroni-4.1.0-1.el9.src.rpm",
            requires=("python312-etcd", "percona-postgresql-common")),
    rpm_pkg("python312-etcd", "python312-etcd-0.4.5-1.el9.src.rpm"),
    rpm_pkg("percona-postgresql-common", "percona-postgresql-common-293-1.el9.src.rpm"),
    rpm_pkg("percona-postgis35_17", "percona-postgis35_17-3.5.7-1.el9.src.rpm", requires=("percona-postgresql17-server",)),
    rpm_pkg("percona-postgresql17-server", "percona-postgresql17-17.11-1.el9.src.rpm"),
)
DEB_REFINE = """Package: percona-patroni
Version: 4.1.0-1
Depends: python3-etcd, python3-psycopg2, percona-postgresql-common

Package: python3-psycopg2
Source: psycopg2
Version: 2.9-1

Package: percona-postgresql-common
Version: 1:293-1

Package: percona-postgresql-17-postgis-3
Source: percona-postgis
Version: 3.5.7-1
Depends: percona-postgresql-17

Package: percona-postgresql-17
Source: percona-postgresql-17
Version: 3:17.11.1-1
Depends: percona-postgresql-common
"""


def _run(rpm, deb, cfg):
    rpm_g = pdp.apply_aliases(pdp.dependency_graph(pdp.parse_rpm_primary(rpm.encode()), "17"), cfg)
    deb_g = pdp.apply_aliases(pdp.dependency_graph(pdp.parse_deb_packages(deb), "17"), cfg)
    return pdp.compare(rpm_g, deb_g)


def test_dependencies_on_one_format_only_packages_are_not_compared():
    r = _run(RPM_REFINE, DEB_REFINE, {})
    deps = {(d["source"], d["dep"]) for d in r["diffs"]}
    assert ("perconapatroni", "python312etcd") not in deps          # python312-etcd: RPM-only package
    assert ("perconapatroni", "psycopg2") not in deps               # psycopg2: Debian-only package
    assert "python312etcd" in r["only_rpm_sources"] and "psycopg2" in r["only_deb_sources"]


def test_aliases_pair_renamed_packages_so_they_are_compared():
    without = _run(RPM_REFINE, DEB_REFINE, {})
    assert "perconapostgis35" in without["only_rpm_sources"] and "perconapostgis" in without["only_deb_sources"]
    paired = _run(RPM_REFINE, DEB_REFINE, {"perconapostgis35": "perconapostgis"})
    assert "perconapostgis35" not in paired["only_rpm_sources"] and "perconapostgis" not in paired["only_deb_sources"]
    assert not [d for d in paired["diffs"] if d["source"] == "perconapostgis"]   # both depend on the server


def test_wildcard_allowlist_and_dict_config(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("aliases:\n  perconapostgis35: perconapostgis\nallowed:\n"
                   "  - source: '*'\n    dep: perconapostgresqlcommon\n    only_in: deb\n    reason: Debian cluster framework\n")
    aliases, allow = pdp.load_config(str(cfg))
    assert aliases == {"perconapostgis35": "perconapostgis"} and len(allow) == 1
    d1 = {"source": "perconapostgresql", "kind": "hard", "dep": "perconapostgresqlcommon", "only_in": "deb"}
    d2 = dict(d1, source="perconapgbouncer")
    d3 = dict(d1, only_in="rpm")
    assert pdp.allowed(d1, "17", allow) and pdp.allowed(d2, "17", allow) and not pdp.allowed(d3, "17", allow)


def test_the_repository_config_file_loads():
    aliases, allow = pdp.load_config(str(SCRIPT.parents[1] / "package-deps-qa.yaml"))
    assert aliases.get("perconapostgis35") == "perconapostgis" and isinstance(allow, list)
    assert all(a.get("reason") for a in allow)          # every intended difference says why
    assert "RockyLinux_9:Debian_12" in pdp._config_pairs(str(SCRIPT.parents[1] / "package-deps-qa.yaml"))


def test_explicit_repository_addresses_e_g_repo_percona_com(tmp_path):
    files = repo_files(RPM_PG17, DEB_PG17)
    moved = {k.replace("/repositories/isv:/percona:/ppg:/staging:/17/RockyLinux_9", "/ppg-17.10/yum/release/9/RPMS/x86_64")
              .replace("/repositories/isv:/percona:/ppg:/staging:/17/Debian_12", "/ppg-17.10/apt/dists/bookworm/main/binary-amd64"): v
             for k, v in files.items()}
    out = tmp_path / "r.json"
    with _Server(moved) as url:
        rc = pdp.main(["--major", "17", "--allowlist", "none", "--json", str(out),
                       "--rpm-url", url + "/ppg-17.10/yum/release/9/RPMS/x86_64",
                       "--deb-url", url + "/ppg-17.10/apt/dists/bookworm/main/binary-amd64/"])
    assert rc == 0
    assert json.loads(out.read_text())["diffs"][0]["dep"] == "perconapgtde"


def test_project_or_both_urls_required():
    with pytest.raises(SystemExit):
        pdp.main(["--rpm-url", "http://x/"])


def test_el10_user_and_group_dependencies_are_ignored():
    # EL10 generates "user(postgres)" deps; the server and pgbackrest both
    # provide it, which made pgbackrest look like it recommends the server.
    rpm = pdp.parse_rpm_primary(primary_xml(
        rpm_pkg("percona-pgbackrest", "percona-pgbackrest-2.60.1-1.el10.src.rpm",
                requires=("user(postgres)",), recommends=("group(postgres)",)),
        rpm_pkg("percona-postgresql17-server", "percona-postgresql17-17.12-1.el10.src.rpm",
                provides=("user(postgres)", "group(postgres)"))).encode())
    graph = pdp.dependency_graph(rpm, "17")
    assert graph["perconapgbackrest"]["hard"] == graph["perconapgbackrest"]["weak"] == set()


def test_several_pairs_in_one_report_say_where_each_difference_is_seen(tmp_path):
    files = repo_files(RPM_PG17, DEB_PG17)
    p = "/repositories/isv:/percona:/ppg:/staging:/17"
    # a second Debian repository with the same packages, and one that is not published
    files[p + "/Ubuntu_24.04/Packages.xz"] = files[p + "/Debian_12/Packages.xz"]
    out, summary = tmp_path / "r.json", tmp_path / "s.md"
    with _Server(files) as url:
        rc = pdp.main(["--project", "isv:percona:ppg:staging:17", "--base-url", url, "--allowlist", "none",
                       "--pairs", "RockyLinux_9:Debian_12,RockyLinux_9:Ubuntu_24.04,RockyLinux_9:Debian_13",
                       "--json", str(out), "--summary", str(summary), "--strict"])
    assert rc == 1
    result = json.loads(out.read_text())
    assert [d["pairs"] for d in result["new"]] == [["RockyLinux_9:Debian_12", "RockyLinux_9:Ubuntu_24.04"]]
    assert result["missing"] == {"RockyLinux_9:Debian_13": "no Debian_13 repository"}
    md = summary.read_text()
    assert "| perconapostgresql | requires | perconapgtde | RPM | Debian | all |" in md
    assert "Not compared (repository not published): RockyLinux_9:Debian_13" in md
