# Multi-instance OBS: profile-declared repository and project slices

Date: 2026-09-23
Status: approved design; implementation plan to follow in
`docs/superpowers/plans/`.
Builds on: `2026-09-23-project-yaml-dedup-design.md` (PR #82, branch
`project-yaml-dedup`), whose resolver (`percona_obs/project_config.py`) is the
single loader every consumer reads `repositories`/`project-config`/
`debuginfo`/`publish`/`build` through.

## Problem

build.opensuse.org (b.o.o) cannot build UBI container images. Percona keeps
building every RPM and DEB package there, but the UBI RPM repositories
(`UBI_8`, `UBI_9`) and everything image-related (`common:containers:ubi8/9`,
`ppg:staging:<V>:containers`, `ppg:staging:<V>:extras:containers`) must move
to a second OBS instance, `obs.pg.labs.percona.com` (labs). The container
images consume RPMs from the UBI repositories of the package projects
(`ppg:staging:<V>/UBI_9`, `ppg:common:deps/UBI_9`, `common:deps:build/UBI_9`),
so labs must rebuild the UBI RPMs itself: package projects exist on both
instances with disjoint repository sets, and a package is present on labs only
if it builds in at least one UBI repository.

Today `percona-obs` talks to exactly one instance per invocation (`-A`/`-R`,
or a `.profile/<name>.yaml`), and the tree under `root/` describes one
complete OBS layout. The only repository-level selection is
`sync push --only-repos`, a label-driven meta filter with special cases
(`ssl*` always kept, `<flavor>-images` label expansion, `:containers:<flavor>`
target filtering) that only the PR workflow uses.

## Goal

One source tree, several OBS instances, each holding a *slice* of it. The
tree stays instance-agnostic; a connection profile says which slice its
instance carries; everything else (which projects exist, which packages are
synced, what is deleted as orphan, what a release contains) is derived.

## Decisions taken during design

- **Selection model 3**: package projects live on both instances with
  disjoint repositories; a package reaches labs only if it builds in a
  surviving repository; b.o.o drops the UBI repositories, the container
  projects and UBI-only packages.
- **One run per instance.** A profile targets one instance and declares its
  slice; CI runs the sync once per instance. No single-run fan-out.
- **Rules live in the profile**, as include/exclude glob lists for repository
  names and for project names. No committed slice catalogue; the tree carries
  no instance information. The operator is responsible for `boo` and `labs`
  being complements; the tool reports slice counts to help.
- **`--only-repos` is removed** and replaced by the profile filter. The PR
  workflow writes PR labels into the PR profile instead of passing a flag.
  Policy that lived in the tool (`ssl*` rescue, `<flavor>-images` expansion)
  moves to the workflow.
- **Out-of-slice projects and packages are orphan-deleted** from an instance
  on a full-tree push, exactly as if they were absent from the tree.
- **Projects with zero repositories are never created** (today only
  `ppg:staging:extras`, package-less).
- **Filter installed once as a process default** in `cli.main()` and used by
  the resolver alias so no consumer can forget it; an explicit argument
  overrides it (tests, release generator).
- **`project release` reads the tree, not live OBS meta**, so the frozen
  release tree stays instance-agnostic and each instance's `sync release`
  slices it.
- **Deferred**: the `registry.opensuse.org/` host hard-coded in `qa:` blocks
  (becomes a profile env var in a follow-up); QA workflow changes.

## Section 1: the filter

### Profile keys

```yaml
# .profile/boo.yaml
apiurl: https://api.opensuse.org
rootprj: isv:percona
exclude-repositories: ["UBI_*", "ubi*", "images"]

# .profile/labs.yaml
apiurl: https://obs.pg.labs.percona.com
rootprj: percona
include-repositories: ["UBI_*", "ubi*", "images"]

# a PR profile on labs for a PR labelled ubi9-images
include-repositories: ["UBI_*", "ubi*", "images", "ubi9", "UBI_9"]
exclude-projects: ["common:containers:ubi8"]
```

