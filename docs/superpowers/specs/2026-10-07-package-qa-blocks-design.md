# Package-level `qa:` blocks in `package.yaml`

**Date:** 2026-10-07
**Status:** approved design, awaiting implementation plan
**Amended after final review:** `--project-only` selector (§2, §3), `qa.name` charset and cross-block collision rule (§1).

## Goal

Let a package declare its own Jenkins QA lanes in `package.yaml`, next to the
project-level `qa:` block that `project.yaml` already supports. A package lane
runs on PR checks only when that package is present in the PR's OBS
subproject, and always on nightly and manual runs.

## Non-goals

- Changing the schema or semantics of the project-level `qa:` block.
- Having the tool talk to OBS during `qa show` / `qa run`. Both stay
  filesystem-only; OBS presence filtering is a CI concern.
- Recursive discovery: `qa show ppg:staging:18` does not report packages of
  `ppg:staging:18:containers`. CI already calls `qa show` once per OBS
  subproject.

## 1. `package.yaml` `qa:` block

(Amended: `name` must match `[A-Za-z0-9][A-Za-z0-9_.+-]*` since CI interpolates
it into a shell command. A package whose name equals a check segment of a
multi-entry project block is rejected by the loader, as both would render the
same status context.)

Same schema as the project block: a mapping, or a list of entries, each with
optional `name`, required `pipeline`, required non-empty `parameters`, optional
`matrix` (list of parameter names whose list values expand combinatorially).

```yaml
# root/ppg/staging/_shared/pg_tde/package.yaml
qa:
  pipeline: pg-tde-parallel
  parameters:
    OBS_PROJECT: ${OBS_ROOTPRJ}:ppg:staging:%!{PG_MAJOR_VERSION}
    VERSION: ppg-%!{PG_VERSION}
    PLATFORMS:
      - rocky-9
      - debian-13
  matrix:
    - PLATFORMS
```

Rendering:

- `%!{...}` macros resolve through `load_package_yaml`, i.e. from the
  directory hierarchy of the path the package is reached by. A block under
  `_shared/<pkg>/package.yaml` therefore renders per major when reached
  through each major's symlink.
- `${VAR}` tokens substitute from the active profile `env:` plus the
  auto-injected `OBS_ROOTPRJ`, `OBS_CONTAINER_REGISTRY` and
  `OBS_CONTAINER_REGISTRY_ROOTPRJ`, exactly as for `project.yaml`.

Validation reuses `_validate_qa`. Error prefixes become `<project>/<package>`
for package entries. The check-run segment uniqueness rule (two entries that
would render the same `status_context` segment are rejected) runs
independently per block: project block and each package block are separate
namespaces. Two packages may each have an unnamed entry on the same pipeline.

A package's `obs/_link` file is irrelevant to QA discovery.

## 2. Discovery and `qa show`

### Loader

`_load_qa_block(project, env_vars)` is replaced by
`_load_qa_lanes(project, env_vars) -> list[Lane]` where

```python
@dataclass
class Lane:
    package: str | None        # None for the project's own block
    entries: list[dict]        # validated entries, always a list
```

Steps:

1. Resolve the project path. Load `project.yaml`; if it has `qa:`, normalise
   and validate it, append `Lane(None, entries)`.
2. For each `(obs_project, package_path)` from
   `find_packages(project_path, project, recursive=False)`: if
   `package_path / "package.yaml"` exists and the loaded mapping has `qa:`,
   normalise and validate, append `Lane(package_path.name, entries)`.
   `find_packages` already follows symlinks and skips `_shared/` itself.
3. Return the list. An empty list means the project has no QA at all;
   `qa show --json` prints `[]`, `qa show` prints nothing, `qa run` errors as
   today ("has no qa: block").

### Human output

Headings become `<project>  →  pipeline: <p>` for project lanes and
`<project> / <package>  →  pipeline: <p>` for package lanes, both with the
existing `(name: …)` suffix when set. Everything below the heading is
unchanged.

### `--json` output

Each combo dict gains:

