# PKG_REVISION package revision floor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every OBS-built deb and rpm a per-package revision floor (`PKG_REVISION = production floor + 1`) rendered into the spec `Release:` and the dsc revision, so OBS's own `vrev` counter starts above the production counter and every OBS package sorts above `repo.percona.com`.

**Architecture:** A new computed macro `PKG_REVISION` is injected per package by `inject_computed_macros` from a hardcoded seed table keyed `(OBS project, package, upstream V)`, where `V` is read offline from the package's `obs/_service` by the extractor that `project versions` already uses (moved to a new leaf module and fixed for `versionrewrite-replacement`). `sync` keeps the rendered spec `Release:` alive through `set_version` (which zeroes it) with a snapshot/restore step in `services.py`. Packaging files are normalised so every spec says `Release: %!{PKG_REVISION}%{?dist}` and every dsc says `[epoch:]<V>-%!{PKG_REVISION}`. OBS does the climbing: `vrev = max(previous + 1, spec Release)`, reset per upstream version.

**Tech Stack:** Python 3 (`percona_obs/`), pytest (`tests/`), black, pyright, obs-service-set_version 0.6.6 (local, `/usr/lib/obs/service/set_version`), OBS source server semantics (`bs_srcserver` `getcommitinfo` + `BSFileDB::fdb_add_i2`).

**Spec:** `docs/superpowers/specs/2026-11-02-deb-revision-counter-design.md`

## Global Constraints

- Worktree `.claude/worktrees/deb-revision-counter` (branch `deb-revision-counter` off `percona/main`). Python tooling: `/home/rdias/Work/percona-obs-packaging/venv/bin/{python,pytest,black,pyright}` (the worktree has no venv). Run every test command from the worktree root with `PYTHONPATH=.`.
- After every code task: `venv/bin/black percona_obs/ tests/` then `venv/bin/pyright` → `0 errors`, then `venv/bin/python -m pytest tests -q` → all pass.
- Commits: `git commit -s`. No `Co-Authored-By`, no "Generated with" lines, ever. Never `git push`, never `gh pr create`: the user does that.
- `PKG_REVISION` must be a pure function of the git tree: `obs/_service` text + macros chain + the table in code. No network, no OBS reads, on either side of `_macros_changed_since`.
- Nothing is injected for a package without `obs/_service` (aggregates, images, simpleimage tarballs, `_link`), or whose rendered `V` still contains `%!{` or `${`.
- An explicitly declared `PKG_REVISION` in any `macros.yaml` wins.
- prjconf `Release:` lines, `Debtransform-Release: 1`, the `+<CI_CNT>.<B_CNT>.<codename>` and `.<CI_CNT>.<B_CNT>` suffixes are NOT touched. The devel tier (`root/ppg/devel`) is NOT touched.
- Spec `Release:` restore in `services.py` restores the first `Release:` line only, unconditionally, for every `*.spec` in the work dir.
- The seed table values are exactly the ones in the spec's review artifact (max over deb and rpm production vaults, dump of 2026-11-02/03); keys are the `(project, package, V)` triples listed in Task 1, computed with the tool's own extractor.

**User decisions (already made):**
- Build on OBS `vrev`; `PKG_REVISION` is a constant floor + 1, no release-cut counting, no `release.yaml` dependency, no prjconf change (2026-11-03).
- `PPG_RELEASE` stays as is; OBS counters stay; `ppg:common:deps` packages get the same rule (floor + 1, no climb).
- Rejected: `CI_CNT` as the Debian revision (letter-led revision trick, tool-predicted `vrev`), commit-API `vrev=` seeding, prjconf `CICntStart:`, a forked `set_version`.
- `V` comes from `obs/_service` (not spec/dsc `Version:`, not `package.yaml`).
- Seeds are hardcoded in Python; no new `percona-obs` command.
- Macro name `PKG_REVISION` (the one open question in the spec; use it unless the user says otherwise).

## Review Focus

1. A `_service` whose rendered `V` still holds an unresolved `%!{X}` or `${ENV}` token (devel-style `@PARENT_TAG@+@TAG_OFFSET@` formats, env-driven revisions): expected no `PKG_REVISION` injected and no crash. Test in Task 2.
2. A spec with no `Release:` line, or with `Release:` only after the first occurrence (subpackage), run through `set_version`: expected the restore step rewrites exactly the first line and never crashes on a missing one. Tests in Task 3.
3. A symlinked `_shared/` package evaluated by `_macros_changed_since` at a historical commit: expected the historical side reads `obs/_service` through the symlink target and compares equal when nothing changed. Test in Task 2.
4. `project verify --offline` / a plain render of every spec and dsc under `root/ppg/staging` and `root/ppg/common` after the packaging edits: expected zero undefined-macro errors, i.e. every package that references `PKG_REVISION` has a `_service` that yields a `V`. Verification step in Tasks 4 and 5.
5. The placeholder-dsc packages after their `set_version` is restricted to the spec: expected the uploaded dsc carries the epoch and `-<revision>`, not `<ver>-0`. Rendering check in Task 5 and the labs check in Task 7.

---

### Task 1: `percona_obs/pkg_version.py` — extractor move, rewrite fix, seed table

**Goal:** A leaf module holding the `_service` version extractor (now applying `versionrewrite-replacement` like tar_scm and taking an optional tag resolver), the seed table and `compute_pkg_revision`; `cmd_project` keeps a thin wrapper so existing callers and tests are unchanged.

**Files:**
- Create: `percona_obs/pkg_version.py`
- Modify: `percona_obs/cmd_project.py:97-200` (remove `_ARCHIVE_SUFFIX_RE`, `_SHA_RE`, `_version_from_set_version`, `_extract_version_from_service` bodies; keep a wrapper)
- Test: `tests/test_pkg_version.py` (new); `tests/test_version_from_set_version.py` (unchanged, must keep passing)

**Acceptance Criteria:**
- [ ] `extract_version_from_service_text` mirrors tar_scm: with `versionformat=@PARENT_TAG@`, `re.sub(pattern, replacement or r"\1", revision)` when the pattern matches (pgadmin4 `REL-9_17` → `9.17`; pg_similarity `pg_similarity_1_0` → `1.0`; `v1.6.8` with pattern `v(.*)` and no replacement → `1.6.8`).
- [ ] SHA revision + `@PARENT_TAG@` with no matching pattern: resolver given → its result (pattern applied to the tag); resolver `None` → `None`.
- [ ] `compute_pkg_revision("ppg:staging:17", "percona-pgaudit", "17.1") == "5"`, unknown key → `"1"`.
- [ ] `cmd_project._extract_version_from_service(path)` still exists and resolves tags via `_git_tag_for_sha` at call time.
- [ ] `tests/test_version_from_set_version.py` passes unchanged.

**Verify:** `PYTHONPATH=. venv/bin/python -m pytest tests/test_pkg_version.py tests/test_version_from_set_version.py -q` → all pass; `venv/bin/pyright` → 0 errors.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pkg_version.py`:

```python
"""Upstream version from obs/_service and the PKG_REVISION seed lookup."""

from pathlib import Path

from percona_obs.pkg_version import (
    PKG_REVISION_FLOORS,
    compute_pkg_revision,
    extract_version_from_service,
    extract_version_from_service_text,
)


def _scm(**params) -> str:
    body = "".join(f'<param name="{k}">{v}</param>' for k, v in params.items())
    return f'<services><service name="obs_scm">{body}</service></services>'


def test_version_param_wins():
    text = _scm(url="u", revision="REL4_2_0", version="4.2.0", versionformat="@PARENT_TAG@")
    assert extract_version_from_service_text(text) == "4.2.0"


def test_rewrite_pattern_with_replacement_like_tar_scm():
    text = _scm(
        url="u",
        revision="REL-9_17",
        versionformat="@PARENT_TAG@",
        **{"versionrewrite-pattern": r"REL-(\d+)_(\d+)", "versionrewrite-replacement": r"\1.\2"},
    )
    assert extract_version_from_service_text(text) == "9.17"


def test_rewrite_pattern_without_replacement_defaults_to_group_one():
    text = _scm(
        url="u", revision="v1.6.8", versionformat="@PARENT_TAG@",
        **{"versionrewrite-pattern": r"v(.*)"},
    )
    assert extract_version_from_service_text(text) == "1.6.8"


def test_pg_similarity_tag_rewrite():
    text = _scm(
        url="u", revision="pg_similarity_1_0", versionformat="@PARENT_TAG@",
        **{"versionrewrite-pattern": r"pg_similarity_(\d+)_(\d+)", "versionrewrite-replacement": r"\1.\2"},
    )
    assert extract_version_from_service_text(text) == "1.0"


