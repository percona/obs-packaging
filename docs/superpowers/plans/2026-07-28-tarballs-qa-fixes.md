# Tarballs QA-Feedback Fixes Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development or superpowers-extended-cc:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fix the 8 QA findings against the pr-2 tarballs: compiled `/tmp` socket defaults (binary patch), `/opt`-prefixed perl/tcl/python runtimes replacing the fragile env-var wrappers, `.pyc` cleanup, haproxy component, and documentation of the perl-version constraint.

**Context — QA findings and root causes:**
1. **initdb wrapper misses positional `initdb DATADIR`** — band-aid on the compiled `DEFAULT_PGSOCKET_DIR=/run/postgresql`.
2. **pgbench/pg_dump/pg_isready can't connect** — only psql was wrapped with `PGHOST=/tmp`; libpq's compiled default is `/run/postgresql`.
3. **plperl broken** (`Can't locate strict.pm`, RHEL @INC) — PLs depend on the `postgres` wrapper exporting `PERL5LIB`; any server start bypassing the wrapper breaks it.
4. **pltcl broken** (`could not initialize Tcl interpreter`) — same class: compiled tcl paths are `/usr/{lib64,share}/tcl8.6`, wrapper exports `TCL_LIBRARY`.
5. **plpython3u backend crash** — same class: needs the wrapper's `PYTHONHOME`.
6. **3838 stray `.pyc`/`__pycache__` files** under percona-python3.
7. **perl 5.26 vs official 5.38** — inherent: `plperl.so` is ABI-tied to the distro libperl the PG RPM was built against (5.26.3 EL8 / 5.32.1 EL9).
8. **percona-haproxy missing** — excluded as an early non-goal; staging has the package.

**User decisions (2026-07-28):**
- Items 1+2: **binary-patch** the C string `DEFAULT_PGSOCKET_DIR` (`/run/postgresql` → `/tmp`, same-length NUL-padded) in every bundled ELF; DELETE the initdb wrapper and the psql `PGHOST` hack.
- Items 3–5: **from-source `/opt`-prefixed runtime packages** (perl matching the distro version per base, tcl 8.6, python 3.12) in `ppg:common:deps`, RL8+RL9 only, distinct names, never published. Compiled-in `/opt` paths make all three PLs work with ZERO environment variables — the official tarball's mechanism. The `postgres` env wrapper is deleted.
- Item 7: **accept + document** distro-matched perl versions (5.26.3 ssl1.1 / 5.32.1 ssl3). Full 5.38 parity would require building the shipped PG RPM against a custom perl — out of scope, product decision.
- Item 8: **add** the percona-haproxy component.

---

### Task 15: compiled /tmp socket defaults via ELF string patch (items 1+2)

**Goal:** Every bundled PG binary and libpq copy defaults to a `/tmp` unix socket — server, initdb-generated conf, and all clients — with no wrappers.

**Files:**
- Modify: `root/ppg/staging/17/tarballs/percona-postgresql-tarball/obs/build-tarball.sh`

