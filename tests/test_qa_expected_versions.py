"""``percona-obs qa`` adds EXPECTED_VERSIONS to every triggered job.

The value lists the versions OBS builds for the packages under test, as
``package=version`` lines keyed by OBS package name: each package's obs/_service
``version`` (an aggregate's taken from its source package), with macros
resolved from the package's macros.yaml chain.  Test jobs check installed
software against it without depending on macro names.
"""

import json
from types import SimpleNamespace

import percona_obs.cmd_qa as cmd_qa
import percona_obs.common as common

_QA = """\
title: P
qa:
  - name: server
    pipeline: ppg-multiOS-parallel
    parameters:
      VERSION: ppg-%!{PG_VERSION}
  - name: pinned
    pipeline: other-job
    parameters:
      EXPECTED_VERSIONS: "percona-pgbackrest=1.0"
"""


def _service(version: str) -> str:
    return (
        '<services><service name="obs_scm">'
        '<param name="url">https://example.com/x.git</param>'
        f'<param name="version">{version}</param>'
        "</service></services>"
    )


def _package(path, service=None, aggregate=None):
    (path / "obs").mkdir(parents=True)
    if service is not None:
        (path / "obs" / "_service").write_text(service)
    if aggregate is not None:
        (path / "obs" / "_aggregate").write_text(aggregate)


def _tree(tmp_path, monkeypatch, qa=_QA):
    """root/ppg/staging/{17,18}: shared packages, an aggregate, a subproject."""
    root = tmp_path / "root"
    staging = root / "ppg" / "staging"
    (root / "macros.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "macros.yaml").write_text(
        "- PGBACKREST_VERSION: 2.59.2\n- PERCONA_PG_PATCH_VERSION: 1\n"
    )
    _package(
        staging / "_shared" / "percona-pgbackrest",
        service=_service("%!{PGBACKREST_VERSION}"),
    )
    _package(
        staging / "_shared" / "percona-pgaudit", service=_service("%!{PGAUDIT_VERSION}")
    )
    _package(staging / "_shared" / "percona-ppg-server", service="<services/>")
    _package(root / "ppg" / "common" / "deps" / "etcd", service=_service("3.5.33"))
    (root / "ppg" / "common" / "deps" / "project.yaml").write_text("title: deps\n")
    _package(
        staging / "_shared" / "etcd",
        aggregate='<aggregatelist><aggregate project="${OBS_ROOTPRJ}:ppg:common:deps">'
        "<package>etcd</package></aggregate></aggregatelist>",
    )
    for major in ("17", "18"):
        d = staging / major
        d.mkdir()
        (d / "macros.yaml").write_text(
            f"- PG_MAJOR_VERSION: {major}\n- PG_MINOR_VERSION: 6\n"
            "- PG_VERSION: %!{PG_MAJOR_VERSION}.%!{PG_MINOR_VERSION}\n"
            f"- PGAUDIT_VERSION: {major}.0\n"
        )
        (d / "project.yaml").write_text(qa)
        for pkg in (
            "percona-pgbackrest",
            "percona-pgaudit",
            "percona-ppg-server",
            "etcd",
        ):
            (d / pkg).symlink_to(f"../_shared/{pkg}")
        sub = d / "containers"
        sub.mkdir()
        (sub / "project.yaml").write_text("title: containers\n")
        _package(sub / "percona-image", service=_service("9.9.9"))
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_qa, "REPO_ROOT", root)


def _show(project, capsys):
    args = SimpleNamespace(
        project=project, rootprj="isv:percona", env_overrides=[], json=True
    )
    cmd_qa.cmd_qa_show(args)
    return {r["name"]: r["params"] for r in json.loads(capsys.readouterr().out)}


