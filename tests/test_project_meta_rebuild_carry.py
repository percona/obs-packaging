"""_apply_project_config keeps the repository rebuild attribute on meta updates."""

import xml.etree.ElementTree as ET

import percona_obs.obs_api as obs_api

LIVE = (
    '<project name="root:P"><title>old</title><description/>'
    '<repository name="A" rebuild="local"><arch>x86_64</arch></repository>'
    '<repository name="B" rebuild="local"><arch>x86_64</arch></repository>'
    "</project>"
)
DESIRED_TMPL = (
    '<project name="root:P"><title>{title}</title><description/>'
    '<repository name="A"><arch>x86_64</arch></repository>'
    '<repository name="B"><arch>x86_64</arch></repository>'
    "</project>"
)


def _drive(monkeypatch, tmp_path, live, desired):
    uploads = []
    monkeypatch.setattr(
        obs_api,
        "_load_project_config_with_inheritance",
        lambda p, e: {"title": "t", "repositories": [], "project-config": ""},
    )
    monkeypatch.setattr(obs_api, "build_project_meta", lambda *a, **k: desired)
    monkeypatch.setattr(obs_api.osc.core, "show_project_meta", lambda a, p: live)
    monkeypatch.setattr(obs_api.osc.core, "show_project_conf", lambda a, p: "")
    monkeypatch.setattr(
        obs_api,
        "_edit_project_meta",
        lambda a, p, meta, force: uploads.append(meta) or False,
    )
    obs_api._apply_project_config("http://obs", "root:P", tmp_path, "root")
    return uploads


def test_update_keeps_rebuild_local(monkeypatch, tmp_path):
    uploads = _drive(monkeypatch, tmp_path, LIVE, DESIRED_TMPL.format(title="new"))
    assert len(uploads) == 1
    repos = ET.fromstring(uploads[0]).findall("repository")
    assert [r.get("rebuild") for r in repos] == ["local", "local"]


def test_rebuild_only_difference_causes_no_write(monkeypatch, tmp_path):
    uploads = _drive(monkeypatch, tmp_path, LIVE, DESIRED_TMPL.format(title="old"))
    assert uploads == []
