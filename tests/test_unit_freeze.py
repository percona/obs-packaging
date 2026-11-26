# tests/test_unit_freeze.py
"""Unit tests for percona_obs.unit_freeze; OBS traffic is faked."""

import urllib.error
import xml.etree.ElementTree as ET

import pytest

import percona_obs.unit_freeze as uf

META = (
    '<project name="p"><title>t</title><description/>'
    '<person userid="u" role="maintainer"/>'
    '<build><disable repository="A"/></build>'
    '<repository name="A"><path project="x" repository="r"/><arch>x86_64</arch></repository>'
    '<repository name="B" block="local"><arch>aarch64</arch></repository>'
    "</project>"
)


def test_freeze_state_values():
    assert uf.freeze_state(META) == "unfrozen"
    assert uf.freeze_state(uf.with_rebuild_mode(META, "local")) == "frozen"
    one = META.replace('name="A">', 'name="A" rebuild="local">')
    assert uf.freeze_state(one) == "partial"
    assert uf.freeze_state('<project name="p"/>') == "empty"


def test_with_rebuild_mode_touches_only_the_attribute():
    frozen = ET.fromstring(uf.with_rebuild_mode(META, "local"))
    assert [r.get("rebuild") for r in frozen.findall("repository")] == [
        "local",
        "local",
    ]
    assert frozen.find("repository[@name='B']").get("block") == "local"
    assert frozen.find("person").get("userid") == "u"
    assert frozen.find("build/disable").get("repository") == "A"
    back = ET.fromstring(
        uf.with_rebuild_mode(ET.tostring(frozen, encoding="unicode"), None)
    )
    assert all(r.get("rebuild") is None for r in back.findall("repository"))


def _fake_obs(monkeypatch, metas, stick=()):
    """metas: project -> meta xml (or HTTPError code int). Writes are recorded
    and applied to *metas* unless the project is in *stick*."""
    writes = []

    def show(apiurl, prj):
        m = metas[prj]
        if isinstance(m, int):
            raise urllib.error.HTTPError("u", m, "x", {}, None)  # type: ignore[arg-type]
        return m.encode()

    def edit(apiurl, prj, xml, force):
        writes.append((prj, xml))
        if prj not in stick:
            metas[prj] = xml
        return False

    monkeypatch.setattr(uf.osc.core, "show_project_meta", show)
    monkeypatch.setattr(uf, "_edit_project_meta", edit)
    return writes


def test_apply_freeze_outcomes(monkeypatch):
    frozen = uf.with_rebuild_mode(META, "local")
    writes = _fake_obs(monkeypatch, {"p1": META, "p2": frozen, "p3": 404})
    out = uf.apply_freeze("api", ["p1", "p2", "p3"], frozen=True, dry_run=False)
    assert out == [("p1", "changed"), ("p2", "unchanged"), ("p3", "absent")]
    assert [p for p, _ in writes] == ["p1"]


def test_apply_freeze_dry_run_writes_nothing(monkeypatch):
    writes = _fake_obs(monkeypatch, {"p1": META})
    out = uf.apply_freeze("api", ["p1"], frozen=True, dry_run=True)
    assert out == [("p1", "changed")] and writes == []


def test_apply_freeze_verifies_the_write(monkeypatch):
    _fake_obs(monkeypatch, {"p1": META}, stick=("p1",))
    with pytest.raises(RuntimeError, match="p1"):
        uf.apply_freeze("api", ["p1"], frozen=True, dry_run=False)


def test_frozen_projects_omits_absent(monkeypatch):
    _fake_obs(
        monkeypatch,
        {"p1": META, "p2": uf.with_rebuild_mode(META, "local"), "p3": 404},
    )
    assert uf.frozen_projects("api", ["p1", "p2", "p3"]) == {
        "p1": "unfrozen",
        "p2": "frozen",
    }


def test_unit_obs_projects(tmp_path):
    unit = tmp_path / "ppg" / "staging" / "18"
    for d in (unit, unit / "containers", unit / "extras"):
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.yaml").write_text("title: t\n")
    (unit / "pkg").mkdir()
    (unit / "pkg" / "package.yaml").write_text("{}\n")
    assert uf.unit_obs_projects("ppg:staging:18", "isv:percona", root=tmp_path) == [
        "isv:percona:ppg:staging:18",
        "isv:percona:ppg:staging:18:containers",
    ]
    with pytest.raises(ValueError, match="ppg:staging:18:containers"):
        uf.unit_obs_projects("ppg:staging:18:containers", "isv:percona", root=tmp_path)


def test_carry_rebuild_same_names():
    cur = '<project name="p"><repository name="A" rebuild="local"/><repository name="B" rebuild="direct"/></project>'
    des = '<project name="p"><repository name="A"/><repository name="B"/></project>'
    got = ET.fromstring(uf.carry_rebuild(cur, des))
    assert [(r.get("name"), r.get("rebuild")) for r in got.findall("repository")] == [
        ("A", "local"),
        ("B", "direct"),
    ]


def test_carry_rebuild_new_repo_in_frozen_project():
    cur = '<project name="p"><repository name="A" rebuild="local"/></project>'
    des = '<project name="p"><repository name="A"/><repository name="N"/></project>'
    got = ET.fromstring(uf.carry_rebuild(cur, des))
    assert got.find("repository[@name='N']").get("rebuild") == "local"


def test_carry_rebuild_new_repo_in_unfrozen_project():
    cur = '<project name="p"><repository name="A"/></project>'
    des = '<project name="p"><repository name="A"/><repository name="N"/></project>'
    got = ET.fromstring(uf.carry_rebuild(cur, des))
    assert got.find("repository[@name='N']").get("rebuild") is None
