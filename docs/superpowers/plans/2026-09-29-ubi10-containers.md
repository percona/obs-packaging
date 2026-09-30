# UBI 10 Container Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every PPG container project builds `ubi8`, `ubi9` and `ubi10` flavours of its images (extras: `ubi9` only) from the official `registry.access.redhat.com/ubi<N>/ubi-minimal:latest` images through OBS download-on-demand, with one Dockerfile per image, and the kiwi-built `percona-ubi-minimal` stack is retired.

**Architecture:** Packaging-config change plus a two-line Dockerfile edit. A new `common:containers:ubi10` project supplies `createrepo_c` (the only build helper UBI 10 lacks). Each containers project file (not extras, which build on UBI_9 only) gains a `ubi10` repository whose first path is `RedHat:UBI:Registry/images`, a `%if ubi10` prjconf block, and a `ubi10` QA lane; every existing image repository gets the registry path first and loses the kiwi image path; the base image is selected per repository through a `UBI_BASE` docker build arg that the Dockerfiles consume with `ARG UBI_BASE=… / FROM $UBI_BASE`. No tool or release changes.

**Tech Stack:** YAML packaging tree under `root/`, OBS Dockerfile builds (`Type: docker`, `BuildEngine: podman`, `#!UseOBSRepositories`), `percona-obs` CLI, labs OBS via the `labsmain` profile.

**Spec:** `docs/superpowers/specs/2026-09-29-ubi10-containers-design.md`

## Global Constraints

- Work only in the worktree `.claude/worktrees/ubi10-containers` (branch `ubi10-containers`, based on `percona/main` 07c60bd5). `venv` and `.profile` are symlinks to the primary checkout. `project config` needs `-P labsmain --offline`; that profile slices to `UBI_*`/`ubi*`/`images`, so other repositories are absent from its output by design.
- **`ubi10` repository block rule** (every container project file): copy the file's own `ubi9` block, then (a) insert `- project: RedHat:UBI:Registry` / `repository: images` as the FIRST path, (b) delete the `common:containers:ubi9` / `images` path, (c) replace `UBI_9` → `UBI_10`, `common:containers:ubi9` → `common:containers:ubi10`, `Fedora:EPEL:9` → `Fedora:EPEL:10`, `RedHat:UBI-9` → `RedHat:UBI-10`, `name: ubi9` → `name: ubi10`. Everything else (subproject order, archs) identical. Place it directly after the `ubi9` block.
- **`ubi8`/`ubi9` repository edit rule** (same files): in each existing `ubi8` and `ubi9` block, insert `- project: RedHat:UBI:Registry` / `repository: images` as the FIRST path and delete the two lines `- subproject: common:containers:ubi<N>` / `repository: images`. Keep the `common:containers:ubi<N>` / `UBI_<N>` path and everything else.
- **prjconf rule:** the `%if "%_repository" == "ubi10"` block = the file's `ubi9` block with `RHEL_VER=el9` → `RHEL_VER=el10` and one extra line `BuildFlags: dockerarg:UBI_BASE=registry.access.redhat.com/ubi10/ubi-minimal:latest`. The existing `ubi8` and `ubi9` blocks each gain `BuildFlags: dockerarg:UBI_BASE=registry.access.redhat.com/ubi8/ubi-minimal:latest` (ubi8) / `…/ubi9/ubi-minimal:latest` (ubi9) directly after their `RHEL_VER` line. Two-space indentation inside `project-config: |`, blank lines as in the neighbours.
- **QA rule:** a `ubi10` lane is a copy of the `ubi9` lane with `/ubi9` → `/ubi10` in `REPOSITORY` (and `OLD_DOCKER_REPOSITORY`) and `name: ubi9` → `name: ubi10` (`ubi9-upgrade` → `ubi10-upgrade`). Nothing else in a lane changes.
- **Dockerfile rule:** replace the single line `FROM percona-ubi-minimal:latest` with the two lines `ARG UBI_BASE=registry.access.redhat.com/ubi9/ubi-minimal:latest` and `FROM $UBI_BASE`. Nothing else changes in any Dockerfile.
- No changes under `root/ppg/releases/`, `percona_obs/`; in `tests/` only the lane-count assertion of `test_qa_entry_name.py` (ruling during Task 2). In `.github/` only the one-word loop change. `root/common/containers/ubi8` and `ubi9` change only in Task 7.
- Commits: `git commit -s`, no `Co-Authored-By`. Never `git push`, never `gh pr create`; the user does both (the user also adds the `obs-sync` label).
- After every task: `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q` → "left unchanged", "0 errors", `369 passed`; `venv/bin/python -m percona_obs -P labsmain project verify 2>&1 | grep -i ubi10` → nothing.

