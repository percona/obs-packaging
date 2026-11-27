# Restored PG 18 Upgrade Image + Git-Tracked Upgrade Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `percona-distribution-postgresql-upgrade:18-17-16-15-14` image as a second package, and have `source_script` build `upgrade-scripts.tar.gz` for all three upgrade images from one git-tracked scripts tree.

**Architecture:** `source_script` gains a `--source <dir>` mode that packs a directory of the package with fixed timestamps. `percona-obs` copies `obs/` subdirectories (followed through symlinks, verbatim) into the service work directory and follows `obs/` symlinks in its git change checks. The three upgrade packages link `obs/upgrade-scripts` to `root/ppg/staging/common/upgrade/_shared/upgrade-scripts`.

**Tech Stack:** Python 3 (stdlib only in the service), pytest, black, pyright, OBS Dockerfile builds.

**Spec:** `docs/superpowers/specs/2026-11-27-upgrade-image-18-and-upgrade-scripts-design.md`

## Global Constraints

- Work in the worktree `/home/rdias/Work/percona-obs-packaging/.claude/worktrees/upgrade-image-18` (branch `upgrade-image-18`, off `percona/main`). Tooling: `/home/rdias/Work/percona-obs-packaging/venv/bin/{python,pytest,black,pyright}` (call them `$VENV/...` below; `VENV=/home/rdias/Work/percona-obs-packaging/venv`).
- After every code change: `$VENV/bin/black percona_obs/ tools/obs-services/source_script tests/` then `$VENV/bin/pyright` → `0 errors`.
- Commits: `git commit -s`, no `Co-Authored-By` line, no Claude attribution. Never push or open a PR without asking the user.
- Two PRs: Tasks 1–4 are PR 1 (tool). Tasks 5–7 are PR 2 (packaging) and start only after PR 1 is merged to `main` and the obs-tools image has been rebuilt (the user confirms). PR 2 branches from the updated `percona/main`.
- `source_script` uses only the Python standard library.
- Files copied from an `obs/` subdirectory get **no** `%!{}` macro and **no** `${}` env substitution.
- The existing `--archive` mode of `source_script` keeps its exact behaviour and output bytes (all existing tests pass unchanged).
- Tarball for the upgrade images: file name `upgrade-scripts.tar.gz`, single top directory `upgrade-scripts/`, every mtime `0`, uid/gid 0, no owner names, modes 0755 (dirs and executables) / 0644 (other files), gzip header mtime 0 and no filename.
- Image name of the restored package stays `percona-distribution-postgresql-upgrade`; numbered tags/labels use `%!{UNIT_RELEASE}`.

**User decisions (already made):**
- Approach B: teach `source_script` to pack a package directory (not `obs_scm` on this repo).
- The restored image publishes to the same Docker Hub repository with the old tags.
- `UNIT_RELEASE` (already on `main`) numbers the restored image, not `PPG_RELEASE`.
- The custom image (`percona-distribution-postgresql-upgrade-custom`) shares the scripts tree too and picks up the PG-2868 `start.sh` fix.
- The user checks obs-sync themselves; PR 2 does not merge before that.

**Deviation from the spec (verified while planning):** the spec suggested suffixing the restored package's QA lane names to avoid colliding with the project lanes. Package lanes render as `<project> / <package> → …` (see `percona_obs/cmd_qa.py` around line 300), so the original names (`ubi8-14-to-15`, …) are kept unchanged.

## Review Focus

1. **The `--source` directory is itself a symlink** (how the packages lay it out, and how a developer runs the service by hand in `obs/`): the tarball must hold the target's regular files, never a symlink entry. Test: `test_source_symlinked_dir_packs_its_contents` (Task 1).
2. **Executable bits survive the copy and the pack:** `start.sh` and the other `.sh` files must come out 0755, the templates 0644; the Dockerfiles `chmod +x` anyway, but `relocate-extensions.sh` is copied to `/usr/local/bin`. Test: `test_source_mode_keeps_exec_bits` (Task 1).
3. **Scripts containing `${VAR}` and `%!{VAR}`-looking text** (start.sh uses `${NEW_VERSION}`) must reach the service byte-for-byte. Test: `test_obs_subdir_reaches_services_verbatim` (Task 2).
4. **A dangling `obs/` symlink** (a moved `_shared` tree) must fail the sync with a message naming the link, not a Python traceback. Test: `test_dangling_obs_subdir_link_fails_clearly` (Task 2).
5. **An `obs/` subdirectory must never be uploaded to OBS.** It's already removed from the work directory before upload, but pin it. Test: `test_obs_subdir_not_left_in_workdir` (Task 2).