**Changes:**
- New section (after all component staging, before the verification gate): sweep every regular ELF file under `/opt` and replace each occurrence of the exact byte string `/run/postgresql\0` (16 bytes) with `/tmp\0` + 11 NUL padding bytes (identical length — safe for C string constants, no offset changes). Implement with a small python3 helper (python3.12 is in the chroot); count and log patched files. Expected hits: `postgres`, `initdb`, `libpq.so.5.*` (every copy, incl. the one under percona-python3 for psycopg2), possibly `pg_ctl`/`ecpg`-family; help-text occurrences are fine to patch too.
- DELETE the initdb wrapper block (restore `initdb` as the real binary — no `.bin` rename). This also removes QA item 1's positional-arg bug by removing the wrapper.
- DELETE the `export PGHOST=...` line from the psql wrapper (readline logic stays).
- Gate addition (section 15): assert ZERO ELF files under `/opt` still contain the byte string `/run/postgresql` — loud FATAL otherwise. (Text files are out of scope; the shipped `postgresql.conf.sample` already carries upstream's `'/tmp'` text.)

**Acceptance Criteria:**
- [ ] Container e2e (EL9 harness): `initdb /tmp/data` **positional form, no -D** → generated conf's commented default reads `'/tmp'`; server socket lands in `/tmp`
- [ ] `pgbench -i`, `pg_dump -s postgres`, `pg_isready` all connect with NO `-h`/`PGHOST`/env (QA item 2 regression)
- [ ] plain `psql -d postgres -c '\conninfo'` → "via socket in /tmp"
- [ ] gate FATAL demonstrated on an unpatched tree (negative control)
- [ ] shellcheck severity=error + bash -n clean

**Verify:** container run → gate green incl. the new string assertion; `strings` on extracted postgres/libpq → no `/run/postgresql`.

### Task 16: /opt-prefixed runtime packages — perl, tcl, python (items 3–5 foundation)

**Goal:** Three from-source packages in `ppg:common:deps` installing complete runtimes under `/opt/percona-{perl,tcl,python3}` with compiled-in `/opt` paths, so `plperl.so`/`pltcl.so`/`plpython3.so` (RPM-built, unmodified) resolve their interpreter + stdlib without any environment variables.

**Files:**
- Create: `root/ppg/common/deps/percona-perl/{obs/_service,rpm/*.spec,package.yaml}`
- Create: `root/ppg/common/deps/percona-tcl/{...}`
- Create: `root/ppg/common/deps/percona-python3/{...}`

**Design constraints (load-bearing):**
- **perl:** version MUST equal the distro perl per base — 5.26.3 (RL8) / 5.32.1 (RL9) — because `plperl.so` links the distro libperl ABI. Both upstream tarballs as Sources (download_url); spec `%if 0%{?rhel}` selects. Configure with **Rocky's own Configure flags minus path flags** (copy from the Rocky perl SRPM spec: usethreads, useshrplib, 64bitint, etc. — ABI must match what plperl.so was compiled against), overriding `-Dprefix=/opt/percona-perl -Dprivlib=/opt/percona-perl/lib/%{pver} -Darchlib=/opt/percona-perl/lib/%{pver}` (flat layout → `libperl.so` lands at `/opt/percona-perl/lib/<ver>/CORE/`, exactly where plperl.so's existing RUNPATH points).
- **tcl:** one 8.6.x version (soname `libtcl8.6.so`, ABI-stable within 8.6; implementer picks the newest distro-shipped 8.6 minor and verifies pltcl loads on BOTH bases). `--prefix=/opt/percona-tcl` → `lib/libtcl8.6.so` + `lib/tcl8.6/` stdlib, matching pltcl.so's RUNPATH `/opt/percona-tcl/lib`.
- **python:** 3.12.x upstream, `--prefix=/opt/percona-python3 --enable-shared` → `lib/libpython3.12.so.1.0` (plpython3.so RUNPATH covers it), full stdlib at `lib/python3.12/`. Embedding ABI within 3.12 is stable, and the staging `python3.12-*` site-packages (psycopg2 etc., cp312) remain compatible.
- All three: RL8+RL9 only via `package.yaml` (disable the other repos, atlas-style); distinct names — they install into `/opt`, no shadowing of system packages; `publish: false` is project-wide in common:deps; PERCONA-commented specs + correct changelog day-of-week.

**Acceptance Criteria:**
- [ ] Each package builds in rocky8 AND rocky9 containers (or OBS PR); readelf: our libs carry no surprises; `strings libperl.so | grep /opt/percona-perl` shows compiled @INC
- [ ] **The QA repro passes with NO env vars**: in a container with the runtime installed + percona-postgresql17, from a clean env: `perl -e 'use strict'` via `/opt/percona-perl/bin/perl`; `/opt/percona-python3/bin/python3 -c 'import ssl'`; `echo 'puts ok' | /opt/percona-tcl/bin/tclsh8.6`; AND `plperl` `CREATE FUNCTION ... use strict` + pltcl + plpython3u functions succeed with the server started via **bare `postgres -D`** (no wrapper, no env)
- [ ] isv dry-runs clean (STANDING RULE: -P isv never without --dry-run)

**Verify:** the bare-`postgres` PL test — the exact class QA hit — green on both bases.

### Task 17: rewrite runtime staging in build-tarball.sh + haproxy + .pyc strip (items 3–6, 8)

**Goal:** Tarball consumes the new /opt runtime packages; env-var wrappers gone; haproxy component added; no bytecode litter.