**User decisions (already made):**
- "Always use `latest`" for the base image tag.
- "Just keep the labels that are already set in PPG images. No change here."
- "keep it" — `RUN microdnf -y update` stays.
- "no changes to dev instance".
- "I want you to also transition ubi8 and ubi9 images to use the real ubi image" — done in this PR, together with retiring the kiwi minimal-image.

---

### Task 1: `common:containers:ubi10` with `createrepo_c`

**Goal:** A build-helper project for the ubi10 images that provides `createrepo_c` on a `UBI_10` repository (EPEL 10 + UBI 10 + Rocky 10 devel build path).

**Files:**
- Create: `root/common/containers/ubi10/project.yaml`
- Create: `root/common/containers/ubi10/createrepo_c/obs/createrepo_c.spec`, `…/obs/createrepo_c-0.20.1.tar.gz` (byte copies of `root/common/containers/ubi9/createrepo_c/obs/*`)

**Acceptance Criteria:**
- [ ] `project.yaml` is:
```yaml
title: Percona UBI-10 Container Build Helpers
description: |
  Build-time helpers for the UBI-10 based container images (createrepo_c for
  #!UseOBSRepositories). The images themselves are built from the official
  registry.access.redhat.com/ubi10/ubi-minimal image via RedHat:UBI:Registry.

# This project's repository set and build configuration are unrelated to its
# parent's: declare them in full here instead of patching the inherited ones.
repositories-inherit: false
project-config-inherit: false

publish: false
repositories:
  - name: UBI_10
    paths:
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Fedora:EPEL:10
        repository: standard
      - project: RedHat:UBI-10
        repository: standard
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:10
        repository: devel
    archs: [x86_64, aarch64]

project-config: |
  %if "%_repository" == "UBI_10"
  Type: spec
  %endif
```
- [ ] `cmp root/common/containers/ubi9/createrepo_c/obs/createrepo_c.spec root/common/containers/ubi10/createrepo_c/obs/createrepo_c.spec` and the same for the tarball report no difference.
- [ ] `venv/bin/python -m percona_obs -P labsmain project config --offline common:containers:ubi10 | grep -o 'repository name="[^"]*"'` → `repository name="UBI_10"` only.
- [ ] black/pyright/pytest pass; `project verify` prints nothing for ubi10.

**Verify:** `ls root/common/containers/ubi10 root/common/containers/ubi10/createrepo_c/obs` → `createrepo_c project.yaml` and `createrepo_c-0.20.1.tar.gz createrepo_c.spec`.

**Steps:**
- [ ] Step 1: `mkdir -p root/common/containers/ubi10/createrepo_c/obs && cp root/common/containers/ubi9/createrepo_c/obs/* root/common/containers/ubi10/createrepo_c/obs/`; write `project.yaml` as above.
- [ ] Step 2: run the acceptance commands and the checks.
- [ ] Step 3: commit:
```bash
git add root/common/containers/ubi10
git commit -s -m "containers: common:containers:ubi10 with createrepo_c

UBI 10 images are built from the official ubi10/ubi-minimal image via the
RedHat:UBI:Registry download-on-demand project, so this project only needs
createrepo_c (#!UseOBSRepositories), which neither UBI 10 nor EPEL 10 ships;
umoci comes from EPEL 10 and podman/skopeo from UBI 10 appstream."
```

---

### Task 2: `ubi10` in the per-major and cross-major containers projects

**Goal:** `ppg:staging:<V>:containers` (14–18) and `ppg:staging:containers` build a `ubi10` flavour.

**Files:**
- Modify: `root/ppg/staging/_shared/containers/project.yaml` (repos after line 52, prjconf lines 75–88, qa after line 116; description line 7)
- Modify: `root/ppg/staging/containers/project.yaml` (repos after line 70, prjconf lines 93–106, qa after line 134; description line 7)

