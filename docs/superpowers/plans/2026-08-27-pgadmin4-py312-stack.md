# pgAdmin 4 Python 3.12 Stack (sub-project 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 77 `python3-*` package directories (71 in `root/ppg/devel/pgadmin/`, 6 in `root/ppg/common/deps/` including the `python3-dns` bump) that give `percona-pgadmin4` its complete Python 3.12 runtime closure on UBI 9, and get them all building green in PR #12's OBS project.

**Architecture:** Every package is an ordinary repo package (`package.yaml`, `obs/_service` with a PyPI-sdist `download_url`, `rpm/python3-<name>.spec`) following one EL spec template with three build families (pyproject via `pip wheel`/`pip install`, legacy `setup.py`, self-hosting backends). Because RHEL 9's build backends cannot build current PEP 639 metadata, `ppg:common:deps` gains a shared backend stack (flit-core, packaging, pathspec, trove-classifiers, hatchling) for EL8/EL9/UBI, while EL10/openSUSE use their distro backends through a spec conditional. The 77 directories are written once by a throwaway render script (Appendix A) from a fixed data file (Appendix B) — both live only in the scratchpad, never in the repo — and are hand-maintained afterwards like every other package.

**Tech Stack:** RPM spec files (EL8/EL9/EL10/openSUSE conditionals), OBS `download_url` + `cargo_vendor` services, PyPI sdists, `percona-obs` (`sync push --dry-run`), OBS public API (read-only build monitoring), Python 3 (throwaway render script only).

**Spec:** `docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md`

## Global Constraints

