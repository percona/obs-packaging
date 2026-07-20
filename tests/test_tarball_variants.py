"""The tarball package files must stay byte-identical across SSL variants.

Variant identity lives exclusively in each subproject's macros.yaml and
project.yaml; simpleimage and build-tarball.sh are deliberate copies."""

from pathlib import Path

import pytest

TARBALLS_ROOT = (
    Path(__file__).parent.parent / "root" / "ppg" / "staging" / "17" / "tarballs"
)
VARIANTS = ["ssl1.1", "ssl3", "ssl3.5"]
PACKAGE = "percona-postgresql-tarball"


@pytest.mark.parametrize("filename", ["simpleimage", "build-tarball.sh"])
def test_variant_copies_identical(filename: str) -> None:
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