**Acceptance Criteria:**
- [ ] Both files have a `ubi10` repository per the block rule, and their `ubi8`/`ubi9` blocks are edited per the edit rule (registry path first, no `common:containers:ubi<N>/images` path). `grep -c 'repository: images' <file>` → 3 (one per flavour, all under `RedHat:UBI:Registry`). For `_shared/containers` the rendered paths (`project config --offline ppg:staging:18:containers`) are, in order: `RedHat:UBI:Registry/images`, `isv:percona:ppg:staging:18/UBI_10`, `isv:percona:ppg:common:deps/UBI_10`, `isv:percona:common:containers:ubi10/UBI_10`, `openSUSE.org:Fedora:EPEL:10/standard`, `RedHat:UBI-10/standard`. For `staging/containers` the same with staging 18,17,16,15,14 `UBI_10` paths in place of the single staging path.
- [ ] prjconf per the prjconf rule: three blocks; `grep -c 'dockerarg:UBI_BASE' <file>` → 3 per file; the ubi10 block has `RHEL_VER=el10`.
- [ ] qa: a third lane `- name: ubi10` per the QA rule.
- [ ] Line 7 of both descriptions reads `We currently build our images based on UBI-8, UBI-9 and UBI-10 base containers.`
- [ ] `venv/bin/python -m percona_obs -P labsmain qa show ppg:staging:18:containers` lists lanes `ubi8`, `ubi9`, `ubi10` (same for `ppg:staging:containers`).
- [ ] black/pyright/pytest pass; `project verify` clean.

**Verify:** `for p in ppg:staging:18:containers ppg:staging:containers; do venv/bin/python -m percona_obs -P labsmain project config --offline $p | grep -c 'repository name="ubi10"\|dockerarg:UBI_BASE'; done` → `4` for each (one repo element + three build flags).

**Steps:**
- [ ] Step 1: in each file, apply the edit rule to the `ubi8` and `ubi9` blocks, then insert the `ubi10` repository block (block rule) after the `ubi9` block's `archs:` line.
- [ ] Step 2: prjconf: add `  BuildFlags: dockerarg:UBI_BASE=registry.access.redhat.com/ubi8/ubi-minimal:latest` after the `RHEL_VER=el8` line and the ubi9 equivalent after `RHEL_VER=el9`; append after the `ubi9` block:
```

  %if "%_repository" == "ubi10"

  BuildFlags: dockerarg:RHEL_VER=el10
  BuildFlags: dockerarg:UBI_BASE=registry.access.redhat.com/ubi10/ubi-minimal:latest

  %endif
```
- [ ] Step 3: qa: append the `ubi10` lane (QA rule). Step 4: description line. Step 5: checks. Step 6: commit:
```bash
git add root/ppg/staging/_shared/containers/project.yaml root/ppg/staging/containers/project.yaml
git commit -s -m "containers: ubi10 flavour for the PPG and upgrade images

New ubi10 repository built from registry.access.redhat.com/ubi10/ubi-minimal
via RedHat:UBI:Registry, with UBI_10 RPMs and common:containers:ubi10's
createrepo_c. The base image is now chosen per repository through the
UBI_BASE docker build arg, and ubi8/ubi9 move from the kiwi-built
percona-ubi-minimal to the official ubi8/ubi9 ubi-minimal images."
```

---

### Task 3: extras container projects move to the official ubi9 image

> **Amended during execution:** the extras subprojects build only on `UBI_9` (PR 1 decision), so `ppg:staging:<V>:extras/UBI_10` does not exist and `project verify` rejects a `ubi10` repository here. The task was reduced to the `ubi9` edit rule (registry path first, kiwi `images` path removed) plus the `UBI_BASE` flag in the `%if ubi9` block; no ubi10 repository/prjconf/QA lanes, no QA lane renames, titles unchanged. Commit 1d311651. The original text below is kept for history.

**Goal (original):** `ppg:staging:{16,17,18}:extras:containers` and `ppg:staging:extras:containers` build a `ubi10` flavour, with named QA lanes.

**Files:**
- Modify: `root/ppg/staging/16/extras/containers/project.yaml`, `…/17/…`, `…/18/…` (repos after line 29, prjconf lines 31–53, qa lines 55–end; title/description lines 1–3)
- Modify: `root/ppg/staging/extras/containers/project.yaml` (repos after line 43, prjconf lines 45–66, qa lines 67–end; description)

