# Dep-Cascade Provider Resolution Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `sync push --branch-from` dep-cascade misattributing build-dep edges across same-major tier projects (devel:18 / staging:18 / staging:18:extras), which caused 35 spurious promotions of `ppg:staging:18*` packages in PR #139 and can equally cause silently *missed* rebuilds with the opposite (hash-seed-dependent) project iteration order.

**Architecture:** `_fetch_combined_depinfo()` in `percona_obs/obs_api.py` currently merges all queried projects' binaries into one flat `provided_by[binary] → (project, src)` dict — last write wins, so identical binary names built in multiple tiers (e.g. `percona-postgresql18-devel` in devel:18, staging:18 AND staging:18:extras) get attributed to an arbitrary project. The fix mirrors OBS's own build-environment resolution: keep providers **per project**, fetch each queried repo's `<path>` chain from project `_meta`, and resolve each consumer's dep **own-project-first, then path-chain order**, with a unique-global-provider fallback and drop-with-debug-log for ambiguous leftovers. `_fetch_image_pkg_deps()` (container Dockerfile bdeps) uses the same flat map and gets the same treatment.

**Tech Stack:** Python 3.13, `osc` library (OBS API), `xml.etree.ElementTree`, pytest (new dev dep — first tests in this repo), black + pyright (existing mandatory tooling).

**User decisions (already made):**
- Root cause confirmed 2026-07-13 by investigation of PR #139 CI logs + live `_builddepinfo`/`_meta` queries on api.opensuse.org; user asked for this plan. See memory `dep-cascade-provided-by-collision`.
- Repo rule: `git commit -s`, no Claude attribution, never push / create PRs without asking.
- api.opensuse.org (`isv:percona`) is PRODUCTION: read-only GETs are allowed, any write requires `--dry-run`.

---

## Grounding facts (verified live, 2026-07-13)

An implementer needs these to understand the fixture data and assertions:

- `isv:percona:ppg:devel:18`, `isv:percona:ppg:staging:18`, and `isv:percona:ppg:staging:18:extras` **each build their own `percona-postgresql`** source package producing byte-identical binary names (`percona-postgresql18`, `percona-postgresql18-devel`, …). Same for `percona-pg_oidc_validator` (devel:18 + staging:18).
- Repo path chains (from `_meta`, first-level `<path>` elements, verified):
  - `devel:18` (any repo): `[staging:18, ppg:common:deps, common:deps:build, <distro>]` — devel layers ON staging.
  - `staging:18`: `[ppg:common:deps, common:deps:build, <distro>]` — staging never sees devel.
  - `staging:18:extras` `UBI_9`: `[ppg:common:deps, common:deps:build, staging:18, <distro…>]`.
  - `staging:18:containers:ubi9` `images`: `[containers:ubi9(UBI_9 repo), staging:18, staging:17, ppg:common:deps, common:containers:ubi9…]`.
- Therefore for every observed consumer, own-project-first + one level of path-chain lookup yields the correct provider. Cross-instance/remote paths may be missing from the queried set → unique-global fallback covers those.
- The buggy behavior is nondeterministic: `branch_projects` is a `set[str]`, iteration order varies with `PYTHONHASHSEED`.
- OBS `_builddepinfo` `<package>` elements carry `project="..."` only for entries inherited via path targets; the existing code already skips those (obs_api.py:565-567) — keep that logic.
- Existing codebase idiom for fetching project meta as `str`: `_decode_obs_response(osc.core.show_project_meta(apiurl, project))` (see obs_api.py:778).
- `tmp/` is gitignored — use it for the live-verification script and evidence.
- pyright runs in basic mode over `percona_obs/` only; tests are not type-checked.

---

### Task 1: Provider-resolution helpers with unit tests

