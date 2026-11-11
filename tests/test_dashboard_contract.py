"""Pin the names the external release dashboard depends on.

See docs/superpowers/specs/2026-11-11-dashboard-release-contract-design.md § 4.
Renaming any of these strings breaks the dashboard; change the spec first.
"""

from pathlib import Path

import yaml

from percona_obs import cmd_qa

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text()


def _load(name: str) -> dict:
    return yaml.safe_load(_text(name))


PR = _load("obs-release-pr.yml")
REL = _load("obs-release.yml")


def test_release_pr_job_names():
    jobs = PR["jobs"]
    assert (
        jobs["populate"]["name"] == "Populate pre-release (${{ matrix.instance.name }})"
    )
    assert (
        jobs["cdn-wait"]["name"]
        == "Wait for download CDN (${{ matrix.instance.name }})"
    )
    assert jobs["qa"]["name"] == "Release"
    assert jobs["qa"]["uses"] == "./.github/workflows/qa-fanout.yml"


def test_qa_lane_context_prefix():
    # qa-fanout names each job by status_context; GitHub joins the caller's
    # job name ("Release") and it: "Release / OBS QA / ...".
    context = cmd_qa._status_context("ppg:releases:18", None, None, "")
    assert context.startswith("OBS QA / ")
    assert f"Release / {context}".startswith("Release / OBS QA / ")


def test_populate_report_artifact_and_format():
    steps = PR["jobs"]["populate"]["steps"]
    uploads = [
        s for s in steps if s.get("uses", "").startswith("actions/upload-artifact")
    ]
    assert [u["with"]["name"] for u in uploads] == [
        "prerelease-report-${{ matrix.instance.name }}"
    ]
    text = _text("obs-release-pr.yml")
    assert (
        "{project: $p, prerelease: $pre, outcome: $o, source_commit: $s, removals: $r}"
        in text
    )


def test_release_pr_label():
    assert "'qa-release'" in _text("obs-release-pr.yml")


def test_release_pr_sync_gate():
    # PyYAML loads the bare `on:` key as True; `unlabeled` must stay unsubscribed.
    assert PR[True]["pull_request"]["types"] == [
        "opened",
        "synchronize",
        "reopened",
        "labeled",
    ]
    resolve_if = PR["jobs"]["resolve"]["if"]
    assert "'obs-sync'" in resolve_if and "'qa-release'" in resolve_if
    assert PR["jobs"]["populate"]["if"] == "needs.resolve.outputs.populate == 'true'"


def test_obs_release_names():
    assert REL["run-name"] == "Release PR #${{ inputs.pr_number }}"
    jobs = REL["jobs"]
    assert jobs["release"]["name"] == "Release to OBS (${{ matrix.instance.name }})"
    assert (
        jobs["finalize"]["name"] == "Publish GitHub releases and delete the pre-release"
    )
    assert (
        jobs["delete"]["name"] == "Delete the pre-release (${{ matrix.instance.name }})"
    )
    # PyYAML loads the bare `on:` key as True.
    assert set(REL[True]["workflow_dispatch"]["inputs"]) == {"pr_number", "tags"}


def test_unit_list_file_exists():
    assert (ROOT / "docs" / "versions" / "release-units.json").is_file()


CUT = _load("obs-release-cut.yml")


def test_release_cut_workflow():
    # PyYAML loads the bare `on:` key as True.
    assert CUT["run-name"] == "Cut ${{ inputs.branch }}"
    assert list(CUT[True]) == ["workflow_dispatch"]
    inputs = CUT[True]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"units", "branch"}
    assert all(i["required"] for i in inputs.values())
    assert CUT["concurrency"] == {
        "group": "obs-release-cut-${{ inputs.branch }}",
        "cancel-in-progress": False,
    }
    perms = CUT["jobs"]["cut"]["permissions"]
    assert perms == {"contents": "write", "actions": "read", "packages": "read"}
    steps = CUT["jobs"]["cut"]["steps"]
    upload = [
        s for s in steps if s.get("with", {}).get("name") == "generated-changelogs"
    ]
    assert len(upload) == 1 and "if" not in upload[0]
    names = [s.get("name") for s in steps]
    assert names.index("Push the release branch") < steps.index(upload[0])
    assert names.index("Squash into one commit and summarize") < names.index(
        "Push the release branch"
    )
    assert "gh pr create" not in _text("obs-release-cut.yml")


def test_release_cut_annotates_a_failed_unit():
    text = _text("obs-release-cut.yml")
    assert "::error::${unit}: project release failed" in text
