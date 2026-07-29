"""Unit tests for vendor-aware content comparison (percona_obs.cmd_sync).

Reproduces the percona/obs-packaging PR #5 bug: pgvectorscale ships no
Cargo.lock, so cargo_vendor re-resolves the crate graph on every run and
vendor.tar.gz bytes drift with the crates.io state at generation time.  A
branch-from content check comparing raw md5s then reported "vendor.tar.gz
differs" for packages whose real inputs were untouched, promoting
percona-pgvectorscale in every extras project on unrelated PRs.
"""

from percona_obs.cmd_sync import _content_mismatches
from percona_obs.services import _has_cargo_vendor_service

SPEC = "percona-pgvectorscale.spec"
SRC = "percona-pgvectorscale_16-0.9.0.tar.gz"
VENDOR = "vendor.tar.gz"


def test_vendor_only_drift_ignored_for_cargo_packages():
    local = {SPEC: "a", SRC: "b", VENDOR: "local-bytes"}
    obs = {SPEC: "a", SRC: "b", VENDOR: "obs-bytes"}
    assert _content_mismatches(local, obs, ignore_vendor=True) == []


def test_vendor_drift_reported_without_cargo_vendor_service():
    local = {SPEC: "a", VENDOR: "local-bytes"}
    obs = {SPEC: "a", VENDOR: "obs-bytes"}
    assert _content_mismatches(local, obs, ignore_vendor=False) == [VENDOR]


def test_real_change_still_reported_alongside_vendor_drift():
    local = {SPEC: "changed", SRC: "b", VENDOR: "local-bytes"}
    obs = {SPEC: "a", SRC: "b", VENDOR: "obs-bytes"}
    assert _content_mismatches(local, obs, ignore_vendor=True) == [SPEC]


def test_vendor_missing_on_obs_is_a_mismatch():
    local = {SPEC: "a", VENDOR: "local-bytes"}
    obs = {SPEC: "a"}
    assert _content_mismatches(local, obs, ignore_vendor=True) == [VENDOR]


def test_vendor_missing_locally_is_a_mismatch():
    local = {SPEC: "a"}
    obs = {SPEC: "a", VENDOR: "obs-bytes"}
    assert _content_mismatches(local, obs, ignore_vendor=True) == [VENDOR]


def test_other_compressions_ignored_too():
    local = {SPEC: "a", "vendor.tar.xz": "x", "vendor.tar.zst": "y"}
    obs = {SPEC: "a", "vendor.tar.xz": "p", "vendor.tar.zst": "q"}
    assert _content_mismatches(local, obs, ignore_vendor=True) == []


def test_identical_content_has_no_mismatches():
    local = {SPEC: "a", SRC: "b"}
    obs = {SPEC: "a", SRC: "b"}
    assert _content_mismatches(local, obs, ignore_vendor=False) == []


def test_has_cargo_vendor_service(tmp_path):
    with_vendor = tmp_path / "with" / "_service"
    with_vendor.parent.mkdir()
    with_vendor.write_text(
        "<services>"
        '<service mode="buildtime" name="cargo_vendor">'
        '<param name="compression">gz</param>'
        "</service>"
        "</services>"
    )
    without_vendor = tmp_path / "without" / "_service"
    without_vendor.parent.mkdir()
    without_vendor.write_text(
        '<services><service mode="buildtime" name="tar" /></services>'
    )
    assert _has_cargo_vendor_service(with_vendor) is True
    assert _has_cargo_vendor_service(without_vendor) is False
    assert _has_cargo_vendor_service(tmp_path / "missing" / "_service") is False
