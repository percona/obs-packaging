"""Unit tests for the local service cache (percona_obs.services).

Covers the age-based pruning used by CI to keep the actions/cache tree
bounded: cache hits bump the entry mtime (so mtime means "last used"), and
prune_cache() deletes entries older than the cutoff at the right depth for
each cache tree, cleaning up emptied intermediate key directories.
"""

import os
import time

import percona_obs.services as services
from percona_obs.services import _cache_entry_lookup, prune_cache

_OLD = time.time() - 30 * 86400  # 30 days ago, well past any cutoff


def _make_entry(entry, age=None):
    entry.mkdir(parents=True)
    (entry / "artifact.tar.gz").write_bytes(b"data")
    if age is not None:
        os.utime(entry, (age, age))


def _point_caches_at(monkeypatch, tmp_path):
    cache_dir = tmp_path / ".cache"
    for attr, sub in [
        ("_OBS_SCM_CACHE_DIR", "obs_scm"),
        ("_SVC_CACHE_DIR", "services"),
        ("_DOWNLOAD_URL_CACHE_DIR", "download_url"),
        ("_CARGO_VENDOR_CACHE_DIR", "cargo_vendor"),
    ]:
        monkeypatch.setattr(services, attr, cache_dir / sub)
    return cache_dir


def test_lookup_hit_bumps_mtime(tmp_path):
    entry = tmp_path / "download_url" / "abc123"
    _make_entry(entry, age=_OLD)
    assert entry.stat().st_mtime < time.time() - 86400

    assert _cache_entry_lookup(entry) == ["artifact.tar.gz"]
    assert entry.stat().st_mtime > time.time() - 60


def test_lookup_miss_on_absent_or_empty(tmp_path):
    assert _cache_entry_lookup(tmp_path / "nope") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _cache_entry_lookup(empty) is None


def test_prune_removes_stale_keeps_fresh(tmp_path, monkeypatch):
    cache_dir = _point_caches_at(monkeypatch, tmp_path)

    stale_dl = cache_dir / "download_url" / "stalekey"
    fresh_dl = cache_dir / "download_url" / "freshkey"
    stale_svc = cache_dir / "services" / "stalecommit"
    _make_entry(stale_dl, age=_OLD)
    _make_entry(fresh_dl)
    _make_entry(stale_svc, age=_OLD)

    assert prune_cache(max_age_days=7) == 2
    assert not stale_dl.exists()
    assert not stale_svc.exists()
    assert fresh_dl.exists()


def test_prune_depth2_trees_and_empty_key_dirs(tmp_path, monkeypatch):
    cache_dir = _point_caches_at(monkeypatch, tmp_path)

    # obs_scm nests <params-key>/<head-sha>; the params-key dir itself is old
    # but must survive while it still holds a fresh entry, and be removed
    # once pruning empties it.
    emptied_key = cache_dir / "obs_scm" / "keyA"
    _make_entry(emptied_key / "oldsha", age=_OLD)
    os.utime(emptied_key, (_OLD, _OLD))
    mixed_key = cache_dir / "obs_scm" / "keyB"
    _make_entry(mixed_key / "oldsha", age=_OLD)
    _make_entry(mixed_key / "newsha")
    os.utime(mixed_key, (_OLD, _OLD))
    stale_vendor = cache_dir / "cargo_vendor" / "keyC" / "oldsrc"
    _make_entry(stale_vendor, age=_OLD)

    assert prune_cache(max_age_days=7) == 3
    assert not emptied_key.exists()
    assert not (mixed_key / "oldsha").exists()
    assert (mixed_key / "newsha").exists()
    assert not (cache_dir / "cargo_vendor" / "keyC").exists()


def test_prune_missing_cache_dirs_is_noop(tmp_path, monkeypatch):
    _point_caches_at(monkeypatch, tmp_path)
    assert prune_cache(max_age_days=7) == 0
