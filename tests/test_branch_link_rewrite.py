"""Unit tests for --branch-from _link/_aggregate handling (percona_obs.cmd_sync).

Reproduces the broken-link sync failure: a promoted package's _link targeted
a package in an active PR subproject where the target package itself was NOT
promoted, so the link pointed at a nonexistent package and OBS rejected the
commit.  The rewrite must decide per (project, package) — not per project —
and redirect references to non-promoted packages to the branch-source
(production) namespace.

Also covers the source-level dep edges derived from local _link files: a
linking package builds its target's sources, so promoting the target must
promote the linking package too (OBS _builddepinfo does not model this).
"""

from percona_obs.cmd_sync import (
    _collect_link_dep_edges,
    _parse_link_target,
    _rewrite_aggregate_for_branch,
    _rewrite_link_for_branch,
)
from percona_obs.common import REPO_ROOT, auto_rootprj_env

ROOTPRJ = "home:Admin:PR:pr-9"
BRANCH = "home:Admin:percona"
STAGING = f"{ROOTPRJ}:ppg:staging:18"
STAGING_PROD = f"{BRANCH}:ppg:staging:18"
DEPS = f"{ROOTPRJ}:ppg:common:deps"
DEPS_PROD = f"{BRANCH}:ppg:common:deps"

LINK = f'<link project="{STAGING}" package="percona-ppg-server" />'


def _link_proj(xml: str) -> str:
    import xml.etree.ElementTree as ET

    return ET.fromstring(xml).get("project", "")


def _agg_projs(xml: str) -> list[str]:
    import xml.etree.ElementTree as ET

    return [agg.get("project", "") for agg in ET.fromstring(xml).findall("aggregate")]


# --- _rewrite_link_for_branch ------------------------------------------------


def test_link_kept_when_target_package_promoted():
    promoted = {(STAGING, "percona-ppg-server")}
    out = _rewrite_link_for_branch(
        LINK, ROOTPRJ, BRANCH, promoted, "percona-ppg-server"
    )
    assert _link_proj(out) == STAGING


def test_link_redirected_when_target_package_not_promoted():
    # The target PROJECT is active (another package was promoted there), but
    # the target PACKAGE itself was not — the exact scenario that made OBS
    # reject the commit because the link target did not exist.
    promoted = {(STAGING, "percona-pgaudit")}
    out = _rewrite_link_for_branch(
        LINK, ROOTPRJ, BRANCH, promoted, "percona-ppg-server"
    )
    assert _link_proj(out) == STAGING_PROD


def test_link_redirected_when_nothing_promoted():
    out = _rewrite_link_for_branch(LINK, ROOTPRJ, BRANCH, set(), "percona-ppg-server")
    assert _link_proj(out) == STAGING_PROD


def test_link_redirected_when_promoted_keys_unknown():
    # promoted_keys=None (no promotion info, e.g. legacy callers) must keep
    # the conservative always-redirect behaviour.
    out = _rewrite_link_for_branch(LINK, ROOTPRJ, BRANCH, None, "percona-ppg-server")
    assert _link_proj(out) == STAGING_PROD


def test_link_without_package_attr_uses_own_package_name():
    link = f'<link project="{STAGING}" />'
    promoted = {(STAGING, "percona-ppg-server")}
    out = _rewrite_link_for_branch(
        link, ROOTPRJ, BRANCH, promoted, "percona-ppg-server"
    )
    assert _link_proj(out) == STAGING

    out = _rewrite_link_for_branch(link, ROOTPRJ, BRANCH, promoted, "percona-patroni")
    assert _link_proj(out) == STAGING_PROD


def test_link_outside_rootprj_untouched():
    link = '<link project="openSUSE.org:server:database" package="pg" />'
    out = _rewrite_link_for_branch(link, ROOTPRJ, BRANCH, None, "pg")
    assert out == link


# --- _rewrite_aggregate_for_branch -------------------------------------------


def _agg(project: str, *packages: str) -> str:
    pkg_elems = "".join(f"<package>{p}</package>" for p in packages)
    return f"<aggregatelist><aggregate project={project!r}>{pkg_elems}</aggregate></aggregatelist>"


def test_aggregate_kept_when_all_packages_promoted():
    promoted = {(DEPS, "etcd")}
    out = _rewrite_aggregate_for_branch(_agg(DEPS, "etcd"), ROOTPRJ, BRANCH, promoted)
    assert _agg_projs(out) == [DEPS]


