# pgAdmin 4 Package (SP4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `percona-pgadmin4` (pgAdmin 4 9.17, server mode) for UBI-9 in `ppg:devel:pgadmin`, with a `-gunicorn` subpackage that a container image can run directly, a `-httpd` subpackage for hosts, and a `-doc` subpackage — after bringing the SP3 Python 3.12 stack up to the 9.17 dependency closure.

**Architecture:** The package is built from the upstream git tag `REL-9_17` through the SP1 service chain (`obs_scm` → `npm_lockfile` → `node_modules` → `tar` → `recompress` → `set_version`); the spec runs webpack against the vendored npm tarballs served by `local-npm-registry` (SP2), builds the `pgadmin4` wheel with upstream's `pkg/pip/setup_pip.py`, and installs it into the Python 3.12 site-packages next to the SP3 `python3.12-*` stack. Distribution configuration lives in a shipped `config_distro.py` that also maps `PGADMIN_CONFIG_*` environment variables to settings, so the same package serves the container (gunicorn launcher + env) and hosts (httpd + mod_wsgi, or the systemd unit).

**Tech Stack:** RPM spec (EL9, `python3.12`), OBS services (`obs_scm`, `npm_lockfile`, `node_modules`, `set_version`), Node.js 20 + npm + webpack, `local-npm-registry`, gunicorn 26, Apache httpd + `python3.12-mod_wsgi`, systemd (`systemd-rpm-macros`, sysusers, tmpfiles), podman for the smoke test.

**Spec:** `docs/superpowers/specs/2026-08-28-pgadmin4-package-design.md` (SP4). The SP3 stack spec `docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md` governs the `python3-*` package template; Task 1 amends its §4 inventory.

## Global Constraints

- Everything is delivered on branch `pgadmin-sp1` in this worktree (`/home/rdias/Work/percona-obs-packaging/.claude/worktrees/pgadmin-sp1`) and tested through PR #12 (`percona/obs-packaging`). **Never `git push` without the user's explicit approval for that push.** Never `gh pr create`; never add the `obs-sync` label. PR body edits also need the user's go-ahead.
- Commits: `git commit -s`; no `Co-Authored-By` lines; message style `pgadmin: <what>` / `docs: <what>` as in the branch history.
- OBS: `-P isv` and `-P isv-pr` are PRODUCTION profiles — only `--dry-run` operations locally; builds are observed on `https://build.opensuse.org` (public API `https://api.opensuse.org/public/build/<project>/_result`), never triggered or pushed with the tool. Sync happens via the PR workflow after a push.
- No local RPM builds (`rpmbuild`, `mock`, `osc build`) — validation is OBS-first. Local checks are limited to `rpmspec -P`/`rpmspec -q`, `python3 -m py_compile`, `bash -n`, `patch --dry-run`, and `percona-obs sync push --dry-run`.
- All `python3-*` package specs follow the SP3 template exactly (preamble `__ospython=/usr/bin/python3.12`, `python3_pkgprefix python3.12`, `Epoch: 1`, `pip wheel --no-deps --no-build-isolation --no-index`, `%check` = `PYTHONPATH=… %{__ospython} -P -c "import X"`); Task 1 produces them with the render script in Appendix A — no hand edits to rendered specs except where a step says so.
- Runtime dependencies in `percona-pgadmin4` are spelled as `%{python3_pkgprefix}-<pypi-normalised-name>` for packages built in this repo, and as the verbatim RHEL/UBI names for reused ones (`python3.12-cryptography`, `python3.12-setuptools`, `python3.12-urllib3`, `python3.12-mod_wsgi`). No version floors on reused RHEL packages.
- The pgadmin project must be installable from its own repository: every `ppg:common:deps` package a pgadmin package `Requires` is aggregated into `root/ppg/devel/pgadmin/<pkg>/obs/_aggregate` (`ppg:common:deps` is `publish: false`).
- Authlib stays at 1.6.12 (SP3 ruling; 9.17's `Authlib==1.7.*` pin is not enforced — the spec's `Requires` carries no floor). `joserfc` is not packaged (needs cryptography ≥ 45; RHEL 9 ships 41). `libpass` replaces `passlib` (`Provides/Conflicts %{python3_pkgprefix}-passlib`). `importlib-resources` leaves the stack (no consumer in 9.17).
- Multi-line shell in this worktree: the shell guard refuses compound commands (`for`, `$( )`, `cd … &&`, pipes into loops). Use plain single commands, `python3 -c`, or write a script file and run it.

**User decisions (already made):**
- "start with sp4"; approach **A** — port the openSUSE `pgadmin4.spec` to EL9/python3.12 (not the PGDG spec, not a from-scratch spec).
- "The main purpose of packaging pgadmin is to afterwards create a container image with pgadmin to run pgadmin" — the package must serve as the payload of a container image: `-gunicorn` subpackage with launcher + `PGADMIN_CONFIG_*` env mapping; httpd integration stays for hosts.
- Docs: openSUSE-style — `-doc` ships the rst sources; the in-app "Online Help" link is patched to the upstream online docs for the running version (no Sphinx build).
- "Move to REL-9_17 now" — the `_service` pins `REL-9_17` (SP1 used `REL-9_9`); the SP3 stack is bumped to 9.17's closure first.
- httpd + mod_wsgi is the primary host deployment; the systemd unit is shipped **disabled**; gunicorn is the container runtime.
- Pushes: "Push once now; ask again before each fix push" (SP3 rule, carried over).

---

## File map

| Path | Task | Responsibility |
|---|---|---|
| `root/ppg/devel/pgadmin/python3-{flask-security-too,flask-socketio,flask-wtf,gssapi,psycopg,psycopg-c,pytz,typer,cython}/rpm/*.spec` | 1 | Bumped SP3 packages (rendered) |
| `root/ppg/devel/pgadmin/python3-{annotated-doc,certifi,libpass,gunicorn}/{package.yaml,obs/_service,rpm/*.spec}` | 1 | New SP3 packages (rendered) |
| `root/ppg/devel/pgadmin/python3-{passlib,importlib-resources}/` | 1 | Removed |
| `root/ppg/devel/pgadmin/python3-{click,six,dateutil,psutil,dns}/obs/_aggregate` | 1 | Aggregates of `ppg:common:deps` runtime deps |
| `docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md` | 1 | §4 inventory amended for 9.17 |
| `root/ppg/devel/pgadmin/percona-pgadmin4/package.yaml` | 2 | Package metadata |
| `root/ppg/devel/pgadmin/percona-pgadmin4/obs/_service` | 2 | Source chain (obs_scm REL-9_17 → npm_lockfile → node_modules → tar → recompress → set_version) |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.spec` | 2 | The spec (base, -gunicorn, -httpd, -doc) |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/config_distro.py` | 2 | Distribution config + `PGADMIN_CONFIG_*` env mapping |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/run_pgadmin.py` | 2 | WSGI entry module for gunicorn |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/gunicorn_config.py` | 2 | gunicorn logging config |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4-gunicorn` | 2 | Launcher script (container entry point) |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.service` | 2 | systemd unit (disabled by default) |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.sysusers` | 2 | `pgadmin` system user |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.tmpfiles` | 2 | `/run/pgadmin4` |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4-httpd.conf` | 2 | Apache conf.d snippet |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4-setup-web` | 2 | Host setup helper (setup-db, SELinux, httpd restart) |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/0001-help-menu-online-docs.patch` | 2 | Online Help → upstream docs URL |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/0002-make-cloud-packages-optional.patch` | 2 | openSUSE patch, verbatim |
| `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/0003-use-os-makedirs.patch` | 2 | openSUSE patch, verbatim |
| `root/README.md`, `docs/PERCONA_OBS_TOOL.md` | 3 | Tree/tool docs mention the pgadmin project's application package |
| (OBS project `isv:percona:PR:pr-12:ppg:devel:pgadmin`) | 4 | Build loop |
| (podman, UBI-9) | 5 | Container smoke test — user gate |
| `docs/superpowers/specs/2026-08-28-pgadmin4-package-design.md` §9, PR #12 body | 6 | Outcomes recorded |

---

### Task 1: SP3 stack changes for the 9.17 closure

**Goal:** Bring the `python3-*` stack in `root/ppg/devel/pgadmin/` to pgAdmin 9.17's dependency closure — 9 version bumps, 4 new packages, 2 removals, 5 aggregates — with the SP3 spec inventory updated to match.

**Files:**
- Modify (re-rendered): `root/ppg/devel/pgadmin/python3-flask-security-too/rpm/python3-flask-security-too.spec` (5.5.0 → 5.8.2), `python3-flask-socketio` (5.5.1 → 5.6.1), `python3-flask-wtf` (1.2.2 → 1.3.0), `python3-gssapi` (1.9.0 → 1.11.1), `python3-psycopg` (3.2.x → 3.3.4), `python3-psycopg-c` (3.2.x → 3.3.4), `python3-pytz` (→ 2026.3.post1), `python3-typer` (0.15.x → 0.26.8), `python3-cython` (→ 3.2.4) — each `rpm/<dir>.spec` plus `obs/_service` and `package.yaml` (rendered together; `_service`/`package.yaml` content changes only where the sdist URL/version changed).
- Create (rendered): `root/ppg/devel/pgadmin/python3-annotated-doc/`, `python3-certifi/`, `python3-libpass/`, `python3-gunicorn/` — each with `package.yaml`, `obs/_service`, `rpm/<dir>.spec`.
- Delete: `root/ppg/devel/pgadmin/python3-passlib/`, `root/ppg/devel/pgadmin/python3-importlib-resources/`.
- Create: `root/ppg/devel/pgadmin/python3-click/obs/_aggregate`, `python3-six/obs/_aggregate`, `python3-dateutil/obs/_aggregate`, `python3-psutil/obs/_aggregate`, `python3-dns/obs/_aggregate`.
- Modify: `docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md` §4 inventory table rows for the packages above.

**Acceptance Criteria:**
- [ ] `rpmspec -q --qf '%{NAME}-%{VERSION}\n' <spec>` succeeds for all 13 rendered specs and prints the 9.17 versions (`python3.12-flask-security-too-5.8.2`, `python3.12-flask-socketio-5.6.1`, `python3.12-flask-wtf-1.3.0`, `python3.12-gssapi-1.11.1`, `python3.12-psycopg-3.3.4`, `python3.12-psycopg-c-3.3.4`, `python3.12-pytz-2026.3.post1`, `python3.12-typer-0.26.8`, `python3.12-cython-3.2.4`, `python3.12-annotated-doc-0.0.5`, `python3.12-certifi-2026.6.17`, `python3.12-libpass-1.9.3`, `python3.12-gunicorn-26.2.0`).
- [ ] `python3-libpass.spec` contains `Provides:       %{python3_pkgprefix}-passlib = %{version}` and `Conflicts:      %{python3_pkgprefix}-passlib < 1.9`; `python3-flask-security-too.spec` requires `%{python3_pkgprefix}-libpass >= 1.9.3` and no longer mentions `passlib` or `importlib-resources`.
- [ ] `python3-typer.spec` requires `%{python3_pkgprefix}-annotated-doc >= 0.0.2` and `%{python3_pkgprefix}-rich >= 13.8.0` and does not require `click` or `typing-extensions` (upstream 0.26 metadata).
- [ ] `python3-psycopg.spec`, `python3-psycopg-c.spec`, `python3-gunicorn.spec` carry the PEP 639 `sed` in `%prep` (`license = {text = …}`).
- [ ] `git grep -l passlib root/ppg/devel/pgadmin` lists only `python3-libpass` and `python3-flask-security-too` (the latter only in a `# ` comment, if any) — no `python3-passlib` directory remains; `python3-importlib-resources` directory is gone.
- [ ] Five `_aggregate` files exist and each names the matching `ppg:common:deps` source package.
- [ ] `venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:devel:pgadmin python3-gunicorn` and `… python3-libpass` succeed (service chain runs locally; no upload).
- [ ] SP3 spec §4 table reflects the 9.17 versions, the four additions and the two removals.

**Verify:** `venv/bin/python /tmp/…/scratchpad/sp4-bump/check_bump.py` (written in Step 4) → `OK 13 specs`; `git status --short root/ppg/devel/pgadmin | wc -l` → 13 packages' files changed/added plus 2 deletions plus 5 aggregates.

**Steps:**

- [ ] **Step 1: Materialise the render inputs**

Create a working directory in the session scratchpad (`$SCRATCH` below is `/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/4a404ac4-d132-42d5-92af-b4a8d5e081ba/scratchpad/sp4-bump`; `mkdir -p` it) and write three files into it, byte-for-byte from the appendices of this plan:

- `render_stack.py` ← Appendix A
- `stack.json` ← Appendix B (the 13 packages to render; `Authlib` and `joserfc` are deliberately absent)
- `known.json` ← Appendix C (names of the other 66 stack packages, for `Requires` name resolution — without it the renderer drops dependencies on packages outside the rendered set)

Check: `venv/bin/python -c "import json; print(len(json.load(open('$SCRATCH/stack.json'))), len(json.load(open('$SCRATCH/known.json'))))"` → `13 66`.

- [ ] **Step 2: Remove the two retired packages first**

```bash
git rm -r -q root/ppg/devel/pgadmin/python3-passlib root/ppg/devel/pgadmin/python3-importlib-resources
```

