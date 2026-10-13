"""Unit tests for percona_obs.release_record."""

import pytest

from percona_obs.release_record import (
    ReleaseEntry,
    current_release,
    dump_release_entry,
    parse_release_entries,
    release_tags,
)


def test_parse_string_and_mapping_entries():
    data = {
        "releases": [
            "ppg/18.4-1",
            {"tag": "ppg/18.6-1"},
            {"tag": "ppg/18.7-1", "source_commit": "abc123"},
        ]
    }
    assert parse_release_entries(data) == [
        ReleaseEntry("ppg/18.4-1"),
        ReleaseEntry("ppg/18.6-1"),
        ReleaseEntry("ppg/18.7-1", "abc123"),
    ]
    assert release_tags(data) == ["ppg/18.4-1", "ppg/18.6-1", "ppg/18.7-1"]
    assert current_release(data) == ReleaseEntry("ppg/18.7-1", "abc123")


def test_parse_legacy_revision_and_empty():
    assert parse_release_entries({"revision": "ppg/17.9-1"}) == [
        ReleaseEntry("ppg/17.9-1")
    ]
    assert parse_release_entries({}) == []
    assert parse_release_entries("not a dict") == []
    assert current_release({}) is None


def test_parse_rejects_garbage_entry():
    with pytest.raises(SystemExit, match="unrecognised releases entry"):
        parse_release_entries({"releases": [{"source_commit": "x"}]})


def test_dump_round_trip():
    assert dump_release_entry(ReleaseEntry("ppg/18.4-1")) == "ppg/18.4-1"
    assert dump_release_entry(ReleaseEntry("ppg/18.7-1", "abc")) == {
        "tag": "ppg/18.7-1",
        "source_commit": "abc",
    }
