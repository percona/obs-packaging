"""The tarball package files must stay byte-identical across SSL variants.

Variant identity lives exclusively in each subproject's macros.yaml and
project.yaml; simpleimage and build-tarball.sh are deliberate copies."""

from pathlib import Path

import pytest

TARBALLS_ROOT = (
    Path(__file__).parent.parent / "root" / "ppg" / "staging" / "17" / "tarballs"
)
PACKAGE = "percona-postgresql-tarball"
# Derived from the tree so new variant subprojects are covered automatically.
VARIANTS = sorted(d.name for d in TARBALLS_ROOT.iterdir() if (d / PACKAGE).is_dir())


@pytest.mark.parametrize("filename", ["simpleimage", "build-tarball.sh"])
def test_variant_copies_identical(filename: str) -> None:
    assert "ssl3" in VARIANTS, f"reference variant ssl3 missing from {TARBALLS_ROOT}"
    contents = {
        variant: (TARBALLS_ROOT / variant / PACKAGE / "obs" / filename).read_bytes()
        for variant in VARIANTS
    }
    reference = contents["ssl3"]
    for variant, data in contents.items():
        assert data == reference, (
            f"{filename} in {variant} diverges from ssl3 — "
            "variant differences belong in macros.yaml/project.yaml"
        )