**Acceptance Criteria:**
- [ ] Each file has a `ubi10` repository per the block rule (per-major: extras, staging, prev-major staging, common:deps, then ubi10 helper, EPEL 10, UBI-10, all preceded by the registry path), and its `ubi9` block is edited per the edit rule.
- [ ] prjconf: the existing `%if "%_repository" == "ubi9"` block gains `BuildFlags: dockerarg:UBI_BASE=registry.access.redhat.com/ubi9/ubi-minimal:latest` after its `RHEL_VER=el9` line; a second block `%if "%_repository" == "ubi10"` with the identical body except `RHEL_VER=el10` and `UBI_BASE=registry.access.redhat.com/ubi10/ubi-minimal:latest` follows it.
- [ ] qa, per-major files: the two existing entries get `name: ubi9` and `name: ubi9-upgrade` (as the first key of each entry); two copies follow with `name: ubi10` / `name: ubi10-upgrade` and `/ubi9` → `/ubi10` in `REPOSITORY` and `OLD_DOCKER_REPOSITORY`. Cross-major file: its single mapping-style `qa:` becomes a list of two entries `name: ubi9` and `name: ubi10` (same pipeline/parameters, `/ubi9` → `/ubi10`).
- [ ] Titles/descriptions: per-major `title: Percona Container Custom Images for PostgreSQL %!{PG_MAJOR_VERSION}` and description `This project contains UBI-9 and UBI-10 based container custom images for Percona Software for PostgreSQL %!{PG_MAJOR_VERSION}.`; cross-major description sentence `We currently build these images based on UBI-9 only, …` → `We currently build these images based on UBI-9 and UBI-10, matching the per-version extras/containers projects.`
- [ ] `venv/bin/python -m percona_obs -P labsmain qa show ppg:staging:17:extras:containers` lists `ubi9`, `ubi9-upgrade`, `ubi10`, `ubi10-upgrade`; `qa show ppg:staging:extras:containers` lists `ubi9`, `ubi10`; no "same check segment" error.
- [ ] black/pyright/pytest pass; `project verify` clean.

**Verify:** `for p in ppg:staging:16:extras:containers ppg:staging:17:extras:containers ppg:staging:18:extras:containers ppg:staging:extras:containers; do venv/bin/python -m percona_obs -P labsmain project config --offline $p | grep -c 'repository name="ubi10"\|dockerarg:UBI_BASE'; done` → `3` for each (one repo element + two build flags).

**Steps:** apply the rules file by file (the three per-major files differ only in the hardcoded major in `REPOSITORY` paths and `OLD_SERVER_VERSION`; keep those as they are), run the checks, commit:
```bash
git add root/ppg/staging/16/extras/containers/project.yaml root/ppg/staging/17/extras/containers/project.yaml root/ppg/staging/18/extras/containers/project.yaml root/ppg/staging/extras/containers/project.yaml
git commit -s -m "containers: ubi10 flavour for the extras (custom) images

Same registry-based ubi10 repository as the main images. The extras QA
lanes get names (ubi9/ubi9-upgrade, ubi10/ubi10-upgrade) because two
flavours now share each pipeline; their check-run names change accordingly."
```

---

### Task 4: Dockerfiles take the base image from `UBI_BASE`

**Goal:** All seven Dockerfiles select their base image through the `UBI_BASE` build arg.

**Files:**
- Modify (line 7 or 8, the `FROM` line): `root/ppg/staging/_shared/containers/percona-distribution-postgresql/obs/Dockerfile`, `…/percona-distribution-postgresql-with-postgis/obs/Dockerfile`, `…/percona-pgbackrest/obs/Dockerfile`, `…/percona-pgbouncer/obs/Dockerfile`, `root/ppg/staging/_shared/extras/containers/percona-distribution-postgresql-custom/obs/Dockerfile`, `root/ppg/staging/containers/percona-distribution-postgresql-upgrade/obs/Dockerfile`, `root/ppg/staging/extras/containers/percona-distribution-postgresql-upgrade-custom/obs/Dockerfile`

**Acceptance Criteria:**
- [ ] `grep -rn "^FROM" root --include=Dockerfile` → seven lines, all `FROM $UBI_BASE`, each preceded by `ARG UBI_BASE=registry.access.redhat.com/ubi9/ubi-minimal:latest`.
- [ ] `git diff --stat` shows 7 files, each `+1 -1` plus one added line (2 insertions, 1 deletion).
- [ ] black/pyright/pytest pass.

