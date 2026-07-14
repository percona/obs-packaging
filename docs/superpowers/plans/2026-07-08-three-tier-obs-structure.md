# Three-Tier OBS Project Structure (PG-2518) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the devel/staging/releases three-tier OBS structure per the approved spec at `docs/superpowers/specs/2026-07-08-three-tier-obs-structure-design.md`.

**Architecture:** Four staged PRs: (1) `_link` support in `percona_obs/cmd_sync.py` + docs; (2) `ppg/18` → `ppg/staging/18` rename; (3) `ppg/devel/18` with seed packages; (4) versions 14–17. Human verification gates sit between PRs 2/3/4 because they depend on CI merges and live OBS builds.

**Tech Stack:** Python 3 (`percona_obs/` package, venv at `venv/`), OBS via `osc`, YAML project configs under `root/`, GitHub Actions CI.

**User decisions (already made):**
- D1: spec covers structure + migration + tooling; nightly trigger is future work.
- D2: all versions 14–18 renamed to `staging/`; every version gets a devel project (14–17 empty).
- D3: `ppg:devel:18` seeded with percona-postgresql, percona-pg_tde, percona-pg_oidc_validator (Class A) + percona-ppg-server (Class B).
- D4: seed dev branches = sensible defaults, confirmed at implementation against the upstream repos.
- D5 (revised): Class A packages carry **full copies** of `rpm/`/`debian/`/macros — duplicated from staging, maintained by hand, allowed to diverge. No symlinks.
- D6: staged migration, four PRs, verification gates between them.
- D8: no CLI aliases for old project names.
- Repo convention (CLAUDE.md): every code change is verified with `venv/bin/black percona_obs/` + `venv/bin/pyright`; there is **no test suite** in this repo, so tasks verify via black/pyright and `--dry-run` CLI runs against the `dev` profile instead of pytest.

**Conventions for every task:**
- Work branches are cut from up-to-date `main` (`git fetch origin && git checkout -b <branch> origin/main`).
- Commits use `git commit -s`. Never add `Co-Authored-By: Claude` lines.
- After any change under `percona_obs/`: `venv/bin/black percona_obs/` then `venv/bin/pyright` — both must pass.

---

### Task 1: `_link`-aware unexpanded comparison in cmd_sync

**Goal:** Sync compares `_link` packages against OBS unexpanded, so a link package is recognized as unchanged instead of permanently mismatching against the link target's expanded files.

**Files:**
- Modify: `percona_obs/cmd_sync.py` (around lines 223–316, `_content_matches_branch`)

**Acceptance Criteria:**
- [ ] New helper `_is_link_package(obs_dir)` returns True iff `obs_dir/_link` exists.
- [ ] `_content_matches_branch` fetches OBS md5s with `expanded=False` when the local package is a link package, `expanded=True` otherwise (current behavior unchanged).
- [ ] `venv/bin/black percona_obs/` and `venv/bin/pyright` pass.
- [ ] Existing behavior unchanged for non-link packages: `venv/bin/python -m percona_obs -P dev sync push --dry-run ppg:17 etcd` output is identical before/after the change.

**Verify:** `venv/bin/black percona_obs/ && venv/bin/pyright` → "0 errors"; dry-run comparison above.

**Steps:**

- [ ] **Step 1: Capture the baseline dry-run output**

```bash
venv/bin/python -m percona_obs -P dev sync push --dry-run ppg:17 etcd | tee /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/657ffae6-5439-499d-89af-f963049a8ffc/scratchpad/task1-before.txt
```

- [ ] **Step 2: Add the helper above `_content_matches_branch` in `percona_obs/cmd_sync.py`**

```python
def _is_link_package(obs_dir: Path) -> bool:
    """Return True if the package's obs/ directory carries an OBS source link.

    Link packages (obs/_link only) are compared against OBS unexpanded: the
    stored _link file itself is the source of truth.  An expanded fetch would
    return the link *target's* files and report a permanent mismatch.
    """
    return (obs_dir / "_link").is_file()
```

- [ ] **Step 3: Use it in `_content_matches_branch`** — replace the line

```python
    obs_md5s = _fetch_obs_file_md5s(apiurl, branch_project, package_name, expanded=True)
```

with

```python
    obs_md5s = _fetch_obs_file_md5s(
        apiurl,
        branch_project,
        package_name,
        expanded=not _is_link_package(obs_dir),
    )
```

- [ ] **Step 4: Format, type-check, and compare behavior**

