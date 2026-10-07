"""Helpers of the manual QA workflow (.github/workflows/obs-qa-run.yml):

* resolve_qa_instance.py picks the one OBS_INSTANCES entry hosting a project.
* filter_qa_matrix.py narrows a `qa show --json` matrix by entry name / axis.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).parent.parent / ".github/scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# resolve_qa_instance
# ---------------------------------------------------------------------------

_INSTANCES = [
    {
        "name": "boo",
        "apiurl": "https://api.opensuse.org",
        "rootprj": "isv:percona",
        "pr_rootprj": "isv:percona:PR",
        "exclude_projects": "*:containers,*:containers:*",
        "qa_types": "packages",
    },
    {
        "name": "labs",
        "apiurl": "https://obs.labs",
        "rootprj": "isv:percona",
        "pr_rootprj": "isv:percona:PR",
        "include_projects": "*:containers,*:containers:*",
        "qa_types": "containers",
    },
]


def test_resolve_picks_packages_instance():
    m = _load("resolve_qa_instance")
    inst = m.resolve_instance(_INSTANCES, "ppg:staging:18")
    assert inst["name"] == "boo"


def test_resolve_picks_containers_instance():
    m = _load("resolve_qa_instance")
    inst = m.resolve_instance(_INSTANCES, "ppg:staging:18:containers")
    assert inst["name"] == "labs"


def test_resolve_qa_types_alone_disambiguates():
    # Both instances carry the project; only one declares the QA kind.
    m = _load("resolve_qa_instance")
    instances = [
        {"name": "a", "qa_types": "packages"},
        {"name": "b", "qa_types": "containers"},
    ]
    assert m.resolve_instance(instances, "ppg:staging:18")["name"] == "a"


def test_resolve_no_qa_types_means_all_kinds():
    m = _load("resolve_qa_instance")
    instances = [{"name": "only"}]
    assert m.resolve_instance(instances, "ppg:staging:18:containers")["name"] == "only"


def test_resolve_zero_matches_lists_candidates():
    m = _load("resolve_qa_instance")
    instances = [
        {"name": "boo", "include_projects": "ppg:*"},
        {"name": "labs", "include_projects": "ppg:*:containers"},
    ]
    with pytest.raises(SystemExit) as exc:
        m.resolve_instance(instances, "common:deps")
    # the message names what was tried so the user can fix OBS_INSTANCES
    assert "no OBS instance" in str(exc.value)
    assert "boo" in str(exc.value) and "labs" in str(exc.value)


def test_resolve_ambiguous_fails():
    m = _load("resolve_qa_instance")
    instances = [{"name": "a"}, {"name": "b"}]
    with pytest.raises(SystemExit) as exc:
        m.resolve_instance(instances, "ppg:staging:18")
    assert "ambiguous" in str(exc.value)


@pytest.mark.parametrize(
    "project",
    ["ppg:staging:18", "ppg:staging:18:containers", "common:deps:build", "ppg:16:tde"],
)
def test_valid_project_names(project):
    m = _load("resolve_qa_instance")
    m.validate_project(project)


@pytest.mark.parametrize(
    "project",
    ["", ":ppg", "ppg:", "ppg::18", "ppg staging", "ppg;rm -rf", "ppg:$(x)", "a/b"],
)
def test_invalid_project_names(project):
    m = _load("resolve_qa_instance")
    with pytest.raises(SystemExit):
        m.validate_project(project)


@pytest.mark.parametrize("pr", ["", "1", "42"])
def test_valid_pr_numbers(pr):
    m = _load("resolve_qa_instance")
    m.validate_pr_number(pr)


@pytest.mark.parametrize("pr", ["x", "4 2", "-1", "0", "01"])
def test_invalid_pr_numbers(pr):
    m = _load("resolve_qa_instance")
    with pytest.raises(SystemExit):
        m.validate_pr_number(pr)


def test_resolve_main_writes_flat_outputs(tmp_path, monkeypatch):
    m = _load("resolve_qa_instance")
    out = tmp_path / "out"
    monkeypatch.setenv("OBS_INSTANCES", json.dumps(_INSTANCES))
    monkeypatch.setenv("QA_PROJECT", "ppg:staging:18:containers")
    monkeypatch.setenv("QA_PR_NUMBER", "42")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    m.main()
    text = out.read_text()
    assert "instance_name=labs\n" in text
    assert "instance_apiurl=https://obs.labs\n" in text
    # PR number given → the PR root is used
    assert "rootprj=isv:percona:PR:pr-42\n" in text
    assert "instance_user=\n" in text
    assert "instance_registry=\n" in text
    assert "instance_env=" in text


def test_resolve_main_production_root(tmp_path, monkeypatch):
    m = _load("resolve_qa_instance")
    out = tmp_path / "out"
    monkeypatch.setenv("OBS_INSTANCES", json.dumps(_INSTANCES))
    monkeypatch.setenv("QA_PROJECT", "ppg:staging:18")
    monkeypatch.setenv("QA_PR_NUMBER", "")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    m.main()
    assert "rootprj=isv:percona\n" in out.read_text()


def test_resolve_main_malformed_instances(monkeypatch, tmp_path):
    m = _load("resolve_qa_instance")
    monkeypatch.setenv("OBS_INSTANCES", "not json")
    monkeypatch.setenv("QA_PROJECT", "ppg:staging:18")
    monkeypatch.setenv("QA_PR_NUMBER", "")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    with pytest.raises(SystemExit):
        m.main()


# ---------------------------------------------------------------------------
# filter_qa_matrix
# ---------------------------------------------------------------------------


def _combo(name: str, package: str = "", **params: str) -> dict:
    return {
        "project": "ppg:staging:18:containers",
        "package": package,
        "pipeline": "docker",
        "name": name,
        "label": ",".join(f"{k}={v}" for k, v in params.items()) or "default",
        "axis_filters": " ".join(f"--filter {k}={v}" for k, v in params.items()),
        "name_filter": f"--name {name}" if name else "",
        "package_filter": f"--package {package}" if package else "--project-only",
        "status_context": f"OBS QA / x / {package or name}",
        "params": params,
    }


_MATRIX = [
    _combo("ubi8", WITH_POSTGIS="true"),
    _combo("ubi8", WITH_POSTGIS="false"),
    _combo("ubi9", WITH_POSTGIS="true"),
    _combo("ubi9", WITH_POSTGIS="false"),
]


def test_filter_no_inputs_keeps_everything():
    m = _load("filter_qa_matrix")
    assert m.filter_matrix(_MATRIX, "", "") == _MATRIX


def test_filter_by_name():
    m = _load("filter_qa_matrix")
    out = m.filter_matrix(_MATRIX, "ubi9", "")
    assert [c["name"] for c in out] == ["ubi9", "ubi9"]


def test_filter_by_axis_single_value():
    m = _load("filter_qa_matrix")
    out = m.filter_matrix(_MATRIX, "", "WITH_POSTGIS=false")
    assert len(out) == 2
    assert all(c["params"]["WITH_POSTGIS"] == "false" for c in out)


def test_filter_by_axis_multi_value_and_name():
    m = _load("filter_qa_matrix")
    out = m.filter_matrix(_MATRIX, "ubi8", "WITH_POSTGIS=true,false")
    assert [c["name"] for c in out] == ["ubi8", "ubi8"]


def test_filter_several_axes_space_separated():
    m = _load("filter_qa_matrix")
    matrix = [
        _combo("", PLATFORMS="rocky-9", SCENARIO="full"),
        _combo("", PLATFORMS="rocky-9", SCENARIO="smoke"),
        _combo("", PLATFORMS="debian-13", SCENARIO="full"),
    ]
    out = m.filter_matrix(matrix, "", "PLATFORMS=rocky-9 SCENARIO=full")
    assert len(out) == 1
    assert out[0]["params"] == {"PLATFORMS": "rocky-9", "SCENARIO": "full"}


def test_filter_unknown_name_fails_listing_names():
    m = _load("filter_qa_matrix")
    with pytest.raises(SystemExit) as exc:
        m.filter_matrix(_MATRIX, "ubi10", "")
    msg = str(exc.value)
    assert "ubi8" in msg and "ubi9" in msg


def test_filter_unknown_axis_fails_listing_axes():
    m = _load("filter_qa_matrix")
    with pytest.raises(SystemExit) as exc:
        m.filter_matrix(_MATRIX, "", "PLATFORM=rocky-9")
    assert "WITH_POSTGIS" in str(exc.value)


def test_filter_non_axis_parameter_fails_with_hint():
    m = _load("filter_qa_matrix")
    matrix = [
        {
            **_combo("", IO_METHOD="worker"),
            "params": {"IO_METHOD": "worker", "PLATFORMS": "a\nb"},
        },
    ]
    with pytest.raises(SystemExit) as exc:
        m.filter_matrix(matrix, "", "PLATFORMS=a")
    msg = str(exc.value)
    assert "not a matrix axis" in msg and "IO_METHOD" in msg


def test_filter_unknown_value_fails_listing_values():
    m = _load("filter_qa_matrix")
    with pytest.raises(SystemExit) as exc:
        m.filter_matrix(_MATRIX, "", "WITH_POSTGIS=maybe")
    msg = str(exc.value)
    assert "true" in msg and "false" in msg


def test_filter_malformed_filter_token():
    m = _load("filter_qa_matrix")
    with pytest.raises(SystemExit):
        m.filter_matrix(_MATRIX, "", "WITH_POSTGIS")


def test_filter_empty_matrix_fails():
    m = _load("filter_qa_matrix")
    with pytest.raises(SystemExit) as exc:
        m.filter_matrix([], "", "")
    assert "no qa" in str(exc.value).lower()


# --- package selection -----------------------------------------------------------

_WITH_PKG = [
    _combo("", WITH_POSTGIS="true"),
    _combo("", "pg_tde", PLATFORMS="rocky-9"),
    _combo("", "pgbackrest", PLATFORMS="rocky-9"),
]


def test_filter_by_package():
    m = _load("filter_qa_matrix")
    out = m.filter_matrix(_WITH_PKG, "", "", package="pg_tde")
    assert [c["package"] for c in out] == ["pg_tde"]


def test_filter_unknown_package_lists_packages():
    m = _load("filter_qa_matrix")
    with pytest.raises(SystemExit) as exc:
        m.filter_matrix(_WITH_PKG, "", "", package="nope")
    msg = str(exc.value)
    assert "(project)" in msg and "pg_tde" in msg and "pgbackrest" in msg


def test_filter_empty_package_keeps_everything():
    m = _load("filter_qa_matrix")
    assert m.filter_matrix(_WITH_PKG, "", "", package="") == _WITH_PKG


def _presence_env(monkeypatch, tmp_path, present: set[str], **env: str):
    m = _load("filter_qa_matrix")
    monkeypatch.setenv("QA_PACKAGES_PRESENT_ONLY", "true")
    monkeypatch.setenv("OBS_APIURL", "https://obs.example")
    monkeypatch.setenv("OBS_PROJECT", "isv:percona:PR:pr-7:ppg:staging:18")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(m, "fetch_present_packages", lambda a, p: present)
    monkeypatch.setattr(m, "_configure_osc", lambda apiurl: None)
    return m


def test_main_presence_drop_then_narrow(monkeypatch, tmp_path, capsys):
    m = _presence_env(
        monkeypatch, tmp_path, {"pg_tde"}, QA_NAME="", QA_FILTER="", QA_PACKAGE=""
    )
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(_WITH_PKG)))
    m.main()
    out = json.loads(capsys.readouterr().out)
    assert [c["package"] for c in out] == ["", "pg_tde"]


def test_main_presence_requested_absent_package_errors(monkeypatch, tmp_path):
    m = _presence_env(
        monkeypatch,
        tmp_path,
        {"pg_tde"},
        QA_NAME="",
        QA_FILTER="",
        QA_PACKAGE="pgbackrest",
    )
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(_WITH_PKG)))
    with pytest.raises(SystemExit) as exc:
        m.main()
    msg = str(exc.value)
    assert (
        "pgbackrest" in msg
        and "not present in isv:percona:PR:pr-7:ppg:staging:18" in msg
    )


# --- package input validation ----------------------------------------------------


@pytest.mark.parametrize(
    "pkg", ["", "pg_tde", "percona-postgresql18", "python3-psycopg2"]
)
def test_valid_package_names(pkg):
    m = _load("resolve_qa_instance")
    m.validate_package(pkg)


@pytest.mark.parametrize("pkg", ["a b", "a;b", "$(x)", "a/b", "-x"])
def test_invalid_package_names(pkg):
    m = _load("resolve_qa_instance")
    with pytest.raises(SystemExit):
        m.validate_package(pkg)