---

### Task 1: `source_script --source` mode

**Goal:** `source_script` packs a directory of the work directory (optionally after running a script on a copy of it) into a byte-reproducible tarball.

**Files:**
- Modify: `tools/obs-services/source_script` (`parse_args`, `main`, new `resolve_source`, docstring)
- Modify: `tools/obs-services/source_script.service` (new `source` parameter; `archive` no longer `<required/>`; `output` description)
- Modify: `tools/obs-services/README.md` (table row)
- Test: `tests/test_source_script.py`

**Acceptance Criteria:**
- [ ] `--source upgrade-scripts --output upgrade-scripts.tar.gz` with no `--script` writes a tarball whose members are `upgrade-scripts/` plus the tree, every mtime 0, uid/gid 0, empty uname/gname.
- [ ] Same contents give identical bytes across two runs in different temp dirs.
- [ ] A symlinked `--source` directory packs the target's files; no member is a symlink.
- [ ] With `--script`, the script runs with cwd = a copy of the source dir and `NAME=<source dir name>`, `VERSION=""`, `COMMIT=""`, `SOURCE_DATE_EPOCH=0`; its single `OUT_DIR` directory is packed with mtime 0.
- [ ] Exactly one of `--archive`/`--source` is required; `--source` without `--output` fails; `--archive` without `--script` fails; `--source` must be a plain name of an existing directory. Each failure exits 1 with a one-line `source_script: …` cause.
- [ ] All pre-existing tests in `tests/test_source_script.py` pass unchanged.

**Verify:** `$VENV/bin/pytest tests/test_source_script.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** (new fixture `srcdir`: a work dir holding `upgrade-scripts/bin/upgrade/start.sh` (0755, content `echo ${NEW_VERSION}\n`), `upgrade-scripts/conf/upgrade/passwd.template` (0644); chdir into the work dir)

```python
def _run_source(tmp_path, *extra):
    out = tmp_path / "out"
    assert svc.main(["--source", "upgrade-scripts", "--output",
                     "upgrade-scripts.tar.gz", "--outdir", str(out), *extra]) == 0
    return out / "upgrade-scripts.tar.gz"

def test_source_mode_packs_the_directory(srcdir, tmp_path):
    m = _members(_run_source(tmp_path))
    assert set(m) == {"upgrade-scripts", "upgrade-scripts/bin", "upgrade-scripts/bin/upgrade",
                      "upgrade-scripts/bin/upgrade/start.sh", "upgrade-scripts/conf",
                      "upgrade-scripts/conf/upgrade", "upgrade-scripts/conf/upgrade/passwd.template"}
    assert all(x.mtime == 0 and x.uid == 0 and x.gid == 0 and x.uname == "" for x in m.values())

def test_source_mode_keeps_exec_bits(srcdir, tmp_path):
    m = _members(_run_source(tmp_path))
    assert m["upgrade-scripts/bin/upgrade/start.sh"].mode == 0o755
    assert m["upgrade-scripts/conf/upgrade/passwd.template"].mode == 0o644

def test_source_mode_same_contents_same_bytes(srcdir, tmp_path): ...
    # copy srcdir's tree to a second work dir, touch every file with a new mtime,
    # run both; assert the two tarballs' bytes are equal

def test_source_symlinked_dir_packs_its_contents(srcdir, tmp_path):
    # move upgrade-scripts to ../shared/upgrade-scripts, symlink it back
    m = _members(_run_source(tmp_path))
    assert "upgrade-scripts/bin/upgrade/start.sh" in m
    assert not any(x.issym() for x in m.values())

def test_source_mode_runs_the_script_on_a_copy(srcdir, tmp_path):
    # script writes "$NAME|$VERSION|$COMMIT|$SOURCE_DATE_EPOCH" into
    # $OUT_DIR/pkg/env.txt and `cp -R . "$OUT_DIR/pkg/"`; also `rm bin/upgrade/start.sh`
    # assert tarball member pkg/env.txt == "upgrade-scripts|||0\n",
    # and srcdir/upgrade-scripts/bin/upgrade/start.sh still exists

