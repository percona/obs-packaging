"""Unit tests for the --only-repos project-meta filter (percona_obs.obs_api).

SSL-variant tarball repos (ssl1.1/ssl3/ssl3.5) must always survive the filter,
because their names never match a label-derived --only-repos set."""

from percona_obs.obs_api import _filter_meta_repos


def _names(repos):
    return [r["name"] for r in repos]


def test_none_is_passthrough():
    repos = [{"name": "RockyLinux_8"}, {"name": "RockyLinux_9"}]
    assert _filter_meta_repos(repos, None) == repos


def test_standard_filter_drops_non_matching():
    repos = [{"name": "RockyLinux_8"}, {"name": "RockyLinux_9"}, {"name": "Debian_13"}]
    assert _names(_filter_meta_repos(repos, {"RockyLinux_9"})) == ["RockyLinux_9"]


def test_ssl_repos_survive_non_matching_filter():
    repos = [{"name": "ssl1.1"}, {"name": "ssl3"}]
    # A distro-base label like RockyLinux_9 matches neither ssl repo, but both
    # must be kept — otherwise the tarball project meta would be emptied.
    assert _names(_filter_meta_repos(repos, {"RockyLinux_9"})) == ["ssl1.1", "ssl3"]


def test_mixed_project_keeps_matched_standard_and_all_ssl():
    repos = [
        {"name": "RockyLinux_8"},
        {"name": "RockyLinux_9"},
        {"name": "ssl1.1"},
        {"name": "ssl3"},
        {"name": "ssl3.5"},
    ]
    assert _names(_filter_meta_repos(repos, {"RockyLinux_9"})) == [
        "RockyLinux_9",
        "ssl1.1",
        "ssl3",
        "ssl3.5",
    ]


def test_ssl_repo_also_matched_by_name_not_duplicated():
    repos = [{"name": "ssl3"}, {"name": "RockyLinux_9"}]
    # ssl3 is both name-matched and ssl-prefixed; it appears exactly once.
    assert _names(_filter_meta_repos(repos, {"ssl3"})) == ["ssl3"]


def test_empty_only_repos_still_keeps_ssl():
    # An empty set means "no standard repo selected"; ssl repos still survive.
    repos = [{"name": "RockyLinux_9"}, {"name": "ssl3"}]
    assert _names(_filter_meta_repos(repos, set())) == ["ssl3"]
