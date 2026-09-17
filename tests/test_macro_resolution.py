"""Tree-wide checks that every referenced macro resolves.

These run against the real root/ tree, so they catch a declaration removed
without a replacement — the failure mode that would otherwise only show up as
an aborted sync.
"""

from pathlib import Path

import pytest

from percona_obs.common import REPO_ROOT, load_macros
from percona_obs.git_utils import _referenced_macros


def _dirs_referencing_ppg_release() -> "list[Path]":
    hits: set[Path] = set()
    for f in REPO_ROOT.rglob("*"):
        if not f.is_file() or f.name == "macros.yaml":
            continue
        try:
            text = f.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "%!{PPG_RELEASE}" in text:
            # obs/Dockerfile and rpm/*.spec live one level below the package dir
            hits.add(f.parent.parent)
    return sorted(hits)


def test_tree_has_no_ppg_release_declaration():
    declared = []
    for f in REPO_ROOT.rglob("macros.yaml"):
        for line in f.read_text("utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            if line.strip().startswith("- PPG_RELEASE:"):
                declared.append(str(f.relative_to(REPO_ROOT)))
    assert declared == [], f"PPG_RELEASE is now computed, remove: {declared}"


@pytest.mark.parametrize("pkg_dir", _dirs_referencing_ppg_release(), ids=str)
def test_every_referencing_package_resolves_the_macro(pkg_dir):
    macros = load_macros(pkg_dir)
    assert "PPG_RELEASE" in macros
    assert macros["PPG_RELEASE"].isdigit()


def test_referenced_macros_all_resolve():
    for pkg_dir in _dirs_referencing_ppg_release():
        macros = load_macros(pkg_dir)
        missing = _referenced_macros(pkg_dir) - set(macros)
        assert missing == set(), f"{pkg_dir}: unresolved {sorted(missing)}"
