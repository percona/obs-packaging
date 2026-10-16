"""Typing of OBS projects in the QA matrix script (.github/scripts/list_qa_matrix.py)."""

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "list_qa_matrix", Path(__file__).parent.parent / ".github/scripts/list_qa_matrix.py"
)
assert _SPEC is not None


def _load():
    assert _SPEC is not None
    mod = importlib.util.module_from_spec(_SPEC)
    assert _SPEC.loader is not None
    _SPEC.loader.exec_module(mod)
    return mod


def test_qa_project_type():
    m = _load()
    assert m.qa_project_type("x:ppg:staging:18:containers") == "containers"
    assert m.qa_project_type("x:ppg:releases:17:containers:ubi9") == "containers"
    assert m.qa_project_type("x:ppg:staging:17:extras:containers") == "containers"
    assert m.qa_project_type("x:ppg:staging:17:tarballs") == "packages"
    assert m.qa_project_type("x:ppg:staging:17") == "packages"


def test_normalize_entry_name_filter():
    m = _load()
    # qa show already emits name_filter → passed through untouched
    e = m.normalize_entry({"name": "ubi8", "name_filter": "--name ubi8"})
    assert e["name_filter"] == "--name ubi8"
    # derived from `name` when absent
    assert m.normalize_entry({"name": "ubi9"})["name_filter"] == "--name ubi9"
    # unnamed entries get the empty string, mirroring axis_filters
    assert m.normalize_entry({"name": ""})["name_filter"] == ""
    assert m.normalize_entry({})["name_filter"] == ""


def test_normalize_entry_package_filter():
    m = _load()
    assert m.normalize_entry({"package": "pkg"})["package_filter"] == "--package pkg"
    assert m.normalize_entry({"package": ""})["package_filter"] == "--project-only"
    assert m.normalize_entry({})["package_filter"] == "--project-only"
    e = m.normalize_entry({"package": "pkg", "package_filter": "--package pkg"})
    assert e["package_filter"] == "--package pkg"


def _combo(package: str, ctx: str) -> dict:
    return {"package": package, "status_context": ctx, "params": {}}


def test_drop_absent_packages_keeps_project_and_present():
    m = _load()
    matrix = [
        _combo("", "OBS QA / p"),
        _combo("pg_tde", "OBS QA / p / pg_tde"),
        _combo("pgbackrest", "OBS QA / p / pgbackrest"),
    ]
    kept, dropped = m.drop_absent_packages(matrix, {"pg_tde", "unrelated"})
    assert [c["status_context"] for c in kept] == ["OBS QA / p", "OBS QA / p / pg_tde"]
    assert dropped == ["pgbackrest"]


def test_drop_absent_packages_noop_without_package_lanes():
    m = _load()
    matrix = [_combo("", "OBS QA / p")]
    kept, dropped = m.drop_absent_packages(matrix, set())
    assert kept == matrix and dropped == []


def test_main_applies_presence_filter(monkeypatch, capsys):
    import json
    import subprocess

    m = _load()
    monkeypatch.setenv("OBS_APIURL", "https://obs.example")
    monkeypatch.setenv("OBS_PROJECT", "isv:percona:PR:pr-1")
    monkeypatch.setenv("QA_PACKAGES_PRESENT_ONLY", "true")
    monkeypatch.delenv("QA_TYPES", raising=False)

    # Import the real module first: it imports osc at module level, and the
    # stub below only has to satisfy the `import osc.conf` inside main().
    import percona_obs.obs_api as obs_api

    class _Osc:
        class conf:
            @staticmethod
            def get_config(**kw):
                pass

    monkeypatch.setitem(__import__("sys").modules, "osc", _Osc)
    monkeypatch.setitem(__import__("sys").modules, "osc.conf", _Osc.conf)

    monkeypatch.setattr(
        obs_api,
        "_fetch_obs_subproject_names",
        lambda a, p: {"isv:percona:PR:pr-1:ppg:18"},
    )
    calls: list[str] = []

    def fake_fetch(apiurl: str, full_name: str) -> set[str]:
        calls.append(full_name)
        return {"pg_tde"}

    monkeypatch.setattr(m, "fetch_present_packages", fake_fetch)
    shown = [
        _combo("", "OBS QA / ppg:18"),
        _combo("pg_tde", "OBS QA / ppg:18 / pg_tde"),
        _combo("pgbackrest", "OBS QA / ppg:18 / pgbackrest"),
    ]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(shown), ""),
    )
    m.main()
    out = json.loads(capsys.readouterr().out)
    assert [c["status_context"] for c in out] == [
        "OBS QA / ppg:18",
        "OBS QA / ppg:18 / pg_tde",
    ]
    assert calls == ["isv:percona:PR:pr-1:ppg:18"]


