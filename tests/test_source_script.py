"""Unit tests for tools/obs-services/source_script.

The service runs a package's script on an obs_scm checkout and packs the
directory the script produces into a reproducible tarball.  The checkout is a
small fake tree; no network is used.  The tests pass with or without a usable
bubblewrap: the scripts only touch the directories the service gives them.
"""

import gzip
import importlib.machinery
import importlib.util
import io
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from percona_obs import services

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = REPO_ROOT / "tools" / "obs-services" / "source_script"

COMMIT = "7aeba299c49abd768ca741506569007a5cab0870"
MTIME = 1794787200


def _load_service():
    loader = importlib.machinery.SourceFileLoader("source_script", str(SERVICE_PATH))
    spec = importlib.util.spec_from_loader("source_script", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


svc = _load_service()

# Copies the checkout into the output directory and adds a generated file, the
# way a dist step bakes generated sources into a tarball.
DIST_SCRIPT = """#!/bin/sh
set -eu
mkdir "$OUT_DIR/foo-$VERSION"
cp -R . "$OUT_DIR/foo-$VERSION/"
echo "generated for $NAME $VERSION at $SOURCE_DATE_EPOCH" > "$OUT_DIR/foo-$VERSION/generated.txt"
"""


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    """A service work directory holding a source archive and its .obsinfo."""
    work = tmp_path / "work"
    work.mkdir()
    tree = tmp_path / "tree" / "percona-foo-1.2.3"
    (tree / "src").mkdir(parents=True)
    (tree / "src" / "main.c").write_text("int main(void) { return 0; }\n")
    (tree / "configure").write_text("#!/bin/sh\n")
    (tree / "configure").chmod(0o775)
    with tarfile.open(work / "percona-foo-1.2.3.tar.gz", "w:gz") as tar:
        tar.add(tree, arcname=tree.name)
    (work / "percona-foo.obsinfo").write_text(
        f"name: percona-foo\nversion: 1.2.3\nmtime: {MTIME}\ncommit: {COMMIT}\n"
    )
    (tmp_path / "out").mkdir()
    monkeypatch.chdir(work)
    return work


def _script(pkg, text=DIST_SCRIPT, name="dist.sh"):
    (pkg / name).write_text(text)
    return name


def _run(pkg, tmp_path, *extra, script="dist.sh"):
    out = tmp_path / "out"
    rc = svc.main(
        [
            "--archive",
            "percona-foo*.tar.gz",
            "--script",
            script,
            "--outdir",
            str(out),
            *extra,
        ]
    )
    assert rc == 0
    return out


def _members(tarball):
    with tarfile.open(tarball) as tar:
        return {m.name: m for m in tar.getmembers()}


def test_packs_the_directory_the_script_produced(pkg, tmp_path):
    _script(pkg)
    out = _run(pkg, tmp_path)

    assert [p.name for p in out.iterdir()] == ["percona-foo-1.2.3.tar.gz"]
    members = _members(out / "percona-foo-1.2.3.tar.gz")
    assert set(members) == {
        "foo-1.2.3",
        "foo-1.2.3/configure",
        "foo-1.2.3/generated.txt",
        "foo-1.2.3/src",
        "foo-1.2.3/src/main.c",
    }
    with tarfile.open(out / "percona-foo-1.2.3.tar.gz") as tar:
        generated = tar.extractfile("foo-1.2.3/generated.txt")
        assert generated is not None
        assert generated.read().decode() == (
            f"generated for percona-foo 1.2.3 at {MTIME}\n"
        )


def test_output_name_can_be_given(pkg, tmp_path):
    _script(pkg)
    out = _run(pkg, tmp_path, "--output", "foo-dist.tar.gz")
    assert [p.name for p in out.iterdir()] == ["foo-dist.tar.gz"]


def test_tarball_metadata_is_normalised(pkg, tmp_path):
    _script(pkg)
    members = _members(_run(pkg, tmp_path) / "percona-foo-1.2.3.tar.gz")

    assert {m.mtime for m in members.values()} == {MTIME}
    assert {(m.uid, m.gid, m.uname, m.gname) for m in members.values()} == {
        (0, 0, "", "")
    }
    assert members["foo-1.2.3"].mode == 0o755
    assert members["foo-1.2.3/configure"].mode == 0o755
    assert members["foo-1.2.3/src/main.c"].mode == 0o644
    assert list(members) == sorted(members)


def test_same_input_gives_the_same_bytes(pkg, tmp_path):
    _script(pkg)
    first = (_run(pkg, tmp_path) / "percona-foo-1.2.3.tar.gz").read_bytes()
    second = (_run(pkg, tmp_path) / "percona-foo-1.2.3.tar.gz").read_bytes()
    assert first == second
    # No local timestamp or file name in the gzip header either
    with gzip.GzipFile(fileobj=io.BytesIO(first)) as gz:
        gz.read(1)
        assert gz.mtime == 0


def test_script_sees_only_the_documented_environment(pkg, tmp_path, monkeypatch):
    monkeypatch.setenv("OBS_PASSWORD", "hunter2")
    monkeypatch.setenv("GH_TOKEN", "ghp_secret")
    _script(
        pkg,
        '#!/bin/sh\nset -eu\nmkdir "$OUT_DIR/d"\n'
        'env | sort > "$OUT_DIR/d/env"\npwd > "$OUT_DIR/d/cwd"\n',
    )
    out = _run(pkg, tmp_path)

    with tarfile.open(out / "percona-foo-1.2.3.tar.gz") as tar:
        env_file, cwd_file = tar.extractfile("d/env"), tar.extractfile("d/cwd")
        assert env_file is not None and cwd_file is not None
        env = dict(line.split("=", 1) for line in env_file.read().decode().splitlines())
        cwd = cwd_file.read().decode().strip()

    for shell_var in ("PWD", "OLDPWD", "SHLVL", "_"):  # set by the shell itself
        env.pop(shell_var, None)
    assert set(env) == {
        "COMMIT",
        "HOME",
        "LANG",
        "LC_ALL",
        "NAME",
        "OUT_DIR",
        "PATH",
        "SOURCE_DATE_EPOCH",
        "SRC_DIR",
        "TZ",
        "VERSION",
    }
    assert env["COMMIT"] == COMMIT
    assert env["SOURCE_DATE_EPOCH"] == str(MTIME)
    assert env["TZ"] == "UTC"
    assert cwd == env["SRC_DIR"]
    assert cwd.endswith("/src/percona-foo-1.2.3")


def test_runs_without_a_sandbox_and_says_so(pkg, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(svc.shutil, "which", lambda _name: None)
    _script(pkg)
    out = _run(pkg, tmp_path)
    assert (out / "percona-foo-1.2.3.tar.gz").is_file()
    assert "no usable bwrap sandbox" in capsys.readouterr().err


def test_obscpio_archive_is_unpacked(pkg, tmp_path):
    if shutil.which("cpio") is None:
        pytest.skip("cpio not installed")
    (pkg / "percona-foo-1.2.3.tar.gz").unlink()
    tree_root = tmp_path / "tree"
    names = sorted(str(p.relative_to(tree_root)) for p in tree_root.rglob("*"))
    with (pkg / "percona-foo-1.2.3.obscpio").open("wb") as fh:
        subprocess.run(
            ["cpio", "--create", "--format=newc", "--quiet"],
            input="\n".join(names).encode(),
            stdout=fh,
            cwd=tree_root,
            check=True,
        )
    _script(pkg)
    out = tmp_path / "out"
    assert (
        svc.main(
            [
                "--archive",
                "percona-foo*.obscpio",
                "--script",
                "dist.sh",
                "--outdir",
                str(out),
            ]
        )
        == 0
    )
    assert "foo-1.2.3/src/main.c" in _members(out / "percona-foo-1.2.3.tar.gz")


# --- failures -----------------------------------------------------------------


def _fails(pkg, tmp_path, capsys, *args):
    with pytest.raises(SystemExit) as exc:
        svc.main([*args, "--outdir", str(tmp_path / "out")])
    assert exc.value.code == 1
    assert not list((tmp_path / "out").iterdir())
    return capsys.readouterr().err


def test_failing_script_fails_the_service_with_its_output(pkg, tmp_path, capsys):
    _script(pkg, "#!/bin/sh\necho 'release 2.60.0 must have an end commit'\nexit 3\n")
    err = _fails(
        pkg, tmp_path, capsys, "--archive", "percona-foo*.tar.gz", "--script", "dist.sh"
    )
    assert "dist.sh exited with 3" in err
    assert "release 2.60.0 must have an end commit" in err


@pytest.mark.parametrize(
    "body",
    [
        "true\n",
        'mkdir "$OUT_DIR/a" "$OUT_DIR/b"; touch "$OUT_DIR/a/f" "$OUT_DIR/b/f"\n',
        'touch "$OUT_DIR/file"\n',
        'mkdir "$OUT_DIR/empty"\n',
    ],
)
def test_output_must_be_one_non_empty_directory(pkg, tmp_path, capsys, body):
    _script(pkg, "#!/bin/sh\n" + body)
    err = _fails(
        pkg, tmp_path, capsys, "--archive", "percona-foo*.tar.gz", "--script", "dist.sh"
    )
    assert "OUT_DIR" in err


def test_script_must_be_a_file_of_the_package(pkg, tmp_path, capsys):
    err = _fails(
        pkg,
        tmp_path,
        capsys,
        "--archive",
        "percona-foo*.tar.gz",
        "--script",
        "../dist.sh",
    )
    assert "must be a file name" in err
    err = _fails(
        pkg, tmp_path, capsys, "--archive", "percona-foo*.tar.gz", "--script", "nope.sh"
    )
    assert "not found" in err


def test_archive_needs_its_obsinfo(pkg, tmp_path, capsys):
    (pkg / "percona-foo.obsinfo").unlink()
    _script(pkg)
    err = _fails(
        pkg, tmp_path, capsys, "--archive", "percona-foo*.tar.gz", "--script", "dist.sh"
    )
    assert ".obsinfo" in err


def test_archive_glob_must_match_one_file(pkg, tmp_path, capsys):
    _script(pkg)
    err = _fails(pkg, tmp_path, capsys, "--archive", "nothing*", "--script", "dist.sh")
    assert "no file matches" in err


# --- percona_obs.services: cache key of manual-service outputs ----------------


def _manual(script="dist.sh"):
    return ET.fromstring(
        '<service name="source_script" mode="manual">'
        '<param name="archive">percona-foo*.obscpio</param>'
        f'<param name="script">{script}</param></service>'
    )


def test_manual_cache_key_follows_the_script_content(tmp_path):
    obs = tmp_path / "obs"
    obs.mkdir()
    (obs / "_service").write_text("<services/>")
    (obs / "dist.sh").write_text("#!/bin/sh\necho one\n")
    key = services._manual_cache_key(COMMIT, [_manual()], obs)

    assert key.startswith(f"{COMMIT}-")
    assert key == services._manual_cache_key(COMMIT, [_manual()], obs)

    (obs / "dist.sh").write_text("#!/bin/sh\necho two\n")
    assert services._manual_cache_key(COMMIT, [_manual()], obs) != key


def test_manual_cache_key_follows_the_service_params_not_the_service_file(tmp_path):
    obs = tmp_path / "obs"
    obs.mkdir()
    (obs / "_service").write_text("<services/>")
    (obs / "dist.sh").write_text("#!/bin/sh\n")
    key = services._manual_cache_key(COMMIT, [_manual()], obs)

    # _service also carries what does not affect the manual outputs
    (obs / "_service").write_text("<services><!-- changed --></services>")
    assert services._manual_cache_key(COMMIT, [_manual()], obs) == key
    assert services._manual_cache_key(COMMIT, [_manual("other.sh")], obs) != key
    assert services._manual_cache_key("0" * 40, [_manual()], obs) != key
