"""Latest release-id lookup in .github/scripts/update_version_lists.py."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "update_version_lists",
    Path(__file__).parent.parent / ".github/scripts/update_version_lists.py",
)
assert _SPEC is not None


def _load():
    assert _SPEC is not None and _SPEC.loader is not None
    mod = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(mod)
    return mod


def _latest(tmp_path, monkeypatch, releases_yaml: str) -> str:
    m = _load()
    d = tmp_path / "ppg" / "releases" / "18"
    d.mkdir(parents=True)
    (d / "release.yaml").write_text(releases_yaml)
    monkeypatch.setattr(m, "ROOT_DIR", tmp_path)
    return m.get_latest_release_id("ppg:releases:18")


def test_latest_release_id_string_entries(tmp_path, monkeypatch):
    assert (
        _latest(tmp_path, monkeypatch, "releases:\n- ppg/18.4-1\n- ppg/18.6-1\n")
        == "18.6-1"
    )


def test_latest_release_id_mapping_entry(tmp_path, monkeypatch):
    y = "releases:\n- ppg/18.4-1\n- tag: ppg/18.6-1\n  source_commit: abc\n"
    assert _latest(tmp_path, monkeypatch, y) == "18.6-1"