def test_package_versions_keyed_by_package_name(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    lines = _show("ppg:staging:18", capsys)["server"]["EXPECTED_VERSIONS"].split("\n")
    assert lines == [
        "etcd=3.5.33",  # aggregate: version of its source package
        "percona-pgaudit=18.0",  # macro resolved for this major
        "percona-pgbackrest=2.59.2",
    ]


def test_no_macro_names_and_no_unrelated_values(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    value = _show("ppg:staging:18", capsys)["server"]["EXPECTED_VERSIONS"]
    assert "_VERSION" not in value and "PERCONA_PG_PATCH" not in value
    assert "percona-ppg-server" not in value  # declares no version
    assert "percona-image" not in value  # belongs to the containers subproject


def test_values_follow_the_project(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    value = _show("ppg:staging:17", capsys)["server"]["EXPECTED_VERSIONS"]
    assert "percona-pgaudit=17.0" in value.split("\n")


def test_entry_value_wins(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    assert (
        _show("ppg:staging:18", capsys)["pinned"]["EXPECTED_VERSIONS"]
        == "percona-pgbackrest=1.0"
    )


def test_single_package_entry_gets_only_its_package():
    versions = {"etcd": "3.5.33", "percona-pgbackrest": "2.59.2"}
    assert (
        cmd_qa._expected_versions(versions, "percona-pgbackrest")
        == "percona-pgbackrest=2.59.2"
    )
    assert cmd_qa._expected_versions(versions, "unknown") == ""
    assert (
        cmd_qa._expected_versions(versions) == "etcd=3.5.33\npercona-pgbackrest=2.59.2"
    )


def test_package_entry_is_restricted(monkeypatch):
    monkeypatch.setattr(cmd_qa, "_package_versions", lambda p: {"a": "1", "b": "2"})
    entries = [{"name": "x", "pipeline": "p", "parameters": {}, "_package": "b"}]
    (out,) = cmd_qa._with_expected_versions(entries, "any")
    assert out["parameters"]["EXPECTED_VERSIONS"] == "b=2"


def test_nothing_added_without_package_versions(monkeypatch):
    monkeypatch.setattr(cmd_qa, "_package_versions", lambda project: {})
    entries = [{"name": "x", "pipeline": "p", "parameters": {"A": "1"}}]
    assert cmd_qa._with_expected_versions(entries, "any") is entries


def test_no_entries_stays_none():
    assert cmd_qa._with_expected_versions(None, "any") is None


def test_qa_run_dry_run_shows_it(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    args = SimpleNamespace(
        project="ppg:staging:18",
        rootprj="isv:percona",
        env_overrides=[],
        profile=None,
        name="server",
        pipeline=None,
        filter=[],
        param=[],
        dry_run=True,
        wait=False,
        report_json=None,
        run_id=None,
        running=False,
        include_aborted=False,
    )
    cmd_qa.cmd_qa_run(args)
    out = capsys.readouterr().out
    assert "EXPECTED_VERSIONS" in out and "percona-pgbackrest=2.59.2" in out


def _container_tree(tmp_path, monkeypatch):
    """ppg/staging/{17,18} package projects and 18:containers building from them."""
    root = tmp_path / "root"
    staging = root / "ppg" / "staging"
    for major, pgbackrest, pgaudit in (
        ("17", "2.59.2", "17.1"),
        ("18", "2.59.2", "18.0"),
    ):
        d = staging / major
        _package(d / "percona-pgbackrest", service=_service(pgbackrest))
        _package(d / "percona-pgaudit", service=_service(pgaudit))
        (d / "project.yaml").write_text("title: P\n")
    _package(staging / "17" / "percona-only17", service=_service("1.0"))
    containers = staging / "18" / "containers"
    _package(containers / "percona-distribution-postgresql", service="<services/>")
    (containers / "project.yaml").write_text(
        "title: C\n"
        "repositories:\n"
        "  - name: ubi9\n"
        "    paths:\n"
        "      - project: RedHat:UBI:Registry\n"
        "        repository: images\n"
        "      - subproject: ppg:staging:18\n"
        "        repository: UBI_9\n"
        "      - subproject: ppg:staging:17\n"
        "        repository: UBI_9\n"
        "    archs: [x86_64]\n"
        "qa:\n"
        "  - name: ubi9\n"
        "    pipeline: docker-server-parallel\n"
        "    parameters:\n"
        "      DOCKER_TAG: '18'\n"
    )
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_qa, "REPO_ROOT", root)


def test_container_project_gets_the_versions_its_images_build_from(
    tmp_path, monkeypatch, capsys
):
    _container_tree(tmp_path, monkeypatch)
    lines = _show("ppg:staging:18:containers", capsys)["ubi9"][
        "EXPECTED_VERSIONS"
    ].split("\n")
    # first path (18) wins over the second (17); packages only in 17 still appear
    assert lines == [
        "percona-only17=1.0",
        "percona-pgaudit=18.0",
        "percona-pgbackrest=2.59.2",
    ]


def test_project_with_own_versions_does_not_follow_paths(tmp_path, monkeypatch):
    _container_tree(tmp_path, monkeypatch)
    assert cmd_qa._package_versions("ppg:staging:18") == {
        "percona-pgaudit": "18.0",
        "percona-pgbackrest": "2.59.2",
    }