@pytest.mark.parametrize("args, cause", [
    (["--archive", "x*", "--source", "upgrade-scripts", "--script", "dist.sh"], "exactly one of"),
    (["--source", "upgrade-scripts"], "--output"),
    (["--archive", "percona-foo*.tar.gz"], "--script"),
    (["--source", "../upgrade-scripts", "--output", "a.tar.gz"], "plain name"),
    (["--source", "missing", "--output", "a.tar.gz"], "not a directory"),
])
def test_source_mode_argument_errors(srcdir, tmp_path, capsys, args, cause): ...
    # SystemExit code 1, cause substring in stderr
```

- [ ] **Step 2: Run to verify they fail**

Run: `$VENV/bin/pytest tests/test_source_script.py -k source_mode -v`
Expected: FAIL (unrecognized argument `--source`)

- [ ] **Step 3: Implement in `tools/obs-services/source_script`**

  - `parse_args`: `--archive` and `--script` lose `required=True`; add `--source`. In `main`, validate the combinations listed in the criteria, using `die()`.
  - `resolve_source(name: str) -> Path`: the same plain-name rule as `resolve_script`, plus `Path(name).is_dir()` (follows symlinks).
  - Source mode in `main`:
    - `shutil.copytree(source, work / "src" / source.name, symlinks=False)` (fresh `src` dir).
    - With a script: `info = {"name": source.name, "version": "", "commit": "", "mtime": "0"}`, then `script_env` and `run_script` as today on the copy, then `single_output_dir`.
    - Without a script: `tree = work / "src" / source.name`.
    - Then `pack(tree, outdir / output, 0)`.
  - `pack` stays unchanged (it already normalises modes and owners).
  - Update the module docstring, `source_script.service` and the README row to describe the `source` parameter.

- [ ] **Step 4: Run all source_script tests**

Run: `$VENV/bin/pytest tests/test_source_script.py -v` → all pass

- [ ] **Step 5: Format, type-check, commit**

```bash
$VENV/bin/black tools/obs-services/source_script tests/test_source_script.py && $VENV/bin/pyright
git add tools/obs-services/source_script tools/obs-services/source_script.service tools/obs-services/README.md tests/test_source_script.py
git commit -s -m "source_script: pack a directory of the package (--source)"
```

---

### Task 2: `percona-obs` hands `obs/` subdirectories to local services

**Goal:** `_run_local_services` copies `obs/` subdirectories (through symlinks, verbatim) into the service work directory, and the manual-service cache key covers their contents.

**Files:**
- Modify: `percona_obs/services.py` (work-dir setup in `_run_local_services` ~line 939; `_manual_cache_key` ~line 355)
- Test: `tests/test_run_local_services.py`, `tests/test_source_script.py` (cache-key test next to `test_manual_cache_key_follows_the_script_content`)

**Acceptance Criteria:**
- [ ] A service run by `_run_local_services` sees `obs/<sub>/…` (a real dir or a symlink to one) as a real directory in its cwd, byte-identical, `${FOO}`/`%!{BAR}` text not substituted even when the macros/env vars are defined.
- [ ] Dangling `obs/` symlink → `SystemExit` whose message names the link path.
- [ ] After the run, no directory is left in the returned work dir (so nothing is uploaded).
- [ ] `_manual_cache_key` changes when a file inside an `obs/` subdirectory changes, and is unchanged for packages without subdirectories (existing keys keep their value).

**Verify:** `$VENV/bin/pytest tests/test_run_local_services.py tests/test_source_script.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests** in `tests/test_run_local_services.py`. Use a new fake manual service `fake_cat` installed via `_install`. It runs `cat upgrade-scripts/a.sh > "$outdir/seen.txt"`. Use a `_service` that has only that manual service, so there's no obs_scm.

```python
def test_obs_subdir_reaches_services_verbatim(fake_services):
    # obs/upgrade-scripts/a.sh contains 'echo ${FOO} %!{BAR}\n'
    workdir = _run_local_services(obs_dir, cache=False,
                                  env_vars={"FOO": "x"}, macros={"BAR": "y"})
    assert (workdir / "seen.txt").read_text() == "echo ${FOO} %!{BAR}\n"

def test_obs_symlinked_subdir_reaches_services(fake_services): ...
    # obs/upgrade-scripts -> ../../shared/upgrade-scripts; same assertion

def test_obs_subdir_not_left_in_workdir(fake_services):
    workdir = _run_local_services(obs_dir, cache=False)
    assert not [p for p in workdir.iterdir() if p.is_dir()]

def test_dangling_obs_subdir_link_fails_clearly(fake_services):
    (obs_dir / "upgrade-scripts").symlink_to("../nowhere")
    with pytest.raises(SystemExit) as exc:
        _run_local_services(obs_dir, cache=False)
    assert "upgrade-scripts" in str(exc.value)
```

