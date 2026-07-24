"""Unit tests for delete handling in _upload_obs_files (percona_obs.obs_api).

Moving-ref devel packages rename their tarball on every tag-offset bump, so
each sync deletes the previous tarball via http_DELETE.  A 404 on that delete
means the file is already gone — a benign, idempotent outcome that must not
abort the whole sync run.  A non-404 error must still propagate.
"""

import urllib.error

import pytest

import percona_obs.obs_api as obs_api
from percona_obs.obs_api import _upload_obs_files


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "http://obs/source/prj/pkg/old.tar.gz", code, "boom", None, None  # type: ignore[arg-type]
    )


def _prepare(monkeypatch, tmp_path, delete_error):
    """Local dir has new.tar.gz; OBS has old.tar.gz (absent locally → deleted)."""
    (tmp_path / "new.tar.gz").write_bytes(b"new")

    monkeypatch.setattr(
        obs_api,
        "_fetch_obs_file_md5s",
        lambda *a, **k: {"old.tar.gz": "0" * 32},
    )
    monkeypatch.setattr(obs_api.osc.connection, "http_PUT", lambda *a, **k: None)
    monkeypatch.setattr(obs_api.osc.connection, "http_POST", lambda *a, **k: None)

    def _delete(*a, **k):
        if delete_error is not None:
            raise delete_error

    monkeypatch.setattr(obs_api.osc.connection, "http_DELETE", _delete)


def test_delete_404_is_tolerated(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, _http_error(404))
    assert _upload_obs_files("http://obs", "prj", "pkg", tmp_path, message="m") is True


def test_delete_non_404_propagates(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, _http_error(500))
    with pytest.raises(urllib.error.HTTPError):
        _upload_obs_files("http://obs", "prj", "pkg", tmp_path, message="m")
