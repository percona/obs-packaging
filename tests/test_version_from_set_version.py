"""Package versions from a set_version service (download_url sources).

pgBackRest moved from an obs_scm checkout to upstream's release tarball
(download_url + set_version). OBS's set_version reads the version from the
downloaded file's name; percona-obs only read obs_scm versions, so the
package silently dropped out of EXPECTED_VERSIONS and the QA tests fell back
to stale tables.
"""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

from percona_obs import cmd_qa
from percona_obs.cmd_project import _extract_version_from_service

REPO = Path(__file__).resolve().parent.parent


def _service(tmp_path, body):
    f = tmp_path / "_service"
    f.write_text("<services>%s</services>" % body)
    return f


DOWNLOAD = (
    '<service name="download_url">'
    '<param name="url">https://example.org/r/%!{V}/tool-%!{V}.tar.gz</param>'
    '<param name="filename">percona-tool-%!{V}.tar.gz</param>'
    "</service>"
)


def test_version_from_download_filename(tmp_path):
    svc = _service(tmp_path, DOWNLOAD + '<service mode="buildtime" name="set_version">'
                   '<param name="basename">percona-tool</param></service>')
    assert _extract_version_from_service(svc) == "%!{V}"


def test_explicit_set_version_version_wins(tmp_path):
    svc = _service(tmp_path, DOWNLOAD + '<service name="set_version">'
                   '<param name="version">9.9</param><param name="basename">percona-tool</param></service>')
    assert _extract_version_from_service(svc) == "9.9"


@pytest.mark.parametrize("suffix", [".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst", ".tgz", ".zip"])
def test_archive_suffixes(tmp_path, suffix):
    svc = _service(tmp_path, '<service name="download_url"><param name="filename">percona-tool-1.2.3%s</param></service>'
                   '<service name="set_version"><param name="basename">percona-tool</param></service>' % suffix)
    assert _extract_version_from_service(svc) == "1.2.3"


def test_url_basename_when_no_filename(tmp_path):
    svc = _service(tmp_path, '<service name="download_url"><param name="url">https://x/y/percona-tool-2.0.tar.gz</param></service>'
                   '<service name="set_version"><param name="basename">percona-tool</param></service>')
    assert _extract_version_from_service(svc) == "2.0"


@pytest.mark.parametrize("body", [
    DOWNLOAD,  # download_url alone: no set_version, no version
    DOWNLOAD + '<service name="set_version"><param name="file">x.spec</param></service>',  # no basename
    DOWNLOAD + '<service name="set_version"><param name="basename">other</param></service>',  # name mismatch
])
def test_no_version_without_a_usable_set_version(tmp_path, body):
    assert _extract_version_from_service(_service(tmp_path, body)) is None


def test_obs_scm_version_still_wins(tmp_path):
    svc = _service(tmp_path, '<service name="obs_scm"><param name="version">1.0</param></service>' + DOWNLOAD
                   + '<service name="set_version"><param name="basename">percona-tool</param></service>')
    assert _extract_version_from_service(svc) == "1.0"


def test_pgbackrest_in_tools_versions():
    """The real package: its version resolves through PGBACKREST_VERSION."""
    versions = cmd_qa._own_package_versions("ppg:staging:common:tools")
    assert versions.get("percona-pgbackrest")
    assert "%!{" not in versions["percona-pgbackrest"]


def test_pgbackrest_reaches_server_image_expected_versions():
    """End to end: the PG 15 server image QA gets percona-pgbackrest."""
    args = SimpleNamespace(project="ppg:staging:15:containers", rootprj="isv:percona", json=True, apiurl=None,
                           env_overrides=["REMOTE_OBS_ORG_INTERCONNECT:"], profile=None,
                           image_fallback_rootprj=None, package=None, project_only=False)
    out = io.StringIO()
    with redirect_stdout(out):
        cmd_qa.cmd_qa_show(args)
    entries = [e for e in json.loads(out.getvalue()) if e["pipeline"] == "docker-server-parallel"]
    assert entries
    for e in entries:
        lines = e["params"]["EXPECTED_VERSIONS"].splitlines()
        assert any(l.startswith("percona-pgbackrest=") for l in lines), e.get("name")