In `tests/test_source_script.py`:

```python
def test_manual_cache_key_follows_obs_subdir_content(tmp_path):
    # obs/_service + obs/upgrade-scripts/a.sh; key1 = _manual_cache_key(COMMIT, [_manual()], obs)
    # edit a.sh -> key2 != key1; obs with no subdir: key unchanged by the patch
    # (compare against a key computed before creating the subdir)
```

- [ ] **Step 2: Run to verify they fail**

Run: `$VENV/bin/pytest tests/test_run_local_services.py -k obs_subdir -v` → FAIL

- [ ] **Step 3: Implement in `percona_obs/services.py`**

  - Add `_copy_obs_subdirs(obs_dir: Path, workdir: Path) -> None`. For each `src in sorted(obs_dir.iterdir())` with `src.is_dir()`, do `shutil.copytree(src, workdir / src.name, symlinks=False)`.
    - A symlink that is `is_symlink()` but neither a file nor a dir is dangling. Raise `SystemExit(f"error: {src}: link target {os.readlink(src)!r} does not exist")`.
    - Call it in `_run_local_services` right after the existing file-copy loop.
  - `_manual_cache_key`: after the files loop, for each subdirectory (sorted, following symlinks), hash every regular file in sorted `os.walk(..., followlinks=True)` order. Feed the digest `relative path` bytes, then `sha256(content)`. Packages with no subdirectory hash exactly what they do today.

- [ ] **Step 4: Run tests** → all pass (`$VENV/bin/pytest tests/test_run_local_services.py tests/test_source_script.py -v`)

- [ ] **Step 5: Format, type-check, commit**

```bash
$VENV/bin/black percona_obs/ tests/ && $VENV/bin/pyright
git add percona_obs/services.py tests/test_run_local_services.py tests/test_source_script.py
git commit -s -m "services: hand obs/ subdirectories to local services"
```

---

### Task 3: Git change checks follow `obs/` symlinks

**Goal:** An edit under a `_shared/` tree that a package links from its `obs/` counts as a change of that package and of every release unit that ships it.

**Files:**
- Modify: `percona_obs/git_utils.py` (`_package_pathspecs` ~line 54)
- Modify: `percona_obs/cmd_sync.py` (`_scope_local_paths` ~line 3028, the "Package dirs that are symlinks into _shared/" loop)
- Test: `tests/test_shared_source.py`, `tests/test_sync_prerelease.py`

**Acceptance Criteria:**
- [ ] `_package_pathspecs(pkg)` = `[pkg]` + (package link target if `pkg` is a symlink) + the lexical target of each symlink directly in the package's `obs/`. Targets are computed from the package's real location (the link target when `pkg` is a symlink), with `os.readlink` + `normpath`.
- [ ] Existing `_package_pathspecs` tests pass unchanged (plain dir → `[pkg]`; package symlink → `[link, target]`).
- [ ] `_scope_local_paths(root/ppg/staging/common/upgrade/extras, …)` includes `root/ppg/staging/common/upgrade/_shared/upgrade-scripts` when `extras/containers/img/obs/upgrade-scripts` links there. `_changed_files_between` then reports an edit to `_shared/upgrade-scripts/bin/x.sh`.
- [ ] `_scope_local_paths` still adds package-directory link targets (existing `test_shared_symlink_target_edit_is_detected` passes).

**Verify:** `$VENV/bin/pytest tests/test_shared_source.py tests/test_sync_prerelease.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_shared_source.py
def test_git_pathspecs_obs_symlink_adds_lexical_target(tmp_path):
    shared = tmp_path / "root/ppg/staging/common/upgrade/_shared/upgrade-scripts"
    shared.mkdir(parents=True)
    obs = tmp_path / "root/ppg/staging/common/upgrade/containers/img/obs"
    obs.mkdir(parents=True)
    (obs / "upgrade-scripts").symlink_to("../../../_shared/upgrade-scripts")
    assert _package_pathspecs(obs.parent) == [obs.parent, shared]

# tests/test_sync_prerelease.py  (modelled on test_shared_symlink_target_edit_is_detected)
def test_nested_unit_sees_parent_shared_obs_link_edit(tmp_path, monkeypatch):
    # git repo; root/ppg/staging/common/upgrade/_shared/upgrade-scripts/bin/x.sh;
    # root/ppg/staging/common/upgrade/extras/{project.yaml}, extras/containers/{project.yaml},
    # extras/containers/img/obs/upgrade-scripts -> ../../../../_shared/upgrade-scripts
    # commit a; edit x.sh; commit b
    paths = cmd_sync._scope_local_paths(src_extras, [], {}, "home:Admin")
    assert cmd_sync._changed_files_between(a, b, paths) == [
        "root/ppg/staging/common/upgrade/_shared/upgrade-scripts/bin/x.sh"]
```