SHA = "0123456789abcdef0123456789abcdef01234567"


def test_sha_revision_offline_is_none():
    text = _scm(url="https://example.org/x.git", revision=SHA, versionformat="@PARENT_TAG@")
    assert extract_version_from_service_text(text) is None


def test_sha_revision_with_resolver_uses_tag_and_pattern():
    text = _scm(
        url="https://example.org/x.git", revision=SHA, versionformat="@PARENT_TAG@",
        **{"versionrewrite-pattern": r"v(.*)"},
    )
    calls = []

    def resolver(url, sha):
        calls.append((url, sha))
        return "v2.0"

    assert extract_version_from_service_text(text, resolve_tag=resolver) == "2.0"
    assert calls == [("https://example.org/x.git", SHA)]


def test_packaging_obs_scm_is_skipped():
    text = (
        '<services><service name="obs_scm"><param name="filename">debian</param>'
        '<param name="revision">main</param></service>'
        '<service name="obs_scm"><param name="revision">1.2.3</param>'
        '<param name="filename">pkg</param></service></services>'
    )
    assert extract_version_from_service_text(text) == "1.2.3"


def test_env_token_revision_is_none():
    text = _scm(url="u", revision="${PG_REF}", versionformat="@PARENT_TAG@")
    assert extract_version_from_service_text(text) is None


def test_unparsable_file_is_none(tmp_path: Path):
    f = tmp_path / "_service"
    f.write_text("<services><service></services>")
    assert extract_version_from_service(f) is None
    assert extract_version_from_service(tmp_path / "missing") is None


def test_compute_pkg_revision_seed_hit_and_miss():
    assert compute_pkg_revision("ppg:staging:17", "percona-pgaudit", "17.1") == "5"
    assert compute_pkg_revision("ppg:staging:17", "percona-pgaudit_set_user", "4.2.0") == "7"
    assert compute_pkg_revision("ppg:staging:17", "percona-pgaudit", "17.2") == "1"
    assert compute_pkg_revision("ppg:staging:19", "percona-pgaudit", "17.1") == "1"
    assert compute_pkg_revision("ppg:common:deps", "ydiff", "1.4.2") == "4"


def test_seed_table_values_are_positive_ints():
    for key, value in PKG_REVISION_FLOORS.items():
        assert len(key) == 3 and all(isinstance(k, str) and k for k in key)
        assert isinstance(value, int) and value >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. /home/rdias/Work/percona-obs-packaging/venv/bin/python -m pytest tests/test_pkg_version.py -q`
Expected: FAIL / error `ModuleNotFoundError: No module named 'percona_obs.pkg_version'`

- [ ] **Step 3: Create the module**

Create `percona_obs/pkg_version.py` (a leaf: imports only the standard library):

```python
"""Upstream version of a package as OBS computes it, and the PKG_REVISION floor.

``extract_version_from_service_text`` mirrors obs_scm/tar_scm and
set_version: an explicit obs_scm ``version`` wins; a literal
``versionformat`` is returned as is; ``@PARENT_TAG@`` applies
``versionrewrite-pattern``/``-replacement`` to ``revision`` exactly like
tar_scm (``re.sub(pattern, replacement or r"\\1", tag)``); a bare commit SHA
needs a tag lookup, which the caller may provide through *resolve_tag* (the
tool's computed macros never do: they must stay offline).  With no obs_scm
version the set_version service names it (``version`` param, or the
``basename`` + download_url file name).

``PKG_REVISION_FLOORS`` carries the repo.percona.com counters forward across
the OBS migration.  Keyed by OBS project, package directory name and
upstream version (no epoch); the value is max(deb revision, rpm release)
over every production vault, codename and EL major, from the index dump of
2026-11-02/03.  An entry is dead once the package ships another upstream
version; delete the table when every entry is dead.  See
docs/superpowers/specs/2026-11-02-deb-revision-counter-design.md.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

_ARCHIVE_SUFFIX_RE = re.compile(r"\.(tar\.(gz|bz2|xz|zst)|tgz|tbz2|txz|zip)$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

TagResolver = Callable[[str, str], "str | None"]


def _params(svc: ET.Element) -> dict[str, str]:
    return {p.get("name", ""): (p.text or "").strip() for p in svc.findall("param")}


def version_from_set_version(root_el: ET.Element) -> "str | None":
    """Version that a set_version service gives the package, or None.

    An explicit ``version`` param wins; otherwise the version is read from a
    downloaded file named ``<basename>-<version>`` plus an archive suffix,
    here the ``filename`` (or URL basename) of a download_url service.
    Macros (``%!{VAR}``) are returned unresolved for the caller to substitute.
    """
    for svc in root_el.findall("service"):
        if svc.get("name") != "set_version":
            continue
        params = _params(svc)
        if params.get("version"):
            return params["version"]
        basename = params.get("basename", "")
        if not basename:
            return None
        for dl in root_el.findall("service"):
            if dl.get("name") != "download_url":
                continue
            dl_params = _params(dl)
            filename = (
                dl_params.get("filename") or dl_params.get("url", "").rsplit("/", 1)[-1]
            )
            if filename.startswith(basename + "-"):
                version = _ARCHIVE_SUFFIX_RE.sub("", filename[len(basename) + 1 :])
                if version:
                    return version
        return None
    return None


def _rewrite(pattern: str, replacement: str, value: str) -> "str | None":
    """tar_scm's versionrewrite: re.sub with ``\\1`` as the default replacement."""
    try:
        if not re.search(pattern, value):
            return None
        return re.sub(pattern, replacement or r"\1", value)
    except re.error:
        return None


def extract_version_from_service_text(
    text: str, resolve_tag: "TagResolver | None" = None
) -> "str | None":
    """Return the upstream version an obs/_service file yields, or None."""
    try:
        root_el = ET.fromstring(text)
    except ET.ParseError:
        return None

    for svc in root_el.findall("service"):
        if svc.get("name") != "obs_scm":
            continue
        params = _params(svc)
        if params.get("filename") in ("debian", "rpm"):
            continue  # packaging service, not upstream

        version = params.get("version", "")
        versionformat = params.get("versionformat", "")
        revision = params.get("revision", "")

        if version and version != "_none_":
            return version
        if versionformat and versionformat != "@PARENT_TAG@":
            return versionformat
        if versionformat == "@PARENT_TAG@":
            pattern = params.get("versionrewrite-pattern", "")
            replacement = params.get("versionrewrite-replacement", "")
            if _ENV_VAR_RE.search(revision):
                return None
            if pattern and revision:
                rewritten = _rewrite(pattern, replacement, revision)
                if rewritten is not None:
                    return rewritten
            if _SHA_RE.match(revision):
                url = params.get("url", "")
                if resolve_tag is None or not url or _ENV_VAR_RE.search(url):
                    return None
                tag = resolve_tag(url, revision)
                if tag is None:
                    return None
                if pattern:
                    rewritten = _rewrite(pattern, replacement, tag)
                    if rewritten is not None:
                        return rewritten
                return tag
            return revision or None
        if revision and not _ENV_VAR_RE.search(revision):
            return revision
        return None

    return version_from_set_version(root_el)


def extract_version_from_service(
    service_file: Path, resolve_tag: "TagResolver | None" = None
) -> "str | None":
    """``extract_version_from_service_text`` over a file; unreadable → None."""
    try:
        text = service_file.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return extract_version_from_service_text(text, resolve_tag=resolve_tag)