Rationale: `libpass` installs the `passlib` module and `Provides/Conflicts` the old name; `importlib-resources` has no consumer in the 9.17 closure (Flask-Security-Too 5.8 dropped it).

- [ ] **Step 3: Render the 13 packages into the tree**

```bash
venv/bin/python $SCRATCH/render_stack.py /home/rdias/Work/percona-obs-packaging/.claude/worktrees/pgadmin-sp1
```

The renderer writes `root/ppg/devel/pgadmin/<dir>/{package.yaml,obs/_service,rpm/<dir>.spec}` for each of the 13 entries, overwriting the 9 existing packages and creating the 4 new ones. Expected output ends with `rendered 13 packages`. Then `git status --short root/ppg/devel/pgadmin` must show: 9 `M` groups (only `rpm/*.spec` and, where the sdist filename changed, `obs/_service`), 4 `??` directories (`python3-annotated-doc`, `python3-certifi`, `python3-libpass`, `python3-gunicorn`), and the 2 `D` groups from Step 2. If any other package directory shows as modified, the renderer was pointed at the wrong data — stop and compare with Appendix B.

- [ ] **Step 4: Write and run the check script**

`$SCRATCH/check_bump.py`:

```python
"""Assert the 13 rendered specs carry the 9.17 versions and the intended deltas."""
import json, pathlib, re, subprocess, sys

ROOT = pathlib.Path("/home/rdias/Work/percona-obs-packaging/.claude/worktrees/pgadmin-sp1/root/ppg/devel/pgadmin")
S = pathlib.Path(__file__).parent
norm = lambda n: re.sub(r"[._]", "-", n.lower())
rows = json.load(open(S / "stack.json"))
must = {
    "libpass": ["Provides:       %{python3_pkgprefix}-passlib = %{version}",
                "Conflicts:      %{python3_pkgprefix}-passlib < 1.9"],
    "Flask-Security-Too": ["Requires:       %{python3_pkgprefix}-libpass >= 1.9.3"],
    "typer": ["Requires:       %{python3_pkgprefix}-annotated-doc >= 0.0.2",
              "Requires:       %{python3_pkgprefix}-rich >= 13.8.0"],
    "psycopg": ["license = {text ="], "psycopg-c": ["license = {text ="], "gunicorn": ["license = {text ="],
}
must_not = {
    "Flask-Security-Too": ["passlib >=", "importlib-resources"],
    "typer": ["Requires:       %{python3_pkgprefix}-click", "typing-extensions"],
}
bad = 0
for r in rows:
    d = f"python3-{norm(r['pypi'])}"
    spec = ROOT / d / "rpm" / f"{d}.spec"
    p = subprocess.run(["rpmspec", "-q", "--qf", "%{NAME}-%{VERSION}\n", str(spec)], capture_output=True, text=True)
    want = f"python3.12-{norm(r['pypi'])}-{r['version']}"
    if p.returncode or want not in p.stdout:
        bad += 1; print("VERSION/PARSE FAIL", d, p.stdout.strip(), p.stderr.strip()[:200])
    text = spec.read_text()
    for line in must.get(r["pypi"], []):
        if line not in text: bad += 1; print("MISSING", d, line)
    for frag in must_not.get(r["pypi"], []):
        if frag in text: bad += 1; print("UNEXPECTED", d, frag)
for gone in ("python3-passlib", "python3-importlib-resources"):
    if (ROOT / gone).exists(): bad += 1; print("STILL PRESENT", gone)
print("OK 13 specs" if not bad else f"FAILED {bad}")
sys.exit(1 if bad else 0)
```

Run: `venv/bin/python $SCRATCH/check_bump.py` → `OK 13 specs`.

- [ ] **Step 5: Add the five `ppg:common:deps` aggregates**

First confirm the source package names: `ls root/ppg/common/deps` must list `python3-click`, `python3-six`, `python3-dateutil`, `python3-psutil`, `python3-dns` (use the exact directory names found if any differ — the `<package>` element must be the common:deps source package name). For each, create `root/ppg/devel/pgadmin/<name>/obs/_aggregate` with this content, substituting the name:

```xml
<aggregatelist>
  <aggregate project="${OBS_ROOTPRJ}:ppg:common:deps">
    <package>python3-click</package>
  </aggregate>
</aggregatelist>
```

A single Python one-liner is the guard-safe way to write all five:

```bash
venv/bin/python -c "
import pathlib
for n in ['python3-click','python3-six','python3-dateutil','python3-psutil','python3-dns']:
    d=pathlib.Path('root/ppg/devel/pgadmin')/n/'obs'; d.mkdir(parents=True, exist_ok=True)
    (d/'_aggregate').write_text('<aggregatelist>\n  <aggregate project=\"\${OBS_ROOTPRJ}:ppg:common:deps\">\n    <package>%s</package>\n  </aggregate>\n</aggregatelist>\n' % n)
print('ok')"
```

Check: `grep -h '<package>' root/ppg/devel/pgadmin/python3-{click,six,dateutil,psutil,dns}/obs/_aggregate` prints the five names. (Aggregate packages have no `package.yaml` — see `root/ppg/staging/14/etcd/`.)

- [ ] **Step 6: Amend the SP3 spec inventory**

In `docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md` §4 (the inventory table): change the version cells of the nine bumped packages to `5.8.2`, `5.6.1`, `1.3.0`, `1.11.1`, `3.3.4`, `3.3.4`, `2026.3.post1`, `0.26.8`, `3.2.4`; delete the `passlib` and `importlib-resources` rows; add rows for `annotated-doc 0.0.5` (pyproject/pdm-backend → check Appendix B `family`), `certifi 2026.6.17`, `libpass 1.9.3` (hatchling; Provides/Conflicts passlib), `gunicorn 26.2.0` (scripts `gunicorn`, `gunicornc`). Append one paragraph after the table:

> **9.17 update (SP4, 2026-08-28).** pgAdmin moved from REL-9_9 to REL-9_17; the closure changed as follows: bumps Flask-Security-Too 5.8.2, Flask-SocketIO 5.6.1, Flask-WTF 1.3.0, gssapi 1.11.1 (Cython 3.2.4), psycopg/psycopg-c 3.3.4, pytz 2026.3.post1, typer 0.26.8; additions annotated-doc 0.0.5, certifi 2026.6.17, libpass 1.9.3 (replaces passlib; `Provides/Conflicts python3.12-passlib`), gunicorn 26.2.0 (container runtime, SP4 §3); removals passlib, importlib-resources. Not adopted: Authlib 1.7.x (ruling: stay on 1.6.12), joserfc 1.7.4 (needs cryptography ≥ 45; RHEL 9 ships 41).

Use exact-string edits (the Edit tool) per row; do not reflow the table.

- [ ] **Step 7: Dry-run two packages through the sync path**

```bash
venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:devel:pgadmin python3-gunicorn
venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:devel:pgadmin python3-libpass
```

Expected: each ends with the dry-run summary listing the files that *would* be uploaded (`python3-gunicorn.spec`, `gunicorn-26.2.0.tar.gz`, `_service`, …) and no error. `--dry-run` is mandatory — `isv-pr` is production.

- [ ] **Step 8: Commit**

```bash
git add -A root/ppg/devel/pgadmin docs/superpowers/specs/2026-08-26-pgadmin4-py312-stack-design.md
git commit -s -m "pgadmin: py3.12 stack for pgAdmin 9.17

Bump Flask-Security-Too 5.8.2, Flask-SocketIO 5.6.1, Flask-WTF 1.3.0,
gssapi 1.11.1 (Cython 3.2.4), psycopg/psycopg-c 3.3.4, pytz 2026.3.post1,
typer 0.26.8. Add annotated-doc 0.0.5, certifi 2026.6.17, libpass 1.9.3
(replaces passlib) and gunicorn 26.2.0 (container runtime). Drop passlib
and importlib-resources. Aggregate the common:deps runtime packages
(click, six, dateutil, psutil, dns) so the project repo is self-contained."
```

The push of this commit happens in Task 4 (with approval) — do not push here.

---

### Task 2: The `percona-pgadmin4` package

**Goal:** Add `root/ppg/devel/pgadmin/percona-pgadmin4/` — spec, service chain, support files and patches — producing `percona-pgadmin4`, `-gunicorn`, `-httpd` and `-doc`, verified as far as local tooling allows (spec parse, script syntax, patch dry-run, sync dry-run).

**Files:**
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/package.yaml`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/obs/_service`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.spec`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/config_distro.py`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/run_pgadmin.py`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/gunicorn_config.py`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4-gunicorn`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.service`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.sysusers`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.tmpfiles`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4-httpd.conf`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4-setup-web`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/0001-help-menu-online-docs.patch`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/0002-make-cloud-packages-optional.patch`
- Create: `root/ppg/devel/pgadmin/percona-pgadmin4/rpm/0003-use-os-makedirs.patch`

**Acceptance Criteria:**
- [ ] `rpmspec -P root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.spec` succeeds with a stub `node_modules.spec.inc` in `--define "_sourcedir …"` and shows four `%package`/`%files` sections (`percona-pgadmin4`, `-gunicorn`, `-httpd`, `-doc`).
- [ ] `python3 -m py_compile` passes for `config_distro.py`, `run_pgadmin.py`, `gunicorn_config.py`; `bash -n` passes for `percona-pgadmin4-gunicorn` and `percona-pgadmin4-setup-web`; `systemd-analyze verify --man=no` of the unit reports nothing about syntax (missing `ExecStart` binary on this machine is acceptable and expected).
- [ ] All three patches apply with `patch -p1 --dry-run` against a fresh `git archive` of `pgadmin4` tag `REL-9_17` (`web/pgadmin/help/__init__.py`, `web/pgadmin/misc/__init__.py`, `web/pgadmin/setup/data_directory.py`).
- [ ] `config_distro.py` executed with `PGADMIN_CONFIG_SERVER_MODE=false PGADMIN_CONFIG_MAX_LOGIN_ATTEMPTS=7 PGADMIN_CONFIG_HELP_PATH=/x` yields `SERVER_MODE is False`, `MAX_LOGIN_ATTEMPTS == 7`, `HELP_PATH == '/x'` (unit check in Step 3).
- [ ] `venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:devel:pgadmin percona-pgadmin4` runs the full service chain locally (obs_scm clone of REL-9_17, npm_lockfile, node_modules download) and ends listing the files it would upload, including `percona-pgadmin4-9.17.tar.gz`, `package-lock.json`, `node_modules.obscpio`, `node_modules.spec.inc`; the generated `node_modules.spec.inc` is used for the `rpmspec -P` check above instead of the stub.
- [ ] `git status` shows only the new `percona-pgadmin4/` directory; committed.

**Verify:** `rpmspec -P --define "_sourcedir $SCRATCH/pgadmin-src" root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.spec | grep -c '^%files'` → `4`; `venv/bin/python $SCRATCH/check_config_distro.py` → `OK`.

**Steps:**

- [ ] **Step 1: `package.yaml` and `obs/_service`**

`root/ppg/devel/pgadmin/percona-pgadmin4/package.yaml`:

```yaml
title: pgAdmin 4 (server mode) for UBI-9
description: |
  pgAdmin 4 built from the upstream git tag (REL-9_17) with the SP1 npm vendoring
  chain (obs_scm -> npm_lockfile -> node_modules) and the Python 3.12 stack of this
  project. Subpackages: -gunicorn (launcher + systemd unit; the container runtime),
  -httpd (Apache httpd + mod_wsgi integration for hosts), -doc (documentation
  sources). Design: docs/superpowers/specs/2026-08-28-pgadmin4-package-design.md
```

`root/ppg/devel/pgadmin/percona-pgadmin4/obs/_service`:

```xml
<services>
  <service name="obs_scm">
    <param name="scm">git</param>
    <param name="url">https://github.com/pgadmin-org/pgadmin4.git</param>
    <param name="revision">REL-9_17</param>
    <param name="versionformat">@PARENT_TAG@</param>
    <param name="versionrewrite-pattern">REL-(\d+)_(\d+)</param>
    <param name="versionrewrite-replacement">\1.\2</param>
    <param name="filename">percona-pgadmin4</param>
  </service>
  <service name="npm_lockfile" mode="manual">
    <param name="archive">percona-pgadmin4*.obscpio</param>
    <param name="subdir">web</param>
  </service>
  <service name="node_modules" mode="manual">
    <param name="cpio">node_modules.obscpio</param>
    <param name="output">node_modules.spec.inc</param>
    <param name="source-offset">10000</param>
  </service>
  <service name="tar" mode="buildtime"/>
  <service name="recompress" mode="buildtime">
    <param name="file">*.tar</param>
    <param name="compression">gz</param>
  </service>
  <service name="set_version" mode="buildtime"/>
</services>
```

This is the SP1-verified chain with only the revision changed (`REL-9_9` → `REL-9_17`). `obs_scm` produces `percona-pgadmin4-9.17.obscpio` + `percona-pgadmin4.obsinfo`; `npm_lockfile` runs `npm install --package-lock-only` in `web/` and emits `package-lock.json`; `node_modules` downloads every tarball into `node_modules.obscpio` and writes `SourceNNNNN:` lines to `node_modules.spec.inc` starting at 10000; at build time `tar`+`recompress` yield `percona-pgadmin4-9.17.tar.gz` and `set_version` rewrites `Version:` to `9.17`.

