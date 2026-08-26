"""Unit tests for tools/obs-services/npm_lockfile.

The service generates package-lock.json from an upstream source archive so
the OBS node_modules service can vendor npm dependencies.  npm itself is
replaced by a fake executable put first on PATH; it records its argv, cwd and
npm_config_* environment, writes a lockfile, and exits with a configurable
status.  cpio is used for real when available (skipped otherwise).
"""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = REPO_ROOT / "tools" / "obs-services" / "npm_lockfile"


def _load_service():
    loader = importlib.machinery.SourceFileLoader("npm_lockfile", str(SERVICE_PATH))
    spec = importlib.util.spec_from_loader("npm_lockfile", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


svc = _load_service()

FAKE_NPM = """#!/bin/sh
printf '%s\\n' "$@" > "$NPM_FAKE_LOG"
pwd >> "$NPM_FAKE_LOG"
env | grep '^npm_config_' | sort >> "$NPM_FAKE_LOG"
printf '{"name":"web","lockfileVersion":%s,"packages":{}}' "${NPM_FAKE_LOCKVER:-3}" > package-lock.json
exit "${NPM_FAKE_EXIT:-0}"
"""


@pytest.fixture
def fake_npm(tmp_path, monkeypatch):
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    npm = bindir / "npm"
    npm.write_text(FAKE_NPM)
    npm.chmod(npm.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "npm.log"
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("NPM_FAKE_LOG", str(log))
    monkeypatch.delenv("NPM_FAKE_EXIT", raising=False)
    monkeypatch.delenv("NPM_FAKE_LOCKVER", raising=False)
    return log


def _source_tree(root, top="pgadmin4-9.9", subdir="web", with_package_json=True):
    pkg = root / top / subdir
    pkg.mkdir(parents=True)
    if with_package_json:
        (pkg / "package.json").write_text('{"name": "web", "version": "1.0.0"}')
    (root / top / "README.md").write_text("upstream\n")
    return root / top


def _tar_gz(src_root, top, dest):
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(src_root / top, arcname=top)
    return dest


def _obscpio(src_root, top, dest):
    if shutil.which("cpio") is None:
        pytest.skip("cpio not installed")
    files = subprocess.run(
        ["find", top, "-depth", "-print"],
        cwd=src_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    with open(dest, "wb") as fh:
        subprocess.run(
            ["cpio", "-o", "-H", "newc", "--quiet"],
            cwd=src_root,
            input=files.encode(),
            stdout=fh,
            check=True,
        )
    return dest


def _run(workdir, outdir, *extra):
    argv = ["--archive", "*.tar.gz", "--subdir", "web", "--outdir", str(outdir)]
    argv += list(extra)
    cwd = os.getcwd()
    os.chdir(workdir)
    try:
        return svc.main(argv)
    finally:
        os.chdir(cwd)


def test_tar_gz_archive_produces_lockfile_in_outdir(tmp_path, fake_npm):
    src = tmp_path / "src"
    _source_tree(src)
    work = tmp_path / "work"
    work.mkdir()
    _tar_gz(src, "pgadmin4-9.9", work / "percona-pgadmin4-9.9.tar.gz")
    outdir = tmp_path / "out"
    outdir.mkdir()

    assert _run(work, outdir) == 0

    lock = json.loads((outdir / "package-lock.json").read_text())
    assert lock["lockfileVersion"] == 3
    assert sorted(p.name for p in outdir.iterdir()) == ["package-lock.json"]


def test_npm_invocation_argv_cwd_and_env(tmp_path, fake_npm):
    src = tmp_path / "src"
    _source_tree(src)
    work = tmp_path / "work"
    work.mkdir()
    _tar_gz(src, "pgadmin4-9.9", work / "percona-pgadmin4-9.9.tar.gz")
    outdir = tmp_path / "out"
    outdir.mkdir()

    _run(work, outdir)

    lines = fake_npm.read_text().splitlines()
    assert lines[:4] == [
        "install",
        "--package-lock-only",
        "--legacy-peer-deps",
        "--ignore-scripts",
    ]
    cwd_line = lines[4]
    assert cwd_line.endswith(os.path.join("pgadmin4-9.9", "web"))
    env_lines = lines[5:]
    assert "npm_config_audit=false" in env_lines
    assert "npm_config_fund=false" in env_lines
    assert "npm_config_update_notifier=false" in env_lines
    cache_line = next(l for l in env_lines if l.startswith("npm_config_cache="))
    cache_dir = cache_line.split("=", 1)[1]
    assert cache_dir != str(Path.home() / ".npm")
    assert not Path(cache_dir).exists(), "temporary npm cache must be removed"


def test_npm_flags_param_replaces_defaults(tmp_path, fake_npm):
    src = tmp_path / "src"
    _source_tree(src)
    work = tmp_path / "work"
    work.mkdir()
    _tar_gz(src, "pgadmin4-9.9", work / "percona-pgadmin4-9.9.tar.gz")
    outdir = tmp_path / "out"
    outdir.mkdir()

    _run(work, outdir, "--npm-flags", "--ignore-scripts --foo")

    lines = fake_npm.read_text().splitlines()
    assert lines[:4] == ["install", "--package-lock-only", "--ignore-scripts", "--foo"]


def test_obscpio_archive_is_unpacked_with_cpio(tmp_path, fake_npm):
    src = tmp_path / "src"
    _source_tree(src)
    work = tmp_path / "work"
    work.mkdir()
    _obscpio(src, "pgadmin4-9.9", work / "percona-pgadmin4.obscpio")
    outdir = tmp_path / "out"
    outdir.mkdir()

    cwd = os.getcwd()
    os.chdir(work)
    try:
        rc = svc.main(
            ["--archive", "*.obscpio", "--subdir", "web", "--outdir", str(outdir)]
        )
    finally:
        os.chdir(cwd)

    assert rc == 0
    assert (outdir / "package-lock.json").is_file()


def test_archive_glob_zero_matches_fails(tmp_path, fake_npm, capsys):
    work = tmp_path / "work"
    work.mkdir()
    outdir = tmp_path / "out"
    outdir.mkdir()
    with pytest.raises(SystemExit) as exc:
        _run(work, outdir)
    assert exc.value.code == 1
    assert "no file matches" in capsys.readouterr().err


def test_archive_glob_multiple_matches_fails(tmp_path, fake_npm, capsys):
    src = tmp_path / "src"
    _source_tree(src)
    work = tmp_path / "work"
    work.mkdir()
    _tar_gz(src, "pgadmin4-9.9", work / "a-9.9.tar.gz")
    _tar_gz(src, "pgadmin4-9.9", work / "b-9.9.tar.gz")
    outdir = tmp_path / "out"
    outdir.mkdir()
    with pytest.raises(SystemExit) as exc:
        _run(work, outdir)
    assert exc.value.code == 1
    assert "matches 2 files" in capsys.readouterr().err


def test_archive_without_single_top_dir_fails(tmp_path, fake_npm, capsys):
    src = tmp_path / "src"
    _source_tree(src, top="one")
    _source_tree(src, top="two")
    work = tmp_path / "work"
    work.mkdir()
    with tarfile.open(work / "flat-1.0.tar.gz", "w:gz") as tar:
        tar.add(src / "one", arcname="one")
        tar.add(src / "two", arcname="two")
    outdir = tmp_path / "out"
    outdir.mkdir()
    with pytest.raises(SystemExit) as exc:
        _run(work, outdir)
    assert exc.value.code == 1
    assert "exactly one top-level directory" in capsys.readouterr().err


def test_missing_package_json_fails(tmp_path, fake_npm, capsys):
    src = tmp_path / "src"
    _source_tree(src, with_package_json=False)
    work = tmp_path / "work"
    work.mkdir()
    _tar_gz(src, "pgadmin4-9.9", work / "percona-pgadmin4-9.9.tar.gz")
    outdir = tmp_path / "out"
    outdir.mkdir()
    with pytest.raises(SystemExit) as exc:
        _run(work, outdir)
    assert exc.value.code == 1
    assert "package.json" in capsys.readouterr().err


def test_npm_failure_propagates(tmp_path, fake_npm, monkeypatch, capsys):
    monkeypatch.setenv("NPM_FAKE_EXIT", "7")
    src = tmp_path / "src"
    _source_tree(src)
    work = tmp_path / "work"
    work.mkdir()
    _tar_gz(src, "pgadmin4-9.9", work / "percona-pgadmin4-9.9.tar.gz")
    outdir = tmp_path / "out"
    outdir.mkdir()
    with pytest.raises(SystemExit) as exc:
        _run(work, outdir)
    assert exc.value.code == 1
    assert "npm exited with 7" in capsys.readouterr().err
    assert not (outdir / "package-lock.json").exists()


def test_old_lockfile_version_rejected(tmp_path, fake_npm, monkeypatch, capsys):
    monkeypatch.setenv("NPM_FAKE_LOCKVER", "1")
    src = tmp_path / "src"
    _source_tree(src)
    work = tmp_path / "work"
    work.mkdir()
    _tar_gz(src, "pgadmin4-9.9", work / "percona-pgadmin4-9.9.tar.gz")
    outdir = tmp_path / "out"
    outdir.mkdir()
    with pytest.raises(SystemExit) as exc:
        _run(work, outdir)
    assert exc.value.code == 1
    assert "lockfileVersion" in capsys.readouterr().err


def test_npm_missing_from_path_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    (tmp_path / "empty-bin").mkdir()
    src = tmp_path / "src"
    _source_tree(src)
    work = tmp_path / "work"
    work.mkdir()
    _tar_gz(src, "pgadmin4-9.9", work / "percona-pgadmin4-9.9.tar.gz")
    outdir = tmp_path / "out"
    outdir.mkdir()
    with pytest.raises(SystemExit) as exc:
        _run(work, outdir)
    assert exc.value.code == 1
    assert "npm not found" in capsys.readouterr().err


def test_temp_dirs_are_removed(tmp_path, fake_npm, monkeypatch):
    scratch = tmp_path / "tmproot"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    import tempfile

    tempfile.tempdir = None  # make tempfile re-read TMPDIR
    src = tmp_path / "src"
    _source_tree(src)
    work = tmp_path / "work"
    work.mkdir()
    _tar_gz(src, "pgadmin4-9.9", work / "percona-pgadmin4-9.9.tar.gz")
    outdir = tmp_path / "out"
    outdir.mkdir()
    try:
        assert _run(work, outdir) == 0
        assert list(scratch.iterdir()) == []
    finally:
        tempfile.tempdir = None
