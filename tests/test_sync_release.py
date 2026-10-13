"""Unit tests for the sync release subproject handling (percona_obs.cmd_sync).

collect_release_subprojects maps source subprojects to release mirrors;
cmd_sync_release must hard-error on missing mirrors.  OBS interaction is
monkeypatched out.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import percona_obs.cmd_sync as cmd_sync
import percona_obs.release_copy as rc
from percona_obs.release_copy import collect_release_subprojects

_REPO_YAML = "repositories:\n  - name: {name}\n    archs: [x86_64]\n    paths: []\n"


def _mk_tree(tmp_path: Path, monkeypatch=None):
    """staging tree with containers (ubi9 repo) + tarballs (ssl3 repo); release tree mirrors only containers."""
    root = tmp_path / "root"
    (root / "macros.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "macros.yaml").write_text("- M: 1\n")
    (root / "project.yaml").write_text(_REPO_YAML.format(name="RockyLinux_9"))
    src = root / "ppg/staging/17"
    (src / "containers").mkdir(parents=True)
    (src / "containers" / "project.yaml").write_text(
        "repositories-inherit: false\n" + _REPO_YAML.format(name="ubi9")
    )
    (src / "tarballs").mkdir()
    (src / "tarballs" / "project.yaml").write_text(
        "repositories-inherit: false\n" + _REPO_YAML.format(name="ssl3")
    )
    (src / "project.yaml").write_text("title: S\n")
    rel = root / "ppg/releases/17"
    (rel / "containers").mkdir(parents=True)
    (rel / "containers" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ubi9")
    )
    (rel / "release.yaml").write_text(
        "project: ppg:staging:17\nreleases: [ppg/17.11-1]\n"
    )
    (root / "ppg/releases/subprojects.yaml").write_text("standalone: true\n")
    if monkeypatch is not None:
        import percona_obs.common as common

        monkeypatch.setattr(common, "REPO_ROOT", root)
    return src, rel


def test_collect_pairs_and_missing(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    monkeypatch.setattr(rc, "resolve_project_path", lambda pid: src)
    pairs, missing = collect_release_subprojects("ppg:staging:17", rel)
    assert [name for name, _ in pairs] == ["containers"]
    assert missing == ["tarballs"]


class _Args:
    """Minimal args namespace matching what cmd_sync_release touches."""

    def __init__(self, project, rootprj, no_freeze=False, verify_timeout=600):
        self.project = project
        self.force = False
        self.skip_tag_check = True
        self.no_freeze = no_freeze
        self.freeze_timeout = 1
        self.verify_timeout = verify_timeout
        self.profile = None
        self.rootprj = rootprj
        self.env_overrides = None
        self.message = None
        self.from_project = None


def _wire_release_update_path(monkeypatch, src, rel):
    """Stub every OBS/osc touchpoint cmd_sync_release hits on the update
    (project-exists) path, so the test only exercises the freeze wiring."""
    monkeypatch.setattr(
        cmd_sync,
        "resolve_project_path",
        lambda pid: src if pid == "ppg:staging:17" else rel,
    )
    monkeypatch.setattr(
        rc, "resolve_project_path", lambda pid: src if pid == "ppg:staging:17" else rel
    )
    monkeypatch.setattr(cmd_sync, "_REPO_DIR", rel.parents[2])
    monkeypatch.setattr(cmd_sync.osc.conf, "config", {"apiurl": "http://obs"})
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda *a, **k: True)
    monkeypatch.setattr(rc, "_apply_project_config", lambda *a, **k: (False, None))
    monkeypatch.setattr(rc, "_disable_project_builds", lambda *a, **k: None)
    monkeypatch.setattr(rc, "_read_project_release_source", lambda *a, **k: ([], None))
    monkeypatch.setattr(
        rc, "filter_release_repo_names", lambda apiurl, names, target: names
    )
    monkeypatch.setattr(rc, "_add_release_targets", lambda *a, **k: None)
    monkeypatch.setattr(rc, "_remove_release_targets", lambda *a, **k: None)
    monkeypatch.setattr(rc, "_fetch_obs_subproject_names", lambda apiurl, prefix: set())


def test_missing_mirror_is_hard_error(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    _wire_release_update_path(monkeypatch, src, rel)
    args = _Args(project="ppg:releases:17", rootprj="home:Admin")
    with pytest.raises(SystemExit, match="tarballs"):
        cmd_sync.cmd_sync_release(args)


def test_freeze_order_and_restore_on_failure(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ssl3")
    )
    _wire_release_update_path(monkeypatch, src, rel)

    calls = []
    monkeypatch.setattr(
        cmd_sync, "wait_for_quiesce", lambda *a, **k: calls.append("drain")
    )
    monkeypatch.setattr(
        cmd_sync, "assert_all_green", lambda *a, **k: calls.append("green") or []
    )
    monkeypatch.setattr(
        cmd_sync,
        "freeze_builds",
        lambda *a, **k: calls.append("freeze") or {"p": "<x/>"},
    )
    monkeypatch.setattr(
        cmd_sync, "restore_builds", lambda *a, **k: calls.append("restore")
    )
    monkeypatch.setattr(rc, "verify_release_landed", lambda *a, **k: None)

    def boom(*a, **k):
        calls.append("release")
        raise RuntimeError("osc failed")

    monkeypatch.setattr(rc.subprocess, "run", boom)

    args = _Args(project="ppg:releases:17", rootprj="home:Admin")

    with pytest.raises(RuntimeError):
        cmd_sync.cmd_sync_release(args)

    assert calls[:3] == ["drain", "green", "freeze"]
    assert calls[-1] == "restore"


def test_red_staging_aborts_before_freeze(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ssl3")
    )
    _wire_release_update_path(monkeypatch, src, rel)

    freeze_called = []
    monkeypatch.setattr(cmd_sync, "wait_for_quiesce", lambda *a, **k: None)
    monkeypatch.setattr(
        cmd_sync, "assert_all_green", lambda *a, **k: ["p/pkg repo/x86_64: failed"]
    )
    monkeypatch.setattr(
        cmd_sync, "freeze_builds", lambda *a, **k: freeze_called.append(1) or {}
    )
    monkeypatch.setattr(cmd_sync, "restore_builds", lambda *a, **k: None)
    monkeypatch.setattr(rc, "verify_release_landed", lambda *a, **k: None)
    monkeypatch.setattr(
        rc.subprocess,
        "run",
        lambda *a, **k: pytest.fail("osc release must not run"),
    )

    args = _Args(project="ppg:releases:17", rootprj="home:Admin")

    with pytest.raises(SystemExit, match="not fully green"):
        cmd_sync.cmd_sync_release(args)

    assert freeze_called == []


def test_no_freeze_skips_gate_but_verifies(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ssl3")
    )
    _wire_release_update_path(monkeypatch, src, rel)

    def fail_if_called(*a, **k):
        pytest.fail("drain/green/freeze must be skipped with --no-freeze")

    monkeypatch.setattr(cmd_sync, "wait_for_quiesce", fail_if_called)
    monkeypatch.setattr(cmd_sync, "assert_all_green", fail_if_called)
    monkeypatch.setattr(cmd_sync, "freeze_builds", fail_if_called)
    monkeypatch.setattr(cmd_sync, "restore_builds", lambda *a, **k: None)
    monkeypatch.setattr(rc.subprocess, "run", lambda *a, **k: None)

    verified = []
    monkeypatch.setattr(
        rc,
        "verify_release_landed",
        lambda apiurl, src_prj, rel_prj, timeout_s=600: verified.append(
            (src_prj, rel_prj)
        ),
    )

    args = _Args(
        project="ppg:releases:17",
        rootprj="home:Admin",
        no_freeze=True,
        verify_timeout=5,
    )

    cmd_sync.cmd_sync_release(args)

    assert ("home:Admin:ppg:staging:17", "home:Admin:ppg:releases:17") in verified
    assert (
        "home:Admin:ppg:staging:17:containers",
        "home:Admin:ppg:releases:17:containers",
    ) in verified
    assert (
        "home:Admin:ppg:staging:17:tarballs",
        "home:Admin:ppg:releases:17:tarballs",
    ) in verified


def _wire_release_first_path(monkeypatch, src, rel):
    """Stub every OBS/osc touchpoint cmd_sync_release hits on the first-release
    (project-does-not-exist) path."""
    monkeypatch.setattr(
        cmd_sync,
        "resolve_project_path",
        lambda pid: src if pid == "ppg:staging:17" else rel,
    )
    monkeypatch.setattr(
        rc, "resolve_project_path", lambda pid: src if pid == "ppg:staging:17" else rel
    )
    monkeypatch.setattr(cmd_sync, "_REPO_DIR", rel.parents[2])
    monkeypatch.setattr(cmd_sync.osc.conf, "config", {"apiurl": "http://obs"})
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda *a, **k: False)
    monkeypatch.setattr(cmd_sync, "_create_release_project", lambda *a, **k: [])
    monkeypatch.setattr(cmd_sync, "_copy_project_conf", lambda *a, **k: None)
    monkeypatch.setattr(rc, "_apply_project_config", lambda *a, **k: (False, None))
    monkeypatch.setattr(rc, "_disable_project_builds", lambda *a, **k: None)
    monkeypatch.setattr(rc, "_read_project_release_source", lambda *a, **k: ([], None))
    monkeypatch.setattr(
        rc, "filter_release_repo_names", lambda apiurl, names, target: names
    )
    monkeypatch.setattr(rc, "_add_release_targets", lambda *a, **k: None)
    monkeypatch.setattr(rc, "_remove_release_targets", lambda *a, **k: None)
    monkeypatch.setattr(rc, "_fetch_obs_subproject_names", lambda apiurl, prefix: set())


def test_first_release_does_not_shell_out_to_dry_run_sync(tmp_path, monkeypatch):
    """The first-release path must not run a `sync push --dry-run` subprocess
    to validate OBS-level divergence; only `osc release` may be invoked."""
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ssl3")
    )
    _wire_release_first_path(monkeypatch, src, rel)

    monkeypatch.setattr(cmd_sync, "wait_for_quiesce", lambda *a, **k: None)
    monkeypatch.setattr(cmd_sync, "assert_all_green", lambda *a, **k: [])
    monkeypatch.setattr(cmd_sync, "freeze_builds", lambda *a, **k: {})
    monkeypatch.setattr(cmd_sync, "restore_builds", lambda *a, **k: None)
    monkeypatch.setattr(rc, "verify_release_landed", lambda *a, **k: None)

    run_calls = []

    def fake_run(cmd, *a, **k):
        run_calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(rc.subprocess, "run", fake_run)

    args = _Args(project="ppg:releases:17", rootprj="home:Admin")

    cmd_sync.cmd_sync_release(args)

    assert not any("push" in cmd for cmd in run_calls)
    assert any("release" in cmd for cmd in run_calls)


def _dry_run_args(project="ppg:releases:17"):
    return SimpleNamespace(
        project=project,
        rootprj="home:Admin",
        env_overrides=None,
        profile=None,
        force=False,
        skip_tag_check=False,
        dry_run=True,
        no_freeze=False,
        freeze_timeout=1,
        verify_timeout=0,
        message=None,
    )


def _patch_dry_run_common(monkeypatch, tmp_path, src, rel):
    monkeypatch.setattr(
        cmd_sync,
        "resolve_project_path",
        lambda pid: rel if "releases" in pid else src,
    )
    monkeypatch.setattr(cmd_sync, "_REPO_DIR", tmp_path)
    monkeypatch.setattr(cmd_sync.osc.conf, "config", {"apiurl": "http://obs"})


def test_dry_run_reports_all_failures(tmp_path, monkeypatch, capsys):
    src, rel = _mk_tree(
        tmp_path, monkeypatch
    )  # tarballs mirror missing by construction
    (rel / "CHANGELOG.md").write_text("# Changelog\n")  # no release section
    _patch_dry_run_common(monkeypatch, tmp_path, src, rel)
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda a, p: False)
    monkeypatch.setattr(cmd_sync, "assert_all_green", lambda a, p, **k: [])
    monkeypatch.setattr(
        cmd_sync.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
    )
    with pytest.raises(SystemExit, match="dry-run failed"):
        cmd_sync.cmd_sync_release(_dry_run_args())
    err = capsys.readouterr().err
    assert "missing release mirror" in err and "tarballs" in err
    assert "## [17.11-1]" in err
    assert "not found on OBS" in err


def test_dry_run_passes_when_clean(tmp_path, monkeypatch, capsys):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ssl3")
    )
    (rel / "CHANGELOG.md").write_text("# Changelog\n\n## [17.11-1] - 2026-09-03\n")
    _patch_dry_run_common(monkeypatch, tmp_path, src, rel)
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda a, p: True)
    monkeypatch.setattr(cmd_sync, "assert_all_green", lambda a, p, **k: [])
    monkeypatch.setattr(
        cmd_sync.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
    )
    cmd_sync.cmd_sync_release(_dry_run_args())
    assert "dry-run passed" in capsys.readouterr().out


def test_filter_release_repo_names_warns_and_drops(monkeypatch, capsys):
    monkeypatch.setattr(
        rc,
        "_fetch_obs_project_repository_names",
        lambda apiurl, prj: {"RockyLinux_9", "Debian_13"},
    )
    kept = rc.filter_release_repo_names(
        "http://obs", ["RockyLinux_9", "UBI_9", "Debian_13"], "x:rel"
    )
    assert kept == ["RockyLinux_9", "Debian_13"]
    assert "UBI_9 has no counterpart" in capsys.readouterr().out


def test_collect_release_subprojects_respects_slice(tmp_path, monkeypatch):
    import percona_obs.common as common
    from percona_obs.project_config import RepositoryFilter

    src, rel = _mk_tree(tmp_path, monkeypatch)
    monkeypatch.setattr(rc, "resolve_project_path", lambda pid: src)
    try:
        # boo: containers is out of slice (mirror and source) → not a pair, not missing;
        # tarballs is in slice on boo and has no mirror → missing
        common.set_default_repository_filter(RepositoryFilter(exclude_repos=("ubi*",)))
        pairs, missing = collect_release_subprojects("ppg:staging:17", rel)
        assert pairs == [] and missing == ["tarballs"]
        # labs: containers released, tarballs is out of slice → not missing
        common.set_default_repository_filter(RepositoryFilter(include_repos=("ubi*",)))
        pairs, missing = collect_release_subprojects("ppg:staging:17", rel)
        assert [n for n, _ in pairs] == ["containers"] and missing == []
    finally:
        common.set_default_repository_filter(None)


def test_build_freeze_scope_merges_extra_sources(tmp_path, monkeypatch):
    import percona_obs.release_scope as rs

    src, rel = _mk_tree(tmp_path, monkeypatch)
    monkeypatch.setattr(
        cmd_sync,
        "collect_release_scope",
        lambda *a, **k: rs.ReleaseScope(
            whole_projects=["home:Admin:ppg:staging:18"],
            packages={
                "home:Admin:ppg:staging:common:tools": {"percona-pgbouncer"},
                "home:Admin:ppg:staging:18": {"ignored-because-whole"},
            },
        ),
    )
    whole, packages = cmd_sync._build_freeze_scope(
        "home:Admin:ppg:staging:17",
        ["home:Admin:ppg:staging:17:containers"],
        src,
        "ppg:staging:17",
        "home:Admin",
        {},
    )
    assert whole == [
        "home:Admin:ppg:staging:17",
        "home:Admin:ppg:staging:17:containers",
        "home:Admin:ppg:staging:18",
    ]
    assert packages == {"home:Admin:ppg:staging:common:tools": {"percona-pgbouncer"}}


def _args_from(rel, **kw):
    a = _Args(project="ppg:releases:17", rootprj="home:Admin")
    a.from_project = "home:Admin:PR:pr-5:ppg:releases:17"
    a.__dict__.update(kw)
    return a


def _mapping_release_yaml(rel, sha="b" * 40):
    (rel / "release.yaml").write_text(
        f"project: ppg:staging:17\nreleases:\n  - tag: ppg/17.11-1\n    source_commit: {sha}\n"
    )


def test_from_prerelease_skips_freeze_and_copies_from_it(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ssl3")
    )
    _mapping_release_yaml(rel)
    _wire_release_update_path(monkeypatch, src, rel)
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda *a, **k: False)
    monkeypatch.setattr(
        cmd_sync, "read_project_description_marker", lambda a, p, k: "b" * 40
    )
    fail = lambda *a, **k: pytest.fail("freeze must be skipped with --from")
    monkeypatch.setattr(cmd_sync, "wait_for_quiesce", fail)
    monkeypatch.setattr(cmd_sync, "freeze_builds", fail)
    monkeypatch.setattr(cmd_sync, "_create_release_project", fail)
    metas, copies = [], []
    monkeypatch.setattr(
        cmd_sync, "apply_mirror_meta", lambda a, prj, *r, **k: metas.append(prj)
    )
    monkeypatch.setattr(
        cmd_sync, "release_tree", lambda a, s, t, *r, **k: copies.append((s, t))
    )
    cmd_sync.cmd_sync_release(_args_from(rel))
    assert metas == ["home:Admin:ppg:releases:17"]
    assert copies == [
        ("home:Admin:PR:pr-5:ppg:releases:17", "home:Admin:ppg:releases:17")
    ]


def test_from_prerelease_marker_mismatch(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ssl3")
    )
    _mapping_release_yaml(rel)
    _wire_release_update_path(monkeypatch, src, rel)
    monkeypatch.setattr(
        cmd_sync, "read_project_description_marker", lambda a, p, k: "c" * 40
    )
    monkeypatch.setattr(
        cmd_sync,
        "apply_mirror_meta",
        lambda *a, **k: pytest.fail("no meta on mismatch"),
    )
    monkeypatch.setattr(
        cmd_sync, "release_tree", lambda *a, **k: pytest.fail("no copy on mismatch")
    )
    with pytest.raises(SystemExit, match="source_commit mismatch"):
        cmd_sync.cmd_sync_release(_args_from(rel))


def _bare_tag_setup(tmp_path, monkeypatch):
    src, rel = _mk_tree(tmp_path, monkeypatch)
    (rel / "tarballs").mkdir()
    (rel / "tarballs" / "project.yaml").write_text(
        "build: false\n" + _REPO_YAML.format(name="ssl3")
    )
    (rel / "release.yaml").write_text(
        "project: ppg:staging:17\nreleases:\n  - ppg/17.11-1\n"
    )
    _wire_release_update_path(monkeypatch, src, rel)
    monkeypatch.setattr(cmd_sync, "_obs_project_exists", lambda *a, **k: False)
    monkeypatch.setattr(
        cmd_sync, "read_project_description_marker", lambda a, p, k: None
    )
    return rel


def test_from_prerelease_bare_tag_entry_refused(tmp_path, monkeypatch):
    rel = _bare_tag_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        cmd_sync, "apply_mirror_meta", lambda *a, **k: pytest.fail("no meta")
    )
    monkeypatch.setattr(
        cmd_sync, "release_tree", lambda *a, **k: pytest.fail("no copy")
    )
    with pytest.raises(SystemExit, match="has no source_commit"):
        cmd_sync.cmd_sync_release(_args_from(rel))


def test_from_prerelease_force_skips_provenance_checks(tmp_path, monkeypatch):
    rel = _bare_tag_setup(tmp_path, monkeypatch)
    metas, copies = [], []
    monkeypatch.setattr(
        cmd_sync, "apply_mirror_meta", lambda a, prj, *r, **k: metas.append(prj)
    )
    monkeypatch.setattr(
        cmd_sync, "release_tree", lambda a, s, t, *r, **k: copies.append((s, t))
    )
    cmd_sync.cmd_sync_release(_args_from(rel, force=True))
    assert len(metas) == 1 and len(copies) == 1
