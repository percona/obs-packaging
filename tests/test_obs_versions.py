"""percona_obs.obs_versions: package versions from OBS binary file names."""

import io
import urllib.error

import pytest

import percona_obs.obs_versions as ov
from percona_obs.cmd_build import _version_from_binary
from percona_obs.project_config import RepositoryFilter

_XML = """<resultlist state="x">
 <result project="P" repository="RockyLinux_9" arch="x86_64" code="published" state="published">
  <binarylist package="percona-pgbackrest">
   <binary filename="_buildenv" size="1" mtime="1"/>
   <binary filename="percona-pgbackrest-debuginfo-2.60.0-1.1.x86_64.rpm" size="1" mtime="1"/>
   <binary filename="percona-pgbackrest-2.60.0-1.1.src.rpm" size="1" mtime="1"/>
  </binarylist>
  <binarylist package="percona-image"><binary filename="img.containerinfo" size="1" mtime="1"/></binarylist>
  <binarylist package="geos"/>
 </result>
 <result project="P" repository="Debian_12" arch="x86_64" code="published" state="published">
  <binarylist package="percona-pgbackrest">
   <binary filename="percona-pgbackrest_2.60.0-1_amd64.deb" size="1" mtime="1"/>
  </binarylist>
 </result>
 <result project="P" repository="ubi9" arch="x86_64" code="published" state="published">
  <binarylist package="percona-pgbackrest">
   <binary filename="percona-pgbackrest-2.60.0-3.1.src.rpm" size="1" mtime="1"/>
  </binarylist>
 </result>
</resultlist>"""


class _Resp(io.BytesIO):
    pass


@pytest.fixture(autouse=True)
def _clear():
    ov.clear_cache()
    yield
    ov.clear_cache()


def _serve(monkeypatch, body=_XML, error=None):
    calls = []

    def get(url):
        calls.append(url)
        if error is not None:
            raise error
        return _Resp(body.encode())

    monkeypatch.setattr(ov.osc.connection, "http_GET", get)
    monkeypatch.setattr(
        ov.osc.core,
        "makeurl",
        lambda apiurl, path, query=None: f"{apiurl}/{'/'.join(path)}?{query}",
    )
    return calls


def test_version_from_binary_reads_source_artifacts():
    assert _version_from_binary("percona-pgbackrest-2.60.0-1.1.src.rpm") == "2.60.0-1.1"
    assert _version_from_binary("percona-postgresql-17_17.11.1-1.dsc") == "17.11.1-1"
    assert (
        _version_from_binary("percona-postgresql17-17.11.1-1.18.x86_64.rpm")
        == "17.11.1-1.18"
    )
    assert _version_from_binary("percona-pg-tde18_2.2.2-6_amd64.deb") == "2.2.2-6"
    assert _version_from_binary("_buildenv") is None
    assert (
        _version_from_binary("percona-postgresql-17.11.1-ssl3-linux-x86_64.tar.gz")
        is None
    )


def test_project_binary_versions_per_repo(monkeypatch):
    calls = _serve(monkeypatch)
    got = ov.project_binary_versions("http://obs", "P")
    assert got == {
        "percona-pgbackrest": {
            ("RockyLinux_9", "x86_64"): "2.60.0-1.1",  # .src.rpm preferred
            ("Debian_12", "x86_64"): "2.60.0-1",
            ("ubi9", "x86_64"): "2.60.0-3.1",
        },
        "percona-image": {},  # listed, nothing readable
        "geos": {},  # listed, no binaries
    }
    assert len(calls) == 1 and "binarylist" in calls[0]


def test_project_binary_versions_is_cached(monkeypatch):
    calls = _serve(monkeypatch)
    ov.project_binary_versions("http://obs", "P")
    ov.project_binary_versions("http://obs", "P")
    assert len(calls) == 1


def test_project_binary_versions_respects_the_slice(monkeypatch):
    _serve(monkeypatch)
    rf = RepositoryFilter.from_profile({"exclude-repositories": ["ubi*"]})
    got = ov.project_binary_versions("http://obs", "P", rf)
    assert ("ubi9", "x86_64") not in got["percona-pgbackrest"]


def test_missing_project_is_none(monkeypatch):
    _serve(monkeypatch, error=urllib.error.HTTPError("u", 404, "nf", {}, None))  # type: ignore[arg-type]
    assert ov.project_binary_versions("http://obs", "P") is None


def test_other_errors_are_not_swallowed(monkeypatch):
    _serve(monkeypatch, error=urllib.error.HTTPError("u", 500, "boom", {}, None))  # type: ignore[arg-type]
    with pytest.raises(SystemExit, match="P"):
        ov.project_binary_versions("http://obs", "P")


def test_upstream_version():
    assert ov.upstream_version("2.60.0-1.1") == "2.60.0"
    assert ov.upstream_version("1.0-rc1-2") == "1.0-rc1"
    assert ov.upstream_version("293") == "293"
    # Debian aggregate binaries on OBS carry the distro in the release
    assert ov.upstream_version("2.60.0-1+1.1.bookworm") == "2.60.0"


def test_aggregate_binaries_are_listed_under_the_aggregating_package(monkeypatch):
    """OBS lists an _aggregate's binaries under its own package name in the
    aggregating project's binarylist (real shape, ppg:staging:17)."""
    body = """<resultlist state="x">
 <result project="P" repository="Debian_12" arch="x86_64" code="published" state="published">
  <binarylist package="percona-pgbackrest">
   <binary filename="percona-pgbackrest-dbgsym_2.60.0-1+1.1.bookworm_amd64.deb" size="1" mtime="1"/>
   <binary filename="percona-pgbackrest_2.60.0-1+1.1.bookworm_amd64.deb" size="1" mtime="1"/>
  </binarylist>
 </result>
</resultlist>"""
    _serve(monkeypatch, body=body)
    per = ov.project_binary_versions("http://obs", "P")["percona-pgbackrest"]
    assert ov.agreed_version("percona-pgbackrest", per) == "2.60.0"


def test_agreed_version_and_conflict():
    same = {
        ("Debian_12", "x86_64"): "2.60.0-1",
        ("RockyLinux_9", "x86_64"): "2.60.0-1.1",
    }
    assert ov.agreed_version("p", same) == "2.60.0"
    differ = {
        ("RockyLinux_9", "x86_64"): "1.2.3-1.1",
        ("Debian_12", "x86_64"): "1.2.3-1",
        ("Ubuntu_24.04", "x86_64"): "1.2.4-1",
    }
    with pytest.raises(ov.VersionConflict) as exc:
        ov.agreed_version("percona-foo", differ)
    assert str(exc.value) == (
        "percona-foo: OBS builds disagree on the version: "
        "1.2.3 (Debian_12/x86_64, RockyLinux_9/x86_64), 1.2.4 (Ubuntu_24.04/x86_64)"
    )


def test_first_versrel_is_the_first_sorted_repo():
    per = {("ubi9", "x86_64"): "2.60.0-3.1", ("Debian_12", "x86_64"): "2.60.0-1"}
    assert ov.first_versrel(per) == "2.60.0-1"
