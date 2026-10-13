"""Unit tests for the project description marker and publish override (percona_obs.obs_api)."""

from pathlib import Path

import percona_obs.obs_api as obs_api

_META = (
    '<project name="P"><title>t</title><description>Mirror of X\n'
    "source_commit: old</description><repository name=\"r\"/></project>"
)


def test_marker_round_trip(monkeypatch):
    pushed = {}
    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", lambda a, p: _META)
    monkeypatch.setattr(
        obs_api, "_edit_project_meta", lambda a, p, meta, force: pushed.setdefault("meta", meta) or False
    )
    obs_api.set_project_description_marker("http://obs", "P", "source_commit", "new")
    assert pushed["meta"].count("source_commit:") == 1
    assert "source_commit: new" in pushed["meta"]
    assert "Mirror of X" in pushed["meta"]

    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", lambda a, p: pushed["meta"])
    assert obs_api.read_project_description_marker("http://obs", "P", "source_commit") == "new"
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
    monkeypatch.setattr(obs_api, "_fetch_root_project_managed_elements", lambda a, r: [])
    monkeypatch.setattr(obs_api, "_inject_obs_managed_elements", lambda m, e: m)
    obs_api._apply_project_config(
        "http://obs", "root:P", tmp_path, "root", dry_run=True, publish_override=True
    )
    assert seen["publish"] is True
