"""Unit tests for the sync-state manifest (percona_obs.sync_state)."""

from types import SimpleNamespace

import percona_obs.git_utils as git_utils
import percona_obs.sync_state as sync_state
from percona_obs.git_utils import _head_is_pushed
from percona_obs.sync_state import (
    load_manifest,
    manifest_entry_clean,
    record_or_invalidate,
    save_manifest,
)


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
    monkeypatch.setattr(
        sync_state, "_has_package_content_changes_since", lambda *a: False
    )
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: False)
    monkeypatch.setattr(sync_state, "_macros_changed_since", lambda *a: False)
    manifest = {"p/x": "abc1234"}
    assert manifest_entry_clean(manifest, "p/x", tmp_path) is True
    assert manifest_entry_clean(manifest, "p/missing", tmp_path) is False
    monkeypatch.setattr(
        sync_state, "_has_package_content_changes_since", lambda *a: True
    )
    assert manifest_entry_clean(manifest, "p/x", tmp_path) is False


def test_entry_clean_false_on_dirty_or_macros(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path)
    manifest = {"p/x": "abc1234"}
    monkeypatch.setattr(
        sync_state, "_has_package_content_changes_since", lambda *a: False
    )
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: True)
    monkeypatch.setattr(sync_state, "_macros_changed_since", lambda *a: False)
    assert manifest_entry_clean(manifest, "p/x", tmp_path) is False
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: False)
    monkeypatch.setattr(sync_state, "_macros_changed_since", lambda *a: True)
    assert manifest_entry_clean(manifest, "p/x", tmp_path) is False


def test_record_or_invalidate_records_when_honest(monkeypatch, tmp_path):
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: False)
    monkeypatch.setattr(sync_state, "_inherited_macros_files", lambda p: [])
    manifest: dict[str, str] = {}
    record_or_invalidate(manifest, "p/x", "abc1234", True, tmp_path)
    assert manifest == {"p/x": "abc1234"}


def test_record_or_invalidate_pops_stale_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: False)
    monkeypatch.setattr(sync_state, "_inherited_macros_files", lambda p: [])
    # Unpushed HEAD: pop.
    manifest = {"p/x": "old1111"}
    record_or_invalidate(manifest, "p/x", "abc1234", False, tmp_path)
    assert manifest == {}
    # No HEAD sha: pop.
    manifest = {"p/x": "old1111"}
    record_or_invalidate(manifest, "p/x", None, True, tmp_path)
    assert manifest == {}
    # Dirty inputs: pop.
    manifest = {"p/x": "old1111"}
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: True)
    record_or_invalidate(manifest, "p/x", "abc1234", True, tmp_path)
    assert manifest == {}


def test_record_only_variant_never_pops(monkeypatch, tmp_path):
    monkeypatch.setattr(sync_state, "_inherited_macros_files", lambda p: [])
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: True)
    manifest = {"p/x": "old1111"}
    record_or_invalidate(manifest, "p/x", "abc1234", True, tmp_path, invalidate=False)
    assert manifest == {"p/x": "old1111"}
    record_or_invalidate(manifest, "p/x", None, False, tmp_path, invalidate=False)
    assert manifest == {"p/x": "old1111"}
    monkeypatch.setattr(sync_state, "_is_path_dirty", lambda *a: False)
    record_or_invalidate(manifest, "p/x", "new2222", True, tmp_path, invalidate=False)
    assert manifest == {"p/x": "new2222"}


def test_record_dirtiness_covers_inherited_macros(monkeypatch, tmp_path):
    seen: dict[str, tuple] = {}

    def fake_dirty(*paths):
        seen["paths"] = paths
        return False

    macros = tmp_path / "macros.yaml"
    monkeypatch.setattr(sync_state, "_is_path_dirty", fake_dirty)
    monkeypatch.setattr(sync_state, "_inherited_macros_files", lambda p: [macros])
    manifest: dict[str, str] = {}
    record_or_invalidate(manifest, "p/x", "abc1234", True, tmp_path)
    assert seen["paths"] == (tmp_path, macros)
    assert manifest == {"p/x": "abc1234"}


def test_head_is_pushed(monkeypatch):
    monkeypatch.setattr(
        git_utils.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="  origin/main\n"),
    )
    assert _head_is_pushed() is True
    monkeypatch.setattr(
        git_utils.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="\n"),
    )
    assert _head_is_pushed() is False
    monkeypatch.setattr(
        git_utils.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=128, stdout=""),
    )
    assert _head_is_pushed() is False