def test_main_skips_presence_filter_when_unset(monkeypatch, capsys):
    import json
    import subprocess

    m = _load()
    monkeypatch.setenv("OBS_APIURL", "https://obs.example")
    monkeypatch.setenv("OBS_PROJECT", "isv:percona")
    monkeypatch.delenv("QA_PACKAGES_PRESENT_ONLY", raising=False)
    monkeypatch.delenv("QA_TYPES", raising=False)

    # Import the real module first: it imports osc at module level, and the
    # stub below only has to satisfy the `import osc.conf` inside main().
    import percona_obs.obs_api as obs_api

    class _Osc:
        class conf:
            @staticmethod
            def get_config(**kw):
                pass

    monkeypatch.setitem(__import__("sys").modules, "osc", _Osc)
    monkeypatch.setitem(__import__("sys").modules, "osc.conf", _Osc.conf)

    monkeypatch.setattr(
        obs_api, "_fetch_obs_subproject_names", lambda a, p: {"isv:percona:ppg:18"}
    )

    def boom(apiurl: str, full_name: str) -> set[str]:
        raise AssertionError("presence filter must not run")

    monkeypatch.setattr(m, "fetch_present_packages", boom)
    shown = [_combo("pgbackrest", "OBS QA / ppg:18 / pgbackrest")]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(shown), ""),
    )
    m.main()
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 1 and out[0]["package_filter"] == "--package pgbackrest"


def test_fetch_present_packages_propagates_listing_errors(monkeypatch):
    import pytest

    m = _load()
    import percona_obs.obs_api as obs_api

    def boom(apiurl: str, project: str) -> set[str]:
        raise SystemExit("error listing packages")

    monkeypatch.setattr(obs_api, "_fetch_obs_package_names_or_fail", boom)
    with pytest.raises(SystemExit):
        m.fetch_present_packages("https://x", "p")


def test_qa_show_stderr_is_forwarded(monkeypatch, capsys, tmp_path):
    """Image-reference decisions are printed by `qa show` on stderr; the detect
    job must show them, so a successful run's stderr is forwarded."""
    import subprocess
    from types import SimpleNamespace

    m = _load()
    monkeypatch.setenv("OBS_APIURL", "http://obs")
    monkeypatch.setenv("OBS_PROJECT", "isv:percona:PR:pr-1")
    monkeypatch.delenv("QA_TYPES", raising=False)
    monkeypatch.delenv("QA_PACKAGES_PRESENT_ONLY", raising=False)
    monkeypatch.setattr("osc.conf.get_config", lambda **k: None)
    monkeypatch.setattr(
        "percona_obs.obs_api._fetch_obs_subproject_names",
        lambda apiurl, root: {"isv:percona:PR:pr-1:ppg:staging:18:containers"},
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=0,
            stdout='[{"project":"ppg:staging:18:containers","package":"","name":"ubi9"}]',
            stderr="  image x (ppg:staging:18:containers) → REPOSITORY = r  [fallback: not in p]\n",
        ),
    )
    m.main()
    captured = capsys.readouterr()
    assert "fallback" in captured.err
    assert "ppg:staging:18:containers" in captured.err


