# project.yaml deduplication: merge-based inheritance

Date: 2026-09-23
Status: approved design (amended during planning, see "Amendments"); implementation plan in
`docs/superpowers/plans/2026-09-23-project-yaml-dedup.md`

## Problem

`root/` holds 50 `project.yaml` files totalling about 9300 lines. Nearly all
of it repeats the same 13 distro repositories and the same OBS project-config
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
  not deduplicated. The only change under `root/ppg/releases/` is a new
  `subprojects.yaml` marker at the tier level (see `standalone`).
- **Merge semantics, not fragments or templates.** Fragments (`include:`)
  would still require every child to list what it includes, reintroducing
  drift on every new shared block. A template renderer would create a second
  representation of the tree. Merge-on-inheritance fixes the actual root
  cause (override granularity is the whole field) with one new tier-level file
  type, and mirrors how the `macros.yaml` chain works.
- **No effective OBS change on landing.** For every non-release project, the
  rendered meta XML must be byte-identical and the effective prjconf per
  repository must be unchanged (see the gate in Section 3). Textual prjconf
  order and comments may change.

## Amendments made while planning (2026-09-23)

Facts found in the tree forced these refinements. None changes the goal.

1. **Root and staging disagree textually.** Root lists 7 of the 13
   repositories with the distro path *before* `common:deps:build`; staging
   lists `ppg:common:deps`, `common:deps:build`, then the distro. Root's
   prjconf has `Prefer: libverto-libev` and `Prefer: Lmod` that staging lacks;
   staging has EL8 `Prefer: python3-devel`/`atlas`, a UBI_9 EL9 block and a
   RockyLinux_10 block that root lacks. Because path order is semantic in OBS,
   the tier carries by-name patches (`paths-replace`) for those 7 repositories
   instead of root being reordered. The two `Prefer` lines move from root to
   the two projects where they are effective today.
2. **Tier-level content needs its own file.** Content that a tier (for example
   `root/ppg/staging/`) contributes to its descendants goes in
   `subprojects.yaml` next to the tier's `project.yaml`. Reasons: the tier's own
   OBS project (`ppg:staging`, package-less) keeps its current meta and
   prjconf; the file may use macros such as `%!{PG_MAJOR_VERSION}` that are
   only defined in the descendants; and `title`/`description` stay obviously
   per-project. `devel` reuses staging's file through a relative symlink,
   which the repo already does for shared package sources.
3. **The gate compares effective prjconf per repository**, not raw text,
   because moving blocks between files reorders them and adds provenance
   comments. All 318 `%if` lines in the tree have the form
   `%if "%_repository" == "A" || "%_repository" == "B" …` with no nesting and
   no `%else`, so the evaluation is exact.
4. **`project render` becomes flags on the existing `project config`
   command**, which already renders meta and prjconf. Adding a second command
   would duplicate it.
5. **`debuginfo`, `publish`, `build` inherit whole-value, child wins**, and
   `null` resets to "unset". Per-repo merging of these maps is not needed by
   any file in the tree.
6. **Substitution order stays text-level.** Three `qa:` blocks start YAML
   scalars with `%!{…}`, so files cannot be parsed before macro substitution.
   Ancestor layers are substituted leniently (undefined tokens left in place);
   a token that survives into the *resolved* config is an error.

## Section 1: schema and merge semantics

### Files and fold order

For a project P whose directory chain from `root/` is A0 (= `root/`), A1, …,
An (= P), the resolver folds, in order:

    A0/project.yaml, A0/subprojects.yaml, A1/project.yaml, A1/subprojects.yaml, …, P/project.yaml