Four optional keys, each a list of shell globs (`fnmatch.fnmatchcase`):
`include-repositories`, `exclude-repositories`, `include-projects`,
`exclude-projects`. All absent means unfiltered (today's behaviour; the dev
profile). Repository globs match the repository name. Project globs match the
OBS project name **without** the rootprj prefix (`ppg:staging:17:containers`,
`common:containers:*`); the root project itself matches the empty string and
is never excluded.

### Semantics

- A repository *matches* iff (no include list or it matches an include glob)
  and it matches no exclude glob.
- A project *passes the project test* iff (no include list or its name
  matches an include glob) and it matches no exclude glob. Descendants are
  independent: excluding `ppg:staging:17:containers` does not exclude
  `ppg:staging:17:containers:x`; use `:*` globs.
- **Same-project rescue**: a matching repository whose `paths` reference a
  sibling repository of the same project keeps that sibling too, transitively
  (OBS rejects meta whose kept repo paths to a missing sibling). Cross-project
  paths never rescue anything; Section 4 validates them instead.
- Applied to a resolved configuration the filter removes non-matching
  entries from `repositories` and drops the corresponding keys from the
  `debuginfo`, `publish` and `build` maps. `project-config` text is not
  touched (`%if "%_repository" == "UBI_8"` blocks are inert on an instance
  without that repository).

### Derived selection

- **Project in slice** iff it passes the project test **and** its filtered
  repository list is non-empty. A project that already has zero repositories
  unfiltered is therefore out of slice everywhere (new rule: never created).
- **Package in slice** iff its project is in slice and at least one surviving
  repository is not `false` in the package's `package.yaml` `build:` map.
- Both predicates live in `project_config.py` next to the filter and are the
  only way consumers decide membership.

### Implementation

- `project_config.RepositoryFilter` (frozen dataclass): `include_repos`,
  `exclude_repos`, `include_projects`, `exclude_projects` as tuples;
  `is_empty`; `project_passes(name)`; `repo_matches(name)`;
  `apply(config, project_name) -> dict` (repositories with rescue, flag maps);
  `from_profile(dict)` and `from_env_json(str)` constructors.
  `RepositoryFilter.EMPTY` is the explicit "unfiltered" value.
- `resolve_project_config(project_path, env_vars=None, repo_filter=None)`:
  `None` means "use the process default"; `RepositoryFilter.EMPTY` means
  unfiltered. The project name for the project test is derived from
  `project_path` relative to `REPO_ROOT` joined with colons, honouring a `name:`
  override in the leaf file.
- `common.set_default_repository_filter(f)` / `get_default_repository_filter()`;
  `cli.main()` calls the setter after profile loading. The default is
  `RepositoryFilter.EMPTY` when no profile or a profile without filter keys is
  active. `common._load_project_config_with_inheritance(project_path,
  env_vars=None, repo_filter=None)` forwards the argument.
- `project_config.project_in_slice(project_path, env_vars=None,
  repo_filter=None) -> bool` and `package_in_slice(package_path, env_vars=None,
  repo_filter=None) -> bool`; both accept an optional pre-resolved config to
  avoid re-resolving in loops.
- `cmd_profile._load_profile` returns the four lists (validated: list of
  strings, else error naming the profile file); `profile create` gains
  repeatable flags `--include-repos`, `--exclude-repos`, `--include-projects`,
  `--exclude-projects` (comma-separated globs) and writes the keys;
  `-P name profile create name` round-trips them like `-e`; `profile list`
  prints them.

## Section 2: `sync push`

- Targets and the project pre-pass skip out-of-slice projects and packages:
  not created, not configured, not uploaded, not added to
  `local_project_names` / `local_packages_by_project`. The summary line gains
  `(N projects, M packages out of slice)`; `--verbose` lists them as `·`
  lines.
- Orphan cleanup therefore deletes them on a full-tree push (existing guards
  unchanged: only when `args.project is None`, never with `--non-recursive`,
  PR- and release-managed projects exempt). The first `sync push -P boo`
  deletes every `:containers` project and every UBI-only package from
  production; the rollout starts with `--dry-run` and a reviewed deletion list.
