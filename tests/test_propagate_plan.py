# tests/test_propagate_plan.py
"""Unit tests for the pure planning part of percona_obs.propagate.

No OBS traffic: upstream_projects reads project meta through a faked
osc.core.show_project_meta.
"""

from percona_obs import cmd_sync, common
import percona_obs.propagate as pp

R, C, I, D = "r:u", "r:u:tarballs", "r:u:containers", "r:deps"
ORDER = [D, R, C, I]


def test_closure_excludes_seeds_and_follows_transitively():
    fwd = {(R, "b"): {(R, "a")}, (R, "c"): {(R, "b")}, (R, "x"): {(R, "y")}}
    assert pp.closure({(R, "a")}, fwd) == {(R, "b"), (R, "c")}


def test_closure_wildcard_matches_any_package_of_project():
    fwd = {(R, "agg"): {(D, "*")}, (R, "b"): {(R, "agg")}}
    assert pp.closure({(D, "lib")}, fwd) == {(R, "agg"), (R, "b")}


def test_same_project_dependents_one_stage():
    fwd = {(R, "b"): {(R, "a")}, (R, "c"): {(R, "b")}}
    st = pp.plan_stages({(R, "a")}, fwd, {R}, ORDER, set())
    assert st == [pp.Stage(frozenset({(R, "a")}), {R: ["b", "c"]})]


def test_children_come_after_root_and_wait_for_it():
    fwd = {(R, "b"): {(R, "a")}, (I, "img"): {(R, "b")}, (C, "t"): {(R, "a")}}
    st = pp.plan_stages({(R, "a")}, fwd, {R, C, I}, ORDER, set())
    assert [s.trigger for s in st] == [{R: ["b"]}, {C: ["t"]}, {I: ["img"]}]
    assert (R, "b") in st[2].wait_for and (R, "a") in st[1].wait_for


def test_seed_outside_frozen_unit_reaches_it():
    fwd = {(D, "mid"): {(D, "lib")}, (R, "b"): {(D, "mid")}}
    st = pp.plan_stages({(D, "lib")}, fwd, {R}, ORDER, set())
    assert st[0].trigger == {R: ["b"]}
    assert {(D, "lib"), (D, "mid")} <= st[0].wait_for


def test_aggregates_first_within_project():
    fwd = {(R, "agg"): {(D, "lib")}, (R, "b"): {(R, "agg")}}
    st = pp.plan_stages({(D, "lib")}, fwd, {R}, ORDER, {(R, "agg")})
    assert [s.trigger for s in st] == [{R: ["agg"]}, {R: ["b"]}]
    assert (R, "agg") in st[1].wait_for


def test_same_project_aggregate_of_dependent_comes_after_it():
    fwd = {(R, "x"): {(D, "lib")}, (R, "agg"): {(R, "x")}}
    st = pp.plan_stages({(D, "lib")}, fwd, {R}, ORDER, {(R, "agg")})
    assert [s.trigger for s in st] == [{R: ["x"]}, {R: ["agg"]}]
    assert (D, "lib") in st[0].wait_for
    assert (R, "x") in st[1].wait_for


def test_graph_order_beats_project_order():
    fwd = {(R, "b"): {(R, "a")}, (I, "img"): {(R, "b")}}
    st = pp.plan_stages({(R, "a")}, fwd, {R, I}, [I, C, R, D], set())
    assert [s.trigger for s in st] == [{R: ["b"]}, {I: ["img"]}]
    assert (R, "b") in st[1].wait_for


def test_frozen_projects_in_a_cycle_share_one_stage():
    fwd = {(R, "b"): {(R, "a"), (C, "t")}, (C, "t"): {(R, "b")}}
    st = pp.plan_stages({(R, "a")}, fwd, {R, C}, ORDER, set())
    assert [s.trigger for s in st] == [{R: ["b"], C: ["t"]}]
    assert (R, "a") in st[0].wait_for


def test_frozen_seed_depending_on_another_seed_is_triggered():
    fwd = {(R, "b"): {(R, "a")}}
    st = pp.plan_stages({(R, "a"), (R, "b")}, fwd, {R}, ORDER, set())
    assert len(st) == 1
    assert (R, "a") in st[0].wait_for
    assert st[0].trigger == {R: ["b"]}


def test_non_frozen_seed_depending_on_another_seed_is_not_triggered():
    fwd = {(R, "b"): {(R, "a")}}
    assert pp.plan_stages({(R, "a"), (R, "b")}, fwd, set(), ORDER, set()) == []


def test_extra_members_are_triggered_and_wait_for_seeds():
    st = pp.plan_stages({(D, "lib")}, {}, {R}, ORDER, set(), extra={(R, "a"), (R, "b")})
    assert st == [pp.Stage(frozenset({(D, "lib")}), {R: ["a", "b"]})]


def test_nothing_frozen_downstream():
    assert pp.plan_stages({(R, "a")}, {(R, "b"): {(R, "a")}}, set(), ORDER, set()) == []