- `project.yaml` fields apply to the project itself **and** are inherited by
  its descendants (today's rule, now merged rather than replaced).
- `subprojects.yaml` applies to **strict descendants only**. Allowed keys:
  `repositories`, `project-config`, `path-prefix`, `debuginfo`, `publish`,
  `build`, `repositories-inherit`, `project-config-inherit`, `standalone`.
  Unknown keys are an error. The file may be a symlink.
- `subprojects.yaml` containing only `standalone: true` makes every strict
  descendant resolve from its own `project.yaml` alone (all ancestor layers,
  including intermediate ones, are dropped). Used by `root/ppg/releases/`.
- A missing or empty file contributes nothing.

Fields that **never** merge and are read only from P's own file: `title`,
`description`, `name`, `qa`, and any key the resolver does not know.

Macro substitution uses P's macro set (the full `macros.yaml` chain down to P,
which is a superset of every ancestor's). Ancestor layers are substituted
leniently: an undefined `%!{VAR}` is left in place so that, for example, a
`Prefer: percona-postgresql%!{PG_MAJOR_VERSION}-server` line in the staging
tier does not break a descendant that opts out of the prjconf. Any `%!{…}`
token remaining in the resolved configuration is an error naming P.

### project-config

Concatenation in fold order. Each contribution is stripped of leading and
trailing blank lines, then preceded by a provenance comment naming the file it
came from, relative to the repository, and contributions are separated by one
blank line:

```
# --- from root/project.yaml ---
%if "%_repository" == "Debian_12"
...
%endif

# --- from root/ppg/staging/subprojects.yaml ---
%if "%_repository" == "openSUSE_Tumbleweed" || "%_repository" == "openSUSE_Leap_16"
...
```

OBS prjconf accepts `#` comments. `project-config-inherit: false` on a layer
discards everything accumulated so far and starts from that layer's own text.

### repositories

A list merged by `name`. For each entry in a layer:

| Situation | Behaviour |
|---|---|
| name not yet known, entry has `archs` | appended as a new repository, exactly as written |
| name not yet known, entry has no `archs` | **error**: a patch for an unknown repository (catches typos) |
| name known | entry's `paths` are **prepended** to the accumulated paths; `archs` replaces if present |
| name known, `paths-replace: true` | entry's `paths` replace the accumulated list |
| `remove: true` | drops the repository; entry may carry no key other than `name` |
| `remove: true` for an unknown name | **error** |

Allowed keys on an entry: `name`, `paths`, `archs`, `paths-replace`,
`remove`. Anything else is an error.

`repositories-inherit: false` on a layer discards the accumulated repository
list **and the accumulated `path-prefix` entries**, and starts from that
layer's own list. Used by every project whose
repository set is not a superset of its parent's (tarballs, extras,
containers, tde, `common/containers/*`, `ppg/common/deps/tarballs`).

### path-prefix

A list of path entries (`subproject:` or `project:`, plus `repository:`)
prepended to **every** repository of the resolved set, after all merging. In
`repository`, the literal token `%_repository` is replaced by the repository
name. Contributions from several layers concatenate child-first.

```yaml
path-prefix:
  - subproject: ppg:staging:%!{PG_MAJOR_VERSION}
    repository: "%_repository"
```

Used by `root/ppg/devel/<V>/project.yaml` (14–18) to say "resolve everything
else from the matching staging project" in three lines instead of thirteen.

### debuginfo, publish, build

Whole-value, child wins. `null` (`~`) resets the value to unset, which is how
a descendant declines a map inherited from a tier.

### Resulting tree shape

- `root/project.yaml`: the 13 distro repository definitions; distro-wide
  prjconf (EL module flags, deb `Release:` codenames, golang, libcurl/libjpeg,
  ncurses/cron) minus `Prefer: libverto-libev` ×2 and `Prefer: Lmod`, which
  move to `common/deps/runtime` and `ppg/common/deps` (the only projects where
  they are effective; root has no packages).
- `root/ppg/staging/subprojects.yaml`: staging `debuginfo` map; a single
  `path-prefix` putting `ppg:common:deps` first in every repository (root
  lists `common:deps:build` before the distro everywhere, so the order is
  `ppg:common:deps`, `common:deps:build`, distro for all 13); PPG-wide prjconf blocks (EL8
  python3-devel/atlas, UBI_9 EL9 block, RockyLinux_10 block, SUSE
  `Prefer: percona-postgresql%!{PG_MAJOR_VERSION}-server` + python313 prefers
  + `Ignore: postgresql-server`/`postgresql`).
- `root/ppg/staging/<V>/project.yaml`: title, description, `qa`, per-major
  prjconf delta only (SUSE `Ignore: postgresql<N>-server`, llvm-21 policy),
  plus for 19 the `RockyLinux_10` prepend patch.
- `root/ppg/devel/subprojects.yaml` → symlink `../staging/subprojects.yaml`.
- `root/ppg/devel/<V>/project.yaml`: title, description, devel `debuginfo`
  map, `path-prefix` to `ppg:staging:%!{PG_MAJOR_VERSION}` (14–18),
  `remove: true` for Debian_12 (14–17), the same per-major prjconf delta as
  staging/<V>. devel/19 mirrors staging/19 exactly (no prefix), as today.
- Tarballs, extras, containers, tde, `common/containers/*`,
  `ppg/common/deps/tarballs`: `repositories-inherit: false` and, where the
  prjconf is not the parent's, `project-config-inherit: false`; `debuginfo: ~`
  where the project has none today. Content otherwise unchanged.
