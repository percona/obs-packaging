"""Typing of OBS projects in the QA matrix script (.github/scripts/list_qa_matrix.py)."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "list_qa_matrix", Path(__file__).parent.parent / ".github/scripts/list_qa_matrix.py"
)
assert _SPEC is not None


def _load():
    assert _SPEC is not None
    mod = importlib.util.module_from_spec(_SPEC)
    assert _SPEC.loader is not None
    _SPEC.loader.exec_module(mod)
    return mod


def test_qa_project_type():
    m = _load()
    assert m.qa_project_type("x:ppg:staging:18:containers") == "containers"
    assert m.qa_project_type("x:ppg:releases:17:containers:ubi9") == "containers"
    assert m.qa_project_type("x:ppg:staging:17:extras:containers") == "containers"
    assert m.qa_project_type("x:ppg:staging:17:tarballs") == "packages"
    assert m.qa_project_type("x:ppg:staging:17") == "packages"


def test_normalize_entry_name_filter():
    m = _load()
    # qa show already emits name_filter → passed through untouched
    e = m.normalize_entry({"name": "ubi8", "name_filter": "--name ubi8"})
    assert e["name_filter"] == "--name ubi8"
    # derived from `name` when absent
    assert m.normalize_entry({"name": "ubi9"})["name_filter"] == "--name ubi9"
    # unnamed entries get the empty string, mirroring axis_filters
    assert m.normalize_entry({"name": ""})["name_filter"] == ""
    assert m.normalize_entry({})["name_filter"] == ""


def test_normalize_entry_package_filter():
    m = _load()
    assert m.normalize_entry({"package": "pkg"})["package_filter"] == "--package pkg"
    assert m.normalize_entry({"package": ""})["package_filter"] == ""
    assert m.normalize_entry({})["package_filter"] == ""
    e = m.normalize_entry({"package": "pkg", "package_filter": "--package pkg"})
    assert e["package_filter"] == "--package pkg"


def _combo(package: str, ctx: str) -> dict:
    return {"package": package, "status_context": ctx, "params": {}}


def test_drop_absent_packages_keeps_project_and_present():
    m = _load()
    matrix = [
        _combo("", "OBS QA / p"),
        _combo("pg_tde", "OBS QA / p / pg_tde"),
        _combo("pgbackrest", "OBS QA / p / pgbackrest"),
    ]
    kept, dropped = m.drop_absent_packages(matrix, {"pg_tde", "unrelated"})
    assert [c["status_context"] for c in kept] == ["OBS QA / p", "OBS QA / p / pg_tde"]
    assert dropped == ["pgbackrest"]


def test_drop_absent_packages_noop_without_package_lanes():
    m = _load()
    matrix = [_combo("", "OBS QA / p")]
    kept, dropped = m.drop_absent_packages(matrix, set())
    assert kept == matrix and dropped == []


def test_main_applies_presence_filter(monkeypatch, capsys):
    import json
    import subprocess

    m = _load()
    monkeypatch.setenv("OBS_APIURL", "https://obs.example")
    monkeypatch.setenv("OBS_PROJECT", "isv:percona:PR:pr-1")
    monkeypatch.setenv("QA_PACKAGES_PRESENT_ONLY", "true")
    monkeypatch.delenv("QA_TYPES", raising=False)

    # Import the real module first: it imports osc at module level, and the
    # stub below only has to satisfy the `import osc.conf` inside main().
    import percona_obs.obs_api as obs_api

    class _Osc:
        class conf:
            @staticmethod
            def get_config(**kw):
                pass

    monkeypatch.setitem(__import__("sys").modules, "osc", _Osc)
    monkeypatch.setitem(__import__("sys").modules, "osc.conf", _Osc.conf)

    monkeypatch.setattr(
        obs_api,
        "_fetch_obs_subproject_names",
        lambda a, p: {"isv:percona:PR:pr-1:ppg:18"},
    )
    calls: list[str] = []

    def fake_fetch(apiurl: str, full_name: str) -> set[str]:
        calls.append(full_name)
        return {"pg_tde"}

    monkeypatch.setattr(m, "fetch_present_packages", fake_fetch)
    shown = [
        _combo("", "OBS QA / ppg:18"),
        _combo("pg_tde", "OBS QA / ppg:18 / pg_tde"),
        _combo("pgbackrest", "OBS QA / ppg:18 / pgbackrest"),
    ]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(shown), ""),
    )
    m.main()
    out = json.loads(capsys.readouterr().out)
    assert [c["status_context"] for c in out] == [
        "OBS QA / ppg:18",
        "OBS QA / ppg:18 / pg_tde",
    ]
    assert calls == ["isv:percona:PR:pr-1:ppg:18"]


def test_main_skips_presence_filter_when_unset(monkeypatch, capsys):
    import json
    import subprocess

    m = _load()
    monkeypatch.setenv("OBS_APIURL", "https://obs.example")
    monkeypatch.setenv("OBS_PROJECT", "isv:percona")
    monkeypatch.delenv("QA_PACKAGES_PRESENT_ONLY", raising=False)
    monkeypatch.delenv("QA_TYPES", raising=False)

    # Import the real module first: it imports osc at module level, and the
    # stub below only has to satisfy the `import osc.conf` inside main().
    import percona_obs.obs_api as obs_api

    class _Osc:
        class conf:
            @staticmethod
            def get_config(**kw):
                pass

    monkeypatch.setitem(__import__("sys").modules, "osc", _Osc)
    monkeypatch.setitem(__import__("sys").modules, "osc.conf", _Osc.conf)

    monkeypatch.setattr(
        obs_api, "_fetch_obs_subproject_names", lambda a, p: {"isv:percona:ppg:18"}
    )

    def boom(apiurl: str, full_name: str) -> set[str]:
        raise AssertionError("presence filter must not run")

    monkeypatch.setattr(m, "fetch_present_packages", boom)
    shown = [_combo("pgbackrest", "OBS QA / ppg:18 / pgbackrest")]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(shown), ""),
    )
    m.main()
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 1 and out[0]["package_filter"] == "--package pgbackrest"
