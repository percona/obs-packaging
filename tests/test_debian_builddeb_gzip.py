"""Tree-wide check that every Debian package builds gzip-compressed .debs.

repo.percona.com rejects .debs whose members are zstd, the dpkg-deb default
on Ubuntu, so each debian/rules must override dh_builddeb with -Zgzip.  A
misspelled target (``override_dh_buildde:``) is silently never run by
debhelper, so the check looks for the exact target and its recipe rather
than for the flag anywhere in the file.
"""

import re
from pathlib import Path

import pytest

from percona_obs.common import REPO_ROOT

_TARGET = "override_dh_builddeb:"
_GZIP_CALL = re.compile(r"\bdh_builddeb\b.*\s--\s.*-Zgzip\b")


def _rules_files() -> "list[Path]":
    # rglob does not descend into symlinked package dirs, so _shared/ rules
    # are checked once through their real location.
    return sorted(
        p for p in REPO_ROOT.rglob("rules") if p.parent.name == "debian" and p.is_file()
    )


def _builddeb_recipe(text: str) -> "list[str]":
    """Recipe lines of the ``override_dh_builddeb:`` target (empty if absent)."""
    recipe: list[str] = []
    in_target = False
    for line in text.splitlines():
        if line.startswith("\t"):
            if in_target:
                recipe.append(line)
        elif line.strip() and not line.lstrip().startswith("#"):
            in_target = line.rstrip() == _TARGET
    return recipe


def test_rules_files_found():
    assert _rules_files(), "no debian/rules found under root/"


@pytest.mark.parametrize(
    "rules", _rules_files(), ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_builddeb_forces_gzip(rules: Path):
    recipe = _builddeb_recipe(rules.read_text("utf-8"))
    assert any(_GZIP_CALL.search(line) for line in recipe), (
        f"{rules.relative_to(REPO_ROOT)}: add\n\n"
        f"{_TARGET}\n\tdh_builddeb -- -Zgzip\n\n"
        "(repo.percona.com rejects zstd-compressed .debs)"
    )


@pytest.mark.parametrize(
    "text, ok",
    [
        ("override_dh_builddeb:\n\tdh_builddeb -- -Zgzip\n", True),
        ("override_dh_builddeb:\n\tdh_builddeb -- -Zgzip -z9\n", True),
        ("override_dh_buildde:\n\tdh_builddeb -- -Zgzip\n", False),
        ("override_dh_builddeb:\n\tdh_builddeb\n", False),
        ("%:\n\tdh $@\n\n# dh_builddeb -- -Zgzip\n", False),
        (
            "override_dh_builddeb:\n\n"
            "override_dh_install:\n\tdh_builddeb -- -Zgzip\n",
            False,
        ),
    ],
)
def test_builddeb_recipe_parsing(text: str, ok: bool):
    assert any(_GZIP_CALL.search(line) for line in _builddeb_recipe(text)) is ok