- `root/ppg/staging/extras/project.yaml`: a package-less intermediate that
  previously had no `project.yaml` of its own and inherited root's 13
  repositories by default; it now carries all three opt-outs
  (`repositories-inherit: false`, `project-config-inherit: false`,
  `debuginfo: ~`) and declares no repositories of its own, since nothing
  paths to it.
- `common/deps/build`: inherits root's repositories and prjconf, adds its
  RockyLinux_10 `Prefer:` lines.
- `root/ppg/releases/subprojects.yaml`: `standalone: true`. Release
  snapshots untouched.

### Known residual duplication (accepted for this iteration)

- The per-major prjconf delta is written in both `staging/_shared` and
  `devel/_shared` (devel mirrors staging by design). Within a tier the
  majors share two files: `project.pre18.yaml` (14–17, symlinked) and
  `project.post18.yaml` (18+, symlinked; the SUSE line uses
  `PG_PREV_MAJOR_VERSION`).
- The per-major `containers` and `extras/containers` files stay verbatim;
  their only cross-major difference is a `Prefer: percona-postgresql<N>-libs`
  line that a later change can express with the macro.

### Deliberate effective changes made during review (user decisions)

- Root listed the distro path before `common:deps:build` in six repositories
  (Debian_12/13, Ubuntu_22.04/24.04, Tumbleweed, Leap) and staging carried
  `paths-replace` patches to restore the intended order. Decision: the order is
  `ppg:common:deps`, `common:deps:build`, distro for every repository. Root is
  reordered (affects root, `common:deps:runtime`, `ppg:common:deps`, the
  package-less tiers) and the tier uses one `path-prefix`; UBI_8 in staging
  swaps our two projects' order accordingly.

- `RockyLinux_10` was the only repository whose path list lacked
  `ppg:common:deps` in majors 14–18 (19 had it). Declared a typo; the path now
  comes from the staging tier file for every major. Meta change for
  staging/devel 14–18 on the first sync.
- `devel/19` was a verbatim copy of staging/19 (staging title, no path to
  `ppg:staging:19`). Declared a mistake; it is now a thin devel project like
  devel/18. Meta change for devel/19 on the first sync.
- `staging/19` and `devel/19` ignored `postgresql19-server` on Leap but
  `postgresql18-server` on Tumbleweed. Declared a typo; both now ignore the
  previous major. Effective prjconf change for those two projects.

## Section 2: tool changes

### Single resolver

New module `percona_obs/project_config.py` with
`resolve_project_config(project_path, env_vars=None) -> dict` implementing
Section 1. `common._load_project_config_with_inheritance` becomes a thin
alias so existing callers (`obs_api`, `cmd_sync`, `targets`, `cmd_project`)
switch without edits. `common.apply_macro_substitution` gains
`strict: bool = True`; `strict=False` leaves undefined tokens in place.

Call sites that use the plain loader today and must switch to the resolver:

| Location | Purpose |
|---|---|
| `cmd_project.py` `_repo_arch_pairs_from_yaml` | `project status` repo/arch fallback |
| `cmd_project.py` `_validate_subproject_refs` | prepass check 1 |
| `cmd_project.py` `_validate_project_path_refs` | prepass check for external paths |
| `cmd_project.py` `_write_release_tree` | release subproject mirror |

`load_project_yaml` remains for `title`, `description`, `name` and `qa`
(`find_projects`, `_iter_project_chain`, `cmd_qa`, `build status`,
`.github/scripts/poll_obs_builds.py` read only those).

### Validation of deltas

Merge errors (unknown patch target, bad `remove`, unknown keys in
`subprojects.yaml`, leftover macro) are raised by the resolver as
`SystemExit("error: <file>: …")`. `project verify` reaches them because its
validators now iterate projects through the resolver; `sync` reaches them the
first time it renders a project.

### Release generator

Output unchanged in shape. The top-level release `project.yaml` already comes
from live OBS meta. The subproject mirror now reads the resolved config, so a
delta-style staging subproject still produces a fully materialized release
mirror.

### Branch decision, content checks, sync

No change. These compare rendered meta and prjconf against OBS, not yaml
text. An ancestor edit propagates because `check_project_config_changed`
renders each descendant.

### `project config --resolved` and `--diff`

