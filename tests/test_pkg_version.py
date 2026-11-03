"""Upstream version from obs/_service and the PKG_REVISION seed lookup."""

from pathlib import Path

from percona_obs.pkg_version import (
    PKG_REVISION_FLOORS,
    compute_pkg_revision,
    extract_version_from_service,
    extract_version_from_service_text,
)


def _scm(**params) -> str:
    body = "".join(f'<param name="{k}">{v}</param>' for k, v in params.items())
    return f'<services><service name="obs_scm">{body}</service></services>'


def test_version_param_wins():
    text = _scm(
        url="u", revision="REL4_2_0", version="4.2.0", versionformat="@PARENT_TAG@"
    )
    assert extract_version_from_service_text(text) == "4.2.0"


def test_rewrite_pattern_with_replacement_like_tar_scm():
    text = _scm(
        url="u",
        revision="REL-9_17",
        versionformat="@PARENT_TAG@",
        **{
            "versionrewrite-pattern": r"REL-(\d+)_(\d+)",
            "versionrewrite-replacement": r"\1.\2",
        },
    )
    assert extract_version_from_service_text(text) == "9.17"


def test_rewrite_pattern_without_replacement_defaults_to_group_one():
    text = _scm(
        url="u",
        revision="v1.6.8",
        versionformat="@PARENT_TAG@",
        **{"versionrewrite-pattern": r"v(.*)"},
    )
    assert extract_version_from_service_text(text) == "1.6.8"


def test_pg_similarity_tag_rewrite():
    text = _scm(
        url="u",
        revision="pg_similarity_1_0",
        versionformat="@PARENT_TAG@",
        **{
            "versionrewrite-pattern": r"pg_similarity_(\d+)_(\d+)",
            "versionrewrite-replacement": r"\1.\2",
        },
    )
    assert extract_version_from_service_text(text) == "1.0"


SHA = "0123456789abcdef0123456789abcdef01234567"


def test_sha_revision_offline_is_none():
    text = _scm(
        url="https://example.org/x.git", revision=SHA, versionformat="@PARENT_TAG@"
    )
    assert extract_version_from_service_text(text) is None


def test_sha_revision_with_resolver_uses_tag_and_pattern():
    text = _scm(
        url="https://example.org/x.git",
        revision=SHA,
        versionformat="@PARENT_TAG@",
        **{"versionrewrite-pattern": r"v(.*)"},
    )
    calls = []

    def resolver(url, sha):
        calls.append((url, sha))
        return "v2.0"

    assert extract_version_from_service_text(text, resolve_tag=resolver) == "2.0"
    assert calls == [("https://example.org/x.git", SHA)]


def test_packaging_obs_scm_is_skipped():
    text = (
        '<services><service name="obs_scm"><param name="filename">debian</param>'
        '<param name="revision">main</param></service>'
        '<service name="obs_scm"><param name="revision">1.2.3</param>'
        '<param name="filename">pkg</param></service></services>'
    )
    assert extract_version_from_service_text(text) == "1.2.3"


def test_env_token_revision_is_none():
    text = _scm(url="u", revision="${PG_REF}", versionformat="@PARENT_TAG@")
    assert extract_version_from_service_text(text) is None


def test_unparsable_file_is_none(tmp_path: Path):
    f = tmp_path / "_service"
    f.write_text("<services><service></services>")
    assert extract_version_from_service(f) is None
    assert extract_version_from_service(tmp_path / "missing") is None


def test_compute_pkg_revision_seed_hit_and_miss():
    assert compute_pkg_revision("ppg:staging:17", "percona-pgaudit", "17.1") == "5"
    assert (
        compute_pkg_revision("ppg:staging:17", "percona-pgaudit_set_user", "4.2.0")
        == "7"
    )
    assert compute_pkg_revision("ppg:staging:17", "percona-pgaudit", "17.2") == "1"
    assert compute_pkg_revision("ppg:staging:19", "percona-pgaudit", "17.1") == "1"
    assert compute_pkg_revision("ppg:common:deps", "ydiff", "1.4.2") == "4"


def test_seed_table_values_are_positive_ints():
    for key, value in PKG_REVISION_FLOORS.items():
        assert len(key) == 3 and all(isinstance(k, str) and k for k in key)
        assert isinstance(value, int) and value >= 1
