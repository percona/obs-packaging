"""Structure of the manual freeze workflow and the nightly frozen-units warning."""

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _on(wf: dict) -> dict:
    # PyYAML (YAML 1.1) parses the bare key `on` as boolean True.
    return wf.get("on", wf.get(True))


FREEZE = _load("obs-freeze.yml")
SYNC = _load("sync-main.yml")
JOB = FREEZE["jobs"]["freeze"]
SYNC_JOB = SYNC["jobs"]["sync"]


def _step(job: dict, name_prefix: str) -> dict:
    for s in job["steps"]:
        if s.get("name", "").startswith(name_prefix):
            return s
    raise AssertionError(f"no step named {name_prefix!r}")


def test_trigger_and_inputs():
    on = _on(FREEZE)
    assert list(on) == ["workflow_dispatch"]
    inputs = on["workflow_dispatch"]["inputs"]
    assert inputs["units"]["required"] is True
    assert inputs["units"]["description"] == (
        "Release unit roots, space-separated "
        "(e.g. ppg:staging:18 ppg:staging:17:extras)"
    )
    assert inputs["action"]["required"] is True
    assert inputs["action"]["type"] == "choice"
    assert inputs["action"]["options"] == ["freeze", "unfreeze"]
    assert FREEZE["permissions"] == {}
    assert "run-name" in FREEZE


def test_matrix_and_concurrency():
    assert JOB["strategy"]["fail-fast"] is False
    assert (
        JOB["strategy"]["matrix"]["instance"] == "${{ fromJSON(vars.OBS_INSTANCES) }}"
    )
    assert JOB["concurrency"] == {
        "group": "obs-freeze-${{ matrix.instance.name }}",
        "cancel-in-progress": False,
    }
    for key in ("runs-on", "container"):
        assert JOB[key] == SYNC_JOB[key]
    assert JOB["permissions"] == {"contents": "read", "packages": "read"}


def test_setup_steps_match_sync():
    uses = [s["uses"] for s in JOB["steps"] if "uses" in s]
    assert "./.github/actions/obs-setup" in uses
    ours = [s for s in JOB["steps"] if s.get("uses") == "./.github/actions/obs-setup"]
    theirs = [
        s for s in SYNC_JOB["steps"] if s.get("uses") == "./.github/actions/obs-setup"
    ]
    assert ours == theirs
    prefix = "Create percona-obs profile"
    a, b = _step(JOB, prefix), _step(SYNC_JOB, prefix)
    assert a["run"] == b["run"] and a["env"] == b["env"] and a["shell"] == b["shell"]


def test_validates_units_before_obs_steps():
    names = [s.get("name", s.get("uses", "")) for s in JOB["steps"]]
    validate = next(
        i
        for i, s in enumerate(JOB["steps"])
        if "release_cut.py check" in s.get("run", "")
    )
    setup = next(
        i
        for i, s in enumerate(JOB["steps"])
        if s.get("uses") == "./.github/actions/obs-setup"
    )
    assert validate < setup, names
    assert 'check -- "${UNIT_LIST[@]}"' in JOB["steps"][validate]["run"]


def test_no_input_interpolated_into_scripts():
    for s in JOB["steps"]:
        assert "${{ inputs." not in s.get("run", "")


def test_run_step():
    s = _step(JOB, "Freeze")
    assert s["shell"] == "bash"
    assert s["env"]["ACTION"] == "${{ inputs.action }}"
    assert s["env"]["UNITS"] == "${{ inputs.units }}"
    run = s["run"]
    assert "read -r -a UNIT_LIST" in run
    assert '-P main project "$ACTION" "${UNIT_LIST[@]}"' in run
    assert "GITHUB_STEP_SUMMARY" in run
    assert "pipefail" in run


def test_nightly_warning_step():
    steps = SYNC_JOB["steps"]
    names = [s.get("name") for s in steps]
    step = next(s for s in steps if "freeze-status" in s.get("run", ""))
    assert names.index("Sync to OBS") + 1 == steps.index(step)
    # always(): a red nightly sync must still print the reminder.
    assert step["if"] == "always() && github.event_name == 'schedule'"
    assert step["continue-on-error"] is True
    assert step["timeout-minutes"] == 5
    assert "-P main project freeze-status --github-warning" in step["run"]


def test_run_blocks_are_valid_bash(tmp_path):
    for wf in (FREEZE, SYNC):
        for job in wf["jobs"].values():
            for s in job.get("steps", []):
                run = s.get("run")
                if not run or s.get("shell") != "bash":
                    continue
                if "${{" in run:
                    run = run.replace("${{", "$ {{")
                f = tmp_path / "s.sh"
                f.write_text(run)
                subprocess.run(["bash", "-n", str(f)], check=True)
