"""Unit tests for OBS dep-cascade provider resolution (percona_obs.obs_api).

Reproduces the PR #139 bug: ppg:devel:18, ppg:staging:18 and
ppg:staging:18:extras all build percona-postgresql with identical binary
names; the resolver must attribute each consumer's dep edge to the tier its
build environment actually uses (own project first, then repo path chain),
regardless of project iteration order.
"""

from percona_obs.obs_api import _parse_repo_path_projects, _resolve_provider

DEVEL = "isv:percona:ppg:devel:18"
STAGING = "isv:percona:ppg:staging:18"
EXTRAS = "isv:percona:ppg:staging:18:extras"
UBI9 = "isv:percona:ppg:staging:18:containers:ubi9"
DEPS = "isv:percona:ppg:common:deps"

PG_DEVEL_BIN = "percona-postgresql18-devel"
OIDC_BIN = "percona-pg_oidc_validator18"


def _providers():
    return {
        DEVEL: {
            PG_DEVEL_BIN: (DEVEL, "percona-postgresql"),
            OIDC_BIN: (DEVEL, "percona-pg_oidc_validator"),
        },
        STAGING: {
            PG_DEVEL_BIN: (STAGING, "percona-postgresql"),
            OIDC_BIN: (STAGING, "percona-pg_oidc_validator"),
        },
        EXTRAS: {
            PG_DEVEL_BIN: (EXTRAS, "percona-postgresql"),
        },
        DEPS: {
            "etcd": (DEPS, "etcd"),
        },
    }


def _globals(providers):
    out = {}
    for provider_map in providers.values():
        for binary, provider in provider_map.items():
            out.setdefault(binary, set()).add(provider)
    return out


# First-level <path> chains as verified on api.opensuse.org (2026-07-13).
CHAINS = {
    DEVEL: [STAGING, DEPS],
    STAGING: [DEPS],
    EXTRAS: [DEPS, STAGING],
    UBI9: [UBI9, STAGING, DEPS],
}


def test_own_project_beats_sibling_tier():
    providers = _providers()
    assert _resolve_provider(
        STAGING, PG_DEVEL_BIN, providers, CHAINS[STAGING], _globals(providers)
    ) == (STAGING, "percona-postgresql")


def test_devel_consumer_resolves_to_devel():
    # devel:18 paths into staging:18, but its own project must win.
    providers = _providers()
    assert _resolve_provider(
        DEVEL, PG_DEVEL_BIN, providers, CHAINS[DEVEL], _globals(providers)
    ) == (DEVEL, "percona-postgresql")


def test_container_resolves_via_path_chain_not_sibling():
    # containers:ubi9 builds no RPMs itself; its images repo paths into
    # staging:18 — a devel:18 provider must never be chosen.
    providers = _providers()
    assert _resolve_provider(
        UBI9, OIDC_BIN, providers, CHAINS[UBI9], _globals(providers)
    ) == (STAGING, "percona-pg_oidc_validator")


def test_unique_global_provider_fallback():
    # Binary provided by exactly one queried project resolves even with an
    # empty/incomplete path chain.
    providers = _providers()
    assert _resolve_provider(UBI9, "etcd", providers, [], _globals(providers)) == (
        DEPS,
        "etcd",
    )


def test_ambiguous_binary_outside_chain_is_dropped():
    # Multiple providers, none visible through the consumer's chain: the
    # edge must be dropped (None), not guessed.
    providers = _providers()
    assert (
        _resolve_provider(DEPS, PG_DEVEL_BIN, providers, [], _globals(providers))
        is None
    )


def test_resolution_independent_of_insertion_order():
    # The old flat provided_by dict was last-write-wins over set iteration
    # order (PYTHONHASHSEED-dependent).  The resolver must give the same
    # answer for any insertion order.
    providers = _providers()
    reordered = dict(reversed(list(providers.items())))
    for candidate in (providers, reordered):
        assert _resolve_provider(
            STAGING, PG_DEVEL_BIN, candidate, CHAINS[STAGING], _globals(candidate)
        ) == (STAGING, "percona-postgresql")


META_XML = """\
<project name="isv:percona:ppg:staging:18:extras">
  <repository name="UBI_9">
    <path project="isv:percona:ppg:common:deps" repository="UBI_9"/>
    <path project="isv:percona:common:deps:build" repository="UBI_9"/>
    <path project="isv:percona:ppg:staging:18" repository="UBI_9"/>
    <path project="RedHat:UBI-9" repository="standard"/>
    <arch>x86_64</arch>
  </repository>
  <repository name="Debian_13">
    <path project="isv:percona:ppg:staging:18" repository="Debian_13"/>
  </repository>
</project>
"""


def test_parse_repo_path_projects():
    assert _parse_repo_path_projects(META_XML, "UBI_9") == [
        "isv:percona:ppg:common:deps",
        "isv:percona:common:deps:build",
        "isv:percona:ppg:staging:18",
        "RedHat:UBI-9",
    ]
    assert _parse_repo_path_projects(META_XML, "Debian_13") == [
        "isv:percona:ppg:staging:18"
    ]
    assert _parse_repo_path_projects(META_XML, "missing") == []
    assert _parse_repo_path_projects("not xml <", "UBI_9") == []
