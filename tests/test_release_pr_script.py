"""Pure helpers of the release-PR workflow (.github/scripts/release_pr.py)."""

import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).parent.parent / ".github/scripts"


def _load():
    spec = importlib.util.spec_from_file_location("release_pr", _SCRIPTS / "release_pr.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_classify_files():
    m = _load()
    assert m.classify_files(
        ["root/ppg/releases/18/release.yaml", "root/ppg/releases/18/CHANGELOG.md", "docs/x.md"]
    ) == ("release", ["root/ppg/releases/18/release.yaml"])
    assert m.classify_files(["root/ppg/releases/18/release.yaml", "root/ppg/staging/18/x/rpm/x.spec"])[0] == "mixed"
    assert m.classify_files(["docs/x.md"]) == ("none", [])


def test_release_projects():
    m = _load()
    assert m.release_projects(
        ["root/ppg/releases/18/release.yaml", "root/ppg/releases/17/release.yaml", "root/ppg/releases/18/release.yaml"]
    ) == ["ppg:releases:17", "ppg:releases:18"]


def test_conflicting_prs_only_older_same_file():
    m = _load()
    mine = ["root/ppg/releases/18/release.yaml"]
    others = [
        {"number": 10, "files": ["root/ppg/releases/18/release.yaml"]},
        {"number": 12, "files": ["root/ppg/releases/18/release.yaml"]},  # newer: not a conflict for 11
        {"number": 9, "files": ["root/ppg/releases/17/release.yaml"]},
        {"number": 11, "files": mine},  # self
    ]
    assert m.conflicting_prs(11, mine, others) == [(10, "root/ppg/releases/18/release.yaml")]


def test_prerelease_project():
    m = _load()
    assert m.prerelease_project("isv:percona:PR", 42, "ppg:releases:18") == "isv:percona:PR:pr-42:ppg:releases:18"