- Work happens in the worktree `/home/rdias/Work/percona-obs-packaging/.claude/worktrees/pgadmin-sp1` on branch `pgadmin-sp1` (PR #12). Run every command from there.
- Every commit: `git commit -s` (Signed-off-by). **No** `Co-Authored-By: Claude` lines.
- **Pushing is authorised only to `percona pgadmin-sp1`** (the user designated PR #12 as the test vehicle for SP2–4: "use the same PR to test the following SP"). Never push anywhere else; never open a PR; never add the `obs-sync` label (the user manages labels).
- OBS: `-P isv-pr` and `-P isv` are **production** (api.opensuse.org) — only ever with `--dry-run`. Build results and logs are read through the public API (`https://api.opensuse.org/public/build/...`), never through `osc` writes. No local `rpmbuild`/mock builds (OBS-first validation).
- The render script and its data file live in the scratchpad `/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/4a404ac4-d132-42d5-92af-b4a8d5e081ba/scratchpad/` and are **never committed**. Only the rendered package directories and the docs changes go into git. After rendering, the specs are hand-maintained: a build fix is an edit to that package's spec (and, if you like, a re-render is *not* required).
- Directory names are `python3-<pypi name lower-cased, `.`/`_` → `-`>`; the one exception is `python3-dns` (dnspython), whose name is kept because `python3-etcd` and `percona-patroni` require `%{python3_pkgprefix}-dns`.
- Versions are exactly those in Appendix B (spec §3/§4). Do not "upgrade" a package while fixing a build — pins were chosen to fit RHEL's setuptools 68.
- `percona_obs/` is not touched. Still run `venv/bin/black percona_obs/`, `venv/bin/pyright`, `venv/bin/pytest -q` once before the first push to prove nothing moved (expected: unchanged / 0 errors / 147 passed).
- Root-level `macros.yaml`, `project.yaml` files and `root/ppg/devel/pgadmin/project.yaml` are **not** modified by this plan.

**User decisions (already made):**
- Reuse existing packages where the libraries' real minimums are met (RHEL 9: cffi, cryptography 41.0.7, idna, pycparser, urllib3 1.26, setuptools 68; ppg:common:deps: six, dateutil, psutil 6.1.1, click 8.1.7) — no maturin/Rust for cryptography, no replacement of RHEL runtime packages.
- Bump `python3-dns` in `ppg:common:deps` to dnspython 2.8.0 for everyone (name kept) and add the shared build-backend stack to `ppg:common:deps`.
- Plain package directories, **no generator or manifest committed** to the repo; render once with a throwaway script, then hand-maintain.
- PR #12 stays open as the test vehicle for SP2–4; the user does not merge it yet.
- `%check` is an import smoke test only (no pytest).

---

## File structure

| Path | Responsibility |
|---|---|
| `root/ppg/common/deps/python3-dns/{package.yaml,obs/_service,rpm/python3-dns.spec}` (modify) | dnspython 1.15.0 → 2.8.0, hatchling build, `download_url` source; `package.yaml` is new (the directory had none). |
| `root/ppg/common/deps/python3-{flit-core,packaging,pathspec,trove-classifiers,hatchling}/` (new) | Shared build-backend stack; `build:` flags disable RockyLinux_10 and both openSUSE repos. |
| `root/ppg/devel/pgadmin/python3-<name>/` ×71 (new) | 68 runtime libraries + build tools `python3-cython`, `python3-poetry-core`, `python3-pdm-backend`. |
| `docs/PACKAGING_HOWTO.md` (modify) | New section "Python 3.12 packages (pyproject builds)" documenting the template; checklist row. |
| `root/README.md` (modify) | `devel/pgadmin/` paragraph lists the Python stack; `common/deps/` mentions the build-backend stack. |
| scratchpad `render_stack.py` + `stack.json` (not committed) | Appendix A and B; produce the 77 directories. |

Batches (each its own commit, in this order, so an OBS failure localises):

- **Batch A — `ppg:common:deps` (6):** `python3-flit-core`, `python3-packaging`, `python3-pathspec`, `python3-trove-classifiers`, `python3-hatchling`, `python3-dns`.
- **Batch B — pgadmin build tools + leaves (36):** `python3-cython`, `python3-poetry-core`, `python3-pdm-backend`; leaves (no dependency on another pgadmin package): `authlib babel backports-zstd bcrypt bidict blinker brotli decorator email-validator flask-principal greenlet h11 importlib-resources itsdangerous jaraco-context jeepney jsonformatter libgravatar markupsafe mdurl more-itertools passlib pillow psycopg-c pyasn1 pygments pynacl pyotp pytz shellingham sqlparse typing-extensions ua-parser` (each prefixed `python3-`).
- **Batch C — pgadmin dependents (35):** `alembic flask flask-babel flask-compress flask-login flask-mail flask-migrate flask-paranoid flask-security-too flask-socketio flask-sqlalchemy flask-wtf gssapi jaraco-classes jaraco-functools jinja2 keyring ldap3 mako markdown-it-py paramiko psycopg python-engineio python-socketio qrcode rich secretstorage simple-websocket sqlalchemy sshtunnel typer user-agents werkzeug wsproto wtforms` (each prefixed `python3-`).

---

### Task 1: Render all 77 package directories and commit batch A (`ppg:common:deps`)

**Goal:** The render script and data are materialised in the scratchpad, all 77 directories exist in the worktree exactly as the template prescribes, every spec parses, a sample dry-run sync resolves the sources, and the six `ppg:common:deps` packages are committed.

**Files:**
- Create (scratchpad, not committed): `.../scratchpad/render_stack.py` (Appendix A), `.../scratchpad/stack.json` (Appendix B), `.../scratchpad/check_render.py` (Step 3)
- Create: `root/ppg/common/deps/python3-{flit-core,packaging,pathspec,trove-classifiers,hatchling}/{package.yaml,obs/_service,rpm/python3-<name>.spec}`
- Modify: `root/ppg/common/deps/python3-dns/obs/_service`, `root/ppg/common/deps/python3-dns/rpm/python3-dns.spec`; Create: `root/ppg/common/deps/python3-dns/package.yaml`
- Create (left uncommitted for Tasks 2–3): the 71 `root/ppg/devel/pgadmin/python3-*/` directories

**Acceptance Criteria:**
- [ ] `find root/ppg/devel/pgadmin -name '*.spec' | wc -l` prints `71`; `ls -d root/ppg/common/deps/python3-{flit-core,packaging,pathspec,trove-classifiers,hatchling,dns}` lists 6 directories
- [ ] `check_render.py` reports `specs: 77  parsed OK: 77  failures: 0` and `non-SPDX-looking: []`
- [ ] `sync push --dry-run -P isv-pr ppg:common:deps python3-hatchling` and `... python3-trove-classifiers` each print `✔ service download_url`, `~ 2 files` (spec + sdist) and `✔ sync successful (dry run)`
- [ ] `git show --stat HEAD` lists exactly 17 files: 6 × (`package.yaml`, `obs/_service`, `rpm/*.spec`) minus the pre-existing `python3-dns/obs/_service` + `rpm/python3-dns.spec` counted as modified (i.e. 15 new + 2 modified)
- [ ] `git status --short` afterwards shows only the 71 untracked `root/ppg/devel/pgadmin/python3-*/` directories (plus the pre-existing untracked `.profile`, `venv`)

**Verify:** `venv/bin/python /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/4a404ac4-d132-42d5-92af-b4a8d5e081ba/scratchpad/check_render.py root` → `specs: 77  parsed OK: 77  failures: 0`

**Steps:**

- [ ] **Step 1: Materialise the render inputs in the scratchpad**

Write Appendix A verbatim to `/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/4a404ac4-d132-42d5-92af-b4a8d5e081ba/scratchpad/render_stack.py` and Appendix B verbatim to `/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/4a404ac4-d132-42d5-92af-b4a8d5e081ba/scratchpad/stack.json` (the script reads `stack.json` from its own directory). Write the checker below to `/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/4a404ac4-d132-42d5-92af-b4a8d5e081ba/scratchpad/check_render.py`:

```python
"""Parse every rendered spec with rpmspec and audit licence strings.  Usage: check_render.py <tree-root>"""

import collections
import pathlib
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
specs = sorted(p for p in root.rglob("python3-*/rpm/*.spec"))
bad = 0
licences = collections.Counter()
for spec in specs:
    r = subprocess.run(
        ["rpmspec", "-q", "--qf", "%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n", str(spec)],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        bad += 1
        print("FAIL", spec.name, r.stderr.strip()[:300])
    for line in spec.read_text().splitlines():
        if line.startswith("License:"):
            licences[line.split(":", 1)[1].strip()] += 1
            break
print(f"specs: {len(specs)}  parsed OK: {len(specs) - bad}  failures: {bad}")
print("licences:", dict(licences))
odd = [l for l in licences if "see upstream" in l or " " in l.replace(" AND ", "")]
print("non-SPDX-looking:", odd)
```

Note: `rpmspec` runs locally on Fedora where `%rhel` is undefined, so the specs' SUSE/`python3` branch is what gets parsed — a syntax check, not an EL rendering. That is intended.

- [ ] **Step 2: Render into the worktree**

```bash
cd /home/rdias/Work/percona-obs-packaging/.claude/worktrees/pgadmin-sp1
venv/bin/python /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/4a404ac4-d132-42d5-92af-b4a8d5e081ba/scratchpad/render_stack.py . | wc -l
```
Expected: `77`. Then `git status --short | grep -c '^?? root/ppg/devel/pgadmin/python3-'` → `71`, and `git status --short root/ppg/common/deps` → 5 `??` directories plus ` M root/ppg/common/deps/python3-dns/obs/_service`, ` M root/ppg/common/deps/python3-dns/rpm/python3-dns.spec`, `?? root/ppg/common/deps/python3-dns/package.yaml`.

- [ ] **Step 3: Parse every spec**

```bash
venv/bin/python /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/4a404ac4-d132-42d5-92af-b4a8d5e081ba/scratchpad/check_render.py root
```
Expected: `specs: 77  parsed OK: 77  failures: 0`, `non-SPDX-looking: []`. Any FAIL is a render-script bug: fix it in the scratchpad script, re-run Step 2, repeat.

- [ ] **Step 4: Dry-run the two batch-A packages that exercise special paths**

```bash
venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:common:deps python3-hatchling 2>&1 | tail -8
venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:common:deps python3-trove-classifiers 2>&1 | tail -8
venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:common:deps python3-dns 2>&1 | tail -8
```
Expected for each: `✔  service download_url  ...`, `✔  packaging rpm/  ...  (1 files)`, `~ 2 files` with `|_ + python3-<name>.spec` and `|_ + <sdist>.tar.gz` (for `python3-dns`: `~ 3 files` with `|_ - python3-dns-1.15.0.tar.gz` or the obs_scm artefacts removed, `|_ + dnspython-2.8.0.tar.gz`, `|_ ~ python3-dns.spec`), `✔  sync successful (dry run)`. A 404 from `download_url` means a wrong sdist URL in Appendix B — fix the `sdist_url` there, re-render.

- [ ] **Step 5: Commit batch A**

```bash
git add root/ppg/common/deps/python3-flit-core root/ppg/common/deps/python3-packaging \
        root/ppg/common/deps/python3-pathspec root/ppg/common/deps/python3-trove-classifiers \
        root/ppg/common/deps/python3-hatchling root/ppg/common/deps/python3-dns
git commit -s -F - <<'EOF'
ppg:common:deps: Python 3.12 build-backend stack; bump python3-dns to dnspython 2.8.0

Add python3-flit-core 3.12.0, python3-packaging 25.0, python3-pathspec 0.12.1,
python3-trove-classifiers 2025.9.11.17 and python3-hatchling 1.28.0 for
EL8/EL9/UBI (EL10 and openSUSE use their distro backends; disabled via
package.yaml build flags). RHEL's flit-core 3.9 / hatchling / packaging 23.2
cannot build current PEP 639 metadata (Flask, Werkzeug, Pygments, ...).

Bump python3-dns from dnspython 1.15.0 to 2.8.0 (email-validator, needed by
Flask-Security-Too for pgAdmin 4, requires >= 2.0). Package/RPM name kept so
python3-etcd and percona-patroni need no change; source moves from obs_scm
to the PyPI sdist via download_url; built with hatchling.

Design: docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md
EOF
git show --stat HEAD | tail -20
```
Expected: 15 new files + 2 modified (17 in the stat).

---

### Task 2: Commit batch B (pgadmin build tools + leaf libraries)

**Goal:** The 36 pgadmin packages that depend on nothing else in the pgadmin project (three build tools + 33 leaves) are committed, after a dry-run proves the `cargo_vendor` path for bcrypt and the plain path for a native leaf.

**Files:**
- Create: `root/ppg/devel/pgadmin/python3-{cython,poetry-core,pdm-backend}/` and the 33 leaf directories listed under "Batch B" above (each `package.yaml`, `obs/_service`, `rpm/python3-<name>.spec`)

**Acceptance Criteria:**
- [ ] `sync push --dry-run -P isv-pr ppg:devel:pgadmin python3-bcrypt` prints `✔ service download_url`, `✔ service cargo_vendor` and a would-be upload of 3 files (`python3-bcrypt.spec`, `bcrypt-5.0.0.tar.gz`, `vendor.tar.gz`)
- [ ] `sync push --dry-run -P isv-pr ppg:devel:pgadmin python3-psycopg-c` prints `~ 2 files` and `✔ sync successful (dry run)`
- [ ] `git show --stat HEAD | tail -1` reports `108 files changed` (36 × 3)
- [ ] `git status --short | grep -c '^?? root/ppg/devel/pgadmin/'` → `35`

**Verify:** `git show --stat HEAD | tail -1` → `108 files changed, ... insertions(+)`

**Steps:**

- [ ] **Step 1: Dry-run bcrypt (cargo_vendor) and one native leaf**

```bash
venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:devel:pgadmin python3-bcrypt 2>&1 | tail -12
venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:devel:pgadmin python3-psycopg-c 2>&1 | tail -8
```
Expected (bcrypt): `✔  service download_url`, `✔  service cargo_vendor`, `~ 3 files` listing `+ python3-bcrypt.spec`, `+ bcrypt-5.0.0.tar.gz`, `+ vendor.tar.gz`, `✔  sync successful (dry run)`. If `cargo_vendor` fails with "no Cargo.toml", the `cargotoml` param path is wrong — check `tar tzf` of the sdist for the crate path (`bcrypt-5.0.0/src/_bcrypt/Cargo.toml`) and fix `obs/_service` by hand (this is the only hand edit expected in this task; keep the render script in sync only if you re-render).

- [ ] **Step 2: Commit batch B**

```bash
cd root/ppg/devel/pgadmin
git add python3-cython python3-poetry-core python3-pdm-backend \
  python3-authlib python3-babel python3-backports-zstd python3-bcrypt python3-bidict python3-blinker \
  python3-brotli python3-decorator python3-email-validator python3-flask-principal python3-greenlet \
  python3-h11 python3-importlib-resources python3-itsdangerous python3-jaraco-context python3-jeepney \
  python3-jsonformatter python3-libgravatar python3-markupsafe python3-mdurl python3-more-itertools \
  python3-passlib python3-pillow python3-psycopg-c python3-pyasn1 python3-pygments python3-pynacl \
  python3-pyotp python3-pytz python3-shellingham python3-sqlparse python3-typing-extensions python3-ua-parser
cd -
git commit -s -F - <<'EOF'
ppg:devel:pgadmin: Python 3.12 stack, part 1 — build tools and leaf libraries

Build tools: python3-cython 3.1.3 (gssapi, SQLAlchemy speedups),
python3-poetry-core 2.2.1 and python3-pdm-backend 2.4.5 (self-hosting).

33 leaf libraries of pgAdmin 4's Python 3.12 closure that depend only on
RHEL 9 / ppg:common:deps packages: PyPI sdists via download_url, one EL
spec template (pip wheel / pip install, or setup.py for legacy packages),
import smoke test in %check. bcrypt vendors its Rust crate with
cargo_vendor (cargotoml=src/_bcrypt/Cargo.toml).

Versions follow the spec: pinned below latest where PEP 639 metadata would
need setuptools >= 77 (importlib-resources 6.5.2, jaraco.context 6.0.1,
Pillow 11.1.0), bidict 0.23.1 (no uv_build), pyotp 2.9.0 (no hatch-vcs),
ua-parser 0.18.0 (self-contained).

Design: docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md
EOF
git show --stat HEAD | tail -1
```
Expected: `108 files changed`.

---

### Task 3: Commit batch C (pgadmin dependents)

**Goal:** The remaining 35 pgadmin packages, which depend on batch A/B packages, are committed after a dry-run of one package per remaining build family.

**Files:**
- Create: the 35 directories listed under "Batch C" above

**Acceptance Criteria:**
- [ ] Dry-runs of `python3-flask` (flit), `python3-wtforms` (hatchling), `python3-paramiko` (setup.py), `python3-typer` (pdm), `python3-rich` (poetry) each end with `✔ sync successful (dry run)` and `~ 2 files`
- [ ] `git show --stat HEAD | tail -1` reports `105 files changed` (35 × 3)
- [ ] `git status --short | grep -c '^?? root/'` → `0`

**Verify:** `git status --short | grep -c '^?? root/'` → `0`

**Steps:**

- [ ] **Step 1: Dry-run one package per build family**

```bash
for p in python3-flask python3-wtforms python3-paramiko python3-typer python3-rich; do
  venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:devel:pgadmin $p 2>&1 | tail -4
done
```
Expected: five times `~ 2 files` and `✔  sync successful (dry run)`.

- [ ] **Step 2: Commit batch C**

```bash
cd root/ppg/devel/pgadmin
git add python3-alembic python3-flask python3-flask-babel python3-flask-compress python3-flask-login \
  python3-flask-mail python3-flask-migrate python3-flask-paranoid python3-flask-security-too \
  python3-flask-socketio python3-flask-sqlalchemy python3-flask-wtf python3-gssapi python3-jaraco-classes \
  python3-jaraco-functools python3-jinja2 python3-keyring python3-ldap3 python3-mako python3-markdown-it-py \
  python3-paramiko python3-psycopg python3-python-engineio python3-python-socketio python3-qrcode python3-rich \
  python3-secretstorage python3-simple-websocket python3-sqlalchemy python3-sshtunnel python3-typer \
  python3-user-agents python3-werkzeug python3-wsproto python3-wtforms
cd -
git commit -s -F - <<'EOF'
ppg:devel:pgadmin: Python 3.12 stack, part 2 — Flask, SQLAlchemy, keyring and friends

The 35 remaining libraries of pgAdmin 4's Python 3.12 closure, which
depend on part 1 / ppg:common:deps packages: Flask 3.1.3 and its
extensions (Flask-Security-Too 5.6.2, Flask-SocketIO, Flask-Migrate, ...),
SQLAlchemy 2.0.52 + alembic, Werkzeug/Jinja2, keyring 25.2.1 stack,
paramiko/sshtunnel, psycopg 3.2.10, typer/rich, gssapi 1.10.1 (Cython 3),
python-socketio/engineio, WTForms.

Runtime dependencies are also BuildRequires so the %check import smoke
test runs against the buildroot; OBS orders the builds accordingly.

Design: docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md
EOF
git show --stat HEAD | tail -1
```
Expected: `105 files changed`.

---

### Task 4: Document the template and the new package sets

**Goal:** `docs/PACKAGING_HOWTO.md` explains how a Python 3.12 pyproject-based package is written here (so the next one follows the same pattern), and `root/README.md` says what `devel/pgadmin/` and `common/deps/` now contain.

**Files:**
- Modify: `docs/PACKAGING_HOWTO.md` (insert a new section before `## Adding a Package as an Aggregate in a Subproject`; add one checklist row)
- Modify: `root/README.md` (the `common/deps/` bullet and the `### devel/pgadmin/` paragraph)

**Acceptance Criteria:**
- [ ] `grep -n "^## Python 3.12 packages" docs/PACKAGING_HOWTO.md` finds the section, positioned before `## Adding a Package as an Aggregate in a Subproject`
- [ ] The section contains the header block, the `pip wheel`/`pip install` recipe, the `setup.py` legacy recipe, the hatchling `%if 0%{?rhel} == 8 || 0%{?rhel} == 9` conditional, the `%check` line and the reuse policy
- [ ] `grep -c "python3-hatchling\|build-backend stack" root/README.md` ≥ 2
- [ ] `venv/bin/pytest -q` → `147 passed`; `venv/bin/black percona_obs/` → unchanged; `venv/bin/pyright` → `0 errors`

**Verify:** `grep -n "^## Python 3.12 packages\|^## Adding a Package as an Aggregate" docs/PACKAGING_HOWTO.md` → the Python section's line number is smaller

**Steps:**

- [ ] **Step 1: Insert the how-to section**

Insert the following immediately before the line `## Adding a Package as an Aggregate in a Subproject` in `docs/PACKAGING_HOWTO.md`:

````markdown
## Python 3.12 packages (pyproject builds)

RPM-only Python libraries for RHEL-family targets are built for `/usr/bin/python3.12`
and named `python3.12-<name>` (`%{python3_pkgprefix}-<name>`; plain `python3-<name>` on
openSUSE). The directory is `python3-<PyPI name lower-cased, `.`/`_` → `-`>`. Examples:
everything under `root/ppg/devel/pgadmin/python3-*` and the build-backend stack in
`root/ppg/common/deps/` (`python3-flit-core`, `python3-packaging`, `python3-pathspec`,
`python3-trove-classifiers`, `python3-hatchling`).

**Reuse before you build.** RHEL 9 already ships `python3.12-{cffi,cryptography,idna,
pycparser,urllib3,setuptools,pip,wheel}` (AppStream) and `python3.12-{packaging 23.2,
pluggy,pytest,setuptools-rust,flit-core 3.9,Cython 0.29}` (CRB); `ppg:common:deps` has
`six`, `dateutil`, `psutil`, `click`, `dns`. Depend on those by their RPM name — without a
version floor, since RHEL's versions are often older than upstream's declared minimum but
work — and only package what is missing. RHEL's *build backends* are too old for current
PEP 639 metadata; use ours from `ppg:common:deps` (see the conditional below).

**Source:** the PyPI sdist via `download_url`, literal version:

```xml
<services>
  <service name="download_url">
    <param name="url">https://files.pythonhosted.org/packages/source/f/flask/flask-3.1.3.tar.gz</param>
  </service>
</services>
```

**Spec header** (identical in every package; copy from `root/ppg/devel/pgadmin/python3-flask/rpm/python3-flask.spec`):

```rpmspec
%global debug_package %{nil}          # noarch only; drop for C/Rust extensions
%if 0%{?rhel} && 0%{?rhel} >= 8
%global __ospython        %{_bindir}/python3.12
%global python3_pkgprefix python3.12
%global python3_buildversion 3.12
%global __requires_exclude ^python3\\.12dist
%else
%global __ospython        %{_bindir}/python3
%global python3_pkgprefix python3
%global python3_buildversion 3
%endif
%{expand: %%global py3ver %(echo `%{__ospython} -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" `)}
%global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")
# extensions: python3_sitearch with 'platlib' instead

Name:           %{python3_pkgprefix}-flask
Version:        3.1.3
Release:        1%{?dist}
Source0:        https://files.pythonhosted.org/packages/source/f/flask/flask-3.1.3.tar.gz
BuildArch:      noarch
Epoch:          1
BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
```

Then the backend the sdist's `[build-system]` names — `python%{python3_buildversion}-flit-core`,
`%{python3_pkgprefix}-poetry-core`, `%{python3_pkgprefix}-pdm-backend`, `%{python3_pkgprefix}-setuptools_scm`
(EPEL) when `setuptools_scm` is listed — and for hatchling the distro/ours switch:

```rpmspec
%if 0%{?rhel} == 8 || 0%{?rhel} == 9
BuildRequires:  %{python3_pkgprefix}-hatchling      # ours, ppg:common:deps
%else
BuildRequires:  python3-hatchling                    # EL10 CRB / openSUSE
%endif
```

Every runtime `Requires:` is also a `BuildRequires:` so `%check` can import the module.

**Build/install — pyproject packages** (setuptools, flit, hatchling, poetry, pdm):

```rpmspec
%prep
%autosetup -p1 -n flask-%{version}

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -c "import flask"

%files
%{python3_sitelib}/*
%{_bindir}/flask
```

Self-hosting backends (hatchling, poetry-core, pdm-backend, flit-core) add
`export PYTHONPATH=$PWD/src` (flit-core: `$PWD/.`) before `pip wheel`. Rust extensions
(bcrypt) add a `cargo_vendor` service (`cargotoml` pointing at the crate's `Cargo.toml`),
`Source1: vendor.tar.gz`, `%autosetup -a1`, `CARGO_NET_OFFLINE=true`.

**Build/install — legacy `setup.py`-only packages** (no `pyproject.toml`): keep the
`%{__ospython} setup.py build` / `setup.py install --single-version-externally-managed -O1
--root=%{buildroot} --record=INSTALLED_FILES` recipe and `%files -f INSTALLED_FILES`, as in
`root/ppg/common/deps/python3-click`.

**Bumping:** edit the sdist URL in `obs/_service`, `Version:` in the spec, add a
`%changelog` entry. Nothing is generated.

---

````

And add this row to the "Quick Reference: File Checklist" table, after the `rpm/<name>.spec` row:

```markdown
| `rpm/python3-<name>.spec` | Python 3.12 libs | Template in "Python 3.12 packages"; `Version:` literal; runtime deps also `BuildRequires` |
```

- [ ] **Step 2: Update root/README.md**

In the `### devel/pgadmin/ — a version-independent devel project` paragraph of `root/README.md`, replace the sentence

`Packages there follow the normal `rpm/` + `obs/_service` layout; the npm dependencies are vendored at sync time by the `npm_lockfile` → `node_modules` service pair (see `docs/PERCONA_OBS_TOOL.md`).`

with

`Packages there follow the normal `rpm/` + `obs/_service` layout. The Python side is the ~70 `python3-*` directories (pgAdmin's Python 3.12 closure, built from PyPI sdists — see "Python 3.12 packages" in `docs/PACKAGING_HOWTO.md`); the npm dependencies are vendored at sync time by the `npm_lockfile` → `node_modules` service pair (see `docs/PERCONA_OBS_TOOL.md`). The shared Python build-backend stack (`python3-flit-core`, `python3-packaging`, `python3-pathspec`, `python3-trove-classifiers`, `python3-hatchling`) lives in `ppg/common/deps/` because other products' Python packages need it too.`

- [ ] **Step 3: Run the repo checks and commit**

```bash
venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest -q
git add docs/PACKAGING_HOWTO.md root/README.md
git commit -s -m "docs: how to write Python 3.12 (pyproject) packages; document the pgAdmin Python stack"
```
Expected: `left unchanged`, `0 errors`, `147 passed`.

---

### Task 5: Build everything in PR #12's OBS project and fix what fails

**Goal:** All 77 packages build green in `isv:percona:PR:pr-12` — the six common:deps ones on every repo they build for, the 71 pgadmin ones on UBI_9 x86_64 and aarch64 — with the dnspython cascade (python3-etcd, percona-patroni) also green.

**Files:**
- Modify (only as build failures dictate): individual `root/**/python3-*/rpm/*.spec` or `obs/_service` files
- Push: `percona pgadmin-sp1`

**Acceptance Criteria:**
- [ ] `git push percona pgadmin-sp1` succeeds and a new `OBS PR Check` run appears for the pushed head (`gh run list --repo percona/obs-packaging --branch pgadmin-sp1 --limit 1`)
- [ ] The run's "Sync packages to OBS" job succeeds and its log shows `+ package isv:percona:PR:pr-12:ppg:common:deps/python3-hatchling` (and the other 5) and 71 `+ package isv:percona:PR:pr-12:ppg:devel:pgadmin/python3-...` lines, plus dep-promotes of `python3-etcd` and `percona-patroni`
- [ ] `_result` of `isv:percona:PR:pr-12:ppg:devel:pgadmin` shows `code="succeeded"` for all 71 packages on UBI_9 x86_64 and aarch64 (no `failed`, `unresolvable`, `broken`)
- [ ] `_result` of `isv:percona:PR:pr-12:ppg:common:deps` shows `succeeded` for `python3-dns` on every RPM repo, for the five backend packages on RockyLinux_8/9 and UBI_8/9 (and `disabled` on RockyLinux_10/openSUSE), and for `python3-etcd`
- [ ] Every fix made during the loop is a committed spec/_service edit with a one-line rationale in the commit message; the fixes are listed in the PR body (Task 6)

**Verify:** `curl -s "https://api.opensuse.org/public/build/isv:percona:PR:pr-12:ppg:devel:pgadmin/_result" | grep -c 'code="succeeded"'` → `142` (71 × 2 archs)

**Steps:**

- [ ] **Step 1: Push**

```bash
git log --oneline percona/pgadmin-sp1..HEAD     # expect: the 4 commits from Tasks 1-4 (+ the two spec commits already there if not yet pushed)
git push percona pgadmin-sp1
gh run list --repo percona/obs-packaging --branch pgadmin-sp1 --limit 2 --json databaseId,headSha,status,conclusion --jq '.[] | "\(.databaseId) \(.headSha[0:7]) \(.status)/\(.conclusion)"'
```
Expected: a run for the new head. (Actions may be delayed after outages; if no run appears within 15 minutes and githubstatus.com shows Actions degraded, wait — do not re-push.)

- [ ] **Step 2: Watch the sync job, then the builds**

Sync job log (after it completes): `gh api repos/percona/obs-packaging/actions/jobs/<sync-job-id>/logs | grep -E "\+ package|dep-promote|error" | head -120`. Expected: 77 `+ package` lines for our packages plus dep-promotes of `python3-etcd` and the `percona-patroni` packages; no `error:`.

Build results (poll every ~10 min; OBS builds the stack bottom-up over 1–2 hours):
```bash
curl -s "https://api.opensuse.org/public/build/isv:percona:PR:pr-12:ppg:common:deps/_result?package=python3-flit-core&package=python3-packaging&package=python3-pathspec&package=python3-trove-classifiers&package=python3-hatchling&package=python3-dns&package=python3-etcd" | grep -E "<result|<status"
curl -s "https://api.opensuse.org/public/build/isv:percona:PR:pr-12:ppg:devel:pgadmin/_result" | grep -oE 'package="[^"]*" code="[^"]*"' | sort | uniq -c | sort -rn | grep -v succeeded
```
Expected end state: the second command prints nothing (every package `succeeded`); the first shows `succeeded` (or `disabled` for the five backends on RockyLinux_10/openSUSE).

- [ ] **Step 3: Fix loop for each failed package**

Read the log: `curl -s "https://api.opensuse.org/public/build/isv:percona:PR:pr-12:ppg:devel:pgadmin/UBI_9/x86_64/<pkg>/_log" | grep -nE "error|Error|No such|not found|ModuleNotFoundError" | tail -30` (use `.../ppg:common:deps/<repo>/x86_64/...` for batch A). Known likely causes and their fixes (edit the spec by hand, commit, push — each push re-syncs only the changed package):
  - `ModuleNotFoundError` in `%check` → a runtime dependency missing from `BuildRequires`/`Requires`; add it (`%{python3_pkgprefix}-<name>`, or the RHEL name for reused packages).
  - `nothing provides python3.12-<x>` (unresolvable) → the dependency's RPM name differs (RHEL names: `python3.12-setuptools_scm` is EPEL's exact name; ours are `%{python3_pkgprefix}-<dir name without python3->`); fix the name.
  - `error: Installed (but unpackaged) file(s)` → a console script or data file outside `%{python3_sitelib}`; add the path to `%files`.
  - `license-files`/`license field should be dict` → a backend too old resolved (EL10/openSUSE distro backend on a package that should not build there) — check the package's `build:` flags / conditional.
  - bcrypt `failed to select a version for ... offline` → vendor tarball not found by cargo; ensure `%autosetup -a1` extracted `vendor/` and `.cargo/config` at the sdist root; if the vendor config lives elsewhere, `cp .cargo/config.toml src/_bcrypt/.cargo/` in `%prep`.
  - gssapi `Cython.Compiler` errors → `python3.12-cython` (ours, 3.1.3) not selected over CRB 0.29: add `BuildRequires: %{python3_pkgprefix}-cython >= 3.1`.
  - Pillow feature errors → adjust the `-C <feature>=disable` list in `%build`.
  - trove-classifiers `use_calver` still present → the `sed` in `%prep` missed; inspect the sdist's `setup.py` and adapt the expression.
  Commit each fix: `git commit -s -m "python3-<name>: <one-line cause and fix>"`, then `git push percona pgadmin-sp1`.

- [ ] **Step 4: Record the final state**

When both `_result` queries show the expected end state, save the final counts (number of fix commits, list of packages that needed fixes) for Task 6.

---

### Task 6: Update PR #12 and the effort's records

**Goal:** PR #12's body describes SP3 (what was added, versions policy, the dnspython bump and its cascade, verification results, fixes made during the build loop), and the spec's risk table reflects what actually happened.

**Files:**
- Modify: `docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md` (§8 rows: mark each risk as observed/not, add any new failure class found)
- Modify (via `gh pr edit`): PR #12 title and body

**Acceptance Criteria:**
- [ ] `gh pr view 12 --repo percona/obs-packaging --json title --jq .title` → `pgAdmin 4 for UBI-9: SP1 node_modules tooling + SP2 local-npm-registry + SP3 Python 3.12 stack`
- [ ] The PR body has an `## SP3 — Changes` section (package counts, the six common:deps packages, dnspython bump + cascade, version pins) and an `## SP3` block under Verification (dry-runs, OBS results, list of build-loop fixes)
- [ ] Spec §8 has no row left saying only "verified by the first build"; each says what happened
- [ ] Spec change committed and pushed with `git push percona pgadmin-sp1`

**Verify:** `gh pr view 12 --repo percona/obs-packaging --json body --jq .body | grep -c "SP3"` ≥ 3

**Steps:**

- [ ] **Step 1: Update spec §8 with the observed outcome** — for every row in the risks table, replace the mitigation text's forward-looking part with what the OBS builds showed (e.g. "did not occur", or "occurred on <pkg>: fixed by <commit>"). Commit: `git commit -s -m "docs: SP3 spec — record build outcomes against the risk table"`.

- [ ] **Step 2: Edit the PR** — fetch the current body (`gh pr view 12 --repo percona/obs-packaging --json body --jq .body > /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/4a404ac4-d132-42d5-92af-b4a8d5e081ba/scratchpad/pr12-body.md`), then:
  - Title: `pgAdmin 4 for UBI-9: SP1 node_modules tooling + SP2 local-npm-registry + SP3 Python 3.12 stack`.
  - Summary list: add `- **SP3 — Python 3.12 stack:** the 71 python3.12-* RPMs of pgAdmin 4's dependency closure in ppg:devel:pgadmin, plus a shared build-backend stack and a dnspython bump in ppg:common:deps.`
  - New section after `## SP2 — Changes`:
    ```markdown
    ## SP3 — Changes

    - **`root/ppg/devel/pgadmin/python3-*` (71 new)** — pgAdmin 4 `REL-9_9`'s Python 3.12 closure (cloud extras excluded), one EL spec template: PyPI sdist via `download_url`, `pip wheel --no-build-isolation` + `pip install --root` (legacy `setup.py` for 9 packages), import smoke test in `%check`, runtime deps doubled as `BuildRequires`. Build tools `python3-cython` 3.1.3, `python3-poetry-core`, `python3-pdm-backend`. bcrypt vendors its Rust crate with `cargo_vendor`.
    - **`root/ppg/common/deps/`** — `python3-dns` bumped 1.15.0 → dnspython 2.8.0 (email-validator ≥ 2.0; name kept, `python3-etcd`/`percona-patroni` rebuilt by dep-cascade); new shared build-backend stack `python3-flit-core` 3.12.0, `python3-packaging` 25.0, `python3-pathspec`, `python3-trove-classifiers`, `python3-hatchling` 1.28.0 for EL8/EL9/UBI (RHEL's backends cannot build PEP 639 metadata; EL10/openSUSE use their distro ones via a spec conditional).
    - **Version policy** — reuse RHEL 9's `python3.12-{cffi,cryptography 41,idna,pycparser,urllib3 1.26,setuptools 68}` and common:deps' `six/dateutil/psutil/click`; pinned down where PEP 639 metadata would need setuptools ≥ 77 (keyring 25.2.1, jaraco.context 6.0.1, jaraco.functools 4.1.0, importlib-resources 6.5.2, Pillow 11.1.0), bidict 0.23.1, pyotp 2.9.0, ua-parser 0.18.0.
    - **Docs** — `docs/PACKAGING_HOWTO.md` "Python 3.12 packages (pyproject builds)"; `root/README.md`.
    - Design: `docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md`.
    ```
  - Under `## Verification`, add a `**SP3**` block with: the dry-run results, the OBS `_result` end state (counts), the list of build-loop fixes (package → cause → commit), and the dnspython cascade result (python3-etcd + patroni green).
  - `gh pr edit 12 --repo percona/obs-packaging --title "<title>" --body-file <the file>`.

- [ ] **Step 3: Push the spec update**

```bash
git push percona pgadmin-sp1
```

---

## Self-review

- **Spec coverage:** §3 decisions → Tasks 1–3 (reuse via `REUSED` map, pins in Appendix B, dnspython bump and backend stack in batch A, plain directories, sdist sources, `%check` policy, naming) and Task 4 (docs). §4 inventory → Appendix B (77 entries = 71 + 6). §5 template → Appendix A `spec_text` (header, families, hatchling conditional, `%files`, `%check` with `PYTHONPATH`, changelog, trove-classifiers patch, bcrypt cargo). §6 → Global Constraints (scratchpad-only script) + Task 4. §7 verification → Tasks 1–3 dry-runs and Task 5 OBS acceptance. §8 risks → Task 5 Step 3 fix catalogue and Task 6 Step 1. §9 out of scope respected.
- **Placeholder scan:** none — every step has its command/content; the render script and data are complete in the appendices.
- **Consistency:** batch lists sum to 6 + 36 + 35 = 77 and match Appendix B's `project` fields; RPM names follow `python3-<norm>` everywhere except `python3-dns`; the docs section reproduces the exact template Appendix A emits.

---

## Appendix A — `render_stack.py` (throwaway; save to the scratchpad, do not commit)

```python
"""Render the SP3 Python 3.12 stack package directories from stack.json.

Throwaway: run once, commit the resulting package directories, never commit
this script.  Usage:  python render_stack.py <repo-root> [--only name,name]

For every entry in stack.json writes
  <repo>/root/<project-dir>/python3-<name>/package.yaml
  <repo>/root/<project-dir>/python3-<name>/obs/_service
  <repo>/root/<project-dir>/python3-<name>/rpm/python3-<name>.spec
following the spec template in docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md §5.
"""

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
STACK = json.loads((HERE / "stack.json").read_text())
TODAY = datetime.date(2026, 8, 27)  # fixed so re-runs are byte-identical
CHANGELOG_DATE = TODAY.strftime("%a %b %d %Y")

PROJECT_DIR = {"pgadmin": "ppg/devel/pgadmin", "common": "ppg/common/deps"}

# PyPI name (normalised) -> RPM name for packages we do NOT build here.
REUSED = {
    "cffi": "python3.12-cffi",
    "cryptography": "python3.12-cryptography",
    "idna": "python3.12-idna",
    "pycparser": "python3.12-pycparser",
    "urllib3": "python3.12-urllib3",
    "setuptools": "python3.12-setuptools",
    "click": "%{python3_pkgprefix}-click",
    "six": "%{python3_pkgprefix}-six",
    "python-dateutil": "%{python3_pkgprefix}-dateutil",
    "psutil": "%{python3_pkgprefix}-psutil",
    "dnspython": "%{python3_pkgprefix}-dns",
    "pluggy": "python3.12-pluggy",
}
# Classifier / free-text licence strings -> SPDX identifiers.
LICENSE = {
    "MIT License": "MIT",
    "MIT": "MIT",
    "BSD License": "BSD-3-Clause",
    "Apache Software License": "Apache-2.0",
    "Apache 2.0": "Apache-2.0",
    "ISC License (ISCL)": "ISC",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.1-or-later",
    "LGPL": "LGPL-2.1-or-later",
    "Python Software Foundation License": "PSF-2.0",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "GNU General Public License v3 or later (GPLv3+)": "GPL-3.0-or-later",
    "MIT-CMU": "MIT-CMU",
    "MPL 2.0": "MPL-2.0",
    "LGPL v3": "LGPL-3.0-only",
    "ISC License": "ISC",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "The Unlicense (Unlicense)": "Unlicense",
}
# Per-package overrides where PyPI metadata is missing or ambiguous (checked upstream).
LICENSE_BY_PKG = {
    "hatchling": "MIT",
    "python-engineio": "MIT",
    "python-socketio": "MIT",
    "bidict": "MPL-2.0",
    "ldap3": "LGPL-3.0-only",
    "pytz": "MIT",
    "shellingham": "ISC",
    "mdurl": "MIT",
    "markdown-it-py": "MIT",
    "typing-extensions": "PSF-2.0",
    "jsonformatter": "MIT",
    "libgravatar": "MIT",
    "qrcode": "BSD-3-Clause",
    "Flask-Principal": "MIT",
    "Flask-Login": "MIT",
    "simple-websocket": "MIT",
    "wsproto": "MIT",
    "ua-parser": "Apache-2.0",
    "user-agents": "MIT",
    "passlib": "BSD-3-Clause",
    "psycopg": "LGPL-3.0-only",
    "psycopg-c": "LGPL-3.0-only",
}


def spdx(pypi: str, lic: str) -> str:
    if pypi in LICENSE_BY_PKG:
        return LICENSE_BY_PKG[pypi]
    lic = lic.strip()
    return LICENSE.get(lic, lic or "see upstream")
# Directory / RPM-name exceptions.
DIRNAME = {"dnspython": "dns"}
# Import smoke-test overrides (wheel top_level.txt missing or namespace pkgs).
MODULES = {
    "Flask-Principal": ["flask_principal"],
    "jsonformatter": ["jsonformatter"],
    "psycopg-c": ["psycopg_c"],
    "jaraco.classes": ["jaraco.classes"],
    "jaraco.context": ["jaraco.context"],
    "jaraco.functools": ["jaraco.functools"],
    "backports.zstd": ["backports.zstd"],
    "poetry-core": ["poetry.core.masonry.api"],
    "pdm-backend": ["pdm.backend"],
    "flit-core": ["flit_core.buildapi"],
    "Cython": ["Cython"],
    "brotli": ["brotli"],
    "PyNaCl": ["nacl"],
}
# Self-hosting build backends: the directory to put on PYTHONPATH so the
# backend can build itself with --no-build-isolation.
SELF_HOSTING = {"hatchling": "src", "poetry-core": "src", "pdm-backend": "src", "flit-core": "."}
# Extra BuildRequires by package (beyond family defaults).
EXTRA_BR = {
    "bcrypt": ["%{python3_pkgprefix}-setuptools-rust", "cargo", "rust", "gcc"],
    "gssapi": ["%{python3_pkgprefix}-cython", "krb5-devel", "gcc"],
    "SQLAlchemy": ["%{python3_pkgprefix}-cython", "gcc"],
    "psycopg-c": ["libpq-devel", "gcc"],
    "PyNaCl": ["python3.12-cffi", "libffi-devel", "make", "gcc"],
    "pillow": ["libjpeg-turbo-devel", "zlib-devel", "gcc"],
    "backports.zstd": ["libzstd-devel", "gcc"],
    "brotli": ["gcc-c++"],
    "greenlet": ["gcc-c++"],
    "MarkupSafe": ["gcc"],
    "Cython": ["gcc"],
    "SecretStorage": [],
}
NEEDS_SCM = lambda r: bool(re.search(r"setuptools[-_]scm", r["build_requires"]))  # noqa: E731
# Build flags (package.yaml build:) — the common:deps hatchling stack only.
DISABLE_DISTRO_HATCHLING = {"hatchling", "pathspec", "trove-classifiers", "flit-core", "packaging"}
BUILD_FLAGS_DISTRO = ["RockyLinux_10", "openSUSE_Leap_16", "openSUSE_Tumbleweed"]
# pip wheel config settings.
CONFIG_SETTINGS = {
    "pillow": " ".join(
        f"-C {f}" for f in [
            "platform-guessing=disable", "zlib=enable", "jpeg=enable", "tiff=disable",
            "freetype=disable", "raqm=disable", "lcms=disable", "webp=disable",
            "xcb=disable", "jpeg2000=disable", "imagequant=disable", "avif=disable",
        ]
    )
}
# Previous changelog entries to keep (package -> text block).
OLD_CHANGELOG = {
    "dnspython": "* Mon Mar 30 2026 Percona Build/Release Team <eng-build@percona.com> - 1.15.0-1\n- Initial build of python3-dns 1.15.0\n",
}


def norm(name: str) -> str:
    return re.sub(r"[._]", "-", name.lower())


BUILT = {norm(r["pypi"]): r for r in STACK}


def rpm_dep(req: str) -> str | None:
    """PyPI requirement 'Name spec' -> 'Requires:' target, or None to drop."""
    m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", req)
    if not m:
        return None
    name, spec = norm(m.group(1)), m.group(2).strip()
    if name in REUSED:
        target = REUSED[name]
    elif name in BUILT:
        target = f"%{{python3_pkgprefix}}-{DIRNAME.get(BUILT[name]['pypi'], name)}"
    else:
        return None  # not in our closure (optional/extra dependency)
    floor = None
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        mm = re.match(r"^(>=|~=|==)\s*([0-9][0-9A-Za-z.]*)$", part)
        if mm:
            floor = mm.group(2)
    # RHEL's reused packages are older than several floors; the libraries work
    # with them (spec §3), so never emit a floor against a reused package.
    if floor and name not in REUSED:
        return f"{target} >= {floor}"
    return target


def spec_text(r: dict) -> str:
    pypi, ver = r["pypi"], r["version"]
    name = DIRNAME.get(pypi, norm(pypi))
    fam = "self-hosting" if pypi in SELF_HOSTING else r["family"]
    native = r["native"]
    sitedir = "python3_sitearch" if native else "python3_sitelib"
    lines = []
    if not native:
        lines.append("%global debug_package %{nil}\n")
    lines.append(
        "%if 0%{?rhel} && 0%{?rhel} >= 8\n"
        "%global __ospython        %{_bindir}/python3.12\n"
        "%global python3_pkgprefix python3.12\n"
        "%global python3_buildversion 3.12\n"
        "%global __requires_exclude ^python3\\\\.12dist\n"
        "%else\n"
        "%global __ospython        %{_bindir}/python3\n"
        "%global python3_pkgprefix python3\n"
        "%global python3_buildversion 3\n"
        "%endif\n"
        "%{expand: %%global py3ver %(echo `%{__ospython} -c \"import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')\" `)}\n"
    )
    if native:
        lines.append("%global python3_sitearch %(%{__ospython} -Esc \"import sysconfig; print(sysconfig.get_path('platlib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))\")\n")
    else:
        lines.append("%global python3_sitelib %(%{__ospython} -Esc \"import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))\")\n")
    lines.append(
        f"\nName:           %{{python3_pkgprefix}}-{name}\n"
        f"Version:        {ver}\n"
        "Release:        1%{?dist}\n"
        f"Summary:        {r['summary'] or pypi}\n"
        f"License:        {spdx(pypi, r['license'])}\n"
        f"URL:            {r['url']}\n"
        f"Source0:        {r['sdist_url']}\n"
    )
    if pypi == "bcrypt":
        lines.append("Source1:        vendor.tar.gz\n")
    if not native:
        lines.append("BuildArch:      noarch\n")
    lines.append(
        "Vendor:         Percona, LLC\n"
        "Packager:       Percona Development Team <https://jira.percona.com>\n"
        "Epoch:          1\n\n"
    )
    br = [
        "python%{python3_buildversion}-devel",
        "python%{python3_buildversion}-pip",
        "python%{python3_buildversion}-setuptools",
        "python%{python3_buildversion}-wheel",
    ]
    if fam == "flit":
        br.append("python%{python3_buildversion}-flit-core")
    if fam == "poetry":
        br.append("%{python3_pkgprefix}-poetry-core")
    if fam == "pdm":
        br.append("%{python3_pkgprefix}-pdm-backend")
    if NEEDS_SCM(r) and pypi not in SELF_HOSTING:
        br.append("%{python3_pkgprefix}-setuptools_scm")
    br += EXTRA_BR.get(pypi, [])
    for b in br:
        lines.append(f"BuildRequires:  {b}\n")
    if fam == "hatchling":
        lines.append(
            "%if 0%{?rhel} == 8 || 0%{?rhel} == 9\n"
            "BuildRequires:  %{python3_pkgprefix}-hatchling\n"
            "%else\n"
            "BuildRequires:  python3-hatchling\n"
            "%endif\n"
        )
    reqs = []
    for req in r["requires"]:
        dep = rpm_dep(req)
        if dep and dep not in reqs:
            reqs.append(dep)
    if reqs:
        # Runtime deps are also build deps so %check can import the module.
        lines.append("# runtime dependencies, also needed by the %check import test\n")
        for d in reqs:
            lines.append(f"BuildRequires:  {d}\n")
        lines.append("\n")
        for d in reqs:
            lines.append(f"Requires:       {d}\n")
    role = (
        "part of the pgAdmin 4 (percona-pgadmin4) dependency stack"
        if r["project"] == "pgadmin"
        else "a Python 3.12 build/runtime dependency shared by Percona PostgreSQL packages"
    )
    lines.append(f"\n%description\n{r['summary'] or pypi}.\n\nBuilt for Python 3.12 from the PyPI sdist; {role}.\n")
    # prep
    lines.append(f"\n%prep\n%autosetup -p1 -n {r['sdist_top']}")
    if pypi == "bcrypt":
        lines[-1] += " -a1"
    lines.append("\n")
    if pypi == "trove-classifiers":
        lines.append(
            "# Build without calver (not packaged): pin the version literally.\n"
            "sed -i 's/\"calver\"//; s/, *\\]/]/' pyproject.toml\n"
            "sed -i 's/use_calver=\"[^\"]*\",/version=\"%{version}\",/; /setup_requires=\\[\"calver\"\\],/d' setup.py\n"
        )
    # build / install
    if fam == "setup.py":
        lines.append(
            "\n%build\n%{__ospython} setup.py build\n\n"
            "%install\n%{__ospython} setup.py install --single-version-externally-managed -O1 --root=%{buildroot} --record=INSTALLED_FILES\n"
            f"find %{{buildroot}}%{{{sitedir}}} -mindepth 1 -type d | sed \"s|%{{buildroot}}||\" | sed 's/^/%dir /' >> INSTALLED_FILES\n"
        )
    else:
        env = ""
        if pypi in SELF_HOSTING:
            env = f"export PYTHONPATH=$PWD/{SELF_HOSTING[pypi]}\n"
        if pypi == "bcrypt":
            env += "export CARGO_NET_OFFLINE=true\nexport CARGO_HOME=$PWD/.cargo\n"
        cs = CONFIG_SETTINGS.get(pypi, "")
        lines.append(
            f"\n%build\n{env}%{{__ospython}} -m pip wheel --no-deps --no-build-isolation --no-index {cs + ' ' if cs else ''}--wheel-dir dist .\n\n"
            "%install\n%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl\n"
        )
    # check
    mods = MODULES.get(pypi) or [m for m in r["modules"] if not m.startswith("_")]
    # Import from the installed buildroot (src-layout packages are not importable
    # from the source directory).
    lines.append(
        f"\n%check\nPYTHONPATH=%{{buildroot}}%{{{sitedir}}} %{{__ospython}} -c \"{'; '.join('import ' + m for m in mods)}\"\n"
    )
    # files
    if fam == "setup.py":
        lines.append("\n%files -f INSTALLED_FILES\n%defattr(-,root,root)\n")
    else:
        lines.append(f"\n%files\n%{{{sitedir}}}/*\n")
    for s in r["scripts"]:
        lines.append(f"%{{_bindir}}/{s}\n")
    # changelog
    what = "pgAdmin 4 dependency stack" if r["project"] == "pgadmin" else "shared Python 3.12 build stack"
    if pypi == "dnspython":
        what = "bump to 2.8.0 (email-validator needs >= 2.0); built with hatchling"
    lines.append(
        f"\n%changelog\n* {CHANGELOG_DATE} Percona Development Team <info@percona.com> - {ver}-1\n"
        f"- Package {pypi} {ver} for Python 3.12 ({what})\n"
    )
    if pypi in OLD_CHANGELOG:
        lines.append("\n" + OLD_CHANGELOG[pypi])
    return "".join(lines)


def service_text(r: dict) -> str:
    s = "<services>\n  <service name=\"download_url\">\n" f"    <param name=\"url\">{r['sdist_url']}</param>\n  </service>\n"
    if r["pypi"] == "bcrypt":
        s += (
            "  <!-- Vendor the Rust crate's dependencies (Cargo.toml lives under src/_bcrypt)\n"
            "       for an offline OBS build; produces vendor.tar.gz incl. .cargo/config. -->\n"
            "  <service mode=\"buildtime\" name=\"cargo_vendor\">\n"
            f"    <param name=\"src\">{r['sdist_filename']}</param>\n"
            "    <param name=\"cargotoml\">src/_bcrypt/Cargo.toml</param>\n"
            "    <param name=\"compression\">gz</param>\n"
            "    <param name=\"update\">false</param>\n"
            "  </service>\n"
        )
    return s + "</services>\n"


def package_yaml(r: dict) -> str:
    pypi, ver = r["pypi"], r["version"]
    who = "pgAdmin 4 (percona-pgadmin4)" if r["project"] == "pgadmin" else "Percona PostgreSQL packages"
    text = (
        f"title: {pypi} {ver} for Python 3.12\n"
        "description: |\n"
        f"  {r['summary'] or pypi}. RPM-only python3.12-* build from the PyPI sdist,\n"
        f"  consumed by {who}. Bump by editing obs/_service (sdist URL) and\n"
        "  rpm/*.spec (Version + changelog).\n"
    )
    if pypi in DISABLE_DISTRO_HATCHLING:
        text += "\n# EL10 and openSUSE ship python3-hatchling & friends; only EL8/EL9/UBI need ours.\nbuild:\n"
        for f in BUILD_FLAGS_DISTRO:
            text += f"  {f}: false\n"
    return text


def main(argv):
    repo = Path(argv[1]).resolve()
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
    for r in STACK:
        if only and r["pypi"] not in only and norm(r["pypi"]) not in only:
            continue
        name = DIRNAME.get(r["pypi"], norm(r["pypi"]))
        pkg = repo / "root" / PROJECT_DIR[r["project"]] / f"python3-{name}"
        (pkg / "obs").mkdir(parents=True, exist_ok=True)
        (pkg / "rpm").mkdir(parents=True, exist_ok=True)
        (pkg / "package.yaml").write_text(package_yaml(r))
        (pkg / "obs" / "_service").write_text(service_text(r))
        (pkg / "rpm" / f"python3-{name}.spec").write_text(spec_text(r))
        print(pkg.relative_to(repo))


if __name__ == "__main__":
    main(sys.argv)
```

## Appendix B — `stack.json` (data for Appendix A; save next to it as `stack.json`, do not commit)

```json
[
 {
  "pypi": "alembic",
  "version": "1.19.1",
  "project": "pgadmin",
  "summary": "A database migration tool for SQLAlchemy",
  "url": "https://alembic.sqlalchemy.org",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/a/alembic/alembic-1.19.1.tar.gz",
  "sdist_filename": "alembic-1.19.1.tar.gz",
  "sdist_top": "alembic-1.19.1",
  "family": "setuptools",
  "native": false,
  "requires": [
   "SQLAlchemy >=1.4.23",
   "Mako",
   "typing-extensions >=4.12"
  ],
  "build_requires": "\"setuptools>=77.0.3\"",
  "scripts": [
   "alembic"
  ],
  "modules": [
   "alembic"
  ]
 },
 {
  "pypi": "Authlib",
  "version": "1.6.12",
  "project": "pgadmin",
  "summary": "The ultimate Python library in building OAuth and OpenID Connect servers and clients",
  "url": "https://github.com/authlib/authlib",
  "license": "BSD-3-Clause",
  "sdist_url": "https://files.pythonhosted.org/packages/source/A/Authlib/authlib-1.6.12.tar.gz",
  "sdist_filename": "authlib-1.6.12.tar.gz",
  "sdist_top": "authlib-1.6.12",
  "family": "setuptools",
  "native": false,
  "requires": [
   "cryptography"
  ],
  "build_requires": "\"setuptools\", \"wheel\"",
  "scripts": [],
  "modules": [
   "authlib"
  ]
 },
 {
  "pypi": "babel",
  "version": "2.18.0",
  "project": "pgadmin",
  "summary": "Internationalization utilities",
  "url": "https://babel.pocoo.org/",
  "license": "BSD-3-Clause",
  "sdist_url": "https://files.pythonhosted.org/packages/source/b/babel/babel-2.18.0.tar.gz",
  "sdist_filename": "babel-2.18.0.tar.gz",
  "sdist_top": "babel-2.18.0",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "",
  "scripts": [
   "pybabel"
  ],
  "modules": [
   "babel"
  ]
 },
 {
  "pypi": "backports.zstd",
  "version": "1.7.0",
  "project": "pgadmin",
  "summary": "Backport of compression.zstd",
  "url": "https://github.com/rogdham/backports.zstd",
  "license": "PSF-2.0",
  "sdist_url": "https://files.pythonhosted.org/packages/source/b/backports.zstd/backports_zstd-1.7.0.tar.gz",
  "sdist_filename": "backports_zstd-1.7.0.tar.gz",
  "sdist_top": "backports_zstd-1.7.0",
  "family": "setuptools",
  "native": true,
  "requires": [],
  "build_requires": "\"setuptools>=80\"",
  "scripts": [],
  "modules": [
   "backports"
  ]
 },
 {
  "pypi": "bcrypt",
  "version": "5.0.0",
  "project": "pgadmin",
  "summary": "Modern password hashing for your software and your servers",
  "url": "https://pypi.org/project/bcrypt/",
  "license": "Apache-2.0",
  "sdist_url": "https://files.pythonhosted.org/packages/source/b/bcrypt/bcrypt-5.0.0.tar.gz",
  "sdist_filename": "bcrypt-5.0.0.tar.gz",
  "sdist_top": "bcrypt-5.0.0",
  "family": "setuptools",
  "native": true,
  "requires": [],
  "build_requires": "\"setuptools>=42.0.0\", \"wheel\", \"setuptools-rust>=1.7.0\",",
  "scripts": [],
  "modules": [
   "bcrypt"
  ]
 },
 {
  "pypi": "bidict",
  "version": "0.23.1",
  "project": "pgadmin",
  "summary": "The bidirectional mapping library for Python",
  "url": "https://pypi.org/project/bidict/",
  "license": "MPL 2.0",
  "sdist_url": "https://files.pythonhosted.org/packages/source/b/bidict/bidict-0.23.1.tar.gz",
  "sdist_filename": "bidict-0.23.1.tar.gz",
  "sdist_top": "bidict-0.23.1",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "\"setuptools >= 40.9.0\"",
  "scripts": [],
  "modules": [
   "bidict"
  ]
 },
 {
  "pypi": "blinker",
  "version": "1.9.0",
  "project": "pgadmin",
  "summary": "Fast, simple object-to-object and broadcast signaling",
  "url": "https://github.com/pallets-eco/blinker/",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/b/blinker/blinker-1.9.0.tar.gz",
  "sdist_filename": "blinker-1.9.0.tar.gz",
  "sdist_top": "blinker-1.9.0",
  "family": "flit",
  "native": false,
  "requires": [],
  "build_requires": "\"flit_core<4\"",
  "scripts": [],
  "modules": [
   "blinker"
  ]
 },
 {
  "pypi": "brotli",
  "version": "1.2.0",
  "project": "pgadmin",
  "summary": "Python bindings for the Brotli compression library",
  "url": "https://github.com/google/brotli",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/b/brotli/brotli-1.2.0.tar.gz",
  "sdist_filename": "brotli-1.2.0.tar.gz",
  "sdist_top": "brotli-1.2.0",
  "family": "setuptools",
  "native": true,
  "requires": [],
  "build_requires": "\"setuptools\", \"pkgconfig\"",
  "scripts": [],
  "modules": [
   "brotli"
  ]
 },
 {
  "pypi": "decorator",
  "version": "5.3.1",
  "project": "pgadmin",
  "summary": "Decorators for Humans",
  "url": "https://pypi.org/project/decorator/",
  "license": "BSD-2-Clause",
  "sdist_url": "https://files.pythonhosted.org/packages/source/d/decorator/decorator-5.3.1.tar.gz",
  "sdist_filename": "decorator-5.3.1.tar.gz",
  "sdist_top": "decorator-5.3.1",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "\"setuptools>=77.0.0\"",
  "scripts": [],
  "modules": [
   "decorator"
  ]
 },
 {
  "pypi": "email-validator",
  "version": "2.3.0",
  "project": "pgadmin",
  "summary": "A robust email address syntax and deliverability validation library",
  "url": "https://github.com/JoshData/python-email-validator",
  "license": "Unlicense",
  "sdist_url": "https://files.pythonhosted.org/packages/source/e/email-validator/email_validator-2.3.0.tar.gz",
  "sdist_filename": "email_validator-2.3.0.tar.gz",
  "sdist_top": "email_validator-2.3.0",
  "family": "setuptools",
  "native": false,
  "requires": [
   "dnspython >=2.0.0",
   "idna >=2.0.0"
  ],
  "build_requires": "",
  "scripts": [
   "email_validator"
  ],
  "modules": [
   "email_validator"
  ]
 },
 {
  "pypi": "Flask",
  "version": "3.1.3",
  "project": "pgadmin",
  "summary": "A simple framework for building complex web applications",
  "url": "https://github.com/pallets/flask/",
  "license": "BSD-3-Clause",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask/flask-3.1.3.tar.gz",
  "sdist_filename": "flask-3.1.3.tar.gz",
  "sdist_top": "flask-3.1.3",
  "family": "flit",
  "native": false,
  "requires": [
   "blinker >=1.9.0",
   "click >=8.1.3",
   "itsdangerous >=2.2.0",
   "jinja2 >=3.1.2",
   "markupsafe >=2.1.1",
   "werkzeug >=3.1.0"
  ],
  "build_requires": "\"flit_core>=3.11,<4\"",
  "scripts": [
   "flask"
  ],
  "modules": [
   "flask"
  ]
 },
 {
  "pypi": "flask-babel",
  "version": "4.0.0",
  "project": "pgadmin",
  "summary": "Adds i18n/l10n support for Flask applications",
  "url": "https://github.com/python-babel/flask-babel",
  "license": "BSD-3-Clause",
  "sdist_url": "https://files.pythonhosted.org/packages/source/f/flask-babel/flask_babel-4.0.0.tar.gz",
  "sdist_filename": "flask_babel-4.0.0.tar.gz",
  "sdist_top": "flask_babel-4.0.0",
  "family": "poetry",
  "native": false,
  "requires": [
   "pytz (>=2022.7)",
   "Flask (>=2.0)",
   "Babel (>=2.12)",
   "Jinja2 (>=3.1)"
  ],
  "build_requires": "\"poetry-core>=1.0.0\"",
  "scripts": [],
  "modules": [
   "flask_babel"
  ]
 },
 {
  "pypi": "Flask-Compress",
  "version": "1.24",
  "project": "pgadmin",
  "summary": "Compress responses in your Flask app with gzip, deflate, brotli or zstandard",
  "url": "https://github.com/colour-science/flask-compress",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-Compress/flask_compress-1.24.tar.gz",
  "sdist_filename": "flask_compress-1.24.tar.gz",
  "sdist_top": "flask_compress-1.24",
  "family": "setuptools",
  "native": false,
  "requires": [
   "flask",
   "brotli",
   "backports.zstd"
  ],
  "build_requires": "\"setuptools>=42\", \"wheel\", \"setuptools_scm[toml",
  "scripts": [],
  "modules": [
   "flask_compress"
  ]
 },
 {
  "pypi": "Flask-Login",
  "version": "0.6.3",
  "project": "pgadmin",
  "summary": "User authentication and session management for Flask",
  "url": "https://github.com/maxcountryman/flask-login",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-Login/Flask-Login-0.6.3.tar.gz",
  "sdist_filename": "Flask-Login-0.6.3.tar.gz",
  "sdist_top": "Flask-Login-0.6.3",
  "family": "setup.py",
  "native": false,
  "requires": [
   "Flask >=1.0.4",
   "Werkzeug >=1.0.1"
  ],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "flask_login"
  ]
 },
 {
  "pypi": "Flask-Mail",
  "version": "0.10.0",
  "project": "pgadmin",
  "summary": "Flask extension for sending email",
  "url": "https://github.com/pallets-eco/flask-mail/",
  "license": "BSD License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-Mail/flask_mail-0.10.0.tar.gz",
  "sdist_filename": "flask_mail-0.10.0.tar.gz",
  "sdist_top": "flask_mail-0.10.0",
  "family": "flit",
  "native": false,
  "requires": [
   "flask",
   "blinker"
  ],
  "build_requires": "\"flit_core<4\"",
  "scripts": [],
  "modules": [
   "flask_mail"
  ]
 },
 {
  "pypi": "Flask-Migrate",
  "version": "4.1.0",
  "project": "pgadmin",
  "summary": "SQLAlchemy database migrations for Flask applications using Alembic",
  "url": "https://github.com/miguelgrinberg/flask-migrate",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-Migrate/flask_migrate-4.1.0.tar.gz",
  "sdist_filename": "flask_migrate-4.1.0.tar.gz",
  "sdist_top": "flask_migrate-4.1.0",
  "family": "setuptools",
  "native": false,
  "requires": [
   "Flask >=0.9",
   "Flask-SQLAlchemy >=1.0",
   "alembic >=1.9.0"
  ],
  "build_requires": "\"setuptools>=61.2\",",
  "scripts": [],
  "modules": [
   "flask_migrate"
  ]
 },
 {
  "pypi": "Flask-Paranoid",
  "version": "0.3.0",
  "project": "pgadmin",
  "summary": "Simple user session protection",
  "url": "https://github.com/miguelgrinberg/flask-paranoid",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-Paranoid/Flask-Paranoid-0.3.0.tar.gz",
  "sdist_filename": "Flask-Paranoid-0.3.0.tar.gz",
  "sdist_top": "Flask-Paranoid-0.3.0",
  "family": "setuptools",
  "native": false,
  "requires": [
   "Flask (>=0.10)"
  ],
  "build_requires": "\"setuptools>=42\", \"wheel\"",
  "scripts": [],
  "modules": [
   "flask_paranoid"
  ]
 },
 {
  "pypi": "Flask-Principal",
  "version": "0.4.0",
  "project": "pgadmin",
  "summary": "Identity management for flask",
  "url": "http://packages.python.org/Flask-Principal/",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-Principal/Flask-Principal-0.4.0.tar.gz",
  "sdist_filename": "Flask-Principal-0.4.0.tar.gz",
  "sdist_top": "Flask-Principal-0.4.0",
  "family": "setup.py",
  "native": false,
  "requires": [],
  "build_requires": "",
  "scripts": [],
  "modules": []
 },
 {
  "pypi": "Flask-Security-Too",
  "version": "5.6.2",
  "project": "pgadmin",
  "summary": "Quickly add security features to your Flask application",
  "url": "https://github.com/pallets-eco/flask-security",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-Security-Too/flask_security_too-5.6.2.tar.gz",
  "sdist_filename": "flask_security_too-5.6.2.tar.gz",
  "sdist_top": "flask_security_too-5.6.2",
  "family": "flit",
  "native": false,
  "requires": [
   "Flask >=3.0.0",
   "Flask-Login >=0.6.3",
   "Flask-Principal >=0.4.0",
   "Flask-WTF >=1.1.2",
   "email-validator >=2.0.0",
   "markupsafe >=2.1.0",
   "passlib >=1.7.4",
   "setuptools",
   "wtforms >=3.0.0",
   "importlib_resources >=5.10.0"
  ],
  "build_requires": "\"flit_core >=3.8,<4\"",
  "scripts": [],
  "modules": [
   "flask_security"
  ]
 },
 {
  "pypi": "Flask-SocketIO",
  "version": "5.5.1",
  "project": "pgadmin",
  "summary": "Socket.IO integration for Flask applications",
  "url": "https://github.com/miguelgrinberg/flask-socketio",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-SocketIO/flask_socketio-5.5.1.tar.gz",
  "sdist_filename": "flask_socketio-5.5.1.tar.gz",
  "sdist_top": "flask_socketio-5.5.1",
  "family": "setuptools",
  "native": false,
  "requires": [
   "Flask >=0.9",
   "python-socketio >=5.12.0"
  ],
  "build_requires": "\"setuptools>=61.2\",",
  "scripts": [],
  "modules": [
   "flask_socketio"
  ]
 },
 {
  "pypi": "Flask-SQLAlchemy",
  "version": "3.1.1",
  "project": "pgadmin",
  "summary": "Add SQLAlchemy support to your Flask application",
  "url": "https://pypi.org/project/Flask-SQLAlchemy/",
  "license": "BSD License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-SQLAlchemy/flask_sqlalchemy-3.1.1.tar.gz",
  "sdist_filename": "flask_sqlalchemy-3.1.1.tar.gz",
  "sdist_top": "flask_sqlalchemy-3.1.1",
  "family": "flit",
  "native": false,
  "requires": [
   "flask >=2.2.5",
   "sqlalchemy >=2.0.16"
  ],
  "build_requires": "\"flit_core<4\"",
  "scripts": [],
  "modules": [
   "flask_sqlalchemy"
  ]
 },
 {
  "pypi": "Flask-WTF",
  "version": "1.2.2",
  "project": "pgadmin",
  "summary": "Form rendering, validation, and CSRF protection for Flask with WTForms",
  "url": "https://pypi.org/project/Flask-WTF/",
  "license": "BSD License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-WTF/flask_wtf-1.2.2.tar.gz",
  "sdist_filename": "flask_wtf-1.2.2.tar.gz",
  "sdist_top": "flask_wtf-1.2.2",
  "family": "hatchling",
  "native": false,
  "requires": [
   "flask",
   "itsdangerous",
   "wtforms"
  ],
  "build_requires": "\"hatchling\"",
  "scripts": [],
  "modules": [
   "flask_wtf"
  ]
 },
 {
  "pypi": "greenlet",
  "version": "3.5.5",
  "project": "pgadmin",
  "summary": "Lightweight in-process concurrent programming",
  "url": "https://greenlet.readthedocs.io",
  "license": "MIT AND PSF-2.0",
  "sdist_url": "https://files.pythonhosted.org/packages/source/g/greenlet/greenlet-3.5.5.tar.gz",
  "sdist_filename": "greenlet-3.5.5.tar.gz",
  "sdist_top": "greenlet-3.5.5",
  "family": "setuptools",
  "native": true,
  "requires": [],
  "build_requires": "\"setuptools >= 77.0.3\"",
  "scripts": [],
  "modules": [
   "greenlet"
  ]
 },
 {
  "pypi": "gssapi",
  "version": "1.10.1",
  "project": "pgadmin",
  "summary": "Python GSSAPI Wrapper",
  "url": "https://github.com/pythongssapi/python-gssapi",
  "license": "ISC",
  "sdist_url": "https://files.pythonhosted.org/packages/source/g/gssapi/gssapi-1.10.1.tar.gz",
  "sdist_filename": "gssapi-1.10.1.tar.gz",
  "sdist_top": "gssapi-1.10.1",
  "family": "setuptools",
  "native": true,
  "requires": [
   "decorator"
  ],
  "build_requires": "\"Cython == 3.1.3\", \"setuptools >= 40.6.0\", # Start of PEP 517 support for setuptools",
  "scripts": [],
  "modules": [
   "gssapi"
  ]
 },
 {
  "pypi": "h11",
  "version": "0.16.0",
  "project": "pgadmin",
  "summary": "A pure-Python, bring-your-own-I/O implementation of HTTP/1.1",
  "url": "https://github.com/python-hyper/h11",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/h/h11/h11-0.16.0.tar.gz",
  "sdist_filename": "h11-0.16.0.tar.gz",
  "sdist_top": "h11-0.16.0",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "h11"
  ]
 },
 {
  "pypi": "importlib-resources",
  "version": "6.5.2",
  "project": "pgadmin",
  "summary": "Read resources from Python packages",
  "url": "https://github.com/python/importlib_resources",
  "license": "Apache Software License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/i/importlib-resources/importlib_resources-6.5.2.tar.gz",
  "sdist_filename": "importlib_resources-6.5.2.tar.gz",
  "sdist_top": "importlib_resources-6.5.2",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "\"setuptools>=61.2\", \"setuptools_scm[toml",
  "scripts": [],
  "modules": [
   "importlib_resources"
  ]
 },
 {
  "pypi": "itsdangerous",
  "version": "2.2.0",
  "project": "pgadmin",
  "summary": "Safely pass data to untrusted environments and back",
  "url": "https://github.com/pallets/itsdangerous/",
  "license": "BSD License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/i/itsdangerous/itsdangerous-2.2.0.tar.gz",
  "sdist_filename": "itsdangerous-2.2.0.tar.gz",
  "sdist_top": "itsdangerous-2.2.0",
  "family": "flit",
  "native": false,
  "requires": [],
  "build_requires": "\"flit_core<4\"",
  "scripts": [],
  "modules": [
   "itsdangerous"
  ]
 },
 {
  "pypi": "jaraco.classes",
  "version": "3.4.0",
  "project": "pgadmin",
  "summary": "Utility functions for Python class constructs",
  "url": "https://github.com/jaraco/jaraco.classes",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/j/jaraco.classes/jaraco.classes-3.4.0.tar.gz",
  "sdist_filename": "jaraco.classes-3.4.0.tar.gz",
  "sdist_top": "jaraco.classes-3.4.0",
  "family": "setuptools",
  "native": false,
  "requires": [
   "more-itertools"
  ],
  "build_requires": "\"setuptools>=56\", \"setuptools_scm[toml",
  "scripts": [],
  "modules": [
   "jaraco"
  ]
 },
 {
  "pypi": "jaraco.context",
  "version": "6.0.1",
  "project": "pgadmin",
  "summary": "Useful decorators and context managers",
  "url": "https://github.com/jaraco/jaraco.context",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/j/jaraco.context/jaraco_context-6.0.1.tar.gz",
  "sdist_filename": "jaraco_context-6.0.1.tar.gz",
  "sdist_top": "jaraco_context-6.0.1",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "\"setuptools>=61.2\", \"setuptools_scm[toml",
  "scripts": [],
  "modules": [
   "jaraco"
  ]
 },
 {
  "pypi": "jaraco.functools",
  "version": "4.1.0",
  "project": "pgadmin",
  "summary": "Functools like those found in stdlib",
  "url": "https://github.com/jaraco/jaraco.functools",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/j/jaraco.functools/jaraco_functools-4.1.0.tar.gz",
  "sdist_filename": "jaraco_functools-4.1.0.tar.gz",
  "sdist_top": "jaraco_functools-4.1.0",
  "family": "setuptools",
  "native": false,
  "requires": [
   "more-itertools"
  ],
  "build_requires": "\"setuptools>=61.2\", \"setuptools_scm[toml",
  "scripts": [],
  "modules": [
   "jaraco"
  ]
 },
 {
  "pypi": "jeepney",
  "version": "0.9.0",
  "project": "pgadmin",
  "summary": "Low-level, pure Python DBus protocol wrapper",
  "url": "https://gitlab.com/takluyver/jeepney",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/j/jeepney/jeepney-0.9.0.tar.gz",
  "sdist_filename": "jeepney-0.9.0.tar.gz",
  "sdist_top": "jeepney-0.9.0",
  "family": "flit",
  "native": false,
  "requires": [],
  "build_requires": "\"flit_core >=3.11,<4\"",
  "scripts": [],
  "modules": [
   "jeepney"
  ]
 },
 {
  "pypi": "Jinja2",
  "version": "3.1.6",
  "project": "pgadmin",
  "summary": "A very fast and expressive template engine",
  "url": "https://github.com/pallets/jinja/",
  "license": "BSD License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/J/Jinja2/jinja2-3.1.6.tar.gz",
  "sdist_filename": "jinja2-3.1.6.tar.gz",
  "sdist_top": "jinja2-3.1.6",
  "family": "flit",
  "native": false,
  "requires": [
   "MarkupSafe >=2.0"
  ],
  "build_requires": "\"flit_core<4\"",
  "scripts": [],
  "modules": [
   "jinja2"
  ]
 },
 {
  "pypi": "jsonformatter",
  "version": "0.3.4",
  "project": "pgadmin",
  "summary": "Python log in json format",
  "url": "https://github.com/MyColorfulDays/jsonformatter.git",
  "license": "BSD License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/j/jsonformatter/jsonformatter-0.3.4.tar.gz",
  "sdist_filename": "jsonformatter-0.3.4.tar.gz",
  "sdist_top": "jsonformatter-0.3.4",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "\"setuptools\"",
  "scripts": [],
  "modules": []
 },
 {
  "pypi": "keyring",
  "version": "25.2.1",
  "project": "pgadmin",
  "summary": "Store and access your passwords safely",
  "url": "https://github.com/jaraco/keyring",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/k/keyring/keyring-25.2.1.tar.gz",
  "sdist_filename": "keyring-25.2.1.tar.gz",
  "sdist_top": "keyring-25.2.1",
  "family": "setuptools",
  "native": false,
  "requires": [
   "jaraco.classes",
   "jaraco.functools",
   "jaraco.context",
   "SecretStorage >=3.2",
   "jeepney >=0.4.2"
  ],
  "build_requires": "\"setuptools>=61.2\", \"setuptools_scm[toml",
  "scripts": [
   "keyring"
  ],
  "modules": [
   "keyring"
  ]
 },
 {
  "pypi": "ldap3",
  "version": "2.9.1",
  "project": "pgadmin",
  "summary": "A strictly RFC 4510 conforming LDAP V3 pure Python client library",
  "url": "https://github.com/cannatag/ldap3",
  "license": "LGPL v3",
  "sdist_url": "https://files.pythonhosted.org/packages/source/l/ldap3/ldap3-2.9.1.tar.gz",
  "sdist_filename": "ldap3-2.9.1.tar.gz",
  "sdist_top": "ldap3-2.9.1",
  "family": "setup.py",
  "native": false,
  "requires": [
   "pyasn1 (>=0.4.6)"
  ],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "ldap3"
  ]
 },
 {
  "pypi": "libgravatar",
  "version": "1.0.4",
  "project": "pgadmin",
  "summary": "A library that provides a Python 3 interface for the Gravatar API",
  "url": "https://github.com/pabluk/libgravatar",
  "license": "GNU General Public License v3 (GPLv3)",
  "sdist_url": "https://files.pythonhosted.org/packages/source/l/libgravatar/libgravatar-1.0.4.tar.gz",
  "sdist_filename": "libgravatar-1.0.4.tar.gz",
  "sdist_top": "libgravatar-1.0.4",
  "family": "setup.py",
  "native": false,
  "requires": [],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "libgravatar"
  ]
 },
 {
  "pypi": "Mako",
  "version": "1.4.1",
  "project": "pgadmin",
  "summary": "A super-fast templating language that borrows the best ideas from the existing templating languages",
  "url": "https://www.makotemplates.org/",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/M/Mako/mako-1.4.1.tar.gz",
  "sdist_filename": "mako-1.4.1.tar.gz",
  "sdist_top": "mako-1.4.1",
  "family": "setuptools",
  "native": false,
  "requires": [
   "MarkupSafe >=2.0"
  ],
  "build_requires": "\"setuptools>=77.0.0\"",
  "scripts": [
   "mako-render"
  ],
  "modules": [
   "mako"
  ]
 },
 {
  "pypi": "markdown-it-py",
  "version": "4.2.0",
  "project": "pgadmin",
  "summary": "Python port of markdown-it. Markdown parsing, done right!",
  "url": "https://github.com/executablebooks/markdown-it-py",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/m/markdown-it-py/markdown_it_py-4.2.0.tar.gz",
  "sdist_filename": "markdown_it_py-4.2.0.tar.gz",
  "sdist_top": "markdown_it_py-4.2.0",
  "family": "flit",
  "native": false,
  "requires": [
   "mdurl ~=0.1"
  ],
  "build_requires": "\"flit_core >=3.4,<4\"",
  "scripts": [
   "markdown-it"
  ],
  "modules": [
   "markdown_it"
  ]
 },
 {
  "pypi": "MarkupSafe",
  "version": "3.0.3",
  "project": "pgadmin",
  "summary": "Safely add untrusted strings to HTML/XML markup",
  "url": "https://github.com/pallets/markupsafe/",
  "license": "BSD-3-Clause",
  "sdist_url": "https://files.pythonhosted.org/packages/source/M/MarkupSafe/markupsafe-3.0.3.tar.gz",
  "sdist_filename": "markupsafe-3.0.3.tar.gz",
  "sdist_top": "markupsafe-3.0.3",
  "family": "setuptools",
  "native": true,
  "requires": [],
  "build_requires": "\"setuptools>=77\"",
  "scripts": [],
  "modules": [
   "markupsafe"
  ]
 },
 {
  "pypi": "mdurl",
  "version": "0.1.2",
  "project": "pgadmin",
  "summary": "Markdown URL utilities",
  "url": "https://github.com/executablebooks/mdurl",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/m/mdurl/mdurl-0.1.2.tar.gz",
  "sdist_filename": "mdurl-0.1.2.tar.gz",
  "sdist_top": "mdurl-0.1.2",
  "family": "flit",
  "native": false,
  "requires": [],
  "build_requires": "\"flit_core>=3.2.0,<4\"",
  "scripts": [],
  "modules": [
   "mdurl"
  ]
 },
 {
  "pypi": "more-itertools",
  "version": "11.1.0",
  "project": "pgadmin",
  "summary": "More routines for operating on iterables, beyond itertools",
  "url": "https://github.com/more-itertools/more-itertools",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/m/more-itertools/more_itertools-11.1.0.tar.gz",
  "sdist_filename": "more_itertools-11.1.0.tar.gz",
  "sdist_top": "more_itertools-11.1.0",
  "family": "flit",
  "native": false,
  "requires": [],
  "build_requires": "\"flit_core >=3.12,<4\"",
  "scripts": [],
  "modules": [
   "more_itertools"
  ]
 },
 {
  "pypi": "paramiko",
  "version": "3.5.1",
  "project": "pgadmin",
  "summary": "SSH2 protocol library",
  "url": "https://paramiko.org",
  "license": "LGPL",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/paramiko/paramiko-3.5.1.tar.gz",
  "sdist_filename": "paramiko-3.5.1.tar.gz",
  "sdist_top": "paramiko-3.5.1",
  "family": "setup.py",
  "native": false,
  "requires": [
   "bcrypt >=3.2",
   "cryptography >=3.3",
   "pynacl >=1.5"
  ],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "paramiko"
  ]
 },
 {
  "pypi": "passlib",
  "version": "1.7.4",
  "project": "pgadmin",
  "summary": "comprehensive password hashing framework supporting over 30 schemes",
  "url": "https://passlib.readthedocs.io",
  "license": "BSD",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/passlib/passlib-1.7.4.tar.gz",
  "sdist_filename": "passlib-1.7.4.tar.gz",
  "sdist_top": "passlib-1.7.4",
  "family": "setup.py",
  "native": false,
  "requires": [],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "passlib"
  ]
 },
 {
  "pypi": "pillow",
  "version": "11.1.0",
  "project": "pgadmin",
  "summary": "Python Imaging Library (Fork)",
  "url": "https://python-pillow.github.io",
  "license": "MIT-CMU",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/pillow/pillow-11.1.0.tar.gz",
  "sdist_filename": "pillow-11.1.0.tar.gz",
  "sdist_top": "pillow-11.1.0",
  "family": "setuptools",
  "native": true,
  "requires": [],
  "build_requires": "\"setuptools>=67.8\",",
  "scripts": [],
  "modules": [
   "PIL"
  ]
 },
 {
  "pypi": "psycopg",
  "version": "3.2.10",
  "project": "pgadmin",
  "summary": "PostgreSQL database adapter for Python",
  "url": "https://psycopg.org/",
  "license": "GNU Lesser General Public License v3 (LGPLv3)",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/psycopg/psycopg-3.2.10.tar.gz",
  "sdist_filename": "psycopg-3.2.10.tar.gz",
  "sdist_top": "psycopg-3.2.10",
  "family": "setuptools",
  "native": false,
  "requires": [
   "typing-extensions >=4.6"
  ],
  "build_requires": "\"setuptools>=49.2.0\", \"wheel>=0.37\"",
  "scripts": [],
  "modules": [
   "psycopg"
  ]
 },
 {
  "pypi": "psycopg-c",
  "version": "3.2.10",
  "project": "pgadmin",
  "summary": "PostgreSQL database adapter for Python -- C optimisation distribution",
  "url": "https://psycopg.org/",
  "license": "GNU Lesser General Public License v3 (LGPLv3)",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/psycopg-c/psycopg_c-3.2.10.tar.gz",
  "sdist_filename": "psycopg_c-3.2.10.tar.gz",
  "sdist_top": "psycopg_c-3.2.10",
  "family": "setuptools",
  "native": true,
  "requires": [],
  "build_requires": "\"setuptools >= 49.2.0\", \"wheel >= 0.37\", \"tomli >= 2.0.1; python_version < '3.11'\",",
  "scripts": [],
  "modules": []
 },
 {
  "pypi": "pyasn1",
  "version": "0.6.4",
  "project": "pgadmin",
  "summary": "Pure-Python implementation of ASN.1 types and DER/BER/CER codecs (X.208)",
  "url": "https://github.com/pyasn1/pyasn1",
  "license": "BSD-2-Clause",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/pyasn1/pyasn1-0.6.4.tar.gz",
  "sdist_filename": "pyasn1-0.6.4.tar.gz",
  "sdist_top": "pyasn1-0.6.4",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "\"setuptools\"",
  "scripts": [],
  "modules": [
   "pyasn1"
  ]
 },
 {
  "pypi": "Pygments",
  "version": "2.21.0",
  "project": "pgadmin",
  "summary": "Pygments is a syntax highlighting package written in Python",
  "url": "https://pygments.org",
  "license": "BSD-2-Clause",
  "sdist_url": "https://files.pythonhosted.org/packages/source/P/Pygments/pygments-2.21.0.tar.gz",
  "sdist_filename": "pygments-2.21.0.tar.gz",
  "sdist_top": "pygments-2.21.0",
  "family": "hatchling",
  "native": false,
  "requires": [],
  "build_requires": "\"hatchling>=1.27\"",
  "scripts": [
   "pygmentize"
  ],
  "modules": [
   "pygments"
  ]
 },
 {
  "pypi": "PyNaCl",
  "version": "1.6.2",
  "project": "pgadmin",
  "summary": "Python binding to the Networking and Cryptography (NaCl) library",
  "url": "https://github.com/pyca/pynacl",
  "license": "Apache-2.0",
  "sdist_url": "https://files.pythonhosted.org/packages/source/P/PyNaCl/pynacl-1.6.2.tar.gz",
  "sdist_filename": "pynacl-1.6.2.tar.gz",
  "sdist_top": "pynacl-1.6.2",
  "family": "setuptools",
  "native": true,
  "requires": [
   "cffi >=2.0.0"
  ],
  "build_requires": "\"setuptools>=61.0.0,!=74.0.0\", \"wheel\", \"cffi>=1.4.1; platform_python_implementation != 'PyPy' and python_version < '3.9'\", \"cffi>=2.0.0; platform_python_implementation != 'PyPy' and python_version >= '3.9'\",",
  "scripts": [],
  "modules": [
   "nacl"
  ]
 },
 {
  "pypi": "PyOTP",
  "version": "2.9.0",
  "project": "pgadmin",
  "summary": "Python One Time Password Library",
  "url": "https://github.com/pyotp/pyotp",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/P/PyOTP/pyotp-2.9.0.tar.gz",
  "sdist_filename": "pyotp-2.9.0.tar.gz",
  "sdist_top": "pyotp-2.9.0",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "pyotp"
  ]
 },
 {
  "pypi": "python-engineio",
  "version": "4.13.5",
  "project": "pgadmin",
  "summary": "Engine.IO server and client for Python",
  "url": "https://github.com/miguelgrinberg/python-engineio",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/python-engineio/python_engineio-4.13.5.tar.gz",
  "sdist_filename": "python_engineio-4.13.5.tar.gz",
  "sdist_top": "python_engineio-4.13.5",
  "family": "setuptools",
  "native": false,
  "requires": [
   "simple-websocket >=0.10.0"
  ],
  "build_requires": "\"setuptools>=61.2\"",
  "scripts": [],
  "modules": [
   "engineio"
  ]
 },
 {
  "pypi": "python-socketio",
  "version": "5.16.4",
  "project": "pgadmin",
  "summary": "Socket.IO server and client for Python",
  "url": "https://github.com/miguelgrinberg/python-socketio",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/python-socketio/python_socketio-5.16.4.tar.gz",
  "sdist_filename": "python_socketio-5.16.4.tar.gz",
  "sdist_top": "python_socketio-5.16.4",
  "family": "setuptools",
  "native": false,
  "requires": [
   "bidict >=0.21.0",
   "python-engineio >=4.13.2"
  ],
  "build_requires": "\"setuptools>=61.2\"",
  "scripts": [],
  "modules": [
   "socketio"
  ]
 },
 {
  "pypi": "pytz",
  "version": "2025.2",
  "project": "pgadmin",
  "summary": "World timezone definitions, modern and historical",
  "url": "http://pythonhosted.org/pytz",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/pytz/pytz-2025.2.tar.gz",
  "sdist_filename": "pytz-2025.2.tar.gz",
  "sdist_top": "pytz-2025.2",
  "family": "setup.py",
  "native": false,
  "requires": [],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "pytz"
  ]
 },
 {
  "pypi": "qrcode",
  "version": "8.2",
  "project": "pgadmin",
  "summary": "QR Code image generator",
  "url": "https://github.com/lincolnloop/python-qrcode",
  "license": "BSD",
  "sdist_url": "https://files.pythonhosted.org/packages/source/q/qrcode/qrcode-8.2.tar.gz",
  "sdist_filename": "qrcode-8.2.tar.gz",
  "sdist_top": "qrcode-8.2",
  "family": "poetry",
  "native": false,
  "requires": [],
  "build_requires": "\"poetry-core\"",
  "scripts": [
   "qr"
  ],
  "modules": [
   "qrcode"
  ]
 },
 {
  "pypi": "rich",
  "version": "15.0.0",
  "project": "pgadmin",
  "summary": "Render rich text, tables, progress bars, syntax highlighting, markdown and more to the terminal",
  "url": "https://github.com/Textualize/rich",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/r/rich/rich-15.0.0.tar.gz",
  "sdist_filename": "rich-15.0.0.tar.gz",
  "sdist_top": "rich-15.0.0",
  "family": "poetry",
  "native": false,
  "requires": [
   "markdown-it-py >=2.2.0",
   "pygments <3.0.0,>=2.13.0"
  ],
  "build_requires": "\"poetry-core>=1.0.0\"",
  "scripts": [],
  "modules": [
   "rich"
  ]
 },
 {
  "pypi": "SecretStorage",
  "version": "3.5.0",
  "project": "pgadmin",
  "summary": "Python bindings to FreeDesktop.org Secret Service API",
  "url": "https://github.com/mitya57/secretstorage",
  "license": "BSD-3-Clause",
  "sdist_url": "https://files.pythonhosted.org/packages/source/S/SecretStorage/secretstorage-3.5.0.tar.gz",
  "sdist_filename": "secretstorage-3.5.0.tar.gz",
  "sdist_top": "secretstorage-3.5.0",
  "family": "setuptools",
  "native": false,
  "requires": [
   "cryptography >=2.0",
   "jeepney >=0.6"
  ],
  "build_requires": "\"setuptools>=77.0\"",
  "scripts": [],
  "modules": [
   "secretstorage"
  ]
 },
 {
  "pypi": "shellingham",
  "version": "1.5.4",
  "project": "pgadmin",
  "summary": "Tool to Detect Surrounding Shell",
  "url": "https://github.com/sarugaku/shellingham",
  "license": "ISC License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/s/shellingham/shellingham-1.5.4.tar.gz",
  "sdist_filename": "shellingham-1.5.4.tar.gz",
  "sdist_top": "shellingham-1.5.4",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "\"setuptools\", \"wheel\"",
  "scripts": [],
  "modules": [
   "shellingham"
  ]
 },
 {
  "pypi": "simple-websocket",
  "version": "1.1.0",
  "project": "pgadmin",
  "summary": "Simple WebSocket server and client for Python",
  "url": "https://github.com/miguelgrinberg/simple-websocket",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/s/simple-websocket/simple_websocket-1.1.0.tar.gz",
  "sdist_filename": "simple_websocket-1.1.0.tar.gz",
  "sdist_top": "simple_websocket-1.1.0",
  "family": "setuptools",
  "native": false,
  "requires": [
   "wsproto"
  ],
  "build_requires": "\"setuptools>=61.2\",",
  "scripts": [],
  "modules": [
   "simple_websocket"
  ]
 },
 {
  "pypi": "SQLAlchemy",
  "version": "2.0.52",
  "project": "pgadmin",
  "summary": "Database Abstraction Library",
  "url": "https://www.sqlalchemy.org",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/S/SQLAlchemy/sqlalchemy-2.0.52.tar.gz",
  "sdist_filename": "sqlalchemy-2.0.52.tar.gz",
  "sdist_top": "sqlalchemy-2.0.52",
  "family": "setuptools",
  "native": true,
  "requires": [
   "greenlet >=1",
   "typing-extensions >=4.6.0"
  ],
  "build_requires": "\"setuptools>=61.0\", \"cython>=0.29.24; platform_python_implementation == 'CPython'\", # Skip cython when using pypy",
  "scripts": [],
  "modules": [
   "sqlalchemy"
  ]
 },
 {
  "pypi": "sqlparse",
  "version": "0.6.0",
  "project": "pgadmin",
  "summary": "A non-validating SQL parser",
  "url": "https://github.com/andialbrecht/sqlparse",
  "license": "BSD License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/s/sqlparse/sqlparse-0.6.0.tar.gz",
  "sdist_filename": "sqlparse-0.6.0.tar.gz",
  "sdist_top": "sqlparse-0.6.0",
  "family": "hatchling",
  "native": false,
  "requires": [],
  "build_requires": "\"hatchling\"",
  "scripts": [
   "sqlformat"
  ],
  "modules": [
   "sqlparse"
  ]
 },
 {
  "pypi": "sshtunnel",
  "version": "0.4.0",
  "project": "pgadmin",
  "summary": "Pure python SSH tunnels",
  "url": "https://github.com/pahaz/sshtunnel",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/s/sshtunnel/sshtunnel-0.4.0.tar.gz",
  "sdist_filename": "sshtunnel-0.4.0.tar.gz",
  "sdist_top": "sshtunnel-0.4.0",
  "family": "setuptools",
  "native": false,
  "requires": [
   "paramiko (>=2.7.2)"
  ],
  "build_requires": "\"setuptools\", \"wheel\"",
  "scripts": [
   "sshtunnel"
  ],
  "modules": [
   "sshtunnel"
  ]
 },
 {
  "pypi": "typer",
  "version": "0.19.2",
  "project": "pgadmin",
  "summary": "Typer, build great CLIs. Easy to code. Based on Python type hints",
  "url": "https://github.com/fastapi/typer",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/t/typer/typer-0.19.2.tar.gz",
  "sdist_filename": "typer-0.19.2.tar.gz",
  "sdist_top": "typer-0.19.2",
  "family": "pdm",
  "native": false,
  "requires": [
   "click >=8.0.0",
   "typing-extensions >=3.7.4.3",
   "shellingham >=1.3.0",
   "rich >=10.11.0"
  ],
  "build_requires": "\"pdm-backend\",",
  "scripts": [
   "typer"
  ],
  "modules": [
   "typer"
  ]
 },
 {
  "pypi": "typing-extensions",
  "version": "4.16.0",
  "project": "pgadmin",
  "summary": "Backported and Experimental Type Hints for Python 3.9+",
  "url": "https://pypi.org/project/typing-extensions/",
  "license": "PSF-2.0",
  "sdist_url": "https://files.pythonhosted.org/packages/source/t/typing-extensions/typing_extensions-4.16.0.tar.gz",
  "sdist_filename": "typing_extensions-4.16.0.tar.gz",
  "sdist_top": "typing_extensions-4.16.0",
  "family": "flit",
  "native": false,
  "requires": [],
  "build_requires": "\"flit_core >=3.11,<4\"",
  "scripts": [],
  "modules": [
   "typing_extensions"
  ]
 },
 {
  "pypi": "ua-parser",
  "version": "0.18.0",
  "project": "pgadmin",
  "summary": "Python port of Browserscope's user agent parser",
  "url": "https://github.com/ua-parser/uap-python",
  "license": "Apache 2.0",
  "sdist_url": "https://files.pythonhosted.org/packages/source/u/ua-parser/ua-parser-0.18.0.tar.gz",
  "sdist_filename": "ua-parser-0.18.0.tar.gz",
  "sdist_top": "ua-parser-0.18.0",
  "family": "setup.py",
  "native": false,
  "requires": [],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "ua_parser"
  ]
 },
 {
  "pypi": "user-agents",
  "version": "2.2.0",
  "project": "pgadmin",
  "summary": "A library to identify devices (phones, tablets) and their capabilities by parsing browser user agent strings",
  "url": "https://github.com/selwin/python-user-agents",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/u/user-agents/user-agents-2.2.0.tar.gz",
  "sdist_filename": "user-agents-2.2.0.tar.gz",
  "sdist_top": "user-agents-2.2.0",
  "family": "setup.py",
  "native": false,
  "requires": [
   "ua-parser (>=0.10.0)"
  ],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "user_agents"
  ]
 },
 {
  "pypi": "Werkzeug",
  "version": "3.1.8",
  "project": "pgadmin",
  "summary": "The comprehensive WSGI web application library",
  "url": "https://github.com/pallets/werkzeug/",
  "license": "BSD-3-Clause",
  "sdist_url": "https://files.pythonhosted.org/packages/source/W/Werkzeug/werkzeug-3.1.8.tar.gz",
  "sdist_filename": "werkzeug-3.1.8.tar.gz",
  "sdist_top": "werkzeug-3.1.8",
  "family": "flit",
  "native": false,
  "requires": [
   "markupsafe >=2.1.1"
  ],
  "build_requires": "\"flit_core<4\"",
  "scripts": [],
  "modules": [
   "werkzeug"
  ]
 },
 {
  "pypi": "wsproto",
  "version": "1.3.2",
  "project": "pgadmin",
  "summary": "Pure-Python WebSocket protocol implementation",
  "url": "https://github.com/python-hyper/wsproto/",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/w/wsproto/wsproto-1.3.2.tar.gz",
  "sdist_filename": "wsproto-1.3.2.tar.gz",
  "sdist_top": "wsproto-1.3.2",
  "family": "setuptools",
  "native": false,
  "requires": [
   "h11 <1,>=0.16.0"
  ],
  "build_requires": "\"setuptools>=77\"",
  "scripts": [],
  "modules": [
   "wsproto"
  ]
 },
 {
  "pypi": "WTForms",
  "version": "3.2.2",
  "project": "pgadmin",
  "summary": "Form validation and rendering for Python web development",
  "url": "https://pypi.org/project/WTForms/",
  "license": "BSD License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/W/WTForms/wtforms-3.2.2.tar.gz",
  "sdist_filename": "wtforms-3.2.2.tar.gz",
  "sdist_top": "wtforms-3.2.2",
  "family": "hatchling",
  "native": false,
  "requires": [
   "markupsafe >=1.1.1"
  ],
  "build_requires": "\"hatchling\"",
  "scripts": [],
  "modules": [
   "wtforms"
  ]
 },
 {
  "pypi": "Cython",
  "version": "3.1.3",
  "project": "pgadmin",
  "summary": "The Cython compiler for writing C extensions in the Python language",
  "url": "https://cython.org/",
  "license": "Apache-2.0",
  "sdist_url": "https://files.pythonhosted.org/packages/source/C/Cython/cython-3.1.3.tar.gz",
  "sdist_filename": "cython-3.1.3.tar.gz",
  "sdist_top": "cython-3.1.3",
  "family": "setup.py",
  "native": true,
  "requires": [],
  "build_requires": "",
  "scripts": [
   "cygdb",
   "cython",
   "cythonize"
  ],
  "modules": [
   "Cython",
   "cython",
   "pyximport"
  ]
 },
 {
  "pypi": "poetry-core",
  "version": "2.2.1",
  "project": "pgadmin",
  "summary": "Poetry PEP 517 Build Backend",
  "url": "https://github.com/python-poetry/poetry-core",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/poetry-core/poetry_core-2.2.1.tar.gz",
  "sdist_filename": "poetry_core-2.2.1.tar.gz",
  "sdist_top": "poetry_core-2.2.1",
  "family": "poetry",
  "native": false,
  "requires": [],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "poetry"
  ]
 },
 {
  "pypi": "pdm-backend",
  "version": "2.4.5",
  "project": "pgadmin",
  "summary": "The build backend used by PDM that supports latest packaging standards",
  "url": "https://github.com/pdm-project/pdm-backend",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/pdm-backend/pdm_backend-2.4.5.tar.gz",
  "sdist_filename": "pdm_backend-2.4.5.tar.gz",
  "sdist_top": "pdm_backend-2.4.5",
  "family": "pdm",
  "native": false,
  "requires": [],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "pdm"
  ]
 },
 {
  "pypi": "dnspython",
  "version": "2.8.0",
  "project": "common",
  "summary": "DNS toolkit",
  "url": "https://pypi.org/project/dnspython/",
  "license": "ISC",
  "sdist_url": "https://files.pythonhosted.org/packages/source/d/dnspython/dnspython-2.8.0.tar.gz",
  "sdist_filename": "dnspython-2.8.0.tar.gz",
  "sdist_top": "dnspython-2.8.0",
  "family": "hatchling",
  "native": false,
  "requires": [],
  "build_requires": "\"hatchling>=1.21.0\"",
  "scripts": [],
  "modules": [
   "dns"
  ]
 },
 {
  "pypi": "hatchling",
  "version": "1.28.0",
  "project": "common",
  "summary": "Modern, extensible Python build backend",
  "url": "https://hatch.pypa.io/latest/",
  "license": "",
  "sdist_url": "https://files.pythonhosted.org/packages/source/h/hatchling/hatchling-1.28.0.tar.gz",
  "sdist_filename": "hatchling-1.28.0.tar.gz",
  "sdist_top": "hatchling-1.28.0",
  "family": "setuptools",
  "native": false,
  "requires": [
   "packaging >=24.2",
   "pathspec >=0.10.1",
   "pluggy >=1.0.0",
   "trove-classifiers"
  ],
  "build_requires": "",
  "scripts": [
   "hatchling"
  ],
  "modules": [
   "hatchling"
  ]
 },
 {
  "pypi": "pathspec",
  "version": "0.12.1",
  "project": "common",
  "summary": "Utility library for gitignore style pattern matching of file paths",
  "url": "https://pypi.org/project/pathspec/",
  "license": "Mozilla Public License 2.0 (MPL 2.0)",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/pathspec/pathspec-0.12.1.tar.gz",
  "sdist_filename": "pathspec-0.12.1.tar.gz",
  "sdist_top": "pathspec-0.12.1",
  "family": "flit",
  "native": false,
  "requires": [],
  "build_requires": "\"flit_core >=3.2,<4\"",
  "scripts": [],
  "modules": [
   "pathspec"
  ]
 },
 {
  "pypi": "trove-classifiers",
  "version": "2025.9.11.17",
  "project": "common",
  "summary": "Canonical source for classifiers on PyPI (pypi.org)",
  "url": "https://github.com/pypa/trove-classifiers",
  "license": "Apache Software License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/t/trove-classifiers/trove_classifiers-2025.9.11.17.tar.gz",
  "sdist_filename": "trove_classifiers-2025.9.11.17.tar.gz",
  "sdist_top": "trove_classifiers-2025.9.11.17",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "\"setuptools\", \"calver\"",
  "scripts": [
   "trove-classifiers"
  ],
  "modules": [
   "trove_classifiers"
  ]
 },
 {
  "pypi": "flit-core",
  "version": "3.12.0",
  "project": "common",
  "summary": "Distribution-building parts of Flit. See flit package for more information",
  "url": "https://github.com/pypa/flit",
  "license": "BSD-3-Clause",
  "sdist_url": "https://files.pythonhosted.org/packages/source/f/flit-core/flit_core-3.12.0.tar.gz",
  "sdist_filename": "flit_core-3.12.0.tar.gz",
  "sdist_top": "flit_core-3.12.0",
  "family": "flit",
  "native": false,
  "requires": [],
  "build_requires": "",
  "scripts": [],
  "modules": [
   "flit_core"
  ]
 },
 {
  "pypi": "packaging",
  "version": "25.0",
  "project": "common",
  "summary": "Core utilities for Python packages",
  "url": "https://github.com/pypa/packaging",
  "license": "Apache Software License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/packaging/packaging-25.0.tar.gz",
  "sdist_filename": "packaging-25.0.tar.gz",
  "sdist_top": "packaging-25.0",
  "family": "flit",
  "native": false,
  "requires": [],
  "build_requires": "\"flit_core >=3.3\"",
  "scripts": [],
  "modules": [
   "packaging"
  ]
 }
]
```
