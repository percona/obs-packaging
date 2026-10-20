"""``percona-obs qa`` adds EXPECTED_VERSIONS to every triggered job.

The value lists the versions OBS built for the packages under test, as
``package=version`` lines keyed by OBS package name, read from the binaries
of the OBS project under test (``qa run`` always, ``qa show`` with
``--expected-versions``).  Test jobs check installed software against it
without depending on macro names.
"""

import json
import shutil
from types import SimpleNamespace

import pytest

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


R9 = ("RockyLinux_9", "x86_64")
D12 = ("Debian_12", "x86_64")

OBS = {
    "isv:percona:ppg:staging:18": {
        "percona-pgbackrest": {R9: "2.60.0-1.1", D12: "2.60.0-1"},
        "percona-pgaudit": {R9: "18.0-1.1"},
        "percona-ppg-server": {},  # listed, no readable binary
        "etcd": {R9: "3.5.34-1.1"},  # aggregate: binaries listed here
    },
    "isv:percona:ppg:staging:17": {
        "percona-pgbackrest": {R9: "2.60.0-1.1"},
        "percona-pgaudit": {R9: "17.0-1.1"},
        "percona-ppg-server": {},
        "etcd": {R9: "3.5.34-1.1"},
    },
}


def _obs(monkeypatch, data=OBS):
    calls = []

    def fetch(apiurl, project, repo_filter=None):
        calls.append(project)
        return data.get(project)

    monkeypatch.setattr(cmd_qa, "project_binary_versions", fetch)
    return calls


def _show(project, capsys, **kw):
    args = SimpleNamespace(
        project=project,
        rootprj=kw.pop("rootprj", "isv:percona"),
        env_overrides=[],
        json=True,
        apiurl="http://obs",
        image_fallback_rootprj=kw.pop("fallback", None),
        expected_versions=kw.pop("expected_versions", True),
        profile=None,
    )
    cmd_qa.cmd_qa_show(args)
    out = capsys.readouterr()
    return {r["name"]: r["params"] for r in json.loads(out.out)}, out.err


def _lookup(rootprj="isv:percona", fallback=None, project=""):
    return cmd_qa._VersionLookup(
        "http://obs", rootprj, fallback, cmd_qa._mirror_source(project)
    )