- [ ] **Step 2: Support files — configuration and WSGI**

`rpm/config_distro.py` (installed as `%{python3_sitelib}/pgadmin4/config_distro.py`; pgAdmin imports it after `config.py` and before `config_local.py`/`/etc/pgadmin/config_system.py`):

```python
# Distribution configuration for percona-pgadmin4 (server mode).
#
# Precedence (lowest to highest): config.py (upstream defaults) < this file <
# config_local.py < /etc/pgadmin/config_system.py.  Container images and unit
# files override any setting through the environment: every PGADMIN_CONFIG_<NAME>
# variable becomes the setting <NAME>; the value is parsed as a Python literal
# (numbers, True/False/None, quoted strings, lists, dicts) and kept as a plain
# string when it is not one — the same contract as the upstream container image.
import ast
import os

SERVER_MODE = True
MINIFY_HTML = False
UPGRADE_CHECK_ENABLED = False
HELP_PATH = '/usr/share/doc/percona-pgadmin4/en_US'
LOG_FILE = '/var/log/pgadmin/pgadmin4.log'
SQLITE_PATH = '/var/lib/pgadmin/pgadmin4.db'
SESSION_DB_PATH = '/var/lib/pgadmin/sessions'
STORAGE_DIR = '/var/lib/pgadmin/storage'
AZURE_CREDENTIAL_CACHE_DIR = '/var/lib/pgadmin/azurecredentialcache'
KERBEROS_CCACHE_DIR = '/var/lib/pgadmin/krbccache'
DEFAULT_BINARY_PATHS = {
    "pg": "/usr/pgsql-18/bin",
    "pg-13": "/usr/pgsql-13/bin",
    "pg-14": "/usr/pgsql-14/bin",
    "pg-15": "/usr/pgsql-15/bin",
    "pg-16": "/usr/pgsql-16/bin",
    "pg-17": "/usr/pgsql-17/bin",
    "pg-18": "/usr/pgsql-18/bin",
}

_PREFIX = 'PGADMIN_CONFIG_'
for _key, _value in os.environ.items():
    if not _key.startswith(_PREFIX) or len(_key) == len(_PREFIX):
        continue
    _literal = {'true': 'True', 'false': 'False'}.get(_value.strip().lower(), _value)
    try:
        globals()[_key[len(_PREFIX):]] = ast.literal_eval(_literal)
    except (ValueError, SyntaxError):
        globals()[_key[len(_PREFIX):]] = _value
del _PREFIX, _key, _value, _literal
```

(`del` of `_key`/`_value`/`_literal` is guarded by the loop having run at least once only if any variable exists — `os.environ` always has entries, so the names are always bound; keep the `del` as written.)

`rpm/run_pgadmin.py` (installed as `%{python3_sitelib}/pgadmin4/run_pgadmin.py`; gunicorn's WSGI target `run_pgadmin:app`):

```python
# WSGI entry point for gunicorn: `gunicorn … run_pgadmin:app`.
# Mirrors upstream's container run_pgadmin.py; the app module is pgAdmin4.py
# in this directory, which builds the Flask application on import.
import builtins
import os
import sys

# Set SERVER_MODE explicitly for the builtin check performed by config.py.
builtins.SERVER_MODE = True

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from pgAdmin4 import app  # noqa: E402,F401
```

`rpm/gunicorn_config.py` (installed as `%{python3_sitelib}/pgadmin4/gunicorn_config.py`; upstream's container logging config, unchanged in substance):

```python
# gunicorn configuration for percona-pgadmin4-gunicorn.
# Log to stdout/stderr (container-friendly); the launcher passes bind/workers/TLS
# on the command line so environment variables stay the single knob.
import logging

logconfig_dict = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'generic': {
            'format': '%(asctime)s [%(process)d] [%(levelname)s] %(message)s',
            'datefmt': '[%Y-%m-%d %H:%M:%S %z]',
            'class': 'logging.Formatter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'generic',
            'stream': 'ext://sys.stdout',
        },
        'error_console': {
            'class': 'logging.StreamHandler',
            'formatter': 'generic',
            'stream': 'ext://sys.stderr',
        },
    },
    'loggers': {
        'gunicorn.error': {'level': 'INFO', 'handlers': ['error_console'], 'propagate': False},
        'gunicorn.access': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
    },
    'root': {'level': logging.INFO, 'handlers': ['console']},
}
```

- [ ] **Step 3: Unit-check `config_distro.py`**

`$SCRATCH/check_config_distro.py`:

```python
"""config_distro.py must apply PGADMIN_CONFIG_* env overrides with literal parsing."""
import os, runpy, sys
src = "/home/rdias/Work/percona-obs-packaging/.claude/worktrees/pgadmin-sp1/root/ppg/devel/pgadmin/percona-pgadmin4/rpm/config_distro.py"
os.environ.update({
    "PGADMIN_CONFIG_SERVER_MODE": "false",
    "PGADMIN_CONFIG_MAX_LOGIN_ATTEMPTS": "7",
    "PGADMIN_CONFIG_HELP_PATH": "/x",
    "PGADMIN_CONFIG_AUTHENTICATION_SOURCES": "['internal', 'ldap']",
    "PGADMIN_CONFIG_": "ignored",
})
g = runpy.run_path(src)
assert g["SERVER_MODE"] is False, g["SERVER_MODE"]
assert g["MAX_LOGIN_ATTEMPTS"] == 7 and isinstance(g["MAX_LOGIN_ATTEMPTS"], int)
assert g["HELP_PATH"] == "/x"
assert g["AUTHENTICATION_SOURCES"] == ["internal", "ldap"]
assert g["DEFAULT_BINARY_PATHS"]["pg-17"] == "/usr/pgsql-17/bin"
assert "_key" not in g and "_PREFIX" not in g
print("OK")
```

Run: `venv/bin/python $SCRATCH/check_config_distro.py` → `OK`. (Write this check before `config_distro.py` if you follow TDD strictly: it fails with `FileNotFoundError` first, then passes.)

- [ ] **Step 4: Support files — gunicorn launcher, unit, sysusers, tmpfiles**

`rpm/percona-pgadmin4-gunicorn` (installed as `%{_bindir}/percona-pgadmin4-gunicorn`, mode 0755; the container `CMD`):

```bash
#!/bin/bash
# percona-pgadmin4-gunicorn — run pgAdmin 4 under gunicorn.
#
# Environment (all optional):
#   PGADMIN_LISTEN_ADDRESS   bind address            (default 127.0.0.1)
#   PGADMIN_LISTEN_PORT      bind port               (default 5050)
#   PGADMIN_ENABLE_TLS       "true" to serve HTTPS using /certs/server.cert + /certs/server.key
#   GUNICORN_ACCESS_LOGFILE  access log target       (default "-" = stdout)
#   GUNICORN_THREADS         threads per worker      (default 25)
#   GUNICORN_LIMIT_REQUEST_LINE  (default 8190)
#   PGADMIN_CONFIG_<SETTING> any pgAdmin setting, applied by config_distro.py
#   PGADMIN_DEFAULT_EMAIL / PGADMIN_DEFAULT_PASSWORD
#                            create the initial admin user when no configuration
#                            database exists yet (same names as the upstream image).
# The systemd unit runs this script as user pgadmin; containers run it as their
# unprivileged user with /var/lib/pgadmin and /var/log/pgadmin writable.
set -euo pipefail

PGADMIN_DIR=/usr/lib/python3.12/site-packages/pgadmin4
: "${PGADMIN_LISTEN_ADDRESS:=127.0.0.1}"
: "${PGADMIN_LISTEN_PORT:=5050}"
: "${GUNICORN_ACCESS_LOGFILE:=-}"
: "${GUNICORN_THREADS:=25}"
: "${GUNICORN_LIMIT_REQUEST_LINE:=8190}"

cd "${PGADMIN_DIR}"

# First start: create the configuration database and the initial user.
if [ ! -e "${PGADMIN_CONFIG_SQLITE_PATH:-/var/lib/pgadmin/pgadmin4.db}" ] && \
   [ -n "${PGADMIN_DEFAULT_EMAIL:-}" ] && [ -n "${PGADMIN_DEFAULT_PASSWORD:-}" ]; then
    PGADMIN_SETUP_EMAIL="${PGADMIN_DEFAULT_EMAIL}" \
    PGADMIN_SETUP_PASSWORD="${PGADMIN_DEFAULT_PASSWORD}" \
        /usr/bin/python3.12 setup.py setup-db
fi

TLS_ARGS=()
if [ "${PGADMIN_ENABLE_TLS:-}" = "true" ]; then
    TLS_ARGS=(--certfile /certs/server.cert --keyfile /certs/server.key)
fi

exec /usr/bin/gunicorn \
    --bind "${PGADMIN_LISTEN_ADDRESS}:${PGADMIN_LISTEN_PORT}" \
    --workers 1 --threads "${GUNICORN_THREADS}" \
    --limit-request-line "${GUNICORN_LIMIT_REQUEST_LINE}" \
    --access-logfile "${GUNICORN_ACCESS_LOGFILE}" \
    "${TLS_ARGS[@]}" \
    -c gunicorn_config.py run_pgadmin:app
```

Note `setup.py setup-db` is upstream's setup entry point (`web/setup.py`, installed by the wheel under `pgadmin4/`); it honours `PGADMIN_SETUP_EMAIL`/`PGADMIN_SETUP_PASSWORD`. The gunicorn console script is `/usr/bin/gunicorn` (from `python3.12-gunicorn`; SP3 survey `scripts`: `gunicorn`, `gunicornc`). The hard-coded `PGADMIN_DIR` equals `%{python3_sitelib}/pgadmin4` on EL9 python3.12 (`/usr/lib/python3.12/site-packages`) — the spec asserts this in `%install` (Step 6).

`rpm/percona-pgadmin4.service`:

```ini
[Unit]
Description=pgAdmin 4 (gunicorn)
Documentation=https://www.pgadmin.org/docs/
After=network.target

[Service]
Type=exec
User=pgadmin
Group=pgadmin
RuntimeDirectory=pgadmin4
Environment=PGADMIN_LISTEN_ADDRESS=127.0.0.1
Environment=PGADMIN_LISTEN_PORT=5050
EnvironmentFile=-/etc/sysconfig/percona-pgadmin4
ExecStart=/usr/bin/percona-pgadmin4-gunicorn
Restart=on-failure
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/pgadmin /var/log/pgadmin
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

`rpm/percona-pgadmin4.sysusers`:

```
u pgadmin - "pgAdmin 4" /var/lib/pgadmin /sbin/nologin
```

`rpm/percona-pgadmin4.tmpfiles`:

```
d /run/pgadmin4 0755 pgadmin pgadmin -
```

- [ ] **Step 5: Support files — httpd integration**

`rpm/percona-pgadmin4-httpd.conf` (installed as `%{_sysconfdir}/httpd/conf.d/percona-pgadmin4.conf`, `%config(noreplace)`):

```apache
# pgAdmin 4 under Apache httpd + mod_wsgi (python3.12-mod_wsgi).
# URL: http://<host>/pgadmin4/   Run `percona-pgadmin4-setup-web` once after install.
LoadModule wsgi_module modules/mod_wsgi_python3.so

WSGIDaemonProcess pgadmin user=pgadmin group=pgadmin processes=1 threads=25 \
    python-path=/usr/lib/python3.12/site-packages/pgadmin4 \
    home=/var/lib/pgadmin lang=en_US.UTF-8 locale=en_US.UTF-8
WSGIScriptAlias /pgadmin4 /usr/lib/python3.12/site-packages/pgadmin4/pgAdmin4.wsgi

<Directory /usr/lib/python3.12/site-packages/pgadmin4/>
    WSGIProcessGroup pgadmin
    WSGIApplicationGroup %{GLOBAL}
    Require all granted
</Directory>
```

(`10-wsgi-python3.conf` from `python3.12-mod_wsgi` already loads the module in `conf.modules.d`; the explicit `LoadModule` here is harmless — httpd ignores a second identical `LoadModule` — and keeps the snippet self-describing. If the OBS build's `%check`/smoke test shows `module wsgi_module is already loaded, skipping` warnings, that is expected.)

`rpm/percona-pgadmin4-setup-web` (installed as `%{_bindir}/percona-pgadmin4-setup-web`, 0755):

```bash
#!/bin/bash
# percona-pgadmin4-setup-web — one-time host setup for the httpd (mod_wsgi) deployment.
#
#   1. creates the pgAdmin configuration database and the initial admin user
#      (prompts unless PGADMIN_SETUP_EMAIL and PGADMIN_SETUP_PASSWORD are set)
#   2. fixes ownership of /var/lib/pgadmin and /var/log/pgadmin
#   3. on SELinux hosts, allows httpd network access and labels the data directories
#   4. enables and restarts httpd (skip with --no-service or when not booted with systemd)
set -euo pipefail

NO_SERVICE=0
for arg in "$@"; do
    case "$arg" in
        --no-service) NO_SERVICE=1 ;;
        -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "percona-pgadmin4-setup-web must run as root" >&2
    exit 1
fi

PGADMIN_DIR=/usr/lib/python3.12/site-packages/pgadmin4
DATA_DIR=/var/lib/pgadmin
LOG_DIR=/var/log/pgadmin

echo "Setting up pgAdmin 4 in web mode (httpd + mod_wsgi)..."
mkdir -p "${DATA_DIR}/sessions" "${DATA_DIR}/storage" "${LOG_DIR}"
chown -R pgadmin:pgadmin "${DATA_DIR}" "${LOG_DIR}"

if [ ! -e "${DATA_DIR}/pgadmin4.db" ]; then
    echo "Creating configuration database..."
    (cd "${PGADMIN_DIR}" && runuser -u pgadmin -- /usr/bin/python3.12 setup.py setup-db)
    chmod 0600 "${DATA_DIR}/pgadmin4.db"
fi

if command -v getenforce >/dev/null 2>&1 && [ "$(getenforce)" != "Disabled" ]; then
    echo "Configuring SELinux..."
    setsebool -P httpd_can_network_connect 1 || true
    setsebool -P httpd_can_network_connect_db 1 || true
    if command -v semanage >/dev/null 2>&1; then
        semanage fcontext -a -t httpd_var_lib_t "${DATA_DIR}(/.*)?" 2>/dev/null || \
            semanage fcontext -m -t httpd_var_lib_t "${DATA_DIR}(/.*)?"
        semanage fcontext -a -t httpd_log_t "${LOG_DIR}(/.*)?" 2>/dev/null || \
            semanage fcontext -m -t httpd_log_t "${LOG_DIR}(/.*)?"
        restorecon -R "${DATA_DIR}" "${LOG_DIR}"
    else
        echo "warning: semanage not found (install policycoreutils-python-utils); skipping file contexts" >&2
    fi
fi

if [ "${NO_SERVICE}" -eq 0 ] && [ -d /run/systemd/system ]; then
    echo "Enabling and restarting httpd..."
    systemctl enable --now httpd
    systemctl restart httpd
else
    echo "Skipping the httpd service step (--no-service or no systemd)."
fi

echo "pgAdmin 4 is available at http://$(hostname -f 2>/dev/null || hostname)/pgadmin4"
```

- [ ] **Step 6: The spec**

`rpm/percona-pgadmin4.spec`:

```spec
# Ported from openSUSE's pgadmin4.spec (Factory) to EL9 + python3.12 for UBI-9.
# Bumps: change <param name="revision"> in obs/_service (REL-<major>_<minor>) and
# re-check web/requirements.txt against the python3-* packages of this project.
%global debug_package %{nil}
%global __ospython %{_bindir}/python3.12
%global python3_pkgprefix python3.12
%global python3_buildversion 3.12
%global __requires_exclude ^python3\\.12dist
%global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '%{_prefix}', 'base': '%{_prefix}'}))")
%global pgadmin_dir %{python3_sitelib}/pgadmin4
%global pgadmin_user pgadmin
%global pgadmin_data %{_sharedstatedir}/pgadmin
%global pgadmin_log %{_localstatedir}/log/pgadmin
%global pgadmin_etc %{_sysconfdir}/pgadmin

