"""Package versions from a set_version service (download_url sources).

pgBackRest moved from an obs_scm checkout to upstream's release tarball
(download_url + set_version). OBS's set_version reads the version from the
downloaded file's name; percona-obs only read obs_scm versions, so the
package silently dropped out of EXPECTED_VERSIONS and the QA tests fell back
to stale tables.
"""

from pathlib import Path

import pytest

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
    svc = _service(
        tmp_path,
        DOWNLOAD + '<service mode="buildtime" name="set_version">'
        '<param name="basename">percona-tool</param></service>',
    )
    assert _extract_version_from_service(svc) == "%!{V}"


def test_explicit_set_version_version_wins(tmp_path):
    svc = _service(
        tmp_path,
        DOWNLOAD + '<service name="set_version">'
        '<param name="version">9.9</param><param name="basename">percona-tool</param></service>',
    )
    assert _extract_version_from_service(svc) == "9.9"


@pytest.mark.parametrize(
    "suffix", [".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst", ".tgz", ".zip"]
)
def test_archive_suffixes(tmp_path, suffix):
    svc = _service(
        tmp_path,
        '<service name="download_url"><param name="filename">percona-tool-1.2.3%s</param></service>'
        '<service name="set_version"><param name="basename">percona-tool</param></service>'
        % suffix,
    )
    assert _extract_version_from_service(svc) == "1.2.3"


def test_url_basename_when_no_filename(tmp_path):
    svc = _service(
        tmp_path,
        '<service name="download_url"><param name="url">https://x/y/percona-tool-2.0.tar.gz</param></service>'
        '<service name="set_version"><param name="basename">percona-tool</param></service>',
    )
    assert _extract_version_from_service(svc) == "2.0"


@pytest.mark.parametrize(
    "body",
    [
        DOWNLOAD,  # download_url alone: no set_version, no version
        DOWNLOAD
        + '<service name="set_version"><param name="file">x.spec</param></service>',  # no basename
        DOWNLOAD
        + '<service name="set_version"><param name="basename">other</param></service>',  # name mismatch
    ],
)
def test_no_version_without_a_usable_set_version(tmp_path, body):
    assert _extract_version_from_service(_service(tmp_path, body)) is None


def test_obs_scm_version_still_wins(tmp_path):
    svc = _service(
        tmp_path,
        '<service name="obs_scm"><param name="version">1.0</param></service>'
        + DOWNLOAD
        + '<service name="set_version"><param name="basename">percona-tool</param></service>',
    )
    assert _extract_version_from_service(svc) == "1.0"


def test_pgbackrest_service_resolves_through_macros():
    from percona_obs.common import REPO_ROOT, apply_macro_substitution, load_macros

    pkg = REPO_ROOT / "ppg" / "staging" / "common" / "tools" / "percona-pgbackrest"
    raw = _extract_version_from_service(pkg / "obs" / "_service")
    assert raw and "%!{" in raw
    version = apply_macro_substitution(raw, load_macros(pkg), strict=False)
    assert version and "%!{" not in version
