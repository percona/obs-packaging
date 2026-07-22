# Tarballs SSL Portability Plan (post-acceptance round)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development or superpowers-extended-cc:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the OBS tarballs genuinely portable per their SSL-variant promises, based on the PR-145 acceptance-gate findings: two variants (ssl1.1 on EL8, ssl3 on EL9), a one-macro PostgreSQL patch, rebuilt krb5/libssh for EL8, and the cross-variant script fixes.

**Context (findings driving this plan):**
- The acceptance gate failed 2 of 3 variants on foreign hosts. ssl3 (Ubuntu debs) is unfixable — PGDG deb layout is non-relocatable (`SHAREDIR=/usr/share/postgresql/17` hard-compiled; verified identical in PGDG's own debs). ssl1.1 (EL8) fails on stock 1.1 hosts because two bundled RH-prebuilt libs (`libk5crypto`, `libssh`) need the RH-only `OPENSSL_1_1_1b` symbol node.
- All PG-side EL8/EL9 binaries carry only stock OpenSSL nodes EXCEPT `pgcrypto.so` on ≥3.4 build bases: OpenSSL 3.4's headers remap the `EVP_MD_CTX_size()` macro to `EVP_MD_CTX_get_size_ex@OPENSSL_3.4.0`. One-macro patch → EL9-built ssl3 covers ALL OpenSSL 3.x hosts (glibc floor 2.34: includes Ubuntu 22.04/24.04, Debian 12).
- Official-tarball reference behaviors to replicate: krb5 with builtin crypto (no libcrypto dep); psql readline wrapper; no Net::SSLeay (done).
- Cross-variant acceptance findings: `postgres` wrapper must export `PYTHONHOME` (backend segfault in plpython3u otherwise); readline wrapper misses Debian multiarch path; `libunistring`/`libnghttp2`/`libidn2` must be bundled (sonames not universal); `/run/postgresql` socket dir is a host prerequisite (docs).

**User decisions (already made):**
- ssl3 reverts to Rocky 9 RPMs + pgcrypto macro patch; strict `OPENSSL_3.0.*` gate stays.
- ssl3.5 is DROPPED (redundant: patched ssl3 serves every 3.x host with a lower glibc floor).
- Deb builder (`build-tarball-deb.sh` + dispatcher + deb BuildRequires branch) is REMOVED (history preserves it; rationale recorded in spec).
- ssl1.1 portability via rebuilt packages: krb5 with builtin crypto; libssh built against stock OpenSSL 1.1 headers (requires a build-only, UNPUBLISHED percona openssl-1.1 devel package). Runtime crypto stays host-provided everywhere; we never bundle/ship OpenSSL (EOL-ownership liability rejected).
- ssl1.1 gate pattern TIGHTENED to exactly `OPENSSL_1_1_0`/`OPENSSL_1_1_1` (rejects RH-only suffixed nodes at build time).

---

### Task 11: pgcrypto OpenSSL-3.4 macro patch (staging percona-postgresql RPM)

**Goal:** EL9-built `pgcrypto.so` references only `OPENSSL_3.0.0` nodes.

**Files:**
- Create: `root/ppg/staging/17/percona-postgresql/rpm/<patch-file>.patch`
- Modify: `root/ppg/staging/17/percona-postgresql/rpm/*.spec` (Patch entry + %prep application, following the spec's existing patch conventions)

**Acceptance Criteria:**
- [ ] Patch confines itself to `contrib/pgcrypto` OpenSSL usage: force the pre-3.4 expansion of `EVP_MD_CTX_size()` (e.g. `EVP_MD_get_size(EVP_MD_CTX_get0_md(ctx))`) so no `EVP_MD_CTX_get_size_ex` reference is emitted; behaviorally identical
- [ ] Local rebuild evidence (rocky9 container rpmbuild or OBS PR build): `readelf` on built pgcrypto.so → zero version needs beyond `OPENSSL_3.0.*`
- [ ] Patch header documents why + upstream-flag note (candidate for percona/postgres upstream)

**Verify:** `readelf -V pgcrypto.so | grep OPENSSL_3.[1-9]` → empty on the EL9-built artifact.

### Task 12: matrix revert — ssl3 to Rocky 9, drop ssl3.5, remove deb builder, script fixes

**Goal:** Two-variant tree (ssl1.1, ssl3-on-EL9) with the acceptance-derived script fixes and tightened gate.

**Files:**
- Modify: `root/ppg/staging/17/tarballs/project.yaml` (ssl3 → Rocky 9 chain [pre-4c598e4 block + `Binarytype: rpm` + any needed Prefers]; delete ssl3.5 repo + prjconf block; keep ssl1.1)
- Modify: `obs/simpleimage` (remove deb `%if` branch AND the ssl3.5 python conditional — python3.12 set unconditionally; `%build` = plain `exec bash -x .../build-tarball.sh`)
- Delete: `obs/build-tarball-deb.sh`
- Modify: `obs/build-tarball.sh`:
  - EL mapping: 8→ssl1.1, 9→ssl3 (reachable again — restore active policy arm, drop the "unreachable" annotation), anything else FATAL (10 removed)
  - SSL-ABI policy: ssl1.1 pattern tightened to `^OPENSSL_1_1_0$|^OPENSSL_1_1_1$` (grep -qE or two -qx checks); ssl3 stays `OPENSSL_3\.0\.[0-9]*`
  - `postgres` wrapper: `export PYTHONHOME=/opt/percona-python3` (comment: embedded plpython3 has no wrapper env otherwise; acceptance-verified backend crash)
  - psql wrapper: add `/lib/x86_64-linux-gnu/libreadline.so.8` (+ aarch64-safe generic pattern) to the host-readline search paths
  - SYSTEM_LIBS_EXCLUDE: remove `libunistring`, `libnghttp2`, `libidn2` (get bundled; comment why — soname drift across distro generations, acceptance evidence)
- Modify: `root/README.md` + `docs/superpowers/specs/2026-07-20-obs-simpleimage-tarballs-design.md` (two-variant matrix, patched-pgcrypto note, deb-attempt rationale recorded, host prerequisites: `/run/postgresql`, tzdata, krb5 [pending Task 13 outcome])

**Acceptance Criteria:**
- [ ] Tree contains exactly ssl1.1 + ssl3 repos; no deb references anywhere outside git history and the spec's rejected-alternatives section
- [ ] shellcheck severity=error + bash -n clean; pytest/pyright/black green
- [ ] Container validation (EL9 provisioned image + Task 11's patched PG RPMs if available, else note): gate GREEN under strict ssl3 policy incl. pgcrypto
- [ ] isv dry-run clean (STANDING RULE: -P isv never without --dry-run)

**Verify:** container run → artifact `percona-postgresql-17.10-ssl3-linux-x86_64.tar.gz`, both audits 0 findings.

### Task 13: EL8 portability packages — krb5 (builtin crypto) + libssh (stock OpenSSL) + build-only openssl 1.1

**Goal:** ssl1.1 tarball loads on stock OpenSSL 1.1 hosts (Debian 11-class), no RH-only symbol needs.

**Files (USER DECISION 2026-07-22: packages live in `ppg:common:deps`, RockyLinux_8 ONLY, with the SAME NAMES as the distro originals):**
- Create: `root/ppg/common/deps/krb5/` — krb5 rebuilt with `--with-crypto-impl=builtin` (no OpenSSL linkage at all; official-tarball parity). Same source-package/binary names as the distro (`krb5-libs` etc.); wins resolution via higher EVR (e.g. a `.percona` release suffix). `package.yaml` restricts builds to RockyLinux_8 only (repo-restriction convention already used in the tree).
- Create: `root/ppg/common/deps/libssh/` — libssh rebuilt so its OpenSSL needs are stock-only. PREFERRED approach: build with the **libgcrypt backend** (`-DWITH_GCRYPT=ON`) — no OpenSSL involvement, no extra package needed (note: libgcrypt then must stay host-provided; it is in SYSTEM_LIBS_EXCLUDE and universally present). FALLBACK if gcrypt backend proves unworkable: build against a stock OpenSSL 1.1 devel package — in that case create `root/ppg/common/deps/openssl11-build/` with a DISTINCT name (`percona-openssl11-devel` or similar — same-name shadowing of `openssl` in common:deps would leak into every EL8 staging build chroot and is NOT acceptable), devel-only, never bundled/published.
- Modify: `root/ppg/staging/17/tarballs/project.yaml` — ssl1.1 chain already includes `ppg:common:deps/RockyLinux_8`; verify our same-named packages win (EVR) and add `Prefer:` lines only if OBS still reports a choice.

**Shadowing side effect to verify (not skip):** `ppg:staging:17`'s RockyLinux_8 repo chains `ppg:common:deps` too, so every EL8 staging build chroot will now resolve OUR krb5/libssh instead of Red Hat's. Consumers reference only stable krb5/libssh sonames+symbols, so produced RPMs should be identical in their requirements — but the implementer must verify at least one affected staging package (e.g. percona-postgresql EL8 buildinfo before/after via dry-run reasoning or PR build) and record the finding. If this side effect is deemed unwanted at review time, escalate to the user rather than silently switching to Prefer-scoped containment.

**Acceptance Criteria:**
- [ ] Rebuilt libk5crypto: NO libcrypto dependency at all (readelf NEEDED)
- [ ] Rebuilt libssh: OpenSSL needs = stock nodes only
- [ ] openssl11 package never appears in any published repo nor inside the tarball (audit + publish flags)
- [ ] EL8 container validation: full build green under the TIGHTENED ssl1.1 gate; artifact loads `initdb`/`postgres` on a debian:11 container (spot pre-check before the full Task 14 battery)

**Verify:** `readelf -d libk5crypto.so.3 | grep -i crypto` → no libcrypto NEEDED; gate output on EL8 build → 0 violations under the strict pattern.

### Task 14: re-validation + PR round 2 + acceptance rerun (USER GATE — continues plan Task 6)

> **USER-ORDERED GATE — NON-SKIPPABLE.** Close only with captured evidence for every criterion.

**Steps:** local container validations (EL8 + EL9) → user pushes → PR-145 re-sync → watch both repos to `succeeded` (budget one resolution iteration for the new tarball-deps chain) → download artifacts → acceptance battery:
- ssl1.1 on **debian:11** (previously FAILED — must pass: initdb, server, psql via fixed wrapper, pg_tde, **pgcrypto digest**, plpython3u [PYTHONHOME via wrapper — no manual env], plperlu, pltclu, patronictl, patroni_aws [jmespath present in fresh artifact])
- ssl3 on **ubuntu:22.04** AND **ubuntu:24.04** (the tier's real audience; pgcrypto digest on host OpenSSL 3.0 is the headline proof; libunistring bundling verified by loading on 24.04)
- structure-diffs vs official; document divergences + host prerequisites for release notes

**Acceptance Criteria:**
- [ ] Both variants PASS their full battery on the listed hosts with zero manual workarounds beyond documented host prerequisites (`/run/postgresql`, tzdata)
- [ ] Evidence captured per command; user merges the PR

---

## Execution notes
- Order: Task 11 ∥ Task 13 (disjoint files) → Task 12 (needs 11's patch for its container validation ideally; can start structural work in parallel but shares no files with 11/13 except simpleimage with 13 — coordinate: 12 owns tarballs/ tree, 13 adds its Prefer/BuildRequires hunks AFTER 12 lands) → Task 14 last.
- Standing rules: `git commit -s`, no AI attribution, never push / create PRs (user does), `-P isv` writes only with `--dry-run`.
- The pgcrypto patch (11) also changes shipping RPM symbol needs (strictly beneficial); flag to Percona upstream for a permanent home.