**Goal:** Add two pure, unit-testable functions to `percona_obs/obs_api.py` — `_resolve_provider` (own-project-first / path-chain / unique-fallback resolution) and `_parse_repo_path_projects` (extract a repo's `<path>` projects from `_meta` XML) — plus one thin HTTP wrapper `_fetch_repo_path_projects`, with pytest coverage reproducing the PR #139 collision.

**Files:**
- Modify: `percona_obs/obs_api.py` (insert new functions immediately above `_fetch_image_pkg_deps`, currently line 446)
- Modify: `requirements.txt` (add `pytest` under development tools)
- Create: `tests/test_provider_resolution.py`

**Acceptance Criteria:**
- [ ] `_resolve_provider` returns the consumer's own project's provider even when a sibling tier provides the same binary name
- [ ] Path-chain lookup resolves consumers that build nothing themselves (container projects) to the chain project, never a sibling tier
- [ ] Unique-global fallback works; ambiguous unresolvable binaries return `None`
- [ ] Resolution result is independent of provider-map insertion order (the nondeterminism regression test)
- [ ] `_parse_repo_path_projects` preserves document order, dedups, returns `[]` for missing repo / unparseable XML
- [ ] `venv/bin/pytest tests/ -v` passes; `venv/bin/black percona_obs/` and `venv/bin/pyright` clean

**Verify:** `venv/bin/pytest tests/ -v` → 7 passed

**Steps:**

- [ ] **Step 1: Install pytest and record it**

Run: `venv/bin/pip install pytest`

In `requirements.txt`, change the dev-tools block to:

```
# development tools
black
pyright
pytest
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_provider_resolution.py`:

```python
"""Unit tests for OBS dep-cascade provider resolution (percona_obs.obs_api).

Reproduces the PR #139 bug: ppg:devel:18, ppg:staging:18 and
ppg:staging:18:extras all build percona-postgresql with identical binary
names; the resolver must attribute each consumer's dep edge to the tier its
build environment actually uses (own project first, then repo path chain),
regardless of project iteration order.
"""

from percona_obs.obs_api import _parse_repo_path_projects, _resolve_provider

DEVEL = "isv:percona:ppg:devel:18"
STAGING = "isv:percona:ppg:staging:18"
EXTRAS = "isv:percona:ppg:staging:18:extras"
UBI9 = "isv:percona:ppg:staging:18:containers:ubi9"
DEPS = "isv:percona:ppg:common:deps"

PG_DEVEL_BIN = "percona-postgresql18-devel"
OIDC_BIN = "percona-pg_oidc_validator18"


def _providers():
    return {
        DEVEL: {
            PG_DEVEL_BIN: (DEVEL, "percona-postgresql"),
            OIDC_BIN: (DEVEL, "percona-pg_oidc_validator"),
        },
        STAGING: {
            PG_DEVEL_BIN: (STAGING, "percona-postgresql"),
            OIDC_BIN: (STAGING, "percona-pg_oidc_validator"),
        },
        EXTRAS: {
            PG_DEVEL_BIN: (EXTRAS, "percona-postgresql"),
        },
        DEPS: {
            "etcd": (DEPS, "etcd"),
        },
    }


def _globals(providers):
    out = {}
    for provider_map in providers.values():
        for binary, provider in provider_map.items():
            out.setdefault(binary, set()).add(provider)
    return out


# First-level <path> chains as verified on api.opensuse.org (2026-07-13).
CHAINS = {
    DEVEL: [STAGING, DEPS],
    STAGING: [DEPS],
    EXTRAS: [DEPS, STAGING],
    UBI9: [UBI9, STAGING, DEPS],
}


def test_own_project_beats_sibling_tier():
    providers = _providers()
    assert _resolve_provider(
        STAGING, PG_DEVEL_BIN, providers, CHAINS[STAGING], _globals(providers)
    ) == (STAGING, "percona-postgresql")


def test_devel_consumer_resolves_to_devel():
    # devel:18 paths into staging:18, but its own project must win.
    providers = _providers()
    assert _resolve_provider(
        DEVEL, PG_DEVEL_BIN, providers, CHAINS[DEVEL], _globals(providers)
    ) == (DEVEL, "percona-postgresql")


def test_container_resolves_via_path_chain_not_sibling():
    # containers:ubi9 builds no RPMs itself; its images repo paths into
    # staging:18 — a devel:18 provider must never be chosen.
    providers = _providers()
    assert _resolve_provider(
        UBI9, OIDC_BIN, providers, CHAINS[UBI9], _globals(providers)
    ) == (STAGING, "percona-pg_oidc_validator")


def test_unique_global_provider_fallback():
    # Binary provided by exactly one queried project resolves even with an
    # empty/incomplete path chain.
    providers = _providers()
    assert _resolve_provider(UBI9, "etcd", providers, [], _globals(providers)) == (
        DEPS,
        "etcd",
    )


def test_ambiguous_binary_outside_chain_is_dropped():
    # Multiple providers, none visible through the consumer's chain: the
    # edge must be dropped (None), not guessed.
    providers = _providers()
    assert (
        _resolve_provider(DEPS, PG_DEVEL_BIN, providers, [], _globals(providers))
        is None
    )


def test_resolution_independent_of_insertion_order():
    # The old flat provided_by dict was last-write-wins over set iteration
    # order (PYTHONHASHSEED-dependent).  The resolver must give the same
    # answer for any insertion order.
    providers = _providers()
    reordered = dict(reversed(list(providers.items())))
    for candidate in (providers, reordered):
        assert _resolve_provider(
            STAGING, PG_DEVEL_BIN, candidate, CHAINS[STAGING], _globals(candidate)
        ) == (STAGING, "percona-postgresql")


META_XML = """\
<project name="isv:percona:ppg:staging:18:extras">
  <repository name="UBI_9">
    <path project="isv:percona:ppg:common:deps" repository="UBI_9"/>
    <path project="isv:percona:common:deps:build" repository="UBI_9"/>
    <path project="isv:percona:ppg:staging:18" repository="UBI_9"/>
    <path project="RedHat:UBI-9" repository="standard"/>
    <arch>x86_64</arch>
  </repository>
  <repository name="Debian_13">
    <path project="isv:percona:ppg:staging:18" repository="Debian_13"/>
  </repository>
</project>
"""


def test_parse_repo_path_projects():
    assert _parse_repo_path_projects(META_XML, "UBI_9") == [
        "isv:percona:ppg:common:deps",
        "isv:percona:common:deps:build",
        "isv:percona:ppg:staging:18",
        "RedHat:UBI-9",
    ]
    assert _parse_repo_path_projects(META_XML, "Debian_13") == [
        "isv:percona:ppg:staging:18"
    ]
    assert _parse_repo_path_projects(META_XML, "missing") == []
    assert _parse_repo_path_projects("not xml <", "UBI_9") == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `venv/bin/pytest tests/ -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_provider'`

- [ ] **Step 4: Implement the helpers**

In `percona_obs/obs_api.py`, insert immediately above `def _fetch_image_pkg_deps` (line 446):

```python
def _resolve_provider(
    consumer_project: str,
    binary: str,
    providers_by_project: dict[str, dict[str, tuple[str, str]]],
    path_chain: list[str],
    global_providers: dict[str, set[tuple[str, str]]],
) -> "tuple[str, str] | None":
    """Resolve *binary* to the (project, source_pkg) providing it for a
    consumer that builds in *consumer_project*.

    Mirrors OBS build-environment resolution: the consumer's own project is
    searched first, then the ``<path>`` projects of the repository whose
    builddepinfo was queried, in document order.  This keeps same-named
    binaries built in multiple sibling projects (e.g. percona-postgresql18-*
    in both ppg:devel:18 and ppg:staging:18) attributed to the correct tier;
    a flat merged map was last-write-wins over set iteration order, causing
    spurious cross-tier dep-promotions (or, with the opposite order,
    silently missed rebuilds).

    Falls back to the unique provider when exactly one queried project
    provides the binary (path data may be incomplete, e.g. remote
    interconnect paths).  Ambiguous binaries not visible through the
    consumer's path chain are dropped with a debug log rather than guessed.
    """
    for candidate_project in (consumer_project, *path_chain):
        provider = providers_by_project.get(candidate_project, {}).get(binary)
        if provider is not None:
            return provider
    candidates = global_providers.get(binary, set())
    if len(candidates) == 1:
        return next(iter(candidates))
    if candidates:
        logger.debug(
            f"_resolve_provider: ambiguous providers for {binary!r} from"
            f" {consumer_project!r} (none in path chain): {sorted(candidates)}"
        )
    return None


def _parse_repo_path_projects(meta_xml: str, repo_name: str) -> list[str]:
    """Return the ordered ``<path project="...">`` names of *repo_name*.

    Parses a project ``_meta`` document and extracts the path projects of
    the ``<repository>`` element matching *repo_name*, preserving document
    order and dropping duplicates.  Returns ``[]`` when the repository is
    absent or the XML does not parse.
    """
    try:
        root = ET.fromstring(meta_xml)
    except ET.ParseError:
        return []
    for repo_elem in root.findall("repository"):
        if repo_elem.get("name") != repo_name:
            continue
        chain: list[str] = []
        for path_elem in repo_elem.findall("path"):
            path_project = path_elem.get("project", "")
            if path_project and path_project not in chain:
                chain.append(path_project)
        return chain
    return []


def _fetch_repo_path_projects(
    apiurl: str, obs_project: str, repo_name: str
) -> list[str]:
    """Fetch *obs_project*'s ``_meta`` and return *repo_name*'s path projects.

    Returns ``[]`` on any fetch error — the resolver then falls back to
    own-project and unique-provider resolution only.
    """
    try:
        raw = _decode_obs_response(osc.core.show_project_meta(apiurl, obs_project))
    except Exception as exc:
        logger.debug(
            f"_fetch_repo_path_projects: error fetching {obs_project!r}: {exc}"
        )
        return []
    return _parse_repo_path_projects(raw, repo_name)
```

(`ET`, `osc.core`, `_decode_obs_response`, and `logger` are already imported at the top of `obs_api.py` — no import changes needed.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/ -v`
Expected: 7 passed

- [ ] **Step 6: Format, type-check, commit**

```bash
venv/bin/black percona_obs/
venv/bin/pyright
git add percona_obs/obs_api.py tests/test_provider_resolution.py requirements.txt
git commit -s -m "obs_api: add project-aware build-dep provider resolution helpers"
```

Expected: black "left unchanged" or reformats cleanly; pyright "0 errors".

---

### Task 2: Rewire `_fetch_combined_depinfo` and `_fetch_image_pkg_deps`

**Goal:** Replace the flat last-write-wins `provided_by` map with per-project provider maps + path chains, resolving every dep edge through `_resolve_provider` — for both RPM/deb consumers (`pkgdep`) and container image consumers (`bdep`).

**Files:**
- Modify: `percona_obs/obs_api.py:446-491` (`_fetch_image_pkg_deps`) and `percona_obs/obs_api.py:494-608` (`_fetch_combined_depinfo`) — line numbers pre-Task-1; both functions are replaced wholesale
- Modify: `.github/copilot-instructions.md` (dep-promote debugging section, ~line 870)

**Acceptance Criteria:**
- [ ] `_fetch_combined_depinfo` builds `providers_by_project` (per-project) instead of one flat dict, fetches each queried project's path chain once, and resolves every `pkgdep` via `_resolve_provider`
- [ ] `_fetch_image_pkg_deps` takes the resolution maps + the image project's chain instead of a flat `provided_by` dict; chain for `(project, repo)` pairs not already queried is fetched lazily
- [ ] Function signatures/callers consistent — `_fetch_combined_depinfo`'s public signature is unchanged, so `cmd_sync.py` needs no edits
- [ ] `venv/bin/pytest tests/ -v` still passes; black + pyright clean

**Verify:** `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest tests/ -v` → 0 errors, 7 passed

**Steps:**

- [ ] **Step 1: Replace `_fetch_image_pkg_deps`**

Replace the whole function (docstring included) with:

```python
def _fetch_image_pkg_deps(
    apiurl: str,
    branch_project: str,
    repo: str,
    arch: str,
    pkg_name: str,
    providers_by_project: dict[str, dict[str, tuple[str, str]]],
    path_chain: list[str],
    global_providers: dict[str, set[tuple[str, str]]],
    local_pkg_set: set[tuple[str, str]],
) -> set[tuple[str, str]]:
    """Return local source packages a Dockerfile image depends on, via _buildinfo.

    OBS's project-level _builddepinfo does not expose the RPM packages parsed
    by Build::Docker from the Dockerfile's RUN dnf/zypper/apt/apk install
    blocks — only the FROM base container shows up.  The per-package _buildinfo
    endpoint does include them, as <bdep name="..."/> entries.  Each bdep name
    is resolved to its providing (home_project, source_pkg) with
    _resolve_provider, searching the image project itself and then *path_chain*
    (the <path> projects of the image's repository) so that same-named
    binaries built in multiple sibling projects are attributed to the tier the
    image actually pulls from.
    """
    try:
        url = osc.core.makeurl(
            apiurl, ["build", branch_project, repo, arch, pkg_name, "_buildinfo"]
        )
        root = ET.fromstring(osc.connection.http_GET(url).read())
    except Exception as exc:
        logger.debug(
            f"_fetch_image_pkg_deps: error fetching {branch_project}/{repo}/{arch}/{pkg_name}: {exc}"
        )
        return set()

    deps: set[tuple[str, str]] = set()
    for bdep in root.findall("bdep"):
        name = bdep.get("name", "")
        if not name:
            continue
        provider = _resolve_provider(
            branch_project, name, providers_by_project, path_chain, global_providers
        )
        if (
            provider
            and provider != (branch_project, pkg_name)
            and provider in local_pkg_set
        ):
            deps.add(provider)
    return deps
```

- [ ] **Step 2: Replace `_fetch_combined_depinfo`**

Replace the whole function (docstring included) with:

```python
def _fetch_combined_depinfo(
    apiurl: str,
    branch_projects: set[str],
    local_pkg_set: set[tuple[str, str]],
    image_pkgs: "dict[str, list[tuple[str, str, str]]] | None" = None,
) -> dict[tuple[str, str], set[tuple[str, str]]]:
    """Return a project-aware forward build-dependency map across OBS projects.

    Queries _builddepinfo for each project in branch_projects, records each
    project's provided binaries separately (binary → (home_project, source_pkg)
    per project), then builds a forward dep map:

        fwd_deps[(P, A)] = set of (Q, B) where source pkg A in project P
                           build-depends on a binary produced by source pkg
                           B in project Q.

    Each <pkgdep> is resolved with _resolve_provider: the consumer's own
    project first, then the <path> projects of the queried repository (from
    the project's _meta), then a unique-global-provider fallback.  This keeps
    same-named binaries built in multiple sibling projects (e.g.
    percona-postgresql18-* in ppg:devel:18, ppg:staging:18 AND
    ppg:staging:18:extras) attributed to the tier the consumer actually
    builds against — a flat merged map was last-write-wins over set
    iteration order and produced spurious (or missed) cross-tier
    dep-promotions.  Only first-level <path> projects are considered; OBS's
    transitive expansion of the last path is not modelled, the unique-global
    fallback covers providers reached that way.

    Edges are filtered to entries whose ``(project, name)`` tuple is in
    ``local_pkg_set`` (the producer side).

    OBS _builddepinfo for a project includes <package> entries inherited from
    <path> targets; those carry a ``project`` attribute pointing at their
    home project.  We only attribute a <package> element to the project we
    queried, skipping inherited entries — they are picked up directly when
    their home project is queried.

    Returns ``{}`` if no project has build results yet or on any error.

    ``image_pkgs`` optionally extends the map with Dockerfile-image → RPM
    edges that OBS omits from _builddepinfo.  It maps image pkg_name →
    list of (branch_project, repo, arch) to query per-package _buildinfo for.
    """
    # providers_by_project[P][binary] = (P, source_pkg) for binaries built
    # in P itself (inherited entries excluded).
    providers_by_project: dict[str, dict[str, tuple[str, str]]] = {}
    # path_chains[(P, repo)] = ordered <path> projects of P's repo, used as
    # the provider search order after P itself.
    path_chains: dict[tuple[str, str], list[str]] = {}
    # queried_repo[P] = the repository whose builddepinfo was fetched for P.
    queried_repo: dict[str, str] = {}
    # Each entry: (pkg_elem, home_project, src) where home_project is the
    # OBS project this <package> belongs to (the queried project, after
    # filtering out inherited entries).
    all_pkg_elems: list[tuple[ET.Element, str, str]] = []

    for obs_project in branch_projects:
        try:
            repo_url = osc.core.makeurl(apiurl, ["build", obs_project])
            repo_root = ET.fromstring(osc.connection.http_GET(repo_url).read())
            repos = [
                e.get("name", "") for e in repo_root.findall("entry") if e.get("name")
            ]
            if not repos:
                continue
            arch_url = osc.core.makeurl(apiurl, ["build", obs_project, repos[0]])
            arch_root = ET.fromstring(osc.connection.http_GET(arch_url).read())
            archs = [
                e.get("name", "") for e in arch_root.findall("entry") if e.get("name")
            ]
            if not archs:
                continue
            dep_url = osc.core.makeurl(
                apiurl, ["build", obs_project, repos[0], archs[0], "_builddepinfo"]
            )
            dep_root = ET.fromstring(osc.connection.http_GET(dep_url).read())
        except Exception as exc:
            logger.debug(
                f"_fetch_combined_depinfo: error fetching {obs_project}: {exc}"
            )
            continue

        queried_repo[obs_project] = repos[0]
        path_chains[(obs_project, repos[0])] = _fetch_repo_path_projects(
            apiurl, obs_project, repos[0]
        )

        for pkg_elem in dep_root.findall("package"):
            # Skip <package> entries inherited from path targets — they are
            # attributed to their home project when that project is queried,
            # not to the queried project here.
            elem_proj = pkg_elem.get("project", "")
            if elem_proj and elem_proj != obs_project:
                continue
            raw_src = pkg_elem.get("name", "")
            if not raw_src:
                continue
            # Strip multibuild flavor suffix (e.g. "pkg:flavor" → "pkg") so
            # that dep lookups always use the base package name.
            src = raw_src.split(":")[0]
            all_pkg_elems.append((pkg_elem, obs_project, src))
            project_providers = providers_by_project.setdefault(obs_project, {})
            for subpkg in pkg_elem.findall("subpkg"):
                binary = (subpkg.text or "").strip()
                if binary:
                    project_providers[binary] = (obs_project, src)

    # global_providers[binary] = every (project, src) building it — the
    # unambiguous fallback for binaries not visible through a consumer's
    # own project or path chain.
    global_providers: dict[str, set[tuple[str, str]]] = {}
    for project_providers in providers_by_project.values():
        for binary, provider in project_providers.items():
            global_providers.setdefault(binary, set()).add(provider)

    # Build forward dep map: fwd_deps[(P, A)] = {(Q, B), ...}.
    fwd_deps: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for pkg_elem, home_project, src in all_pkg_elems:
        if not src:
            continue
        src_key = (home_project, src)
        chain = path_chains.get((home_project, queried_repo.get(home_project, "")), [])
        for pkgdep in pkg_elem.findall("pkgdep"):
            binary = (pkgdep.text or "").strip()
            provider = _resolve_provider(
                home_project, binary, providers_by_project, chain, global_providers
            )
            if provider and provider != src_key and provider in local_pkg_set:
                fwd_deps.setdefault(src_key, set()).add(provider)

    # Enrich with Dockerfile-image → RPM edges from per-package _buildinfo.
    if image_pkgs:
        for pkg_name, entries in image_pkgs.items():
            for branch_project, repo, arch in entries:
                chain_key = (branch_project, repo)
                if chain_key not in path_chains:
                    path_chains[chain_key] = _fetch_repo_path_projects(
                        apiurl, branch_project, repo
                    )
                extra = _fetch_image_pkg_deps(
                    apiurl,
                    branch_project,
                    repo,
                    arch,
                    pkg_name,
                    providers_by_project,
                    path_chains[chain_key],
                    global_providers,
                    local_pkg_set,
                )
                if extra:
                    fwd_deps.setdefault((branch_project, pkg_name), set()).update(extra)

    return fwd_deps
```

Note: `_fetch_combined_depinfo`'s signature is unchanged, so `cmd_sync.py` (the only caller, two call sites at lines 836 and 871) needs no changes. `_fetch_image_pkg_deps` is only called from `_fetch_combined_depinfo` — no other callers exist.

- [ ] **Step 3: Update the debugging doc**

In `.github/copilot-instructions.md`, find the dep-promote debugging table (~line 870) and add one row after the `dep-promote: <pkg> promoted by dep on <other>` row:

```markdown
| `_resolve_provider: ambiguous providers for <binary>` | A dep edge was dropped: multiple projects build the binary and none is in the consumer's repo path chain |
```

And after the paragraph about `builddepinfo covers 0 local packages`, add:

```markdown
Dep edges attribute each binary to a provider by searching the consumer's own
project first, then the `<path>` projects of the queried repository (fetched
from the project `_meta`), then falling back to the unique provider across all
queried projects.  Same-named binaries in sibling tiers (devel vs staging of
the same PG major) are therefore never conflated.
```

- [ ] **Step 4: Format, type-check, test**

Run: `venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest tests/ -v`
Expected: black clean, pyright 0 errors, 7 passed

- [ ] **Step 5: Commit**

```bash
git add percona_obs/obs_api.py .github/copilot-instructions.md
git commit -s -m "obs_api: resolve dep-cascade providers via own project and repo path chain

The flat provided_by map merged binaries from all queried projects with
last-write-wins semantics.  Tier projects of the same PG major (devel:18,
staging:18, staging:18:extras) build identical binary names, so dep edges
were attributed to an arbitrary tier depending on set iteration order:
PR #139 (touching only ppg:devel:18) dep-promoted 35 ppg:staging:18*
packages; the opposite order would silently skip required rebuilds."
```

---

### Task 3: Live read-only verification against api.opensuse.org

**Goal:** Prove on real production data (read-only GETs) that the fixed dep map produces zero staging→devel cross-tier edges for any hash seed, while devel-internal cascade edges are preserved.

**Files:**
- Create: `tmp/verify_dep_resolution.py` (tmp/ is gitignored — evidence artifact, not committed)
- Create: `tmp/dep-resolution-evidence.txt` (captured output)

**Acceptance Criteria:**
- [ ] Script exits 0 for `PYTHONHASHSEED` values 0, 1, 2, 3, 42 (five runs)
- [ ] Every run reports 0 edges from a `staging:18*` consumer to a `devel:18` provider
- [ ] Every run reports ≥1 edge from a `devel:18` consumer to `(devel:18, percona-postgresql)` (positive control: intra-devel cascade still works)
- [ ] Output of all runs captured in `tmp/dep-resolution-evidence.txt`

**Verify:** `for s in 0 1 2 3 42; do PYTHONHASHSEED=$s venv/bin/python tmp/verify_dep_resolution.py || exit 1; done; echo ALL_OK` → `ALL_OK`

**Steps:**

- [ ] **Step 1: Write the verification script**

Create `tmp/verify_dep_resolution.py`:

```python
"""Live read-only check of dep-cascade provider attribution (PR #139 bug).

Queries _builddepinfo/_meta on api.opensuse.org (GET only — no writes) for
the PG-18 tier projects and asserts:
  1. no dep edge attributes a staging:18* consumer to a devel:18 provider
  2. devel:18 consumers still depend on devel:18/percona-postgresql
     (intra-tier cascade preserved)

Run with several hash seeds to prove order-independence:
    for s in 0 1 2 3 42; do PYTHONHASHSEED=$s venv/bin/python tmp/verify_dep_resolution.py || exit 1; done
"""

import os
import sys
import xml.etree.ElementTree as ET

import osc.conf

osc.conf.get_config(override_apiurl="https://api.opensuse.org")

import osc.connection
import osc.core

from percona_obs.obs_api import _fetch_combined_depinfo

APIURL = "https://api.opensuse.org"
DEVEL = "isv:percona:ppg:devel:18"
PROJECTS = {
    DEVEL,
    "isv:percona:ppg:staging:18",
    "isv:percona:ppg:staging:18:extras",
    "isv:percona:ppg:staging:18:containers:ubi8",
    "isv:percona:ppg:staging:18:containers:ubi9",
    "isv:percona:ppg:common:deps",
}

# local_pkg_set = every (project, package) that exists in the queried
# projects, so no edge is dropped by the locality filter.
local_pkg_set = set()
for proj in PROJECTS:
    url = osc.core.makeurl(APIURL, ["source", proj])
    root = ET.fromstring(osc.connection.http_GET(url).read())
    for entry in root.findall("entry"):
        name = entry.get("name", "")
        if name:
            local_pkg_set.add((proj, name))

fwd = _fetch_combined_depinfo(APIURL, PROJECTS, local_pkg_set)

bad = sorted(
    (consumer, provider)
    for consumer, deps in fwd.items()
    for provider in deps
    if consumer[0].startswith("isv:percona:ppg:staging:18") and provider[0] == DEVEL
)
control = sorted(
    consumer
    for consumer, deps in fwd.items()
    if consumer[0] == DEVEL and (DEVEL, "percona-postgresql") in deps
)

seed = os.environ.get("PYTHONHASHSEED", "random")
edges = sum(len(d) for d in fwd.values())
print(f"seed={seed}: {len(fwd)} consumers, {edges} edges")
for consumer, provider in bad:
    print(f"  BAD cross-tier edge: {consumer} -> {provider}")
print(f"  staging->devel edges: {len(bad)} (want 0)")
print(f"  devel consumers of devel/percona-postgresql: {len(control)} (want >=1)")
sys.exit(0 if not bad and control else 1)
```

- [ ] **Step 2: Run across hash seeds and capture evidence**

Run:

```bash
for s in 0 1 2 3 42; do
  PYTHONHASHSEED=$s venv/bin/python tmp/verify_dep_resolution.py || exit 1
done 2>&1 | tee tmp/dep-resolution-evidence.txt
echo "exit=$?" >> tmp/dep-resolution-evidence.txt
```

Expected: five `seed=N` blocks, each with `staging->devel edges: 0 (want 0)` and `devel consumers ...: >=1`, final `exit=0`.

Baseline note for the reviewer: the pre-fix failure is already evidenced by CI — workflow run 29241998426 on rjd15372/percona-obs-packaging (job 86789994630) logged 35 `dep-promote:` lines attributing `staging:18*` packages to `devel:18` providers. No need to re-run the broken code.

- [ ] **Step 3: No commit**

`tmp/` is gitignored. Nothing to commit; the task is complete when the evidence file shows all five seeds passing.

---

## Post-plan follow-ups (not part of this plan)

- Update the PR #139 branch is NOT needed — the fix lives in `percona_obs/`, which the PR workflow checks out from the PR head. Re-running the PR workflow after this fix merges to main will still use the PR branch's copy of `percona_obs/`; the fix must be rebased into (or merged into) the `devel-18` branch, or land on main first and the PR rebased. Decide with the user which route to take.
- Pushing / PR creation requires explicit user approval (repo rule).
