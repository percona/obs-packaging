# Package-level `qa:` blocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a `package.yaml` declare its own Jenkins QA lanes, discovered by `qa show`/`qa run` next to the project's `project.yaml` block, and run by CI only when the package is present in the PR's OBS subproject.

**Architecture:** `percona_obs/cmd_qa.py` loads a list of `Lane` objects (the project's block plus one per direct package with a `qa:` key, following `_shared/` symlinks) instead of a single block; `qa show --json` adds `package`/`package_filter` fields and inserts the package into `status_context`; `qa run --package` selects a lane. CI keeps the filesystem/OBS split: the tool never talks to OBS for QA, and `.github/scripts/list_qa_matrix.py` drops package lanes whose package is absent from the OBS project when `QA_PACKAGES_PRESENT_ONLY=true` (PR runs). `filter_qa_matrix.py` reuses that helper for the manual workflow.

**Tech Stack:** Python 3 (argparse, dataclasses, PyYAML, osc), pytest, GitHub Actions YAML.

**Spec:** `docs/superpowers/specs/2026-10-07-package-qa-blocks-design.md`

## Global Constraints

- Project-lane `qa show --json` output must stay byte-for-byte identical except for the two new fields `package: ""` and `package_filter: ""`. Existing `status_context` strings for project lanes do not change.
- `qa show` and `qa run` never call OBS. OBS presence filtering lives only in `.github/scripts/`.
- Discovery is non-recursive: `qa show ppg:staging:18` must not report packages of `ppg:staging:18:containers`.
- Package `qa:` blocks are validated with the existing `_validate_qa`; error prefixes are `<project>/<package>`.
- The segment-uniqueness check runs per block (project block and each package block are separate namespaces).
- After every Python change run `venv/bin/black percona_obs/ tests/` then `venv/bin/pyright`; both must pass before the task's commit.
- Commits use `git commit -s`. No `Co-Authored-By` lines (CLAUDE.md rule).
- Work happens in the worktree `.claude/worktrees/package-qa-blocks` on branch `package-qa-blocks`. Never push or open a PR without asking.

**User decisions (already made):**
- Package lanes run on PR checks only when the package is present in the PR's OBS subproject (any real package, including dep-cascade promotions); nightly and manual runs cover all package lanes.
- Same commands with an optional `--package PKG` selector; no separate positional.
- `qa show` is filesystem-only: package directories enumerated on disk (symlinks followed), `package.yaml` macro-rendered, `qa:` parsed. A package's `obs/_link` file is irrelevant.
- `qa:` blocks will live under `_shared/<pkg>/package.yaml` and render per major via `%!{PG_MAJOR_VERSION}`.
- CI env var name `QA_PACKAGES_PRESENT_ONLY`; `obs-qa-run` dispatch input name `package`.

---

## File Structure

| file | responsibility after this plan |
|---|---|
| `percona_obs/cmd_qa.py` | `Lane` dataclass, `_normalise_qa_block` (validate one loaded block), `_load_qa_lanes` (project + direct packages), `_status_context`, show/run/status/retry/list output aware of `package` |
| `percona_obs/qa_state.py` | `RunState.package` (default `""`), persisted, reported |
| `percona_obs/cli.py` | `qa run --package`, help text mentions package.yaml |
| `.github/scripts/list_qa_matrix.py` | `normalize_entry` fills `package_filter`; `drop_absent_packages` + `fetch_present_packages` helpers; `main` applies them when `QA_PACKAGES_PRESENT_ONLY=true` |
| `.github/scripts/filter_qa_matrix.py` | `QA_PACKAGE` selection; applies the presence drop (imported from `list_qa_matrix`) when `QA_PACKAGES_PRESENT_ONLY=true` |
| `.github/scripts/resolve_qa_instance.py` | `validate_package` for the new dispatch input |
| `.github/workflows/obs-pr-check.yml` | sets `QA_PACKAGES_PRESENT_ONLY`, passes `package_filter` |
| `.github/workflows/obs-nightly-qa.yml` | passes `name_filter` and `package_filter` |
| `.github/workflows/obs-qa-run.yml` | `package` input, `QA_PACKAGE`, presence env when `pr_number` set, passes `package_filter` |
| `tests/test_qa_package_lanes.py` | new: loader, show, run tests for package lanes |
| `tests/test_qa_entry_name.py` | updated for the renamed loader |
| `tests/test_list_qa_matrix.py`, `tests/test_manual_qa_scripts.py` | new tests for the script changes |
| `docs/PERCONA_OBS_TOOL.md`, `.github/copilot-instructions.md` | docs |

---

### Task 1: `Lane` and `_load_qa_lanes` loader

**Goal:** Replace `_load_qa_block` with `_load_qa_lanes`, which returns the project's block plus one `Lane` per direct package whose `package.yaml` has a `qa:` key, rendered through the package directory's macro chain.

**Files:**
- Modify: `percona_obs/cmd_qa.py:1-152` (module docstring, imports, loader section)
- Modify: `tests/test_qa_entry_name.py:70-120` (four tests call `_load_qa_block`)
- Create: `tests/test_qa_package_lanes.py`

**Acceptance Criteria:**
- [ ] `_load_qa_lanes("ppg:17", {})` on a tree with a project block and two packages (one with `qa:`, one without) returns two lanes: `Lane(None, [...])` then `Lane("pkg", [...])`.
- [ ] A `_shared/pkg/package.yaml` reached through `17/pkg` and `18/pkg` symlinks renders `%!{PG_MAJOR_VERSION}` as `17` and `18` respectively.
- [ ] A package inside a subproject directory (`17/sub/deep/package.yaml`) is not discovered by `_load_qa_lanes("ppg:17", ...)`.
- [ ] A project with neither block returns `[]`.
- [ ] Two unnamed entries sharing a pipeline inside one package block raise `SystemExit` whose message starts with `error: ppg:17/pkg:`; the same pipeline unnamed in the project block and in a package block does not raise.
- [ ] Existing tests in `tests/test_qa_entry_name.py` pass using `_load_qa_lanes(p, {})[0].entries`.

**Verify:** `venv/bin/python -m pytest tests/test_qa_package_lanes.py tests/test_qa_entry_name.py -q` → all pass; `venv/bin/black percona_obs/ tests/ && venv/bin/pyright` → "0 errors".

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_qa_package_lanes.py`:

```python
"""Package-level ``qa:`` blocks declared in ``package.yaml``.

A project's QA lanes are its own ``project.yaml`` block plus one block per
direct package that declares ``qa:``.  Package blocks under ``_shared/`` are
reached through per-major symlinks and render macros from the link's location.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import percona_obs.cmd_qa as cmd_qa
import percona_obs.common as common

_PROJECT_QA = """\
qa:
  pipeline: ppg-multiOS-parallel
  parameters:
    VERSION: ppg-%!{PG_MAJOR_VERSION}
    IO_METHOD: [worker, sync]
  matrix: [IO_METHOD]
"""

_PKG_QA = """\
title: pkg
qa:
  pipeline: pkg-parallel
  parameters:
    PG_MAJOR: "%!{PG_MAJOR_VERSION}"
    PLATFORMS: [rocky-9, debian-13]
  matrix: [PLATFORMS]
"""


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def tree(tmp_path, monkeypatch) -> Path:
    """root/ppg/{17,18}/{project.yaml, macros.yaml, pkg -> ../_shared/pkg, other/}.

    ``other`` is a package without ``qa:``; ``17/sub/deep`` is a package in a
    subproject and must not be discovered from ``ppg:17``.
    """
    root = tmp_path / "root"
    _write(root, "macros.yaml", "- M: 1\n")
    for major in ("17", "18"):
        _write(root, f"ppg/{major}/macros.yaml", f"- PG_MAJOR_VERSION: {major}\n")
        _write(root, f"ppg/{major}/project.yaml", "title: P\n" + _PROJECT_QA)
        _write(root, f"ppg/{major}/other/package.yaml", "title: other\n")
        (root / "ppg" / major / "pkg").symlink_to(Path("..") / "_shared" / "pkg")
    _write(root, "ppg/_shared/pkg/package.yaml", _PKG_QA)
    _write(root, "ppg/17/sub/project.yaml", "title: sub\n")
    _write(root, "ppg/17/sub/deep/package.yaml", _PKG_QA)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    return root


# --- loader ----------------------------------------------------------------------


def test_lanes_project_then_packages(tree):
    lanes = cmd_qa._load_qa_lanes("ppg:17", {})
    assert [lane.package for lane in lanes] == [None, "pkg"]
    assert lanes[0].entries[0]["pipeline"] == "ppg-multiOS-parallel"
    assert lanes[1].entries[0]["pipeline"] == "pkg-parallel"


def test_shared_package_renders_per_major(tree):
    seventeen = cmd_qa._load_qa_lanes("ppg:17", {})[1].entries[0]
    eighteen = cmd_qa._load_qa_lanes("ppg:18", {})[1].entries[0]
    assert seventeen["parameters"]["PG_MAJOR"] == "17"
    assert eighteen["parameters"]["PG_MAJOR"] == "18"


def test_subproject_packages_are_not_discovered(tree):
    lanes = cmd_qa._load_qa_lanes("ppg:17", {})
    assert "deep" not in [lane.package for lane in lanes]


def test_package_without_qa_is_skipped(tree):
    lanes = cmd_qa._load_qa_lanes("ppg:17", {})
    assert "other" not in [lane.package for lane in lanes]


def test_no_blocks_at_all_is_empty(tree):
    _write(tree, "ppg/17/project.yaml", "title: P\n")
    os.remove(tree / "ppg/_shared/pkg/package.yaml")
    assert cmd_qa._load_qa_lanes("ppg:17", {}) == []


def test_package_only_project(tree):
    _write(tree, "ppg/17/project.yaml", "title: P\n")
    lanes = cmd_qa._load_qa_lanes("ppg:17", {})
    assert [lane.package for lane in lanes] == ["pkg"]


def test_package_block_validation_prefix(tree):
    _write(tree, "ppg/_shared/pkg/package.yaml", "qa:\n  pipeline: x\n")
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_lanes("ppg:17", {})
    assert str(exc.value).startswith("error: ppg:17/pkg: qa.parameters")


def test_segment_uniqueness_is_per_block(tree):
    # project block and package block both have an unnamed entry on pipeline x
    _write(tree, "ppg/17/project.yaml", "qa:\n  pipeline: x\n  parameters:\n    A: b\n")
    _write(tree, "ppg/_shared/pkg/package.yaml", "qa:\n  pipeline: x\n  parameters:\n    A: c\n")
    lanes = cmd_qa._load_qa_lanes("ppg:17", {})
    assert len(lanes) == 2

    # two unnamed entries on the same pipeline INSIDE the package block → error
    _write(
        tree,
        "ppg/_shared/pkg/package.yaml",
        "qa:\n  - pipeline: x\n    parameters:\n      A: b\n"
        "  - pipeline: x\n    parameters:\n      A: c\n",
    )
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_lanes("ppg:17", {})
    assert str(exc.value).startswith("error: ppg:17/pkg: two qa entries")


def test_env_substitution_applies_to_package_block(tree):
    _write(
        tree,
        "ppg/_shared/pkg/package.yaml",
        "qa:\n  pipeline: x\n  parameters:\n    P: ${OBS_ROOTPRJ}:ppg\n",
    )
    lane = cmd_qa._load_qa_lanes("ppg:17", {"OBS_ROOTPRJ": "isv:percona"})[1]
    assert lane.entries[0]["parameters"]["P"] == "isv:percona:ppg"
```

Update `tests/test_qa_entry_name.py`: replace every `cmd_qa._load_qa_block(p, {})` with `cmd_qa._load_qa_lanes(p, {})[0].entries` (four occurrences: `test_name_is_optional_and_must_be_a_non_empty_string`, `test_duplicate_name_is_rejected`, `test_same_pipeline_without_names_is_rejected`, `test_named_entry_loads`). In `test_named_entry_loads` the `assert entries is not None` line can stay.

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_qa_package_lanes.py tests/test_qa_entry_name.py -q`
Expected: FAIL with `AttributeError: module 'percona_obs.cmd_qa' has no attribute '_load_qa_lanes'`.

- [ ] **Step 3: Implement the loader**

In `percona_obs/cmd_qa.py`:

Module docstring, replace the first paragraph with:

```python
"""Implements `percona-obs qa` subcommands.

Reads the optional ``qa:`` block of a project's ``project.yaml`` and of each
direct package's ``package.yaml`` (one *lane* per block), expands every
matrix into one Jenkins job per combination, optionally polls for completion,
and persists per-combo state under ``.percona-obs/qa/<run-id>.json``.
"""
```

Add `import dataclasses` to the stdlib imports. Extend the `.common` import to include `find_packages`, `load_macros`, `load_yaml_with_env`.

Replace `_load_qa_block` (lines 71-111) with:

```python
@dataclasses.dataclass
class Lane:
    """One ``qa:`` block: the project's own (``package is None``) or a package's."""

    package: str | None
    entries: list[dict[str, Any]]


def _lane_where(project: str, package: str | None) -> str:
    """Error-message prefix for a lane: ``<project>`` or ``<project>/<package>``."""
    return project if package is None else f"{project}/{package}"


def _normalise_qa_block(qa: Any, where: str) -> list[dict[str, Any]]:
    """Validate one loaded ``qa:`` value and return it as a list of entries.

    A single-dict ``qa:`` is normalised to a one-element list so callers can
    always iterate.  ``where`` prefixes error messages.
    """
    if isinstance(qa, dict):
        entries: list[Any] = [qa]
    elif isinstance(qa, list):
        entries = qa
    else:
        raise SystemExit(f"error: {where}: qa block must be a mapping or a list")
    # Two entries that disambiguate to the same segment would render the same
    # status_context, i.e. the same check-run name: CI would drop one lane and
    # `qa run` would trigger both under one check.  Reject it here instead.
    seen_segments: set[str] = set()
    for entry in entries:
        _validate_qa(entry, where)
        segment = _entry_segment(entry)
        if segment in seen_segments:
            hint = (
                "give each one a distinct 'name'"
                if not entry.get("name")
                else "rename one of them"
            )
            raise SystemExit(
                f"error: {where}: two qa entries resolve to the same check segment "
                f"{segment!r}; {hint}"
            )
        seen_segments.add(segment)
    return entries


def _load_qa_lanes(project: str, env_vars: dict[str, str]) -> list[Lane]:
    """Load every ``qa:`` block of a project: its own, then its direct packages'.

    The project's ``project.yaml`` block (when present) comes first as
    ``Lane(None, ...)``; then one ``Lane(<dirname>, ...)`` per direct package
    whose ``package.yaml`` declares ``qa:``, in ``find_packages`` order.
    Packages are enumerated on disk only (symlinks into ``_shared/`` are
    followed, and macros resolve from the link's location); subprojects are
    not descended into because CI calls this once per OBS subproject.
    Returns ``[]`` when the project declares no QA at all.
    """
    project_path = resolve_project_path(project)
    if not project_path.is_dir():
        raise SystemExit(f"error: project {project!r} not found at {project_path}")
    lanes: list[Lane] = []
    cfg = load_project_yaml(project_path / "project.yaml", env_vars)
    if cfg.get("qa") is not None:
        lanes.append(Lane(None, _normalise_qa_block(cfg["qa"], project)))
    for _obs_project, package_path in find_packages(
        project_path, project, recursive=False
    ):
        pkg_yaml = package_path / "package.yaml"
        if not pkg_yaml.is_file():
            continue
        pkg_cfg = load_yaml_with_env(
            pkg_yaml, env_vars, macros=load_macros(package_path)
        )
        if pkg_cfg.get("qa") is None:
            continue
        package = package_path.name
        lanes.append(
            Lane(
                package,
                _normalise_qa_block(pkg_cfg["qa"], _lane_where(project, package)),
            )
        )
    return lanes
```

`cmd_qa_show` and `cmd_qa_run` still call `_load_qa_block`; make them compile for now with a minimal adaptation so this task's tests run (Tasks 2 and 3 rewrite them properly):

```python
# in cmd_qa_show, replace:
#     entries = _load_qa_block(args.project, env_vars)
# with:
    lanes = _load_qa_lanes(args.project, env_vars)
    entries = lanes[0].entries if lanes else None
```

```python
# in cmd_qa_run, replace:
#     entries = _load_qa_block(args.project, env_vars)
#     if entries is None:
# with:
    lanes = _load_qa_lanes(args.project, env_vars)
    entries = lanes[0].entries if lanes else None
    if entries is None:
```

- [ ] **Step 4: Run tests, formatter and type checker**

Run: `venv/bin/python -m pytest tests/test_qa_package_lanes.py tests/test_qa_entry_name.py -q`
Expected: all pass.

Run: `venv/bin/black percona_obs/ tests/ && venv/bin/pyright`
Expected: black reports reformatted/unchanged; pyright `0 errors`.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/cmd_qa.py tests/test_qa_package_lanes.py tests/test_qa_entry_name.py
git commit -s -m "qa: load package.yaml qa: blocks as lanes next to the project block"
```

---

### Task 2: `qa show` output with package lanes

**Goal:** `qa show` prints every lane; `--json` combos carry `package`, `package_filter` and a `status_context` that inserts the package after the project.

**Files:**
- Modify: `percona_obs/cmd_qa.py` (`cmd_qa_show`, new `_status_context`)
- Modify: `tests/test_qa_package_lanes.py`

**Acceptance Criteria:**
- [ ] `qa show --json` on the fixture tree emits project combos with `package == ""`, `package_filter == ""` and contexts `OBS QA / ppg:17 / IO_METHOD=worker` etc., followed by package combos with `package == "pkg"`, `package_filter == "--package pkg"` and contexts `OBS QA / ppg:17 / pkg / PLATFORMS=rocky-9` etc.
- [ ] A package block with two named entries yields `OBS QA / ppg:17 / pkg / <name> / <combo>`; a package block with one unnamed, matrix-less entry yields `OBS QA / ppg:17 / pkg`.
- [ ] `tests/test_qa_entry_name.py` project-lane context assertions still pass unchanged.
- [ ] Human output contains a heading `ppg:17 / pkg  →  pipeline: pkg-parallel`.
- [ ] `qa show --json` for a project with no lanes prints `[]`.

**Verify:** `venv/bin/python -m pytest tests/test_qa_package_lanes.py tests/test_qa_entry_name.py -q` → all pass; black + pyright clean.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_qa_package_lanes.py`:

```python
# --- qa show ---------------------------------------------------------------------


def _show_json(project: str, capsys) -> list[dict]:
    args = SimpleNamespace(
        project=project, rootprj="isv:percona", env_overrides=[], json=True
    )
    cmd_qa.cmd_qa_show(args)
    return json.loads(capsys.readouterr().out)


def test_show_json_lists_project_then_package_combos(tree, capsys):
    out = _show_json("ppg:17", capsys)
    assert [(e["package"], e["status_context"]) for e in out] == [
        ("", "OBS QA / ppg:17 / IO_METHOD=worker"),
        ("", "OBS QA / ppg:17 / IO_METHOD=sync"),
        ("pkg", "OBS QA / ppg:17 / pkg / PLATFORMS=rocky-9"),
        ("pkg", "OBS QA / ppg:17 / pkg / PLATFORMS=debian-13"),
    ]
    assert [e["package_filter"] for e in out] == ["", "", "--package pkg", "--package pkg"]
    assert out[2]["params"]["PG_MAJOR"] == "17"
    assert out[2]["pipeline"] == "pkg-parallel"


def test_show_json_package_multi_entry_segment(tree, capsys):
    _write(
        tree,
        "ppg/_shared/pkg/package.yaml",
        "qa:\n"
        "  - name: a\n    pipeline: x\n    parameters:\n      P: [1, 2]\n    matrix: [P]\n"
        "  - name: b\n    pipeline: x\n    parameters:\n      Q: v\n",
    )
    out = _show_json("ppg:17", capsys)
    pkg = [e["status_context"] for e in out if e["package"] == "pkg"]
    assert pkg == [
        "OBS QA / ppg:17 / pkg / a / P=1",
        "OBS QA / ppg:17 / pkg / a / P=2",
        "OBS QA / ppg:17 / pkg / b",
    ]
    assert {e["name_filter"] for e in out if e["package"] == "pkg"} == {
        "--name a",
        "--name b",
    }


def test_show_json_package_single_entry_no_matrix(tree, capsys):
    _write(tree, "ppg/_shared/pkg/package.yaml", "qa:\n  pipeline: x\n  parameters:\n    Q: v\n")
    out = _show_json("ppg:17", capsys)
    assert [e["status_context"] for e in out if e["package"] == "pkg"] == [
        "OBS QA / ppg:17 / pkg"
    ]
    assert [e["label"] for e in out if e["package"] == "pkg"] == ["default"]


def test_show_json_empty_when_no_lanes(tree, capsys):
    _write(tree, "ppg/17/project.yaml", "title: P\n")
    os.remove(tree / "ppg/_shared/pkg/package.yaml")
    assert _show_json("ppg:17", capsys) == []


def test_show_human_output_names_the_package(tree, capsys):
    args = SimpleNamespace(
        project="ppg:17", rootprj="isv:percona", env_overrides=[], json=False
    )
    cmd_qa.cmd_qa_show(args)
    out = capsys.readouterr().out
    assert "ppg:17  →  pipeline: ppg-multiOS-parallel" in out
    assert "ppg:17 / pkg  →  pipeline: pkg-parallel" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_qa_package_lanes.py -q -k show`
Expected: FAIL (`KeyError: 'package'` and/or missing package combos).

- [ ] **Step 3: Implement `_status_context` and rewrite `cmd_qa_show`**

In `percona_obs/cmd_qa.py`, add above the `# `qa show`` section header:

```python
def _status_context(
    project: str, package: str | None, segment: str | None, label: str
) -> str:
    """Check-run name of one combo.

    ``OBS QA / <project>[ / <package>][ / <segment>][ / <combo>]`` — the
    package only for package lanes, the segment only for multi-entry blocks,
    the combo label only when the entry has a ``matrix:``.  Project-lane
    contexts are byte-for-byte what they were before package lanes existed.
    """
    parts = ["OBS QA", project]
    if package:
        parts.append(package)
    if segment:
        parts.append(segment)
    if label:
        parts.append(label)
    return " / ".join(parts)
```

Replace the whole body of `cmd_qa_show` with:

```python
def cmd_qa_show(args: argparse.Namespace) -> None:
    env_vars = _qa_env_vars(args)
    lanes = _load_qa_lanes(args.project, env_vars)
    json_mode: bool = bool(getattr(args, "json", False))

    if not lanes:
        if json_mode:
            print("[]")
        return

    if json_mode:
        out: list[dict[str, Any]] = []
        for lane in lanes:
            package = lane.package or ""
            package_filter = f"--package {package}" if package else ""
            multi_entry = len(lane.entries) > 1
            for entry in lane.entries:
                pipeline = entry["pipeline"]
                name = entry.get("name")
                combos = _expand_matrix(entry)
                matrix_axes = list(entry.get("matrix") or [])
                # Disambiguating segment for a multi-entry block: the entry
                # `name` when it has one (two entries may share a pipeline),
                # else the pipeline, which keeps unnamed entries' contexts.
                segment = (name or pipeline) if multi_entry else None
                name_filter = f"--name {name}" if name else ""
                for label, params in combos:
                    axis_filters = " ".join(
                        f"--filter {axis}={params[axis]}" for axis in matrix_axes
                    )
                    out.append(
                        {
                            "project": args.project,
                            "package": package,
                            "pipeline": pipeline,
                            "name": name or "",
                            "label": label or "default",
                            "axis_filters": axis_filters,
                            "name_filter": name_filter,
                            "package_filter": package_filter,
                            "status_context": _status_context(
                                args.project, lane.package, segment, label
                            ),
                            "params": params,
                        }
                    )
        print(json.dumps(out))
        return

    for lane in lanes:
        where = _lane_where(args.project, lane.package).replace("/", " / ")
        for entry in lane.entries:
            pipeline = entry["pipeline"]
            name = entry.get("name")
            combos = _expand_matrix(entry)
            matrix_axes = list(entry.get("matrix") or [])
            heading = f"{where}  →  pipeline: {pipeline}"
            if name:
                heading += f"  (name: {name})"
            print(_col(_BOLD, heading))
            print(f"{_col(_DIM, 'matrix:')} {', '.join(matrix_axes) or '(none)'}")
            print(f"{_col(_DIM, 'combos:')} {len(combos)}")
            for label, params in combos:
                print()
                print(_col(_CYAN, f"• {label or '(no matrix)'}"))
                _print_params(params)
            print()
```

Note on `where`: `_lane_where` returns `ppg:17/pkg`; the `.replace("/", " / ")` renders the heading as `ppg:17 / pkg`. Project names never contain `/`.

- [ ] **Step 4: Run tests, formatter and type checker**

Run: `venv/bin/python -m pytest tests/test_qa_package_lanes.py tests/test_qa_entry_name.py -q`
Expected: all pass.

Run: `venv/bin/black percona_obs/ tests/ && venv/bin/pyright`
Expected: clean, `0 errors`.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/cmd_qa.py tests/test_qa_package_lanes.py
git commit -s -m "qa show: report package lanes with package/package_filter and nested status_context"
```

---

### Task 3: `qa run --package`, run state and reports

**Goal:** `qa run` triggers every lane by default, `--package PKG` narrows to one package's lanes, and the run state / report / list / status / retry outputs tell package lanes apart.

**Files:**
- Modify: `percona_obs/cmd_qa.py` (`cmd_qa_run`, `cmd_qa_retry` heading, `cmd_qa_list` row)
- Modify: `percona_obs/qa_state.py` (`RunState.package`, `load_state`, `write_report_json`)
- Modify: `percona_obs/cli.py:415-478` (`--package`, help text)
- Modify: `tests/test_qa_package_lanes.py`

**Acceptance Criteria:**
- [ ] `qa run ppg:17 --dry-run` prints both the project pipeline and `pkg-parallel`.
- [ ] `qa run ppg:17 --package pkg --dry-run` prints only `pkg-parallel` and a `package: pkg` line; `--package nope` exits with `error: ppg:17: no package with a qa: block named 'nope'; packages: pkg`.
- [ ] `--package pkg --name a` selects only entry `a` of the package block; `--name` alone matching nothing still errors `no qa entry with name`.
- [ ] `RunState` round-trips `package` through `save_state`/`load_state`; a state file without the key loads with `package == ""`.
- [ ] `write_report_json` output has top-level `package` and `package` on every combo row.
- [ ] `qa list` row shows `ppg:17/pkg` for a package-lane run and `ppg:17` for a project-lane run.
- [ ] `percona-obs qa run --help` lists `--package PKG`.

**Verify:** `venv/bin/python -m pytest tests/test_qa_package_lanes.py tests/test_qa_entry_name.py -q` → all pass; `venv/bin/python -m percona_obs qa run --help | grep -- --package` → one line; black + pyright clean.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_qa_package_lanes.py`:

```python
# --- qa run --package ------------------------------------------------------------


def _run_args(project: str, **kw):
    base = dict(
        project=project,
        rootprj="isv:percona",
        env_overrides=[],
        package=None,
        name=None,
        pipeline=None,
        filter=[],
        param=[],
        dry_run=True,
        wait=False,
        report_json=None,
        profile=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_run_without_package_triggers_every_lane(tree, capsys):
    cmd_qa.cmd_qa_run(_run_args("ppg:17"))
    out = capsys.readouterr().out
    assert "would trigger pipeline 'ppg-multiOS-parallel'" in out
    assert "would trigger pipeline 'pkg-parallel'" in out


def test_run_package_selects_one_lane(tree, capsys):
    cmd_qa.cmd_qa_run(_run_args("ppg:17", package="pkg"))
    out = capsys.readouterr().out
    assert "would trigger pipeline 'pkg-parallel'" in out
    assert "ppg-multiOS-parallel" not in out
    assert "package: pkg" in out


def test_run_unknown_package_errors_listing_packages(tree):
    with pytest.raises(SystemExit) as exc:
        cmd_qa.cmd_qa_run(_run_args("ppg:17", package="nope"))
    assert str(exc.value) == (
        "error: ppg:17: no package with a qa: block named 'nope'; packages: pkg"
    )


def test_run_package_combines_with_name(tree, capsys):
    _write(
        tree,
        "ppg/_shared/pkg/package.yaml",
        "qa:\n"
        "  - name: a\n    pipeline: x\n    parameters:\n      P: va\n"
        "  - name: b\n    pipeline: x\n    parameters:\n      P: vb\n",
    )
    cmd_qa.cmd_qa_run(_run_args("ppg:17", package="pkg", name="a"))
    out = capsys.readouterr().out
    assert "P: va" in out and "P: vb" not in out

    with pytest.raises(SystemExit) as exc:
        cmd_qa.cmd_qa_run(_run_args("ppg:17", name="zzz"))
    assert "no qa entry with name 'zzz'" in str(exc.value)


# --- run state -------------------------------------------------------------------


def test_run_state_round_trips_package(tmp_path, monkeypatch):
    import percona_obs.qa_state as qa_state

    monkeypatch.setattr(qa_state, "_STATE_DIR", tmp_path / "qa")
    state = qa_state.RunState(
        run_id="r1",
        project="ppg:17",
        pipeline="x",
        created_at="t",
        combos=[qa_state.Combo(label="", params={"A": "b"})],
        package="pkg",
    )
    qa_state.save_state(state)
    assert qa_state.load_state("r1").package == "pkg"

    # a state file written before the field existed loads with ""
    path = tmp_path / "qa" / "r0.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "r0",
                "project": "ppg:17",
                "pipeline": "x",
                "created_at": "t",
                "combos": [],
            }
        )
    )
    assert qa_state.load_state("r0").package == ""


def test_report_json_carries_package(tmp_path):
    import percona_obs.qa_state as qa_state

    state = qa_state.RunState(
        run_id="r1",
        project="ppg:17",
        pipeline="x",
        created_at="t",
        combos=[qa_state.Combo(label="P=1", params={"P": "1"})],
        package="pkg",
    )
    out = tmp_path / "report.json"
    qa_state.write_report_json(state, out)
    data = json.loads(out.read_text())
    assert data["package"] == "pkg"
    assert data["combos"][0]["package"] == "pkg"


def test_qa_list_shows_project_slash_package(tmp_path, monkeypatch, capsys):
    import percona_obs.qa_state as qa_state

    monkeypatch.setattr(qa_state, "_STATE_DIR", tmp_path / "qa")
    for run_id, package in (("r1", "pkg"), ("r2", "")):
        qa_state.save_state(
            qa_state.RunState(
                run_id=run_id,
                project="ppg:17",
                pipeline="x",
                created_at="t",
                combos=[],
                package=package,
            )
        )
    cmd_qa.cmd_qa_list(SimpleNamespace(running=False))
    out = capsys.readouterr().out
    assert "ppg:17/pkg  x" in out
    assert "ppg:17  x" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_qa_package_lanes.py -q -k "run or state or report or list"`
Expected: FAIL (`TypeError: RunState.__init__() got an unexpected keyword argument 'package'`, missing pipeline in dry-run output).

- [ ] **Step 3: Extend `qa_state.py`**

In `percona_obs/qa_state.py`:

```python
@dataclasses.dataclass
class RunState:
    run_id: str
    project: str
    pipeline: str
    created_at: str
    combos: list[Combo]
    # Package of a package-lane run (``package.yaml`` qa: block); "" for the
    # project's own block.  Defaulted so state files written before the
    # field existed still load.
    package: str = ""
```

In `load_state`, add `package=data.get("package", ""),` to the `RunState(...)` constructor call.

In `write_report_json`, add `"package": state.package,` after `"project": state.project,` at the top level, and `"package": state.package,` as the first key of every combo row dict.

- [ ] **Step 4: Rewrite `cmd_qa_run` and adjust retry/list**

In `percona_obs/cmd_qa.py`, replace `cmd_qa_run` from its start through the `if not active:` check with:

```python
def cmd_qa_run(args: argparse.Namespace) -> None:
    env_vars = _qa_env_vars(args)
    lanes = _load_qa_lanes(args.project, env_vars)
    if not lanes:
        raise SystemExit(
            f"error: {args.project} has no qa: block in its project.yaml "
            "or in any package.yaml"
        )

    package = getattr(args, "package", None)
    if package:
        lanes = [lane for lane in lanes if lane.package == package]
        if not lanes:
            have = sorted(
                lane.package
                for lane in _load_qa_lanes(args.project, env_vars)
                if lane.package
            )
            raise SystemExit(
                f"error: {args.project}: no package with a qa: block named "
                f"{package!r}; packages: {', '.join(have) or '(none)'}"
            )

    name = getattr(args, "name", None)
    if name:
        lanes = [
            Lane(lane.package, [e for e in lane.entries if e.get("name") == name])
            for lane in lanes
        ]
        lanes = [lane for lane in lanes if lane.entries]
        if not lanes:
            raise SystemExit(f"error: {args.project}: no qa entry with name {name!r}")

    if args.pipeline:
        lanes = [
            Lane(
                lane.package,
                [e for e in lane.entries if e["pipeline"] == args.pipeline],
            )
            for lane in lanes
        ]
        lanes = [lane for lane in lanes if lane.entries]
        if not lanes:
            suffix = f" (after --name {name})" if name else ""
            raise SystemExit(
                f"error: {args.project}: no qa entry with pipeline "
                f"{args.pipeline!r}{suffix}"
            )

    filters = _parse_filter(args.filter or [])
    overrides = _parse_param_overrides(args.param or [])

    # Pre-expand all entries so we can detect the no-match case before triggering.
    active: list[tuple[str, str, list[tuple[str, dict[str, str]]]]] = []
    for lane in lanes:
        for entry in lane.entries:
            pipeline = entry["pipeline"]
            combos = _expand_matrix(entry)
            combos = _apply_filters(combos, filters)
            combos = _apply_param_overrides(combos, overrides)
            if combos:
                active.append((lane.package or "", pipeline, combos))

    if not active:
        raise SystemExit("error: no matrix combinations match the given --filter")
```

Then replace the dry-run block and the trigger loop:

```python
    if args.dry_run:
        for lane_package, pipeline, combos in active:
            print(_col(_BOLD, f"DRY RUN: would trigger pipeline {pipeline!r}"))
            print(f"  project: {args.project}")
            if lane_package:
                print(f"  package: {lane_package}")
            print(f"  combos:  {len(combos)}")
            for label, params in combos:
                print()
                print(_col(_CYAN, f"• {label or '(no matrix)'}"))
                _print_params(params)
            print()
        return

    cfg = load_jenkins_config(args.profile)

    any_failed = False
    for lane_package, pipeline, combos in active:
        state = RunState(
            run_id=new_run_id(),
            project=args.project,
            pipeline=pipeline,
            created_at=_utcnow_iso(),
            combos=[],
            package=lane_package,
        )
        target = _run_target(state)
        print(
            _col(
                _BOLD,
                f"qa run {target}  pipeline: {pipeline}  (run-id: {state.run_id})",
            )
        )
        queue_urls = _trigger_combos(
            cfg, pipeline, combos, state, record_new_combo=True
        )
        save_state(state)

        if args.wait and queue_urls:
            _wait_and_record(cfg, state, queue_urls)

        if args.report_json:
            write_report_json(state, Path(args.report_json))

        if args.wait and _summarize(state):
            any_failed = True

    if args.wait and any_failed:
        sys.exit(1)
```

Add this helper in the "Pretty-printers" section:

```python
def _run_target(state: RunState) -> str:
    """``<project>`` or ``<project>/<package>`` for headings and `qa list` rows."""
    return f"{state.project}/{state.package}" if state.package else state.project
```

In `cmd_qa_retry`, change the heading f-string `f"qa retry {state.project}  "` to `f"qa retry {_run_target(state)}  "`.

In `cmd_qa_list`, change `f"{state.project}  {state.pipeline}  "` to `f"{_run_target(state)}  {state.pipeline}  "`.

- [ ] **Step 5: Add `--package` to the CLI**

In `percona_obs/cli.py`:

```python
    qa_parser = subparsers.add_parser(
        "qa",
        help="Trigger Jenkins QA pipelines declared in project.yaml / package.yaml.",
    )
```

```python
    _qa_project_help = (
        "Project name (colon notation, e.g. ppg:18:containers:ubi9). "
        "QA lanes come from the project's project.yaml qa: block and from the "
        "qa: block of each direct package's package.yaml."
    )
```

After the `--name` argument of `qa_run_parser`, add:

```python
    qa_run_parser.add_argument(
        "--package",
        metavar="PKG",
        default=None,
        help="Restrict execution to the qa: block of this package's "
        "package.yaml. Without it, the project's own block and every "
        "package block are triggered. Combinable with --name/--pipeline.",
    )
```

- [ ] **Step 6: Run tests, help, formatter and type checker**

Run: `venv/bin/python -m pytest tests/test_qa_package_lanes.py tests/test_qa_entry_name.py -q`
Expected: all pass.

Run: `venv/bin/python -m percona_obs qa run --help | grep -- --package`
Expected: one line mentioning `--package PKG`.

Run: `venv/bin/black percona_obs/ tests/ && venv/bin/pyright`
Expected: clean, `0 errors`.

- [ ] **Step 7: Commit**

```bash
git add percona_obs/cmd_qa.py percona_obs/qa_state.py percona_obs/cli.py tests/test_qa_package_lanes.py
git commit -s -m "qa run: --package lane selection, package in run state and reports"
```

---

### Task 4: CI discovery script: `package_filter` and OBS presence filter

**Goal:** `list_qa_matrix.py` normalises `package_filter`, and when `QA_PACKAGES_PRESENT_ONLY=true` drops package lanes whose package is not in the OBS subproject.

**Files:**
- Modify: `.github/scripts/list_qa_matrix.py`
- Modify: `tests/test_list_qa_matrix.py`

**Acceptance Criteria:**
- [ ] `normalize_entry({"package": "pkg"})["package_filter"] == "--package pkg"`; `normalize_entry({})["package_filter"] == ""`; an existing `package_filter` passes through.
- [ ] `drop_absent_packages(matrix, {"pkg"})` keeps project lanes (`package == ""`) and `pkg` lanes, drops others, and returns the sorted list of dropped package names.
- [ ] `main()` with `QA_PACKAGES_PRESENT_ONLY=true` calls `fetch_present_packages` once per subproject and filters; without it no OBS package listing happens.

**Verify:** `venv/bin/python -m pytest tests/test_list_qa_matrix.py -q` → all pass; black + pyright clean (`tests/` is black-checked in CI).

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_list_qa_matrix.py`:

```python
def test_normalize_entry_package_filter():
    m = _load()
    assert m.normalize_entry({"package": "pkg"})["package_filter"] == "--package pkg"
    assert m.normalize_entry({"package": ""})["package_filter"] == ""
    assert m.normalize_entry({})["package_filter"] == ""
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
        obs_api, "_fetch_obs_subproject_names", lambda a, p: {"isv:percona:PR:pr-1:ppg:18"}
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_list_qa_matrix.py -q`
Expected: FAIL (`AttributeError: ... has no attribute 'drop_absent_packages'`, `KeyError: 'package_filter'`).

- [ ] **Step 3: Implement**

In `.github/scripts/list_qa_matrix.py`:

Extend the module docstring "Optional:" list with:

```
  QA_TYPES                  comma-separated subset of packages,containers; only
                            subprojects of those kinds are scanned
  QA_PACKAGES_PRESENT_ONLY  "true": drop package lanes (combos with a non-empty
                            ``package``) whose package is not in the OBS
                            subproject.  Set by PR runs, where the PR project
                            holds only promoted packages; unset for the nightly.
```

Replace `normalize_entry` with:

```python
def normalize_entry(entry: dict) -> dict:
    """Ensure a combo carries ready-to-use ``name_filter``/``package_filter`` strings.

    Mirrors the ``axis_filters`` convention: the workflow interpolates the
    values straight into the ``qa run`` command line, so each is either
    ``--name <name>`` / ``--package <pkg>`` or the empty string.
    """
    if not entry.get("name_filter"):
        name = entry.get("name") or ""
        entry["name_filter"] = f"--name {name}" if name else ""
    if not entry.get("package_filter"):
        package = entry.get("package") or ""
        entry["package_filter"] = f"--package {package}" if package else ""
    return entry


def fetch_present_packages(apiurl: str, full_project: str) -> set[str]:
    """Package names currently in an OBS project (empty on 404 / error)."""
    from percona_obs.obs_api import _fetch_obs_package_names

    return _fetch_obs_package_names(apiurl, full_project)


def drop_absent_packages(
    matrix: list[dict], present: set[str]
) -> tuple[list[dict], list[str]]:
    """Keep project lanes and the package lanes whose package is in ``present``.

    Returns ``(kept, dropped_package_names)``; project lanes (``package`` empty)
    are never dropped.
    """
    kept: list[dict] = []
    dropped: set[str] = set()
    for combo in matrix:
        package = combo.get("package") or ""
        if package and package not in present:
            dropped.add(package)
            continue
        kept.append(combo)
    return kept, sorted(dropped)
```

In `main()`, read the flag next to `qa_types`:

```python
    present_only = os.environ.get("QA_PACKAGES_PRESENT_ONLY", "") == "true"
```

and replace the tail of the loop body (`if entries:` block) with:

```python
        if entries and present_only and any(e.get("package") for e in entries):
            present = fetch_present_packages(apiurl, full_name)
            entries, dropped = drop_absent_packages(entries, present)
            if dropped:
                print(
                    f"  {project}: package lane(s) skipped, not in {full_name}: "
                    + ", ".join(dropped),
                    file=sys.stderr,
                )
        if entries:
            print(f"  {project}: {len(entries)} combo(s)", file=sys.stderr)
            matrix.extend(normalize_entry(e) for e in entries)
```

- [ ] **Step 4: Run tests, formatter and type checker**

Run: `venv/bin/python -m pytest tests/test_list_qa_matrix.py -q`
Expected: all pass.

Run: `venv/bin/black percona_obs/ tests/ .github/scripts/ && venv/bin/pyright`
Expected: clean, `0 errors`.

- [ ] **Step 5: Commit**

```bash
git add .github/scripts/list_qa_matrix.py tests/test_list_qa_matrix.py
git commit -s -m "ci: list_qa_matrix emits package_filter and drops package lanes absent from OBS"
```

---

### Task 5: Manual-run scripts: `QA_PACKAGE` and presence filter

**Goal:** `filter_qa_matrix.py` selects by package and applies the OBS presence drop for PR targets; `resolve_qa_instance.py` validates the new `package` input.

**Files:**
- Modify: `.github/scripts/filter_qa_matrix.py`
- Modify: `.github/scripts/resolve_qa_instance.py`
- Modify: `tests/test_manual_qa_scripts.py`

**Acceptance Criteria:**
- [ ] `filter_matrix(matrix, "", "", package="pkg")` keeps only `pkg` combos; an unknown package errors listing `(project)` and the package names present.
- [ ] `filter_matrix(..., package="")` behaves exactly as before.
- [ ] `main()` with `QA_PACKAGES_PRESENT_ONLY=true`, `OBS_APIURL`, `OBS_PROJECT` drops absent package lanes before narrowing; if `QA_PACKAGE` names a dropped package the error says it is not present in the OBS project.
- [ ] `validate_package` accepts `""`, `pg_tde`, `percona-postgresql18`, `python3-psycopg2`; rejects `a b`, `a;b`, `$(x)`, `a/b`, `-x`.

**Verify:** `venv/bin/python -m pytest tests/test_manual_qa_scripts.py -q` → all pass; black + pyright clean.

**Steps:**

- [ ] **Step 1: Write the failing tests**

In `tests/test_manual_qa_scripts.py`, extend `_combo` to accept a package and add tests. Replace the existing `_combo` helper with:

```python
def _combo(name: str, package: str = "", **params: str) -> dict:
    return {
        "project": "ppg:staging:18:containers",
        "package": package,
        "pipeline": "docker",
        "name": name,
        "label": ",".join(f"{k}={v}" for k, v in params.items()) or "default",
        "axis_filters": " ".join(f"--filter {k}={v}" for k, v in params.items()),
        "name_filter": f"--name {name}" if name else "",
        "package_filter": f"--package {package}" if package else "",
        "status_context": f"OBS QA / x / {package or name}",
        "params": params,
    }
```

Append:

```python
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
    m = _presence_env(monkeypatch, tmp_path, {"pg_tde"}, QA_NAME="", QA_FILTER="", QA_PACKAGE="")
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(_WITH_PKG)))
    m.main()
    out = json.loads(capsys.readouterr().out)
    assert [c["package"] for c in out] == ["", "pg_tde"]


def test_main_presence_requested_absent_package_errors(monkeypatch, tmp_path):
    m = _presence_env(
        monkeypatch, tmp_path, {"pg_tde"}, QA_NAME="", QA_FILTER="", QA_PACKAGE="pgbackrest"
    )
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(_WITH_PKG)))
    with pytest.raises(SystemExit) as exc:
        m.main()
    msg = str(exc.value)
    assert "pgbackrest" in msg and "not present in isv:percona:PR:pr-7:ppg:staging:18" in msg


# --- package input validation ----------------------------------------------------


@pytest.mark.parametrize("pkg", ["", "pg_tde", "percona-postgresql18", "python3-psycopg2"])
def test_valid_package_names(pkg):
    m = _load("resolve_qa_instance")
    m.validate_package(pkg)


@pytest.mark.parametrize("pkg", ["a b", "a;b", "$(x)", "a/b", "-x"])
def test_invalid_package_names(pkg):
    m = _load("resolve_qa_instance")
    with pytest.raises(SystemExit):
        m.validate_package(pkg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_manual_qa_scripts.py -q`
Expected: FAIL (`TypeError: filter_matrix() got an unexpected keyword argument 'package'`, missing `validate_package`).

- [ ] **Step 3: Implement `filter_qa_matrix.py`**

Extend the docstring with:

```
  QA_PACKAGE  keep only combos of the package.yaml ``qa:`` block of this
              package (combos whose ``package`` equals it)

  QA_PACKAGES_PRESENT_ONLY  "true" (manual runs against a PR project): drop
              package lanes whose package is not in ``$OBS_PROJECT`` on
              ``$OBS_APIURL`` before narrowing, same rule as list_qa_matrix.py.
```

Add after the imports (mirrors `resolve_qa_instance.py`):

```python
# Scripts in this directory share the presence helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from list_qa_matrix import drop_absent_packages, fetch_present_packages  # noqa: E402
```

with `from pathlib import Path` added to the imports.

Change the signature and start of `filter_matrix`:

```python
def filter_matrix(
    matrix: list[dict[str, Any]], name: str, filter_text: str, package: str = ""
) -> list[dict[str, Any]]:
    if not matrix:
        raise SystemExit("error: no QA combos found: the project has no qa: block")

    package = package.strip()
    if package:
        packages = sorted({str(c.get("package") or "") for c in matrix})
        matrix = [c for c in matrix if (c.get("package") or "") == package]
        if not matrix:
            shown = ", ".join(p or "(project)" for p in packages)
            raise SystemExit(
                f"error: no qa: block for package {package!r}; lanes: {shown}"
            )

    name = name.strip()
    ...  # existing name / axis code unchanged
```

Add and use an osc configuration helper, then rewrite `main`:

```python
def _configure_osc(apiurl: str) -> None:
    import osc.conf

    osc.conf.get_config(override_apiurl=apiurl)


def main() -> None:
    try:
        matrix = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: matrix on stdin is not valid JSON: {exc}")
    if not isinstance(matrix, list):
        raise SystemExit("error: matrix on stdin must be a JSON list")

    package = os.environ.get("QA_PACKAGE", "").strip()
    if os.environ.get("QA_PACKAGES_PRESENT_ONLY", "") == "true" and any(
        c.get("package") for c in matrix
    ):
        apiurl = os.environ["OBS_APIURL"]
        obs_project = os.environ["OBS_PROJECT"]
        _configure_osc(apiurl)
        matrix, dropped = drop_absent_packages(
            matrix, fetch_present_packages(apiurl, obs_project)
        )
        if dropped:
            print(
                f"package lane(s) skipped, not present in {obs_project}: "
                + ", ".join(dropped),
                file=sys.stderr,
            )
        if package and package in dropped:
            raise SystemExit(
                f"error: package {package!r} declares a qa: block but is not "
                f"present in {obs_project}; it was not promoted into this PR project"
            )

    kept = filter_matrix(
        matrix,
        os.environ.get("QA_NAME", ""),
        os.environ.get("QA_FILTER", ""),
        package=package,
    )
    for combo in kept:
        print(f"  {combo.get('status_context')}", file=sys.stderr)
    print(json.dumps(kept))
```

- [ ] **Step 4: Implement `validate_package` in `resolve_qa_instance.py`**

Add after `_PR_RE`:

```python
_PACKAGE_RE = re.compile(r"^(|[A-Za-z0-9][A-Za-z0-9_.+-]*)$")
```

Add after `validate_pr_number`:

```python
def validate_package(package: str) -> None:
    if not _PACKAGE_RE.match(package):
        raise SystemExit(
            f"error: invalid package name {package!r}; expected a package "
            "directory name such as pg_tde, or empty"
        )
```

In `main()`, after `validate_pr_number(pr_number)` add:

```python
    validate_package(os.environ.get("QA_PACKAGE", ""))
```

Mention `QA_PACKAGE` in the docstring's "Also validates" sentence and "Optional" list.

- [ ] **Step 5: Run tests, formatter and type checker**

Run: `venv/bin/python -m pytest tests/test_manual_qa_scripts.py tests/test_list_qa_matrix.py -q`
Expected: all pass.

Run: `venv/bin/black percona_obs/ tests/ .github/scripts/ && venv/bin/pyright`
Expected: clean, `0 errors`.

- [ ] **Step 6: Commit**

```bash
git add .github/scripts/filter_qa_matrix.py .github/scripts/resolve_qa_instance.py tests/test_manual_qa_scripts.py
git commit -s -m "ci: manual QA run selects by package and honours OBS presence for PR targets"
```

---

### Task 6: Workflow wiring

**Goal:** The three QA workflows pass `package_filter` to `qa run`, the PR check and PR-targeted manual runs enable the presence filter, and `obs-qa-run` exposes a `package` input.

**Files:**
- Modify: `.github/workflows/obs-pr-check.yml:694-705, 870-879`
- Modify: `.github/workflows/obs-nightly-qa.yml:183-192`
- Modify: `.github/workflows/obs-qa-run.yml` (inputs, resolve env, detect env + step, qa step)

**Acceptance Criteria:**
- [ ] All three workflow files parse as YAML.
- [ ] `obs-pr-check.yml`: the "Discover QA matrix from OBS PR subprojects" step has `QA_PACKAGES_PRESENT_ONLY: "true"` in `env`; the `qa run` command ends with `${{ matrix.name_filter }} \`, `${{ matrix.package_filter }} \`, `${{ matrix.axis_filters }}`.
- [ ] `obs-nightly-qa.yml`: the `qa run` command passes `${{ matrix.name_filter }}` and `${{ matrix.package_filter }}` (the nightly was missing `name_filter`; multi-entry named blocks ran every entry under one `--pipeline`).
- [ ] `obs-qa-run.yml`: `inputs.package` exists; `resolve` env has `QA_PACKAGE: ${{ inputs.package }}`; `detect`'s narrowing step has `QA_PACKAGE`, `QA_PACKAGES_PRESENT_ONLY: ${{ inputs.pr_number != '' && 'true' || '' }}`, `OBS_APIURL: ${{ needs.resolve.outputs.instance_apiurl }}`, `OBS_PROJECT: ${{ needs.resolve.outputs.rootprj }}:${{ inputs.project }}`; the `qa run` step passes `${{ matrix.package_filter }}`; the concurrency group is unchanged.

**Verify:** `for f in .github/workflows/obs-pr-check.yml .github/workflows/obs-nightly-qa.yml .github/workflows/obs-qa-run.yml; do venv/bin/python -c "import sys,yaml; yaml.safe_load(open(sys.argv[1]))" "$f" && echo "ok $f"; done` → three `ok` lines; `grep -c 'package_filter' .github/workflows/obs-pr-check.yml .github/workflows/obs-nightly-qa.yml .github/workflows/obs-qa-run.yml` → `1` for each.

**Steps:**

- [ ] **Step 1: `obs-pr-check.yml`**

In the step `Discover QA matrix from OBS PR subprojects`, add to `env`:

```yaml
          # PR projects hold only promoted packages: a package.yaml qa: lane
          # runs only when its package is present there.
          QA_PACKAGES_PRESENT_ONLY: "true"
```

In the `qa` job's `Run qa pipeline` step, replace the command with:

```yaml
          venv/bin/python -m percona_obs -P ci qa run "${{ matrix.project }}" \
            --pipeline "${{ matrix.pipeline }}" \
            --wait \
            --report-json /tmp/qa-report.json \
            ${{ matrix.name_filter }} \
            ${{ matrix.package_filter }} \
            ${{ matrix.axis_filters }}
```

Update the header comment block near line 40 (the paragraph starting "`detect-qa-matrix` is matrixed the same way") by appending one sentence: `Package-level qa: lanes (package.yaml) are kept only when the package is present in the PR project (QA_PACKAGES_PRESENT_ONLY).`

- [ ] **Step 2: `obs-nightly-qa.yml`**

Replace the `Run qa pipeline` command with:

```yaml
          venv/bin/python -m percona_obs -P ci qa run "${{ matrix.project }}" \
            --pipeline "${{ matrix.pipeline }}" \
            --wait \
            --report-json /tmp/qa-report.json \
            ${{ matrix.name_filter }} \
            ${{ matrix.package_filter }} \
            ${{ matrix.axis_filters }}
```

Add above that step:

```yaml
      # `name_filter` / `package_filter` / `axis_filters` are tool-generated
      # flag strings from `qa show --json` (normalised by list_qa_matrix.py),
      # same contract as obs-pr-check.yml.  No presence filter here: on the
      # production root every package exists, so every package lane runs.
```

- [ ] **Step 3: `obs-qa-run.yml`**

Add an input after `name`:

```yaml
      package:
        description: 'Package whose package.yaml qa: block to run (e.g. pg_tde); empty = project block plus every package block'
        required: false
        default: ''
        type: string
```

In `resolve`'s step env add `QA_PACKAGE: ${{ inputs.package }}`.

In `detect`'s `Expand and narrow the QA matrix` step env add:

```yaml
          QA_PACKAGE: ${{ inputs.package }}
          # Against a PR project only promoted packages exist; skip the
          # package lanes of absent packages, as obs-pr-check does.
          QA_PACKAGES_PRESENT_ONLY: ${{ inputs.pr_number != '' && 'true' || '' }}
          OBS_APIURL: ${{ needs.resolve.outputs.instance_apiurl }}
          OBS_PROJECT: ${{ needs.resolve.outputs.rootprj }}:${{ inputs.project }}
```

In the `qa` job's `Run qa pipeline` step, add `${{ matrix.package_filter }} \` between `name_filter` and `axis_filters`, and extend the comment above it to mention `package_filter`.

Update the header comment: "(and optionally a PR number, a `qa:` entry name, a package and an axis filter)" and add: "QA lanes come from the project's project.yaml and from each direct package's package.yaml."

- [ ] **Step 4: Verify**

Run:

```bash
for f in .github/workflows/obs-pr-check.yml .github/workflows/obs-nightly-qa.yml .github/workflows/obs-qa-run.yml; do
  venv/bin/python -c "import sys,yaml; yaml.safe_load(open(sys.argv[1]))" "$f" && echo "ok $f"
done
grep -c 'package_filter' .github/workflows/obs-pr-check.yml .github/workflows/obs-nightly-qa.yml .github/workflows/obs-qa-run.yml
```

Expected: three `ok` lines, then `1` per file.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/obs-pr-check.yml .github/workflows/obs-nightly-qa.yml .github/workflows/obs-qa-run.yml
git commit -s -m "ci: pass package_filter to qa run; presence filter on PR targets; package input on obs-qa-run"
```

---

### Task 7: Documentation

**Goal:** Document package-level `qa:` blocks, `--package`, the new JSON fields, the status-context shapes and the CI knobs.

**Files:**
- Modify: `docs/PERCONA_OBS_TOOL.md:628-700`
- Modify: `.github/copilot-instructions.md:186-195, 1051-1119`

**Acceptance Criteria:**
- [ ] `docs/PERCONA_OBS_TOOL.md` "Triggering Jenkins QA pipelines" says lanes come from project.yaml and package.yaml, shows a package.yaml example, has the four-row status-context table, documents `--package` in the `qa run` row and `package`/`package_filter` in the `qa show` row, and documents `QA_PACKAGES_PRESENT_ONLY`.
- [ ] `.github/copilot-instructions.md` package.yaml section lists `qa:`; Workflow 2 and Workflow 5 descriptions mention package lanes, `QA_PACKAGES_PRESENT_ONLY`, `package_filter` and the `package` input.
- [ ] `grep -c 'package_filter' docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md` ≥ 1 each.

**Verify:** `grep -n 'QA_PACKAGES_PRESENT_ONLY' docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md` → at least one hit per file.

**Steps:**

- [ ] **Step 1: `docs/PERCONA_OBS_TOOL.md`**

Rewrite the opening paragraph of "Triggering Jenkins QA pipelines":

```markdown
`qa run` reads a project's QA *lanes* — the optional `qa:` block of its
`project.yaml` plus the optional `qa:` block of each direct package's
`package.yaml` — expands every matrix into one Jenkins job per combination,
triggers each via Jenkins' `buildWithParameters` REST endpoint, and (with
`--wait`) polls every triggered build until it reaches a terminal state.
```

After the `qa:` block schema code block add:

```markdown
The same schema applies to a package's `package.yaml`. Package blocks are
discovered on disk from the project's direct package directories (symlinks into
`_shared/` are followed and `%!{...}` macros resolve from the link's location,
so one block under `_shared/<pkg>/package.yaml` renders per major), without
descending into subprojects. The package's `obs/_link`, if any, is irrelevant.

```yaml
# root/ppg/staging/_shared/pg_tde/package.yaml
qa:
  pipeline: pg-tde-parallel
  parameters:
    OBS_PROJECT: ${OBS_ROOTPRJ}:ppg:staging:%!{PG_MAJOR_VERSION}
    VERSION: ppg-%!{PG_VERSION}
    PLATFORMS: [rocky-9, debian-13]
  matrix: [PLATFORMS]
```

The segment-uniqueness rule below is checked per block: the project block and
each package block are separate namespaces.

#### Status contexts

| lane | entries | `status_context` |
|---|---|---|
| project | one | `OBS QA / <project>[ / <combo>]` |
| project | several | `OBS QA / <project> / <segment>[ / <combo>]` |
| package | one | `OBS QA / <project> / <package>[ / <combo>]` |
| package | several | `OBS QA / <project> / <package> / <segment>[ / <combo>]` |

`<segment>` is the entry `name` when set, else the pipeline; `<combo>` is the
matrix label and is absent for entries without `matrix:`.

#### When package lanes run

* `qa run <project>` with no `--package` triggers the project block and every
  package block. This is what the nightly does.
* On PR checks (`obs-pr-check.yml`) and on `obs-qa-run` dispatches with a PR
  number, `.github/scripts/list_qa_matrix.py` / `filter_qa_matrix.py` run with
  `QA_PACKAGES_PRESENT_ONLY=true` and drop the package lanes whose package is
  not in the PR's OBS subproject (which holds only promoted packages, including
  dep-cascade rebuilds). Project lanes are never dropped. The tool itself never
  talks to OBS for QA.
```

Update the subcommand table rows:

- `qa show`: the `--json` field list becomes `project`, `package` (empty for project lanes), `pipeline`, `name`, `label`, `axis_filters`, `name_filter`, `package_filter`, `status_context`, `params`; "Empty `[]` when the project has no lane."
- `qa run`: add "`--package PKG` runs only that package's `package.yaml` block (combinable with `--name`/`--pipeline`); without it every lane runs."
- `qa list`: "(run-id, project or project/package, pipeline, summary)".

In the `obs-qa-run` paragraph add "an optional `package`" to the list of inputs.

- [ ] **Step 2: `.github/copilot-instructions.md`**

Package Configuration section: extend the example and text:

```yaml
title: My Package Title
description: "Human-readable description."
build:            # optional per-repository build flags (see Project Configuration)
  Debian_13: false
qa:               # optional Jenkins QA lane(s); same schema as project.yaml qa:
  pipeline: my-pkg-pipeline
  parameters:
    VERSION: "%!{PG_VERSION}"
```

Add after "These fields map directly...": "`qa:` declares package-level QA lanes discovered by `percona-obs qa show/run <project>` next to the project's own block; see `docs/PERCONA_OBS_TOOL.md` § Triggering Jenkins QA pipelines."

Workflow 2: in the sentence about `detect-qa-matrix` (around line 1053-1069 there is no explicit QA paragraph; add one after item 5):

```markdown
6. QA (`qa-packages` / `qa-containers` label): `detect-qa-matrix` calls `qa show --json` per OBS subproject with `QA_PACKAGES_PRESENT_ONLY=true`, so package-level `qa:` lanes (from `package.yaml`) are kept only when the package is present in the PR project; `qa` fans out one job per combo passing the tool-generated `name_filter`, `package_filter` and `axis_filters` flags.
```

Workflow 5: in "Inputs", add "`package` (optional: run only that package's `package.yaml` `qa:` block)"; in "What it does", mention `QA_PACKAGE`, that `QA_PACKAGES_PRESENT_ONLY` is set when `pr_number` is given, and that `qa` passes `package_filter`.

- [ ] **Step 3: Verify and commit**

Run: `grep -n 'QA_PACKAGES_PRESENT_ONLY' docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md`
Expected: at least one line per file.

```bash
git add docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md
git commit -s -m "docs: package-level qa: blocks, --package, status contexts, CI presence filter"
```

---

### Task 8: Full verification pass

**Goal:** Confirm the whole suite, formatter and type checker pass on the finished branch, and that project-lane output is unchanged on the real tree.

**Files:** none modified.

**Acceptance Criteria:**
- [ ] `venv/bin/python -m pytest tests -q` passes.
- [ ] `venv/bin/black --check percona_obs/ tests/ .github/scripts/` and `venv/bin/pyright` pass.
- [ ] `qa show --json` for `ppg:staging:18` and `ppg:staging:containers` with `-R isv:percona` produces the same `status_context` list as on `percona/main` (no package lanes exist in the tree yet, so output must match apart from the two new empty fields).

**Verify:** the commands in the steps below.

**Steps:**

- [ ] **Step 1: Suite, formatter, type checker**

```bash
venv/bin/python -m pytest tests -q
venv/bin/black --check percona_obs/ tests/ .github/scripts/
venv/bin/pyright
```

Expected: pytest all pass; black "unchanged"; pyright `0 errors`.

- [ ] **Step 2: Compare real-tree output against main**

Run the same `qa show --json` here and in the primary checkout (`/home/rdias/Work/percona-obs-packaging`, on `main`, read-only) and diff the context lists:

```bash
CTX='import json,sys; [print(e["status_context"]) for e in json.load(sys.stdin)]'
for p in ppg:staging:18 ppg:staging:containers; do
  venv/bin/python -m percona_obs -R isv:percona qa show "$p" --json \
    | venv/bin/python -c "$CTX" > "/tmp/new-$p.txt"
  (cd /home/rdias/Work/percona-obs-packaging && venv/bin/python -m percona_obs -R isv:percona qa show "$p" --json \
    | venv/bin/python -c "$CTX") > "/tmp/old-$p.txt"
  diff "/tmp/old-$p.txt" "/tmp/new-$p.txt" && echo "same: $p"
done
```

Expected: `same: ppg:staging:18` and `same: ppg:staging:containers`. (Reading the primary checkout is fine; nothing is modified there.)

- [ ] **Step 3: Report**

No commit. Report the results to the user, then stop: pushing the branch and opening the PR require the user's go-ahead (see Global Constraints).