def _run_failing_qa_show(monkeypatch, present_only):
    import subprocess
    from types import SimpleNamespace

    m = _load()
    monkeypatch.setenv("OBS_APIURL", "http://obs")
    monkeypatch.setenv("OBS_PROJECT", "isv:percona:PR:pr-1")
    monkeypatch.delenv("QA_TYPES", raising=False)
    if present_only:
        monkeypatch.setenv("QA_PACKAGES_PRESENT_ONLY", "true")
    else:
        monkeypatch.delenv("QA_PACKAGES_PRESENT_ONLY", raising=False)
    monkeypatch.setattr("osc.conf.get_config", lambda **k: None)
    monkeypatch.setattr(
        "percona_obs.obs_api._fetch_obs_subproject_names",
        lambda apiurl, root: {"isv:percona:PR:pr-1:ppg:staging:18:containers"},
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )
    return m


def test_qa_show_failure_aborts_in_present_only_mode(monkeypatch):
    m = _run_failing_qa_show(monkeypatch, True)
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert "ppg:staging:18:containers" in str(exc.value)


def test_qa_show_failure_is_skipped_in_nightly_mode(monkeypatch, capsys):
    m = _run_failing_qa_show(monkeypatch, False)
    m.main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "[]"
    assert "warning: qa show" in captured.err


def test_is_release_tier():
    m = _load()
    assert m.is_release_tier("a:ppg:releases:18")
    assert m.is_release_tier("a:ppg:releases:18:containers")
    assert not m.is_release_tier("a:ppg:staging:18")
    assert not m.is_release_tier("a:ppg:devel:18:containers")


# --- one major per night ------------------------------------------------------

import io
import json
from contextlib import redirect_stdout
from types import SimpleNamespace

import yaml

REPO = Path(__file__).parent.parent
SCHEDULE = REPO / ".github" / "nightly-qa-schedule.yml"
MAJORS = ("14", "15", "16", "17", "18", "19")
UNSCHEDULED = {"19"}  # in development: on demand only, see the schedule file


@pytest.mark.parametrize(
    "project, name, major, expected",
    [
        ("ppg:staging:17", "server", "17", True),
        ("ppg:staging:17:containers", "ubi9", "17", True),
        ("ppg:staging:17:tarballs", "ssl3", "17", True),
        ("ppg:staging:17", "server", "18", False),
        ("ppg:staging:common:tools:containers", "ubi9-pgbouncer-pg17", "17", True),
        ("ppg:staging:common:tools:containers", "ubi9-pgbouncer-pg17", "18", False),
        ("ppg:staging:common:containers", "ubi9-16-to-17", "17", True),  # into 17
        ("ppg:staging:common:containers", "ubi9-16-to-17", "16", False),  # not from 16
        ("ppg:staging:common:extras:containers", "ubi9-17-to-18", "18", True),
        ("ppg:staging:common:containers", None, "17", False),
        # a major's own project belongs to that major only, whatever the name
        ("ppg:staging:18", "ubi9-16-to-17", "17", False),
        ("ppg:staging:18", "ubi9-16-to-17", "18", True),
    ],
)
def test_belongs_to_major(project, name, major, expected):
    assert _load().belongs_to_major(project, name, major) is expected