**Verify:** `grep -rn -B1 "^FROM" root --include=Dockerfile | grep -c "ARG UBI_BASE=registry.access.redhat.com/ubi9/ubi-minimal:latest"` → `7`.

**Steps:** `sed -i 's|^FROM percona-ubi-minimal:latest$|ARG UBI_BASE=registry.access.redhat.com/ubi9/ubi-minimal:latest\nFROM $UBI_BASE|' <each file>`; verify; commit:
```bash
git add root/ppg/staging/_shared/containers/*/obs/Dockerfile root/ppg/staging/_shared/extras/containers/*/obs/Dockerfile root/ppg/staging/containers/*/obs/Dockerfile root/ppg/staging/extras/containers/*/obs/Dockerfile
git commit -s -m "containers: select the base image with the UBI_BASE build arg

ARG UBI_BASE before FROM lets one Dockerfile serve ubi8, ubi9 and ubi10,
each built from the official registry.access.redhat.com/ubi<N>/ubi-minimal
image; each repository's prjconf sets the value."
```

---

### Task 5: PR-check flavour loop, render checks, hand-over

**Goal:** CI knows the third flavour; the whole branch renders as designed; the user gets push/PR instructions.

**Files:**
- Modify: `.github/workflows/obs-pr-check.yml:307` (`for other in ubi8 ubi9; do` → `for other in ubi8 ubi9 ubi10; do`)

**Acceptance Criteria:**
- [ ] The loop lists `ubi8 ubi9 ubi10`; nothing else in the workflow changes.
- [ ] Offline renders (`-P labsmain --offline`) of `common:containers:ubi10`, `ppg:staging:18:containers`, `ppg:staging:containers`, `ppg:staging:18:extras:containers`, `ppg:staging:extras:containers` show every image repository with the registry path first, no `common:containers:ubi*/images` path anywhere (`grep -rn 'repository: images' root/ppg/staging --include=project.yaml | grep -vc 'RedHat:UBI:Registry' ` is not needed: instead `grep -rn -B1 'repository: images' root/ppg/staging --include=project.yaml | grep -c 'common:containers'` → 0), and the `UBI_BASE` flags for every flavour; `common:containers:ubi8`/`ubi9` render only a `UBI_8`/`UBI_9` repository.
- [ ] `venv/bin/python -m percona_obs -P labsmain project config --diff ppg:staging:18:containers | grep '^[-+]' | grep -v '^[-+][-+]' | grep -v 'ubi10\|UBI_10\|UBI_BASE'` prints only pre-existing drift (self-closing tag spacing, container path reorders) — no other `-` lines.
- [ ] `git log percona/main..HEAD --oneline` shows the docs commits plus six implementation commits (Tasks 1, 4, 3, 2, 7, 5); `git status` clean apart from `venv`/`.profile`.

**Verify:** `grep -n 'for other in' .github/workflows/obs-pr-check.yml` → one line with `ubi8 ubi9 ubi10`.

**Steps:** edit, run checks, commit (`ci: PR check knows the ubi10 image flavour`), then report to the user:
```
Branch ubi10-containers in .claude/worktrees/ubi10-containers is ready.
Push:   git push percona ubi10-containers
PR:     against percona/obs-packaging main, labels ubi8-images ubi9-images ubi10-images (you add obs-sync).
Then:   tell me the PR number for the build round.
```

---

### Task 6: Build round on the labs PR project

**Goal:** Every image builds green on `ubi8`, `ubi9` and `ubi10` in `isv:percona:PR:pr-N` from the official base images, and the shrunken helper projects still provide what the builds need.

**Files:** none unless triage fixes (then one commit per fix naming the OBS symptom).

**Acceptance Criteria:**
- [ ] `common:containers:ubi10/createrepo_c` succeeded on `UBI_10` x86_64 + aarch64.
- [ ] Every image package in `ppg:staging:14–18:containers` and `ppg:staging:containers` is `succeeded` on `ubi8`, `ubi9` and `ubi10`, and every image in `ppg:staging:16–18:extras:containers` and `ppg:staging:extras:containers` on `ubi9`, for both arches (`build status --repo <flavour> <prj>`).
- [ ] For each flavour, `osc api /build/<PR>:ppg:staging:18:containers/<flavour>/x86_64/percona-pgbouncer/_buildinfo` lists a `container:registry.access.redhat.com-ubi<N>-ubi-minimal-latest` bdep from `RedHat:UBI:Registry` and no bdep from `common:containers:ubi<N>` other than `createrepo_c*`/`umoci`.
- [ ] `osc ls <PR>:common:containers:ubi9` → `createrepo_c umoci`; `osc ls <PR>:common:containers:ubi8` → `createrepo_c file-devel popt-devel rpm-devel umoci`; both `UBI_N` builds succeeded.

