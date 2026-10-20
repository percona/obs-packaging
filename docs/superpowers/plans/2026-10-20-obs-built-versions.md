# Package Versions From OBS Builds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `qa` (`EXPECTED_VERSIONS`) and `project versions --online` read package versions from the binaries OBS built, with an agreement check across the instance's repositories, instead of parsing `obs/_service` locally.

**Architecture:** A new module `percona_obs/obs_versions.py` fetches one `binarylist` per OBS project and turns binary file names into per-repository versrels. `cmd_qa` keeps its package-selection rule (local tree decides *which* packages; for a release mirror the local tree of its staging source) and takes the *version* from OBS at `qa run`. `project release` stops baking `EXPECTED_VERSIONS` and marks copied package lanes with `package:`. `project versions --online` uses the same batch fetch for its package rows.

**Tech Stack:** Python 3.11, osc (`osc.core.makeurl`, `osc.connection.http_GET`), pytest, black, pyright.

**Spec:** `docs/superpowers/specs/2026-10-20-obs-built-versions-design.md`

## Global Constraints

- After every code change: `venv/bin/black percona_obs/ tests/` then `venv/bin/pyright` (0 errors) then `venv/bin/pytest -q` (all pass). Do not reformat unrelated files: run black only on files you changed if black wants to touch others (`git checkout --` anything unrelated it rewrote).
- Commits: `git commit -s`; **no** `Co-Authored-By` line; never `git push`.
- Work only in the worktree `/home/rdias/Work/percona-obs-packaging/.claude/worktrees/obs-built-versions` (branch `obs-built-versions`). The virtualenv is `venv/` → use `/home/rdias/Work/percona-obs-packaging/venv/bin/...` if `venv` is not present in the worktree.
- Versrel = `<version>-<release>` as parsed from a binary file name (`2.60.0-1.1`). Upstream version = versrel without the release (everything from the last `-` dropped): `2.60.0`. DEB file names carry no epoch; never add one.
- `EXPECTED_VERSIONS` values are upstream versions, one `package=version` line per package, sorted by package name (unchanged format).
- An OBS request error is never swallowed: it raises `SystemExit` naming the project. HTTP 404 on a project means "project absent" (returns `None`).
- `-P isv` is production: only read-only commands with it (Task 6 is read-only).