# (OBS project, package directory name, upstream version) -> production counter.
PKG_REVISION_FLOORS: dict[tuple[str, str, str], int] = {
    # pgaudit: 14/15 rpm counter ahead of deb (7 vs 4)
    ("ppg:staging:14", "percona-pgaudit", "1.6.3"): 7,
    ("ppg:staging:15", "percona-pgaudit", "1.7.1"): 7,
    ("ppg:staging:16", "percona-pgaudit", "16.1"): 4,
    ("ppg:staging:17", "percona-pgaudit", "17.1"): 4,
    ("ppg:staging:18", "percona-pgaudit", "18.0"): 4,
    # set_user
    ("ppg:staging:14", "percona-pgaudit_set_user", "4.2.0"): 4,
    ("ppg:staging:15", "percona-pgaudit_set_user", "4.2.0"): 4,
    ("ppg:staging:16", "percona-pgaudit_set_user", "4.2.0"): 4,
    ("ppg:staging:17", "percona-pgaudit_set_user", "4.2.0"): 6,
    ("ppg:staging:18", "percona-pgaudit_set_user", "4.2.0"): 4,
    # pg_repack: 14-17 at 5, 18 at 4 -> global max
    ("ppg:staging:14", "percona-pg_repack", "1.5.3"): 5,
    ("ppg:staging:15", "percona-pg_repack", "1.5.3"): 5,
    ("ppg:staging:16", "percona-pg_repack", "1.5.3"): 5,
    ("ppg:staging:17", "percona-pg_repack", "1.5.3"): 5,
    ("ppg:staging:18", "percona-pg_repack", "1.5.3"): 5,
    # pg-telemetry: not in the 18 vault
    ("ppg:staging:14", "percona-pg-telemetry", "1.2.0"): 3,
    ("ppg:staging:15", "percona-pg-telemetry", "1.2.0"): 3,
    ("ppg:staging:16", "percona-pg-telemetry", "1.2.0"): 3,
    ("ppg:staging:17", "percona-pg-telemetry", "1.2.0"): 3,
    # pg_gather: rpm name has no major, shared across majors
    ("ppg:staging:14", "percona-pg_gather", "33"): 3,
    ("ppg:staging:15", "percona-pg_gather", "33"): 3,
    ("ppg:staging:16", "percona-pg_gather", "33"): 3,
    ("ppg:staging:17", "percona-pg_gather", "33"): 3,
    ("ppg:staging:18", "percona-pg_gather", "33"): 3,
    ("ppg:staging:19", "percona-pg_gather", "33"): 3,
    # postgis: 14-17 at 2, 18 at 3 -> global max
    ("ppg:staging:14", "percona-postgis", "3.5.7"): 3,
    ("ppg:staging:15", "percona-postgis", "3.5.7"): 3,
    ("ppg:staging:16", "percona-postgis", "3.5.7"): 3,
    ("ppg:staging:17", "percona-postgis", "3.5.7"): 3,
    ("ppg:staging:18", "percona-postgis", "3.5.7"): 3,
    # pgpool-II: deb 2 ahead of rpm 1
    ("ppg:staging:14", "percona-pgpool-II", "4.7.2"): 2,
    ("ppg:staging:15", "percona-pgpool-II", "4.7.2"): 2,
    ("ppg:staging:16", "percona-pgpool-II", "4.7.2"): 2,
    ("ppg:staging:17", "percona-pgpool-II", "4.7.2"): 2,
    ("ppg:staging:18", "percona-pgpool-II", "4.7.2"): 2,
    ("ppg:staging:19", "percona-pgpool-II", "4.7.2"): 2,
    # shared tools and deps
    ("ppg:staging:common:tools", "percona-pgbadger", "13.2"): 3,
    ("ppg:staging:common:tools", "percona-patroni", "4.1.5"): 1,
    ("ppg:common:deps", "ydiff", "1.4.2"): 3,
    # production counter 1: deb "V-1+..." sorts below "V-1.codename"
    ("ppg:staging:14", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:15", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:16", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:17", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:18", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:19", "percona-postgresql-common", "293"): 1,
    ("ppg:staging:14", "percona-pg_cron", "1.6.8"): 1,
    ("ppg:staging:15", "percona-pg_cron", "1.6.8"): 1,
    ("ppg:staging:16", "percona-pg_cron", "1.6.8"): 1,
    ("ppg:staging:17", "percona-pg_cron", "1.6.8"): 1,
    ("ppg:staging:18", "percona-pg_cron", "1.6.8"): 1,
    ("ppg:staging:17", "percona-pg_tde", "2.2.2"): 1,
    ("ppg:staging:18", "percona-pg_tde", "2.2.2"): 1,
    ("ppg:staging:18", "percona-pg_oidc_validator", "1.1.0"): 1,
}


def compute_pkg_revision(project: str, package: str, version: str) -> str:
    """``floor(project, package, version) + 1`` as a string; 1 when unseeded."""
    return str(PKG_REVISION_FLOORS.get((project, package, version), 0) + 1)
```

- [ ] **Step 4: Replace the bodies in `cmd_project.py` with a wrapper**

In `percona_obs/cmd_project.py` delete `_ARCHIVE_SUFFIX_RE`, `_SHA_RE`, `_version_from_set_version` and `_extract_version_from_service` (lines 97–200 region; keep `_ENV_VAR_RE` import if other code uses it, check with grep) and add:

```python
from .pkg_version import extract_version_from_service


def _extract_version_from_service(service_file: Path) -> "str | None":
    """Return the upstream version from an obs/_service file, or None.

    Online variant: a commit SHA revision is resolved to its tag through
    ``_git_tag_for_sha`` (``git ls-remote``).  The computed macros use the
    offline function in ``pkg_version`` directly.
    """
    return extract_version_from_service(service_file, resolve_tag=_git_tag_for_sha)
```

Keep the `_git_tag_for_sha` import on line 92. Run `grep -n "_version_from_set_version\|_ARCHIVE_SUFFIX_RE\|_SHA_RE" percona_obs/*.py tests/*.py` and fix any remaining reference (tests import `_extract_version_from_service` from `cmd_project`; that keeps working).

- [ ] **Step 5: Run tests, black, pyright**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_pkg_version.py tests/test_version_from_set_version.py tests/test_versions_online.py tests/test_qa_expected_versions.py -q`
Expected: all pass.
Run: `venv/bin/black percona_obs/ tests/ && venv/bin/pyright`
Expected: `0 errors`.

- [ ] **Step 6: Commit**

```bash
git add percona_obs/pkg_version.py percona_obs/cmd_project.py tests/test_pkg_version.py
git commit -s -m "pkg_version: move the _service version extractor, apply versionrewrite-replacement, add PKG_REVISION seeds"
```

---

### Task 2: Inject `PKG_REVISION` in `inject_computed_macros`, symmetric in `_macros_changed_since`

**Goal:** Every package with an `obs/_service` gets `PKG_REVISION` in its resolved macros, from the same inputs on the working tree and at a historical commit, including through `_shared/` symlinks.

**Files:**
- Modify: `percona_obs/common.py:361-406` (`inject_computed_macros`)
- Modify: `percona_obs/git_utils.py:280-333` (`_macros_changed_since`: read historical files through `_git_tracked_path`)
- Test: `tests/test_computed_macros.py`, `tests/test_macros_changed_since.py`

**Acceptance Criteria:**
- [ ] `inject_computed_macros` adds `PKG_REVISION` for a package path with `obs/_service` whose rendered `V` is concrete; not for a project path, a package without `_service`, a `V` with `%!{`/`${` left, or when `PKG_REVISION` is already declared.
- [ ] Injection happens even when the chain has no `PG_VERSION` (`ppg:common:deps`); `PPG_RELEASE` behaviour is unchanged.
- [ ] `_macros_changed_since` returns False for an unchanged symlinked package that references `PKG_REVISION`, True after the package's `_service` version changes.
- [ ] `project` key is the colon-joined path of the package's parent relative to `root/` (`ppg:staging:17`), `package` is the directory name (lexical, i.e. the symlink name).

**Verify:** `PYTHONPATH=. venv/bin/python -m pytest tests/test_computed_macros.py tests/test_macros_changed_since.py -q` → pass; `venv/bin/pyright` → 0 errors.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_computed_macros.py`:

```python
import percona_obs.pkg_version as pkg_version

SERVICE = """<services>
  <service name="obs_scm">
    <param name="url">https://github.com/pgaudit/pgaudit.git</param>
    <param name="revision">%!{PGAUDIT_VERSION}</param>
    <param name="version">%!{PGAUDIT_VERSION}</param>
    <param name="filename">percona-pgaudit</param>
  </service>
</services>
"""


def _pkg_tree(tmp_path: Path, version_line: str = "- PGAUDIT_VERSION: 17.1\n") -> tuple[Path, Path]:
    root = tmp_path / "root"
    proj = root / "ppg" / "staging" / "17"
    pkg = proj / "percona-pgaudit"
    (pkg / "obs").mkdir(parents=True)
    (proj / "macros.yaml").write_text(version_line)
    (pkg / "obs" / "_service").write_text(SERVICE)
    return root, pkg


def _read(p: Path):
    return common._read_worktree_file(p)


def test_pkg_revision_injected_from_seed(tmp_path, monkeypatch):
    root, pkg = _pkg_tree(tmp_path)
    monkeypatch.setitem(
        pkg_version.PKG_REVISION_FLOORS, ("ppg:staging:17", "percona-pgaudit", "17.1"), 4
    )
    out = inject_computed_macros({"PGAUDIT_VERSION": "17.1"}, pkg, _read, repo_root=root)
    assert out["PKG_REVISION"] == "5"


def test_pkg_revision_resets_on_upstream_bump(tmp_path):
    root, pkg = _pkg_tree(tmp_path, "- PGAUDIT_VERSION: 17.2\n")
    out = inject_computed_macros({"PGAUDIT_VERSION": "17.2"}, pkg, _read, repo_root=root)
    assert out["PKG_REVISION"] == "1"


def test_pkg_revision_without_pg_version_in_chain(tmp_path):
    # ppg:common:deps has no PG_VERSION; PKG_REVISION must still appear.
    root = tmp_path / "root"
    pkg = root / "ppg" / "common" / "deps" / "ydiff"
    (pkg / "obs").mkdir(parents=True)
    (pkg / "obs" / "_service").write_text(
        '<services><service name="obs_scm"><param name="version">1.4.2</param>'
        '<param name="filename">ydiff</param></service></services>'
    )
    out = inject_computed_macros({}, pkg, _read, repo_root=root)
    assert out["PKG_REVISION"] == str(
        pkg_version.PKG_REVISION_FLOORS[("ppg:common:deps", "ydiff", "1.4.2")] + 1
    )
    assert "PPG_RELEASE" not in out


def test_pkg_revision_not_injected_without_service(tmp_path):
    root = tmp_path / "root"
    pkg = root / "ppg" / "staging" / "17" / "percona-postgresql-tarball"
    (pkg / "obs").mkdir(parents=True)
    (pkg / "obs" / "_aggregate").write_text("<aggregatelist/>")
    out = inject_computed_macros({"PG_VERSION": "17.11"}, pkg, _read, repo_root=root)
    assert "PKG_REVISION" not in out


def test_pkg_revision_not_injected_for_project_path(tmp_path):
    root, pkg = _pkg_tree(tmp_path)
    out = inject_computed_macros({"PGAUDIT_VERSION": "17.1"}, pkg.parent, _read, repo_root=root)
    assert "PKG_REVISION" not in out


def test_pkg_revision_skipped_when_version_unresolved(tmp_path):
    root, pkg = _pkg_tree(tmp_path)
    # PGAUDIT_VERSION missing from the chain: V renders to "%!{PGAUDIT_VERSION}".
    out = inject_computed_macros({}, pkg, _read, repo_root=root)
    assert "PKG_REVISION" not in out
    (pkg / "obs" / "_service").write_text(SERVICE.replace("%!{PGAUDIT_VERSION}", "${PGAUDIT_REF}"))
    out = inject_computed_macros({}, pkg, _read, repo_root=root)
    assert "PKG_REVISION" not in out


def test_declared_pkg_revision_wins(tmp_path):
    root, pkg = _pkg_tree(tmp_path)
    out = inject_computed_macros(
        {"PGAUDIT_VERSION": "17.1", "PKG_REVISION": "42"}, pkg, _read, repo_root=root
    )
    assert out["PKG_REVISION"] == "42"


def test_pkg_revision_computed_identically_from_git_reader(tmp_path):
    # The git side passes a reader over "git show"; the same text must give the
    # same value.  Simulate with a dict-backed reader.
    root, pkg = _pkg_tree(tmp_path)
    blobs = {pkg / "obs" / "_service": SERVICE}
    out = inject_computed_macros(
        {"PGAUDIT_VERSION": "17.1"}, pkg, lambda p: blobs.get(p), repo_root=root
    )
    assert out["PKG_REVISION"] == inject_computed_macros(
        {"PGAUDIT_VERSION": "17.1"}, pkg, _read, repo_root=root
    )["PKG_REVISION"]
```

Append to `tests/test_macros_changed_since.py` (reuse its `_git`, `_write` helpers and the pattern of its existing `repo` fixture: it monkeypatches `common.REPO_ROOT`, `git_utils._REPO_DIR` and `git_utils._REPO_ROOT` to the temp repo; copy those three `monkeypatch.setattr` lines from the existing fixture):

```python
PKG_SERVICE = """<services>
  <service name="obs_scm">
    <param name="url">https://example.org/pgaudit.git</param>
    <param name="revision">%!{PGAUDIT_VERSION}</param>
    <param name="version">%!{PGAUDIT_VERSION}</param>
    <param name="filename">percona-pgaudit</param>
  </service>
</services>
"""


@pytest.fixture
def symlinked_repo(monkeypatch, tmp_path):
    """A package under staging/17 that is a symlink into _shared/, referencing PKG_REVISION."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "root/ppg/staging/17/macros.yaml", "- PGAUDIT_VERSION: 17.1\n")
    _write(repo, "root/ppg/staging/_shared/percona-pgaudit/obs/_service", PKG_SERVICE)
    _write(
        repo,
        "root/ppg/staging/_shared/percona-pgaudit/rpm/percona-pgaudit.spec",
        "Name: x\nVersion: 1.0.0\nRelease: %!{PKG_REVISION}%{?dist}\n",
    )
    link = repo / "root/ppg/staging/17/percona-pgaudit"
    link.symlink_to("../_shared/percona-pgaudit")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    sha = _git(repo, "rev-parse", "--short", "HEAD")
    monkeypatch.setattr(common, "REPO_ROOT", repo / "root")
    monkeypatch.setattr(git_utils, "_REPO_DIR", repo)
    monkeypatch.setattr(git_utils, "_REPO_ROOT", repo / "root")
    git_utils._git_show_cache.clear()
    return repo, sha, link


def test_pkg_revision_unchanged_through_symlink(symlinked_repo):
    repo, sha, pkg = symlinked_repo
    assert _macros_changed_since(sha, pkg) is False


def test_pkg_revision_changes_when_service_version_changes(symlinked_repo):
    repo, sha, pkg = symlinked_repo
    # An upstream bump in the shared _service resets PKG_REVISION (seeded 17.1 -> 4+1, 17.2 -> 1)
    import percona_obs.pkg_version as pkg_version

    pkg_version.PKG_REVISION_FLOORS[("ppg:staging:17", "percona-pgaudit", "17.1")] = 4
    try:
        _write(repo, "root/ppg/staging/17/macros.yaml", "- PGAUDIT_VERSION: 17.2\n")
        assert _macros_changed_since(sha, pkg) is True
    finally:
        del pkg_version.PKG_REVISION_FLOORS[("ppg:staging:17", "percona-pgaudit", "17.1")]
```

(If the existing fixture names the attributes differently, e.g. only `_REPO_DIR`, mirror exactly what it does; `grep -n "monkeypatch.setattr" tests/test_macros_changed_since.py` shows the lines.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_computed_macros.py tests/test_macros_changed_since.py -q`
Expected: the new tests FAIL (`KeyError: 'PKG_REVISION'` / `assert True is False`).

- [ ] **Step 3: Implement the injection in `common.py`**

Replace `inject_computed_macros` (keep its docstring, extend it) so that the `PG_VERSION`/`PPG_RELEASE` early returns no longer skip the new entry:

```python
def inject_computed_macros(
    macros: dict[str, str],
    project_path: Path,
    read_file: "Callable[[Path], str | None]",
    repo_root: "Path | None" = None,
) -> dict[str, str]:
    """Return *macros* plus the tool-computed entries, without mutating it.

    Three entries: ``PG_PREV_MAJOR_VERSION`` (the major before
    ``PG_MAJOR_VERSION``), ``PPG_RELEASE`` (see ``compute_ppg_release``) and
    ``PKG_REVISION`` (see ``pkg_version.compute_pkg_revision``).  *read_file*
    returns a repo file's contents or None; callers pass a working-tree reader
    or a git-revision reader so the identical value can be computed at any
    commit — see ``git_utils._macros_changed_since``.  *repo_root* defaults to
    the module global and exists so tests can point at a fixture tree.

    ``PPG_RELEASE`` needs ``PG_VERSION`` in the chain.  ``PKG_REVISION`` needs
    *project_path* to be a package (``obs/_service`` readable) whose upstream
    version renders to a concrete string; projects, aggregates, images,
    tarballs and ``_link`` packages get nothing.  An explicitly declared
    ``PPG_RELEASE``/``PKG_REVISION`` always wins.
    """
    from .pkg_version import compute_pkg_revision, extract_version_from_service_text

    root = REPO_ROOT if repo_root is None else repo_root
    major_str = (macros.get("PG_MAJOR_VERSION") or "").strip()
    if major_str.isdigit() and "PG_PREV_MAJOR_VERSION" not in macros:
        macros = {**macros, "PG_PREV_MAJOR_VERSION": str(int(major_str) - 1)}
    try:
        parts = project_path.relative_to(root).parts
    except ValueError:
        return macros
    if not parts:
        return macros

    pg_version = macros.get("PG_VERSION")
    if pg_version and "PPG_RELEASE" not in macros:
        product = parts[0]
        major = pg_version.split(".", 1)[0].strip()
        if major:
            release_file = root / product / "releases" / major / "release.yaml"
            macros = {
                **macros,
                "PPG_RELEASE": compute_ppg_release(
                    product, pg_version, read_file(release_file)
                ),
            }

    if "PKG_REVISION" not in macros and len(parts) >= 2:
        service_text = read_file(project_path / "obs" / "_service")
        if service_text is not None:
            rendered = apply_macro_substitution(service_text, macros, strict=False)
            version = extract_version_from_service_text(rendered)
            if version and "%!{" not in version and "${" not in version:
                macros = {
                    **macros,
                    "PKG_REVISION": compute_pkg_revision(
                        ":".join(parts[:-1]), parts[-1], version
                    ),
                }
    return macros
```

Check `apply_macro_substitution(..., strict=False)` leaves undefined tokens in place (its docstring says so) and does not require `source` unless a date built-in appears; `_service` files carry none.

- [ ] **Step 4: Make the historical reader symlink-aware in `git_utils.py`**

In `_macros_changed_since`, the lambda passed to `inject_computed_macros` reads `p.relative_to(_REPO_DIR)`; a package path through a `_shared/` symlink is a blob to git. Replace it:

```python
        then = inject_computed_macros(
            resolve_macros(sources),
            package_path,
            lambda p: _git_show_at(
                short_sha, _git_tracked_path(p).relative_to(_REPO_DIR).as_posix()
            ),
        )
```

`_git_tracked_path` is defined later in the same module (line ~410); Python resolves it at call time, no reordering needed.

- [ ] **Step 5: Run tests, black, pyright**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_computed_macros.py tests/test_macros_changed_since.py tests/test_macro_resolution.py tests/test_skip_unchanged.py -q`
Expected: pass.
Run: `venv/bin/black percona_obs/ tests/ && venv/bin/pyright`
Expected: `0 errors`.

- [ ] **Step 6: Commit**

```bash
git add percona_obs/common.py percona_obs/git_utils.py tests/test_computed_macros.py tests/test_macros_changed_since.py
git commit -s -m "macros: computed PKG_REVISION per package from the _service version and the seed floors"
```

---

### Task 3: Keep the rendered spec `Release:` through `set_version` in `services.py`

**Goal:** After the local buildtime services run, every `*.spec` in the work dir carries the `Release:` line it had after macro rendering, so OBS records the floor at commit.

**Files:**
- Modify: `percona_obs/services.py:1063-1102` (`_run_local_services`: snapshot after `_copy_local_packaging`, restore before the cleanup block)
- Test: `tests/test_run_local_services.py`

**Acceptance Criteria:**
- [ ] With a fake `set_version` that rewrites `Release:` to `0%{?dist}`, the work dir spec ends with the original `Release:        5%{?dist}` line.
- [ ] A spec with no `Release:` line is left untouched; only the first `Release:` line is restored when several exist.
- [ ] The dsc is not touched by the restore step.

**Verify:** `PYTHONPATH=. venv/bin/python -m pytest tests/test_run_local_services.py -q` → pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run_local_services.py`:

```python
SERVICE_XML_SET_VERSION = """<services>
  <service name="obs_scm">
    <param name="url">https://example.invalid/foo.git</param>
    <param name="scm">git</param>
    <param name="revision">v1.0</param>
    <param name="filename">foo</param>
  </service>
  <service mode="buildtime" name="set_version">
    <param name="basename">foo</param>
  </service>
</services>
"""

# Fake set_version: does to every spec in cwd what the real one does
# (obs-service-set_version 0.6.6 line 490): Version from the archive name,
# Release reset to 0, inline rpm macro kept.
FAKE_SET_VERSION = r"""#!/bin/sh
set -e
outdir=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--outdir" ]; then outdir="$2"; shift; fi
  shift
done
for f in *.spec; do
  [ -f "$f" ] || continue
  sed -e 's/^Version:\([ \t]*\)[^%]*/Version:\11.0/' -e 's/^Release:\([ \t]*\)[^%]*/Release:\10/' "$f" > "$outdir/$f"
done
"""


@pytest.fixture
def set_version_pkg(fake_services):
    bindir, obs_dir, _cache = fake_services
    _install(bindir, "set_version", FAKE_SET_VERSION)
    (obs_dir / "_service").write_text(SERVICE_XML_SET_VERSION)
    rpm = obs_dir.parent / "rpm"
    rpm.mkdir()
    (rpm / "foo.spec").write_text(
        "Name:           foo\nVersion:        1.0.0\nRelease:        5%{?dist}\n"
        "Summary:        x\n%package sub\nRelease:        99\n%description\n"
    )
    (rpm / "norelease.spec").write_text("Name:           bar\nVersion:        1.0.0\n")
    return obs_dir


def test_spec_release_survives_set_version(set_version_pkg):
    workdir = _run_local_services(set_version_pkg, cache=False)
    text = (workdir / "foo.spec").read_text()
    assert "Version:        1.0\n" in text  # set_version did run
    assert "Release:        5%{?dist}\n" in text  # restored
    assert text.count("Release:") == 2 and "Release:        99\n" in text  # only the first
    assert (workdir / "norelease.spec").read_text() == "Name:           bar\nVersion:        1.0\n"
    shutil.rmtree(workdir, ignore_errors=True)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_run_local_services.py::test_spec_release_survives_set_version -q`
Expected: FAIL on `assert "Release:        5%{?dist}\n" in text` (the spec says `Release:        0%{?dist}`).

- [ ] **Step 3: Implement snapshot/restore**

Add near `_copy_file_with_macros` in `percona_obs/services.py`:

```python
_SPEC_RELEASE_RE = re.compile(r"^Release:[ \t]*.*$", re.MULTILINE)


def _spec_release_lines(workdir: Path) -> dict[str, str]:
    """First ``Release:`` line of every ``*.spec`` in *workdir*, by file name."""
    lines: dict[str, str] = {}
    for spec in sorted(workdir.glob("*.spec")):
        m = _SPEC_RELEASE_RE.search(spec.read_text("utf-8"))
        if m:
            lines[spec.name] = m.group(0)
    return lines


def _restore_spec_release_lines(workdir: Path, lines: dict[str, str]) -> None:
    """Put the snapshotted ``Release:`` line back after the buildtime services.

    obs-service-set_version rewrites every spec's ``Release:`` to ``0``
    unconditionally (no parameter controls it).  The OBS source server reads
    the committed spec's ``Release:`` at commit time as the floor of the
    package's ``vrev`` (CI_CNT), which is how ``%!{PKG_REVISION}`` reaches the
    built RPM; so the rendered line must win over set_version's reset.  Only
    the first ``Release:`` line is restored: that is the one OBS parses.
    """
    for name, line in lines.items():
        spec = workdir / name
        if not spec.is_file():
            continue
        text = spec.read_text("utf-8")
        new = _SPEC_RELEASE_RE.sub(lambda _m: line, text, count=1)
        if new != text:
            spec.write_text(new, "utf-8")
            logger.debug(f"restored {name} {line!r} after buildtime services")
```

In `_run_local_services`, right after `_copy_local_packaging(obs_dir, workdir, pkg_label, macros=macros)` (line 1063):

```python
    spec_release_lines = _spec_release_lines(workdir)
```

and right before the `# ── Cleanup:` comment (line 1102):

```python
    _restore_spec_release_lines(workdir, spec_release_lines)
```

`re` is already imported in `services.py` (check line 3).

- [ ] **Step 4: Run tests, black, pyright**

Run: `PYTHONPATH=. venv/bin/python -m pytest tests/test_run_local_services.py tests/test_service_cache.py -q`
Expected: pass.
Run: `venv/bin/black percona_obs/ tests/ && venv/bin/pyright`
Expected: `0 errors`.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/services.py tests/test_run_local_services.py
git commit -s -m "services: keep the rendered spec Release line through set_version"
```

---

### Task 4: Normalise every spec `Release:` line in the staging and common tiers

**Goal:** Every spec under `root/ppg/staging` and `root/ppg/common` has `Release:        %!{PKG_REVISION}%{?dist}` as its first `Release:` line, and every one of those packages renders without an undefined macro.

**Files:**
- Modify: every `*.spec` under `root/ppg/staging/**/rpm/` and `root/ppg/common/**/rpm/` (about 200 files; `_shared/` files are edited once, symlinked majors follow). Not `root/ppg/devel`, not `root/ppg/releases`.
- Create (temporary, not committed): `/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/545005d2-dd36-495b-8a04-053be993d29f/scratchpad/render_check.py`

**Acceptance Criteria:**
- [ ] `grep -rL` finds no spec under the two trees whose first `Release:` line differs from the template.
- [ ] Rendering every spec and dsc of every package under `root/ppg/staging` and `root/ppg/common` with its own macro chain raises no `SystemExit` (no undefined macro).
- [ ] `git diff --stat` touches only `rpm/*.spec` files and only `Release:` lines.

**Verify:** the two commands in Step 3 print `0` and `OK`.

**Steps:**

- [ ] **Step 1: Rewrite the lines**

From the worktree root:

```bash
find root/ppg/staging root/ppg/common -path '*/rpm/*.spec' -type f -print0 \
  | xargs -0 perl -0pi -e 's/^Release:[ \t]*.*$/Release:        %!{PKG_REVISION}%{?dist}/m'
git diff --stat | tail -1
```

`perl -0 … /m` with no `g` replaces the first match per file only. Expect roughly 200 files changed. Inspect `git diff | grep '^[-+]Release' | sort | uniq -c` : every `-` line is an old `Release:` and every `+` line is the template.

- [ ] **Step 2: Write the render check script** (scratchpad, not committed)

```python
# render_check.py — render every spec/dsc/changelog of every package with its macro chain
import sys
from pathlib import Path
sys.path.insert(0, ".")
from percona_obs.common import REPO_ROOT, find_packages, load_macros, apply_macro_substitution

bad = 0
for top, prj in [("ppg/staging", "ppg:staging"), ("ppg/common", "ppg:common")]:
    for obs_project, pkg in find_packages(REPO_ROOT / top, prj):
        files = list((pkg / "rpm").glob("*.spec")) + list((pkg / "debian").glob("*.dsc"))
        if (pkg / "debian" / "changelog").is_file():
            files.append(pkg / "debian" / "changelog")
        if not files:
            continue
        macros = load_macros(pkg)
        for f in files:
            try:
                apply_macro_substitution(f.read_text("utf-8"), macros, source=f)
            except SystemExit as e:
                bad += 1
                print(f"{obs_project}/{pkg.name}: {f.name}: {e}")
print("OK" if bad == 0 else f"{bad} failures")
```

- [ ] **Step 3: Verify**

```bash
PYTHONPATH=. venv/bin/python -I /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/545005d2-dd36-495b-8a04-053be993d29f/scratchpad/render_check.py
```
Expected: `OK`.

```bash
find root/ppg/staging root/ppg/common -path '*/rpm/*.spec' -type f -exec sh -c \
  'grep -m1 "^Release:" "$1" | grep -qvF "%!{PKG_REVISION}%{?dist}" && echo "$1"' _ {} \; | wc -l
```
Expected: `0`.

If `render_check.py` reports a package whose spec references `PKG_REVISION` but whose `_service` yields no version (none expected: the offline survey of 2026-11-03 found every staging/common package resolves), fix that package's `_service` (add a `version` param) rather than special-casing the tool.

- [ ] **Step 4: Commit**

```bash
git add root/ppg/staging root/ppg/common
git commit -s -m "rpm: every spec Release is %!{PKG_REVISION}%{?dist}"
```

---

### Task 5: Debian dsc, changelog and `set_version` service edits

**Goal:** Every dsc says `[epoch:]<version macro>-%!{PKG_REVISION}`, every changelog header matches, and `set_version` never rewrites a dsc or changelog (restricted to the spec, or dropped).

**Files (40 packages with `debian/changelog`; paths are the real files, symlinked majors follow):**
- Modify dsc + changelog, append `-%!{PKG_REVISION}` (23): `root/ppg/staging/_shared/{percona-pg-telemetry,percona-pg_cron,percona-pg_gather,percona-pg_oidc_validator,percona-pg_repack,percona-pg_stat_monitor,percona-pg_tde,percona-pgaudit,percona-pgaudit_set_user,percona-pgpool-II,percona-pgvector,percona-postgis,percona-postgresql-common,percona-wal2json,python3-psycopg2}`, `root/ppg/staging/common/tools/{percona-haproxy,percona-patroni,percona-pgbackrest,percona-pgbadger,percona-pgbouncer}`, `root/ppg/common/deps/{etcd,python3-pysyncobj,ydiff}`.
- Modify dsc `-1` → `-%!{PKG_REVISION}` (2): `root/ppg/staging/_shared/{percona-ppg-server,percona-ppg-server-ha}`.
- Modify dsc placeholder → real version, drop the dsc `set_version` service (9): `root/ppg/staging/{14,15,16,17,18,19}/percona-postgresql`, `root/ppg/staging/16/tde/percona-postgresql`, `root/ppg/staging/{17,18}/extras/percona-postgresql`; also drop it in `root/ppg/staging/16/extras/percona-postgresql` (no dsc there, service is dead).
- Modify dsc placeholder → real version, add `file` param (6): `root/ppg/staging/16/tde/percona-pg_tde`, `root/ppg/staging/_shared/percona-credcheck`, `root/ppg/staging/19/{percona-pgaudit,percona-postgis,percona-address-standardizer,percona-postgis-tiger-geocoder}`.

**Acceptance Criteria:**
- [ ] Every `debian/*.dsc` under `root/ppg/staging` and `root/ppg/common` has a `Version:` ending in `-%!{PKG_REVISION}`; none is a bare placeholder (`1.0`, `1.0.0`, `1`).
- [ ] Every `debian/changelog` first line has `(<version macros>-%!{PKG_REVISION})`.
- [ ] No `set_version` service under those trees lacks a `file` param in a package that has a dsc.
- [ ] `render_check.py` from Task 4 prints `OK`; `project verify --offline` passes for `ppg:staging` and `ppg:common`.

**Verify:** the commands in Step 5.

**Steps:**

- [ ] **Step 1: Append the revision where the dsc has none (23 packages)**

```bash
for p in root/ppg/staging/_shared/{percona-pg-telemetry,percona-pg_cron,percona-pg_gather,percona-pg_oidc_validator,percona-pg_repack,percona-pg_stat_monitor,percona-pg_tde,percona-pgaudit,percona-pgaudit_set_user,percona-pgpool-II,percona-pgvector,percona-postgis,percona-postgresql-common,percona-wal2json,python3-psycopg2} \
         root/ppg/staging/common/tools/{percona-haproxy,percona-patroni,percona-pgbackrest,percona-pgbadger,percona-pgbouncer} \
         root/ppg/common/deps/{etcd,python3-pysyncobj,ydiff}; do
  perl -pi -e 's/^(Version:[ \t]*\S+?)\s*$/$1-%!{PKG_REVISION}\n/' "$p"/debian/*.dsc
done
grep -h "^Version:" root/ppg/staging/_shared/*/debian/*.dsc root/ppg/staging/common/tools/*/debian/*.dsc root/ppg/common/deps/*/debian/*.dsc | sort | uniq -c
```

Expected: every line ends in `-%!{PKG_REVISION}`; `percona-ppg-server*` show `-1-%!{PKG_REVISION}` → fix those in Step 2.

- [ ] **Step 2: ppg-server / ppg-server-ha**

```bash
perl -pi -e 's/^Version:([ \t]*)1:%!\{PG_VERSION\}-1(-%!\{PKG_REVISION\})?\s*$/Version:${1}1:%!{PG_VERSION}-%!{PKG_REVISION}\n/' \
  root/ppg/staging/_shared/percona-ppg-server/debian/*.dsc root/ppg/staging/_shared/percona-ppg-server-ha/debian/*.dsc
grep -h "^Version:" root/ppg/staging/_shared/percona-ppg-server*/debian/*.dsc
```
Expected: `Version: 1:%!{PG_VERSION}-%!{PKG_REVISION}` twice.

- [ ] **Step 3: Placeholder dscs**

Server family: set the dsc `Version:` to the value of the dsc-rewriting `set_version` service's `version` param plus `-%!{PKG_REVISION}`, then delete that service element (the one with a `version` param and no `file` param). Values per directory:

| directory | new dsc `Version:` |
|---|---|
| `staging/14/percona-postgresql`, `staging/15/percona-postgresql` | `2:%!{PG_VERSION}-%!{PKG_REVISION}` |
| `staging/16/percona-postgresql` | `2:%!{PG_VERSION}-%!{PKG_REVISION}` |
| `staging/16/tde/percona-postgresql`, `staging/17/percona-postgresql` | `2:%!{PG_PACKAGE_VERSION}-%!{PKG_REVISION}` |
| `staging/17/extras/percona-postgresql` | `2:%!{PG_VERSION}-%!{PKG_REVISION}` |
| `staging/18/percona-postgresql`, `staging/19/percona-postgresql` | `3:%!{PG_PACKAGE_VERSION}-%!{PKG_REVISION}` |
| `staging/18/extras/percona-postgresql` | `3:%!{PG_VERSION}-%!{PKG_REVISION}` |

For each: `perl -pi -e 's/^Version:[ \t]*1\.0\s*$/Version: <value>\n/' <dir>/debian/*.dsc`, then in `<dir>/obs/_service` remove the four lines

```xml
  <service mode="buildtime" name="set_version">
    <param name="version">E:%!{...}</param>
  </service>
```

(the block WITHOUT `<param name="file">`). Do the same removal in `staging/16/extras/percona-postgresql/obs/_service`. Confirm with `grep -c set_version <dir>/obs/_service` → `1` for each (the spec-targeted one remains).

Other placeholders: set the dsc `Version:` and add `<param name="file"><spec></param>` inside the existing `set_version` element (for `16/tde/percona-pg_tde` the element is self-closing `<service mode="buildtime" name="set_version" />`: expand it).

| directory | new dsc `Version:` | `file` param |
|---|---|---|
| `staging/16/tde/percona-pg_tde` | `1:%!{PG_TDE_VERSION}-%!{PKG_REVISION}` | `pg_tde.spec` |
| `staging/_shared/percona-credcheck` | `%!{CREDCHECK_VERSION}-%!{PKG_REVISION}` | `percona-credcheck.spec` |
| `staging/19/percona-pgaudit` | `1:%!{PGAUDIT_VERSION}-%!{PKG_REVISION}` | `percona-pgaudit.spec` |
| `staging/19/percona-postgis` | `2:%!{POSTGIS_VERSION}-%!{PKG_REVISION}` | `percona-postgis.spec` |
| `staging/19/percona-address-standardizer` | `%!{ADDRESS_STANDARDIZER_VERSION}-%!{PKG_REVISION}` | `percona-address-standardizer.spec` |
| `staging/19/percona-postgis-tiger-geocoder` | `%!{POSTGIS_TIGER_GEOCODER_VERSION}-%!{PKG_REVISION}` | `percona-postgis-tiger-geocoder.spec` |

Epochs follow the `_shared/` sibling of the same package (pgaudit `1:`, postgis `2:`); the two PG 19-only GIS packages have no production history and get none. The `file` value is the spec's file name in that package's `rpm/` directory (`ls <dir>/rpm/*.spec`).

- [ ] **Step 4: Changelog headers (40 files)**

```bash
# the common case: "(X-1)" -> "(X-%!{PKG_REVISION})"
for f in $(find root/ppg/staging root/ppg/common -path '*/debian/changelog' -type f); do
  perl -pi -e 'if ($. == 1) { s/\(([^)]*?)-1\)/($1-%!{PKG_REVISION})/ }' "$f"
done
# hardcoded or revision-less headers
perl -pi -e 'if ($. == 1) { s/\([^)]*\)/(%!{ETCD_VERSION}-%!{PKG_REVISION})/ }' root/ppg/common/deps/etcd/debian/changelog
perl -pi -e 'if ($. == 1) { s/\([^)]*\)/(%!{PYSYNCOBJ_VERSION}-%!{PKG_REVISION})/ }' root/ppg/common/deps/python3-pysyncobj/debian/changelog
perl -pi -e 'if ($. == 1) { s/\([^)]*\)/(%!{YDIFF_VERSION}-%!{PKG_REVISION})/ }' root/ppg/common/deps/ydiff/debian/changelog
perl -pi -e 'if ($. == 1) { s/\([^)]*\)/(%!{PSYCOPG2_VERSION}-%!{PKG_REVISION})/ }' root/ppg/staging/_shared/python3-psycopg2/debian/changelog
perl -pi -e 'if ($. == 1) { s/\([^)]*\)/(%!{POSTGRESQL_COMMON_VERSION}-%!{PKG_REVISION})/ }' root/ppg/staging/_shared/percona-postgresql-common/debian/changelog
find root/ppg/staging root/ppg/common -path '*/debian/changelog' -type f -exec head -1 {} \; | grep -vc -- '-%!{PKG_REVISION})'
```
Expected last command: `0`. (debtransform re-stamps the changelog header with the dsc version at build time, so this is for consistency, not ordering.)

- [ ] **Step 5: Verify**

```bash
find root/ppg/staging root/ppg/common -path '*/debian/*.dsc' -type f -exec grep -H "^Version:" {} \; | grep -v -- '-%!{PKG_REVISION}$'
```
Expected: no output.

```bash
PYTHONPATH=. venv/bin/python - <<'EOF'
import os, xml.etree.ElementTree as ET
bad = []
for base in ["root/ppg/staging", "root/ppg/common"]:
    for d, _, files in os.walk(base, followlinks=True):
        if os.path.basename(d) != "obs" or "_service" not in files: continue
        pkg = os.path.dirname(d)
        if not any(f.endswith(".dsc") for f in os.listdir(os.path.join(pkg, "debian"))) if os.path.isdir(os.path.join(pkg, "debian")) else True: continue
        for s in ET.fromstring(open(os.path.join(d, "_service")).read()).findall("service"):
            if s.get("name") == "set_version" and not any(p.get("name") == "file" for p in s.findall("param")):
                bad.append(os.path.join(d, "_service"))
print(bad or "OK")
EOF
```
Expected: `OK`.

```bash
PYTHONPATH=. venv/bin/python -I /tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/545005d2-dd36-495b-8a04-053be993d29f/scratchpad/render_check.py
PYTHONPATH=. venv/bin/python -m percona_obs -P labsmain project verify --offline ppg:staging
PYTHONPATH=. venv/bin/python -m percona_obs -P labsmain project verify --offline ppg:common
```
Expected: `OK`, and both verify runs exit 0 (`--offline` makes no OBS call; `-P labsmain` only selects the config).

Then a spot render of one package of each style, e.g.

```bash
PYTHONPATH=. venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, ".")
from pathlib import Path
from percona_obs.common import REPO_ROOT, load_macros, apply_macro_substitution
for rel in ["ppg/staging/17/percona-pgaudit_set_user", "ppg/staging/17/percona-postgresql", "ppg/staging/16/tde/percona-pg_tde", "ppg/common/deps/ydiff"]:
    pkg = REPO_ROOT / rel; m = load_macros(pkg)
    for f in list((pkg/"debian").glob("*.dsc")) + list((pkg/"rpm").glob("*.spec")):
        for line in apply_macro_substitution(f.read_text(), m, source=f).splitlines():
            if line.startswith(("Version:", "Release:")): print(rel, f.name, line); break
EOF
```
Expected (among others): `ppg/staging/17/percona-pgaudit_set_user … Version: 1:4.2.0-7`, `… Release:        7%{?dist}`; `ppg/staging/17/percona-postgresql … Version: 2:17.11.1-1`; `ppg/common/deps/ydiff … Version: 1:1.4.2-4`.

- [ ] **Step 6: Commit**

```bash
git add root/ppg/staging root/ppg/common
git commit -s -m "debian: dsc and changelog revisions render %!{PKG_REVISION}; set_version limited to the spec"
```

---

### Task 6: Documentation

**Goal:** The tool reference and the packaging how-to describe `PKG_REVISION`, and the spec's status says implemented.

**Files:**
- Modify: `docs/PERCONA_OBS_TOOL.md` (after the "The `PPG_RELEASE` counter" section, around line 1069–1090)
- Modify: `docs/PACKAGING_HOWTO.md:160-240` (dsc `Version:` example at 164, `Release:` at 197 and the note at 236; spec example at 453-454)
- Modify: `docs/superpowers/specs/2026-11-02-deb-revision-counter-design.md:4` (Status line)

**Acceptance Criteria:**
- [ ] `docs/PERCONA_OBS_TOOL.md` has a "The `PKG_REVISION` floor" section: what it is, the rule, where `V` comes from, the seed table location, the `set_version` restore, the `vrev` behaviour with the 6-row labs table, the delete/re-add caveat and its manual repair.
- [ ] `docs/PACKAGING_HOWTO.md` templates show `Version: 1:%!{MYPKG_VERSION}-%!{PKG_REVISION}` for the dsc and `Release:        %!{PKG_REVISION}%{?dist}` for the spec, and the note at line 236 no longer says "must be a hardcoded value".
- [ ] Spec status: `Status: implemented (branch deb-revision-counter), 2026-11-03`.

**Verify:** `grep -c PKG_REVISION docs/PERCONA_OBS_TOOL.md docs/PACKAGING_HOWTO.md` → both ≥ 3.

**Steps:**

- [ ] **Step 1: Tool reference section**

Insert after the `PPG_RELEASE` section in `docs/PERCONA_OBS_TOOL.md`:

```markdown
### The `PKG_REVISION` floor

`PKG_REVISION` is the second tool-computed macro. It renders into every spec
`Release:` and every dsc revision in the staging and common tiers:

```
Release:        %!{PKG_REVISION}%{?dist}
Version: 1:%!{PGAUDIT_VERSION}-%!{PKG_REVISION}
```

Its value is `floor + 1`, where `floor` is the counter the old
`postgres-packaging` process shipped to repo.percona.com for this package at
this upstream version (`percona_obs/pkg_version.py`, `PKG_REVISION_FLOORS`,
keyed `(OBS project, package, upstream version)`), and 1 when there is no
entry. The upstream version is read offline from the package's `obs/_service`
with the same extractor `project versions` uses. Packages without a
`_service` (aggregates, images, tarballs, `_link`) get no value.

It is a floor, not a counter. OBS keeps the counter: at every commit the
source server sets the package's `vrev` (what the prjconf calls `<CI_CNT>`)
to `max(previous vrev at the same version + 1, the spec's Release)`, and a
new upstream version starts again from the spec's Release. Observed on labs:

| commit | spec Version / Release | vrev |
|---|---|---|
| 1 | 1.0 / 9 | 9 |
| 2 | 1.0 / 9 | 10 |
| 3 | 1.0 / 3 | 11 (lowering the floor does nothing) |
| 4 | 1.1 / 9 | 9 (new version restarts at the floor) |
| 5 | 1.1 / 9 | 10 |
| 6 | 1.0 / 1 | 12 (keyed by version string, not by order) |

So an RPM is `V-<vrev>.<B_CNT>.elN` with `vrev >= PKG_REVISION`, and a deb is
`[epoch:]V-<PKG_REVISION>+<vrev>.<B_CNT>.<codename>`: the fixed revision beats
production, `+vrev.B_CNT` orders OBS builds among themselves.

`sync` runs `set_version` locally, and that service resets every spec
`Release:` to `0`; `services.py` restores the rendered line afterwards so
the floor reaches OBS. The committed `_service` of a package with a dsc must
restrict `set_version` to the spec (`<param name="file">pkg.spec</param>`),
otherwise the dsc revision and epoch are lost.

Deleting and re-adding a package in OBS restarts `vrev` at the floor, which
may be below the package's own earlier builds at the same version. Repair
by committing once with the OBS commit API's `vrev=<n>` parameter, or by
raising the table entry. Entries become dead when the package moves to
another upstream version; delete the table once every entry is dead.
```

- [ ] **Step 2: How-to templates**

In `docs/PACKAGING_HOWTO.md`: line 164 `Version: 1.0.0` → `Version: 1:%!{MYPKG_VERSION}-%!{PKG_REVISION}` with a sentence "The upstream version macro is the one your `_service` uses; `PKG_REVISION` is computed by the tool (see the tool reference)"; line 197 and 454 `Release:    1%{?dist}` → `Release:    %!{PKG_REVISION}%{?dist}`; rewrite the bullet at 236 to: "`Release:` must be `%!{PKG_REVISION}%{?dist}`. The tool renders the production floor into it and OBS counts commits above it; a literal number is ignored by the build and would only mislead the OBS source server." Adjust the Step 4 sentence at line 102 ("The version here is a placeholder; OBS overwrites it") to say the changelog header uses the same macros as the dsc and debtransform re-stamps it with the final version at build time.

- [ ] **Step 3: Spec status + commit**

Edit line 4 of the spec to `Status: implemented (branch deb-revision-counter), 2026-11-03`.

```bash
git add docs/PERCONA_OBS_TOOL.md docs/PACKAGING_HOWTO.md docs/superpowers/specs/2026-11-02-deb-revision-counter-design.md
git commit -s -m "docs: PKG_REVISION floor and the OBS vrev counter"
```

---

### Task 7: Labs end-to-end check before the PR

**Goal:** Prove on the labs instance that a floored package commits with `vrev >= PKG_REVISION` and that the built file names match the design, before the user opens the PR.

**USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- None in the repo. Uses profile `labspr` (`rootprj isv:percona:PR:pr-97` on https://obs.pg.labs.percona.com) or another labs PR profile the user names.

**Acceptance Criteria:**
- [ ] The user has explicitly said which labs PR project to use and that the push may happen (a `sync push` is a write on labs; ask first, do not assume).
- [ ] `sync push --dry-run` of `ppg:staging:17 percona-pgaudit_set_user` shows the uploaded `percona-pgaudit_set_user.spec` with `Release:        7%{?dist}` and `debian.dsc` with `Version: 1:4.2.0-7`.
- [ ] After the real push, `osc api /source/<PR root>:ppg:staging:17/percona-pgaudit_set_user/_history` shows the new revision with `<version>4.2.0</version>` and `vrev="N"` with `N >= 7`.
- [ ] After the build finishes, `osc ls -b <PR root>:ppg:staging:17 percona-pgaudit_set_user RockyLinux_9 x86_64` lists `percona-pgaudit17_set_user-4.2.0-N.1.el9.x86_64.rpm` and the Debian_12 listing shows `percona-pgaudit17-set-user_4.2.0-7+N.1.bookworm_amd64.deb`.
- [ ] The outputs are pasted into the task close message.

**Verify:**
```
PYTHONPATH=. venv/bin/python -m percona_obs -P labspr sync push --dry-run ppg:staging:17 percona-pgaudit_set_user
PYTHONPATH=. venv/bin/python -m percona_obs -P labspr sync push ppg:staging:17 percona-pgaudit_set_user   # only after the user says go
venv/bin/osc -A https://obs.pg.labs.percona.com api /source/isv:percona:PR:pr-97:ppg:staging:17/percona-pgaudit_set_user/_history | tail -8
venv/bin/osc -A https://obs.pg.labs.percona.com ls -b isv:percona:PR:pr-97:ppg:staging:17 percona-pgaudit_set_user RockyLinux_9 x86_64
venv/bin/osc -A https://obs.pg.labs.percona.com ls -b isv:percona:PR:pr-97:ppg:staging:17 percona-pgaudit_set_user Debian_12 x86_64
```

**Steps:**

- [ ] **Step 1: Dry run** with the first command; confirm the two rendered lines.
- [ ] **Step 2: Ask the user** for the labs PR profile/project and permission to push. Stop here until answered.
- [ ] **Step 3: Push, read `_history`**, capture `vrev`.
- [ ] **Step 4: Wait for the build** (`build status` with the same profile, or `osc results`), capture both binary listings.
- [ ] **Step 5: Report** the three outputs verbatim. No commit in this task.

---

## Self-review notes

- Spec coverage: counter rule (T1/T2), `V` source and rewrite fix (T1), offline rule (T1: resolver `None` → `None`, T2: no injection), seed table (T1), Debian files (T5), RPM files (T4), `set_version` restore (T3), symmetry (T2), docs (T6), labs check (T7), verification script (T4/T5). The spec's "offline guard fails `project verify`" materialises as the normal undefined-macro error when a package references `PKG_REVISION` without a resolvable `V` (Task 4 step 3 checks none exists); no separate error path is added.
- The devel tier is untouched: its specs keep literal `Release:` values, which the restore step now also keeps through `set_version` (today they are zeroed). That only raises devel `vrev` floors to the literal values already in git (1 everywhere except where a spec says otherwise), and devel is never published.
- Type consistency: `extract_version_from_service_text(text, resolve_tag=None)`, `extract_version_from_service(path, resolve_tag=None)`, `compute_pkg_revision(project, package, version) -> str`, `PKG_REVISION_FLOORS`, `_spec_release_lines`, `_restore_spec_release_lines`, `_git_tracked_path` used consistently across tasks.