| field | value |
|---|---|
| `package` | package directory name, or `""` for project lanes |
| `package_filter` | `--package <pkg>` for package lanes, `--project-only` for project lanes (amended: was `""`, which let a project lane's `qa run` also trigger package lanes on the same pipeline) |

`status_context`:

```
project lane, single entry:        OBS QA / <project>[ / <combo>]
project lane, multi entry:         OBS QA / <project> / <segment>[ / <combo>]
package lane, single entry:        OBS QA / <project> / <package>[ / <combo>]
package lane, multi entry:         OBS QA / <project> / <package> / <segment>[ / <combo>]
```

The multi-entry rule is evaluated per block (per `Lane`). Project-lane
contexts are byte-for-byte identical to today's.

## 3. `qa run` selection and run state

New flags `qa run <project> --package PKG` and `--project-only` (project's own
block only; mutually exclusive with `--package`, error if the project has no
block). Selection order:

0. `--project-only`: keep only the project lane.
1. `--package`: keep only lanes with `package == PKG`. No match → error listing
   the packages of the project that declare `qa:`.
2. `--name`: keep entries with that name, across all surviving lanes.
3. `--pipeline`: keep entries with that pipeline, across all surviving lanes.

Without `--package`/`--project-only`, every lane (project and all packages) is eligible. This
is the nightly behaviour.

Run state: one `RunState` per lane and pipeline (today: one per pipeline).
`RunState` gains `package: str = ""`. `qa list` shows `project/package` in its
project column when set. `qa status` / `qa retry` print it in their headings.
`write_report_json` adds `package` to each combo row. Dry-run output prints a
`package:` line when set. The state-file `project` field is unchanged.

Jenkins parameters are not affected by any of this.

## 4. CI and workflows

### `.github/scripts/list_qa_matrix.py`

After collecting `qa show --json` for a subproject, if env
`QA_PACKAGES_PRESENT_ONLY=true`:

- fetch the subproject's OBS package names with
  `percona_obs.obs_api._fetch_obs_package_names(apiurl, full_name)`;
- drop combos whose `package` is non-empty and not in that set;
- log the dropped packages to stderr.

Project lanes (`package == ""`) are never dropped. When the variable is
unset, nothing is filtered. `normalize_entry` also fills `package_filter`
from `package` when absent, as it does for `name_filter`.

| workflow | `QA_PACKAGES_PRESENT_ONLY` |
|---|---|
| `obs-pr-check.yml` detect-qa-matrix | `true` |
| `obs-nightly-qa.yml` detect | unset |
| `obs-qa-run.yml` detect | `true` iff `pr_number` is set |

### `qa` jobs

All three workflows append `${{ matrix.package_filter }}` to the `qa run`
command line, next to `name_filter` and `axis_filters`. Check-run names
already come from `status_context`, so package lanes appear as
`OBS QA / <project> / <package> / …` without further changes. The duplicate
`status_context` dedup in `merge-qa-matrix` applies unchanged.

### `obs-qa-run.yml`

New optional `workflow_dispatch` input `package`. `resolve` validates it with
the same character-class check as `name`. `detect` passes it to
`filter_qa_matrix.py` as `QA_PACKAGE`; a value matching no combo fails the
job listing the packages that exist in the matrix (project lanes are listed
as `(project)`).

### Unaffected

Nightly change check and badge aggregation key on run outcome and project,
not on combo fields. `qa_types` classification is per project, so package
lanes inherit their project's packages/containers kind.

### Documentation

- `docs/PERCONA_OBS_TOOL.md`: `qa:` block schema section (package variant,
  `--package`, new JSON fields, status-context table above).
- `.github/copilot-instructions.md`: package.yaml section gains `qa:`;
  workflow descriptions mention `QA_PACKAGES_PRESENT_ONLY`, `package_filter`
  and the `package` dispatch input.

## 5. Testing

Unit tests under `tests/`:

- `_load_qa_lanes`: project only, package only, both, no QA at all; a
  `_shared` package reached through two major symlinks renders two different
  `%!{PG_MAJOR_VERSION}` values; segment-uniqueness error fires within a
  package block and not across blocks; package block validation error prefix
  is `<project>/<package>`; subproject packages are not discovered.
- `qa show --json`: `package`, `package_filter`, `status_context` for each of
  the four context shapes; project-lane output identical to the pre-change
  fixture.
- `qa run`: `--package` filtering and its no-match error; `--package` combined
  with `--name`; `--report-json` rows carry `package`.
- `list_qa_matrix.py`: presence filter with a stubbed package listing keeps
  project lanes and present packages, drops absent ones, and is a no-op when
  the variable is unset.
- `filter_qa_matrix.py`: `QA_PACKAGE` selection and no-match message.

Manual verification: `percona-obs -P local qa show ppg:staging:18` on a branch
that adds a `qa:` block to one `_shared` package, then an `obs-qa-run`
dispatch of that branch with `package` set, before any package block lands on
`main`.

## Files touched

| file | change |
|---|---|
| `percona_obs/cmd_qa.py` | `Lane`, `_load_qa_lanes`, show/run/list/status/retry output, `--package` selection |
| `percona_obs/qa_state.py` | `RunState.package`, report rows |
| `percona_obs/cli.py` | `--package` on `qa run`, help text |
| `.github/scripts/list_qa_matrix.py` | presence filter, `package_filter` normalisation |
| `.github/scripts/filter_qa_matrix.py` | `QA_PACKAGE` |
| `.github/workflows/obs-pr-check.yml`, `obs-nightly-qa.yml`, `obs-qa-run.yml` | env var, `package_filter`, dispatch input |
| `docs/PERCONA_OBS_TOOL.md`, `.github/copilot-instructions.md` | docs |
| `tests/` | new tests |
