# PPG 15 Binary Tarballs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add binary-tarball (OBS simpleimage) builds for Percona PostgreSQL 15, following the shared-packaging recipe used for PG 16/17/18, including the two deltas PG 15 forces: a macro-driven percona-psql source (PG 15 has no Percona fork) and the EL9 python3.12 plpython fix.

**Architecture:** The tarball packaging is shared across majors via `root/ppg/staging/_shared/` + relative symlinks; each major contributes only `staging/<N>/tarballs/project.yaml`, two symlinks, and macros in `staging/<N>/macros.yaml`. PG 15's PostgreSQL source is upstream `postgres/postgres` (tag `REL_15_19`) — there is no `percona/postgres` `PSP-15.*` tag and no `PERCONA_PG_PATCH_VERSION` for 15 — so the shared `percona-psql` `_service` must reference the source repo/tag through per-major macros instead of hardcoding the Percona-fork scheme.

**Tech Stack:** OBS (Open Build Service) project/package YAML + RPM specs + OBS `_service` files; the `percona-obs` sync tool (Python, `percona_obs/`); `%!{VAR}` macros rendered per linking major from `macros.yaml` chains.

**Spec:** inline — the Context section below is the spec; there is no separate document.

## Context (read this first)

- **Working directory:** `/home/rdias/Work/percona-obs-packaging/.claude/worktrees/tarballs-simpleimage` (a git worktree). Branch `tarballs-pg15` is already created from `percona/main` and checked out, tree clean. Run ALL commands from this directory. Do NOT cd to the main checkout — but note the Python venv lives ONLY there: use `/home/rdias/Work/percona-obs-packaging/venv/bin/python` (call it `$VPY` below).
- **How sharing works:** `staging/_shared/<pkg>/` holds the one copy; `staging/<N>/tarballs/<pkg>` is a relative symlink (`../../_shared/<pkg>`). `%!{VAR}` macros in shared files are rendered from the SYMLINK's directory chain, i.e. `staging/<N>/macros.yaml` (plus ancestors). Any macro a shared file references must be defined for EVERY major that links it.
- **Why the `_service` change:** `staging/_shared/percona-psql/obs/_service` currently hardcodes `https://github.com/percona/postgres.git` + revision `PSP-%!{PG_VERSION}.%!{PERCONA_PG_PATCH_VERSION}`. PG 16/17/18 servers build from those PSP tags. PG 15's server (`root/ppg/staging/15/percona-postgresql/obs/_service`) builds from `https://github.com/postgres/postgres.git` revision `REL_%!{PG_MAJOR_VERSION}_%!{PG_MINOR_VERSION}` — and percona-psql's contract (its spec header) is "the very same PostgreSQL source as the server". Verified facts: `refs/tags/PSP-16.15.1`, `PSP-17.11.1`, `PSP-18.6.1` exist in percona/postgres; NO `PSP-15.*` exists anywhere; `refs/tags/REL_15_19` exists in postgres/postgres; `staging/15/macros.yaml` has `PG_MINOR_VERSION: 19` and NO `PERCONA_PG_PATCH_VERSION`.
- **Why the spec change:** `staging/15/percona-postgresql/rpm/percona-postgresql.spec` builds plpython3 with plain `python3-devel` and `export PYTHON=/usr/bin/python3` — on EL9 that is python 3.9, while the tarball bundles the python 3.12 stdlib in `/opt/percona-python3`. A 3.9-embedded plpython3.so fatals at backend start on any host without `/usr/lib64/python3.9` ("Fatal Python error: init_fs_encoding ... No module named 'encodings'") — this exact failure shipped in the first PG 18 tarball and was fixed for 18 and 16 by porting the 17 spec's parallel-python block. The shared `build-tarball.sh` now carries a gate (plpython3.so's libpython NEEDED soname must exist in `/opt/percona-python3/lib`) that would fail the tarball build if this spec fix is missing — so Task 2 is a prerequisite for Task 3's builds ever going green.
- **Component set for 15** (verified by diffing `staging/15` vs `staging/16` package dirs): identical except 15 lacks `extras/`, `tde/`, the two aggregates, and `tarballs/` — all expected. 15 HAS `percona-pg-telemetry` (exists for majors 14–17), has NO `percona-pg_tde` and NO `percona-pg_oidc_validator`. Ruling from the user: nothing from any `:tde:` subproject may ever enter a tarball.
- **What was verified already (do not re-verify):** PG 15.19 macros present; `staging/15/project.yaml` has RockyLinux_8/9/9.6/10 repos; `REL_15_19` tag exists.