**Verify:** the commands above, with a profile `labspr` whose `rootprj` is `isv:percona:PR:pr-N` (copy `.profile/labsmain.yaml`, change `rootprj`).

**Steps:** (1) wait for the PR check sync; (2) sweep; (3) triage per the PR-1 rules: `unresolvable` → path/prjconf fix; `failed` with a Dockerfile/`microdnf` error → report with the log excerpt (base-image content difference between the kiwi image and the real UBI image, e.g. a package pre-installed in one but not the other) and fix in the Dockerfile only if it is a one-liner that keeps ubi8/ubi9 identical; (4) ask the user to push after each fix batch; (5) report the final state.

---

### Task 7: Retire the kiwi minimal image in `common:containers:ubi8/ubi9`

**Goal:** `common:containers:ubi8` and `ubi9` keep only the build helpers the docker builds still pull; the kiwi image and its toolchain are deleted.

**Files:**
- Delete: `root/common/containers/ubi9/{minimal-image,python-kiwi,obs-service-kiwi_label_helper,obs-service-kiwi_metainfo_helper,python3-docopt,python3-poetry-core,python3-simplejson,python3-xmltodict}` (directories)
- Delete: `root/common/containers/ubi8/{minimal-image,python-kiwi,obs-service-kiwi_label_helper,obs-service-kiwi_metainfo_helper,python3-docopt,python3-poetry-core,python3-simplejson,python3-xmltodict,python3-tomli,dnf4}` (directories)
- Modify: `root/common/containers/ubi9/project.yaml` (drop the `images` repository entry and the `%if "%_repository" == "images" … %endif` prjconf block; title/description)
- Modify: `root/common/containers/ubi8/project.yaml` (same; keep the `UBI_8` block incl. its `ExpandFlags: module:*` and `Prefer: selinux-policy-targeted` lines)

**Acceptance Criteria:**
- [ ] `ls root/common/containers/ubi9` → `createrepo_c project.yaml umoci`; `ls root/common/containers/ubi8` → `createrepo_c file-devel popt-devel project.yaml rpm-devel umoci`.
- [ ] Both `project.yaml` files: `repositories:` holds only `UBI_<N>`; `project-config` holds only the `%if "%_repository" == "UBI_<N>"` block (ubi9: `Type: spec` + `Ignore: kbd-legacy < 2.4.0-11`; ubi8: that plus its existing `ExpandFlags`/`Prefer` lines); no `kiwi`, `Preinstall`, `container-compression-format` or `images` string remains (`grep -c 'kiwi\|images\|Preinstall' <file>` → 0 for both).
- [ ] Titles: `Percona UBI-<N> Container Build Helpers`; descriptions: `Build-time helpers (createrepo_c, umoci[, and the EL8 -devel repackages createrepo_c needs]) for the UBI-<N> based container images, which are built from the official registry.access.redhat.com/ubi<N>/ubi-minimal image via RedHat:UBI:Registry.`
- [ ] `grep -rn "common:containers:ubi[89]" root/ppg/staging --include=project.yaml | grep -c images` → 0 (Tasks 2–3 already removed the consumers; this confirms nothing under staging still points at the deleted repo). `root/ppg/releases/**` is untouched (frozen; still references the old repo, build-disabled).
- [ ] `venv/bin/python -m percona_obs -P labsmain project config --offline common:containers:ubi9 | grep -o 'repository name="[^"]*"'` → `UBI_9` only (same for ubi8 → `UBI_8`).
- [ ] black/pyright/pytest pass; `project verify` clean.

**Verify:** `find root/common/containers -mindepth 2 -maxdepth 2 -type d | sort` → exactly `ubi10/createrepo_c ubi8/createrepo_c ubi8/file-devel ubi8/popt-devel ubi8/rpm-devel ubi8/umoci ubi9/createrepo_c ubi9/umoci` (with the `root/common/containers/` prefix).

