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
    monkeypatch.setattr(
        rc,
        "set_project_publish",
        lambda apiurl, prj, flags: calls.append(("publish", prj, flags)),
    )
    monkeypatch.setattr(
        rc, "mirror_publish_flags", lambda path, env, override=None: override
    )
    monkeypatch.setattr(rc, "_fetch_obs_subproject_names", lambda apiurl, prefix: set())
    monkeypatch.setattr(
        rc,
        "set_project_description_marker",
        lambda apiurl, prj, key, value: calls.append(("marker", prj, key, value)),
    )


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
    rc.release_tree(
        "http://obs",
        "S",
        "T",
        pairs,
        "home:Admin",
        {},
        top_mirror_path=tmp_path,
        verify_timeout=5,
    )
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
        top_mirror_path=tmp_path,
        publish_override=True,
        verify_timeout=0,
    )
    # Subproject meta holds publishing; the override applies after the copy.
    assert seen["publish"] is False
    assert ("publish", "T:x", True) in calls


def test_release_tree_holds_publish_until_verified(monkeypatch, tmp_path):
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
    monkeypatch.setattr(
        rc,
        "mirror_publish_flags",
        lambda path, env, override=None: {"top": True, "sub": {"r": False}}[path.name],
    )
    rc.release_tree(
        "http://obs",
        "S",
        "T",
        [("x", tmp_path / "sub")],
        "home:Admin",
        {},
        top_mirror_path=tmp_path / "top",
        verify_timeout=5,
    )
    kinds = [c[0] for c in calls]
    assert calls[0] == ("publish", "T", False)
    last_verify = max(i for i, k in enumerate(kinds) if k == "verify")
    last_osc = max(i for i, k in enumerate(kinds) if k == "osc")
    released = [c for c in calls if c[0] == "publish" and c[2] is not False]
    assert released == [("publish", "T", True), ("publish", "T:x", {"r": False})]
    assert all(calls.index(c) > max(last_verify, last_osc) for c in released)


def test_mirror_publish_flags(tmp_path):
    (tmp_path / "project.yaml").write_text("publish:\n  r: false\n")
    assert rc.mirror_publish_flags(tmp_path, {}) == {"r": False}
    assert rc.mirror_publish_flags(tmp_path, {}, True) is True


def test_release_tree_writes_release_id_before_each_copy(monkeypatch, tmp_path):
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(
        rc.subprocess, "run", lambda cmd, **k: calls.append(("osc", cmd[4]))
    )
    pairs = [("containers", tmp_path / "containers")]
    rc.release_tree(
        "http://obs",
        "S",
        "T",
        pairs,
        "home:Admin",
        {},
        top_mirror_path=tmp_path,
        verify_timeout=0,
        release_id="18.7-1",
    )
    assert [c for c in calls if c[0] in ("osc", "meta", "marker")] == [
        ("marker", "T", "release_id", "18.7-1"),
        ("osc", "S"),
        ("meta", "T:containers"),
        ("marker", "T:containers", "release_id", "18.7-1"),
        ("osc", "S:containers"),
    ]


def test_release_tree_without_release_id_writes_no_marker(monkeypatch, tmp_path):
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(rc.subprocess, "run", lambda *a, **k: None)
    rc.release_tree(
        "http://obs",
        "S",
        "T",
        [("x", tmp_path)],
        "home:Admin",
        {},
        top_mirror_path=tmp_path,
        verify_timeout=0,
    )
    assert not [c for c in calls if c[0] == "marker"]


