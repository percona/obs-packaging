# project.yaml deduplication: merge-based inheritance

Date: 2026-09-23
Status: approved design, awaiting implementation plan

## Problem

`root/` holds 50 `project.yaml` files totalling about 9300 lines. Nearly all
of it repeats the same 14 distro repositories and the same OBS project-config
(prjconf) blocks. The per-project differences are small: devel adds one path
per repository and drops Debian_12; staging/18 adds the llvm-21 block and
swaps two `Ignore:` lines; tarballs change the repository set but keep the
prjconf.

The root cause is the inheritance rule in
`percona_obs/common.py::_load_project_config_with_inheritance`: `repositories`
and `project-config` are inherited whole-field, nearest ancestor wins. A
subproject that needs one extra path or one extra `Prefer:` must copy the
entire field. Every distro-wide fix (for example the deb `Release:` codename
suffix) therefore has to be replicated into every override, and the copies
drift: comments rot, staging/18 uses a literal `18` where the
`%!{PG_MAJOR_VERSION}` macro exists.

The goal is drift removal: every shared fact lives in exactly one file and a
child expresses only its delta. Reduced onboarding cost and smaller diffs are
welcome side effects, not the target.

## Decisions taken during design

- **Releases stay materialized.** `project release` keeps writing fully
  resolved `project.yaml` files under `root/ppg/releases/`, so a shipped
  release is immune to later edits in root or staging. The releases tree is
  not deduplicated and is not touched by the yaml rewrite.
- **Merge semantics, not fragments or templates.** Fragments (`include:`)
  would still require every child to list what it includes, reintroducing
  drift on every new shared block. A template renderer would create a second
  representation of the tree. Merge-on-inheritance fixes the actual root
  cause (override granularity is the whole field) with no new file types,
  and mirrors how the `macros.yaml` chain already works.
- **Zero OBS churn on landing.** The resolved config of every non-release
  project must be byte-identical before and after the change, so the sync's
  `check_project_config_changed` sees no difference and nothing rebuilds.

## Section 1: schema and merge semantics

### Resolution order

Root to leaf, the same order as `macros.yaml`. The resolver starts from an
empty config, folds in each ancestor's `project.yaml` from `root/` down, and
finally the project's own file. A missing or empty file contributes nothing.

Fields that **never** merge and are read only from the project's own file:
`title`, `description`, `name`, `qa`.

Fields that **do** merge: `repositories`, `project-config`, `debuginfo`,
`publish`, `build`, plus the new control keys below. `debuginfo`, `publish`
and `build` did not inherit before; they now inherit with child-wins
semantics (`debuginfo` merges per repo name, `publish` and `build` replace).
This is a deliberate widening. The byte-identical gate in Section 3 catches
any project where it changes the result.

### project-config

Concatenation in fold order, each contribution stripped of leading and
trailing blank lines first, then preceded by one blank line and a provenance
comment naming the file it came from, relative to the repository:

```
# --- from root/project.yaml ---
%if "%_repository" == "Debian_11"
...
%endif

# --- from root/ppg/staging/project.yaml ---
%if "%_repository" == "openSUSE_Tumbleweed"
...
```

OBS prjconf accepts `#` comments, and the header makes the OBS web UI and
`project render` output self-explaining. OBS prjconf is order-sensitive but
additive, so appending is safe.

`project-config-inherit: false` on a project discards everything inherited so
far and starts from that project's own text. Descendants of that project
inherit from it as usual.

Placement after migration:

- root: distro-wide blocks (EL module `ExpandFlags`, `Prefer:` fixes, the
  Debian/Ubuntu `Release:` codename suffix, golang, libcurl/libjpeg).
- `ppg/staging`: PG-related blocks identical across majors (SUSE
  `Prefer: percona-postgresql%!{PG_MAJOR_VERSION}-server`, `Ignore:` of the
  system postgresql packages, and the `Ignore: postgresql<PREV>-server` line
  written with the `PG_PREV_MAJOR_VERSION` macro).
- `ppg/staging/<V>`: true per-major deltas only (llvm-21 for 18, the
  Debian_11 llvm-11 and Debian_12 llvm-14 `Ignore:` blocks for 18, and so on).
- `ppg/devel` and `ppg/devel/<V>`: same layering as staging.

### repositories

A list merged by `name`. For each entry in the child:

| Situation | Behaviour |
|---|---|
| name not in inherited set | appended as a new repository, exactly as written today |
| name in inherited set | child's `paths` are **prepended** to the inherited paths; `archs` replaces if present, otherwise inherits |
| `remove: true` | drops the repository from the resolved set; no other keys allowed on the entry |
| `paths-replace: true` | child's `paths` replace the inherited list outright instead of prepending |

Prepend is the default because a closer project should shadow a farther one,
matching how ancestor paths are already injected closest-first by
`build_project_meta()`.

`repositories-inherit: false` on a project discards the inherited repository
set and starts from that project's own list. Used by `common/` and by
`ppg/staging/containers`, whose repository sets share nothing with
`ppg/staging/<V>`.

### path-prefix

A project-level list of path entries prepended to **every** repository in the
resolved set, after all per-repository merging. The `repository` value may be
the literal token `%_repository`, which is replaced by the repository's name.

```yaml
path-prefix:
  - subproject: ppg:staging:%!{PG_MAJOR_VERSION}
    repository: "%_repository"
```

This is the only construct that is not a plain merge rule. It exists because
devel's "resolve everything else from staging:<V>" and staging's
"`ppg:common:deps` then `common:deps:build`" are rules over all repositories,
and writing them fourteen times is the drift this design removes.

`path-prefix` itself merges by concatenation, child first, so a devel major's
prefix lands before the tier's prefix.

### Resulting tree shape