Name:           percona-pgadmin4
Version:        1.0.0
Release:        1%{?dist}
Summary:        Management tool for PostgreSQL (pgAdmin 4, server mode)
License:        PostgreSQL
URL:            https://www.pgadmin.org
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>

Source0:        %{name}-%{version}.tar.gz
Source1:        config_distro.py
Source2:        run_pgadmin.py
Source3:        gunicorn_config.py
Source4:        percona-pgadmin4-gunicorn
Source5:        percona-pgadmin4.service
Source6:        percona-pgadmin4.sysusers
Source7:        percona-pgadmin4.tmpfiles
Source8:        percona-pgadmin4-httpd.conf
Source9:        percona-pgadmin4-setup-web
Source20:       package-lock.json
# SourceNNNNN: npm tarballs vendored by the node_modules service (offset 10000)
Source100:      node_modules.spec.inc
%include        %{_sourcedir}/node_modules.spec.inc

# Help > Online Help opens the upstream documentation for the running version
# (no local Sphinx build; -doc ships the rst sources).
Patch1:         0001-help-menu-online-docs.patch
# openSUSE: do not fail at import time when the cloud SDKs are missing
Patch2:         0002-make-cloud-packages-optional.patch
# openSUSE: create data directories with os.makedirs (parents) instead of os.mkdir
Patch3:         0003-use-os-makedirs.patch

BuildArch:      noarch

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
BuildRequires:  local-npm-registry
BuildRequires:  nodejs >= 20
BuildRequires:  npm
BuildRequires:  systemd-rpm-macros
# runtime stack, needed for the %%check import (cloud SDKs — boto3, azure-*, google-* — are
# not packaged; Patch2 makes the cloud deployment module tolerate their absence)
BuildRequires:  %{python3_pkgprefix}-flask
BuildRequires:  %{python3_pkgprefix}-flask-babel
BuildRequires:  %{python3_pkgprefix}-flask-compress
BuildRequires:  %{python3_pkgprefix}-flask-login
BuildRequires:  %{python3_pkgprefix}-flask-mail
BuildRequires:  %{python3_pkgprefix}-flask-migrate
BuildRequires:  %{python3_pkgprefix}-flask-paranoid
BuildRequires:  %{python3_pkgprefix}-flask-security-too
BuildRequires:  %{python3_pkgprefix}-flask-socketio
BuildRequires:  %{python3_pkgprefix}-flask-sqlalchemy
BuildRequires:  %{python3_pkgprefix}-flask-wtf
BuildRequires:  %{python3_pkgprefix}-wtforms
BuildRequires:  %{python3_pkgprefix}-werkzeug
BuildRequires:  %{python3_pkgprefix}-sqlalchemy
BuildRequires:  %{python3_pkgprefix}-sqlparse
BuildRequires:  %{python3_pkgprefix}-psycopg
BuildRequires:  %{python3_pkgprefix}-psycopg-c
BuildRequires:  %{python3_pkgprefix}-libpass
BuildRequires:  %{python3_pkgprefix}-bcrypt
BuildRequires:  %{python3_pkgprefix}-authlib
BuildRequires:  %{python3_pkgprefix}-pyotp
BuildRequires:  %{python3_pkgprefix}-qrcode
BuildRequires:  %{python3_pkgprefix}-ldap3
BuildRequires:  %{python3_pkgprefix}-gssapi
BuildRequires:  %{python3_pkgprefix}-sshtunnel
BuildRequires:  %{python3_pkgprefix}-paramiko
BuildRequires:  %{python3_pkgprefix}-keyring
BuildRequires:  %{python3_pkgprefix}-typer
BuildRequires:  %{python3_pkgprefix}-jsonformatter
BuildRequires:  %{python3_pkgprefix}-libgravatar
BuildRequires:  %{python3_pkgprefix}-user-agents
BuildRequires:  %{python3_pkgprefix}-pytz
BuildRequires:  %{python3_pkgprefix}-certifi
BuildRequires:  %{python3_pkgprefix}-dateutil
BuildRequires:  %{python3_pkgprefix}-psutil
BuildRequires:  python%{python3_buildversion}-cryptography
BuildRequires:  python%{python3_buildversion}-urllib3

Requires:       %{python3_pkgprefix}-flask
Requires:       %{python3_pkgprefix}-flask-babel
Requires:       %{python3_pkgprefix}-flask-compress
Requires:       %{python3_pkgprefix}-flask-login
Requires:       %{python3_pkgprefix}-flask-mail
Requires:       %{python3_pkgprefix}-flask-migrate
Requires:       %{python3_pkgprefix}-flask-paranoid
Requires:       %{python3_pkgprefix}-flask-security-too
Requires:       %{python3_pkgprefix}-flask-socketio
Requires:       %{python3_pkgprefix}-flask-sqlalchemy
Requires:       %{python3_pkgprefix}-flask-wtf
Requires:       %{python3_pkgprefix}-wtforms
Requires:       %{python3_pkgprefix}-werkzeug
Requires:       %{python3_pkgprefix}-sqlalchemy
Requires:       %{python3_pkgprefix}-sqlparse
Requires:       %{python3_pkgprefix}-psycopg
Requires:       %{python3_pkgprefix}-psycopg-c
Requires:       %{python3_pkgprefix}-libpass
Requires:       %{python3_pkgprefix}-bcrypt
Requires:       %{python3_pkgprefix}-authlib
Requires:       %{python3_pkgprefix}-pyotp
Requires:       %{python3_pkgprefix}-qrcode
Requires:       %{python3_pkgprefix}-ldap3
Requires:       %{python3_pkgprefix}-gssapi
Requires:       %{python3_pkgprefix}-sshtunnel
Requires:       %{python3_pkgprefix}-paramiko
Requires:       %{python3_pkgprefix}-keyring
Requires:       %{python3_pkgprefix}-typer
Requires:       %{python3_pkgprefix}-jsonformatter
Requires:       %{python3_pkgprefix}-libgravatar
Requires:       %{python3_pkgprefix}-user-agents
Requires:       %{python3_pkgprefix}-pytz
Requires:       %{python3_pkgprefix}-certifi
Requires:       %{python3_pkgprefix}-dateutil
Requires:       %{python3_pkgprefix}-psutil
Requires:       python%{python3_buildversion}-cryptography
Requires:       python%{python3_buildversion}-setuptools
Requires:       python%{python3_buildversion}-urllib3
Requires(pre):  shadow-utils
Provides:       pgadmin4 = %{version}-%{release}
Suggests:       %{name}-doc

%description
pgAdmin 4 is the leading open source management tool for PostgreSQL. This
package installs the web application in server mode under
%{pgadmin_dir}, with distribution defaults in config_distro.py (data in
%{pgadmin_data}, logs in %{pgadmin_log}, site overrides in
%{pgadmin_etc}/config_system.py). Any setting can also be overridden with a
PGADMIN_CONFIG_<SETTING> environment variable. Install %{name}-gunicorn to run
it stand-alone (containers, systemd) or %{name}-httpd to serve it from Apache.

%package gunicorn
Summary:        Run pgAdmin 4 stand-alone under gunicorn
Requires:       %{name} = %{version}-%{release}
Requires:       %{python3_pkgprefix}-gunicorn
%{?systemd_requires}

%description gunicorn
Launcher script (%{_bindir}/percona-pgadmin4-gunicorn) and systemd unit that
serve pgAdmin 4 with gunicorn. Configured through the environment
(PGADMIN_LISTEN_ADDRESS/PORT, PGADMIN_ENABLE_TLS, PGADMIN_DEFAULT_EMAIL/PASSWORD,
PGADMIN_CONFIG_<SETTING>); this is the runtime used by container images. The
service is not enabled by default.

%package httpd
Summary:        Serve pgAdmin 4 from Apache httpd with mod_wsgi
Requires:       %{name} = %{version}-%{release}
Requires:       httpd
Requires:       python%{python3_buildversion}-mod_wsgi

%description httpd
Apache configuration (/pgadmin4 via mod_wsgi, one daemon process with 25
threads running as the pgadmin user) and the percona-pgadmin4-setup-web helper
that creates the configuration database, applies SELinux settings and
restarts httpd.

%package doc
Summary:        Documentation sources for pgAdmin 4
BuildArch:      noarch

%description doc
The reStructuredText sources of the pgAdmin 4 documentation
(%{_docdir}/%{name}/en_US). The rendered manual for the installed release is
online at https://www.pgadmin.org/docs/pgadmin4/; the application's Help menu
links there.

%prep
%autosetup -p1 -n %{name}-%{version}