## Global Constraints

- Commit with `git commit -s`. Do NOT add `Co-Authored-By` lines of any kind. No Claude attribution anywhere.
- NEVER `git push`, never `gh pr create`, never add labels — after the last task, STOP and report; the user pushes and opens the PR.
- Shared files (`root/ppg/staging/_shared/**`) must not gain any literal major number; everything major-specific goes through `%!{VAR}` macros.
- The `_service` change must render byte-identically to today's values for majors 16/17/18 (`PSP-16.15.1`, `PSP-17.11.1`, `PSP-18.6.1`) — a changed render would trigger pointless prod rebuilds. Task 1's verify step checks exactly this.
- `macros.yaml` files are NOT general YAML: each line must be exactly `- KEY: value` (a custom line scanner parses them; values may contain `%!{...}`). Append lines at the end of the file; never reformat existing lines.
- If anything under `percona_obs/` is changed (none is planned): run `/home/rdias/Work/percona-obs-packaging/venv/bin/black percona_obs/` then `.../venv/bin/pyright` — both must pass.
- The full test suite must pass at the end: `/home/rdias/Work/percona-obs-packaging/venv/bin/python -m pytest tests/ -q`.

**User decisions (already made):**
- "Ok" to: macro-driven percona-psql source URL/revision; PG 15 tarball ships `percona-pg-telemetry15` only (no pg_tde — PG 15 has none; no oidc — that is ≥ 18); include the python3.12 spec fix; include jmespath/s3transfer aggregates for staging:15.
- Earlier ruling, still binding: no package from a `:tde:` subproject may enter any tarball.
- Plan is written for execution by another model/session.

---

### Task 1: Macro-driven percona-psql source

**Goal:** Replace the hardcoded percona-fork URL/tag in the shared percona-psql `_service` with `%!{PG_SOURCE_GIT_URL}` / `%!{PG_SOURCE_GIT_REVISION}` macros, defined for majors 16/17/18 so their renders are byte-identical to today.

**Files:**
- Modify: `root/ppg/staging/_shared/percona-psql/obs/_service`
- Modify: `root/ppg/staging/16/macros.yaml` (append 2 lines)
- Modify: `root/ppg/staging/17/macros.yaml` (append 2 lines)
- Modify: `root/ppg/staging/18/macros.yaml` (append 2 lines)

**Acceptance Criteria:**
- [ ] `_service` contains no literal `percona/postgres.git` and no literal `PSP-`
- [ ] Rendered revision for 16 = `PSP-16.15.1`, 17 = `PSP-17.11.1`, 18 = `PSP-18.6.1` (unchanged from today)
- [ ] Rendered url for 16/17/18 = `https://github.com/percona/postgres.git`

**Verify:** the render script in Step 3 prints exactly the three `PSP-…` values above → then commit.

**Steps:**

- [ ] **Step 1: Edit the `_service`**

In `root/ppg/staging/_shared/percona-psql/obs/_service`, replace exactly:

```xml
    <param name="url">https://github.com/percona/postgres.git</param>
    <param name="scm">git</param>
    <param name="revision">PSP-%!{PG_VERSION}.%!{PERCONA_PG_PATCH_VERSION}</param>
```

with:

```xml
    <param name="url">%!{PG_SOURCE_GIT_URL}</param>
    <param name="scm">git</param>
    <param name="revision">%!{PG_SOURCE_GIT_REVISION}</param>
```

(The `version` and `set_version` params keep `%!{PG_VERSION}` — do not touch them.)

- [ ] **Step 2: Append the macros for 16, 17 and 18**

Append these two lines (exactly, including the leading `- `) to the END of each of `root/ppg/staging/16/macros.yaml`, `root/ppg/staging/17/macros.yaml`, `root/ppg/staging/18/macros.yaml`:

```yaml
- PG_SOURCE_GIT_URL: https://github.com/percona/postgres.git
- PG_SOURCE_GIT_REVISION: PSP-%!{PG_VERSION}.%!{PERCONA_PG_PATCH_VERSION}
```

- [ ] **Step 3: Verify the renders are unchanged**

Run from the worktree root:

```bash
VPY=/home/rdias/Work/percona-obs-packaging/venv/bin/python
PYTHONPATH=. $VPY - <<'EOF'
from pathlib import Path
from percona_obs.common import load_macros, apply_macro_substitution
expect = {'16': 'PSP-16.15.1', '17': 'PSP-17.11.1', '18': 'PSP-18.6.1'}
for major, want in expect.items():
    link = Path.cwd() / f'root/ppg/staging/{major}/tarballs/percona-psql'
    m = load_macros(link)
    got = apply_macro_substitution('%!{PG_SOURCE_GIT_REVISION}', m)
    url = apply_macro_substitution('%!{PG_SOURCE_GIT_URL}', m)
    assert got == want, (major, got)
    assert url == 'https://github.com/percona/postgres.git', (major, url)
    print(major, url, got, 'OK')
EOF
```

Expected: three `... OK` lines. IMPORTANT: build the link path lexically as above — never `Path.resolve()` it (resolve follows the symlink into `_shared/` and loses the major's macro chain).

- [ ] **Step 4: Commit**

```bash
git add root/ppg/staging/_shared/percona-psql/obs/_service root/ppg/staging/16/macros.yaml root/ppg/staging/17/macros.yaml root/ppg/staging/18/macros.yaml
git commit -s -m "staging/_shared: percona-psql source via per-major macros

PG 15 has no Percona fork: its server builds from upstream
postgres/postgres at REL_15_19, and no PSP-15.* tag or
PERCONA_PG_PATCH_VERSION exists. percona-psql must build from the very
same source as each major's server, so the shared _service's url and
revision become %!{PG_SOURCE_GIT_URL} / %!{PG_SOURCE_GIT_REVISION},
defined per major. For 16/17/18 the definitions reproduce today's
values byte-for-byte (PSP-16.15.1 / PSP-17.11.1 / PSP-18.6.1, render
verified), so nothing rebuilds; 15 defines the upstream repo and
REL_M_m scheme in the next tasks."
```

---

### Task 2: staging:15 — build plpython3 against python3.12 on EL8/EL9

**Goal:** Port the 17 spec's parallel-python block into the 15 spec so plpython3.so embeds python 3.12 (matching the tarball's bundled `/opt/percona-python3`), not EL9's system 3.9.

**Files:**
- Modify: `root/ppg/staging/15/percona-postgresql/rpm/percona-postgresql.spec` (two hunks: BuildRequires ~line 239, `%build` export ~line 720)

**Acceptance Criteria:**
- [ ] Spec contains `BuildRequires:  python3.12-devel` guarded by `%if 0%{?rhel} >= 8 && 0%{?rhel} < 10`
- [ ] Spec contains `export PYTHON=%{_bindir}/python3.12` under the same guard, and NO remaining `export PYTHON=/usr/bin/python3` line
- [ ] Non-RHEL / EL10 paths keep plain `python3-devel` / no forced PYTHON

**Verify:** `grep -n 'python3.12-devel\|export PYTHON' root/ppg/staging/15/percona-postgresql/rpm/percona-postgresql.spec` shows exactly the two new guarded spots and no `/usr/bin/python3` export → commit.

**Steps:**

- [ ] **Step 1: Replace the BuildRequires hunk**

In the spec, replace exactly (tab after `BuildRequires:` — copy carefully; the file uses a literal TAB there):

```spec
%if %plpython3
BuildRequires:	python3-devel
%endif
```

with:

```spec
%if %plpython3
# PERCONA: build plpython3 against the parallel python3.12 stack on EL8 AND
# EL9 so the embedded interpreter matches the percona python3.12-* runtime
# packages (and the python 3.12 stdlib bundled in the binary tarball).
# EL10 is left on the default python3-devel, which already IS 3.12 there.
# The matching PYTHON= export lives next to the configure call in %%build.
# (Ported from the staging:17 spec — a system-python plpython3 fatals on
# any host without /usr/lib64/python3.9: "No module named 'encodings'",
# the failure the first PG 18 tarball hit on every Debian-family QA host.)
%if 0%{?rhel} >= 8 && 0%{?rhel} < 10
BuildRequires:  python3.12-devel
%else
BuildRequires:	python3-devel
%endif
%endif
```

- [ ] **Step 2: Replace the export hunk**

In the same spec's `%build`, replace exactly:

```spec
%if %plpython3
export PYTHON=/usr/bin/python3
%endif
```

with:

```spec
%if %plpython3
# PERCONA: steer --with-python explicitly at the 3.12 interpreter on EL8/EL9
# (same bounds as the python3.12-devel BuildRequires above). Without this,
# configure probes plain "python3", which on EL9 is always 3.9 —
# plpython3.so would link libpython3.9 while the tarball bundles the 3.12
# stdlib, and the embedded interpreter then fatals at backend start
# ("No module named 'encodings'").
%if 0%{?rhel} >= 8 && 0%{?rhel} < 10
export PYTHON=%{_bindir}/python3.12
%else
export PYTHON=/usr/bin/python3
%endif
%endif
```

(Note: unlike 16/18, the 15 spec already had an `export PYTHON` block, so the replacement keeps a plain-python3 fallback for non-EL8/9 targets, preserving today's behavior there.)

- [ ] **Step 3: Verify and commit**

```bash
grep -n 'python3.12-devel\|export PYTHON' root/ppg/staging/15/percona-postgresql/rpm/percona-postgresql.spec
```

Expected: one `python3.12-devel` line, one `export PYTHON=%{_bindir}/python3.12`, one fallback `export PYTHON=/usr/bin/python3` inside the `%else` branch only.

```bash
git add root/ppg/staging/15/percona-postgresql/rpm/percona-postgresql.spec
git commit -s -m "staging:15: build plpython3 against python3.12 on EL8/EL9

Same fix as staging:16/18: with plain python3-devel and
export PYTHON=/usr/bin/python3, EL9 builds embed the system python 3.9
in plpython3.so while the binary tarball bundles the 3.12 stdlib, and
the embedded interpreter fatals on any host without /usr/lib64/python3.9
('No module named encodings' — proven on Debian-family QA hosts by the
first PG 18 tarball). Port the 17 spec's parallel-python block; the
tarball build's libpython gate refuses a mismatched artifact either way.
Non-EL8/9 targets keep the previous plain-python3 export."
```

---

### Task 3: staging:15 tarballs subproject, macros and aggregates

**Goal:** Create the PG 15 tarballs subproject (project.yaml + two shared symlinks), define 15's tarball macros (extras + source repo/tag), and add the python3-jmespath/s3transfer aggregates to staging:15.

**Files:**
- Create: `root/ppg/staging/15/tarballs/project.yaml` (verbatim copy of `root/ppg/staging/17/tarballs/project.yaml`)
- Create: symlink `root/ppg/staging/15/tarballs/percona-psql` → `../../_shared/percona-psql`
- Create: symlink `root/ppg/staging/15/tarballs/percona-postgresql-tarball` → `../../_shared/percona-postgresql-tarball`
- Modify: `root/ppg/staging/15/macros.yaml` (append 3 lines)
- Create: `root/ppg/staging/15/python3-jmespath/obs/_aggregate` (copy of the 17 one)
- Create: `root/ppg/staging/15/python3-s3transfer/obs/_aggregate` (copy of the 17 one)

**Acceptance Criteria:**
- [ ] `find_packages` discovers both packages under `...:staging:15:tarballs` and both aggregates under `...:staging:15`
- [ ] 15 renders: extras = `percona-pg-telemetry15`, psql url = `https://github.com/postgres/postgres.git`, psql revision = `REL_15_19`
- [ ] `root/ppg/staging/15/tarballs/project.yaml` contains no literal `1[678]` major and no `tde` reference (`grep -cE 'tde|16|17|18'` → 0)
- [ ] Full pytest suite passes

**Verify:** the script in Step 4 prints the three expected renders and the discovery lines; `pytest tests/ -q` all green → commit.

**Steps:**

- [ ] **Step 1: Create the subproject**

```bash
mkdir root/ppg/staging/15/tarballs
cp root/ppg/staging/17/tarballs/project.yaml root/ppg/staging/15/tarballs/project.yaml
ln -s ../../_shared/percona-psql root/ppg/staging/15/tarballs/percona-psql
ln -s ../../_shared/percona-postgresql-tarball root/ppg/staging/15/tarballs/percona-postgresql-tarball
grep -cE 'tde' root/ppg/staging/15/tarballs/project.yaml   # expect 0
```

(The project.yaml is fully `%!{PG_MAJOR_VERSION}`-parameterized; the copy is deliberately byte-identical across majors.)

- [ ] **Step 2: Append the 15 macros**

Append exactly these three lines to the END of `root/ppg/staging/15/macros.yaml`:

```yaml
- TARBALL_PG_EXTRA_COMPONENTS: percona-pg-telemetry%!{PG_MAJOR_VERSION}
- PG_SOURCE_GIT_URL: https://github.com/postgres/postgres.git
- PG_SOURCE_GIT_REVISION: REL_%!{PG_MAJOR_VERSION}_%!{PG_MINOR_VERSION}
```

(`TARBALL_PG_EXTRA_COMPONENTS` deliberately lists ONLY pg-telemetry: PG 15 has no pg_tde — its TDE is a separate edition whose packages must never enter the tarball — and pg_oidc_validator is ≥ 18 only. The revision macro reproduces the 15 server `_service`'s own pin, `REL_15_19`.)

- [ ] **Step 3: Add the aggregates**

```bash
mkdir -p root/ppg/staging/15/python3-jmespath/obs root/ppg/staging/15/python3-s3transfer/obs
cp root/ppg/staging/17/python3-jmespath/obs/_aggregate root/ppg/staging/15/python3-jmespath/obs/_aggregate
cp root/ppg/staging/17/python3-s3transfer/obs/_aggregate root/ppg/staging/15/python3-s3transfer/obs/_aggregate
```

(Each file is a 5-line `<aggregatelist>` pulling the package's binaries from `${OBS_ROOTPRJ}:ppg:common:deps` — they make the published staging:15 repos self-contained for percona-patroni-aws's boto3 dependency chain.)

- [ ] **Step 4: Verify renders, discovery, tests**

```bash
VPY=/home/rdias/Work/percona-obs-packaging/venv/bin/python
PYTHONPATH=. $VPY - <<'EOF'
from pathlib import Path
from percona_obs.common import find_packages, load_macros, apply_macro_substitution
found = list(find_packages(Path.cwd()/'root/ppg/staging/15', 'X:15'))
tb = sorted(p.name for proj, p in found if 'tarballs' in proj)
assert tb == ['percona-postgresql-tarball', 'percona-psql'], tb
ag = sorted(p.name for _, p in found if p.name.startswith('python3-'))
assert 'python3-jmespath' in ag and 'python3-s3transfer' in ag, ag
link = Path.cwd()/'root/ppg/staging/15/tarballs/percona-postgresql-tarball'
m = load_macros(link)
assert apply_macro_substitution('%!{TARBALL_PG_EXTRA_COMPONENTS}', m) == 'percona-pg-telemetry15'
assert apply_macro_substitution('%!{PG_SOURCE_GIT_URL}', m) == 'https://github.com/postgres/postgres.git'
assert apply_macro_substitution('%!{PG_SOURCE_GIT_REVISION}', m) == 'REL_15_19'
print('15 renders + discovery OK')
EOF
$VPY -c "import yaml; yaml.safe_load(open('root/ppg/staging/15/tarballs/project.yaml')); print('yaml OK')"
$VPY -m pytest tests/ -q | tail -1
```

Expected: `15 renders + discovery OK`, `yaml OK`, all tests passing.

- [ ] **Step 5: Commit**

```bash
git add root/ppg/staging/15
git commit -s -m "staging:15: add the binary tarballs subproject

PG 15 tarballs via the shared packaging: tarballs/project.yaml copied
verbatim from 17, two symlinks into staging/_shared, and three macros —
TARBALL_PG_EXTRA_COMPONENTS=percona-pg-telemetry15 (no pg_tde: PG 15 has
none and :tde: edition packages never enter a tarball; no oidc: >= 18
only) plus PG_SOURCE_GIT_URL/REVISION pointing percona-psql at upstream
postgres/postgres REL_15_19, the very tag the 15 server builds from
(PG 15 predates the Percona fork and its PSP-* tags).

Also aggregate python3-jmespath and python3-s3transfer into staging:15,
as in 16/17/18, so percona-patroni-aws is installable from the published
ppg:staging:15 repos alone."
```

---

## After the last task (hand back to the user — do NOT do these)

- Pushing branch `tarballs-pg15` to the `percona` remote, opening the PR (base `main`), adding labels (`RockyLinux_8`, `RockyLinux_9`, `RockyLinux_9.6`, `keep-pr-build`, `no-dep-cascade`; the user alone decides about `obs-sync`) — all require the user's explicit go-ahead.
- First-build watch items to mention in the report: percona-psql building from the upstream `REL_15_19` tag on all six helper repo/arch rows; the ssl chroots resolving `percona-pg-telemetry15`; the section-15 SSL gates and the libpython gate on the 15 artifacts; 15's psql reporting plain `psql (PostgreSQL) 15.19` (correct — no Percona suffix exists for 15).