**Steps:** `git rm -r` the listed directories; edit the two project files; run the checks; commit:
```bash
git add -A root/common/containers/ubi8 root/common/containers/ubi9
git commit -s -m "containers: retire the kiwi-built percona-ubi-minimal image

All image flavours now build from the official ubi-minimal images via
RedHat:UBI:Registry, so common:containers:ubi8/ubi9 keep only the build
helpers the docker builds still pull (createrepo_c, umoci, and on EL8 the
rpm/file/popt -devel repackages createrepo_c needs). The kiwi description,
python-kiwi, the kiwi helper services, their python3 deps and dnf4 go, as
does the images repository and its kiwi build config. Labs deletes the
removed packages as orphans on the next full sync."
```

---

### Task 8: non-modular EL8 packages for the ubi8 images (`common:containers:ubi8`)

**Goal:** The ubi8 images install no module-stream package: `common:containers:ubi8` provides non-modular perl-IO-Socket-SSL 2.066, perl-Net-SSLeay 1.88, perl-Mozilla-CA 20160104, perl-DBD-Pg 3.7.4 and llvm/llvm-libs/llvm-filesystem 21.1.8.

**Files:**
- Create: `root/common/containers/ubi8/perl-DBD-Pg/obs/{_service,perl-DBD-Pg.spec,patches…}` (CentOS Stream 8 spec …, `BuildRequires: postgresql-devel >= 7.4` → `libpq-devel`, live tests skipped). Amended after review: perl-IO-Socket-SSL, perl-Net-SSLeay and perl-Mozilla-CA are shipped non-modular by UBI 8 and are not rebuilt.
- Create: `root/common/containers/ubi8/llvm/obs/{_service,llvm.spec}`: `download_url` of the six Rocky 8 AppStream RPMs (`https://dl.rockylinux.org/pub/rocky/8/AppStream/<arch>/os/Packages/l/<llvm|llvm-libs|llvm-filesystem>-21.1.8-1.module+el8.10.0+40180+8e26bdb3.<arch>.rpm`, `+` URL-encoded as `%2B`), spec `Name: llvm`, `Version: 21.1.8`, `Release: 1%{?dist}`, subpackages `libs` and `filesystem`, `%prep`/`%install` extracting the matching-arch RPMs with `rpm2cpio | cpio -idm` into the buildroot and generating per-subpackage `%files -f` lists from `rpm -qlp`; `Requires` copied from the originals (`llvm` requires `llvm-libs = %{version}-%{release}`, `llvm-libs` requires `llvm-filesystem`); `%define debug_package %{nil}`; `ExclusiveArch: x86_64 aarch64`.
- Modify: `root/ppg/staging/_shared/containers/project.yaml`, `root/ppg/staging/containers/project.yaml` (`%if ubi8` block: remove the `ExpandFlags: module:perl-IO-Socket-SSL-2.066` and `module:perl-DBD-Pg-3.7` lines and adjust the comment)

**Acceptance Criteria:**
- [ ] `ls root/common/containers/ubi8` → `createrepo_c file-devel llvm perl-DBD-Pg popt-devel project.yaml rpm-devel umoci`.
- [ ] Each perl spec differs from Stream 8's only in Release, bare Source/Patch names, the changelog entry (and `libpq-devel` for DBD-Pg); tarball sha512 matches Stream's `sources`.
- [ ] `rpmspec -P` succeeds for both specs; no `.module+` string anywhere in the specs' `Release`.
- [ ] `venv/bin/python -m percona_obs -P labsmain project config --offline ppg:staging:18:containers | grep -c 'module:perl-IO-Socket-SSL\|module:perl-DBD-Pg'` → 0 and `grep -c 'module:perl-5.26'` → 1.
- [ ] black/pyright/pytest pass; `project verify` prints nothing for `common:containers:ubi8`.
- [ ] Build round: perl-DBD-Pg and llvm `succeeded` on `common:containers:ubi8/UBI_8` (both arches); every ubi8 image `succeeded`; the image `_buildinfo` lists `perl-IO-Socket-SSL`, `perl-DBD-Pg` (PostGIS images) and `llvm-libs` from `…:common:containers:ubi8`, none from `RedHat:UBI-8`.

**Verify:** `grep -rn "module+" root/common/containers/ubi8/*/obs/*.spec` → nothing; `ls root/common/containers/ubi8 | wc -l` → 8.
