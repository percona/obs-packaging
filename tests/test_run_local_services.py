"""Unit tests for services._run_local_services with fake service binaries.

Reproduces the pgAdmin node_modules requirement: a mode="manual" service may
legitimately emit an .obscpio archive (node_modules.obscpio) that OBS unpacks
itself at build time.  _run_local_services used to extract and delete every
*.obscpio in the workdir, which would have exploded that archive into ~1400
loose tarballs and dropped it from the upload.  Only Phase-1 (obs_scm)
archives may be extracted.
"""

import shutil
import stat
from pathlib import Path

import pytest

import percona_obs.services as services
from percona_obs.services import _run_local_services

SERVICE_XML = """<services>
  <service name="obs_scm">
    <param name="url">https://example.invalid/foo.git</param>
    <param name="scm">git</param>
    <param name="revision">v1.0</param>
    <param name="filename">foo</param>
  </service>
  <service name="fake_manual" mode="manual">
    <param name="cpio">bar.obscpio</param>
  </service>
</services>
"""

# Fake obs_scm: writes foo.obsinfo (with a commit) and a real cpio archive
# containing foo-1.0/hello.txt into --outdir.
FAKE_OBS_SCM = """#!/bin/sh
set -e
outdir=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--outdir" ]; then outdir="$2"; shift; fi
  shift
done
printf 'name: foo\\nversion: 1.0\\nmtime: 0\\ncommit: %s\\n' "$FAKE_COMMIT" > "$outdir/foo.obsinfo"
tmp=$(mktemp -d)
mkdir -p "$tmp/foo-1.0"
echo hello > "$tmp/foo-1.0/hello.txt"
(cd "$tmp" && find foo-1.0 -depth -print | cpio -o -H newc --quiet) > "$outdir/foo.obscpio"
rm -rf "$tmp"
"""

# Fake manual service: writes bar.obscpio (arbitrary bytes are fine — the
# tool must not open it) and a companion text file into --outdir.
FAKE_MANUAL = """#!/bin/sh
set -e
outdir=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--outdir" ]; then outdir="$2"; shift; fi
  shift
done
printf 'MANUAL-CPIO-BYTES' > "$outdir/bar.obscpio"
printf 'Source10000: x\\n' > "$outdir/bar.spec.inc"
"""

FAIL_IF_RUN = """#!/bin/sh
echo "manual service must not run on a cache hit" >&2
exit 99
"""


def _install(bindir: Path, name: str, body: str) -> None:
    path = bindir / name
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def fake_services(tmp_path, monkeypatch):
    if shutil.which("cpio") is None:
        pytest.skip("cpio not installed")
    bindir = tmp_path / "obs-service"
    bindir.mkdir()
    _install(bindir, "obs_scm", FAKE_OBS_SCM)
    _install(bindir, "fake_manual", FAKE_MANUAL)
    monkeypatch.setattr(services, "_OBS_SERVICE_DIR", bindir)
    monkeypatch.setenv("FAKE_COMMIT", "0123456789abcdef0123456789abcdef01234567")
    # Point every cache tree at tmp so nothing touches the repo's .cache/.
    cache_dir = tmp_path / ".cache"
    for attr, sub in [
        ("_OBS_SCM_CACHE_DIR", "obs_scm"),
        ("_SVC_CACHE_DIR", "services"),
        ("_DOWNLOAD_URL_CACHE_DIR", "download_url"),
        ("_CARGO_VENDOR_CACHE_DIR", "cargo_vendor"),
    ]:
        monkeypatch.setattr(services, attr, cache_dir / sub)
    # No network: the obs_scm cache key lookup must fall through to _run_one.
    monkeypatch.setattr(services, "_git_head_sha", lambda url, rev: None)
    pkg = tmp_path / "pkg"
    obs_dir = pkg / "obs"
    obs_dir.mkdir(parents=True)
    (obs_dir / "_service").write_text(SERVICE_XML)
    return bindir, obs_dir, cache_dir


def test_manual_obscpio_kept_and_obs_scm_obscpio_extracted(fake_services):
    _, obs_dir, _ = fake_services
    workdir = _run_local_services(obs_dir, cache=False)
    try:
        names = sorted(p.name for p in workdir.iterdir())
        assert "bar.obscpio" in names
        assert (workdir / "bar.obscpio").read_bytes() == b"MANUAL-CPIO-BYTES"
        assert "bar.spec.inc" in names
        assert "foo.obscpio" not in names
        assert "foo.obsinfo" in names
        assert not any(p.is_dir() for p in workdir.iterdir())
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_manual_obscpio_kept_on_cache_hit(fake_services):
    bindir, obs_dir, cache_dir = fake_services
    commit = "0123456789abcdef0123456789abcdef01234567"
    entry = cache_dir / "services" / commit
    entry.mkdir(parents=True)
    (entry / "bar.obscpio").write_bytes(b"CACHED-CPIO-BYTES")
    (entry / "bar.spec.inc").write_text("Source10000: cached\n")
    _install(bindir, "fake_manual", FAIL_IF_RUN)

    workdir = _run_local_services(obs_dir, cache=True)
    try:
        assert (workdir / "bar.obscpio").read_bytes() == b"CACHED-CPIO-BYTES"
        assert (workdir / "bar.spec.inc").read_text() == "Source10000: cached\n"
        assert not (workdir / "foo.obscpio").exists()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
