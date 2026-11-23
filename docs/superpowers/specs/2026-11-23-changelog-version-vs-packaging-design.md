# Changelog: separate version updates from packaging updates

Date: 2026-11-23
Status: awaiting approval

## Intent

The CHANGELOG section written by `project release` is the raw material for the
release notes (and the GitHub release body). Today it is hard to use for that:

- Top-level packages get a line only when the upstream version changed. A
  packaging-only change is silently dropped.
- Container image entries list every installed package whose version-release
  string differs, so a handful of real changes hide among dozens of rebuild
  counter increments.

The section should show two clearly separated kinds of change and nothing else:
upstream version updates, and packaging updates with the reason for each.

## Goals

- `### Changed` is split into `#### Version updates` and `#### Packaging updates`.
- Pure rebuilds (only the build counter moved) are never listed, for top-level
  packages and inside container image entries alike.
- Each packaging update shows the counter change and the commits that caused
  it, each commit linked to the pull request that brought it in.

## Non-goals

- Rewriting sections of already-cut releases.
- Changing `### Added` or `### Removed`, or the existing upstream-scan lines
  of `### Security`.
- Listing CVEs still open in the new images.
- Commit lists under version-update lines (the upstream release link is the
  explanation there).
- Commit lists inside container image sub-lists.

## Anti-goal

A changelog that disagrees with the shipped binaries: a packaging change that
reached the binaries must not be missing because no commit touched the package
directory.

## Definitions

A version-release string is `<upstream version>-<release>`. In `<release>` the
source-commit counter (OBS `vrev`) is followed by the build counter:

- RPM: `<vrev>.<bcnt>[.dist]`, e.g. `2.60.0-4.2.el9` has vrev `4`.
- Deb: `<N>+<vrev>.<bcnt>.<codename>`, e.g. `4.2.0-6+7.3.bookworm` has vrev `7`.

Comparing the previous release with the one being cut, per package:

| Upstream version | vrev | Class |
|---|---|---|
| differs | any | version update |
| same | differs | packaging update |
| same | same | rebuild: not listed |

## Approaches

1. **Counter decides, git explains (chosen).** The class comes from the version
   data above. Git supplies the reasons. Reflects what shipped; a tool-driven
   re-commit (shared macro, re-render) still appears, labelled as such.
2. **Git decides, counter shown.** A package is a packaging update only when
   commits touched its directory. No tooling noise, but misses changes that
   arrive through shared macros or prjconf and lists commits that changed
   nothing in the build. Rejected: violates the anti-goal.
3. **Either triggers.** Carries the noise of both. Rejected.

## Design

### Output

```markdown
## [17.12-2] - 2026-11-27

### Changed

#### Version updates
- percona-credcheck: update upstream version 6.0 (https://github.com/HexaCluster/credcheck/releases/tag/v6.0)
- percona-distribution-postgresql [container image]: update image 17.12-1 → 17.12-2
  - [ubi8, ubi9, ubi10] updated: percona-credcheck17 5.0 → 6.0

#### Packaging updates
- percona-pgaudit: 17.2-1 → 17.2-2
  - PG-2955 percona-pgaudit<N>-llvmjit is not installable on EL8/9/10 ([#310](https://github.com/percona/obs-packaging/pull/310))
- percona-pgbackrest: 2.60.0-4 → 2.60.0-5
  - no package-level commits (shared macro or tooling change)
```

Rules:

- A packaging line shows `<version>-<old vrev> → <version>-<new vrev>`; the
  build counter and dist suffix are not printed.
- Container image entries: each installed package is classified with the same
  table. `added:`/`removed:`/version `updated:` items go in the image's entry
  under Version updates. Repackaged and rebuilt packages of an image are not
  listed, and an image with no version item gets no entry. Version items print
  upstream versions only (`5.0 → 6.0`).
  (Changed 2026-11-23 after the first dry run: the original design listed
  `repackaged:` items per image under Packaging updates. They duplicated the
  top-level packaging entries without the reason and made up about half of the
  section, so they were dropped.)
- The flavors of an image (`ubi8`, `ubi9`, `ubi10`) share one entry, in
  `### Added`, `### Changed` and `### Security` alike. Every sub-item is
  prefixed with the flavors it applies to, in natural order; a line identical
  in several flavors is written once. Sub-items are ordered by package, then
  by flavor. A removed image is one line naming its flavors:
  `- <image> (ubi8, ubi9) [container image]: remove image <prev>`.
  (Changed 2026-11-23: the original design had one entry per image and flavor,
  which repeated nearly identical blocks.)
- A subsection with no entries is omitted. If both are empty, `### Changed`
  holds the single line
  `- Rebuild only: no version or packaging changes.`

### Commit lookup