- [ ] **Step 2: Run to verify they fail** → FAIL (`_package_pathspecs` returns `[pkg]`; changed files `[]`)

- [ ] **Step 3: Implement**
  - `git_utils._package_pathspecs`: keep the current list. Then let `real = paths[-1]`, and for each `link in sorted((real / "obs").iterdir())` with `link.is_symlink()`, append `Path(os.path.normpath(link.parent / os.readlink(link)))` if it isn't already present. Do nothing when `real / "obs"` isn't a dir. Update the docstring.
  - `cmd_sync._scope_local_paths`: replace the direct-children symlink loop with one over `common.find_packages(d, "")` for every `d` in `project_dirs`. For each yielded package path `p`, `_add` every entry of `_package_pathspecs(p)[1:]`. Keep the comment, extended to mention `obs/` links. `find_packages` already follows package links and skips `_shared/` and release dirs.

- [ ] **Step 4: Run tests** → all pass (`$VENV/bin/pytest tests/test_shared_source.py tests/test_sync_prerelease.py -v`), then the full suite: `$VENV/bin/pytest -q` → no failures

- [ ] **Step 5: Format, type-check, commit**

```bash
$VENV/bin/black percona_obs/ tests/ && $VENV/bin/pyright
git add percona_obs/git_utils.py percona_obs/cmd_sync.py tests/test_shared_source.py tests/test_sync_prerelease.py
git commit -s -m "git checks: follow obs/ symlinks into _shared trees"
```

---

### Task 4: Documentation for the tool change

**Goal:** The docs describe `source_script --source`, `obs/` subdirectories, and the `obs/` link change detection.

**Files:**
- Modify: `docs/PERCONA_OBS_TOOL.md` (source_script section: `--source` mode with the upgrade-scripts `_service` as the example; `obs/` subdirectories are copied verbatim to manual services and never uploaded)
- Modify: `.github/copilot-instructions.md` (where it lists what `_run_local_services` copies from `obs/`; `_shared` paragraph: packages may link `obs/<dir>` into a `_shared/` tree, and change detection follows it)
- Modify: `root/README.md` (the `_shared/` section: `_shared/` trees may also be referenced by `obs/` symlinks)

**Acceptance Criteria:**
- [ ] `grep -n "\-\-source" docs/PERCONA_OBS_TOOL.md tools/obs-services/README.md` shows the new mode in both.
- [ ] `grep -n "obs/" root/README.md` shows the `obs/` link convention in the `_shared` section.

**Verify:** `grep -c "source_script" docs/PERCONA_OBS_TOOL.md` → greater than before (record before/after)

**Steps:**
- [ ] **Step 1:** Edit the three files as listed (prose only; no code).
- [ ] **Step 2: Commit**

```bash
git add docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md root/README.md
git commit -s -m "docs: source_script --source and obs/ links into _shared"
```

**PR 1 boundary:** stop here. Report to the user. The user decides on push and PR, and then on merge. PR 2 waits for: PR 1 merged, the obs-tools image rebuilt from `main`, and the local service reinstalled (`tools/obs-services/README.md` § Installing locally).

---

### Task 5: Shared scripts tree; 19 and custom images build the tarball

**Goal:** `root/ppg/staging/common/upgrade/_shared/upgrade-scripts/` holds the scripts. `percona-distribution-postgresql-upgrade` and `percona-distribution-postgresql-upgrade-custom` build `upgrade-scripts.tar.gz` from it with `source_script`, and the committed tarballs are gone.

