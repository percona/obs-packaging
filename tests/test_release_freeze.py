# tests/test_release_freeze.py
"""Unit tests for percona_obs.release_freeze.

All OBS traffic is faked: fetch_project_results is driven by canned _result
XML via a monkeypatched http_GET, and meta round-trips are captured through
a monkeypatched _edit_project_meta.
"""

import pytest

import percona_obs.release_freeze as rf


def _result_xml(entries, repo_state="published", dirty=False):
    """entries: list of (pkg, repo, arch, code)."""
    by_repo = {}
    for pkg, repo, arch, code in entries:
        by_repo.setdefault((repo, arch), []).append((pkg, code))
    parts = ["<resultlist>"]
    for (repo, arch), pkgs in by_repo.items():
        dirty_attr = ' dirty="true"' if dirty else ""
        parts.append(
            f'<result project="p" repository="{repo}" arch="{arch}" '
            f'state="{repo_state}"{dirty_attr}>'
        )
        for pkg, code in pkgs:
            parts.append(f'<status package="{pkg}" code="{code}"/>')
        parts.append("</result>")
    parts.append("</resultlist>")
    return "".join(parts).encode()


class _Resp:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data


def _patch_results(monkeypatch, xml_bytes):
    monkeypatch.setattr(rf.osc.core, "makeurl", lambda *a: "http://x")
    monkeypatch.setattr(rf.osc.connection, "http_GET", lambda url: _Resp(xml_bytes))


def test_fetch_project_results_parses_codes_and_states(monkeypatch):
    _patch_results(
        monkeypatch,
        _result_xml(
            [("a", "R9", "x86_64", "succeeded"), ("b", "R9", "x86_64", "failed")]
        ),
    )
    pkg_codes, repo_states = rf.fetch_project_results("http://obs", "prj")
    assert pkg_codes[("a", "R9", "x86_64")] == "succeeded"
    assert pkg_codes[("b", "R9", "x86_64")] == "failed"
    assert repo_states[("R9", "x86_64")] == "published"


def test_dirty_repo_reports_dirty_state(monkeypatch):
    _patch_results(
        monkeypatch, _result_xml([("a", "R9", "x86_64", "succeeded")], dirty=True)
    )
    _, repo_states = rf.fetch_project_results("http://obs", "prj")
    assert repo_states[("R9", "x86_64")] == "dirty"


def test_wait_for_quiesce_returns_when_idle(monkeypatch):
    _patch_results(monkeypatch, _result_xml([("a", "R9", "x86_64", "succeeded")]))
    rf.wait_for_quiesce("http://obs", ["prj"], timeout_s=1, poll_interval_s=0)


def test_wait_for_quiesce_times_out_on_building(monkeypatch):
    _patch_results(monkeypatch, _result_xml([("a", "R9", "x86_64", "building")]))
    monkeypatch.setattr(rf.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit, match="did not quiesce"):
        rf.wait_for_quiesce("http://obs", ["prj"], timeout_s=0, poll_interval_s=0)


def test_assert_all_green_accepts_disabled_and_excluded(monkeypatch):
    _patch_results(
        monkeypatch,
        _result_xml(
            [
                ("a", "R9", "x86_64", "succeeded"),
                ("b", "R9", "x86_64", "excluded"),
                ("c", "R9", "x86_64", "disabled"),
            ]
        ),
    )
    assert rf.assert_all_green("http://obs", ["prj"]) == []


def test_assert_all_green_reports_failures(monkeypatch):
    _patch_results(monkeypatch, _result_xml([("b", "R9", "aarch64", "failed")]))
    problems = rf.assert_all_green("http://obs", ["prj"])
    assert problems == ["prj/b R9/aarch64: failed"]


def test_freeze_snapshots_and_restores_exact_meta(monkeypatch):
    orig = (
        '<project name="prj"><title/><description/>'
        '<publish><disable repository="R8"/></publish>'
        '<repository name="R8"/></project>'
    )
    written = []
    monkeypatch.setattr(
        rf.osc.core, "show_project_meta", lambda apiurl, prj: orig.encode()
    )
    monkeypatch.setattr(
        rf,
        "_edit_project_meta",
        lambda apiurl, prj, meta, force: written.append((prj, meta, force)),
    )
    snaps = rf.freeze_builds("http://obs", ["prj"])
    assert snaps == {"prj": orig}
    assert len(written) == 1
    assert "<disable" in written[0][1] and "<build>" in written[0][1]
    # publish flags survive inside the frozen meta too
    assert 'repository="R8"' in written[0][1]

    rf.restore_builds("http://obs", snaps)
    assert written[-1] == ("prj", orig, True)


def test_restore_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("obs down")

    monkeypatch.setattr(rf, "_edit_project_meta", boom)
    rf.restore_builds("http://obs", {"prj": "<project/>"})  # must not raise


def test_verify_release_landed_ok(monkeypatch):
    sets = {"src": {"a", "b"}, "rel": {"a", "b", "extra"}}
    monkeypatch.setattr(
        rf,
        "_fetch_obs_package_names",
        lambda apiurl, prj: sets["src" if "src" in prj else "rel"],
    )
    rf.verify_release_landed(
        "http://obs", "x:src", "x:rel", timeout_s=1, poll_interval_s=0
    )


def test_verify_release_landed_timeout(monkeypatch):
    monkeypatch.setattr(
        rf,
        "_fetch_obs_package_names",
        lambda apiurl, prj: {"a", "b"} if "src" in prj else {"a"},
    )
    monkeypatch.setattr(rf.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit, match="missing in x:rel"):
        rf.verify_release_landed(
            "http://obs", "x:src", "x:rel", timeout_s=0, poll_interval_s=0
        )
