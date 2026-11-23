import pytest
from percona_obs.release_changes import classify_change, split_versrel


@pytest.mark.parametrize(
    "versrel, expected",
    [
        ("2.60.0-4.2.el9", ("2.60.0", "4")),
        ("3.5.26-6.1", ("3.5.26", "6")),
        ("17.11-1", ("17.11", "1")),
        ("4.2.0-6+7.3.bookworm", ("4.2.0", "7")),
        ("2.9.0.post0-3.1.el8", ("2.9.0.post0", "3")),
        ("1.19", ("1.19", None)),
    ],
)
def test_split_versrel(versrel, expected):
    assert split_versrel(versrel) == expected


@pytest.mark.parametrize(
    "old, new, kind",
    [
        ("5.0-5.1.el10", "6.0-1.2.el10", "version"),
        (
            "2.4.1-4.3.el10",
            "2.4.0-3.1.el10",
            "version",
        ),  # downgrade is a version change
        ("17.1-5.6.el10", "17.1-6.2.el10", "packaging"),
        ("2.60.0-4.1.el10", "2.60.0-4.2.el10", "rebuild"),
        ("2.60.0-4.1.el10", "2.60.0-4.1.el10", "rebuild"),
        ("4.2.0-6+7.3.bookworm", "4.2.0-7.5", "rebuild"),
        ("4.2.0-6+7.3.bookworm", "4.2.0-8.1", "packaging"),
        ("1.19", "1.19", "rebuild"),
        ("1.19", "1.19-2.1", "packaging"),
    ],
)
def test_classify_change(old, new, kind):
    assert classify_change(old, new) == kind