**Files:**
- Create: `root/ppg/staging/common/upgrade/_shared/upgrade-scripts/` (the 8 files of the current 19-image tarball: `bin/relocate-extensions.sh`, `bin/common/{common_lib,nss_wrapper,nss_wrapper_env,uid_postgres,uid_postgres_no_exec}.sh`, `bin/upgrade/start.sh`, `conf/upgrade/{group,passwd}.template`; `.sh` mode 0755, templates 0644)
- Create: `root/ppg/staging/common/upgrade/containers/percona-distribution-postgresql-upgrade/obs/_service`
- Create: symlink `root/ppg/staging/common/upgrade/containers/percona-distribution-postgresql-upgrade/obs/upgrade-scripts` → `../../../_shared/upgrade-scripts`
- Create: `root/ppg/staging/common/upgrade/extras/containers/percona-distribution-postgresql-upgrade-custom/obs/_service`
- Create: symlink `…/extras/containers/percona-distribution-postgresql-upgrade-custom/obs/upgrade-scripts` → `../../../../_shared/upgrade-scripts`
- Delete: both `obs/upgrade-scripts.tar.gz`
- Modify: both Dockerfiles, `tar -xzf` line only

**Acceptance Criteria:**
- [ ] The shared tree is byte-identical to the current 19 tarball's contents, with the modes listed above.
- [ ] Both `_service` files are exactly the XML below.
- [ ] Both Dockerfiles extract with `tar -xzf /tmp/upgrade-scripts.tar.gz -C /tmp/upgrade-scripts --strip-components=1`; no other line changes.
- [ ] `_run_local_services` on each `obs/` dir (with `_OBS_SERVICE_DIR=tools/obs-services`) produces `upgrade-scripts.tar.gz`. `tar tzf` lists `upgrade-scripts/bin/upgrade/start.sh`, and after `--strip-components=1` the file set equals the old 19 tarball's.
- [ ] `percona-obs … project verify ppg:staging:common:upgrade --offline` → `all checks passed`.

**Verify:**

```bash
VENV=/home/rdias/Work/percona-obs-packaging/venv
for d in root/ppg/staging/common/upgrade/containers/percona-distribution-postgresql-upgrade/obs \
         root/ppg/staging/common/upgrade/extras/containers/percona-distribution-postgresql-upgrade-custom/obs; do
  $VENV/bin/python -c "import sys,subprocess; from pathlib import Path; from percona_obs import services; \
services._OBS_SERVICE_DIR=Path('tools/obs-services').resolve(); \
w=services._run_local_services(Path(sys.argv[1]), cache=False); \
print(sorted(p.name for p in w.iterdir())); \
print(subprocess.run(['tar','tzvf',str(w/'upgrade-scripts.tar.gz')],capture_output=True,text=True).stdout)" "$d"
done
$VENV/bin/python -m percona_obs -R X -e REMOTE_OBS_ORG_INTERCONNECT: -e PERCONA_OBS_PACKAGING_REPO:https://x \
  -e PERCONA_OBS_PACKAGING_BRANCH:main project verify ppg:staging:common:upgrade --offline
```

Expected: each listing includes `Dockerfile`, `LICENSE`, `upgrade-scripts.tar.gz` (no `upgrade-scripts` dir). The tar listing shows 8 files under `upgrade-scripts/` owned `0/0`, date `1970-01-01`, `.sh` as `-rwxr-xr-x`. Verify ends `✔  project verify: all checks passed`.

**Steps:**

- [ ] **Step 1: Extract the tree**

```bash
D=root/ppg/staging/common/upgrade
mkdir -p $D/_shared/upgrade-scripts
tar xzf $D/containers/percona-distribution-postgresql-upgrade/obs/upgrade-scripts.tar.gz -C $D/_shared/upgrade-scripts --no-same-owner
```

Check that the modes are 0755 for `*.sh` and 0644 for `*.template`; fix them with `chmod` if needed.

- [ ] **Step 2: Both `_service` files**

```xml
<services>
  <!-- obs/upgrade-scripts links to the scripts tree shared by every upgrade
       image (root/ppg/staging/common/upgrade/_shared/upgrade-scripts).
       percona-obs sync packs it into upgrade-scripts.tar.gz. -->
  <service name="source_script" mode="manual">
    <param name="source">upgrade-scripts</param>
    <param name="output">upgrade-scripts.tar.gz</param>
  </service>
</services>
```

- [ ] **Step 3: Symlinks, tarball removal, Dockerfile line** (both packages, paths as in Files)

```bash
ln -s ../../../_shared/upgrade-scripts $D/containers/percona-distribution-postgresql-upgrade/obs/upgrade-scripts
ln -s ../../../../_shared/upgrade-scripts $D/extras/containers/percona-distribution-postgresql-upgrade-custom/obs/upgrade-scripts
git rm $D/containers/percona-distribution-postgresql-upgrade/obs/upgrade-scripts.tar.gz \
       $D/extras/containers/percona-distribution-postgresql-upgrade-custom/obs/upgrade-scripts.tar.gz
```