- `--only-repos` and its plumbing are removed: the CLI flag; `only_repos` /
  `effective_only_repos` in `cmd_sync.py`; `_IMAGES_REPO_RE`,
  `_CONTAINER_SUBPROJ_RE` and the target filtering they drive;
  `obs_api._filter_meta_repos` and the `only_repos` parameter of
  `_apply_project_config`; the `only_repos` clause of
  `_can_skip_project_apply` (Phase 2.5 now compares sliced meta, so its
  verdict stands). `image_dep_query_repos` loses its `only_repos` parameter;
  it reads sliced repositories through the loader.
- Branch decision, dep-cascade and content checks are unchanged in logic:
  they read repository names through the loader and compare against the
  instance's own OBS state. `--branch-from` already requires both profiles to
  share an instance; both profiles must also carry the same filter, which the
  tool checks and refuses otherwise.

## Section 3: `project verify` and `project config`

- **Repository path integrity** (new, always on): for every in-slice project
  and every kept repository, each `subproject:` path that names a project in
  the tree must name a project that is in slice and a repository that is kept
  there. Unfiltered this is plain repo-level reference validation (does not
  exist today). Failures are errors naming the referring file, repository and
  path.
- **Slice summary**: `project verify -P X` prints the counts of out-of-slice
  projects and packages; `--verbose` lists them. `project config --resolved
  -P X` renders in-slice projects only and emits
  `# project <name>: out of slice` for the others; `project config <prj>` for
  an out-of-slice project prints that line and exits 0.
- Validators keep skipping `_shared/` and `releases/` as before.

## Section 4: release flow

### `project release` (generator)

The top-level `root/ppg/releases/<V>/project.yaml` is generated from the
**unfiltered** resolved configuration of the source staging project
(`repo_filter=RepositoryFilter.EMPTY`), rendered with the release macros, the
same way the subproject mirrors already are since PR #82. Live OBS meta is no
longer the source of repositories or `debuginfo` for the release tree. The
generated files are byte-identical to today's for the current tree (gate,
Section 7); `_read_project_release_source`/`_obs_meta_to_yaml_repos` stay for
`sync release`.

### `sync release`

Runs once per instance. Release project meta (first release copies live
sliced source repos; update releases render the frozen mirror through the
sliced loader), release targets and `_filter_release_repo_names` need no
change. `_collect_release_subprojects` drops subprojects whose release mirror
is out of slice for the active filter, so the release loop, the build-freeze
scope, `assert_all_green`, `verify_release_landed` and the missing-mirror hard
error see only projects that exist on that instance. A release stays a full
snapshot of that instance's slice. The orphan warning for release
subprojects is unchanged.

## Section 5: CI workflows

A repository variable `OBS_INSTANCES` holds a JSON list, one entry per
instance:

```json
[{"name": "boo",  "apiurl": "https://api.opensuse.org",
  "rootprj": "isv:percona", "pr_rootprj": "isv:percona:pr",
  "exclude_repos": "UBI_*,ubi*,images"},
 {"name": "labs", "apiurl": "https://obs.pg.labs.percona.com",
  "rootprj": "percona", "pr_rootprj": "percona:pr",
  "include_repos": "UBI_*,ubi*,images"}]
```

Password secrets are `OBS_PASSWORD_<NAME>` (looked up with
`secrets[format('OBS_PASSWORD_{0}', matrix.instance.name)]`). Missing filter
fields mean unfiltered.

- **sync-main**: `sync` and `poll` jobs run as `strategy.matrix.instance:
  fromJSON(vars.OBS_INSTANCES)`, `fail-fast: false`; each creates its profile
  with the instance's `-A/-R` and filter flags; sync report, badge and summary
  are per instance.