def test_aggregate_redirected_when_package_not_promoted():
    # Project active (telemetry-agent promoted) but etcd not promoted there.
    promoted = {(DEPS, "percona-telemetry-agent")}
    out = _rewrite_aggregate_for_branch(_agg(DEPS, "etcd"), ROOTPRJ, BRANCH, promoted)
    assert _agg_projs(out) == [DEPS_PROD]


def test_aggregate_multibuild_flavor_checked_by_base_name():
    promoted = {(DEPS, "percona-pg-telemetry")}
    out = _rewrite_aggregate_for_branch(
        _agg(DEPS, "percona-pg-telemetry:17"), ROOTPRJ, BRANCH, promoted
    )
    assert _agg_projs(out) == [DEPS]


def test_aggregate_redirected_when_promoted_keys_unknown():
    out = _rewrite_aggregate_for_branch(_agg(DEPS, "etcd"), ROOTPRJ, BRANCH, None)
    assert _agg_projs(out) == [DEPS_PROD]


def test_aggregate_elements_rewritten_independently():
    xml = (
        "<aggregatelist>"
        f"<aggregate project={DEPS!r}><package>etcd</package></aggregate>"
        f"<aggregate project={STAGING!r}><package>percona-pgaudit</package></aggregate>"
        "</aggregatelist>"
    )
    promoted = {(STAGING, "percona-pgaudit")}
    out = _rewrite_aggregate_for_branch(xml, ROOTPRJ, BRANCH, promoted)
    assert _agg_projs(out) == [DEPS_PROD, STAGING]


def test_aggregate_outside_rootprj_untouched():
    xml = _agg("openSUSE.org:devel:languages:python", "python3-yaml")
    out = _rewrite_aggregate_for_branch(xml, ROOTPRJ, BRANCH, None)
    assert out == xml


# --- _parse_link_target -------------------------------------------------------


def test_parse_link_target_explicit_attrs():
    assert _parse_link_target(LINK, "defproj", "defpkg") == (
        STAGING,
        "percona-ppg-server",
    )


def test_parse_link_target_defaults():
    assert _parse_link_target("<link />", "defproj", "defpkg") == ("defproj", "defpkg")


def test_parse_link_target_rejects_non_link():
    assert _parse_link_target("<aggregatelist />", "p", "k") is None
    assert _parse_link_target("not xml", "p", "k") is None


# --- _collect_link_dep_edges ---------------------------------------------------


def test_collect_link_dep_edges_from_real_tree():
    # root/ppg/staging/16/tde/percona-haproxy/obs/_link targets
    # ${OBS_ROOTPRJ}:ppg:staging:16 / percona-haproxy.
    tde_proj = f"{ROOTPRJ}:ppg:staging:16:tde"
    target_proj = f"{ROOTPRJ}:ppg:staging:16"
    pkg_path = REPO_ROOT / "ppg" / "staging" / "16" / "tde" / "percona-haproxy"
    decisions = {
        (target_proj, "percona-haproxy"): "promote",
        (tde_proj, "percona-haproxy"): "aggregate",
    }
    edges = _collect_link_dep_edges(
        [(tde_proj, pkg_path)], auto_rootprj_env(ROOTPRJ), decisions
    )
    assert edges == {(target_proj, "percona-haproxy"): {(tde_proj, "percona-haproxy")}}


def test_collect_link_dep_edges_ignores_targets_outside_sync_scope():
    tde_proj = f"{ROOTPRJ}:ppg:staging:16:tde"
    pkg_path = REPO_ROOT / "ppg" / "staging" / "16" / "tde" / "percona-haproxy"
    decisions = {(tde_proj, "percona-haproxy"): "aggregate"}
    edges = _collect_link_dep_edges(
        [(tde_proj, pkg_path)], auto_rootprj_env(ROOTPRJ), decisions
    )
    assert edges == {}


def test_collect_link_dep_edges_skips_packages_without_link():
    proj = f"{ROOTPRJ}:ppg:staging:14"
    pkg_path = REPO_ROOT / "ppg" / "staging" / "14" / "etcd"  # _aggregate, no _link
    edges = _collect_link_dep_edges(
        [(proj, pkg_path)], auto_rootprj_env(ROOTPRJ), {(proj, "etcd"): "promote"}
    )
    assert edges == {}