def _stub_listing(monkeypatch, packages, subprojects):
    deleted = []
    monkeypatch.setattr(
        rc,
        "_fetch_obs_package_names_or_fail",
        lambda apiurl, prj: set(packages.get(prj, ())),
    )
    monkeypatch.setattr(
        rc, "_fetch_obs_package_names", lambda apiurl, prj: set(packages.get(prj, ()))
    )
    monkeypatch.setattr(
        rc, "_fetch_obs_subproject_names", lambda apiurl, prj: set(subprojects)
    )
    monkeypatch.setattr(
        rc,
        "_delete_obs_package",
        lambda apiurl, prj, pkg, dry_run: deleted.append(("pkg", prj, pkg, dry_run)),
    )
    monkeypatch.setattr(
        rc,
        "_delete_obs_project",
        lambda apiurl, prj, dry_run, recursive=False: deleted.append(
            ("prj", prj, dry_run, recursive)
        ),
    )
    return deleted


def _mirror(tmp_path, *subs):
    top = tmp_path / "releases/18"
    for sub in ("", *subs):
        (top / sub).mkdir(parents=True, exist_ok=True)
        (top / sub / "project.yaml").write_text("build: false\n")
    return top


def test_prune_deletes_stale_packages_per_member(tmp_path, monkeypatch):
    top = _mirror(tmp_path, "containers")
    deleted = _stub_listing(
        monkeypatch,
        {
            "S": {"a", "b"},
            "T": {"a", "b", "gone"},
            "S:containers": {"img"},
            "T:containers": {"img", "old-img"},
        },
        {"T:containers"},
    )
    rc.prune_release_tree(
        "http://obs", "S", "T", [("containers", top / "containers")], top
    )
    assert deleted == [
        ("pkg", "T", "gone", False),
        ("pkg", "T:containers", "old-img", False),
    ]


def test_stale_subprojects_keeps_projects_with_a_mirror(tmp_path, monkeypatch):
    # extras is another unit: it has a mirror dir (no release.yaml yet) and stays.
    top = _mirror(tmp_path, "containers", "extras", "extras/containers")
    deleted = _stub_listing(
        monkeypatch,
        {"S": {"a"}, "T": {"a"}, "S:containers": {"i"}, "T:containers": {"i"}},
        {
            "T:containers",
            "T:extras",
            "T:extras:containers",
            "T:old",
            "T:old:ubi9",
            "T:old:ubi9:x",
        },
    )
    rc.prune_release_tree(
        "http://obs", "S", "T", [("containers", top / "containers")], top
    )
    assert deleted == [
        ("prj", "T:old:ubi9:x", False, True),
        ("prj", "T:old:ubi9", False, True),
        ("prj", "T:old", False, True),
    ]


def test_stale_subprojects_never_enter_another_unit(tmp_path, monkeypatch):
    # extras/old has no mirror, but extras is another unit: not ours to judge.
    top = _mirror(tmp_path, "extras")
    deleted = _stub_listing(
        monkeypatch,
        {"S": {"a"}, "T": {"a"}},
        {"T:extras", "T:extras:old", "T:extras:containers"},
    )
    rc.prune_release_tree("http://obs", "S", "T", [], top)
    assert deleted == []


def test_stale_subprojects_inside_a_bundled_child(tmp_path, monkeypatch):
    top = _mirror(tmp_path, "containers")
    deleted = _stub_listing(
        monkeypatch,
        {"S": {"a"}, "T": {"a"}, "S:containers": {"i"}, "T:containers": {"i"}},
        {"T:containers", "T:containers:ubi9"},
    )
    rc.prune_release_tree(
        "http://obs", "S", "T", [("containers", top / "containers")], top
    )
    assert deleted == [("prj", "T:containers:ubi9", False, True)]


def test_stale_subprojects_retired_unit_goes_deepest_first(tmp_path, monkeypatch):
    top = _mirror(tmp_path)
    deleted = _stub_listing(
        monkeypatch, {"S": {"a"}, "T": {"a"}}, {"T:tde", "T:tde:sub"}
    )
    rc.prune_release_tree("http://obs", "S", "T", [], top)
    assert deleted == [("prj", "T:tde:sub", False, True), ("prj", "T:tde", False, True)]