- **obs-pr-check**: `sync` and `build` take the same matrix; the PR profile of every instance gets the instance filter **plus**
  the label-derived rules appended: each repo label becomes an
  `--include-repos` entry; `<flavor>-images` expands to
  `<flavor>,UBI_<n>` plus `--exclude-projects common:containers:<other>`;
  `ssl*` is appended whenever any repo label is present (tarballs keep
  building on labelled PRs, as today). `detect-qa-matrix` and `qa` are left
  as they are in this change, still reading the existing `OBS_APIURL` /
  `OBS_PR_ROOTPRJ` variables (QA routing per instance is the deferred
  follow-up).
- **obs-release**: the `release` job takes the matrix; one dispatch releases
  both slices.
- **`poll_obs_builds.py`** receives `OBS_REPO_FILTER` (the instance's four
  lists as JSON) and applies `project_in_slice` when discovering projects from
  the tree, so it never polls projects absent from that instance.
- Setting `OBS_INSTANCES` and the secrets is an operator step, documented in
  `docs/PERCONA_OBS_TOOL.md`.

## Section 6: documentation

- `.github/copilot-instructions.md`: new subsection "Connection profiles and
  slices" under the profile section; remove `--only-repos` from the `sync
  push` synopsis; note the zero-repository rule under project configuration.
- `docs/PERCONA_OBS_TOOL.md`: profile keys, `profile create` flags, slice
  semantics with the `boo`/`labs` example, `OBS_INSTANCES` shape, rollout
  notes (first-run deletions).
- `root/README.md`: one paragraph stating the tree is instance-agnostic and
  profiles slice it.

## Section 7: testing and rollout

### Tests

- `tests/test_project_config_merge.py`: filter application (include only,
  exclude only, both, unfiltered default), flag-map pruning, same-project
  rescue transitive and not cross-project, project globs, root never
  excluded, `name:` override honoured, explicit `EMPTY` beats the default.
- New `tests/test_slice_selection.py`: `project_in_slice` /
  `package_in_slice` including zero-repository projects, `build:` maps that
  disable every surviving repo, `_collect_release_subprojects` dropping
  out-of-slice mirrors, `project verify` path-integrity errors and slice
  summary, profile parsing and `profile create` round-trip, `--branch-from`
  filter mismatch refusal.
- `tests/test_meta_repo_filter.py` and the `only_repos` cases in
  `tests/test_image_dep_repos.py` are rewritten against `RepositoryFilter`;
  `tests/test_project_prepass.py` and `tests/test_project_release.py`
  adjusted where they pass `only_repos`.
- `tests/test_project_release.py`: generator output from the tree equals the
  former live-meta output for a fixture staging project.

### Gates (scratchpad scripts, not committed)

1. **Unfiltered regression**: rendered meta XML and effective prjconf per
   repository for every non-release, non-`_shared` project are byte-identical
   to the baseline captured from a detached worktree of
   `percona/project-yaml-dedup` with the same venv.
2. **Partition**: with the `boo` and `labs` rules, for every project the union
   of the two sliced repository sets equals the unfiltered set and the
   intersection is empty; for every package, it is in slice on at least one
   instance and the two instances' surviving-repository sets are disjoint.
3. **Release generator**: `project release --dry-run`-equivalent rendering of
   the tree for staging 17 and 18 produces the current
   `root/ppg/releases/{17,18}/project.yaml` modulo fields that already differ
   between staging and the frozen snapshot (documented in the plan).

### Rollout

1. Tool PR against `percona/main` (after PR #82 merges; rebase the worktree).
2. Create `.profile/boo.yaml` locally; `sync push -P boo --dry-run` against
   production; review the deletion list (containers projects, UBI-only
   packages) and the meta updates (UBI repos removed from package projects).
3. Create `.profile/labs.yaml`; `sync push -P labs --dry-run`, then the real
   push builds the UBI slice on labs.
4. Set `OBS_INSTANCES` and secrets; land the workflow changes.

## Out of scope

- QA registry host (`registry.opensuse.org/` in `qa:` blocks) and QA workflow
  routing per instance.
- Cross-instance dependencies inside one run (labs never paths to b.o.o).
- Any change to `project.yaml`/`subprojects.yaml` semantics or to
  `macros.yaml`.
- Deduplicating or editing `root/ppg/releases/`.