**Files:**
- Modify: `obs/simpleimage` (BuildRequires: + percona-{perl,tcl,python3}, + percona-haproxy; drop distro `perl`/`tcl`/`python3.12` runtime BuildRequires that only served the flatten logic — KEEP the `python3.12-*` dep packages for patroni's site-packages and keep `-devel` only if the gate/tools need it)
- Modify: `obs/build-tarball.sh`

**Changes:**
- Runtime staging sections (7–12): the RPMs already install into `/opt/percona-{perl,tcl,python3}` in the buildroot — delete the flatten-from-system logic; keep only: patroni site-packages copy into `/opt/percona-python3/lib/python3.12/site-packages`, shebang rewrites (patroni bins, pip/pgbadger/perl-utils → `/opt/percona-*/bin/...`), and generic `bundle_deps`/`patch_rpath` over the three prefixes.
- DELETE the `postgres` env wrapper (`postgres.real` rename undone; `PERL5LIB`/`TCL_LIBRARY`/`PYTHONHOME` exports gone). DELETE the python3 PYTHONHOME wrapper (our python binary has the right compiled prefix). Simplify section-14 RPATHs accordingly (PL `.so` RUNPATHs keep their `/opt/...` entries; the postgres binary needs only `$ORIGIN/../lib`).
- `.pyc` strip: `find /opt/percona-python3 \( -name __pycache__ -o -name '*.pyc' -o -name '*.pyo' \) ...` remove; gate asserts count 0 (item 6). Check whether the official tarball ships any and note.
- haproxy: stage from the `percona-haproxy` RPM into `/opt/percona-haproxy/` mirroring the official component layout (read it from the official tarball in the scratchpad: bin/etc/lib/sbin/share); bundle_deps + patch_rpath; component-count checks go 10 → 11 (item 8).
- Update smoke commands: plperl/pltcl/plpython checks now run WITHOUT env manipulation; add `/opt/percona-haproxy/sbin/haproxy -v` (or bin — per layout).

**Acceptance Criteria:**
- [ ] Full container runs green on BOTH bases (EL8 + EL9 harnesses; re-provision with the new BuildRequires) — both audits + new gates (no `/run/postgresql` strings, no .pyc, 11 components)
- [ ] Artifact structure-diff vs official: haproxy divergence GONE; remaining diffs enumerated
- [ ] pytest/pyright/black green; isv dry-run clean

**Verify:** container gate output + `tar -tzf | awk -F/ '{print $1}' | sort -u` → eleven `percona-*` dirs.

### Task 18: docs, spec, release notes (item 7 + all changes)

**Files:** `root/README.md`, `docs/superpowers/specs/2026-07-20-obs-simpleimage-tarballs-design.md`

**Content:** compiled `/tmp` socket defaults (no `/run/postgresql`, no PGHOST needed for ANY client); PLs work with zero env vars; runtimes are /opt-prefixed from-source builds (versions: perl 5.26.3/5.32.1 per variant — documented constraint with the plperl-ABI rationale, official ships 5.38 via a different build model; tcl 8.6.x; python 3.12); haproxy included; host prerequisites shrink to: `postgres` user, `libreadline8`, `tzdata`, `/opt` copy step for the runtimes (unchanged, matches official docs).

### Task 19: acceptance battery round 5 (USER GATE)

> **USER-ORDERED GATE — NON-SKIPPABLE.** Captured output for every criterion.

After the user pushes and the PR project rebuilds: fetch both artifacts and run on debian:11 (ssl1.1) + ubuntu:22.04 + ubuntu:24.04 (ssl3), with the QA flows as explicit regression targets:
- [ ] **positional `initdb /path`** (no -D) → socket in `/tmp`
- [ ] **pgbench, pg_dump, pg_isready** connect with zero env/flags
- [ ] server started via **bare `bin/postgres -D`** (maximum wrapper bypass) → plperl function with `use strict`, pltclu function, plpython3u `import sqlite3, ssl` — all work
- [ ] zero `.pyc`/`__pycache__` in the artifact; eleven components incl. haproxy (`haproxy -v` runs)
- [ ] `perl -V` from the bundled perl shows `/opt/percona-perl` @INC; versions per variant documented
- [ ] all carried-over regressions (pgcrypto digest, pg_tde, patronictl/patroni_aws, psql on debian:11, OPENSSL sweeps)

---

## Execution notes
- Order: Task 15 ∥ Task 16 (disjoint files) → Task 17 (needs both) → Task 18 → Task 19 (gate).
- Standing rules: `git commit -s`, no AI attribution, never push/create PRs (user does), `-P isv` writes only with `--dry-run`.
- The perl ABI-match constraint (Task 16) is the highest-risk item: if plperl.so refuses our libperl (config mismatch), iterate on Configure flags against Rocky's spec — do NOT ship a mismatched libperl; escalate if parity can't be reached.