- `root/project.yaml`: the 14 distro repository definitions with their
  external (`project:`) paths and archs; distro-wide prjconf.
- `root/ppg/staging/project.yaml`: `path-prefix` for `ppg:common:deps` and
  `common:deps:build`; shared PG prjconf; `debuginfo` map.
- `root/ppg/staging/<V>/project.yaml`: title, description, `qa`, per-major
  prjconf delta. Where a major needs a repository change (for example a
  `RockyLinux_10` entry without `ppg:common:deps`) it is a by-name patch.
- `root/ppg/devel/project.yaml`: `path-prefix` for `ppg:staging:%!{PG_MAJOR_VERSION}`
  plus the staging prefixes; `remove: true` for Debian_12; shared prjconf.
- `root/ppg/devel/<V>/project.yaml`: title, description, per-major prjconf
  delta.
- Tarballs, extras, containers, tde: by-name patches, `paths-replace`, or
  `repositories-inherit: false` as the repository set dictates.
- `root/common/**`: `repositories-inherit: false` where the set is unrelated.
- `root/ppg/releases/**`: untouched.

## Section 2: tool changes

### Single resolver

`_load_project_config_with_inheritance` in `percona_obs/common.py` becomes
the merge implementation, renamed `resolve_project_config`. The old name is
kept as an alias during migration. Every consumer of `repositories`,
`project-config`, `debuginfo`, `publish` or `build` goes through it.

Call sites that today use the plain loader and must switch:

| Location | Purpose |
|---|---|
| `cmd_project.py` `_repo_arch_pairs_from_yaml` | `project status` repo/arch fallback |
| `cmd_project.py` `_validate_subproject_refs` | prepass check 1 |
| `cmd_project.py` `project:` path validator | prepass check for external paths |
| `cmd_project.py` `_write_release_tree` | release subproject mirror |

`load_project_yaml` remains for `title`, `description`, `name` and `qa`. The
`build status` tree walk in `cmd_build.py` reads only `name` and stays on the
plain loader.

### Validation of deltas

The subproject-reference and `project:` validators run on the resolved config,
since that is what reaches OBS. Two new prepass errors:

- `remove: true` or a by-name patch names a repository that is not in the
  inherited set (catches `Debian_21`).
- `remove: true` entry carries any key other than `name` and `remove`.

### Release generator

Output unchanged. The top-level release `project.yaml` already comes from
live OBS meta. The subproject mirror now reads the resolved config, which is
what keeps releases materialized.

### Branch decision, content checks, sync

No change. These compare rendered meta and prjconf against OBS, not yaml
text. A change to an ancestor `project.yaml` already triggers
`check_project_config_changed` for each descendant because that check
renders the config, so a root fix propagates on the next sync run.

### New subcommand: `project render`

`percona-obs project render <project> [--diff]` prints the fully resolved
config (YAML), or with `--diff` shows a unified diff of the rendered meta and
prjconf against what OBS currently holds. It reuses the render path the sync
already uses. This is the migration tool and the everyday answer to "what
does staging:18 actually get".

### Documentation

- `.github/copilot-instructions.md`, section "Config inheritance": replace
  with the merge rules and a worked devel/17 example.
- `docs/PERCONA_OBS_TOOL.md`: document `project render` and the new keys.
- `root/README.md`: one paragraph stating files are deltas and pointing at
  `project render`.

## Section 3: migration, testing, rollout

### Byte-identical gate

A throwaway script (scratchpad, not committed) renders the resolved config of
every non-release project with the current tool and stores it as a baseline
(one file per project: resolved YAML plus rendered prjconf text). After the
tool change and each step of the yaml rewrite, the same render must match the
baseline exactly. The prjconf comparison strips comment lines (`#`-prefixed)
on both sides, because the provenance headers are new by design. Two
documented exceptions, both of which render to the same text anyway:
staging/18 and devel/18 where a literal `18` becomes the macro. Any other
difference is a bug in the rewrite.

Consequence: the first sync after merge writes a new prjconf (comments only)
to every non-release project. A prjconf-only change rebuilds nothing in OBS
(observed during the deb codename rollout), and comment lines cannot alter
dependency resolution, so this is churn in metadata only.

### Rewrite order

1. `root/project.yaml`
2. `root/ppg/staging/project.yaml`, `root/ppg/devel/project.yaml`
3. `root/ppg/{staging,devel}/<V>/project.yaml`
4. tarballs, extras, containers, tde subtrees
5. `root/common/**`

Gate re-run after each step. Releases untouched.

### Tests

New `tests/test_project_config_merge.py` with fixture trees covering:

- plain inheritance (child has no field) unchanged from today
- prjconf concatenation and `project-config-inherit: false`
- repository append (new name)
- path prepend by name, `archs` override and inherit
- `remove: true`, including the two validator errors
- `paths-replace: true`
- `repositories-inherit: false`
- `path-prefix` with `%_repository` substitution and child-first ordering
- `debuginfo` per-repo merge, `publish`/`build` child-wins

`tests/test_project_release.py` gains a case where the source subproject is a
delta and the release mirror emits fully materialized repositories.

Tests are written before the implementation.

### Rollout

One PR against `percona/main` from worktree
`.claude/worktrees/project-yaml-dedup`, three commits:

1. resolver, validators, tests
2. `project render` and docs
3. yaml rewrite

The sync running with no OBS change other than the comment-only prjconf
rewrite is the acceptance test. If anything
rebuilds, commit 3 reverts cleanly and commits 1 and 2 stand on their own.

## Out of scope

- Deduplicating `root/ppg/releases/`.
- Deduplicating the `qa:` blocks.
- Any change to `macros.yaml` resolution.
- `include:`-style fragments or template rendering.