In each Dockerfile, change `tar -xzf /tmp/upgrade-scripts.tar.gz -C /tmp/upgrade-scripts && \` to `tar -xzf /tmp/upgrade-scripts.tar.gz -C /tmp/upgrade-scripts --strip-components=1 && \`.

- [ ] **Step 4: Run Verify** (above) → expected output.

- [ ] **Step 5: Commit**

```bash
git add $D/_shared $D/containers/percona-distribution-postgresql-upgrade/obs $D/extras/containers/percona-distribution-postgresql-upgrade-custom/obs
git commit -s -m "upgrade images: build upgrade-scripts.tar.gz from the shared scripts tree"
```

---

### Task 6: Restored package `percona-distribution-postgresql-upgrade-18`

**Goal:** A new package builds `percona-distribution-postgresql-upgrade` with the 18-target content and the `18-17-16-15-14` tag set, and carries the 12 old QA lanes.

**Files:**
- Create: `root/ppg/staging/common/upgrade/containers/percona-distribution-postgresql-upgrade-18/package.yaml`
- Create: `…/percona-distribution-postgresql-upgrade-18/obs/Dockerfile`
- Create: `…/percona-distribution-postgresql-upgrade-18/obs/LICENSE` (copy of the 19 package's)
- Create: `…/percona-distribution-postgresql-upgrade-18/obs/_service` (identical to Task 5's)
- Create: symlink `…/percona-distribution-postgresql-upgrade-18/obs/upgrade-scripts` → `../../../_shared/upgrade-scripts`

**Acceptance Criteria:**
- [ ] `diff` of the new Dockerfile against the 19 package's Dockerfile contains only these PG-19-specific differences:
  - **Header:**

    ```
    #!BuildVersion: 18.%!{PG_18_MINOR_VERSION}-17.%!{PG_17_MINOR_VERSION}-16.%!{PG_16_MINOR_VERSION}-15.%!{PG_15_MINOR_VERSION}-14.%!{PG_14_MINOR_VERSION}-%!{UNIT_RELEASE}
    #!BuildTag: percona-distribution-postgresql-upgrade:18-17-16-15-14-%!{UNIT_RELEASE}
    #!BuildTag: percona-distribution-postgresql-upgrade:18.%!{PG_18_MINOR_VERSION}-17.%!{PG_17_MINOR_VERSION}-16.%!{PG_16_MINOR_VERSION}-15.%!{PG_15_MINOR_VERSION}-14.%!{PG_14_MINOR_VERSION}-%!{UNIT_RELEASE}
    #!BuildTag: percona-distribution-postgresql-upgrade:18-17-16-15-14
    #!BuildTag: percona-distribution-postgresql-upgrade:18.%!{PG_18_MINOR_VERSION}-17.%!{PG_17_MINOR_VERSION}-16.%!{PG_16_MINOR_VERSION}-15.%!{PG_15_MINOR_VERSION}-14.%!{PG_14_MINOR_VERSION}
    ```
  - **Labels and ENV:**
    - The description reads `…upgrades from PostgreSQL 14, 15, 16, or 17 to 18 using pg_upgrade.`
    - `LABEL version="18.%!{PG_18_MINOR_VERSION}-%!{UNIT_RELEASE}"`
    - `ENV PPG_VERSION 18.%!{PG_18_MINOR_VERSION}-%!{UNIT_RELEASE}`
    - `ENV PPG_MAJOR_VERSION 18`
  - **Target install block:**
    - The five `percona-postgis%!{POSTGIS_RPM_MAJOR}_…` lines become `percona-postgis35_…`.
    - The three lines `percona-address-standardizer${PPG_MAJOR_VERSION}`, `…-llvmjit` and `percona-postgis-tiger-geocoder${PPG_MAJOR_VERSION}` are removed. This matches `git show d4602b6e^:<19 Dockerfile path>`.
  - **Older-majors loop and extras:**
    - The loop is `{{FOR pg_version IN 17,16,15,14}}`.
    - The trailing `RUN` installs only `percona-pg_tde17`. Its comment reverts to the pre-d4602b6e wording: "pg_tde is only packaged standalone from PG17 onward, so it's installed separately here rather than inside the loop above."
- [ ] No `%!{PG_MAJOR_VERSION}`, `%!{PG_VERSION}`, `%!{POSTGIS_RPM_MAJOR}` or `PPG_RELEASE` token remains in the new Dockerfile.
- [ ] `package.yaml` has `title`, `description` (PG-18-target upgrade image kept so the `18-17-16-15-14` tags keep receiving CVE fixes), and a `qa:` block. That block is the 12 entries of `git show d4602b6e^:root/ppg/staging/common/upgrade/containers/project.yaml` (from `- name: ubi8-14-to-15` through `ubi10-17-to-18`), unchanged except `UPGRADE_REPOSITORY.image: percona-distribution-postgresql-upgrade-18`.
- [ ] `qa show` lists `ppg:staging:common:upgrade:containers / percona-distribution-postgresql-upgrade-18` lanes with `UPGRADE_DOCKER_TAG: 18-17-16-15-14` (12 entries), and the project lanes are unchanged.
- [ ] Running the services on its `obs/` produces `upgrade-scripts.tar.gz` (same check as Task 5); `project verify … --offline` passes.

**Verify:**

```bash
P=root/ppg/staging/common/upgrade/containers
diff $P/percona-distribution-postgresql-upgrade/obs/Dockerfile $P/percona-distribution-postgresql-upgrade-18/obs/Dockerfile
grep -nE 'PG_MAJOR_VERSION\}|PG_VERSION\}|POSTGIS_RPM_MAJOR|PPG_RELEASE' $P/percona-distribution-postgresql-upgrade-18/obs/Dockerfile   # → no output
$VENV/bin/python -m percona_obs -R X -e REMOTE_OBS_ORG_INTERCONNECT: -e PERCONA_OBS_PACKAGING_REPO:https://x \
  -e PERCONA_OBS_PACKAGING_BRANCH:main qa show ppg:staging:common:upgrade:containers | grep -c 'percona-distribution-postgresql-upgrade-18  →'
