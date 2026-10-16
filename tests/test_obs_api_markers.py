"""Unit tests for the project description marker and publish override (percona_obs.obs_api)."""

from pathlib import Path

import percona_obs.obs_api as obs_api

_META = (
    '<project name="P"><title>t</title><description>Mirror of X\n'
    'source_commit: old</description><repository name="r"/></project>'
)


def test_marker_round_trip(monkeypatch):
    pushed = {}
    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", lambda a, p: _META)
    monkeypatch.setattr(
        obs_api,
        "_edit_project_meta",
        lambda a, p, meta, force: pushed.setdefault("meta", meta) and False,
    )
    obs_api.set_project_description_marker("http://obs", "P", "source_commit", "new")
    assert pushed["meta"].count("source_commit:") == 1
    assert "source_commit: new" in pushed["meta"]
    assert "Mirror of X" in pushed["meta"]

    monkeypatch.setattr(
        obs_api.osc.core, "show_project_meta", lambda a, p: pushed["meta"]
    )
    assert (
        obs_api.read_project_description_marker("http://obs", "P", "source_commit")
        == "new"
    )
    assert obs_api.read_project_description_marker("http://obs", "P", "other") is None


def test_publish_override_forces_enable(monkeypatch, tmp_path):
    (tmp_path / "project.yaml").write_text(
        "publish: {r: false}\nrepositories:\n  - name: r\n    archs: [x86_64]\n    paths: []\n"
    )
    seen = {}
    monkeypatch.setattr(
        obs_api,
        "build_project_meta",
        lambda *a, **k: seen.setdefault("publish", k.get("publish")) or "<project/>",
    )
    import urllib.error

    def not_found(*a, **k):
        raise urllib.error.HTTPError("u", 404, "nf", {}, None)

    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", not_found)
    monkeypatch.setattr(obs_api.osc.core, "show_project_conf", not_found)
    monkeypatch.setattr(
        obs_api, "_fetch_root_project_managed_elements", lambda a, r: []
    )
    monkeypatch.setattr(obs_api, "_inject_obs_managed_elements", lambda m, e: m)
    obs_api._apply_project_config(
        "http://obs", "root:P", tmp_path, "root", dry_run=True, publish_override=True
    )
    assert seen["publish"] is True


def test_marker_refuses_when_repository_paths_stripped(monkeypatch):
    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", lambda a, p: _META)
    monkeypatch.setattr(obs_api, "_edit_project_meta", lambda a, p, meta, force: True)
    import pytest

    with pytest.raises(SystemExit, match="stripped its repository paths"):
        obs_api.set_project_description_marker(
            "http://obs", "P", "source_commit", "new"
        )


def test_marker_inserts_missing_description_after_title(monkeypatch):
    no_desc = '<project name="P"><title>t</title><repository name="r"/></project>'
    pushed = {}
    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", lambda a, p: no_desc)
    monkeypatch.setattr(
        obs_api,
        "_edit_project_meta",
        lambda a, p, meta, force: pushed.setdefault("meta", meta) and False,
    )
    obs_api.set_project_description_marker("http://obs", "P", "source_commit", "abc")
    import xml.etree.ElementTree as ET

    root = ET.fromstring(pushed["meta"])
    tags = [child.tag for child in root]
    assert tags == ["title", "description", "repository"]
    assert root.findtext("description") == "source_commit: abc"


def test_markers_written_in_order_in_one_meta_write(monkeypatch):
    meta = (
        '<project name="P"><title>t</title><description>Mirror of X\n'
        "release_id: 18.7-1\nsource_commit: old</description>"
        '<repository name="r"/></project>'
    )
    pushed = []
    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", lambda a, p: meta)
    monkeypatch.setattr(
        obs_api,
        "_edit_project_meta",
        lambda a, p, m, force: pushed.append(m) and False,
    )
    obs_api.set_project_description_markers(
        "http://obs", "P", [("source_commit", "new"), ("release_id", "18.7-2")]
    )
    import xml.etree.ElementTree as ET

    assert len(pushed) == 1
    desc = ET.fromstring(pushed[0]).findtext("description")
    assert desc.splitlines() == [
        "Mirror of X",
        "source_commit: new",
        "release_id: 18.7-2",
    ]


def test_single_marker_is_appended_last(monkeypatch):
    pushed = {}
    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", lambda a, p: _META)
    monkeypatch.setattr(
        obs_api,
        "_edit_project_meta",
        lambda a, p, meta, force: pushed.setdefault("meta", meta) and False,
    )
    obs_api.set_project_description_marker("http://obs", "P", "release_id", "17.11-2")
    import xml.etree.ElementTree as ET

    desc = ET.fromstring(pushed["meta"]).findtext("description")
    assert desc.splitlines()[-1] == "release_id: 17.11-2"
    assert "source_commit: old" in desc