# The git tag is exported without .git: record the upstream commit the way
# pkg/src/build.sh does, and neutralise the "git:hash" npm script.
awk '/^commit:/ {print $2}' %{_sourcedir}/%{name}.obsinfo > web/commit_hash
sed -i 's/"git:hash": "[^"]*"/"git:hash": "exit 0"/' web/package.json
# Upstream pins Yarn via "packageManager"; npm refuses to run with it set.
sed -i -z 's/,\n *"packageManager": "[^"]*"//' web/package.json
# Executable bits and shebangs on files that end up in site-packages
chmod -x web/pgadmin/misc/cloud/*.py web/pgadmin/misc/cloud/utils/*.py 2>/dev/null || :
sed -i '1{/^#!/d}' web/pgadmin/misc/cloud/*.py web/pgadmin/misc/cloud/utils/*.py 2>/dev/null || :
find web/pgadmin -name '*.py' -perm /111 -exec chmod -x {} +
# Vendored npm dependencies: package-lock.json + tarballs served by local-npm-registry
cp %{SOURCE20} web/package-lock.json

%build
# Frontend
pushd web
local-npm-registry %{_sourcedir} install --legacy-peer-deps --ignore-scripts --no-audit --no-fund
NODE_ENV=production NODE_OPTIONS=--max-old-space-size=3072 npx webpack --config webpack.config.js
rm -rf node_modules
popd

# Wheel (upstream's pip packaging helper; produces pgadmin4-<ver>-py3-none-any.whl)
pushd pkg/pip
%{__ospython} setup_pip.py bdist_wheel
popd

%install
%{__ospython} -m pip install --root %{buildroot} --no-deps --no-index --no-warn-script-location \
    pkg/pip/dist/pgadmin4-*.whl

# The launcher and httpd conf hard-code the site-packages path: assert it.
test "%{python3_sitelib}" = "%{_prefix}/lib/python%{python3_buildversion}/site-packages"

# distribution config + gunicorn entry points
install -m 0644 %{SOURCE1} %{buildroot}%{pgadmin_dir}/config_distro.py
install -m 0644 %{SOURCE2} %{buildroot}%{pgadmin_dir}/run_pgadmin.py
install -m 0644 %{SOURCE3} %{buildroot}%{pgadmin_dir}/gunicorn_config.py

# The wheel installs upstream's CLI entry point as pgadmin4-cli; keep it.
# Data, log and configuration directories
install -d -m 0750 %{buildroot}%{pgadmin_data}
install -d -m 0755 %{buildroot}%{pgadmin_data}/storage
install -d -m 0700 %{buildroot}%{pgadmin_data}/sessions
install -d -m 0750 %{buildroot}%{pgadmin_log}
install -d -m 0750 %{buildroot}%{pgadmin_etc}
cat > %{buildroot}%{pgadmin_etc}/config_system.py <<'EOF'
# Site-specific pgAdmin 4 settings (highest precedence; imported after config_distro.py
# and config_local.py). Any setting from config.py may be set here, e.g.
#   DEFAULT_SERVER = '0.0.0.0'
#   MAX_LOGIN_ATTEMPTS = 3
EOF

# users and runtime dirs
install -D -m 0644 %{SOURCE6} %{buildroot}%{_sysusersdir}/%{name}.conf
install -D -m 0644 %{SOURCE7} %{buildroot}%{_tmpfilesdir}/%{name}.conf

# -gunicorn
install -D -m 0755 %{SOURCE4} %{buildroot}%{_bindir}/percona-pgadmin4-gunicorn
install -D -m 0644 %{SOURCE5} %{buildroot}%{_unitdir}/%{name}.service
install -d -m 0755 %{buildroot}/run/pgadmin4

# -httpd
install -D -m 0644 %{SOURCE8} %{buildroot}%{_sysconfdir}/httpd/conf.d/%{name}.conf
install -D -m 0755 %{SOURCE9} %{buildroot}%{_bindir}/percona-pgadmin4-setup-web

# -doc: rst sources (drop build tooling and editor artefacts)
install -d -m 0755 %{buildroot}%{_docdir}/%{name}
cp -a docs/en_US %{buildroot}%{_docdir}/%{name}/en_US
rm -f %{buildroot}%{_docdir}/%{name}/en_US/Makefile.sphinx \
      %{buildroot}%{_docdir}/%{name}/en_US/conf.py \
      %{buildroot}%{_docdir}/%{name}/en_US/build_code_snippet.py \
      %{buildroot}%{_docdir}/%{name}/en_US/.gitignore
find %{buildroot}%{_docdir}/%{name}/en_US -name '*.excalidraw' -delete
install -m 0644 LICENSE README.md %{buildroot}%{_docdir}/%{name}/

# byte-compile with the interpreter that runs the app
%{__ospython} -m compileall -q -s %{buildroot} -p / %{buildroot}%{pgadmin_dir}

%check
PYTHONPATH=%{buildroot}%{pgadmin_dir} PGADMIN_CONFIG_HELP_PATH=/nonexistent \
    %{__ospython} -P -c "import config, config_distro; assert config.SERVER_MODE is True; assert config.HELP_PATH == '/nonexistent'"

%pre
%sysusers_create_compat %{SOURCE6}

%post gunicorn
%systemd_post %{name}.service
%tmpfiles_create %{_tmpfilesdir}/%{name}.conf

%preun gunicorn
%systemd_preun %{name}.service

%postun gunicorn
%systemd_postun_with_restart %{name}.service

%files
%license LICENSE
%doc README.md
%{pgadmin_dir}/
%{python3_sitelib}/pgadmin4-*.dist-info/
%{_bindir}/pgadmin4-cli
%{_sysusersdir}/%{name}.conf
%dir %attr(0750,%{pgadmin_user},%{pgadmin_user}) %{pgadmin_data}
%dir %attr(0755,%{pgadmin_user},%{pgadmin_user}) %{pgadmin_data}/storage
%dir %attr(0700,%{pgadmin_user},%{pgadmin_user}) %{pgadmin_data}/sessions
%dir %attr(0750,%{pgadmin_user},%{pgadmin_user}) %{pgadmin_log}
%dir %attr(0750,root,%{pgadmin_user}) %{pgadmin_etc}
%config(noreplace) %attr(0640,root,%{pgadmin_user}) %{pgadmin_etc}/config_system.py

%files gunicorn
%{_bindir}/percona-pgadmin4-gunicorn
%{_unitdir}/%{name}.service
%{_tmpfilesdir}/%{name}.conf
%dir %attr(0755,%{pgadmin_user},%{pgadmin_user}) /run/pgadmin4

%files httpd
%config(noreplace) %{_sysconfdir}/httpd/conf.d/%{name}.conf
%{_bindir}/percona-pgadmin4-setup-web

%files doc
%docdir %{_docdir}/%{name}/en_US
%{_docdir}/%{name}/en_US/

%changelog
* Fri Aug 28 2026 Percona Development Team <https://jira.percona.com> - 1.0.0-1
- Initial percona-pgadmin4 package (pgAdmin 4, server mode) for UBI-9, ported
  from openSUSE's pgadmin4.spec: gunicorn and httpd/mod_wsgi runtimes, rst docs.
```

Notes the implementer must respect:
- `%{__requires_exclude}` keeps rpm from generating `python3.12dist(...)` requirements (which UBI's stack does not provide) — the same setting the SP3 template uses.
- The `%files` entry `%{_bindir}/pgadmin4-cli` matches the console script declared by `pkg/pip/setup_pip.py` (`entry_points console_scripts pgadmin4-cli = pgadmin4.setup:main`). If the OBS build's `%install` shows a different name in `--no-warn-script-location` output, adjust in the fix loop and record it in the ledger.
- `%license LICENSE` / `README.md` are at the tarball root (upstream repo root).
- `LICENSE`/`README.md` are also copied under `%{_docdir}` for the `-doc` layout; both are listed only in the main package via `%license`/`%doc` — the copies under `%{_docdir}/%{name}/` are picked up by `%doc`'s directory. If rpmbuild reports them unpackaged, replace the `install -m 0644 LICENSE README.md …` line with nothing (they are already `%license`/`%doc`).
- The `%check` imports `config` with `PYTHONPATH` set to the installed tree so `config_distro.py` is exercised; `HELP_PATH` override proves the env mapping runs in situ.

- [ ] **Step 7: The three patches**

`rpm/0001-help-menu-online-docs.patch` — replaces the local help URL in the Help menu with the upstream online documentation for the running release:

```diff
From: Percona Development Team <https://jira.percona.com>
Subject: Help menu: link "Online Help" to the upstream docs for this release

The package ships the documentation sources only (-doc); the rendered
manual lives at https://www.pgadmin.org/docs/pgadmin4/<release>/.

--- a/web/pgadmin/help/__init__.py
+++ b/web/pgadmin/help/__init__.py
@@ -34,7 +34,8 @@
                      priority=100,
                      target='pgadmin_help',
                      icon='fa fa-question',
-                     url=url_for('help.static', filename='index.html')),
+                     url='https://www.pgadmin.org/docs/pgadmin4/%s.%s/' % (
+                         config.APP_RELEASE, config.APP_REVISION)),
 
             MenuItem(name='mnu_pgadmin_website',
                      label=gettext('pgAdmin Website'),
```

The hunk was generated against REL-9_17 and applies cleanly (no fuzz, no offset); Step 8 re-checks it with `patch -p1 --dry-run`. `import config` already exists in that module (line 14 in REL-9_17); `url_for` stays imported because `HelpModule` uses it elsewhere — do not remove the import.

`rpm/0002-make-cloud-packages-optional.patch` — openSUSE's patch, verbatim (Appendix D).

`rpm/0003-use-os-makedirs.patch` — openSUSE's patch, verbatim (Appendix E).

- [ ] **Step 8: Local verification**

1. Fresh upstream checkout for patch checks (outside the worktree, in `$SCRATCH/pgadmin-src`):
   `git clone --depth 1 --branch REL-9_17 https://github.com/pgadmin-org/pgadmin4.git $SCRATCH/pgadmin-src/pgadmin4`
   then, from inside it, `patch -p1 --dry-run < <worktree>/root/ppg/devel/pgadmin/percona-pgadmin4/rpm/0001-help-menu-online-docs.patch` (and 0002, 0003). Expected: `checking file web/pgadmin/help/__init__.py` with no `FAILED`. If `0002` or `0003` report failures (openSUSE wrote them against 8.2/7.4), regenerate the hunk against the 9.17 file keeping the same semantic change and note it in the ledger.
2. Scripts: `bash -n root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4-gunicorn`, `bash -n …/percona-pgadmin4-setup-web`, `python3 -m py_compile …/config_distro.py …/run_pgadmin.py …/gunicorn_config.py`, `systemd-analyze verify --man=no root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.service` (expect only "Command … is not executable" style warnings about `/usr/bin/percona-pgadmin4-gunicorn`, nothing about syntax).
3. Config unit check: `venv/bin/python $SCRATCH/check_config_distro.py` → `OK`.
4. Sync dry-run (runs the whole service chain locally — several minutes; it clones REL-9_17, generates the lockfile, downloads ~1500 npm tarballs):
   `venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:devel:pgadmin percona-pgadmin4`
   Expected: dry-run summary listing `percona-pgadmin4-9.17.obscpio` (or the `.tar.gz` if the tool runs buildtime services), `percona-pgadmin4.obsinfo`, `package-lock.json`, `node_modules.obscpio`, `node_modules.spec.inc`, the spec, the nine support files and three patches. The tool caches service output under its cache dir; locate `node_modules.spec.inc` in that output (the dry-run prints the work directory) and copy it to `$SCRATCH/pgadmin-src/node_modules.spec.inc`.
5. Spec parse with the real include:
   `rpmspec -P --define "_sourcedir $SCRATCH/pgadmin-src" root/ppg/devel/pgadmin/percona-pgadmin4/rpm/percona-pgadmin4.spec > $SCRATCH/pgadmin-src/expanded.spec` → exit 0; `grep -c '^%files' $SCRATCH/pgadmin-src/expanded.spec` → `4`; `grep -c '^Source1[0-9][0-9][0-9][0-9]:' $SCRATCH/pgadmin-src/expanded.spec` → a number > 1000 (vendored tarballs).
   If the sync dry-run cannot produce the include (e.g. no network), create a stub `$SCRATCH/pgadmin-src/node_modules.spec.inc` containing `Source10000: react-19.0.0.tgz` and run the same `rpmspec -P`; record in the ledger that the include check ran against a stub.

- [ ] **Step 9: Commit**

```bash
git add root/ppg/devel/pgadmin/percona-pgadmin4
git commit -s -m "pgadmin: add percona-pgadmin4 (pgAdmin 4 9.17, server mode) for UBI-9

Ported from openSUSE's pgadmin4.spec to EL9/python3.12. Sources come
from the upstream REL-9_17 tag through obs_scm -> npm_lockfile ->
node_modules; webpack runs against local-npm-registry. Subpackages:
-gunicorn (launcher + systemd unit, PGADMIN_CONFIG_* env mapping; the
container runtime), -httpd (mod_wsgi conf + percona-pgadmin4-setup-web),
-doc (rst sources; Help menu links to the online manual)."
```

No push in this task.

---

### Task 3: Documentation

**Goal:** Record the pgadmin project's application package in the tree/tool docs so the next person finds it where the other projects are described.

**Files:**
- Modify: `root/README.md` — the `ppg/devel/pgadmin` entry (or the devel-tier section that lists project purposes).
- Modify: `docs/PERCONA_OBS_TOOL.md` — the section that mentions `npm_lockfile`/`node_modules` (added in SP1) gets one paragraph on how `percona-pgadmin4` uses the chain.

**Acceptance Criteria:**
- [ ] `grep -n percona-pgadmin4 root/README.md docs/PERCONA_OBS_TOOL.md` shows at least one hit in each file.
- [ ] `root/README.md` describes `ppg/devel/pgadmin` as: python3.12 stack (`python3-*`), aggregates of `ppg:common:deps` runtime packages, and `percona-pgadmin4` (+ `-gunicorn`/`-httpd`/`-doc`), built for UBI_9 only.
- [ ] No other sections are reflowed or reworded (diff limited to the additions).

**Verify:** `git diff --stat HEAD~1` after the commit → exactly the two files.

**Steps:**

- [ ] **Step 1: `root/README.md`**

Find the line that introduces `ppg/devel/pgadmin` (`grep -n pgadmin root/README.md`). Directly after that entry's existing description, add:

```markdown
  `percona-pgadmin4` is the application package (pgAdmin 4 in server mode, built from the
  upstream git tag through `obs_scm` → `npm_lockfile` → `node_modules`, with webpack served by
  `local-npm-registry`). It ships `-gunicorn` (launcher + systemd unit; the runtime a container
  image uses), `-httpd` (Apache + `python3.12-mod_wsgi`) and `-doc` (rst sources). The
  `python3-*` packages are its Python 3.12 dependency stack; `python3-click`, `python3-six`,
  `python3-dateutil`, `python3-psutil` and `python3-dns` are `_aggregate`s of `ppg:common:deps`
  so the project repository installs on its own. UBI_9 only.
```

Match the indentation of the surrounding list item. If `root/README.md` has no `pgadmin` entry yet, add one under the devel-tier listing following the format of the neighbouring entries (project path, one-line purpose, then the paragraph above).

- [ ] **Step 2: `docs/PERCONA_OBS_TOOL.md`**

Find the `npm_lockfile` description (`grep -n npm_lockfile docs/PERCONA_OBS_TOOL.md`). After the paragraph that explains the chain, add:

```markdown
`root/ppg/devel/pgadmin/percona-pgadmin4/obs/_service` is the reference user of this chain:
`obs_scm` (tag `REL-9_17`, `versionrewrite-pattern REL-(\d+)_(\d+)` → `9.17`) →
`npm_lockfile` (`subdir web`) → `node_modules` (`source-offset 10000`) → `tar`/`recompress`/
`set_version` at build time. A `sync push --dry-run` of that package runs the whole chain
locally and takes several minutes (it downloads every npm tarball once; later runs hit the
service cache).
```

- [ ] **Step 3: Commit**

```bash
git add root/README.md docs/PERCONA_OBS_TOOL.md
git commit -s -m "docs: describe percona-pgadmin4 and the pgadmin project layout"
```

---

### Task 4: OBS build loop via PR #12

**Goal:** Get every package in `isv:percona:PR:pr-12:ppg:devel:pgadmin` (UBI_9) to `succeeded` after pushing Tasks 1–3: first the stack commit, then the application package — fixing build failures in rounds, each push approved by the user.

**Files:**
- Modify (as failures dictate): files under `root/ppg/devel/pgadmin/` only.

**Acceptance Criteria:**
- [ ] Push 1 (after user approval): branch `pgadmin-sp1` pushed to `origin` with Tasks 1–3 commits; PR #12 CI sync run succeeds (`gh run list --branch pgadmin-sp1 --limit 3` shows the `obs-sync`/PR workflow `completed success`).
- [ ] `https://api.opensuse.org/public/build/isv:percona:PR:pr-12:ppg:devel:pgadmin/_result?repository=UBI_9` shows every `python3-*` package `succeeded` (the 13 rendered ones included), the five aggregates present, and `percona-pgadmin4` `succeeded`, with `code="published"` for the repository.
- [ ] Every fix round is one commit per root cause with the OBS log excerpt in its message body; each push asked for and approved individually.
- [ ] `_result` polled with the `Monitor`/background-script pattern (no foreground sleeps) — the controller, not the implementer, waits.

**Verify:** `curl -s 'https://api.opensuse.org/public/build/isv:percona:PR:pr-12:ppg:devel:pgadmin/_result?repository=UBI_9&arch=x86_64' | grep -c 'code="succeeded"'` → equals the number of source packages (`ls root/ppg/devel/pgadmin | wc -l` minus the 5 aggregates, which report `code="succeeded"` too once published — accept either count as long as no `failed`/`unresolvable`/`broken` appears: `grep -cE 'code="(failed|unresolvable|broken)"'` → `0`).

**Steps:**

- [ ] **Step 1: Ask for push 1**

Controller action (not a subagent): ask the user "Tasks 1–3 are committed (stack bump for 9.17, percona-pgadmin4, docs). Push `pgadmin-sp1` to origin so PR #12 syncs them?" Only on a yes:

```bash
git push origin pgadmin-sp1
```

Record the push SHA in the ledger. Nothing else is pushed without a fresh yes.

- [ ] **Step 2: Wait for the sync**

```bash
gh run list --branch pgadmin-sp1 --limit 3
```

Wait for the PR workflow's sync job to complete (`Monitor` on `gh run watch <id> --exit-status`, or a background `until` script checking `gh run view <id> --json status -q .status` every 60 s). On `failure`, read the log (`gh run view <id> --log-failed`) — a `sync` failure is a tooling problem, not a packaging one: fix the tree (e.g. `_service` XML error), commit, and ask before pushing again.

- [ ] **Step 3: Watch the build**

Poll `https://api.opensuse.org/public/build/isv:percona:PR:pr-12:ppg:devel:pgadmin/_result?repository=UBI_9&arch=x86_64` every 5 minutes with a background script (`$SCRATCH/watch_obs.sh` pattern from SP3: `until` loop writing the summary counts to a file; the controller reads the file). The build of `percona-pgadmin4` alone takes 20–40 minutes (webpack); the whole project after a stack push can take 1–3 hours on the x86_64 scheduler. States: `scheduled`/`building`/`blocked` → keep waiting; `unresolvable` → dependency naming issue (check `_result` `details`); `failed` → read the log:

```bash
curl -s 'https://api.opensuse.org/public/build/isv:percona:PR:pr-12:ppg:devel:pgadmin/UBI_9/x86_64/<package>/_log' | tail -n 200
```

- [ ] **Step 4: Fix rounds**

For each failed package, diagnose from the log and fix the root cause in the tree. Expected failure classes and their fixes:

| Symptom in log | Fix |
|---|---|
| `nothing provides python3.12-<x>` for a stack package | the dependency is missing from the project — add its render or fix the `Requires` name (`%{python3_pkgprefix}-<pypi-normalised>`); for a `ppg:common:deps` package add an `_aggregate` |
| `npm ERR! 404 … local-npm-registry` / `ETARGET` | the lockfile and the vendored tarballs disagree: re-run the sync dry-run to regenerate `package-lock.json`/`node_modules.obscpio` (they are service outputs; a re-sync refreshes them) — check `npm_lockfile` flags; if npm needs `--legacy-peer-deps` to resolve, add `<param name="npm-flags">--legacy-peer-deps</param>` to `npm_lockfile` |
| webpack `JavaScript heap out of memory` | raise `NODE_OPTIONS=--max-old-space-size=4096` in `%build` |
| `error: Installed (but unpackaged) file(s)` | add the listed paths to the right `%files` section (typical: `%{_bindir}/pgadmin4-cli` name, `%{_docdir}/%{name}/LICENSE`) |
| `%check` `ModuleNotFoundError: <mod>` | a runtime dependency is missing from `BuildRequires`/`Requires` — add both |
| `ImportError` from `passlib` | `python3.12-libpass` not installed/Provides missing — check Task 1 output |
| `setup_pip.py: error: invalid command 'bdist_wheel'` | `python3.12-wheel` missing from BuildRequires (it is listed — check the log for the real cause) |
| gssapi/psycopg-c `Cython` version errors | Task 1 pinned Cython 3.2.4; confirm `python3-cython` built before them (`blocked` → wait) |

Commit each fix as `pgadmin: fix <package> — <cause>` with the log excerpt in the body. Ask the user before every push: "Fix round N (<packages>): push?" Then repeat Steps 2–3. If a fix is confined to one package that has no dependants building, say so when asking (a single-package sync does not cancel the others' builds).

- [ ] **Step 5: Record the outcome in the ledger**

Append to the ledger: the final `_result` summary (counts by state), the list of fix commits, and the published repo URL `https://download.opensuse.org/repositories/isv:/percona:/PR:/pr-12:/ppg:/devel:/pgadmin/UBI_9/`.

---

### Task 5: Container smoke test (podman, UBI-9)

**Goal:** Prove the published PR #12 repository installs and runs pgAdmin 4 the way the future container image will: `percona-pgadmin4` + `-gunicorn` installed into a UBI-9 container, first start creates the admin user from the environment, `GET /login` returns HTTP 200 and the page identifies as pgAdmin 4 9.17; and `-httpd` installs cleanly with `httpd -t` accepting the shipped configuration.

**USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Create: `$SCRATCH/smoke/pr12.repo`, `$SCRATCH/smoke/smoke-gunicorn.sh`, `$SCRATCH/smoke/smoke-httpd.sh` (scratch only — nothing in the repo unless a packaging fix is needed).
- Modify (only if the test finds a packaging defect): files under `root/ppg/devel/pgadmin/percona-pgadmin4/`.

**Acceptance Criteria:**
- [ ] `smoke-gunicorn.sh` output contains `INSTALL OK`, `SETUP OK` (the `pgadmin4.db` exists after first start), `HTTP 200` for `http://127.0.0.1:8080/login`, and `VERSION OK 9.17` (the login page HTML contains `9.17`).
- [ ] `smoke-gunicorn.sh` also shows the env mapping works: with `PGADMIN_CONFIG_MAX_LOGIN_ATTEMPTS=7` set, `python3.12 -c` inside the container prints `7` from `config.MAX_LOGIN_ATTEMPTS`.
- [ ] `smoke-httpd.sh` output contains `INSTALL OK` and `Syntax OK` from `httpd -t` with `/etc/httpd/conf.d/percona-pgadmin4.conf` present and `mod_wsgi_python3.so` loaded (no `Cannot load` errors).
- [ ] Captured outputs saved to `$SCRATCH/smoke/gunicorn.log` and `$SCRATCH/smoke/httpd.log`; the ledger cites both paths and quotes the four OK tokens.

**Verify:** `bash $SCRATCH/smoke/smoke-gunicorn.sh 2>&1 | tee $SCRATCH/smoke/gunicorn.log | grep -E 'INSTALL OK|SETUP OK|HTTP 200|VERSION OK|ENV OK 7'` → five lines; `bash $SCRATCH/smoke/smoke-httpd.sh 2>&1 | tee $SCRATCH/smoke/httpd.log | grep -E 'INSTALL OK|Syntax OK'` → two lines.

**Steps:**

- [ ] **Step 1: Repository file**

`$SCRATCH/smoke/pr12.repo` (the PR project's published UBI_9 repo; GPG checking is off because the PR project signs with the OBS project key that the container does not trust):

```ini
[pr12-pgadmin]
name=isv:percona:PR:pr-12:ppg:devel:pgadmin (UBI_9)
baseurl=https://download.opensuse.org/repositories/isv:/percona:/PR:/pr-12:/ppg:/devel:/pgadmin/UBI_9/
enabled=1
gpgcheck=0
```

- [ ] **Step 2: gunicorn smoke script**

`$SCRATCH/smoke/smoke-gunicorn.sh`:

```bash
#!/bin/bash
# Install percona-pgadmin4 + -gunicorn in a UBI-9 container from the PR #12 repo,
# start it as the upstream image would, and check the login page.
set -u
HERE=$(dirname "$(readlink -f "$0")")
podman run --rm -v "$HERE/pr12.repo:/etc/yum.repos.d/pr12.repo:ro,z" \
    -e PGADMIN_DEFAULT_EMAIL=admin@example.com -e PGADMIN_DEFAULT_PASSWORD='Sm0keTest!pw' \
    -e PGADMIN_LISTEN_ADDRESS=127.0.0.1 -e PGADMIN_LISTEN_PORT=8080 \
    -e PGADMIN_CONFIG_MAX_LOGIN_ATTEMPTS=7 \
    registry.access.redhat.com/ubi9/ubi:latest bash -c '
set -u
dnf -y -q install percona-pgadmin4 percona-pgadmin4-gunicorn curl >/tmp/dnf.log 2>&1 \
    && echo "INSTALL OK" || { echo "INSTALL FAILED"; tail -n 40 /tmp/dnf.log; exit 1; }
rpm -q percona-pgadmin4 percona-pgadmin4-gunicorn python3.12-gunicorn python3.12-libpass
chown -R pgadmin:pgadmin /var/lib/pgadmin /var/log/pgadmin
cd /usr/lib/python3.12/site-packages/pgadmin4 && PYTHONPATH=$PWD python3.12 -P -c "import config; print(\"ENV OK\", config.MAX_LOGIN_ATTEMPTS)"
runuser -u pgadmin -- env PGADMIN_DEFAULT_EMAIL PGADMIN_DEFAULT_PASSWORD PGADMIN_LISTEN_ADDRESS PGADMIN_LISTEN_PORT \
    /usr/bin/percona-pgadmin4-gunicorn >/tmp/gunicorn.out 2>&1 &
for i in $(seq 1 60); do
    curl -s -o /tmp/login.html -w "%{http_code}" http://127.0.0.1:8080/login >/tmp/code 2>/dev/null && [ "$(cat /tmp/code)" = "200" ] && break
    sleep 2
done
echo "HTTP $(cat /tmp/code 2>/dev/null || echo none)"
test -e /var/lib/pgadmin/pgadmin4.db && echo "SETUP OK" || echo "SETUP FAILED"
grep -q "9\.17" /tmp/login.html && echo "VERSION OK 9.17" || { echo "VERSION CHECK FAILED"; head -c 600 /tmp/login.html; }
echo "--- gunicorn output (tail) ---"; tail -n 30 /tmp/gunicorn.out
'
```

Run it: `bash $SCRATCH/smoke/smoke-gunicorn.sh 2>&1 | tee $SCRATCH/smoke/gunicorn.log`. Pulls `ubi9/ubi` on first use (public registry, no login). The `runuser … env VAR` form passes only the listed variables; `PGADMIN_CONFIG_MAX_LOGIN_ATTEMPTS` is checked separately with the `python3.12 -P -c` line (it prints `ENV OK 7`).

- [ ] **Step 3: httpd smoke script**

`$SCRATCH/smoke/smoke-httpd.sh`:

```bash
#!/bin/bash
# Install percona-pgadmin4-httpd in UBI-9 and check the Apache configuration parses
# with mod_wsgi loaded (no systemd in the container: use httpd -t).
set -u
HERE=$(dirname "$(readlink -f "$0")")
podman run --rm -v "$HERE/pr12.repo:/etc/yum.repos.d/pr12.repo:ro,z" \
    registry.access.redhat.com/ubi9/ubi:latest bash -c '
set -u
dnf -y -q install percona-pgadmin4 percona-pgadmin4-httpd >/tmp/dnf.log 2>&1 \
    && echo "INSTALL OK" || { echo "INSTALL FAILED"; tail -n 40 /tmp/dnf.log; exit 1; }
rpm -q httpd python3.12-mod_wsgi percona-pgadmin4-httpd
test -f /etc/httpd/conf.d/percona-pgadmin4.conf && echo "CONF PRESENT"
httpd -t 2>&1
httpd -M 2>/dev/null | grep -i wsgi || echo "wsgi module NOT listed"
PGADMIN_SETUP_EMAIL=admin@example.com PGADMIN_SETUP_PASSWORD="Sm0keTest!pw" /usr/bin/percona-pgadmin4-setup-web --no-service 2>&1 | tail -n 5
test -e /var/lib/pgadmin/pgadmin4.db && echo "SETUP-WEB OK"
'
```

Run it: `bash $SCRATCH/smoke/smoke-httpd.sh 2>&1 | tee $SCRATCH/smoke/httpd.log`. Expected `Syntax OK`, `wsgi_module (shared)`, `SETUP-WEB OK`. (`percona-pgadmin4-setup-web` runs as root here; SELinux is not enforced inside the container, so the SELinux branch is skipped — that branch is exercised on a host, out of scope for this task.)

- [ ] **Step 4: Fix defects, if any**

A failure here is a packaging defect (missing `Requires`, wrong path in the launcher, `%files` ownership, `passlib` import, missing `libpq`, …). Fix it in `root/ppg/devel/pgadmin/percona-pgadmin4/` (or the stack package), commit as `pgadmin: fix <what> (smoke test)`, and hand back to the controller to run Task 4's push/build loop for that fix (approval per push), then re-run this task's scripts. Do not paper over a failure by editing the smoke script.

- [ ] **Step 5: Ledger**

Append: paths of both logs, the five gunicorn tokens and two httpd tokens as they appeared, the image digest (`podman image inspect registry.access.redhat.com/ubi9/ubi:latest --format '{{.Digest}}'`), and the `percona-pgadmin4` NEVRA installed (`rpm -q` line from the log).

---

### Task 6: Records — spec outcomes and PR #12

**Goal:** Close the loop: the SP4 spec's §9 gets the observed outcomes (what broke in OBS and how it was fixed, smoke-test result), and PR #12's title/body describe SP1–SP4 as delivered.

**Files:**
- Modify: `docs/superpowers/specs/2026-08-28-pgadmin4-package-design.md` — §9 (risks/verification outcomes) and, if Task 2/4 changed a decision (e.g. `pgadmin4-cli` script name, `npm-flags`), the affected §5 line.
- Modify (remote, with approval): PR #12 body via `gh pr edit 12 --repo percona/obs-packaging --body-file …`.

**Acceptance Criteria:**
- [ ] Spec §9 ends with an "Outcomes (2026-08-XX)" list: number of OBS fix rounds and their causes, final `_result` counts, smoke-test tokens with log paths, any decision changed during execution (with the ledger ruling text).
- [ ] The spec no longer states anything the delivered package contradicts (grep for `pgadmin4-cli`, `--legacy-peer-deps`, `REL-9_17`, `Authlib` and compare with the tree).
- [ ] PR #12 body (after user approval of the edit) has an "SP4 — percona-pgadmin4" section: what was added, the stack changes for 9.17, the smoke-test result, and how to run the container (`podman run … -e PGADMIN_DEFAULT_EMAIL … percona-pgadmin4-gunicorn`). No Claude attribution, no `obs-sync` label.
- [ ] Committed (`docs: SP4 outcomes`) and, after approval, pushed with the last fix push or on its own.

**Verify:** `grep -n "Outcomes" docs/superpowers/specs/2026-08-28-pgadmin4-package-design.md` → one hit in §9; `gh pr view 12 --repo percona/obs-packaging --json body -q .body | grep -c "SP4"` → ≥ 1.

**Steps:**

- [ ] **Step 1: Spec §9 outcomes**

Append to §9 of the SP4 spec (Edit tool, after the last risk row/paragraph):

```markdown
### Outcomes (<date>)

- OBS (`isv:percona:PR:pr-12:ppg:devel:pgadmin`, UBI_9): <N> fix rounds — <package: cause → fix, one per line>. Final `_result`: <count> succeeded, 0 failed/unresolvable; repository published.
- Stack for 9.17: 9 bumps, 4 additions (annotated-doc, certifi, libpass, gunicorn), 2 removals (passlib, importlib-resources), 5 `_aggregate`s of `ppg:common:deps`.
- Container smoke test (podman, `ubi9/ubi@<digest>`): `INSTALL OK`, `SETUP OK`, `HTTP 200`, `VERSION OK 9.17`, `ENV OK 7`; httpd: `Syntax OK`, `SETUP-WEB OK`. Logs: `<scratch>/smoke/gunicorn.log`, `<scratch>/smoke/httpd.log`.
- Decisions changed during execution: <none | list with ledger ruling text>.
```

Fill every `<…>` from the ledger and the logs — a placeholder left in the committed spec is a defect.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-08-28-pgadmin4-package-design.md
git commit -s -m "docs: SP4 outcomes (OBS fix rounds, smoke test)"
```

- [ ] **Step 3: PR #12 body (controller, with approval)**

Draft the SP4 section into `$SCRATCH/pr12-body.md` by fetching the current body (`gh pr view 12 --repo percona/obs-packaging --json body -q .body > $SCRATCH/pr12-body.md`) and appending:

```markdown
## SP4 — percona-pgadmin4 (pgAdmin 4 9.17, server mode)

- `root/ppg/devel/pgadmin/percona-pgadmin4`: spec ported from openSUSE to EL9/python3.12; sources via `obs_scm` (REL-9_17) → `npm_lockfile` → `node_modules`; webpack against `local-npm-registry`; wheel via upstream `pkg/pip/setup_pip.py`.
- Subpackages: `-gunicorn` (launcher `percona-pgadmin4-gunicorn` + systemd unit, disabled; `PGADMIN_CONFIG_*` env → settings; the runtime for the container image), `-httpd` (mod_wsgi conf + `percona-pgadmin4-setup-web`), `-doc` (rst sources; Help menu links to the online manual).
- Python stack for 9.17: bumps Flask-Security-Too 5.8.2, Flask-SocketIO 5.6.1, Flask-WTF 1.3.0, gssapi 1.11.1 (Cython 3.2.4), psycopg/psycopg-c 3.3.4, pytz 2026.3.post1, typer 0.26.8; new annotated-doc, certifi, libpass (replaces passlib), gunicorn; removed passlib, importlib-resources; `_aggregate`s of click/six/dateutil/psutil/dns from `ppg:common:deps`.
- Smoke test (UBI-9 container from this PR's repo): install, first-start setup from `PGADMIN_DEFAULT_EMAIL/PASSWORD`, `GET /login` → 200, version 9.17; `httpd -t` Syntax OK with mod_wsgi.
- Try it: `podman run --rm -p 8080:8080 -e PGADMIN_DEFAULT_EMAIL=admin@example.com -e PGADMIN_DEFAULT_PASSWORD=… -e PGADMIN_LISTEN_ADDRESS=0.0.0.0 -e PGADMIN_LISTEN_PORT=8080 <ubi9 image with percona-pgadmin4-gunicorn installed> percona-pgadmin4-gunicorn`.
```

Ask the user: "Update PR #12's body with the SP4 section (draft at `$SCRATCH/pr12-body.md`)?" Only on a yes: `gh pr edit 12 --repo percona/obs-packaging --body-file $SCRATCH/pr12-body.md`. The push of the `docs: SP4 outcomes` commit is asked for separately (or bundled with the last fix push if the user prefers — say so when asking).

---

## Appendix A — `render_stack.py` (final, used by Task 1)

Write verbatim to `$SCRATCH/sp4-bump/render_stack.py`. It is the SP3 renderer plus: `-P` in `%check`, BuildRequires dedupe, PEP 639 `sed` set, `EXTRA_TAGS` (libpass Provides/Conflicts), `EXTRA_REQ`/`CHECK_BR`/`CHECK_IMPORT`, `known.json` name resolution, and same-name `Requires` dedupe (keeps the entry with a version floor).

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
# setuptools-family sdists with PEP 639 licence metadata (license = "SPDX" string /
# license-files), which RHEL's setuptools 68 rejects: patched in %prep (SP3 fix round 1
# for the first seven; psycopg 3.3, gunicorn added for the 9.17 bump).
PEP639_PATCH = {
    "alembic", "backports.zstd", "greenlet", "Mako", "MarkupSafe", "SecretStorage", "wsproto",
    "psycopg", "psycopg-c", "gunicorn",
}
# Extra tags emitted after Requires (package -> lines).
EXTRA_TAGS = {
    # libpass is a passlib fork that installs the `passlib` module.
    "libpass": [
        "Provides:       %{python3_pkgprefix}-passlib = %{version}",
        "Conflicts:      %{python3_pkgprefix}-passlib < 1.9",
    ],
}
# Extra runtime Requires (RPM names) not derivable from PyPI metadata (package -> lines),
# and whether to mirror them as BuildRequires.
EXTRA_REQ = {
    "psycopg": [("libpq", True), ("%{python3_pkgprefix}-psycopg-c", False)],  # psycopg-c BRs psycopg → no mirror
    "Flask-Principal": [("%{python3_pkgprefix}-flask", True), ("%{python3_pkgprefix}-blinker", True)],
    "qrcode": [("%{python3_pkgprefix}-pillow", True)],
}
# Build-only extras for the %check import (package -> BuildRequires lines).
CHECK_BR = {"psycopg-c": ["%{python3_pkgprefix}-psycopg"]}
# %check import string overrides.
CHECK_IMPORT = {"psycopg-c": "import psycopg; import psycopg_c"}


def norm(name: str) -> str:
    return re.sub(r"[._]", "-", name.lower())


# Packages that exist in the stack (for Requires name resolution): the rendered set plus,
# when rendering a subset (e.g. a version bump), everything else already in the tree —
# listed in an optional known.json next to stack.json (same record format).
_KNOWN_FILE = HERE / "known.json"
KNOWN = STACK + (json.loads(_KNOWN_FILE.read_text()) if _KNOWN_FILE.exists() else [])
BUILT = {}
for _r in KNOWN:
    BUILT.setdefault(norm(_r["pypi"]), _r)


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
        "%{expand: %%global py3ver %(echo `%{__ospython} -P -c \"import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')\" `)}\n"
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
    reqs_preview = [rpm_dep(q) for q in r["requires"]]
    # A native build dep that is also a runtime dep is listed once, in the
    # runtime block below (review finding, Task 2: python3-pynacl / cffi).
    br = [b for b in dict.fromkeys(br) if b not in reqs_preview]
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
        if not dep:
            continue
        # One line per dependency: when metadata lists a name twice (e.g. "flask" and
        # "Flask>=2.1.0"), keep the entry that carries a version floor.
        name_only = dep.split(" >= ")[0]
        existing = next((d for d in reqs if d.split(" >= ")[0] == name_only), None)
        if existing is None:
            reqs.append(dep)
        elif " >= " in dep and " >= " not in existing:
            reqs[reqs.index(existing)] = dep
    no_mirror = set()
    for dep, mirror in EXTRA_REQ.get(pypi, []):
        if dep not in reqs:
            reqs.append(dep)
        if not mirror:
            no_mirror.add(dep)
    for b in CHECK_BR.get(pypi, []):
        lines.append(f"# for the %check import\nBuildRequires:  {b}\n")
    if reqs:
        # Runtime deps are also build deps so %check can import the module —
        # except those the preamble already declares (python3.12-setuptools ==
        # python%{python3_buildversion}-setuptools on EL; review finding, Task 3).
        base_names = {"python3.12-devel", "python3.12-pip", "python3.12-setuptools", "python3.12-wheel"}
        lines.append("# runtime dependencies, also needed by the %check import test\n")
        for d in reqs:
            if d not in base_names and d not in no_mirror:
                lines.append(f"BuildRequires:  {d}\n")
        lines.append("\n")
        for d in reqs:
            if d in no_mirror:
                lines.append("# not mirrored as BuildRequires: the dependency BuildRequires this package for its %check\n")
            lines.append(f"Requires:       {d}\n")
    for t in EXTRA_TAGS.get(pypi, []):
        lines.append(t + "\n")
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
    if pypi in PEP639_PATCH:
        lines.append(
            "# setuptools 68 (RHEL 9) cannot parse PEP 639 licence metadata: use the table form, drop license-files\n"
            "sed -i -e 's/^license = \"\\(.*\\)\"$/license = {text = \"\\1\"}/' -e '/^license-files = \\[$/,/^\\]$/d' -e '/^license-files = \\[.*\\]$/d' pyproject.toml\n"
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
    imports = CHECK_IMPORT.get(pypi) or "; ".join("import " + m for m in mods)
    # Import from the installed buildroot (src-layout packages are not importable
    # from the source directory); -P keeps the cwd off sys.path.
    lines.append(
        f"\n%check\nPYTHONPATH=%{{buildroot}}%{{{sitedir}}} %{{__ospython}} -P -c \"{imports}\"\n"
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

## Appendix B — `stack.json` (the 13 packages to render)

Write verbatim to `$SCRATCH/sp4-bump/stack.json`.

```json
[
 {
  "pypi": "Flask-Security-Too",
  "version": "5.8.2",
  "project": "pgadmin",
  "summary": "Quickly add security features to your Flask application",
  "url": "https://github.com/pallets-eco/flask-security",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-Security-Too/flask_security_too-5.8.2.tar.gz",
  "sdist_filename": "flask_security_too-5.8.2.tar.gz",
  "sdist_top": "flask_security_too-5.8.2",
  "family": "flit",
  "native": false,
  "requires": [
   "Flask >=3.1.1",
   "Flask-Login >=0.6.3",
   "Flask-Principal >=0.4.0",
   "Flask-WTF >=1.1.2",
   "email-validator >=2.3.0",
   "markupsafe >=2.1.0",
   "libpass >=1.9.3",
   "wtforms >=3.0.0"
  ],
  "build_requires": "\"flit_core >=3.8,<5\"",
  "scripts": [],
  "modules": [
   "flask_security"
  ]
 },
 {
  "pypi": "Flask-SocketIO",
  "version": "5.6.1",
  "project": "pgadmin",
  "summary": "Socket.IO integration for Flask applications",
  "url": "https://github.com/miguelgrinberg/flask-socketio",
  "license": "MIT License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-SocketIO/flask_socketio-5.6.1.tar.gz",
  "sdist_filename": "flask_socketio-5.6.1.tar.gz",
  "sdist_top": "flask_socketio-5.6.1",
  "family": "setuptools",
  "native": false,
  "requires": [
   "blinker",
   "click",
   "flask",
   "Flask >=2.1.0",
   "jinja2",
   "python-socketio >=5.12.0",
   "werkzeug"
  ],
  "build_requires": "\"setuptools>=61.2\",",
  "scripts": [],
  "modules": [
   "flask_socketio"
  ]
 },
 {
  "pypi": "Flask-WTF",
  "version": "1.3.0",
  "project": "pgadmin",
  "summary": "Form rendering, validation, and CSRF protection for Flask with WTForms",
  "url": "https://pypi.org/project/Flask-WTF/",
  "license": "BSD License",
  "sdist_url": "https://files.pythonhosted.org/packages/source/F/Flask-WTF/flask_wtf-1.3.0.tar.gz",
  "sdist_filename": "flask_wtf-1.3.0.tar.gz",
  "sdist_top": "flask_wtf-1.3.0",
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
  "pypi": "gssapi",
  "version": "1.11.1",
  "project": "pgadmin",
  "summary": "Python GSSAPI Wrapper",
  "url": "https://github.com/pythongssapi/python-gssapi",
  "license": "ISC",
  "sdist_url": "https://files.pythonhosted.org/packages/source/g/gssapi/gssapi-1.11.1.tar.gz",
  "sdist_filename": "gssapi-1.11.1.tar.gz",
  "sdist_top": "gssapi-1.11.1",
  "family": "setuptools",
  "native": true,
  "requires": [
   "decorator"
  ],
  "build_requires": "\"Cython == 3.2.4\", \"setuptools >= 40.6.0\", # Start of PEP 517 support for setuptools",
  "scripts": [],
  "modules": [
   "gssapi"
  ]
 },
 {
  "pypi": "psycopg",
  "version": "3.3.4",
  "project": "pgadmin",
  "summary": "PostgreSQL database adapter for Python",
  "url": "https://psycopg.org/",
  "license": "LGPL-3.0-only",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/psycopg/psycopg-3.3.4.tar.gz",
  "sdist_filename": "psycopg-3.3.4.tar.gz",
  "sdist_top": "psycopg-3.3.4",
  "family": "setuptools",
  "native": false,
  "requires": [
   "typing-extensions >=4.6"
  ],
  "build_requires": "\"setuptools>=80.3.1\", \"wheel>=0.37\"",
  "scripts": [],
  "modules": [
   "psycopg"
  ]
 },
 {
  "pypi": "psycopg-c",
  "version": "3.3.4",
  "project": "pgadmin",
  "summary": "PostgreSQL database adapter for Python -- C optimisation distribution",
  "url": "https://psycopg.org/",
  "license": "LGPL-3.0-only",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/psycopg-c/psycopg_c-3.3.4.tar.gz",
  "sdist_filename": "psycopg_c-3.3.4.tar.gz",
  "sdist_top": "psycopg_c-3.3.4",
  "family": "setuptools",
  "native": true,
  "requires": [],
  "build_requires": "# Note: pinning this version strictly because of the setuptools warning: # # `[tool.setuptools.ext-modules",
  "scripts": [],
  "modules": []
 },
 {
  "pypi": "pytz",
  "version": "2026.3.post1",
  "project": "pgadmin",
  "summary": "World timezone definitions, modern and historical",
  "url": "http://pythonhosted.org/pytz",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/p/pytz/pytz-2026.3.post1.tar.gz",
  "sdist_filename": "pytz-2026.3.post1.tar.gz",
  "sdist_top": "pytz-2026.3.post1",
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
  "pypi": "typer",
  "version": "0.26.8",
  "project": "pgadmin",
  "summary": "Typer, build great CLIs. Easy to code. Based on Python type hints",
  "url": "https://github.com/fastapi/typer",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/t/typer/typer-0.26.8.tar.gz",
  "sdist_filename": "typer-0.26.8.tar.gz",
  "sdist_top": "typer-0.26.8",
  "family": "pdm",
  "native": false,
  "requires": [
   "shellingham >=1.3.0",
   "rich >=13.8.0",
   "annotated-doc >=0.0.2"
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
  "pypi": "annotated-doc",
  "version": "0.0.5",
  "project": "pgadmin",
  "summary": "Document parameters, class attributes, return types, and variables inline, with Annotated",
  "url": "https://github.com/fastapi/annotated-doc",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/a/annotated-doc/annotated_doc-0.0.5.tar.gz",
  "sdist_filename": "annotated_doc-0.0.5.tar.gz",
  "sdist_top": "annotated_doc-0.0.5",
  "family": "pdm",
  "native": false,
  "requires": [],
  "build_requires": "\"pdm-backend\",",
  "scripts": [],
  "modules": [
   "annotated_doc"
  ]
 },
 {
  "pypi": "certifi",
  "version": "2026.6.17",
  "project": "pgadmin",
  "summary": "Python package for providing Mozilla's CA Bundle",
  "url": "https://github.com/certifi/python-certifi",
  "license": "MPL-2.0",
  "sdist_url": "https://files.pythonhosted.org/packages/source/c/certifi/certifi-2026.6.17.tar.gz",
  "sdist_filename": "certifi-2026.6.17.tar.gz",
  "sdist_top": "certifi-2026.6.17",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "\"setuptools >= 42.0.0\"",
  "scripts": [],
  "modules": [
   "certifi"
  ]
 },
 {
  "pypi": "libpass",
  "version": "1.9.3",
  "project": "pgadmin",
  "summary": "Fork of passlib, a comprehensive password hashing framework supporting over 30 schemes",
  "url": "https://github.com/notypecheck/passlib",
  "license": "BSD",
  "sdist_url": "https://files.pythonhosted.org/packages/source/l/libpass/libpass-1.9.3.tar.gz",
  "sdist_filename": "libpass-1.9.3.tar.gz",
  "sdist_top": "libpass-1.9.3",
  "family": "hatchling",
  "native": false,
  "requires": [],
  "build_requires": "\"hatchling\"",
  "scripts": [],
  "modules": [
   "passlib"
  ]
 },
 {
  "pypi": "gunicorn",
  "version": "26.2.0",
  "project": "pgadmin",
  "summary": "WSGI HTTP Server for UNIX",
  "url": "https://gunicorn.org",
  "license": "MIT",
  "sdist_url": "https://files.pythonhosted.org/packages/source/g/gunicorn/gunicorn-26.2.0.tar.gz",
  "sdist_filename": "gunicorn-26.2.0.tar.gz",
  "sdist_top": "gunicorn-26.2.0",
  "family": "setuptools",
  "native": false,
  "requires": [],
  "build_requires": "\"setuptools>=61.2\"",
  "scripts": [
   "gunicorn",
   "gunicornc"
  ],
  "modules": [
   "gunicorn"
  ]
 },
 {
  "pypi": "Cython",
  "version": "3.2.4",
  "project": "pgadmin",
  "summary": "The Cython compiler for writing C extensions in the Python language",
  "url": "https://cython.org/",
  "license": "Apache-2.0",
  "sdist_url": "https://files.pythonhosted.org/packages/source/C/Cython/cython-3.2.4.tar.gz",
  "sdist_filename": "cython-3.2.4.tar.gz",
  "sdist_top": "cython-3.2.4",
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
 }
]
```

## Appendix C — `known.json` (names of the other 66 stack packages)

Write verbatim to `$SCRATCH/sp4-bump/known.json`. Only the `pypi` field is read; it lets the renderer emit `Requires:` on packages outside the rendered set (`flask`, `wtforms`, `rich`, `python-socketio`, `decorator`, …).

```json
[{"pypi": "alembic"}, {"pypi": "Authlib"}, {"pypi": "babel"}, {"pypi": "backports.zstd"}, {"pypi": "bcrypt"}, {"pypi": "bidict"}, {"pypi": "blinker"}, {"pypi": "brotli"}, {"pypi": "decorator"}, {"pypi": "email-validator"}, {"pypi": "Flask"}, {"pypi": "flask-babel"}, {"pypi": "Flask-Compress"}, {"pypi": "Flask-Login"}, {"pypi": "Flask-Mail"}, {"pypi": "Flask-Migrate"}, {"pypi": "Flask-Paranoid"}, {"pypi": "Flask-Principal"}, {"pypi": "Flask-SQLAlchemy"}, {"pypi": "greenlet"}, {"pypi": "h11"}, {"pypi": "itsdangerous"}, {"pypi": "jaraco.classes"}, {"pypi": "jaraco.context"}, {"pypi": "jaraco.functools"}, {"pypi": "jeepney"}, {"pypi": "Jinja2"}, {"pypi": "jsonformatter"}, {"pypi": "keyring"}, {"pypi": "ldap3"}, {"pypi": "libgravatar"}, {"pypi": "Mako"}, {"pypi": "markdown-it-py"}, {"pypi": "MarkupSafe"}, {"pypi": "mdurl"}, {"pypi": "more-itertools"}, {"pypi": "paramiko"}, {"pypi": "pillow"}, {"pypi": "pyasn1"}, {"pypi": "Pygments"}, {"pypi": "PyNaCl"}, {"pypi": "PyOTP"}, {"pypi": "python-engineio"}, {"pypi": "python-socketio"}, {"pypi": "qrcode"}, {"pypi": "rich"}, {"pypi": "SecretStorage"}, {"pypi": "shellingham"}, {"pypi": "simple-websocket"}, {"pypi": "SQLAlchemy"}, {"pypi": "sqlparse"}, {"pypi": "sshtunnel"}, {"pypi": "typing-extensions"}, {"pypi": "ua-parser"}, {"pypi": "user-agents"}, {"pypi": "Werkzeug"}, {"pypi": "wsproto"}, {"pypi": "WTForms"}, {"pypi": "poetry-core"}, {"pypi": "pdm-backend"}, {"pypi": "dnspython"}, {"pypi": "hatchling"}, {"pypi": "pathspec"}, {"pypi": "trove-classifiers"}, {"pypi": "flit-core"}, {"pypi": "packaging"}]
```

## Appendix D — `0002-make-cloud-packages-optional.patch` (openSUSE, verbatim)

```diff
Index: pgadmin4-8.2/web/pgadmin/misc/__init__.py
===================================================================
--- pgadmin4-8.2.orig/web/pgadmin/misc/__init__.py
+++ pgadmin4-8.2/web/pgadmin/misc/__init__.py
@@ -108,8 +108,17 @@ class MiscModule(PgAdminModule):
         from .bgprocess import blueprint as module
         self.submodules.append(module)
 
-        from .cloud import blueprint as module
-        self.submodules.append(module)
+        try:
+            from .cloud import blueprint as module
+            self.submodules.append(module)
+        except ModuleNotFoundError:
+            print('\n\n')
+            print('###########################################################\n')
+            print('    IMPORTANT WARNING:\n')
+            print('Cloud packages not found, if you want to enable cloud support,')
+            print('please install the pgadmin4-cloud package')
+            print('\n###########################################################\n')
+
 
         from .dependencies import blueprint as module
         self.submodules.append(module)
```

## Appendix E — `0003-use-os-makedirs.patch` (openSUSE, verbatim)

```diff
From: Antonio Larrosa <alarrosa@suse.com>
Subject: Use os.makedirs instead of os.mkdir

So parent directories are created if needed

---
 web/pgadmin/setup/data_directory.py |    2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)

Index: pgadmin4-7.4/web/pgadmin/setup/data_directory.py
===================================================================
--- pgadmin4-7.4.orig/web/pgadmin/setup/data_directory.py
+++ pgadmin4-7.4/web/pgadmin/setup/data_directory.py
@@ -18,7 +18,7 @@ FAILED_CREATE_DIR = \
 
 def _create_directory_if_not_exists(_path):
     if _path and not os.path.exists(_path):
-        os.mkdir(_path)
+        os.makedirs(_path)
         return True
 
     return False
```