**User decisions (already made):**
- "OBS built versrel" is the source of truth for package versions.
- Container/tarball projects: source packages' versrel (projects they build from), not the artifact manifest.
- "Yes: compute only at qa run" — `project release` stops baking `EXPECTED_VERSIONS`; every lane (PR, staging, nightly, pre-release) computes at `qa run`.
- "Must agree; differ = error" — differing upstream versions across the slice's repositories fail `qa run` before any Jenkins trigger; packages with no binaries are left out and named in one warning.
- "Approach 1" — one `binarylist` request per OBS project.
- `project versions --online` uses the new implementation and "Keep versrel output" (first repository's versrel, warn on conflict).

**Rulings made while planning (spec gaps):**
- Ruling: release mirrors take their *structure* (packages, build-from projects, artifact detection) from the staging project they mirror (the `project:` of the nearest `release.yaml` plus the same sub-path), and read *versions* from the mirror's OBS project — this is what cut-time baking computed, now at run time — cost if wrong: mirror lanes list the staging package set, which `project release` copies 1:1 anyway.
- Ruling: mirror package lanes (`<pkg>.<segment>`) carry a persisted `package: <name>` key (replacing the in-memory `_package` marker) so `qa run` still scopes them to their own package — cost if wrong: one extra optional qa-entry key, validated as a non-empty string.
- Ruling: the fallback root applies only to projects that are not mirror translations (a release lane never falls back to production release projects); a package present in its project but without binaries never falls back — cost if wrong: a cross-major mirror path reads production staging, as baking did.
- Ruling: packages whose local `obs/` holds an image or tarball recipe (`Dockerfile`, `simpleimage`, `*.kiwi`) are not version candidates and never appear in the "no binaries" warning.

---

## File Structure

| File | Responsibility |
|---|---|
| `percona_obs/obs_versions.py` (new) | Fetch a project's `binarylist`, per-repo versrels, upstream normalisation, agreement, first versrel. |
| `percona_obs/cmd_build.py` | `_version_from_binary` also parses `.src.rpm` and `.dsc`. |
| `percona_obs/cmd_qa.py` | `EXPECTED_VERSIONS` from OBS; mirror structure mapping; `package:` key; `qa show --expected-versions`. |
| `percona_obs/cli.py` | `--expected-versions` flag on `qa show`. |
| `percona_obs/cmd_project.py` | `_mirror_qa_entries` stops baking and writes `package:`; `project versions --online` package rows via the batch fetch. |
| `tests/test_obs_versions.py` (new) | Module tests. |
| `tests/test_qa_expected_versions.py` | Rewritten for OBS-sourced versions. |
| `tests/test_version_from_set_version.py`, `tests/test_project_release.py`, `tests/test_versions_online.py`, `tests/test_qa_package_lanes.py` | Updated to the new behaviour. |
| `docs/PERCONA_OBS_TOOL.md`, `.github/copilot-instructions.md`, `docs/superpowers/specs/2026-10-13-prerelease-project-release-flow-design.md` | Docs. |

---

### Task 1: `obs_versions` module and source-artifact file names

**Goal:** A module that returns `{package: {(repo, arch): versrel}}` for an OBS project from one `binarylist` request, plus upstream normalisation, agreement and first-versrel helpers; `_version_from_binary` reads `.src.rpm` and `.dsc`.

**Files:**
- Create: `percona_obs/obs_versions.py`
- Modify: `percona_obs/cmd_build.py` (`_version_from_binary`, ~line 136)
- Test: `tests/test_obs_versions.py`

**Acceptance Criteria:**
- [ ] `_version_from_binary("percona-pgbackrest-2.60.0-1.1.src.rpm") == "2.60.0-1.1"` and `_version_from_binary("percona-postgresql-17_17.11.1-1.dsc") == "17.11.1-1"`; existing `.rpm`/`.deb` results unchanged; `_buildenv` → `None`.
- [ ] `project_binary_versions` makes exactly one GET to `/build/<prj>/_result?view=binarylist` per `(apiurl, project, filter)` per process (cached), skips repositories the filter rejects, keeps a package with an empty `{}` when it is listed without readable binaries, prefers `.src.rpm`/`.dsc` over binaries, returns `None` on HTTP 404 and raises `SystemExit` naming the project on any other HTTP/URL/XML error.
- [ ] `upstream_version("2.60.0-1.1") == "2.60.0"`, `upstream_version("1.0-rc1-2") == "1.0-rc1"`, `upstream_version("293") == "293"`, `upstream_version("2.60.0-1+1.1.bookworm") == "2.60.0"`.
- [ ] An `_aggregate` package's binaries, listed under its own name in the aggregating project's `binarylist` (Debian `…_2.60.0-1+1.1.bookworm_amd64.deb`), resolve to `2.60.0`.
- [ ] `agreed_version` returns the single upstream value; on two values raises `VersionConflict` whose `str()` is `percona-foo: OBS builds disagree on the version: 1.2.3 (Debian_12/x86_64, RockyLinux_9/x86_64), 1.2.4 (Ubuntu_24.04/x86_64)` (values sorted, repos sorted).
- [ ] `first_versrel` returns the versrel of `min((repo, arch))`.

**Verify:** `venv/bin/pytest -q tests/test_obs_versions.py tests/test_versions_online.py` → all pass; `venv/bin/pyright` → 0 errors.

**Steps:**

- [ ] **Step 1: Write the failing tests** — `tests/test_obs_versions.py`:

```python
"""percona_obs.obs_versions: package versions from OBS binary file names."""

import io
import urllib.error

import pytest

import percona_obs.obs_versions as ov
from percona_obs.cmd_build import _version_from_binary
from percona_obs.project_config import RepositoryFilter

_XML = """<resultlist state="x">
 <result project="P" repository="RockyLinux_9" arch="x86_64" code="published" state="published">
  <binarylist package="percona-pgbackrest">
   <binary filename="_buildenv" size="1" mtime="1"/>
   <binary filename="percona-pgbackrest-debuginfo-2.60.0-1.1.x86_64.rpm" size="1" mtime="1"/>
   <binary filename="percona-pgbackrest-2.60.0-1.1.src.rpm" size="1" mtime="1"/>
  </binarylist>
  <binarylist package="percona-image"><binary filename="img.containerinfo" size="1" mtime="1"/></binarylist>
  <binarylist package="geos"/>
 </result>
 <result project="P" repository="Debian_12" arch="x86_64" code="published" state="published">
  <binarylist package="percona-pgbackrest">
   <binary filename="percona-pgbackrest_2.60.0-1_amd64.deb" size="1" mtime="1"/>
  </binarylist>
 </result>
 <result project="P" repository="ubi9" arch="x86_64" code="published" state="published">
  <binarylist package="percona-pgbackrest">
   <binary filename="percona-pgbackrest-2.60.0-3.1.src.rpm" size="1" mtime="1"/>
  </binarylist>
 </result>
</resultlist>"""


class _Resp(io.BytesIO):
    pass


@pytest.fixture(autouse=True)
def _clear():
    ov.clear_cache()
    yield
    ov.clear_cache()


def _serve(monkeypatch, body=_XML, error=None):
    calls = []

    def get(url):
        calls.append(url)
        if error is not None:
            raise error
        return _Resp(body.encode())

    monkeypatch.setattr(ov.osc.connection, "http_GET", get)
    monkeypatch.setattr(
        ov.osc.core,
        "makeurl",
        lambda apiurl, path, query=None: f"{apiurl}/{'/'.join(path)}?{query}",
    )
    return calls


def test_version_from_binary_reads_source_artifacts():
    assert _version_from_binary("percona-pgbackrest-2.60.0-1.1.src.rpm") == "2.60.0-1.1"
    assert _version_from_binary("percona-postgresql-17_17.11.1-1.dsc") == "17.11.1-1"
    assert (
        _version_from_binary("percona-postgresql17-17.11.1-1.18.x86_64.rpm")
        == "17.11.1-1.18"
    )
    assert _version_from_binary("percona-pg-tde18_2.2.2-6_amd64.deb") == "2.2.2-6"
    assert _version_from_binary("_buildenv") is None
    assert _version_from_binary("percona-postgresql-17.11.1-ssl3-linux-x86_64.tar.gz") is None


def test_project_binary_versions_per_repo(monkeypatch):
    calls = _serve(monkeypatch)
    got = ov.project_binary_versions("http://obs", "P")
    assert got == {
        "percona-pgbackrest": {
            ("RockyLinux_9", "x86_64"): "2.60.0-1.1",  # .src.rpm preferred
            ("Debian_12", "x86_64"): "2.60.0-1",
            ("ubi9", "x86_64"): "2.60.0-3.1",
        },
        "percona-image": {},  # listed, nothing readable
        "geos": {},  # listed, no binaries
    }
    assert len(calls) == 1 and "binarylist" in calls[0]


def test_project_binary_versions_is_cached(monkeypatch):
    calls = _serve(monkeypatch)
    ov.project_binary_versions("http://obs", "P")
    ov.project_binary_versions("http://obs", "P")
    assert len(calls) == 1


def test_project_binary_versions_respects_the_slice(monkeypatch):
    _serve(monkeypatch)
    rf = RepositoryFilter.from_profile({"exclude-repositories": ["ubi*"]})
    got = ov.project_binary_versions("http://obs", "P", rf)
    assert ("ubi9", "x86_64") not in got["percona-pgbackrest"]


def test_missing_project_is_none(monkeypatch):
    _serve(monkeypatch, error=urllib.error.HTTPError("u", 404, "nf", {}, None))  # type: ignore[arg-type]
    assert ov.project_binary_versions("http://obs", "P") is None


def test_other_errors_are_not_swallowed(monkeypatch):
    _serve(monkeypatch, error=urllib.error.HTTPError("u", 500, "boom", {}, None))  # type: ignore[arg-type]
    with pytest.raises(SystemExit, match="P"):
        ov.project_binary_versions("http://obs", "P")


def test_upstream_version():
    assert ov.upstream_version("2.60.0-1.1") == "2.60.0"
    assert ov.upstream_version("1.0-rc1-2") == "1.0-rc1"
    assert ov.upstream_version("293") == "293"
    # Debian aggregate binaries on OBS carry the distro in the release
    assert ov.upstream_version("2.60.0-1+1.1.bookworm") == "2.60.0"


def test_aggregate_binaries_are_listed_under_the_aggregating_package(monkeypatch):
    """OBS lists an _aggregate's binaries under its own package name in the
    aggregating project's binarylist (real shape, ppg:staging:17)."""
    body = """<resultlist state="x">
 <result project="P" repository="Debian_12" arch="x86_64" code="published" state="published">
  <binarylist package="percona-pgbackrest">
   <binary filename="percona-pgbackrest-dbgsym_2.60.0-1+1.1.bookworm_amd64.deb" size="1" mtime="1"/>
   <binary filename="percona-pgbackrest_2.60.0-1+1.1.bookworm_amd64.deb" size="1" mtime="1"/>
  </binarylist>
 </result>
</resultlist>"""
    _serve(monkeypatch, body=body)
    per = ov.project_binary_versions("http://obs", "P")["percona-pgbackrest"]
    assert ov.agreed_version("percona-pgbackrest", per) == "2.60.0"


def test_agreed_version_and_conflict():
    same = {("Debian_12", "x86_64"): "2.60.0-1", ("RockyLinux_9", "x86_64"): "2.60.0-1.1"}
    assert ov.agreed_version("p", same) == "2.60.0"
    differ = {
        ("RockyLinux_9", "x86_64"): "1.2.3-1.1",
        ("Debian_12", "x86_64"): "1.2.3-1",
        ("Ubuntu_24.04", "x86_64"): "1.2.4-1",
    }
    with pytest.raises(ov.VersionConflict) as exc:
        ov.agreed_version("percona-foo", differ)
    assert str(exc.value) == (
        "percona-foo: OBS builds disagree on the version: "
        "1.2.3 (Debian_12/x86_64, RockyLinux_9/x86_64), 1.2.4 (Ubuntu_24.04/x86_64)"
    )


def test_first_versrel_is_the_first_sorted_repo():
    per = {("ubi9", "x86_64"): "2.60.0-3.1", ("Debian_12", "x86_64"): "2.60.0-1"}
    assert ov.first_versrel(per) == "2.60.0-1"
```

Check `RepositoryFilter.from_profile`'s key names in `percona_obs/project_config.py` (~line 73, the `("include-repositories", "include_repos")` table) and use the exclude key it defines if it is not `exclude-repositories`.

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_obs_versions.py`
Expected: FAIL (`ModuleNotFoundError: percona_obs.obs_versions`).

- [ ] **Step 3: Extend `_version_from_binary`** in `percona_obs/cmd_build.py` — replace the function body:

```python
def _version_from_binary(filename: str) -> str | None:
    """Extract version-release from a package file name.

    Supports RPM binaries and sources (name-version-release[.arch].rpm,
    name-version-release.src.rpm), DEB binaries (name_version_arch.deb) and
    DEB sources (name_version.dsc).  DEB names carry no epoch.
    """
    if filename.endswith(".src.rpm"):
        chunks = filename[: -len(".src.rpm")].rsplit("-", 2)
        if len(chunks) == 3:
            return f"{chunks[1]}-{chunks[2]}"
    elif filename.endswith(".rpm"):
        # name-version-release.arch.rpm → strip arch.rpm, split off last two -
        base = filename.rsplit(".", 2)  # ['name-ver-rel', 'arch', 'rpm']
        if len(base) == 3:
            chunks = base[0].rsplit("-", 2)
            if len(chunks) == 3:
                return f"{chunks[1]}-{chunks[2]}"
    elif filename.endswith(".deb"):
        # name_version_arch.deb
        parts = filename[:-4].split("_", 2)
        if len(parts) >= 2:
            return parts[1]
    elif filename.endswith(".dsc"):
        parts = filename[:-4].split("_", 1)
        if len(parts) == 2 and parts[1]:
            return parts[1]
    return None
```

`_fetch_pkg_versrel` iterates binaries and returns the first readable one; every binary of a package shares its versrel, so its results do not change. Run `venv/bin/pytest -q tests/test_versions_online.py` to confirm.

- [ ] **Step 4: Create `percona_obs/obs_versions.py`**

```python
"""Package versions as OBS built them.

One ``GET /build/<project>/_result?view=binarylist`` lists every package's
binaries in every repository of a project; the version-release of a package
in a repository is read from a binary file name (source artifacts preferred,
their names are the package's own).  Callers decide what to do with
disagreeing repositories: ``agreed_version`` (qa) or ``first_versrel``
(``project versions --online``).
"""

from __future__ import annotations

import urllib.error
import xml.etree.ElementTree as ET

import osc.connection
import osc.core

from .cmd_build import _version_from_binary
from .project_config import RepositoryFilter

PerRepo = dict[tuple[str, str], str]
ProjectVersions = dict[str, PerRepo]

_cache: dict[tuple[str, str, str], "ProjectVersions | None"] = {}


def clear_cache() -> None:
    _cache.clear()


def _pick_versrel(filenames: list[str]) -> "str | None":
    names = sorted(filenames)
    for name in names:
        if name.endswith((".src.rpm", ".dsc")):
            versrel = _version_from_binary(name)
            if versrel:
                return versrel
    for name in names:
        versrel = _version_from_binary(name)
        if versrel:
            return versrel
    return None


def project_binary_versions(
    apiurl: str, obs_project: str, repo_filter: "RepositoryFilter | None" = None
) -> "ProjectVersions | None":
    """``{package: {(repo, arch): versrel}}`` for *obs_project*, or None when
    the project does not exist.  A package listed without a readable binary
    in a repository has no entry for it (an empty dict when it has none
    anywhere).  Repositories rejected by *repo_filter* are skipped."""
    key = (apiurl, obs_project, repr(repo_filter.to_profile()) if repo_filter else "")
    if key in _cache:
        return _cache[key]
    url = osc.core.makeurl(
        apiurl, ["build", obs_project, "_result"], query={"view": "binarylist"}
    )
    try:
        root = ET.fromstring(osc.connection.http_GET(url).read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _cache[key] = None
            return None
        raise SystemExit(
            f"error: cannot list the binaries of {obs_project}: HTTP {exc.code} {exc.reason}"
        )
    except (urllib.error.URLError, ET.ParseError, OSError) as exc:
        raise SystemExit(f"error: cannot list the binaries of {obs_project}: {exc}")
    versions: ProjectVersions = {}
    for result in root.findall("result"):
        repo = result.get("repository", "")
        arch = result.get("arch", "")
        if repo_filter is not None and not repo_filter.repo_matches(repo):
            continue
        for binarylist in result.findall("binarylist"):
            package = binarylist.get("package", "")
            if not package:
                continue
            per_repo = versions.setdefault(package, {})
            versrel = _pick_versrel(
                [b.get("filename", "") for b in binarylist.findall("binary")]
            )
            if versrel:
                per_repo[(repo, arch)] = versrel
    _cache[key] = versions
    return versions


def upstream_version(versrel: str) -> str:
    """'2.60.0-1.1' -> '2.60.0': the version without the release."""
    return versrel.rsplit("-", 1)[0]


class VersionConflict(Exception):
    def __init__(self, package: str, by_version: "dict[str, list[tuple[str, str]]]"):
        self.package = package
        self.by_version = by_version
        listing = ", ".join(
            f"{version} ({', '.join(f'{r}/{a}' for r, a in sorted(repos))})"
            for version, repos in sorted(by_version.items())
        )
        super().__init__(f"{package}: OBS builds disagree on the version: {listing}")


def agreed_version(package: str, per_repo: PerRepo) -> str:
    """The upstream version every repository agrees on."""
    by_version: dict[str, list[tuple[str, str]]] = {}
    for repo_arch, versrel in per_repo.items():
        by_version.setdefault(upstream_version(versrel), []).append(repo_arch)
    if len(by_version) != 1:
        raise VersionConflict(package, by_version)
    return next(iter(by_version))


def first_versrel(per_repo: PerRepo) -> str:
    """The versrel of the first (repo, arch) in sorted order."""
    return per_repo[min(per_repo)]
```

If `RepositoryFilter` has no `to_profile()` returning something `repr`-stable, key the cache on `id(repo_filter)` instead (filters are process-wide singletons).

- [ ] **Step 5: Run tests, black, pyright**

Run: `venv/bin/black percona_obs/obs_versions.py percona_obs/cmd_build.py tests/test_obs_versions.py && venv/bin/pyright && venv/bin/pytest -q tests/test_obs_versions.py tests/test_versions_online.py`
Expected: all pass, 0 errors.

- [ ] **Step 6: Commit**

```bash
git add percona_obs/obs_versions.py percona_obs/cmd_build.py tests/test_obs_versions.py
git commit -s -m "obs_versions: package versions from OBS binary file names

One binarylist request per project gives every package's versrel per
repository; source artifacts (.src.rpm, .dsc) are preferred and
_version_from_binary now reads them. Helpers normalise to the upstream
version, check that repositories agree, or pick the first repository."
```

```json:metadata
{"files": ["percona_obs/obs_versions.py", "percona_obs/cmd_build.py", "tests/test_obs_versions.py"], "verifyCommand": "venv/bin/pytest -q tests/test_obs_versions.py tests/test_versions_online.py && venv/bin/pyright", "acceptanceCriteria": ["_version_from_binary parses .src.rpm and .dsc; existing rpm/deb results unchanged", "project_binary_versions: one cached GET per project, slice filter, empty dict for listed packages without readable binaries, source artifacts preferred, None on 404, SystemExit naming the project otherwise", "upstream_version drops the release", "agreed_version returns the single value or raises VersionConflict with the specified message", "first_versrel returns the versrel of min((repo, arch))"], "modelTier": "mechanical"}
```

---

### Task 2: `qa` takes `EXPECTED_VERSIONS` from OBS

**Goal:** `qa run` (always) and `qa show --expected-versions` (opt-in) compute `EXPECTED_VERSIONS` from OBS binaries, with mirror-structure mapping, PR fallback, a conflict error before any trigger, one warning for packages without binaries, and the `package:` entry key.

**Files:**
- Modify: `percona_obs/cmd_qa.py` (lines ~44, ~249–295 `_validate_qa`, ~482–630 versions block, `cmd_qa_show` ~633, `cmd_qa_run` ~833)
- Modify: `percona_obs/cli.py` (`qa show` parser, ~line 578)
- Test: `tests/test_qa_expected_versions.py` (rewrite fixtures), `tests/test_version_from_set_version.py` (replace the two qa-route tests), `tests/test_qa_package_lanes.py` (only if a test breaks)

**Acceptance Criteria:**
- [ ] `_package_versions` keeps the selection rule (own packages; for projects without own versions or that build artifacts, then the `subproject:` path projects, first provider wins) but every version comes from `project_binary_versions(<rootprj>:<project>)` via `agreed_version`.
- [ ] A release-mirror project (`ppg:releases:18:containers`) uses the structure of its staging source (`ppg:staging:18:containers`) and reads versions from `<rootprj>:ppg:releases:18[...]`; ids outside the staging top (e.g. `ppg:staging:17`) are read unchanged.
- [ ] A package absent from its OBS project (no `binarylist` entry, or the project returns `None`) is read from `<fallback_rootprj>:<same id>` when a fallback root is set and the project is not a mirror translation; a present package with no readable binary never falls back.
- [ ] Packages whose local `obs/` has `Dockerfile`, `simpleimage` or `*.kiwi` are not candidates; packages left without a version are named in exactly one stderr line `warning: no OBS binaries for: <a>, <b> — left out of EXPECTED_VERSIONS`.
- [ ] A `VersionConflict` makes `qa run` exit with `error: <conflict message>` before any Jenkins trigger.
- [ ] `qa show` makes no OBS request without `--expected-versions` and adds no `EXPECTED_VERSIONS`; with it, values are computed. `qa run` without an apiurl exits `error: EXPECTED_VERSIONS needs an OBS connection (-P profile or -A apiurl)`.
- [ ] An entry with `package: <name>` gets only that package's line; `package` must be a non-empty string (validation error otherwise); an entry setting `EXPECTED_VERSIONS` itself is unchanged.
- [ ] Nothing in `cmd_qa` calls `_extract_version_from_service` any more.

**Verify:** `venv/bin/pytest -q tests/test_qa_expected_versions.py tests/test_qa_package_lanes.py tests/test_version_from_set_version.py tests/test_qa_images.py && venv/bin/pytest -q && venv/bin/pyright` → all pass, 0 errors.

**Steps:**

- [ ] **Step 1: Rewrite the test fixtures to mock OBS** — in `tests/test_qa_expected_versions.py` keep `_QA`, `_package` and the tree layout of `_tree`, but drop the `_service` versions as the source: OBS answers come from a dict. Add:

```python
import percona_obs.obs_versions as ov

R9 = ("RockyLinux_9", "x86_64")
D12 = ("Debian_12", "x86_64")

OBS = {
    "isv:percona:ppg:staging:18": {
        "percona-pgbackrest": {R9: "2.60.0-1.1", D12: "2.60.0-1"},
        "percona-pgaudit": {R9: "18.0-1.1"},
        "percona-ppg-server": {},          # listed, no readable binary
        "etcd": {R9: "3.5.34-1.1"},        # aggregate: binaries listed here
    },
    "isv:percona:ppg:staging:17": {
        "percona-pgbackrest": {R9: "2.60.0-1.1"},
        "percona-pgaudit": {R9: "17.0-1.1"},
        "percona-ppg-server": {},
        "etcd": {R9: "3.5.34-1.1"},
    },
}


def _obs(monkeypatch, data=OBS):
    calls = []

    def fetch(apiurl, project, repo_filter=None):
        calls.append(project)
        return data.get(project)

    monkeypatch.setattr(cmd_qa, "project_binary_versions", fetch)
    return calls


def _show(project, capsys, **kw):
    args = SimpleNamespace(
        project=project,
        rootprj="isv:percona",
        env_overrides=[],
        json=True,
        apiurl="http://obs",
        image_fallback_rootprj=kw.pop("fallback", None),
        expected_versions=kw.pop("expected_versions", True),
        profile=None,
    )
    cmd_qa.cmd_qa_show(args)
    out = capsys.readouterr()
    return {r["name"]: r["params"] for r in json.loads(out.out)}, out.err
```

Rewrite the existing tests to this fixture (same intent, new source) and add:

```python
def test_versions_come_from_obs(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    _obs(monkeypatch)
    params, err = _show("ppg:staging:18", capsys)
    assert params["server"]["EXPECTED_VERSIONS"].split("\n") == [
        "etcd=3.5.34",
        "percona-pgaudit=18.0",
        "percona-pgbackrest=2.60.0",
    ]
    assert "warning: no OBS binaries for: percona-ppg-server" in err


def test_show_without_flag_makes_no_obs_request(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    calls = _obs(monkeypatch)
    params, _ = _show("ppg:staging:18", capsys, expected_versions=False)
    assert calls == []
    assert "EXPECTED_VERSIONS" not in params["server"]


def test_conflict_aborts(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    data = {
        "isv:percona:ppg:staging:18": {
            "percona-pgbackrest": {R9: "2.60.0-1.1", D12: "2.59.2-1"},
        }
    }
    _obs(monkeypatch, data)
    with pytest.raises(SystemExit, match="percona-pgbackrest: OBS builds disagree"):
        _show("ppg:staging:18", capsys)


def test_pr_fallback_only_for_absent_packages(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    data = {
        "isv:percona:PR:pr-5:ppg:staging:18": {
            "percona-pgaudit": {},                     # present, build failed
        },
        "isv:percona:ppg:staging:18": OBS["isv:percona:ppg:staging:18"],
    }
    calls = _obs(monkeypatch, data)
    args_root = "isv:percona:PR:pr-5"
    monkeypatch.setattr(
        cmd_qa, "_qa_env_vars", lambda a: {"OBS_ROOTPRJ": args_root}
    )
    args = SimpleNamespace(
        project="ppg:staging:18", rootprj=args_root, env_overrides=[], json=True,
        apiurl="http://obs", image_fallback_rootprj="isv:percona",
        expected_versions=True, profile=None,
    )
    cmd_qa.cmd_qa_show(args)
    out = capsys.readouterr()
    value = {r["name"]: r["params"] for r in json.loads(out.out)}["server"][
        "EXPECTED_VERSIONS"
    ]
    assert "percona-pgbackrest=2.60.0" in value      # absent → production
    assert "percona-pgaudit" not in value             # present w/o binaries: no fallback
    assert "percona-pgaudit" in out.err
    assert "isv:percona:ppg:staging:18" in calls


def test_package_key_scopes_the_entry():
    versions = {"etcd": "3.5.34", "percona-pgbackrest": "2.60.0"}
    entries = [{"name": "x", "pipeline": "p", "parameters": {"A": "1"}, "package": "etcd"}]
    out = cmd_qa._with_expected_versions(entries, "ppg:staging:18", None, versions)
    assert out[0]["parameters"]["EXPECTED_VERSIONS"] == "etcd=3.5.34"


def test_package_key_must_be_a_string():
    with pytest.raises(SystemExit, match="qa.package"):
        cmd_qa._validate_qa({"pipeline": "p", "parameters": {"A": 1}, "package": ""}, "P")
```

Add a mirror test: build `root/ppg/releases/18/release.yaml` (`project: ppg:staging:18\nreleases:\n  - ppg/18.6-2\n`), `root/ppg/releases/18/project.yaml` (copy `_QA`, no package dirs), serve OBS data for `isv:percona:PR:pr-148:ppg:releases:18` and assert the server lane gets `percona-pgbackrest=2.60.0` (structure from `ppg:staging:18`'s package dirs, versions from the pre-release id, no request to `isv:percona:ppg:releases:18`). Keep the container/tarball selection tests (`test_container_project_gets_the_versions_its_images_build_from`, `test_tarball_project_adds_the_bundled_components`, `test_project_with_own_versions_*`) with OBS data for every project they read. Change `test_package_entry_is_restricted` to use the `package` key. Also update `test_qa_run_dry_run_shows_it` to set `apiurl` and mock `project_binary_versions`.

In `tests/test_version_from_set_version.py` replace `test_pgbackrest_in_tools_versions` and `test_pgbackrest_reaches_server_image_expected_versions` with one test that asserts on the extractor itself (it still serves `project versions`):

```python
def test_pgbackrest_service_resolves_through_macros():
    from percona_obs.common import REPO_ROOT, apply_macro_substitution, load_macros
    pkg = REPO_ROOT / "ppg" / "staging" / "common" / "tools" / "percona-pgbackrest"
    raw = _extract_version_from_service(pkg / "obs" / "_service")
    assert raw and "%!{" in raw
    version = apply_macro_substitution(raw, load_macros(pkg), strict=False)
    assert version and "%!{" not in version
```

(import `_extract_version_from_service` from `percona_obs.cmd_project` if the file does not already).

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_qa_expected_versions.py`
Expected: FAIL (no `project_binary_versions` in `cmd_qa`, no `expected_versions` handling).

- [ ] **Step 3: Implement in `percona_obs/cmd_qa.py`**

Imports: drop `_extract_version_from_service, _resolve_aggregate_source` from the `cmd_project` import line (delete the line if nothing else is imported from it); add

```python
from .common import get_default_repository_filter
from .obs_versions import VersionConflict, agreed_version, project_binary_versions
```

(merge `get_default_repository_filter` into the existing `from .common import (...)` block).

In `_validate_qa`, after the `name` check:

```python
    if "package" in qa:
        package = qa.get("package")
        if not isinstance(package, str) or not package:
            raise SystemExit(f"error: {project}: qa.package must be a non-empty string")
```

Replace the block from `def _own_package_versions` through `def _lanes_with_expected_versions` (keep `EXPECTED_VERSIONS_PARAM`, `_builds_artifacts`, `_expected_versions`) with:

```python
_ARTIFACT_RECIPES = ("Dockerfile", "simpleimage")


def _is_artifact_package(pkg_path: Path) -> bool:
    obs = pkg_path / "obs"
    return any((obs / n).is_file() for n in _ARTIFACT_RECIPES) or any(obs.glob("*.kiwi"))


def _mirror_source(project: str) -> "tuple[str, str] | None":
    """(release_top, staging_top) when *project* lies in a release mirror tree.

    The nearest directory holding release.yaml is the mirror's top; its
    ``project:`` names the staging project it mirrors."""
    path = resolve_project_path(project)
    while path != REPO_ROOT and REPO_ROOT in path.parents:
        record = path / "release.yaml"
        if record.is_file():
            staging = (load_yaml_with_env(record, {}) or {}).get("project")
            if isinstance(staging, str) and staging:
                return ":".join(path.relative_to(REPO_ROOT).parts), staging
            return None
        path = path.parent
    return None


@dataclasses.dataclass
class _VersionLookup:
    """Where qa reads package versions: the OBS root under test, the PR
    fallback root, and the mirror translation (staging id → release id)."""

    apiurl: str
    rootprj: str
    fallback_rootprj: "str | None"
    mirror: "tuple[str, str] | None" = None  # (release_top, staging_top)
    missing: set[str] = dataclasses.field(default_factory=set)

    def target(self, structure_id: str) -> str:
        if self.mirror is None:
            return structure_id
        release_top, staging_top = self.mirror
        if structure_id == staging_top or structure_id.startswith(staging_top + ":"):
            return release_top + structure_id[len(staging_top) :]
        return structure_id

    def _fetch(self, root: str, project_id: str):
        return project_binary_versions(
            self.apiurl, f"{root}:{project_id}", get_default_repository_filter()
        )

    def version(self, structure_id: str, package: str) -> "str | None":
        target = self.target(structure_id)
        data = self._fetch(self.rootprj, target)
        per_repo = None if data is None else data.get(package)
        if per_repo is None and self.fallback_rootprj and target == structure_id:
            fallback = self._fetch(self.fallback_rootprj, target)
            per_repo = None if fallback is None else fallback.get(package)
        if not per_repo:
            self.missing.add(package)
            return None
        return agreed_version(package, per_repo)


def _version_lookup(args: argparse.Namespace, project: str) -> _VersionLookup:
    apiurl = getattr(args, "apiurl", None) or ""
    if not apiurl:
        raise SystemExit(
            "error: EXPECTED_VERSIONS needs an OBS connection (-P profile or -A apiurl)"
        )
    return _VersionLookup(
        apiurl=apiurl,
        rootprj=args.rootprj,
        fallback_rootprj=getattr(args, "image_fallback_rootprj", None) or None,
        mirror=_mirror_source(project),
    )


def _own_package_versions(structure_id: str, lookup: _VersionLookup) -> dict[str, str]:
    """OBS-built upstream version of each direct package of *structure_id*
    (a local project; image and tarball recipes are not candidates)."""
    versions: dict[str, str] = {}
    for _, pkg_path in find_packages(
        resolve_project_path(structure_id), structure_id, recursive=False
    ):
        if _is_artifact_package(pkg_path):
            continue
        version = lookup.version(structure_id, pkg_path.name)
        if version:
            versions[pkg_path.name] = version
    return versions


def _package_versions(project: str, lookup: _VersionLookup) -> dict[str, str]:
    """Package versions for *project*'s EXPECTED_VERSIONS, as OBS built them.

    Selection as before: the project's own packages; a project without own
    versions, or one that builds images or tarballs, adds the packages of the
    projects its repositories build from (``subproject:`` paths), in path
    order, the first provider winning.  A release mirror has no package
    directories: its structure is the staging project it mirrors, its
    versions are read from the mirror's OBS projects.
    """
    structure = project
    if lookup.mirror is not None:
        release_top, staging_top = lookup.mirror
        structure = staging_top + project[len(release_top) :]
    own = _own_package_versions(structure, lookup)
    if own and not _builds_artifacts(structure):
        return own
    config = _load_project_config_with_inheritance(resolve_project_path(structure))
    sources: list[str] = []
    for repo in config.get("repositories", []) or []:
        for path_info in repo.get("paths", []) or []:
            sub = path_info.get("subproject") if isinstance(path_info, dict) else None
            if sub and sub != structure and sub not in sources:
                sources.append(sub)
    versions: dict[str, str] = dict(own)
    for sub in sources:
        if not resolve_project_path(sub).is_dir():
            continue
        for name, version in _own_package_versions(sub, lookup).items():
            versions.setdefault(name, version)
    return versions
```

Keep `_expected_versions` unchanged. In `_with_expected_versions`: drop the `versions is None` → `_package_versions(project)` default (make `versions` a required `dict[str, str]` argument) and read the entry scope from `entry.get("package")` instead of `entry.get("_package")`; update its docstring (`package:` key, values from OBS). Replace `_lanes_with_expected_versions`:

```python
def _lanes_with_expected_versions(
    lanes: list[Lane], project: str, lookup: _VersionLookup
) -> list[Lane]:
    """Apply :func:`_with_expected_versions` to every lane (versions read from
    OBS once).  A version conflict aborts; packages left without a version are
    named in one warning."""
    if not lanes:
        return lanes
    try:
        versions = _package_versions(project, lookup)
    except VersionConflict as exc:
        raise SystemExit(f"error: {exc}")
    if lookup.missing:
        print(
            "warning: no OBS binaries for: "
            + ", ".join(sorted(lookup.missing))
            + " — left out of EXPECTED_VERSIONS",
            file=sys.stderr,
        )
    return [
        Lane(
            lane.package,
            _with_expected_versions(lane.entries, project, lane.package, versions)
            or lane.entries,
        )
        for lane in lanes
    ]
```

In `cmd_qa_show` replace `lanes = _lanes_with_expected_versions(lanes, args.project)` with:

```python
    if getattr(args, "expected_versions", False):
        lanes = _lanes_with_expected_versions(
            lanes, args.project, _version_lookup(args, args.project)
        )
```

In `cmd_qa_run` replace the same line with:

```python
    lanes = _lanes_with_expected_versions(
        lanes, args.project, _version_lookup(args, args.project)
    )
```

Check every other caller of `_with_expected_versions` / `_package_versions` / `_lanes_with_expected_versions` (`grep -rn` in `percona_obs/`): `cmd_project._mirror_qa_entries` is changed in Task 3 — until then make it compile by leaving its call in place only if the signature still matches; otherwise do Task 3's removal of that block in this task too and note it in the report.

- [ ] **Step 4: Add the CLI flag** in `percona_obs/cli.py` after the `qa show --json` argument:

```python
    qa_show_parser.add_argument(
        "--expected-versions",
        dest="expected_versions",
        action="store_true",
        default=False,
        help="Also compute EXPECTED_VERSIONS from the binaries OBS built "
        "(needs an OBS connection). qa run always computes them.",
    )
```

- [ ] **Step 5: Run tests, black, pyright**

Run: `venv/bin/black percona_obs/cmd_qa.py percona_obs/cli.py tests/test_qa_expected_versions.py tests/test_version_from_set_version.py && venv/bin/pyright && venv/bin/pytest -q`
Expected: all pass, 0 errors. Fix any other test that relied on `qa show` adding `EXPECTED_VERSIONS` by default (pass `expected_versions=True` and mock `project_binary_versions`).

- [ ] **Step 6: Commit**

```bash
git add percona_obs/cmd_qa.py percona_obs/cli.py tests/
git commit -s -m "qa: EXPECTED_VERSIONS from the binaries OBS built

qa run reads each package's version from the OBS project under test
(one binarylist per project) instead of parsing obs/_service. The
upstream version must agree across the instance's repositories, else the
run fails before any trigger; packages without binaries are named in one
warning. PR lanes read packages absent from the PR project from the
fallback root; release mirrors use their staging source's structure and
read versions from the pre-release. qa show computes them only with
--expected-versions, so the CI matrix step stays off OBS. Mirror package
lanes are scoped by a package: key."
```

```json:metadata
{"files": ["percona_obs/cmd_qa.py", "percona_obs/cli.py", "tests/test_qa_expected_versions.py", "tests/test_version_from_set_version.py", "tests/test_qa_package_lanes.py"], "verifyCommand": "venv/bin/pytest -q && venv/bin/pyright", "acceptanceCriteria": ["selection rule kept; versions via project_binary_versions + agreed_version", "release mirror structure from its staging source, versions from the mirror's OBS ids; ids outside the staging top unchanged", "fallback root only for absent packages of non-translated projects; present-without-binaries never falls back", "artifact recipe packages are not candidates; one warning line names packages without binaries", "VersionConflict exits with error before any Jenkins trigger", "qa show: no OBS request without --expected-versions; qa run without apiurl errors", "package: key scopes an entry and must be a non-empty string; explicit EXPECTED_VERSIONS unchanged", "cmd_qa no longer calls _extract_version_from_service"], "modelTier": "standard"}
```

---

### Task 3: `project release` stops baking `EXPECTED_VERSIONS`

**Goal:** Release-mirror `qa:` entries no longer carry computed `EXPECTED_VERSIONS`; copied package lanes carry `package: <name>`.

**Files:**
- Modify: `percona_obs/cmd_project.py` (`_mirror_qa_entries`, ~lines 1775–1850)
- Test: `tests/test_project_release.py` (tests at ~786, ~1020, ~1053, ~1075)

**Acceptance Criteria:**
- [ ] `_mirror_qa_entries` output has no `EXPECTED_VERSIONS` unless the source entry declared it.
- [ ] Each copied package lane is `{"name": "<pkg>.<segment>", "package": "<pkg>", ...}`; project entries have no `package` key.
- [ ] `_mirror_qa_entries` no longer imports `_package_versions`/`_expected_versions` from `cmd_qa`; the `lane_packages` parallel list is gone.

**Verify:** `venv/bin/pytest -q tests/test_project_release.py && venv/bin/pytest -q && venv/bin/pyright` → all pass, 0 errors.

**Steps:**

- [ ] **Step 1: Update the tests** — replace `test_mirror_qa_entries_bake_expected_versions` and `test_mirror_qa_entries_without_versions_add_nothing` with:

```python
def test_mirror_qa_entries_do_not_bake_expected_versions(tmp_path, monkeypatch):
    import percona_obs.common as common
    from percona_obs.cmd_project import _mirror_qa_entries

    src = _staging_tree(tmp_path)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    monkeypatch.setattr(common, "REPO_ROOT", tmp_path / "root")
    _pkg_with_qa(
        src,
        "percona-pg_tde",
        "qa:\n  - name: pg_tde\n    pipeline: p\n    parameters:\n      A: 1\n",
    )
    cfg = {"qa": [{"name": "server", "pipeline": "p", "parameters": {"A": "x"}}]}
    out = _mirror_qa_entries(cfg, src, "ppg:staging:17", "ppg:staging:17", "ppg:releases:17")
    assert all("EXPECTED_VERSIONS" not in e["parameters"] for e in out)
    assert "package" not in out[0]
    assert out[1]["name"] == "percona-pg_tde.pg_tde"
    assert out[1]["package"] == "percona-pg_tde"
```

Keep `test_mirror_qa_entries_keep_explicit_expected_versions` (an entry that declares the parameter keeps it). In `test_mirror_qa_entries_appends_package_lanes` (and any other test asserting the exact copied entry dict) add the expected `"package": "<pkg>"` key. Adapt helper calls (`_pkg_with_qa(..., version=...)`) only if a `version` argument is now unused; leave the helper otherwise.

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_project_release.py -k mirror_qa`
Expected: FAIL (`package` key missing, `EXPECTED_VERSIONS` still baked).

- [ ] **Step 3: Implement** — in `_mirror_qa_entries`: remove `lane_packages` and the whole bake block (the local import of `EXPECTED_VERSIONS_PARAM, _expected_versions, _package_versions` and the `versions = ...` loop); keep the local import of `_normalise_qa_block`. The package-lane append becomes:

```python
            entries.append(
                {"name": f"{pkg_path.name}.{segment}", "package": pkg_path.name, **copied}
            )
```

Update the docstring: the copied lane names its package with `package:` so `qa run` gives it only that package's `EXPECTED_VERSIONS`; versions are not baked (computed at `qa run` from the pre-release).

- [ ] **Step 4: Run tests, black, pyright**

Run: `venv/bin/black percona_obs/cmd_project.py tests/test_project_release.py && venv/bin/pyright && venv/bin/pytest -q`
Expected: all pass, 0 errors.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/cmd_project.py tests/test_project_release.py
git commit -s -m "project release: stop baking EXPECTED_VERSIONS into mirrors

qa run now reads versions from the pre-release on OBS, so the cut no
longer writes them into the release mirror qa: entries. Copied package
lanes carry package: <name> so qa run still gives them only their own
package's line."
```

```json:metadata
{"files": ["percona_obs/cmd_project.py", "tests/test_project_release.py"], "verifyCommand": "venv/bin/pytest -q && venv/bin/pyright", "acceptanceCriteria": ["no computed EXPECTED_VERSIONS in mirror entries; declared ones kept", "copied package lanes carry package: <pkg>; project entries do not", "no cmd_qa version imports or lane_packages list left in _mirror_qa_entries"], "modelTier": "mechanical"}
```

---

### Task 4: `project versions --online` uses the batch fetch

**Goal:** Package rows of `project versions --online` (normal and release projects) come from `project_binary_versions`, printing the first sorted repository's versrel and warning when the upstream part disagrees.

**Files:**
- Modify: `percona_obs/cmd_project.py` (`cmd_project_versions` online branch ~lines 1545–1630; `_fill_release_online_records` ~lines 284–345)
- Test: `tests/test_versions_online.py`

**Acceptance Criteria:**
- [ ] Normal projects: a package row's version is `first_versrel` of its source project's per-repo map (aggregates: source project first, then the aggregating project); one `binarylist` request per OBS project; `_versrel_from_any_repo` is no longer used for package rows.
- [ ] Release projects: package rows use the same batch data; image rows keep containerinfo, history and the container package list.
- [ ] Disagreeing upstream versions log a warning `<pkg>: OBS builds disagree on the version: ...` and the row still prints the first sorted versrel.
- [ ] No version found keeps today's warning text (`<pkg>: no version found: ...`) and a `None` version.
- [ ] Output format (YAML and `--markdown`) unchanged.

**Verify:** `venv/bin/pytest -q tests/test_versions_online.py && venv/bin/pytest -q && venv/bin/pyright` → all pass, 0 errors.

**Steps:**

- [ ] **Step 1: Rewrite `tests/test_versions_online.py`'s fixture** to mock `cmd_project.project_binary_versions` (dict keyed by OBS project, same shape as Task 1) instead of `_fetch_build_results` + `_fetch_pkg_versrel` for package rows; keep its existing scenarios (aggregate source, next repository when the first has no readable binary → now "first sorted repository with a binary", aggregating project fallback, nothing found explained, API errors reported) and add:

```python
def test_first_sorted_versrel_and_conflict_warning(monkeypatch, capsys, caplog):
    data = {
        "isv:percona:ppg:staging:18": {
            "percona-pgbackrest": {
                ("RockyLinux_9", "x86_64"): "2.60.0-1.1",
                ("Debian_12", "x86_64"): "2.59.2-1",
            }
        }
    }
    calls = []
    monkeypatch.setattr(
        cmd_project,
        "project_binary_versions",
        lambda apiurl, prj, rf=None: calls.append(prj) or data.get(prj),
    )
    # invoke cmd_project_versions for ppg:staging:18 percona-pgbackrest --online
    # through the module's existing args helper; then:
    # assert the printed version is "2.59.2-1" (Debian_12 sorts first)
    # assert "OBS builds disagree" in caplog.text
    # assert calls.count("isv:percona:ppg:staging:18") == 1
```

Fill in the invocation with the file's existing helper (it already builds args for `cmd_project_versions`); keep the three asserts as written.

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest -q tests/test_versions_online.py`
Expected: FAIL.

- [ ] **Step 3: Implement** — in `cmd_project.py` import `from .obs_versions import VersionConflict, agreed_version, first_versrel, project_binary_versions`. Add a helper:

```python
def _online_versrel(apiurl: str, obs_project: str, package: str) -> "str | None":
    """versrel of *package* in *obs_project* from the batch binary list:
    the first sorted repository's, with a warning when repositories
    disagree on the upstream version."""
    data = project_binary_versions(apiurl, obs_project, get_default_repository_filter())
    per_repo = (data or {}).get(package) or {}
    if not per_repo:
        return None
    try:
        agreed_version(package, per_repo)
    except VersionConflict as exc:
        logger.warning(str(exc))
    return first_versrel(per_repo)
```

In the normal online branch, for `record["type"] == "package"` replace both `_versrel_from_any_repo(...)` calls with `_online_versrel(apiurl, obs_proj, pkg_name)` and `_online_versrel(apiurl, target, name)`; the `succeeded_in` cache stays for image rows only. In `_fill_release_online_records._collect`, for packages that are not images (`_detect_obs_container_info(...) is None`) use `_online_versrel(apiurl, obs_proj, pkg_name)`; keep `_versrel` (binary listing, then history) for image rows. Remove `_versrel_from_any_repo` if nothing uses it any more (`grep -rn _versrel_from_any_repo percona_obs tests`).

- [ ] **Step 4: Run tests, black, pyright**

Run: `venv/bin/black percona_obs/cmd_project.py tests/test_versions_online.py && venv/bin/pyright && venv/bin/pytest -q`
Expected: all pass, 0 errors.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/cmd_project.py tests/test_versions_online.py
git commit -s -m "project versions --online: package rows from the batch binary list

One binarylist request per OBS project replaces build results plus
per-package, per-repository binary listings. Rows keep printing a full
versrel, now from the first repository in sorted order, and warn when
repositories disagree on the upstream version. Image rows are unchanged."
```

```json:metadata
{"files": ["percona_obs/cmd_project.py", "tests/test_versions_online.py"], "verifyCommand": "venv/bin/pytest -q && venv/bin/pyright", "acceptanceCriteria": ["normal projects: package rows via first_versrel of the batch data, aggregate source then aggregating project, one request per project", "release projects: package rows from batch data, image rows unchanged", "upstream disagreement logs the VersionConflict message and still prints the first sorted versrel", "no-version warning text and None kept", "YAML and markdown output unchanged"], "modelTier": "standard"}
```

---

### Task 5: Docs

**Goal:** The tool reference, architecture reference and two-hop spec describe OBS-sourced `EXPECTED_VERSIONS`, the agreement rule, `qa show --expected-versions`, the `package:` key and the end of cut-time baking.

**Files:**
- Modify: `docs/PERCONA_OBS_TOOL.md` (section `#### EXPECTED_VERSIONS (added automatically)` ~line 854; the "Releasing packages" step about the qa: carry-over; `project versions --online` description)
- Modify: `.github/copilot-instructions.md` (qa / EXPECTED_VERSIONS paragraph)
- Modify: `docs/superpowers/specs/2026-10-13-prerelease-project-release-flow-design.md` (§2 "QA blocks in mirrors")

**Acceptance Criteria:**
- [ ] `PERCONA_OBS_TOOL.md` states: values come from the binaries OBS built in the project under test at `qa run`; upstream version without release; repositories must agree (error before any trigger); one warning for packages without binaries; PR fallback for absent packages only; release mirrors read the pre-release with their staging source's structure; `qa show` computes only with `--expected-versions`; `package:` key; an entry's own `EXPECTED_VERSIONS` wins.
- [ ] No doc still says `project release` bakes `EXPECTED_VERSIONS` (`grep -rn "bake" docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md` shows no EXPECTED_VERSIONS baking claim).
- [ ] `project versions --online` doc: one request per project, first sorted repository's versrel, warning on disagreement.

**Verify:** `grep -n "expected-versions" docs/PERCONA_OBS_TOOL.md` → at least one hit; `grep -rn "EXPECTED_VERSIONS" docs/PERCONA_OBS_TOOL.md | grep -i bake` → no hit.

**Steps:**

- [ ] **Step 1:** Rewrite the `EXPECTED_VERSIONS` section of `docs/PERCONA_OBS_TOOL.md` with the facts listed in the acceptance criteria (one short paragraph each, plus the conflict error line from the spec as a code block).
- [ ] **Step 2:** In the releasing steps, replace the sentence about `project release` baking `EXPECTED_VERSIONS` into mirror `qa:` entries with: copied package lanes get `name: <pkg>.<segment>` and `package: <pkg>`; versions are computed at `qa run` from the pre-release.
- [ ] **Step 3:** Update the `project versions --online` description.
- [ ] **Step 4:** Same facts, two sentences, in `.github/copilot-instructions.md`; one sentence in the two-hop spec §2 ("Mirrors carry no baked `EXPECTED_VERSIONS` since 2026-10-20; `qa run` reads them from the pre-release.").
- [ ] **Step 5: Commit**

```bash
git add docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md docs/superpowers/specs/2026-10-13-prerelease-project-release-flow-design.md
git commit -s -m "docs: EXPECTED_VERSIONS and project versions --online read OBS builds"
```

```json:metadata
{"files": ["docs/PERCONA_OBS_TOOL.md", ".github/copilot-instructions.md", "docs/superpowers/specs/2026-10-13-prerelease-project-release-flow-design.md"], "verifyCommand": "grep -n 'expected-versions' docs/PERCONA_OBS_TOOL.md && ! (grep -rn 'EXPECTED_VERSIONS' docs/PERCONA_OBS_TOOL.md | grep -i bake)", "acceptanceCriteria": ["tool reference states the OBS source, upstream normalisation, agreement error, warning, PR fallback rule, mirror structure rule, qa show flag, package: key, entry value wins", "no doc claims project release bakes EXPECTED_VERSIONS", "project versions --online doc updated"], "modelTier": "mechanical"}
```

---

### Task 6: Live read-only check against both OBS instances

**Goal:** Confirm on real OBS data that `EXPECTED_VERSIONS` resolves without conflicts and includes `percona-pgbackrest=2.60.0`, and compare it with the values the local `_service` parser produced on `main`.

**Files:**
- none (read-only commands; outputs in the scratchpad)

**Acceptance Criteria:**
- [ ] `percona-obs -P isv qa show ppg:staging:18 --expected-versions --json` exits 0, and its `EXPECTED_VERSIONS` contains `percona-pgbackrest=2.60.0`.
- [ ] `percona-obs -P labsmain qa show ppg:staging:18:containers --expected-versions --json` exits 0 with `percona-pgbackrest=2.60.0` and no `OBS builds disagree` error.
- [ ] The same two commands on `ppg:staging:17` / `ppg:staging:17:containers` exit 0.
- [ ] A per-project diff of the new values against `main`'s `qa show --json` values (run from the primary checkout on `percona/main`) is written to the scratchpad and every differing line is explained in the report (expected: only release-suffix-free equal values, plus packages the old parser missed).

**Verify:** the four commands above exit 0; `grep -c "percona-pgbackrest=2.60.0"` on each JSON output ≥ 1.

**Steps:**

- [ ] **Step 1:** From the worktree run the four `qa show --expected-versions --json` commands, saving each to `/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/5244095d-a3b2-4289-9da0-2b4300684346/scratchpad/obsver/<profile>_<project>.json`.
- [ ] **Step 2:** From `/home/rdias/Work/percona-obs-packaging` on a detached `percona/main` checkout in a temporary worktree, run the same four `qa show --json` (old behaviour) into `.../obsver/main_<profile>_<project>.json`.
- [ ] **Step 3:** Diff the `EXPECTED_VERSIONS` line sets per lane and record every difference with its cause. A `VersionConflict` is a real finding: report the package and per-repo values (it is either a packaging bug or a normalisation case the plan missed); do not paper over it.
- [ ] **Step 4:** Remove the temporary worktree.

```json:metadata
{"files": [], "verifyCommand": "venv/bin/python -m percona_obs -P isv qa show ppg:staging:18 --expected-versions --json | grep -c 'percona-pgbackrest=2.60.0'", "acceptanceCriteria": ["isv ppg:staging:18 exits 0 with percona-pgbackrest=2.60.0", "labsmain ppg:staging:18:containers exits 0 with percona-pgbackrest=2.60.0 and no conflict", "the 17 equivalents exit 0", "diff vs main's local-parser values recorded and every difference explained"], "modelTier": "standard"}
```
