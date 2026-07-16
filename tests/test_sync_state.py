"""Unit tests for the sync-state manifest (percona_obs.sync_state)."""

import percona_obs.sync_state as sync_state
from percona_obs.sync_state import load_manifest, save_manifest, manifest_entry_clean


def _point_at(monkeypatch, tmp_path):
    monkeypatch.setattr(sync_state, "_SYNC_STATE_DIR", tmp_path / "sync_state")


def test_round_trip(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path)
    save_manifest("http://obs", "root:prj", {"p/x": "abc1234"})
    assert load_manifest("http://obs", "root:prj") == {"p/x": "abc1234"}


def test_missing_and_corrupt_load_empty(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path)
    assert load_manifest("http://obs", "root:prj") == {}
    save_manifest("http://obs", "root:prj", {"p/x": "abc1234"})
    path = sync_state._manifest_path("http://obs", "root:prj")
    path.write_text("{not json")
    assert load_manifest("http://obs", "root:prj") == {}


def test_manifests_keyed_by_apiurl_and_rootprj(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path)
    save_manifest("http://obs-a", "root", {"p/x": "aaa1111"})
    save_manifest("http://obs-b", "root", {"p/x": "bbb2222"})
    assert load_manifest("http://obs-a", "root") == {"p/x": "aaa1111"}
    assert load_manifest("http://obs-b", "root") == {"p/x": "bbb2222"}


def test_non_dict_and_non_string_entries_filtered(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path)
    path = sync_state._manifest_path("http://obs", "root")
    path.parent.mkdir(parents=True)
    path.write_text('["a", "b"]')
    assert load_manifest("http://obs", "root") == {}
    path.write_text('{"p/x": "abc", "p/y": 42}')
    assert load_manifest("http://obs", "root") == {"p/x": "abc"}


def test_entry_clean_checks_git_state(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path)
    monkeypatch.setattr(sync_state, "_has_package_changes_since", lambda *a: False)
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: False)
    monkeypatch.setattr(sync_state, "_macros_changed_since", lambda *a: False)
    manifest = {"p/x": "abc1234"}
    assert manifest_entry_clean(manifest, "p/x", tmp_path) is True
    assert manifest_entry_clean(manifest, "p/missing", tmp_path) is False
    monkeypatch.setattr(sync_state, "_has_package_changes_since", lambda *a: True)
    assert manifest_entry_clean(manifest, "p/x", tmp_path) is False


def test_entry_clean_false_on_dirty_or_macros(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path)
    manifest = {"p/x": "abc1234"}
    monkeypatch.setattr(sync_state, "_has_package_changes_since", lambda *a: False)
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: True)
    monkeypatch.setattr(sync_state, "_macros_changed_since", lambda *a: False)
    assert manifest_entry_clean(manifest, "p/x", tmp_path) is False
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: False)
    monkeypatch.setattr(sync_state, "_macros_changed_since", lambda *a: True)
    assert manifest_entry_clean(manifest, "p/x", tmp_path) is False