def test_prune_refuses_mirror_without_project_yaml(tmp_path, monkeypatch):
    listed = []
    monkeypatch.setattr(
        rc,
        "_fetch_obs_package_names_or_fail",
        lambda a, p: listed.append(p) or set(),
    )
    monkeypatch.setattr(
        rc, "_fetch_obs_package_names", lambda a, p: listed.append(p) or set()
    )
    monkeypatch.setattr(
        rc, "_fetch_obs_subproject_names", lambda a, p: listed.append(p) or set()
    )
    fail = lambda *a, **k: pytest.fail("no delete")
    monkeypatch.setattr(rc, "_delete_obs_package", fail)
    monkeypatch.setattr(rc, "_delete_obs_project", fail)
    with pytest.raises(SystemExit, match=str(tmp_path)):
        rc.prune_release_tree("http://obs", "S", "T", [], tmp_path)
    assert listed == []


def test_prune_refuses_empty_source_with_packages_in_target(tmp_path, monkeypatch):
    top = _mirror(tmp_path)
    deleted = _stub_listing(monkeypatch, {"S": set(), "T": {"a", "b"}}, set())
    with pytest.raises(SystemExit, match="S lists no packages"):
        rc.prune_release_tree("http://obs", "S", "T", [], top)
    assert deleted == []


def test_prune_allows_packageless_root(tmp_path, monkeypatch):
    top = _mirror(tmp_path, "containers")
    deleted = _stub_listing(
        monkeypatch,
        {"S": set(), "T": set(), "S:containers": {"i"}, "T:containers": {"i", "x"}},
        {"T:containers"},
    )
    rc.prune_release_tree(
        "http://obs", "S", "T", [("containers", top / "containers")], top
    )
    assert deleted == [("pkg", "T:containers", "x", False)]


def test_prune_dry_run_reports_without_deleting(tmp_path, monkeypatch):
    top = _mirror(tmp_path)
    deleted = _stub_listing(monkeypatch, {"S": {"a"}, "T": {"a", "gone"}}, {"T:old"})
    rc.prune_release_tree("http://obs", "S", "T", [], top, dry_run=True)
    assert deleted == [("pkg", "T", "gone", True), ("prj", "T:old", True, True)]


def test_release_tree_prunes_after_verify_and_before_publish(tmp_path, monkeypatch):
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(rc.subprocess, "run", lambda cmd, **k: None)
    monkeypatch.setattr(
        rc, "verify_release_landed", lambda *a, **k: calls.append(("verify", a[2]))
    )
    monkeypatch.setattr(
        rc, "prune_release_tree", lambda *a, **k: calls.append(("prune", a[2]))
    )
    rc.release_tree(
        "http://obs", "S", "T", [], "R", {}, top_mirror_path=tmp_path, prune=True
    )
    kinds = [c[0] for c in calls]
    assert kinds.index("verify") < kinds.index("prune")
    assert kinds.index("prune") < len(kinds) - 1 - kinds[::-1].index("publish")


def test_release_tree_skips_prune_without_verify(tmp_path, monkeypatch, capsys):
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(rc.subprocess, "run", lambda cmd, **k: None)
    monkeypatch.setattr(
        rc, "prune_release_tree", lambda *a, **k: calls.append(("prune",))
    )
    rc.release_tree(
        "http://obs",
        "S",
        "T",
        [],
        "R",
        {},
        top_mirror_path=tmp_path,
        prune=True,
        verify_timeout=0,
    )
    assert ("prune",) not in calls
    assert "not pruned" in capsys.readouterr().out


def test_release_tree_does_not_prune_by_default(tmp_path, monkeypatch):
    calls = []
    _stub_obs(monkeypatch, calls)
    monkeypatch.setattr(rc.subprocess, "run", lambda cmd, **k: None)
    monkeypatch.setattr(rc, "verify_release_landed", lambda *a, **k: None)
    monkeypatch.setattr(
        rc, "prune_release_tree", lambda *a, **k: calls.append(("prune",))
    )
    rc.release_tree("http://obs", "S", "T", [], "R", {}, top_mirror_path=tmp_path)
    assert ("prune",) not in calls