- Range: the previous release's `source_commit` to the `source_commit` of the
  release being cut, both from `release.yaml`.
- Paths: the package directory in the source tree, with symlinks resolved (a
  package linked into `_shared` is matched on both the link and its target).
  A package that is a local `_aggregate` is also matched on the directory of
  the package it aggregates, where its packaging lives.
- `git log --no-merges`, oldest first, subject lines only.
- Commits whose subject starts with `devel:` are skipped: the devel tier shares
  the staging packaging directories, and those commits say nothing about the
  release.
- `### Added` is written only when it has entries.
- If the previous release entry has no `source_commit` (plain tag string), the
  packaging line is written with the counter only and no sub-items.

### Pull request links

History on `main` is rebased, so subjects carry no PR number. The PR is looked
up through the GitHub API (`repos/<slug>/commits/<sha>/pulls`) using the
existing `gh api` helper in `percona_obs/github_api.py`; the slug comes from the
release's `repository`.

- The subject stays plain text, followed by `([#N](<pr url>))`. (My call: a
  subject such as `percona-pgaudit<N>-llvmjit` would break as link text.)
- A commit with no PR (direct push) links to the commit instead:
  `([abc1234](<commit url>))`.
- A failed lookup (no `gh`, offline) prints a warning and writes the subject
  without a link; it does not fail the release.

## Container image CVE fixes (obs-dashboard)

### Intent

The `### Security` section today covers upstream release notes only and ends
with "UBI base-image package CVEs are not covered by this scan". The
obs-dashboard already scans every OBS-built container image, so the changelog
can list the CVEs each image stops carrying with this release.

### Source

`GET <dashboard>/api/cve/scans?project=<project>&package=<image>` returns the
latest scan per (repo, arch): `scanned_at` and `findings[]` with `id`, `pkg`,
`installed`, `fixed`, `severity`, `src`. The project is given without the
instance root prefix (e.g. `ppg:releases:17:containers`).

At cut time the release project still holds the previous release's image and
the source (staging) project holds the candidate. Per image and repo:

- fixed = CVE ids found in the release image (any arch) and absent from the
  source image (every arch).
- Open findings in the new image are **not** listed (decided: fixes only).

### Output

One entry per image in `### Security`, after the existing upstream-scan
lines, covering all its flavors; sub-items are grouped by package and tagged
with their flavors, and the header counts the distinct CVE ids across them:

```markdown
- percona-distribution-postgresql [container image]: fixes 16 HIGH/CRITICAL CVEs
  - [ubi9] krb5-libs 1.21.3-11.el9 (fix: 1.21.3-11.el9_3.2): CVE-2026-112320, CVE-2026-112321
  - [ubi9] python3.12-dns 2.8.0-3.1.el9 → 2.9.0-3.2.el9: CVE-2026-114605
```

- Old version: the finding's `installed`.
- New version: the image package list the tool fetches holds only packages
  built in our OBS projects, not UBI base packages. A package in that list is
  shown as `old → new`. Any other package is shown with the scanner's fixing
  version, `(fix: <fixed>)`, or with nothing when the finding has none.
- The header names the severities actually present among the fixes.
- An image with no fixes gets no entry.
- The line "UBI base-image package CVEs are not covered by this scan." is
  replaced by a line only when the scan could not run (below).

### Configuration and failure

- Dashboard base URL: `OBS_DASHBOARD_URL`, read from the release env (profile
  env and `-e` overrides) and then from the process environment. (My call: no new CLI
  flag or profile key.)
- Best effort, like the existing CVE scan. Unset variable, unreachable
  dashboard, or no scan for an image: a warning on stderr and one line in the
  section, `- Not scanned: <image> (<reason>)`, or
  `- Container image CVEs not scanned (OBS_DASHBOARD_URL not set).` The
  release never fails because of it.
- Freshness: the tool prints each candidate scan's `scanned_at` while
  fetching, so a stale scan is visible at cut time.

### Limits (accepted)

- The dashboard exposes only the latest scan, so past sections cannot be
  regenerated.
- Only the severities the dashboard records (HIGH and CRITICAL as observed).
- An image's first release has no previous image and gets no entry.

## Constraints

- Works with `--also-profile`: classification runs on the already-merged
  version dicts.
- No new dependencies.
- `black` and `pyright` clean; unit tests for the classifier, the vrev parser
  (RPM and deb forms), the section layout, and the commit/PR formatting with
  the git and GitHub calls stubbed, and the image CVE diff and its failure
  lines with the dashboard call stubbed.
- `docs/PERCONA_OBS_TOOL.md` describes the new section layout.

## Left to the builder

- Function boundaries inside `cmd_project.py` (or a new small module if the
  classifier and formatter read better apart from it).
- Caching of PR lookups within a run (one commit can touch several packages).
