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


def test_sibling_path_reference_keeps_filtered_repo():
    # PR #2 regression (project_save_error on OBS): ssl3 lists this project's
    # own RockyLinux_9.6 helper repo as a build path. A label-derived filter
    # ({RockyLinux_9, RockyLinux_8}) would drop RockyLinux_9.6 while the ssl*
    # exemption keeps ssl3, emitting meta whose <path> references a repository
    # element that does not exist — OBS rejects the whole meta. Repos
    # referenced by kept repos' same-project paths must survive the filter.
    repos = [
        {
            "name": "RockyLinux_9.6",
            "paths": [{"subproject": "ppg:staging:17", "repository": "RockyLinux_9.6"}],
        },
        {"name": "RockyLinux_8", "paths": []},
        {
            "name": "ssl3",
            "paths": [
                {
                    "subproject": "ppg:staging:17:tarballs",
                    "repository": "RockyLinux_9.6",
                },
                {"subproject": "ppg:staging:17", "repository": "RockyLinux_9.6"},
            ],
        },
    ]
    assert _names(
        _filter_meta_repos(
            repos, {"RockyLinux_9", "RockyLinux_8"}, "ppg:staging:17:tarballs"
        )
    ) == ["RockyLinux_9.6", "RockyLinux_8", "ssl3"]


def test_sibling_reference_closure_is_transitive():
    # A kept repo's sibling reference may itself reference another sibling.
    repos = [
        {"name": "a", "paths": [{"subproject": "me", "repository": "b"}]},
        {"name": "b", "paths": [{"subproject": "me", "repository": "c"}]},
        {"name": "c", "paths": []},
        {"name": "d", "paths": []},
        {"name": "ssl3", "paths": [{"subproject": "me", "repository": "a"}]},
    ]
    assert _names(_filter_meta_repos(repos, set(), "me")) == ["a", "b", "c", "ssl3"]


def test_cross_project_path_does_not_keep_same_named_repo():
    # A kept repo pointing at ANOTHER project's repository must not rescue a
    # local repo that merely shares that repository name.
    repos = [
        {"name": "standard", "paths": []},
        {
            "name": "ssl3",
            "paths": [{"project": "RockyLinux:9.6", "repository": "standard"}],
        },
    ]
    assert _names(_filter_meta_repos(repos, set(), "ppg:staging:17:tarballs")) == [
        "ssl3"
    ]


def test_no_self_subproject_disables_sibling_closure():
    # Callers that cannot express project identity keep the old behavior.
    repos = [
        {"name": "helper", "paths": []},
        {"name": "ssl3", "paths": [{"subproject": "me", "repository": "helper"}]},
    ]
    assert _names(_filter_meta_repos(repos, set())) == ["ssl3"]