```bash
venv/bin/black percona_obs/ && venv/bin/pyright
venv/bin/python -m percona_obs -P dev sync push --dry-run ppg:17 etcd | diff /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/657ffae6-5439-499d-89af-f963049a8ffc/scratchpad/task1-before.txt -
```

Expected: pyright "0 errors"; diff empty.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/cmd_sync.py
git commit -s -m "sync: compare _link packages against OBS unexpanded"
```

```json:metadata
{"files": ["percona_obs/cmd_sync.py"], "verifyCommand": "venv/bin/black percona_obs/ && venv/bin/pyright", "acceptanceCriteria": ["_is_link_package helper added", "_content_matches_branch uses expanded=not _is_link_package(obs_dir)", "black+pyright pass", "non-link dry-run output unchanged"], "modelTier": "standard"}
```

---

### Task 2: `_link` target rewriting in branch mode

**Goal:** In PR namespaces (`--branch-from`), `_link` `project=` references to unpromoted subprojects are redirected to the production rootprj, exactly like `_aggregate` references — so Class B links expand onto real sources, not onto an `_aggregate`.

**Files:**
- Modify: `percona_obs/cmd_sync.py` (around lines 160–207, `_rewrite_aggregate_for_branch` / `_rewrite_aggregates_in_dir`)

**Acceptance Criteria:**
- [ ] New `_rewrite_link_for_branch(content, rootprj, branch_rootprj, active_projects)` rewrites the `<link project=…>` attribute with the same inactive-project rule as `_rewrite_aggregate_for_branch`.
- [ ] `_rewrite_aggregates_in_dir` also rewrites a `_link` file when present (both existing call sites — upload path and no-services path — pick this up automatically).
- [ ] Malformed XML and non-`<link>` roots are returned unchanged.
- [ ] `venv/bin/black percona_obs/` and `venv/bin/pyright` pass.

**Verify:** `venv/bin/black percona_obs/ && venv/bin/pyright` → "0 errors".

**Steps:**

- [ ] **Step 1: Add `_rewrite_link_for_branch` directly below `_rewrite_aggregate_for_branch`**

```python
def _rewrite_link_for_branch(
    content: str,
    rootprj: str,
    branch_rootprj: str,
    active_projects: "set[str] | None",
) -> str:
    """Rewrite _link XML so references to inactive PR subprojects point to branch_rootprj.

    Mirrors _rewrite_aggregate_for_branch.  A devel package's _link targets its
    staging sibling; in a PR namespace an unpromoted sibling holds an _aggregate
    (binaries only) or does not exist, and expanding a link onto an _aggregate
    copies binaries instead of rebuilding.  Redirect the link to the production
    counterpart, which holds real sources.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return content
    if root.tag != "link":
        return content
    proj = root.get("project", "")
    if proj == rootprj or proj.startswith(rootprj + ":"):
        if active_projects is None or proj not in active_projects:
            suffix = proj[len(rootprj) :]  # "" or ":sub:project"
            root.set("project", branch_rootprj + suffix)
            return ET.tostring(root, encoding="unicode", xml_declaration=False)
    return content
```

- [ ] **Step 2: Extend `_rewrite_aggregates_in_dir`** — append after the `_aggregate` block, and update its docstring to say "_aggregate and _link files":

```python
    link_file = directory / "_link"
    if link_file.is_file():
        original = link_file.read_text("utf-8")
        rewritten = _rewrite_link_for_branch(
            original, rootprj, branch_rootprj, active_projects
        )
        if rewritten != original:
            link_file.write_text(rewritten, "utf-8")
```

- [ ] **Step 3: Sanity-check the rewrite logic with a throwaway script**

```bash
venv/bin/python - <<'EOF'
from percona_obs.cmd_sync import _rewrite_link_for_branch
xml = '<link project="home:Admin:pr:pr-1:ppg:staging:18" package="percona-ppg-server" />'
out = _rewrite_link_for_branch(xml, "home:Admin:pr:pr-1", "home:Admin:percona", None)
assert 'project="home:Admin:percona:ppg:staging:18"' in out, out
assert _rewrite_link_for_branch("<notxml", "a", "b", None) == "<notxml"
assert _rewrite_link_for_branch(xml, "home:Admin:pr:pr-1", "home:Admin:percona",
                                {"home:Admin:pr:pr-1:ppg:staging:18"}) == xml
print("ok")
EOF
```

Expected: `ok`.

- [ ] **Step 4: Format, type-check, commit**

```bash
venv/bin/black percona_obs/ && venv/bin/pyright
git add percona_obs/cmd_sync.py
git commit -s -m "sync: rewrite _link project refs in branch mode like _aggregate"
```

```json:metadata
{"files": ["percona_obs/cmd_sync.py"], "verifyCommand": "venv/bin/black percona_obs/ && venv/bin/pyright", "acceptanceCriteria": ["_rewrite_link_for_branch added with inactive-project rule", "_rewrite_aggregates_in_dir handles _link", "malformed/non-link XML passes through unchanged", "black+pyright pass"], "modelTier": "standard"}
```

---

### Task 3: Release-flow audit + documentation updates (completes PR 1)

**Goal:** Confirm the release flow has no `ppg:<V>`-shaped assumptions, update all docs for the three-tier layout, and open PR 1.

**Files:**
- Audit (modify only if assumptions found): `percona_obs/cmd_project.py`
- Modify: `root/README.md`, `docs/PERCONA_OBS_TOOL.md`, `docs/PACKAGING_HOWTO.md`, `.github/copilot-instructions.md`

**Acceptance Criteria:**
- [ ] Audit confirms `project release` treats `release.yaml`'s `project:` value opaquely (no segment-count or prefix assumptions); any violation found is fixed.
- [ ] Docs describe the devel/staging/releases tiers, Class A (full-copy) / Class B (`_link`) devel packages, and use `ppg:staging:<V>` in examples.
- [ ] `venv/bin/black percona_obs/ && venv/bin/pyright` pass (even if no code changed).
- [ ] PR 1 opened.

**Verify:** `grep -rn "ppg:1[4-8]" docs/ root/README.md .github/copilot-instructions.md` shows no un-tiered source-project examples (release-tag names like `ppg/17.9-1` and `ppg:releases:<V>` stay).

**Steps:**

- [ ] **Step 1: Audit the release flow**

```bash
grep -n "release.yaml\|release_project\|source_project\|\.get(\"project\")\|\['project'\]" percona_obs/cmd_project.py
```

Read each hit. The source project must flow verbatim from `release.yaml`'s `project:` field into OBS API calls; the release project must be derived as `<product>:releases:<name>` only. If any code splits the source project on `:` expecting exactly two segments or prepends/derives from `ppg:<V>` shape, fix it to treat the value opaquely and re-run black+pyright.

- [ ] **Step 2: Update `root/README.md`** — in the top-level structure block, replace the `<major-version>/` bullet with the three-tier layout:

```
├── <product>/              # one directory per Percona product, e.g. ppg/
│   ├── releases/           # release definitions (see below)
│   ├── staging/            # tag-based QA/release-candidate projects
│   │   └── <major-version>/   # full package set, e.g. staging/18 → ppg:staging:18
│   └── devel/              # dev-branch projects (manually curated subsets)
│       └── <major-version>/   # e.g. devel/18 → ppg:devel:18
```

Add a "Devel projects" subsection documenting: Class A = full package copy with `_service` retargeted to a dev branch (packaging duplicated deliberately, may diverge); Class B = `obs/_link` to the staging package, rebuilt in devel context; devel repository paths list `ppg:staging:<V>` first, then a copy of staging's upstream paths (OBS expands only the last path transitively); membership is manual and whoever adds a package must add its direct dependents.

- [ ] **Step 3: Update `docs/PERCONA_OBS_TOOL.md` and `docs/PACKAGING_HOWTO.md`** — replace `ppg:17`/`ppg:18` source-project examples with `ppg:staging:17`/`ppg:staging:18` (leave `ppg:releases:*` and git-tag names like `ppg/17.9-1` untouched); mention the devel tier where project layout is described.

- [ ] **Step 4: Update `.github/copilot-instructions.md`** — Repository Layout section gains the `staging/`/`devel/` levels (as in Step 2); `release.yaml` example's `project:` becomes `ppg:staging:17`; add one paragraph defining Class A/Class B devel packages.

- [ ] **Step 5: Verify, commit, open PR 1**

```bash
venv/bin/black percona_obs/ && venv/bin/pyright
grep -rn "ppg:1[4-8]" docs/ root/README.md .github/copilot-instructions.md | grep -v "releases\|ppg/1"
git add -A && git commit -s -m "docs: describe three-tier devel/staging/releases layout"
git push -u origin pg2518-tooling
gh pr create --title "PG-2518: _link tooling support + three-tier docs" --body "Tooling half of PG-2518 (spec: docs/superpowers/specs/2026-07-08-three-tier-obs-structure-design.md). Inert until a _link package exists.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

```json:metadata
{"files": ["percona_obs/cmd_project.py", "root/README.md", "docs/PERCONA_OBS_TOOL.md", "docs/PACKAGING_HOWTO.md", ".github/copilot-instructions.md"], "verifyCommand": "venv/bin/black percona_obs/ && venv/bin/pyright", "acceptanceCriteria": ["release flow treats source project opaquely", "docs updated to three-tier layout", "PR 1 opened"], "modelTier": "standard"}
```

---

### Task 4: Staging pilot — rename ppg/18 (PR 2)

**Goal:** Move `root/ppg/18` to `root/ppg/staging/18`, add the `ppg:staging` container, and update every `ppg:18` / `ppg/18` reference; open PR 2.

**Files:**
- Move: `root/ppg/18/` → `root/ppg/staging/18/` (git mv)
- Create: `root/ppg/staging/project.yaml`
- Modify: `root/ppg/staging/18/project.yaml` (qa REPO), `root/ppg/staging/18/containers/ubi9/project.yaml`, `root/ppg/staging/18/extras/containers/ubi9/project.yaml` (registry REPOSITORY paths), `root/ppg/releases/18/release.yaml`, `root/ppg/releases/18/project.yaml`

**Acceptance Criteria:**
- [ ] `root/ppg/18` no longer exists; `root/ppg/staging/18` contains the full package set.
- [ ] `grep -rn "ppg:18" root/` returns nothing; `grep -rn "ppg/18" root/` returns only git-tag names in `releases/18/release.yaml` (`ppg/18.3-1` etc.).
- [ ] `venv/bin/python -m percona_obs -P dev project verify` exits 0.
- [ ] Dry-run sync shows `ppg:staging` and `ppg:staging:18` as creations and no unexpected package-content changes.
- [ ] PR 2 opened (after PR 1 merged).

**Verify:** `venv/bin/python -m percona_obs -P dev project verify && venv/bin/python -m percona_obs -P dev sync push --dry-run ppg:staging:18`

**Steps:**

- [ ] **Step 1: Branch and move**

```bash
git fetch origin && git checkout -b pg2518-staging-18 origin/main
mkdir root/ppg/staging
git mv root/ppg/18 root/ppg/staging/18
```

- [ ] **Step 2: Create `root/ppg/staging/project.yaml`**

```yaml
title: Percona Software for PostgreSQL — staging
description: |
  Container project for the per-version staging projects (ppg:staging:<V>).
  Staging projects build every package from git tags and feed QA and the
  release projects (ppg:releases:<V>).
```

- [ ] **Step 3: Update references** (exact known occurrences; re-grep to confirm none were added since planning):

1. `root/ppg/staging/18/project.yaml` — qa section: `REPO: ${OBS_ROOTPRJ}:ppg:%!{PG_MAJOR_VERSION}` → `REPO: ${OBS_ROOTPRJ}:ppg:staging:%!{PG_MAJOR_VERSION}`
2. `root/ppg/staging/18/containers/ubi9/project.yaml` — two `REPOSITORY:` lines: `…/ppg/18/containers/ubi9/images` → `…/ppg/staging/18/containers/ubi9/images`
3. `root/ppg/staging/18/extras/containers/ubi9/project.yaml` — two `REPOSITORY:` lines: `…/ppg/18/extras/…` → `…/ppg/staging/18/extras/…`
4. `root/ppg/releases/18/release.yaml` — `project: ppg:18` → `project: ppg:staging:18` (do NOT touch the `releases:` tag list)
5. `root/ppg/releases/18/project.yaml` — description: `Release project for ppg:18` → `Release project for ppg:staging:18`

```bash
grep -rn "ppg:18\|ppg/18" root/   # expect only releases/18/release.yaml tag names ppg/18.x
```

- [ ] **Step 4: Validate and dry-run**

```bash
venv/bin/python -m percona_obs -P dev project verify
venv/bin/python -m percona_obs -P dev sync push --dry-run ppg:staging:18 2>&1 | tail -30
```

Expected: verify exits 0; dry-run shows `+` for the `ppg:staging` / `ppg:staging:18` project chain.

- [ ] **Step 5: Commit and open PR 2** (only after PR 1 is merged)

```bash
git add -A && git commit -s -m "Move ppg/18 to ppg/staging/18 (PG-2518 staging tier)"
git push -u origin pg2518-staging-18
gh pr create --title "PG-2518: staging pilot — rename ppg:18 to ppg:staging:18" --body "Staging tier pilot per docs/superpowers/specs/2026-07-08-three-tier-obs-structure-design.md §7 PR 2. Full rebuild of version 18 expected in CI.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

```json:metadata
{"files": ["root/ppg/staging/18/", "root/ppg/staging/project.yaml", "root/ppg/releases/18/release.yaml", "root/ppg/releases/18/project.yaml"], "verifyCommand": "venv/bin/python -m percona_obs -P dev project verify", "acceptanceCriteria": ["tree moved with git mv", "all ppg:18 refs updated (grep clean)", "project verify exits 0", "PR 2 opened"], "modelTier": "standard"}
```

---

### Task 5: Staging verification gate

**Goal:** Prove `ppg:staging:18` is a full, healthy replacement for `ppg:18` before any devel work lands.

**USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none (verification against live OBS; one manual OBS deletion at the end)

**Acceptance Criteria:**
- [ ] PR 2 merged and `sync-main.yml` completed successfully (GitHub Actions check green).
- [ ] `venv/bin/python -m percona_obs -P <main-profile> build status ppg:staging:18` shows every package `✔ succeeded` on every repository where it succeeded in `ppg:18` before the move (capture both outputs).
- [ ] `venv/bin/python -m percona_obs -P <main-profile> project release ppg:staging:18` runs end-to-end: it reads `releases/18/release.yaml`, generates the changelog diff, and opens a review PR. The review PR is inspected for correctness and **closed unmerged**.
- [ ] Old project deleted only after the two checks above pass: `osc -A <apiurl> rdelete -r -m "PG-2518: replaced by ppg:staging:18" <rootprj>:ppg:18` — destructive; run manually.

**Verify:** `venv/bin/python -m percona_obs -P <main-profile> build status ppg:staging:18` → all `✔` (treat `succeeded*` as `succeeded`)

**Steps:**

- [ ] **Step 1: Before merging PR 2, capture the pre-move baseline**: `build status ppg:18` output saved to a file.
- [ ] **Step 2: Merge PR 2; wait for `sync-main.yml` to finish (it polls builds to terminal states).**
- [ ] **Step 3: Capture `build status ppg:staging:18` and compare against the baseline package-by-package.**
- [ ] **Step 4: Run the release-flow check and close its review PR unmerged.**
- [ ] **Step 5: Delete the old `ppg:18` OBS project (manual, destructive — user confirms).**

```json:metadata
{"files": [], "verifyCommand": "venv/bin/python -m percona_obs -P dev build status ppg:staging:18", "acceptanceCriteria": ["sync-main green after PR 2 merge", "build status parity ppg:18 vs ppg:staging:18 captured", "project release review PR opened, inspected, closed unmerged", "old ppg:18 deleted only after checks pass"], "userGate": true, "tags": ["user-gate"], "requireEvidenceTokens": [["ppg:18", "baseline", "before"], ["ppg:staging:18", "after"]], "modelTier": "standard"}
```

---

### Task 6: Devel pilot — ppg/devel/18 with seed packages (PR 3)

**Goal:** Create the devel container, `ppg:devel:18` project config, three Class A seed packages, and the Class B `_link` package; open PR 3.

**Files:**
- Create: `root/ppg/devel/project.yaml`, `root/ppg/devel/18/project.yaml`, `root/ppg/devel/18/macros.yaml`
- Create: `root/ppg/devel/18/percona-postgresql/`, `root/ppg/devel/18/percona-pg_tde/`, `root/ppg/devel/18/percona-pg_oidc_validator/` (full copies + `_service` branch retarget)
- Create: `root/ppg/devel/18/percona-ppg-server/obs/_link`

**Acceptance Criteria:**
- [ ] `venv/bin/python -m percona_obs -P dev project verify` exits 0.
- [ ] Dry-run sync of `ppg:devel:18` lists exactly the four seed packages.
- [ ] Each Class A `_service` upstream `revision` is a real branch on its upstream repo (verified via `git ls-remote --heads`); chosen branches recorded in the commit message.
- [ ] devel repos each path to `ppg:staging:18` first, then staging's upstream list.
- [ ] PR 3 opened (after Task 5 gate passes).

**Verify:** `venv/bin/python -m percona_obs -P dev project verify && venv/bin/python -m percona_obs -P dev sync push --dry-run ppg:devel:18`

**Steps:**

- [ ] **Step 1: Branch; create `root/ppg/devel/project.yaml`**

```bash
git fetch origin && git checkout -b pg2518-devel-18 origin/main
```

```yaml
title: Percona Software for PostgreSQL — devel
description: |
  Container project for the per-version devel projects (ppg:devel:<V>).
  Devel projects build a manually curated subset of packages from development
  branches; everything else resolves from ppg:staging:<V> via repository paths.
```

- [ ] **Step 2: Create `root/ppg/devel/18/project.yaml`** from `root/ppg/staging/18/project.yaml` with these exact transformations:
  1. `title:` → `Percona Distribution for PostgreSQL %!{PG_MAJOR_VERSION} — devel`; description states dev-branch purpose.
  2. In **every** repository's `paths:` list, prepend an entry pathing to staging (repository name mirrors the repo's own `name:`). Pattern, shown for RockyLinux_9 — apply to all ten repositories (RockyLinux_8, RockyLinux_9, RockyLinux_10, UBI_9, UBI_8, Debian_13, Ubuntu_22.04, Ubuntu_24.04, Ubuntu_26.04, openSUSE_Tumbleweed, openSUSE_Leap_16):

```yaml
  - name: RockyLinux_9
    paths:
      - subproject: ppg:staging:18
        repository: RockyLinux_9
      - subproject: ppg:common:deps
        repository: RockyLinux_9
      - subproject: common:deps:build
        repository: RockyLinux_9
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Fedora:EPEL:9
        repository: standard
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:9
        repository: standard
    archs: [x86_64, aarch64]
```

  3. Keep `debuginfo:` and `project-config:` verbatim (the Prefer/Ignore rules affect devel builds identically).
  4. **Delete the `qa:` section** (QA pipelines run against staging, not devel).

- [ ] **Step 3: Copy macros**

```bash
cp root/ppg/staging/18/macros.yaml root/ppg/devel/18/macros.yaml
```

- [ ] **Step 4: Seed the Class A packages** — for each of `percona-postgresql`, `percona-pg_tde`, `percona-pg_oidc_validator`:

```bash
cp -r root/ppg/staging/18/<pkg> root/ppg/devel/18/<pkg>
```

Then edit `root/ppg/devel/18/<pkg>/obs/_service`: change only the upstream `obs_scm` `<param name="revision">` to the dev branch. Determine each branch first and record it in the commit message:

```bash
git ls-remote --heads https://github.com/Percona-Lab/postgres.git | tail -20
git ls-remote --heads https://github.com/percona/pg_tde.git | tail -20
git ls-remote --heads https://github.com/Percona-Lab/pg_oidc_validator.git | tail -20
```

Defaults (D4 — confirm against the ls-remote output; if a listed default does not exist, pick the repo's active development branch and record the substitution): pg_tde → `main`; pg_oidc_validator → `main`; percona-postgresql → the current PG-18 development branch on Percona-Lab/postgres (e.g. the `REL_18_STABLE`-derived Percona branch shown by ls-remote). Leave `version` params and buildtime services untouched (same version scheme as staging, user decision).

- [ ] **Step 5: Create the Class B package**

```bash
mkdir -p root/ppg/devel/18/percona-ppg-server/obs
```

`root/ppg/devel/18/percona-ppg-server/obs/_link`:

```xml
<link project="${OBS_ROOTPRJ}:ppg:staging:18" package="percona-ppg-server" />
```

- [ ] **Step 6: Validate, commit, open PR 3** (after Task 5 gate passes)

```bash
venv/bin/python -m percona_obs -P dev project verify
venv/bin/python -m percona_obs -P dev sync push --dry-run ppg:devel:18
git add -A && git commit -s -m "Add ppg:devel:18 with seed packages (PG-2518 devel tier)

Class A dev branches: percona-postgresql=<branch>, pg_tde=<branch>, pg_oidc_validator=<branch>."
git push -u origin pg2518-devel-18
gh pr create --title "PG-2518: devel pilot — ppg:devel:18 with seed packages" --body "Devel tier pilot per spec §7 PR 3. Class A: percona-postgresql, percona-pg_tde, percona-pg_oidc_validator (dev branches). Class B: percona-ppg-server via _link.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

```json:metadata
{"files": ["root/ppg/devel/project.yaml", "root/ppg/devel/18/project.yaml", "root/ppg/devel/18/macros.yaml", "root/ppg/devel/18/percona-postgresql/", "root/ppg/devel/18/percona-pg_tde/", "root/ppg/devel/18/percona-pg_oidc_validator/", "root/ppg/devel/18/percona-ppg-server/obs/_link"], "verifyCommand": "venv/bin/python -m percona_obs -P dev project verify && venv/bin/python -m percona_obs -P dev sync push --dry-run ppg:devel:18", "acceptanceCriteria": ["project verify exits 0", "dry-run lists exactly 4 seed packages", "branches verified via git ls-remote and recorded", "staging path first in every devel repo", "PR 3 opened"], "modelTier": "standard"}
```

---

### Task 7: Devel verification gate

**Goal:** Prove the devel tier mechanics — Class A branch builds, Class B rebuild-against-devel, sync idempotence, and PR decision correctness.

**USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none (verification against live OBS and a throwaway PR)

**Acceptance Criteria:**
- [ ] PR 3 merged, `sync-main.yml` green; `build status ppg:devel:18` shows all four packages `✔ succeeded` on all devel repositories.
- [ ] Class A proof: the `percona-postgresql` build log (`osc buildlog … ppg:devel:18 percona-postgresql <repo> x86_64`) shows the obsinfo commit from the dev branch, not the release tag.
- [ ] Class B proof: the `percona-ppg-server` build log in devel shows it **installed the devel-built** `percona-postgresql*` packages (version/release string matching devel's build, not staging's) during dependency setup.
- [ ] Idempotence: a second `sync push ppg:devel:18 percona-ppg-server` prints `= files …` (no re-upload) — proves the Task 1 unexpanded comparison.
- [ ] PR decision check: a throwaway PR touching only `root/ppg/devel/18/percona-pg_tde/` shows in the PR comment: pg_tde promoted, `percona-ppg-server` promoted via dep-cascade, unrelated packages aggregated; the PR's devel `_link` points at the production staging project (Task 2 rewrite). Close the PR after checking.

**Verify:** `venv/bin/python -m percona_obs -P <main-profile> build status ppg:devel:18` → all `✔`

**Steps:**

- [ ] **Step 1: Merge PR 3, wait for sync-main, capture `build status ppg:devel:18`.**
- [ ] **Step 2: Capture Class A build log evidence (dev-branch commit in obsinfo).**
- [ ] **Step 3: Capture Class B build log evidence (devel-built dependency versions installed).**
- [ ] **Step 4: Run the idempotence check and capture the `=` output.**
- [ ] **Step 5: Open the throwaway PR, capture the decision table and the rewritten `_link` content from the PR OBS project, then close the PR.**

```json:metadata
{"files": [], "verifyCommand": "venv/bin/python -m percona_obs -P dev build status ppg:devel:18", "acceptanceCriteria": ["all 4 devel packages succeeded", "Class A buildlog shows dev-branch commit", "Class B buildlog shows devel-built deps installed", "second sync of link package prints =", "throwaway PR shows correct decisions and rewritten _link"], "userGate": true, "tags": ["user-gate"], "requireEvidenceTokens": [["staging", "tag"], ["devel", "branch", "dev-built"]], "modelTier": "standard"}
```

---

### Task 8: Migrate versions 14–17 (PR 4)

**Goal:** Move `root/ppg/{14..17}` to `staging/`, add their empty devel projects, update `releases/17`; open PR 4.

**Files:**
- Move: `root/ppg/{14,15,16,17}/` → `root/ppg/staging/{14,15,16,17}/`
- Create: `root/ppg/devel/{14,15,16,17}/project.yaml`
- Modify: `root/ppg/releases/17/release.yaml`, `root/ppg/releases/17/project.yaml`, any `ppg:1[4-7]`/`ppg/1[4-7]` references found by grep

**Acceptance Criteria:**
- [ ] `root/ppg/1[4-7]` gone; `root/ppg/staging/{14..17}` present; `root/ppg/devel/{14..17}/project.yaml` present.
- [ ] `grep -rn "ppg:1[4-7]\|ppg/1[4-7]" root/` returns only git-tag names in `releases/*/release.yaml` and distro-package names (e.g. `postgresql17-server` in project-config Prefer/Ignore lines — those are OS package names, NOT project refs; leave them).
- [ ] `venv/bin/python -m percona_obs -P dev project verify` exits 0.
- [ ] PR 4 opened (after Task 7 gate passes).

**Verify:** `venv/bin/python -m percona_obs -P dev project verify`

**Steps:**

- [ ] **Step 1: Branch and move all four versions**

```bash
git fetch origin && git checkout -b pg2518-remaining-versions origin/main
for v in 14 15 16 17; do git mv root/ppg/$v root/ppg/staging/$v; done
```

- [ ] **Step 2: For each version, create `root/ppg/devel/<V>/project.yaml`** using the Task 6 Step 2 recipe against that version's `root/ppg/staging/<V>/project.yaml` (prepend `subproject: ppg:staging:<V>` to every repository's paths; keep project-config; drop qa; devel title). No packages are seeded.

- [ ] **Step 3: Update references**

1. `root/ppg/releases/17/release.yaml` — `project: ppg:17` → `project: ppg:staging:17` (tag list untouched).
2. `root/ppg/releases/17/project.yaml` — description mention of `ppg:17` → `ppg:staging:17`.
3. `grep -rn "ppg:1[4-7]\|ppg/1[4-7]" root/` — update every remaining *project* reference (qa REPO lines, container REPOSITORY registry paths) the same way as Task 4 Step 3; leave git tags and OS package names (`postgresql17-server` etc.) alone.

- [ ] **Step 4: Validate, commit, open PR 4** (after Task 7 gate passes)

```bash
venv/bin/python -m percona_obs -P dev project verify
git add -A && git commit -s -m "Move ppg 14-17 to staging/ and add empty devel projects (PG-2518)"
git push -u origin pg2518-remaining-versions
gh pr create --title "PG-2518: migrate ppg 14-17 to three-tier layout" --body "Final migration per spec §7 PR 4. Full rebuild of versions 14-17 expected in CI.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

```json:metadata
{"files": ["root/ppg/staging/", "root/ppg/devel/", "root/ppg/releases/17/release.yaml", "root/ppg/releases/17/project.yaml"], "verifyCommand": "venv/bin/python -m percona_obs -P dev project verify", "acceptanceCriteria": ["versions 14-17 moved", "empty devel projects created", "grep shows only tags and OS package names", "project verify exits 0", "PR 4 opened"], "modelTier": "standard"}
```

---

### Task 9: Final verification gate and cleanup

**Goal:** Prove versions 14–17 are healthy under staging and retire the old OBS projects.

**USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none (verification against live OBS; manual OBS deletions at the end)

**Acceptance Criteria:**
- [ ] PR 4 merged, `sync-main.yml` green.
- [ ] For each V in 14–17: `build status ppg:staging:<V>` matches the pre-move baseline captured before merging PR 4 (capture both outputs per version).
- [ ] Empty devel projects exist on OBS (`osc meta prj <rootprj>:ppg:devel:<V>` succeeds) with the staging-first path lists.
- [ ] Old projects deleted only after the checks above: `osc -A <apiurl> rdelete -r -m "PG-2518: replaced by ppg:staging:<V>" <rootprj>:ppg:<V>` for V in 14–17 — destructive; run manually per version.

**Verify:** `venv/bin/python -m percona_obs -P <main-profile> build status ppg:staging:17` → all `✔` (repeat for 14–16)

**Steps:**

- [ ] **Step 1: Before merging PR 4, capture `build status ppg:<V>` baselines for V in 14–17.**
- [ ] **Step 2: Merge PR 4, wait for sync-main to reach terminal states.**
- [ ] **Step 3: Capture per-version `build status ppg:staging:<V>` and compare to baselines.**
- [ ] **Step 4: Confirm the four empty devel projects on OBS with staging-first paths.**
- [ ] **Step 5: Delete the four old projects (manual, destructive — user confirms each).**

```json:metadata
{"files": [], "verifyCommand": "venv/bin/python -m percona_obs -P dev build status ppg:staging:17", "acceptanceCriteria": ["sync-main green after PR 4", "per-version build status parity captured (14-17)", "empty devel projects exist with staging-first paths", "old ppg:14..17 deleted only after checks pass"], "userGate": true, "tags": ["user-gate"], "requireEvidenceTokens": [["baseline", "before", "ppg:1"], ["staging", "after"]], "modelTier": "standard"}
```

---

## Dependencies

Task 2 ← Task 1 (same file, sequential commits). Task 3 ← Task 2. Task 4 ← Task 3 (PR 1 must merge first). Task 5 ← Task 4. Task 6 ← Task 5 (gate). Task 7 ← Task 6. Task 8 ← Task 7 (gate). Task 9 ← Task 8.