def test_cycle_terminates():
    fwd = {(R, "b"): {(R, "a"), (R, "c")}, (R, "c"): {(R, "b")}}
    assert pp.plan_stages({(R, "a")}, fwd, {R}, ORDER, set())[0].trigger == {
        R: ["b", "c"]
    }


def test_seeds_never_triggered_and_non_frozen_never_triggered():
    fwd = {(R, "b"): {(R, "a")}, (D, "x"): {(R, "a")}, (R, "a"): {(R, "b")}}
    st = pp.plan_stages({(R, "a")}, fwd, {R}, ORDER, set())
    assert st == [pp.Stage(frozenset({(R, "a")}), {R: ["b"]})]


def test_non_frozen_member_between_frozen_stages_is_waited_for():
    # R:b (frozen) -> D2:x (not frozen, rebuilt by OBS) -> I:img (frozen)
    fwd = {
        (R, "b"): {(R, "a")},
        ("r:mid", "x"): {(R, "b")},
        (I, "img"): {("r:mid", "x")},
    }
    st = pp.plan_stages({(R, "a")}, fwd, {R, I}, ORDER, set())
    assert [s.trigger for s in st] == [{R: ["b"]}, {I: ["img"]}]
    assert st[1].wait_for == frozenset({("r:mid", "x"), (R, "b")})


def test_projects_missing_from_order_sort_last_by_name():
    fwd = {("r:z", "p"): {(R, "a")}, ("r:y", "q"): {(R, "a")}, (C, "t"): {(R, "a")}}
    st = pp.plan_stages({(R, "a")}, fwd, {"r:z", "r:y", C}, ORDER, set())
    assert [s.trigger for s in st] == [{C: ["t"]}, {"r:y": ["q"]}, {"r:z": ["p"]}]


def test_wildcard_dependency_waits_for_matching_members():
    fwd = {(R, "agg"): {(D, "*")}}
    st = pp.plan_stages({(D, "lib"), (D, "lib2")}, fwd, {R}, ORDER, {(R, "agg")})
    assert st == [
        pp.Stage(frozenset({(D, "lib"), (D, "lib2")}), {R: ["agg"]}),
    ]


def test_aggregate_edges_from_local_files(tmp_path, monkeypatch):
    root = tmp_path / "root"
    pkg = root / "u" / "agg"
    (pkg / "obs").mkdir(parents=True)
    (pkg / "obs" / "_aggregate").write_text(
        "<aggregatelist>\n"
        '  <aggregate project="${OBS_ROOTPRJ}:deps">\n'
        "    <package>lib</package>\n"
        "  </aggregate>\n"
        "</aggregatelist>\n"
    )
    plain = root / "u" / "plain"
    (plain / "obs").mkdir(parents=True)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_sync, "REPO_ROOT", root)
    targets = [(R, pkg), (R, plain)]
    assert pp.aggregate_edges(targets, {"OBS_ROOTPRJ": "r"}) == {
        (R, "agg"): {(D, "lib")}
    }


def test_aggregate_without_packages_is_wildcard(tmp_path, monkeypatch):
    root = tmp_path / "root"
    pkg = root / "u" / "agg"
    (pkg / "obs").mkdir(parents=True)
    (pkg / "obs" / "_aggregate").write_text(
        '<aggregatelist><aggregate project="${OBS_ROOTPRJ}:deps"/></aggregatelist>'
    )
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_sync, "REPO_ROOT", root)
    assert pp.aggregate_edges([(R, pkg)], {"OBS_ROOTPRJ": "r"}) == {
        (R, "agg"): {(D, "*")}
    }


def test_failed_depinfo_triggers_whole_frozen_consumers():
    assert pp.expand_failed({D}, {R, I}, {D: {R}}, {R: ["a", "b"], I: ["img"]}) == {
        (R, "a"),
        (R, "b"),
    }


def test_failed_frozen_project_itself_is_expanded():
    assert pp.expand_failed({I}, {R, I}, {}, {R: ["a"], I: ["img"]}) == {(I, "img")}


def _meta(name, paths):
    repo = "".join(f'<path project="{p}" repository="std"/>' for p in paths)
    return (
        f'<project name="{name}"><repository name="std">{repo}</repository></project>'
    )


def test_upstream_projects_follows_paths_under_rootprj(monkeypatch):
    metas = {
        R: _meta(R, ["r:deps", "openSUSE:Factory"]),
        "r:deps": _meta("r:deps", ["r:base"]),
        "r:base": _meta("r:base", []),
    }
    seen = []

    def fake_meta(apiurl, prj):
        seen.append(prj)
        return [line.encode() for line in metas[prj].splitlines(keepends=True)]

    monkeypatch.setattr(pp.osc.core, "show_project_meta", fake_meta)
    assert pp.upstream_projects("https://api", {R}, "r") == {R, "r:deps", "r:base"}
    assert "openSUSE:Factory" not in seen
