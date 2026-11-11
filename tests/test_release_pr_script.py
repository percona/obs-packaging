"""Pure helpers of the release-PR workflow (.github/scripts/release_pr.py)."""

import importlib.util
import pytest
from pathlib import Path

_SCRIPTS = Path(__file__).parent.parent / ".github/scripts"


def _load():
    spec = importlib.util.spec_from_file_location(
        "release_pr", _SCRIPTS / "release_pr.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_classify_files():
    m = _load()
    assert m.classify_files(
        [
            "root/ppg/releases/18/release.yaml",
            "root/ppg/releases/18/CHANGELOG.md",
            "docs/x.md",
        ]
    ) == ("release", ["root/ppg/releases/18/release.yaml"])
    assert (
        m.classify_files(
            ["root/ppg/releases/18/release.yaml", "root/ppg/staging/18/x/rpm/x.spec"]
        )[0]
        == "mixed"
    )
    assert m.classify_files(["docs/x.md"]) == ("none", [])


def test_release_projects():
    m = _load()
    assert m.release_projects(
        [
            "root/ppg/releases/18/release.yaml",
            "root/ppg/releases/17/release.yaml",
            "root/ppg/releases/18/release.yaml",
        ]
    ) == ["ppg:releases:17", "ppg:releases:18"]


def test_conflicting_prs_only_older_same_file():
    m = _load()
    mine = ["root/ppg/releases/18/release.yaml"]
    others = [
        {"number": 10, "files": ["root/ppg/releases/18/release.yaml"]},
        {
            "number": 12,
            "files": ["root/ppg/releases/18/release.yaml"],
        },  # newer: not a conflict for 11
        {"number": 9, "files": ["root/ppg/releases/17/release.yaml"]},
        {"number": 11, "files": mine},  # self
    ]
    assert m.conflicting_prs(11, mine, others) == [
        (10, "root/ppg/releases/18/release.yaml")
    ]


def test_prerelease_project():
    m = _load()
    assert (
        m.prerelease_project("isv:percona:PR", 42, "ppg:releases:18")
        == "isv:percona:PR:pr-42:ppg:releases:18"
    )


def test_decide():
    m = _load()
    rel = ["root/ppg/releases/18/release.yaml"]
    assert m.decide("none", [], True) == (
        "none",
        "this PR changes no release.yaml; nothing to populate",
    )
    assert m.decide("release", [], False) == ("none", None)
    kind, err = m.decide("mixed", rel, False)
    assert kind == "mixed" and err and "also changes other root/ files" in err
    assert m.decide("release", rel, True) == ("release", None)


def test_changelog_only():
    m = _load()
    assert m.changelog_only(
        ["root/ppg/releases/17/CHANGELOG.md", "root/ppg/releases/18/CHANGELOG.md"]
    )
    assert not m.changelog_only(
        ["root/ppg/releases/18/CHANGELOG.md", "root/ppg/releases/18/release.yaml"]
    )
    assert not m.changelog_only(["root/ppg/staging/18/CHANGELOG.md"])
    assert not m.changelog_only([])


def test_cli_classify_push_reads_head_sha(tmp_path, monkeypatch):
    # A synchronize push (--since) looks up the PR head; gh prints a jq
    # string result unquoted, so the lookup must not use --jq.
    import json
    import subprocess

    mod = _load()
    files = [{"path": "root/ppg/releases/17/release.yaml"}]

    def fake_run(cmd, capture_output=True, text=True):
        args = cmd[1:]
        if args[:2] == ["pr", "view"] and "files" in args:
            out = json.dumps(files)
        elif args[:2] == ["pr", "list"]:
            out = "[]"
        elif args[:2] == ["pr", "view"] and "headRefOid" in args:
            out = "abc123\n" if "--jq" in args else json.dumps({"headRefOid": "abc123"})
        elif args[0] == "api":
            assert args[1].endswith("/compare/old...abc123")
            out = json.dumps(["root/ppg/releases/17/CHANGELOG.md"])
        else:
            raise AssertionError(cmd)
        return subprocess.CompletedProcess(cmd, 0, out, "")

    out_file = tmp_path / "out"
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod._cli_classify(201, False, "old")
    assert "kind=changelog" in out_file.read_text()


def test_nested_release_yaml_is_a_release_file():
    m = _load()
    files = [
        "root/ppg/releases/18/extras/release.yaml",
        "root/ppg/releases/18/extras/CHANGELOG.md",
    ]
    kind, yamls = m.classify_files(files)
    assert (kind, yamls) == ("release", ["root/ppg/releases/18/extras/release.yaml"])
    assert m.release_projects(yamls) == ["ppg:releases:18:extras"]
    assert m.changelog_only(["root/ppg/releases/common/upgrade/extras/CHANGELOG.md"])


def test_project_for_tag(tmp_path):
    m = _load()
    rel = tmp_path / "root/ppg/releases/18"
    (rel / "extras").mkdir(parents=True)
    (rel / "release.yaml").write_text(
        "project: ppg:staging:18\nreleases:\n- ppg/18.6-5\n"
    )
    (rel / "extras" / "release.yaml").write_text(
        "project: ppg:staging:18:extras\n"
        "releases:\n- {tag: ppg/extras-18.6-6, source_commit: abc}\n"
    )
    assert m.project_for_tag("ppg/extras-18.6-6", tmp_path) == "ppg:releases:18:extras"
    assert m.project_for_tag("ppg/18.6-5", tmp_path) == "ppg:releases:18"
    assert m.project_for_tag("ppg/18.6-4", tmp_path) is None


@pytest.mark.parametrize(
    "kind,event,action,label,run_sync,want",
    [
        ("release", "pull_request", "opened", "", False, False),
        ("release", "pull_request", "synchronize", "", False, False),
        ("release", "pull_request", "reopened", "", True, True),
        ("release", "pull_request", "synchronize", "", True, True),
        ("release", "pull_request", "labeled", "obs-sync", True, True),
        ("release", "pull_request", "labeled", "obs-sync", False, False),
        ("release", "pull_request", "labeled", "qa-release", True, False),
        ("release", "pull_request", "labeled", "qa-release", False, False),
        ("release", "workflow_dispatch", "", "", False, True),
        ("changelog", "pull_request", "synchronize", "", True, False),
        ("none", "workflow_dispatch", "", "", True, False),
    ],
)
def test_should_populate(kind, event, action, label, run_sync, want):
    assert _load().should_populate(kind, event, action, label, run_sync) is want


def _run_classify(tmp_path, monkeypatch, files, env, since=None, strict=False):
    import json
    import subprocess

    mod = _load()

    def fake_run(cmd, capture_output=True, text=True):
        args = cmd[1:]
        if args[:2] == ["pr", "view"] and "files" in args:
            out = json.dumps(files)
        elif args[:2] == ["pr", "list"]:
            out = "[]"
        elif args[:2] == ["pr", "view"] and "headRefOid" in args:
            out = json.dumps({"headRefOid": "abc123"})
        elif args[0] == "api":
            out = json.dumps(["root/ppg/releases/17/CHANGELOG.md"])
        else:
            raise AssertionError(cmd)
        return subprocess.CompletedProcess(cmd, 0, out, "")

    out_file = tmp_path / "out"
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    for k in ("EVENT_NAME", "EVENT_ACTION", "EVENT_LABEL", "RUN_SYNC"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod._cli_classify(201, strict, since)
    return out_file.read_text()


_REL = [{"path": "root/ppg/releases/17/release.yaml"}]


def test_cli_classify_writes_populate(tmp_path, monkeypatch, capsys):
    env = {"EVENT_NAME": "pull_request", "EVENT_ACTION": "opened", "RUN_SYNC": "true"}
    out = _run_classify(tmp_path, monkeypatch, _REL, env)
    assert "kind=release" in out and "populate=true" in out
    assert "not started" not in capsys.readouterr().out


def test_cli_classify_unlabelled_notice(tmp_path, monkeypatch, capsys):
    env = {"EVENT_NAME": "pull_request", "EVENT_ACTION": "opened", "RUN_SYNC": "false"}
    out = _run_classify(tmp_path, monkeypatch, _REL, env)
    assert "populate=false" in out
    assert (
        "::notice::pre-release sync not started: add the obs-sync label to this PR"
        in capsys.readouterr().out
    )


def test_cli_classify_changelog_push_not_populated(tmp_path, monkeypatch):
    env = {
        "EVENT_NAME": "pull_request",
        "EVENT_ACTION": "synchronize",
        "RUN_SYNC": "true",
    }
    out = _run_classify(tmp_path, monkeypatch, _REL, env, since="old")
    assert "kind=changelog" in out and "populate=false" in out


def test_cli_classify_none_writes_populate_false(tmp_path, monkeypatch):
    out = _run_classify(
        tmp_path, monkeypatch, [{"path": "README.md"}], {"RUN_SYNC": "true"}
    )
    assert "kind=none" in out and "populate=false" in out