def test_schedule_file_is_valid():
    schedule = yaml.safe_load(SCHEDULE.read_text())
    assert set(schedule) <= {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    # the workflow reads the file with nightly_plan.parse_schedule (no yaml on the runner)
    assert _plan().parse_schedule(SCHEDULE.read_text()) == {
        k: str(v) for k, v in schedule.items()
    }
    majors = [str(v) for v in schedule.values()]
    assert len(majors) == len(set(majors)), "a major is scheduled twice"
    assert set(majors) <= set(MAJORS)


def _qa_projects():
    for y in sorted((REPO / "root" / "ppg" / "staging").rglob("project.yaml")):
        rel = y.parent.relative_to(REPO / "root")
        if "_shared" in rel.parts:
            continue
        text = y.read_text()
        pkgs = [
            p / "package.yaml"
            for p in y.parent.iterdir()
            if (p / "package.yaml").exists()
        ]
        if "\nqa:" in text or any("\nqa:" in p.read_text() for p in pkgs):
            yield ":".join(rel.parts)


def test_every_qa_build_runs_on_exactly_one_scheduled_night():
    from percona_obs import cmd_qa

    m = _load()
    scheduled = set(_plan().parse_schedule(SCHEDULE.read_text()).values())
    problems, total = [], 0
    for project in _qa_projects():
        args = SimpleNamespace(
            project=project,
            rootprj="isv:percona",
            json=True,
            apiurl=None,
            env_overrides=["REMOTE_OBS_ORG_INTERCONNECT:"],
            profile=None,
            image_fallback_rootprj=None,
            package=None,
            project_only=False,
        )
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_qa.cmd_qa_show(args)
        for combo in json.loads(out.getvalue() or "[]"):
            total += 1
            owners = [
                mj
                for mj in MAJORS
                if m.belongs_to_major(project, combo.get("name"), mj)
            ]
            label = f"{project} / {combo.get('name') or combo.get('package') or combo['pipeline']}"
            if len(owners) != 1:
                problems.append(f"{label}: belongs to {owners or 'no major'}")
            elif owners[0] not in scheduled | UNSCHEDULED:
                problems.append(f"{label}: PG {owners[0]} has no night in the schedule")
    assert total > 100, f"only {total} QA builds found; is the tree complete?"
    assert not problems, "\n".join(problems)


# --- nightly_plan.py: tonight's major, and skip when nothing changed ----------


def _plan():
    spec = importlib.util.spec_from_file_location(
        "nightly_plan", REPO / ".github/scripts/nightly_plan.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_schedule_ignores_comments():
    text = "# plan\nmon: 14\ntue: '15'  # quoted\n# sun: 19\nfoo: 3\n"
    assert _plan().parse_schedule(text) == {"mon": "14", "tue": "15"}


@pytest.mark.parametrize(
    "inp, day, expected",
    [
        ("", "Mon", (True, "14")),  # scheduled run
        ("today", "Tue", (True, "15")),
        ("today", "Sat", (False, "")),  # nothing scheduled
        ("17", "Sat", (True, "17")),  # manual, any day
        ("all", "Wed", (True, "")),  # manual, every major
    ],
)
def test_resolve_major(inp, day, expected):
    run, major, _ = _plan().resolve_major(inp, day, {"mon": "14", "tue": "15"})
    assert (run, major) == expected


def test_last_tested_sha_uses_the_same_major():
    p = _plan()
    runs = [
        {"databaseId": 3, "headSha": "ccc"},  # newest: Monday, PG 14
        {"databaseId": 2, "headSha": "bbb"},  # last week's full run
        {"databaseId": 1, "headSha": "aaa"},
    ]  # last week's PG 15
    arts = {3: ["nightly-major-14"], 2: ["nightly-major-all"], 1: ["nightly-major-15"]}
    # Tuesday (PG 15) must not compare with Monday's PG 14 run
    assert p.last_tested_sha(runs, lambda r: arts[r], "15") == "bbb"
    assert p.last_tested_sha(runs, lambda r: arts[r], "14") == "ccc"
    assert (
        p.last_tested_sha(runs[:1], lambda r: arts[r], "16") == ""
    )  # never tested: run


def _main(tmp_path, monkeypatch, event, changed, sha="bbb", input_major=""):
    p = _plan()
    out = tmp_path / "out"
    monkeypatch.chdir(REPO)
    monkeypatch.setenv("EVENT_NAME", event)
    monkeypatch.setenv("INPUT_MAJOR", input_major)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(p, "resolve_major", lambda i, d, s: (True, "15", "scheduled"))
    monkeypatch.setattr(
        p,
        "_gh",
        lambda *a: (
            json.dumps([{"databaseId": 1, "headSha": sha}])
            if a[0] == "run"
            else "nightly-major-15"
        ),
    )
    monkeypatch.setattr(p, "_changed_since", lambda s: changed)
    p.main()
    return dict(line.split("=", 1) for line in out.read_text().splitlines())


def test_scheduled_run_skips_without_changes(tmp_path, monkeypatch):
    assert _main(tmp_path, monkeypatch, "schedule", changed=False)["run"] == "false"


def test_scheduled_run_runs_after_changes(tmp_path, monkeypatch):
    out = _main(tmp_path, monkeypatch, "schedule", changed=True)
    assert (out["run"], out["major"], out["marker"]) == (
        "true",
        "15",
        "nightly-major-15",
    )


def test_manual_run_never_skips(tmp_path, monkeypatch):
    assert (
        _main(tmp_path, monkeypatch, "workflow_dispatch", changed=False)["run"]
        == "true"
    )


# --- nightly: each project on the OBS instance that hosts it ------------------

INSTANCES = [
    {
        "name": "boo",
        "apiurl": "https://api.example",
        "rootprj": "isv:percona",
        "qa_types": "packages",
    },
    {
        "name": "labs",
        "apiurl": "https://labs.example",
        "rootprj": "isv:percona",
        "registry": "registry.labs.example",
        "qa_types": "containers",
        "env": {"X": "1"},
    },
]


def _fake_tree(m, monkeypatch, projects):
    monkeypatch.setattr(m, "local_qa_projects", lambda root: projects)
    monkeypatch.setattr(
        m,
        "_qa_show",
        lambda project, profile: [
            {"pipeline": "job", "name": n, "project": project}
            for n in ("server", "ubi9-16-to-17")
        ],
    )


def test_each_project_runs_on_its_instance(monkeypatch):
    m = _load()
    _fake_tree(
        m,
        monkeypatch,
        ["ppg:staging:17", "ppg:staging:17:containers", "ppg:staging:17:tarballs"],
    )
    matrix = m.matrix_per_instance(json.dumps(INSTANCES), Path("root"), "ci", "")
    where = {(c["project"], c["instance_name"]) for c in matrix}
    assert where == {
        ("ppg:staging:17", "boo"),
        ("ppg:staging:17:tarballs", "boo"),
        ("ppg:staging:17:containers", "labs"),
    }
    labs = next(c for c in matrix if c["instance_name"] == "labs")
    assert (
        labs["instance_apiurl"],
        labs["instance_registry"],
        json.loads(labs["instance_env"]),
    ) == ("https://labs.example", "registry.labs.example", {"X": "1"})
    assert all(
        c.get("name_filter") is not None for c in matrix
    )  # normalised like before


def test_release_snapshots_and_unhosted_projects_are_skipped(monkeypatch, capsys):
    m = _load()
    only_packages = [INSTANCES[0]]
    _fake_tree(
        m,
        monkeypatch,
        ["ppg:releases:17", "ppg:staging:17:containers", "ppg:staging:17"],
    )
    matrix = m.matrix_per_instance(json.dumps(only_packages), Path("root"), "ci", "")
    assert {c["project"] for c in matrix} == {"ppg:staging:17"}
    assert "no OBS instance hosts ppg:staging:17:containers" in capsys.readouterr().err


def test_major_filter_applies_per_instance(monkeypatch):
    m = _load()
    _fake_tree(m, monkeypatch, ["ppg:staging:common:containers", "ppg:staging:18"])
    matrix = m.matrix_per_instance(json.dumps(INSTANCES), Path("root"), "ci", "17")
    # only the upgrade into 17 from the shared project; nothing from PG 18
    assert [(c["project"], c["name"]) for c in matrix] == [
        ("ppg:staging:common:containers", "ubi9-16-to-17")
    ]


def test_local_qa_projects_finds_the_real_tree():
    found = _load().local_qa_projects(REPO / "root")
    for p in (
        "ppg:staging:18",
        "ppg:staging:18:containers",
        "ppg:staging:18:tarballs",
        "ppg:staging:common:tools:containers",
        "ppg:staging:common:containers",
    ):
        assert p in found, p
    assert not any("_shared" in p for p in found)