def test_versions_come_from_obs(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    _obs(monkeypatch)
    params, err = _show("ppg:staging:18", capsys)
    assert params["server"]["EXPECTED_VERSIONS"].split("\n") == [
        "etcd=3.5.34",
        "percona-pgaudit=18.0",
        "percona-pgbackrest=2.60.0",
    ]
    assert "warning: no OBS binaries for: percona-ppg-server" in err


def test_no_macro_names_and_no_unrelated_values(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    _obs(monkeypatch)
    value = _show("ppg:staging:18", capsys)[0]["server"]["EXPECTED_VERSIONS"]
    assert "_VERSION" not in value and "PERCONA_PG_PATCH" not in value
    assert "percona-ppg-server" not in value  # no readable binary
    assert "percona-image" not in value  # belongs to the containers subproject


def test_values_follow_the_project(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    _obs(monkeypatch)
    value = _show("ppg:staging:17", capsys)[0]["server"]["EXPECTED_VERSIONS"]
    assert "percona-pgaudit=17.0" in value.split("\n")


def test_entry_value_wins(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    _obs(monkeypatch)
    assert (
        _show("ppg:staging:18", capsys)[0]["pinned"]["EXPECTED_VERSIONS"]
        == "percona-pgbackrest=1.0"
    )


def test_show_without_flag_makes_no_obs_request(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    calls = _obs(monkeypatch)
    params, _ = _show("ppg:staging:18", capsys, expected_versions=False)
    assert calls == []
    assert "EXPECTED_VERSIONS" not in params["server"]


def test_conflict_aborts(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    data = {
        "isv:percona:ppg:staging:18": {
            "percona-pgbackrest": {R9: "2.60.0-1.1", D12: "2.59.2-1"},
        }
    }
    _obs(monkeypatch, data)
    with pytest.raises(SystemExit, match="percona-pgbackrest: OBS builds disagree"):
        _show("ppg:staging:18", capsys)


def test_pr_fallback_only_for_absent_packages(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    data = {
        "isv:percona:PR:pr-5:ppg:staging:18": {
            "percona-pgaudit": {},  # present, build failed
        },
        "isv:percona:ppg:staging:18": OBS["isv:percona:ppg:staging:18"],
    }
    calls = _obs(monkeypatch, data)
    params, err = _show(
        "ppg:staging:18", capsys, rootprj="isv:percona:PR:pr-5", fallback="isv:percona"
    )
    value = params["server"]["EXPECTED_VERSIONS"]
    assert "percona-pgbackrest=2.60.0" in value  # absent -> production
    assert "percona-pgaudit" not in value  # present w/o binaries: no fallback
    assert "percona-pgaudit" in err
    assert "isv:percona:ppg:staging:18" in calls


def test_mirror_uses_staging_structure_and_prerelease_versions(
    tmp_path, monkeypatch, capsys
):
    _tree(tmp_path, monkeypatch)
    rel = tmp_path / "root" / "ppg" / "releases" / "18"
    rel.mkdir(parents=True)
    (rel / "release.yaml").write_text(
        "project: ppg:staging:18\nreleases:\n  - ppg/18.6-2\n"
    )
    (rel / "project.yaml").write_text(
        "title: R\nqa:\n  - name: server\n    pipeline: p\n"
        "    parameters:\n      A: '1'\n"
    )
    data = {
        "isv:percona:PR:pr-148:ppg:releases:18": {
            "percona-pgbackrest": {R9: "2.60.0-1.1"}
        },
        "isv:percona:ppg:releases:18": {"percona-pgbackrest": {R9: "9.9.9-1"}},
    }
    calls = _obs(monkeypatch, data)
    params, _ = _show("ppg:releases:18", capsys, rootprj="isv:percona:PR:pr-148")
    assert "percona-pgbackrest=2.60.0" in params["server"]["EXPECTED_VERSIONS"]
    assert "isv:percona:ppg:releases:18" not in calls


def test_artifact_packages_are_not_candidates(tmp_path, monkeypatch):
    _tree(tmp_path, monkeypatch)
    pkg = tmp_path / "root" / "ppg" / "staging" / "18" / "containers" / "percona-image"
    (pkg / "obs" / "Dockerfile").write_text("FROM x\n")
    assert cmd_qa._is_artifact_package(pkg)
    calls = _obs(monkeypatch, {"isv:percona:ppg:staging:18:containers": {}})
    cmd_qa._own_package_versions("ppg:staging:18:containers", _lookup())
    assert calls == []


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


def test_package_key_scopes_the_entry():
    versions = {"etcd": "3.5.34", "percona-pgbackrest": "2.60.0"}
    entries = [
        {"name": "x", "pipeline": "p", "parameters": {"A": "1"}, "package": "etcd"}
    ]
    out = cmd_qa._with_expected_versions(entries, "ppg:staging:18", None, versions)
    assert out and out[0]["parameters"]["EXPECTED_VERSIONS"] == "etcd=3.5.34"


def test_package_key_must_be_a_string():
    with pytest.raises(SystemExit, match="qa.package"):
        cmd_qa._validate_qa(
            {"pipeline": "p", "parameters": {"A": 1}, "package": ""}, "P"
        )


def test_nothing_added_without_package_versions():
    entries = [{"name": "x", "pipeline": "p", "parameters": {"A": "1"}}]
    assert cmd_qa._with_expected_versions(entries, "any", None, {}) is entries


def test_no_entries_stays_none():
    assert cmd_qa._with_expected_versions(None, "any", None, {"a": "1"}) is None


def test_run_without_apiurl_errors(tmp_path, monkeypatch):
    _tree(tmp_path, monkeypatch)
    args = SimpleNamespace(rootprj="isv:percona", apiurl=None)
    with pytest.raises(SystemExit, match="EXPECTED_VERSIONS needs an OBS connection"):
        cmd_qa._version_lookup(args, "ppg:staging:18")


def test_qa_run_dry_run_shows_it(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    args = SimpleNamespace(
        project="ppg:staging:18",
        rootprj="isv:percona",
        env_overrides=[],
        profile=None,
        apiurl="http://obs",
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
    _obs(monkeypatch)
    cmd_qa.cmd_qa_run(args)
    out = capsys.readouterr().out
    assert "EXPECTED_VERSIONS" in out and "percona-pgbackrest=2.60.0" in out


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
    (containers / "percona-distribution-postgresql" / "obs" / "Dockerfile").write_text(
        "FROM x\n"
    )
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
    _obs(
        monkeypatch,
        {
            "isv:percona:ppg:staging:18": {
                "percona-pgbackrest": {R9: "2.60.0-1.1"},
                "percona-pgaudit": {R9: "18.0-1.1"},
            },
            "isv:percona:ppg:staging:17": {
                "percona-pgbackrest": {R9: "2.59.0-1.1"},
                "percona-pgaudit": {R9: "17.1-1.1"},
                "percona-only17": {R9: "1.0-1.1"},
            },
        },
    )
    params, _ = _show("ppg:staging:18:containers", capsys)
    lines = params["ubi9"]["EXPECTED_VERSIONS"].split("\n")
    # first path (18) wins over the second (17); packages only in 17 still appear
    assert lines == [
        "percona-only17=1.0",
        "percona-pgaudit=18.0",
        "percona-pgbackrest=2.60.0",
    ]


def test_project_with_own_versions_does_not_follow_paths(tmp_path, monkeypatch):
    _container_tree(tmp_path, monkeypatch)
    calls = _obs(
        monkeypatch,
        {
            "isv:percona:ppg:staging:18": {
                "percona-pgbackrest": {R9: "2.60.0-1.1"},
                "percona-pgaudit": {R9: "18.0-1.1"},
            },
        },
    )
    assert cmd_qa._package_versions("ppg:staging:18", _lookup()) == {
        "percona-pgaudit": "18.0",
        "percona-pgbackrest": "2.60.0",
    }
    assert calls == ["isv:percona:ppg:staging:18"] * 2


def _tarball_tree(tmp_path, monkeypatch, with_recipe=True):
    """ppg/staging/18 packages and 18:tarballs: own percona-psql + a tarball recipe."""
    root = tmp_path / "root"
    staging = root / "ppg" / "staging"
    _package(staging / "18" / "percona-pgbackrest", service=_service("2.59.2"))
    _package(staging / "18" / "percona-psql", service=_service("99.0"))
    (staging / "18" / "project.yaml").write_text("title: P\n")
    tarballs = staging / "18" / "tarballs"
    _package(tarballs / "percona-psql", service=_service("18.6"))
    _package(tarballs / "percona-postgresql-tarball", service="<services/>")
    if with_recipe:
        (tarballs / "percona-postgresql-tarball" / "obs" / "simpleimage").write_text(
            "Name: x\n"
        )
    (tarballs / "project.yaml").write_text(
        "title: T\nrepositories:\n  - name: ssl3\n    paths:\n"
        "      - subproject: ppg:staging:18\n        repository: RockyLinux_9\n"
        "    archs: [x86_64]\n"
    )
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_qa, "REPO_ROOT", root)


def test_no_fallback_to_a_lower_provider_without_binaries(
    tmp_path, monkeypatch, capsys
):
    _container_tree(tmp_path, monkeypatch)
    _obs(
        monkeypatch,
        {
            "isv:percona:ppg:staging:18": {
                "percona-pgbackrest": {R9: "2.60.0-1.1"},
                "percona-pgaudit": {},  # present, build failed
            },
            "isv:percona:ppg:staging:17": {
                "percona-pgbackrest": {R9: "2.59.0-1.1"},
                "percona-pgaudit": {R9: "17.1-1.1"},
            },
        },
    )
    params, err = _show("ppg:staging:18:containers", capsys)
    value = params["ubi9"]["EXPECTED_VERSIONS"]
    assert "percona-pgaudit" not in value
    assert "percona-pgbackrest=2.60.0" in value
    assert "no OBS binaries for:" in err and "percona-pgaudit" in err


def test_project_without_resolved_versions_does_not_follow_paths(
    tmp_path, monkeypatch, capsys
):
    _container_tree(tmp_path, monkeypatch)
    staging = tmp_path / "root" / "ppg" / "staging" / "18"
    shutil.rmtree(staging / "percona-pgaudit")  # only percona-pgbackrest remains
    (staging / "project.yaml").write_text(
        "title: P\nrepositories:\n  - name: r\n    paths:\n"
        "      - subproject: ppg:staging:17\n        repository: UBI_9\n"
        "    archs: [x86_64]\n"
        "qa:\n  - name: srv\n    pipeline: p\n    parameters:\n      A: '1'\n"
    )
    calls = _obs(
        monkeypatch,
        {
            "isv:percona:ppg:staging:18": {"percona-pgbackrest": {}},
            "isv:percona:ppg:staging:17": {"percona-only17": {R9: "1.0-1.1"}},
        },
    )
    params, err = _show("ppg:staging:18", capsys)
    assert "EXPECTED_VERSIONS" not in params["srv"]
    assert "isv:percona:ppg:staging:17" not in calls
    assert "warning: no OBS binaries for: percona-pgbackrest" in err


_TARBALL_OBS = {
    "isv:percona:ppg:staging:18": {
        "percona-pgbackrest": {R9: "2.60.0-1.1"},
        "percona-psql": {R9: "99.0-1.1"},
    },
    "isv:percona:ppg:staging:18:tarballs": {
        "percona-psql": {R9: "18.6-1.1"},
        "percona-postgresql-tarball": {},
    },
}


def test_tarball_project_adds_the_bundled_components(tmp_path, monkeypatch):
    _tarball_tree(tmp_path, monkeypatch)
    assert cmd_qa._builds_artifacts("ppg:staging:18:tarballs")
    _obs(monkeypatch, _TARBALL_OBS)
    assert cmd_qa._package_versions("ppg:staging:18:tarballs", _lookup()) == {
        "percona-pgbackrest": "2.60.0",  # from ppg:staging:18, which it builds from
        "percona-psql": "18.6",  # its own package wins over 18's
    }


def test_project_with_own_versions_and_no_recipe_does_not_follow_paths(
    tmp_path, monkeypatch
):
    _tarball_tree(tmp_path, monkeypatch, with_recipe=False)
    assert not cmd_qa._builds_artifacts("ppg:staging:18:tarballs")
    _obs(monkeypatch, _TARBALL_OBS)
    assert cmd_qa._package_versions("ppg:staging:18:tarballs", _lookup()) == {
        "percona-psql": "18.6"
    }
