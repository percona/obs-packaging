# tests/test_release_units.py
"""Unit tests for release_scope.list_release_units and the committed list."""

import json
from pathlib import Path

from percona_obs.release_scope import list_release_units


def _proj(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "project.yaml").write_text("title: T\n")


def _pkg(path: Path) -> None:
    (path / "obs").mkdir(parents=True)
    (path / "obs" / "_service").write_text("<services/>")


def _by_unit(units: "list[dict]") -> "dict[str, dict]":
    return {u["unit"]: u for u in units}


def test_major_bundles_containers_and_tarballs(tmp_path):
    base = tmp_path / "ppg/staging/18"
    _proj(base)
    _pkg(base / "percona-postgresql")
    _proj(base / "containers")
    _proj(base / "tarballs")
    units = list_release_units(tmp_path)
    assert len(units) == 1
    assert units[0] == {
        "unit": "ppg:staging:18",
        "members": [
            "ppg:staging:18",
            "ppg:staging:18:containers",
            "ppg:staging:18:tarballs",
        ],
        "release_project": "ppg:releases:18",
        "release_dir": "root/ppg/releases/18",
    }


def test_nested_units_listed_separately(tmp_path):
    base = tmp_path / "ppg/staging"
    _proj(base / "18")
    _pkg(base / "18/server")
    _proj(base / "18/extras")
    _pkg(base / "18/extras/ext")
    _proj(base / "18/extras/containers")
    _proj(base / "16")
    _proj(base / "16/tde")
    _pkg(base / "16/tde/pg_tde")
    units = _by_unit(list_release_units(tmp_path))
    assert set(units) == {
        "ppg:staging:18",
        "ppg:staging:18:extras",
        "ppg:staging:16:tde",
    }
    extras = units["ppg:staging:18:extras"]
    assert extras["members"] == [
        "ppg:staging:18:extras",
        "ppg:staging:18:extras:containers",
    ]
    assert extras["release_dir"] == "root/ppg/releases/18/extras"


def test_namespace_root_omitted(tmp_path):
    base = tmp_path / "ppg/staging/common"
    _proj(base)
    _proj(base / "tools")
    _pkg(base / "tools/etcd")
    units = list_release_units(tmp_path)
    assert [u["unit"] for u in units] == ["ppg:staging:common:tools"]
    assert units[0]["release_project"] == "ppg:releases:common:tools"


def test_unit_with_packages_only_in_containers_listed(tmp_path):
    base = tmp_path / "ppg/staging/17"
    _proj(base)
    _proj(base / "containers")
    _pkg(base / "containers/image")
    assert [u["unit"] for u in list_release_units(tmp_path)] == ["ppg:staging:17"]


def test_shared_dir_and_bundled_children_omitted(tmp_path):
    base = tmp_path / "ppg/staging"
    _proj(base / "18")
    _pkg(base / "18/server")
    _proj(base / "18/containers")
    _pkg(base / "18/containers/image")
    _proj(base / "_shared")
    _pkg(base / "_shared/pkg")
    units = [u["unit"] for u in list_release_units(tmp_path)]
    assert units == ["ppg:staging:18"]


def test_never_released_unit_listed(tmp_path):
    base = tmp_path / "ppg/staging/15"
    _proj(base)
    _pkg(base / "server")
    assert not (tmp_path / "ppg/releases").exists()
    assert [u["unit"] for u in list_release_units(tmp_path)] == ["ppg:staging:15"]


def test_sorted_by_unit(tmp_path):
    for major in ("19", "14", "17"):
        _proj(tmp_path / "ppg/staging" / major)
        _pkg(tmp_path / "ppg/staging" / major / "server")
    units = [u["unit"] for u in list_release_units(tmp_path)]
    assert units == sorted(units)


def test_committed_file_matches_tree():
    repo = Path(__file__).resolve().parent.parent
    committed = (repo / "docs/versions/release-units.json").read_text()
    assert committed == json.dumps(list_release_units(), indent=2) + "\n"