```

Expected: the diff shows only the hunks listed, the grep prints nothing, and the count is 12 (one header line per package lane entry; check the actual `qa show` layout and adjust the grep if it prints one line per combo).

**Steps:**

- [ ] **Step 1:** Copy the 19 package's `obs/Dockerfile` and `LICENSE`. Apply the differences listed above. For the target block and the trailing `RUN`, cross-check with `git show d4602b6e^:root/ppg/staging/common/upgrade/containers/percona-distribution-postgresql-upgrade/obs/Dockerfile`.
- [ ] **Step 2:** Write `_service` (Task 5 XML) and the `upgrade-scripts` symlink.
- [ ] **Step 3:** Write `package.yaml` with the 12 restored lanes (`image:` changed as stated).
- [ ] **Step 4:** Run Verify plus the Task 5 service check on this `obs/` dir, and `project verify ppg:staging:common:upgrade --offline`.
- [ ] **Step 5: Commit**

```bash
git add root/ppg/staging/common/upgrade/containers/percona-distribution-postgresql-upgrade-18
git commit -s -m "upgrade: restore the 18-17-16-15-14 upgrade image as its own package"
```

---

### Task 7: Labs rehearsal and obs-sync confirmation (user)

**Goal:** Before PR 2 merges, confirm on a non-production OBS that both packages publish their tags side by side under one image name, and that obs-sync publishes both tag sets.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:** none (verification only)

**Acceptance Criteria:**
- [ ] On the labs/PR OBS (never `-P isv` without `--dry-run`), the PR project for PR 2 builds all three images. The registry for `…/common/upgrade/containers/ubi9` lists both `19-18-17-16-15` and `18-17-16-15-14` tags of `percona-distribution-postgresql-upgrade`.
- [ ] The PR's QA run passes or fails for both the project lanes (19 image) and the `percona-distribution-postgresql-upgrade-18` lanes, with the 18 lanes pulling tag `18-17-16-15-14`.
- [ ] The user confirms obs-sync publishes both tag sets to Docker Hub (or that its required change is merged).

**Verify:** `skopeo list-tags docker://<registry>/<pr-rootprj>/ppg/staging/common/upgrade/containers/ubi9/percona-distribution-postgresql-upgrade` → includes both tag sets. User confirmation is recorded in the PR.

**Steps:**
- [ ] **Step 1:** Ask the user before pushing PR 2's branch (`percona` remote, never a direct `sync push`).
- [ ] **Step 2:** After the PR's OBS sync and builds, run Verify and capture the output.
- [ ] **Step 3:** Ask the user for the obs-sync confirmation. If either check fails, stop and bring the `_multibuild` fallback (spec § Dependencies) back to the user.
