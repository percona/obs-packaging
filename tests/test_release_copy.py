"""Unit tests for percona_obs.release_copy (OBS and osc monkeypatched)."""

from pathlib import Path

import pytest

import percona_obs.release_copy as rc


def _stub_obs(monkeypatch, calls):
    monkeypatch.setattr(
        rc, "_read_project_release_source", lambda apiurl, prj: ([], None)
    )
    monkeypatch.setattr(
        rc, "filter_release_repo_names", lambda apiurl, names, target: names
    )
    monkeypatch.setattr(
        rc, "_add_release_targets", lambda *a, **k: calls.append(("add", a[1], a[2]))
    )
    monkeypatch.setattr(
        rc,
        "_remove_release_targets",
        lambda *a, **k: calls.append(("remove", a[1], a[2])),
    )
    monkeypatch.setattr(
        rc,
        "_apply_project_config",
        lambda *a, **k: calls.append(("meta", a[1])) or (False, True),
    )
    monkeypatch.setattr(rc, "_disable_project_builds", lambda *a, **k: None)
    monkeypatch.setattr(rc, "_fetch_obs_subproject_names", lambda apiurl, prefix: set())


def test_copy_project_binaries_restores_targets(monkeypatch):
    calls = []
    _stub_obs(monkeypatch, calls)
    seen = {}
    monkeypatch.setattr(
        rc.subprocess, "run", lambda cmd, **k: seen.setdefault("cmd", cmd)
    )
    rc.copy_project_binaries("http://obs", "S", "T")
    assert "--target-project" not in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("release") + 1] == "S"
    assert calls == [("remove", "S", "T"), ("add", "S", "T"), ("remove", "S", "T")]


def test_copy_project_binaries_restores_on_failure(monkeypatch):
    calls = []
    _stub_obs(monkeypatch, calls)

    def boom(*a, **k):
        raise RuntimeError("osc failed")

    monkeypatch.setattr(rc.subprocess, "run", boom)
    with pytest.raises(RuntimeError):
        rc.copy_project_binaries("http://obs", "S", "T")
    assert calls[-1] == ("remove", "S", "T")


def test_release_tree_order_and_verify(monkeypatch, tmp_path):
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(
        rc.subprocess, "run", lambda cmd, **k: calls.append(("osc", cmd[4]))
    )
    monkeypatch.setattr(
        rc,
        "verify_release_landed",
        lambda apiurl, s, t, timeout_s=600: calls.append(("verify", s, t)),
    )
    pairs = [("containers", tmp_path / "containers")]
    rc.release_tree("http://obs", "S", "T", pairs, "home:Admin", {}, verify_timeout=5)
    assert [c for c in calls if c[0] in ("osc", "meta")] == [
        ("osc", "S"),
        ("meta", "T:containers"),
        ("osc", "S:containers"),
    ]
    assert ("verify", "S", "T") in calls
    assert ("verify", "S:containers", "T:containers") in calls


def test_release_tree_publish_override_reaches_meta(monkeypatch, tmp_path):
    seen = {}
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(
        rc,
        "_apply_project_config",
        lambda *a, **k: (seen.setdefault("publish", k.get("publish_override")), True),
    )
    monkeypatch.setattr(rc.subprocess, "run", lambda *a, **k: None)
    rc.release_tree(
        "http://obs",
        "S",
        "T",
        [("x", tmp_path)],
        "home:Admin",
        {},
        publish_override=True,
        verify_timeout=0,
    )
    assert seen["publish"] is True


def test_warn_orphans(monkeypatch, capsys):
    monkeypatch.setattr(
        rc,
        "_fetch_obs_subproject_names",
        lambda apiurl, prefix: {"T:containers", "T:containers:ubi9"},
    )
    rc.warn_orphans("http://obs", "T", [("containers", Path("/x"))], "home:Admin")
    out = capsys.readouterr().out
    assert "T:containers:ubi9" in out and "sync delete" in out


def test_apply_mirror_meta_forwards_branch_redirection(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(
        rc,
        "_apply_project_config",
        lambda *a, **k: seen.append((k.get("branch_rootprj"), k.get("active_projects")))
        or (False, True),
    )
    monkeypatch.setattr(rc, "_disable_project_builds", lambda *a, **k: None)
    rc.apply_mirror_meta(
        "http://obs",
        "PR:T",
        tmp_path,
        "PR",
        {},
        branch_rootprj="prod",
        active_projects={"PR:T", "PR:T:containers"},
    )
    assert seen == [("prod", {"PR:T", "PR:T:containers"})]


def test_release_tree_forwards_branch_redirection_to_subprojects(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(
        rc,
        "apply_mirror_meta",
        lambda apiurl, prj, path, rootprj, env, **k: seen.append(
            (prj, k.get("branch_rootprj"), k.get("active_projects"))
        ),
    )
    monkeypatch.setattr(rc, "copy_project_binaries", lambda *a, **k: None)
    monkeypatch.setattr(rc, "warn_orphans", lambda *a, **k: None)
    rc.release_tree(
        "http://obs",
        "S",
        "PR:T",
        [("containers", tmp_path)],
        "PR",
        {},
        verify_timeout=0,
        branch_rootprj="prod",
        active_projects={"PR:T", "PR:T:containers"},
    )
    assert seen == [("PR:T:containers", "prod", {"PR:T", "PR:T:containers"})]