`percona-obs project config [project] --resolved` prints the resolved
configuration as YAML per project (what the resolver returns) instead of the
meta XML. `--diff` (requires a profile) prints unified diffs of the rendered
meta and prjconf against what OBS currently holds, after merging OBS-managed
elements exactly as the plain command does. This is the migration tool and the
everyday answer to "what does staging:18 actually get".

### Documentation

- `.github/copilot-instructions.md`, section "Config inheritance": replaced by
  the merge rules, `subprojects.yaml`, and a worked devel/17 example.
- `docs/PERCONA_OBS_TOOL.md`: new subsection documenting `project config`,
  `--resolved`, `--diff`.
- `root/README.md`: one paragraph stating files are deltas and pointing at
  `project config --resolved`.

## Section 3: migration, testing, rollout

### Gate

A throwaway script (scratchpad, not committed; full text in the plan) renders
every non-release project with the tool and stores, per project:

- the meta XML from `build_project_meta` (rootprj `ROOT`, env vars
  unsubstituted);
- the effective prjconf per repository: comments and blank lines dropped,
  every `%if "%_repository" == …` block attributed to the repositories it
  names, lines sorted.

`capture` runs on the current tree before any change. `check` re-renders and
must report no difference except an explicit allowlist: the package-less
projects that inherit root's prjconf verbatim (`root`, `ppg:staging`,
`ppg:devel`) lose `Prefer: libverto-libev` and `Prefer: Lmod`. The
`ppg:releases` tier loses them too but is outside the gate, which skips
everything under `releases/`. Anything else is a bug in the rewrite.

The gate enumerates projects by `project.yaml` presence, so the intermediate
directories without one (`root/common`, `root/common/deps`,
`root/common/containers`, `root/ppg`, `root/ppg/common`) were never
baselined. The final review's full-tree comparison found nine package-less
projects lose `Prefer: libverto-libev`/`Prefer: Lmod`: `ROOT`,
`ROOT:common`, `ROOT:common:containers`, `ROOT:common:deps`, `ROOT:ppg`,
`ROOT:ppg:common`, `ROOT:ppg:devel`, `ROOT:ppg:releases`, `ROOT:ppg:staging`
(all verified to hold no packages).

Consequence on OBS after merge: every non-release project gets a textual
prjconf update (comments, block order) with unchanged effective content, and
the nine package-less projects lose two `Prefer` lines. A prjconf-only change
rebuilds nothing (observed during the deb codename rollout), so this is
metadata churn only. Meta XML is unchanged for every project that existed
before, with one exception: `ppg:staging:extras`, a package-less
intermediate that previously inherited root's 13 repositories, now declares
none (its new `project.yaml` opts out of the tier patches); nothing paths to
it, so OBS should accept the removal. If OBS refuses it, keep `repositories`
inherited in that file instead.

### Rewrite order

1. `root/project.yaml`, `common/deps/runtime`, `ppg/common/deps`,
   `common/deps/build`
2. `root/ppg/staging/subprojects.yaml`, `root/ppg/devel/subprojects.yaml`
3. `root/ppg/{staging,devel}/<V>/project.yaml`
4. opt-outs: tarballs, extras, containers, tde, `common/containers/*`,
   `ppg/common/deps/tarballs`; `root/ppg/releases/subprojects.yaml`

Gate after steps 1–3 and after step 4.

### Tests

`tests/test_project_config_merge.py` with fixture trees covering: plain
inheritance unchanged; prjconf concatenation with headers and
`project-config-inherit: false`; new repository requires `archs`; path prepend
and `archs` override; `remove: true` and its two errors; `paths-replace`;
`repositories-inherit: false`; `path-prefix` substitution and child-first
order; `subprojects.yaml` applies to descendants only and may use leaf macros;
symlinked `subprojects.yaml`; `standalone`; flag keys child-wins and `null`
reset; leaf-only keys; leftover macro error.

`tests/test_project_release.py` gains a case where the source subproject is a
delta over a tier `subprojects.yaml` and the release mirror is fully
materialized.

Tests are written before the implementation.

### Rollout

One PR against `percona/main` from worktree
`.claude/worktrees/project-yaml-dedup`, one commit per plan task. The sync
running with no meta change and only the described prjconf churn is the
acceptance test. If anything rebuilds, the yaml-rewrite commits revert cleanly
and the tool commits stand on their own.

## Out of scope

- Deduplicating `root/ppg/releases/`.
- Deduplicating the `qa:` blocks and the per-major containers files.
- Any change to `macros.yaml` resolution.
- `include:`-style fragments or template rendering.
- Fixing the devel/19 and staging/19 oddities noted above.
