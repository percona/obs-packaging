"""Unit tests for the strict per-project package listing (percona_obs.obs_api).

_fetch_obs_package_names_or_fail feeds the --skip-unchanged existence gate:
a package may only be skipped when OBS is known to have it, so the listing
must not silently degrade to "empty" on API failures the way the lenient
_fetch_obs_package_names (orphan cleanup) does.
"""

import urllib.error

import pytest

import percona_obs.obs_api as obs_api
from percona_obs.obs_api import _fetch_obs_package_names_or_fail


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://obs/source/prj", code, "boom", {}, None)  # type: ignore[arg-type]


def test_returns_names_on_success(monkeypatch):
    monkeypatch.setattr(
        obs_api.osc.core, "meta_get_packagelist", lambda *a, **k: ["a", "", "b"]
    )
    assert _fetch_obs_package_names_or_fail("http://obs", "prj") == {"a", "b"}


def test_missing_project_is_empty_set(monkeypatch):
    def _raise(*a, **k):
        raise _http_error(404)

    monkeypatch.setattr(obs_api.osc.core, "meta_get_packagelist", _raise)
    assert _fetch_obs_package_names_or_fail("http://obs", "prj") == set()


def test_other_http_error_aborts(monkeypatch):
    def _raise(*a, **k):
        raise _http_error(503)

    monkeypatch.setattr(obs_api.osc.core, "meta_get_packagelist", _raise)
    with pytest.raises(SystemExit) as exc:
        _fetch_obs_package_names_or_fail("http://obs", "prj")
    assert "prj" in str(exc.value)


def test_transport_error_aborts_naming_project(monkeypatch):
    def _raise(*a, **k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(obs_api.osc.core, "meta_get_packagelist", _raise)
    with pytest.raises(SystemExit) as exc:
        _fetch_obs_package_names_or_fail("http://obs", "prj")
    assert "prj" in str(exc.value)
