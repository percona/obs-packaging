# QA image references (per-image registry path resolution) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a `qa:` parameter name a container image by its OBS package, so the tool renders the registry path and picks the root project that actually holds that image (the PR project when it was promoted there, the production root otherwise).

**Architecture:** A parameter value that is a mapping with an `image:` key is an *image reference*. A new module `percona_obs/qa_images.py` validates the shape, renders `<registry>/<rootprj>/<project>/<repository>` and decides the rootprj per image with one cached OBS package listing per project. `qa show` / `qa run` resolve every image reference to a plain string before matrix expansion, so Jenkins, the JSON matrix and the state files are unchanged. The fallback rootprj comes from a new profile key `image-fallback-rootprj` that CI writes into the PR profiles only; without it the current rootprj is always used and OBS is never queried (nightly and manual runs keep today's behaviour). `project verify` checks that every image reference names a package and repository that exist in the tree.

**Tech Stack:** Python 3 (`percona_obs/`), pytest (`tests/`), GitHub Actions workflows, YAML packaging tree under `root/`.

**Spec:** No separate spec; the design was settled in conversation on 2026-10-12 and is summarised in *Design* below. The problem statement: a PR that promotes one image into `isv:percona:PR:pr-N:…:containers` still runs every lane of that project's `qa:` block, and each lane's `REPOSITORY` renders with the PR rootprj, so lanes for images that were not promoted point at registry paths that do not exist.

## Design

**YAML shape.** Resolution is keyed on the *value*, never on the parameter name (pipelines name their parameters differently: `REPOSITORY`, `OLD_DOCKER_REPOSITORY`, …):

```yaml
parameters:
  REPOSITORY:                       # any parameter name
    image: percona-pgbouncer        # required: OBS package name of the image
    repository: ubi9                # required: OBS repository, last path segment
    project: ppg:staging:18:containers   # optional: colon notation without rootprj;
                                         # defaults to the project the lane belongs to
```

Rendered value: `<OBS_CONTAINER_REGISTRY>/<rootprj as path>/<project as path>/<repository>`, lower-cased, colons replaced by slashes (the same transformation `auto_rootprj_env` applies to `OBS_CONTAINER_REGISTRY_ROOTPRJ`). Example: `obs.pg.labs.percona.com/isv/percona/pr/pr-124/ppg/staging/18/containers/ubi9`.

**Decision rule** (per image reference, in `qa show` and `qa run`):

| fallback rootprj configured? | `<image>` listed in `<rootprj>:<project>` on OBS? | rootprj used | reason tag |
|---|---|---|---|
| no | not queried | current rootprj | `no-fallback` |
| yes | yes | current rootprj | `present` |
| yes | no (incl. project 404) | fallback rootprj | `fallback` |

Any OBS error other than 404 aborts (same strictness as the present-only filter in `list_qa_matrix.py`). One listing per OBS project per invocation, cached.

**Fallback plumbing.** Profile key `image-fallback-rootprj: isv:percona` (also a global CLI flag `--image-fallback-rootprj`, CLI wins). `obs-pr-check.yml` and `obs-qa-run.yml` (with `pr_number`) write it into the PR CI profile from the instance's production `rootprj` in `OBS_INSTANCES`. The nightly never writes it.

**Out of scope (user decision):** a lane whose matrix axis selects the image inside Jenkins (`WITH_POSTGIS` on `docker-server-parallel`). Such a lane names one image; when only its sibling was promoted the lane tests the fallback image. Image references inside matrix-axis lists are rejected.

**Existing string form stays valid.** `REPOSITORY: ${OBS_CONTAINER_REGISTRY}/${OBS_CONTAINER_REGISTRY_ROOTPRJ}/…` keeps working unchanged; the tree conversion (Task 7) is what switches the lanes over.

## Global Constraints

- Run `venv/bin/black percona_obs/` then `venv/bin/pyright` after every code change; both must pass (pyright: `0 errors`). Run `venv/bin/pytest tests/ -q` before every commit.
- Commits: `git commit -s`; no `Co-Authored-By: Claude` lines. Work on a worktree branch off `percona/main` (`.claude/worktrees/qa-image-refs`), never in the primary checkout. Never `git push` or open a PR without asking.
- Rendered path format is exactly `<registry>/<rootprj path>/<project path>/<repository>` lower-cased, so converted lanes render byte-for-byte what the string form renders today on the production root (e.g. `registry.opensuse.org/isv/percona/ppg/staging/18/containers/ubi9`).
- Without a fallback rootprj the tool must not call OBS from `qa show` / `qa run` (the docs promise "the tool never calls OBS for QA" for that case; Task 6 rewords the promise).
- The `qa show --json` schema (`project, package, pipeline, name, label, axis_filters, name_filter, package_filter, status_context, params`) is unchanged; `params` values are always strings.
- A mapping parameter value without `image:` is an error, as is a `dict` inside any list value.
- `project verify` skips image references whose `project:` is not a directory in the tree (same rule as `_validate_repo_path_refs`); `ppg:staging:16:extras:containers` references `ppg:staging:15:extras:containers`, which exists only on OBS.

**User decisions (already made):**
- "Resolution must not depend on the parameter name, must be something about the value." → mapping value with `image:` key.
- "There's no good solution to the matrix problem … let's leave that out of scope." → image refs are rejected on matrix axes; `WITH_POSTGIS` lanes name the plain server image.
- Option 2 (per-image resolution in the tool) is the chosen approach; option 1 (package-level lanes) and option 3 (promote all sibling images) are not pursued.

---

## File Structure

| File | Responsibility |
|---|---|
| Create `percona_obs/qa_images.py` | Image-reference shape (`is_image_ref`, `validate_image_ref`), path rendering (`registry_path`), the `ImageResolver` decision + cache, `resolve_entry_images`, `image_ref_errors` for verify. No argparse, no printing. |
| Modify `percona_obs/cmd_qa.py` | Validate image refs in `_validate_qa`; build the resolver from `args`; resolve lanes in `cmd_qa_show` / `cmd_qa_run`; print decisions to stderr. |
| Modify `percona_obs/cli.py` | Global `--image-fallback-rootprj` flag; read `image-fallback-rootprj` profile key in `main()`. |
| Modify `percona_obs/cmd_project.py` | `_validate_qa_image_refs` wired into `cmd_project_verify`. |
| Modify `.github/scripts/list_qa_matrix.py` | Forward `qa show` stderr (the decisions) into the detect job log. |
| Modify `.github/scripts/resolve_qa_instance.py` | New output `instance_rootprj` (production root, always). |
| Modify `.github/workflows/obs-pr-check.yml`, `.github/workflows/obs-qa-run.yml` | Write `image-fallback-rootprj` into PR profiles; stamp `instance_rootprj` through the merged matrix. |
| Modify `docs/PERCONA_OBS_TOOL.md`, `.github/copilot-instructions.md` | Schema, decision rule, profile key. |
| Modify `root/ppg/staging/**/containers/project.yaml` (8 files) | Convert `REPOSITORY` / `OLD_DOCKER_REPOSITORY` strings to image references. |
| Create `tests/test_qa_images.py`, `tests/test_qa_image_resolution.py`, `tests/test_project_verify_qa_images.py` | Unit tests per task. Modify `tests/test_list_qa_matrix.py`, `tests/test_container_registry.py`. |

---

### Task 1: `qa_images.py` — shape validation and path rendering

**Goal:** A pure module that recognises an image reference, validates it, and renders the registry path for a given rootprj.

**Files:**
- Create: `percona_obs/qa_images.py`
- Test: `tests/test_qa_images.py`

**Acceptance Criteria:**
- [ ] `is_image_ref({"image": "x"})` is `True`; `is_image_ref("str")`, `is_image_ref({"repository": "ubi9"})`, `is_image_ref(["a"])` are `False`.
- [ ] `validate_image_ref` raises `SystemExit` whose message names `where` and the parameter for: missing/empty `image`, missing/empty `repository`, non-string `project`, unknown keys.
- [ ] `registry_path("reg.example", "isv:percona:PR:pr-124", "ppg:staging:18:containers", "ubi9") == "reg.example/isv/percona/pr/pr-124/ppg/staging/18/containers/ubi9"`.
- [ ] `registry_path` output for `("registry.opensuse.org", "isv:percona", "ppg:staging:18:containers", "ubi9")` equals what the string form renders today: `registry.opensuse.org/isv/percona/ppg/staging/18/containers/ubi9`.

**Verify:** `venv/bin/pytest tests/test_qa_images.py -v` → all PASS; `venv/bin/black percona_obs/ && venv/bin/pyright` → 0 errors.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_qa_images.py
"""Image references in qa: parameters: shape and path rendering."""

import pytest

from percona_obs import qa_images


def test_is_image_ref_requires_mapping_with_image_key():
    assert qa_images.is_image_ref({"image": "percona-pgbouncer", "repository": "ubi9"})
    assert not qa_images.is_image_ref("reg/ubi9")
    assert not qa_images.is_image_ref({"repository": "ubi9"})
    assert not qa_images.is_image_ref(["a", "b"])
    assert not qa_images.is_image_ref(None)


@pytest.mark.parametrize(
    "ref, needle",
    [
        ({"repository": "ubi9"}, "image"),
        ({"image": "", "repository": "ubi9"}, "image"),
        ({"image": "x"}, "repository"),
        ({"image": "x", "repository": 9}, "repository"),
        ({"image": "x", "repository": "ubi9", "project": 18}, "project"),
        ({"image": "x", "repository": "ubi9", "tag": "18"}, "tag"),
    ],
)
def test_validate_image_ref_rejects_bad_shapes(ref, needle):
    with pytest.raises(SystemExit) as exc:
        qa_images.validate_image_ref(ref, "ppg:staging:18:containers", "REPOSITORY")
    msg = str(exc.value)
    assert "ppg:staging:18:containers" in msg
    assert "REPOSITORY" in msg
    assert needle in msg


def test_validate_image_ref_accepts_minimal_and_full():
    qa_images.validate_image_ref({"image": "x", "repository": "ubi9"}, "p", "R")
    qa_images.validate_image_ref(
        {"image": "x", "repository": "ubi9", "project": "ppg:staging:17:containers"},
        "p",
        "R",
    )


def test_registry_path_lowercases_and_slashes():
    assert qa_images.registry_path(
        "reg.example", "isv:percona:PR:pr-124", "ppg:staging:18:containers", "ubi9"
    ) == "reg.example/isv/percona/pr/pr-124/ppg/staging/18/containers/ubi9"


def test_registry_path_matches_the_string_form_on_production():
    # What `${OBS_CONTAINER_REGISTRY}/${OBS_CONTAINER_REGISTRY_ROOTPRJ}/ppg/staging/18/containers/ubi9`
    # renders today with rootprj isv:percona and the default registry.
    assert qa_images.registry_path(
        "registry.opensuse.org", "isv:percona", "ppg:staging:18:containers", "ubi9"
    ) == "registry.opensuse.org/isv/percona/ppg/staging/18/containers/ubi9"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_qa_images.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'percona_obs.qa_images'`

- [ ] **Step 3: Write the module**

```python
# percona_obs/qa_images.py
"""Image references in ``qa:`` parameters.

A parameter whose value is a mapping with an ``image:`` key names a container
image by its OBS package instead of spelling the registry path::

    REPOSITORY:
      image: percona-pgbouncer          # OBS package name of the image
      repository: ubi9                  # OBS repository, last path segment
      project: ppg:staging:18:containers   # optional, defaults to the lane's project

The tool renders ``<registry>/<rootprj>/<project>/<repository>`` and decides
which root project the image lives under: the one ``qa show`` / ``qa run``
are run against when that project holds the package on OBS (it was promoted
and built there), else the fallback root project (profile key
``image-fallback-rootprj``; the production root in PR runs).  Without a
fallback the current root is always used and OBS is never queried.

Resolution is keyed on the value, never on the parameter name: pipelines
name their parameters differently (``REPOSITORY``, ``OLD_DOCKER_REPOSITORY``).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

IMAGE_REF_KEYS = frozenset({"image", "repository", "project"})


def is_image_ref(value: Any) -> bool:
    """True for a mapping carrying an ``image`` key (shape is checked separately)."""
    return isinstance(value, dict) and "image" in value


def validate_image_ref(value: dict[str, Any], where: str, param: str) -> None:
    """Reject a malformed image reference with a message naming *where*/*param*."""
    prefix = f"error: {where}: qa.parameters.{param}"
    unknown = sorted(set(value) - IMAGE_REF_KEYS)
    if unknown:
        raise SystemExit(
            f"{prefix}: unknown key(s) {', '.join(unknown)}; an image reference "
            "takes image, repository and optionally project"
        )
    for key in ("image", "repository"):
        v = value.get(key)
        if not isinstance(v, str) or not v:
            raise SystemExit(f"{prefix}: {key} must be a non-empty string")
    project = value.get("project")
    if project is not None and (not isinstance(project, str) or not project):
        raise SystemExit(f"{prefix}: project must be a non-empty string when set")


def _as_path(obs_name: str) -> str:
    """``isv:percona:PR:pr-1`` → ``isv/percona/pr/pr-1`` (OBS registry path form)."""
    return obs_name.replace(":", "/").lower()


def registry_path(registry: str, rootprj: str, project: str, repository: str) -> str:
    """The registry path Jenkins appends the image name to."""
    return f"{registry}/{_as_path(rootprj)}/{_as_path(project)}/{repository}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_qa_images.py -v`
Expected: all PASS

- [ ] **Step 5: Format, type-check, commit**

```bash
venv/bin/black percona_obs/ && venv/bin/pyright
git add percona_obs/qa_images.py tests/test_qa_images.py
git commit -s -m "qa: add image references (shape + registry path rendering)"
```

---

### Task 2: `ImageResolver` — rootprj decision with OBS lookup, fallback and cache

**Goal:** Decide, per image reference, which rootprj to render with, querying OBS once per project only when a fallback is configured.

**Files:**
- Modify: `percona_obs/qa_images.py` (append)
- Test: `tests/test_qa_images.py` (append)

**Acceptance Criteria:**
- [ ] With `fallback_rootprj=None` the injected `list_packages` callable is never called and every decision has `reason == "no-fallback"` and `rootprj == current`.
- [ ] With a fallback, an image listed in `<current>:<project>` resolves to `current` with reason `present`; an absent one to the fallback with reason `fallback`.
- [ ] Two references into the same project cause exactly one `list_packages` call (cache).
- [ ] `project:` on the reference overrides the lane project in both the lookup and the rendered path.
- [ ] `resolve_entry_images` replaces every image reference in `entry["parameters"]` with the rendered string in place, leaves other values untouched, and returns one `ImageDecision` per reference in parameter order.

**Verify:** `venv/bin/pytest tests/test_qa_images.py -v` → all PASS; black + pyright clean.

**Steps:**

- [ ] **Step 1: Write the failing tests (append to `tests/test_qa_images.py`)**

```python
# --- resolver -------------------------------------------------------------------


class _Lister:
    """Injected OBS listing: records calls, answers from a fixed map."""

    def __init__(self, present: dict[str, set[str]]):
        self.present = present
        self.calls: list[str] = []

    def __call__(self, obs_project: str) -> set[str]:
        self.calls.append(obs_project)
        return self.present.get(obs_project, set())


def _resolver(fallback, lister):
    return qa_images.ImageResolver(
        registry="reg.example",
        rootprj="isv:percona:PR:pr-5",
        fallback_rootprj=fallback,
        list_packages=lister,
    )


def test_no_fallback_never_queries_obs():
    lister = _Lister({})
    d = _resolver(None, lister).decide(
        "REPOSITORY", {"image": "img", "repository": "ubi9"}, "ppg:staging:18:containers"
    )
    assert lister.calls == []
    assert (d.rootprj, d.reason) == ("isv:percona:PR:pr-5", "no-fallback")
    assert d.value == "reg.example/isv/percona/pr/pr-5/ppg/staging/18/containers/ubi9"


def test_present_image_uses_current_rootprj():
    lister = _Lister({"isv:percona:PR:pr-5:ppg:staging:18:containers": {"img"}})
    d = _resolver("isv:percona", lister).decide(
        "REPOSITORY", {"image": "img", "repository": "ubi9"}, "ppg:staging:18:containers"
    )
    assert (d.rootprj, d.reason) == ("isv:percona:PR:pr-5", "present")
    assert d.value.startswith("reg.example/isv/percona/pr/pr-5/")


def test_absent_image_falls_back():
    lister = _Lister({"isv:percona:PR:pr-5:ppg:staging:18:containers": {"other"}})
    d = _resolver("isv:percona", lister).decide(
        "REPOSITORY", {"image": "img", "repository": "ubi9"}, "ppg:staging:18:containers"
    )
    assert (d.rootprj, d.reason) == ("isv:percona", "fallback")
    assert d.value == "reg.example/isv/percona/ppg/staging/18/containers/ubi9"
    assert d.obs_project == "isv:percona:PR:pr-5:ppg:staging:18:containers"


def test_listing_is_cached_per_project():
    lister = _Lister({})
    r = _resolver("isv:percona", lister)
    r.decide("A", {"image": "a", "repository": "ubi9"}, "ppg:staging:18:containers")
    r.decide("B", {"image": "b", "repository": "ubi8"}, "ppg:staging:18:containers")
    r.decide("C", {"image": "c", "repository": "ubi9"}, "ppg:staging:17:containers")
    assert lister.calls == [
        "isv:percona:PR:pr-5:ppg:staging:18:containers",
        "isv:percona:PR:pr-5:ppg:staging:17:containers",
    ]


def test_explicit_project_overrides_lane_project():
    lister = _Lister({"isv:percona:PR:pr-5:ppg:staging:17:extras:containers": {"old"}})
    d = _resolver("isv:percona", lister).decide(
        "OLD_DOCKER_REPOSITORY",
        {"image": "old", "repository": "ubi9", "project": "ppg:staging:17:extras:containers"},
        "ppg:staging:18:extras:containers",
    )
    assert d.project == "ppg:staging:17:extras:containers"
    assert d.reason == "present"
    assert d.value == "reg.example/isv/percona/pr/pr-5/ppg/staging/17/extras/containers/ubi9"


def test_resolve_entry_images_rewrites_in_place_and_in_order():
    lister = _Lister({"isv:percona:PR:pr-5:ppg:staging:18:containers": {"new"}})
    entry = {
        "pipeline": "p",
        "parameters": {
            "TAG": "18",
            "REPOSITORY": {"image": "new", "repository": "ubi9"},
            "OLD_DOCKER_REPOSITORY": {"image": "old", "repository": "ubi9"},
            "PLATFORMS": ["a", "b"],
        },
    }
    decisions = qa_images.resolve_entry_images(
        entry, "ppg:staging:18:containers", _resolver("isv:percona", lister)
    )
    assert [d.param for d in decisions] == ["REPOSITORY", "OLD_DOCKER_REPOSITORY"]
    assert [d.reason for d in decisions] == ["present", "fallback"]
    p = entry["parameters"]
    assert p["TAG"] == "18" and p["PLATFORMS"] == ["a", "b"]
    assert p["REPOSITORY"] == "reg.example/isv/percona/pr/pr-5/ppg/staging/18/containers/ubi9"
    assert p["OLD_DOCKER_REPOSITORY"] == "reg.example/isv/percona/ppg/staging/18/containers/ubi9"


def test_resolve_entry_images_without_refs_is_a_noop():
    entry = {"pipeline": "p", "parameters": {"X": "1"}}
    assert qa_images.resolve_entry_images(entry, "ppg:staging:18", _resolver(None, _Lister({}))) == []
    assert entry["parameters"] == {"X": "1"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_qa_images.py -v -k "resolver or fallback or cached or overrides or resolve_entry"`
Expected: FAIL with `AttributeError: module 'percona_obs.qa_images' has no attribute 'ImageResolver'`

- [ ] **Step 3: Append the resolver to `percona_obs/qa_images.py`**

```python
@dataclasses.dataclass(frozen=True)
class ImageDecision:
    """Which root project one image reference was rendered with, and why."""

    param: str
    image: str
    project: str  # colon notation, without rootprj
    obs_project: str  # the project that was (or would have been) listed
    rootprj: str  # the root project used in ``value``
    reason: str  # "no-fallback" | "present" | "fallback"
    value: str  # rendered registry path


class ImageResolver:
    """Renders image references, choosing the rootprj per image.

    *list_packages* returns the package names of an OBS project (empty on
    404); it is called at most once per project and only when
    *fallback_rootprj* is set.
    """

    def __init__(
        self,
        registry: str,
        rootprj: str,
        fallback_rootprj: str | None,
        list_packages: Callable[[str], set[str]],
    ) -> None:
        self.registry = registry
        self.rootprj = rootprj
        self.fallback_rootprj = fallback_rootprj or None
        self._list_packages = list_packages
        self._present: dict[str, set[str]] = {}

    def _packages(self, obs_project: str) -> set[str]:
        if obs_project not in self._present:
            self._present[obs_project] = set(self._list_packages(obs_project))
        return self._present[obs_project]

    def decide(self, param: str, ref: dict[str, Any], lane_project: str) -> ImageDecision:
        project = ref.get("project") or lane_project
        image: str = ref["image"]
        obs_project = f"{self.rootprj}:{project}"
        if self.fallback_rootprj is None:
            rootprj, reason = self.rootprj, "no-fallback"
        elif image in self._packages(obs_project):
            rootprj, reason = self.rootprj, "present"
        else:
            rootprj, reason = self.fallback_rootprj, "fallback"
        return ImageDecision(
            param=param,
            image=image,
            project=project,
            obs_project=obs_project,
            rootprj=rootprj,
            reason=reason,
            value=registry_path(self.registry, rootprj, project, ref["repository"]),
        )


def resolve_entry_images(
    entry: dict[str, Any], lane_project: str, resolver: ImageResolver
) -> list[ImageDecision]:
    """Replace every image reference in ``entry["parameters"]`` with its path.

    Mutates *entry* in place; returns the decisions in parameter order.
    """
    decisions: list[ImageDecision] = []
    params: dict[str, Any] = entry.get("parameters") or {}
    for name, value in list(params.items()):
        if is_image_ref(value):
            decision = resolver.decide(name, value, lane_project)
            params[name] = decision.value
            decisions.append(decision)
    return decisions
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_qa_images.py -v`
Expected: all PASS

- [ ] **Step 5: Format, type-check, commit**

```bash
venv/bin/black percona_obs/ && venv/bin/pyright
git add percona_obs/qa_images.py tests/test_qa_images.py
git commit -s -m "qa: ImageResolver picks the rootprj per image (present vs fallback)"
```

---

### Task 3: Wire image references into `qa show` / `qa run` and the profile

**Goal:** `qa show` and `qa run` validate image references, resolve them before matrix expansion, print the decisions, and read the fallback rootprj from the profile or CLI.

**Files:**
- Modify: `percona_obs/cmd_qa.py` (`_validate_qa` ~line 180-220, `cmd_qa_show` ~line 505, `cmd_qa_run` ~line 705, new helpers near `_qa_env_vars`)
- Modify: `percona_obs/cli.py` (global parser ~line 60-80; `main()` ~line 822-848)
- Test: `tests/test_qa_image_resolution.py`

**Acceptance Criteria:**
- [ ] A `qa:` block with `REPOSITORY: {image: x, repository: ubi9}` loads; `qa show --json` emits `params.REPOSITORY` as the rendered string.
- [ ] A mapping value without `image:` → `SystemExit` mentioning `qa.parameters.<name>` and "image reference".
- [ ] A `dict` inside a list value (matrix axis or not) → `SystemExit` mentioning "scalars".
- [ ] Without `image_fallback_rootprj` on `args`, no OBS call is made (the lister is monkeypatched to raise).
- [ ] With `image_fallback_rootprj` set and the image absent from the PR project, `qa show` renders the fallback path and prints a line containing `fallback` and the image name on stderr.
- [ ] `cli.main()` sets `args.image_fallback_rootprj` from the profile key `image-fallback-rootprj`; `--image-fallback-rootprj` on the command line wins over the profile.
- [ ] `qa run --dry-run` resolves images the same way (the printed POST body carries the rendered path).

**Verify:** `venv/bin/pytest tests/test_qa_image_resolution.py tests/test_qa_package_lanes.py tests/test_qa_entry_name.py tests/test_container_registry.py -v` → all PASS; black + pyright clean.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_qa_image_resolution.py
"""Image references flow through `qa show` / `qa run` and the profile."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import percona_obs.cli as cli
import percona_obs.cmd_qa as cmd_qa
import percona_obs.common as common
from percona_obs.common import registry_env_override

_QA = """\
title: C
qa:
  - name: ubi9
    pipeline: docker-component-parallel
    parameters:
      TAG: "18"
      REPOSITORY:
        image: percona-pgbouncer
        repository: ubi9
      SERVER_REPOSITORY:
        image: percona-distribution-postgresql
        repository: ubi9
        project: ppg:staging:18:containers
"""


def _tree(tmp_path, monkeypatch, qa_text=_QA) -> Path:
    root = tmp_path / "root"
    proj = root / "ppg" / "staging" / "common" / "tools" / "containers"
    proj.mkdir(parents=True)
    (root / "macros.yaml").write_text("- M: 1\n")
    (proj / "project.yaml").write_text(qa_text)
    monkeypatch.setattr(common, "REPO_ROOT", root)
    return root


def _args(**kw):
    base = dict(
        project="ppg:staging:common:tools:containers",
        rootprj="isv:percona:PR:pr-9",
        apiurl="https://obs.example",
        env_overrides=[registry_env_override("reg.example")],
        image_fallback_rootprj=None,
        json=True,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _show_json(capsys, args):
    cmd_qa.cmd_qa_show(args)
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.err


def test_show_renders_image_refs_without_fallback_and_without_obs(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)

    def boom(apiurl, project):
        raise AssertionError("OBS must not be queried without a fallback rootprj")

    monkeypatch.setattr(cmd_qa, "_fetch_obs_package_names_or_fail", boom)
    entries, err = _show_json(capsys, _args())
    params = entries[0]["params"]
    assert params["REPOSITORY"] == (
        "reg.example/isv/percona/pr/pr-9/ppg/staging/common/tools/containers/ubi9"
    )
    assert params["SERVER_REPOSITORY"] == (
        "reg.example/isv/percona/pr/pr-9/ppg/staging/18/containers/ubi9"
    )
    assert params["TAG"] == "18"


def test_show_falls_back_for_absent_image_and_reports(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    listed: list[str] = []

    def fake_list(apiurl, project):
        listed.append(project)
        return {"percona-pgbouncer"} if project.endswith("tools:containers") else set()

    monkeypatch.setattr(cmd_qa, "_fetch_obs_package_names_or_fail", fake_list)
    entries, err = _show_json(capsys, _args(image_fallback_rootprj="isv:percona"))
    params = entries[0]["params"]
    assert params["REPOSITORY"].startswith("reg.example/isv/percona/pr/pr-9/")
    assert params["SERVER_REPOSITORY"] == (
        "reg.example/isv/percona/ppg/staging/18/containers/ubi9"
    )
    assert listed == [
        "isv:percona:PR:pr-9:ppg:staging:common:tools:containers",
        "isv:percona:PR:pr-9:ppg:staging:18:containers",
    ]
    assert "percona-distribution-postgresql" in err and "fallback" in err
    assert "percona-pgbouncer" in err and "present" in err


def test_mapping_without_image_is_rejected(tmp_path, monkeypatch):
    _tree(
        tmp_path,
        monkeypatch,
        "title: C\nqa:\n  pipeline: p\n  parameters:\n    REPOSITORY:\n      repository: ubi9\n",
    )
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_lanes("ppg:staging:common:tools:containers", {})
    assert "qa.parameters.REPOSITORY" in str(exc.value)
    assert "image" in str(exc.value)


def test_image_ref_inside_a_list_is_rejected(tmp_path, monkeypatch):
    _tree(
        tmp_path,
        monkeypatch,
        "title: C\nqa:\n  pipeline: p\n  parameters:\n    REPOSITORY:\n"
        "      - {image: a, repository: ubi9}\n      - {image: b, repository: ubi9}\n"
        "  matrix: [REPOSITORY]\n",
    )
    with pytest.raises(SystemExit) as exc:
        cmd_qa._load_qa_lanes("ppg:staging:common:tools:containers", {})
    assert "scalars" in str(exc.value)


def test_run_dry_run_resolves_images(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch)
    monkeypatch.setattr(cmd_qa, "_fetch_obs_package_names_or_fail", lambda a, p: set())
    monkeypatch.setattr(cmd_qa, "load_jenkins_config", lambda *a, **k: None)
    args = _args(
        image_fallback_rootprj="isv:percona",
        dry_run=True,
        wait=False,
        filter=[],
        param=[],
        pipeline=None,
        name=None,
        package=None,
        project_only=False,
        report_json=None,
    )
    cmd_qa.cmd_qa_run(args)
    out = capsys.readouterr().out
    assert "reg.example/isv/percona/ppg/staging/common/tools/containers/ubi9" in out


# --- profile / CLI plumbing -----------------------------------------------------


import argparse

import percona_obs.cmd_profile as cmd_profile


def _run_main(monkeypatch, argv, profiles_dir):
    """Run ``cli.main()`` with a stub parser (same pattern as
    tests/test_container_registry.py::_run_main) and return the resolved
    ``args.image_fallback_rootprj``.  The stub uses the local-only ``project``
    command so no OBS connection is attempted."""
    monkeypatch.setattr(cmd_profile, "_PROFILES_DIR", profiles_dir)
    captured: dict[str, object] = {}

    def fake_build_parser() -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(prog="percona-obs")
        p.add_argument("-A", "--apiurl")
        p.add_argument("-R", "--rootprj")
        p.add_argument("-P", "--profile")
        p.add_argument("-e", "--env", action="append", default=[], dest="env_overrides")
        p.add_argument("--image-fallback-rootprj", default=None, dest="image_fallback_rootprj")
        p.add_argument("--verbose", action="store_true", default=False)
        p.add_argument("command")
        p.set_defaults(
            func=lambda a: captured.__setitem__("fallback", a.image_fallback_rootprj)
        )
        return p

    monkeypatch.setattr(cli, "build_parser", fake_build_parser)
    monkeypatch.setattr(cli.sys, "argv", ["percona-obs", *argv])
    cli.main()
    return captured["fallback"]


def test_profile_key_sets_fallback(tmp_path, monkeypatch):
    (tmp_path / "ci.yaml").write_text(
        "apiurl: http://a\nrootprj: isv:percona:PR:pr-9\nimage-fallback-rootprj: isv:percona\n"
    )
    assert _run_main(monkeypatch, ["-P", "ci", "project"], tmp_path) == "isv:percona"


def test_cli_flag_overrides_profile_key(tmp_path, monkeypatch):
    (tmp_path / "ci.yaml").write_text(
        "apiurl: http://a\nrootprj: isv:percona:PR:pr-9\nimage-fallback-rootprj: isv:percona\n"
    )
    assert (
        _run_main(
            monkeypatch,
            ["-P", "ci", "--image-fallback-rootprj", "home:me", "project"],
            tmp_path,
        )
        == "home:me"
    )


def test_no_key_means_no_fallback(tmp_path, monkeypatch):
    (tmp_path / "ci.yaml").write_text("apiurl: http://a\nrootprj: isv:percona\n")
    assert _run_main(monkeypatch, ["-P", "ci", "project"], tmp_path) is None
```

Note for the implementer: the stub parser must declare `--image-fallback-rootprj` because `main()` reads `args.image_fallback_rootprj` unconditionally once Step 5 lands; the real parser gets the flag in the same step.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_qa_image_resolution.py -v`
Expected: FAIL (`AttributeError: ... has no attribute '_fetch_obs_package_names_or_fail'`, `SystemExit` not raised for the shape tests, `AttributeError: 'Namespace' object has no attribute 'image_fallback_rootprj'`).

- [ ] **Step 3: Validation in `_validate_qa` (`percona_obs/cmd_qa.py`)**

Add the imports at the top of `cmd_qa.py`:

```python
from .common import DEFAULT_CONTAINER_REGISTRY  # add to the existing .common import list
from .obs_api import _fetch_obs_package_names_or_fail
from .qa_images import (
    ImageDecision,
    ImageResolver,
    is_image_ref,
    resolve_entry_images,
    validate_image_ref,
)
```

In `_validate_qa`, right after the `parameters` non-empty check and before the `matrix` checks, add:

```python
    for pname, pvalue in parameters.items():
        if isinstance(pvalue, dict):
            if not is_image_ref(pvalue):
                raise SystemExit(
                    f"error: {project}: qa.parameters.{pname}: a mapping value must "
                    "be an image reference (image: <package>, repository: <repo>"
                    "[, project: <project>])"
                )
            validate_image_ref(pvalue, project, pname)
        elif isinstance(pvalue, list) and any(isinstance(x, dict) for x in pvalue):
            raise SystemExit(
                f"error: {project}: qa.parameters.{pname}: list values must be "
                "scalars; image references are not supported inside lists "
                "(matrix axes select images in Jenkins, not in the tool)"
            )
```

- [ ] **Step 4: Resolver construction and lane resolution (`percona_obs/cmd_qa.py`)**

Add after `_qa_env_vars`:

```python
def _image_resolver(args: argparse.Namespace, env_vars: dict[str, str]) -> ImageResolver:
    """The per-invocation resolver for image references.

    The fallback rootprj comes from the profile key ``image-fallback-rootprj``
    (or ``--image-fallback-rootprj``); without it OBS is never queried.
    """
    fallback = getattr(args, "image_fallback_rootprj", None) or None
    apiurl = getattr(args, "apiurl", None) or ""
    if fallback and not apiurl:
        raise SystemExit(
            "error: image-fallback-rootprj needs an OBS apiurl (-A or a profile) "
            "to list the packages of the current root project"
        )
    return ImageResolver(
        registry=env_vars.get("OBS_CONTAINER_REGISTRY", DEFAULT_CONTAINER_REGISTRY),
        rootprj=args.rootprj,
        fallback_rootprj=fallback,
        list_packages=lambda p: _fetch_obs_package_names_or_fail(apiurl, p),
    )


def _resolve_lane_images(
    lanes: list[Lane], project: str, resolver: ImageResolver
) -> list[ImageDecision]:
    """Render every image reference of every lane in place; return the decisions."""
    decisions: list[ImageDecision] = []
    for lane in lanes:
        for entry in lane.entries:
            decisions.extend(resolve_entry_images(entry, project, resolver))
    return decisions


def _print_image_decisions(decisions: list[ImageDecision]) -> None:
    """One stderr line per image reference: which rootprj it got, and why.

    Goes to stderr so `qa show --json` stays machine-readable; CI forwards it.
    """
    for d in decisions:
        if d.reason == "present":
            why = f"present in {d.obs_project}"
        elif d.reason == "fallback":
            why = f"fallback: not in {d.obs_project}"
        else:
            why = "no fallback configured"
        print(
            f"  image {d.image} ({d.project}) → {d.param} = {d.value}  [{d.reason}: {why}]",
            file=sys.stderr,
        )
```

In `cmd_qa_show`, replace the first two statements with:

```python
    env_vars = _qa_env_vars(args)
    lanes = _load_qa_lanes(args.project, env_vars)
    _print_image_decisions(
        _resolve_lane_images(lanes, args.project, _image_resolver(args, env_vars))
    )
    lanes = _lanes_with_expected_versions(lanes, args.project)
```

In `cmd_qa_run`, apply the same replacement to its first two statements (the `if not lanes:` error check stays right after).

- [ ] **Step 5: Profile key and CLI flag (`percona_obs/cli.py`)**

Next to the global `-e/--env` argument in `build_parser()` add:

```python
    parser.add_argument(
        "--image-fallback-rootprj",
        metavar="ROOTPRJ",
        default=None,
        dest="image_fallback_rootprj",
        help="Root project whose registry publishes an image that the current root "
        "project does not hold (qa: image references). CI sets this to the "
        "production root for PR runs; profile key 'image-fallback-rootprj'.",
    )
```

In `main()`, inside the `if args.profile:` block, after the `rootprj` fallback line add:

```python
        if not args.image_fallback_rootprj:
            args.image_fallback_rootprj = profile.get("image-fallback-rootprj")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_qa_image_resolution.py tests/test_qa_package_lanes.py tests/test_qa_entry_name.py tests/test_qa_expected_versions.py tests/test_container_registry.py -v`
Expected: all PASS. If `tests/test_qa_expected_versions.py` builds `SimpleNamespace` args without `apiurl`/`image_fallback_rootprj`, the `getattr` defaults above keep it passing; do not edit that test.

- [ ] **Step 7: Format, type-check, full suite, commit**

```bash
venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest tests/ -q
git add percona_obs/cmd_qa.py percona_obs/cli.py tests/test_qa_image_resolution.py
git commit -s -m "qa: resolve image references in qa show/run; image-fallback-rootprj profile key"
```

---

### Task 4: `project verify` checks image references against the tree

**Goal:** A typo in `image:`, `repository:` or `project:` fails `project verify` locally and in the Project Config Check workflow instead of at Jenkins time.

**Files:**
- Modify: `percona_obs/qa_images.py` (append `image_ref_errors`)
- Modify: `percona_obs/cmd_project.py` (new `_validate_qa_image_refs`; wire into `cmd_project_verify` next to `_validate_env_vars`, ~line 772 and the error printing/exit block ~line 795-816)
- Test: `tests/test_project_verify_qa_images.py`; modify `tests/test_project_verify_offline.py::_stub_validators` (add the new name to the stubbed list so the offline test keeps passing)

**Acceptance Criteria:**
- [ ] An image reference whose `image` is not a directory under the (lane or explicit) project yields an error naming the yaml path, the parameter, the image and the project.
- [ ] An image reference whose `repository` is not one of that project's configured repository names yields an error naming the repository.
- [ ] A reference whose `project:` is not a directory in the tree is skipped (no error).
- [ ] Projects under a release tree are skipped; `_shared/` templates are not scanned directly (they render through the symlinked per-major projects via `_load_qa_lanes`).
- [ ] `project verify --offline` still runs the new check (it is static).
- [ ] `venv/bin/python -m percona_obs -R isv:percona project verify --offline` on the real tree exits 0 (before and after Task 7).

**Verify:** `venv/bin/pytest tests/test_project_verify_qa_images.py tests/test_project_verify_offline.py -v` → all PASS; black + pyright clean.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_project_verify_qa_images.py
"""`project verify` validates qa: image references against the tree."""

from pathlib import Path

import percona_obs.cmd_project as cmd_project
import percona_obs.common as common

_PROJECT = """\
title: C
repositories:
  - name: ubi9
    arch: [x86_64]
    paths:
      - project: RedHat:UBI-9
        repository: standard
qa:
  pipeline: p
  parameters:
    REPOSITORY:
      image: {image}
      repository: {repository}
      {project_line}
"""


def _tree(tmp_path, monkeypatch, image="img", repository="ubi9", project_line=""):
    root = tmp_path / "root"
    proj = root / "ppg" / "staging" / "c"
    (proj / "img").mkdir(parents=True)
    (proj / "img" / "package.yaml").write_text("title: img\n")
    (root / "macros.yaml").write_text("- M: 1\n")
    (root / "project.yaml").write_text("title: R\nname: isv:percona\n")
    (proj / "project.yaml").write_text(
        _PROJECT.format(image=image, repository=repository, project_line=project_line)
    )
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_project.common, "REPO_ROOT", root)
    return root


def _errors(root):
    return [msg for _p, msg in cmd_project._validate_qa_image_refs(root, {})]


def test_valid_reference_passes(tmp_path, monkeypatch):
    assert _errors(_tree(tmp_path, monkeypatch)) == []


def test_unknown_image_is_reported(tmp_path, monkeypatch):
    errs = _errors(_tree(tmp_path, monkeypatch, image="nope"))
    assert len(errs) == 1
    assert "REPOSITORY" in errs[0] and "nope" in errs[0] and "ppg:staging:c" in errs[0]


def test_unknown_repository_is_reported(tmp_path, monkeypatch):
    errs = _errors(_tree(tmp_path, monkeypatch, repository="ubi8"))
    assert len(errs) == 1
    assert "ubi8" in errs[0]


def test_project_outside_the_tree_is_skipped(tmp_path, monkeypatch):
    errs = _errors(
        _tree(tmp_path, monkeypatch, project_line="project: ppg:staging:15:extras:containers")
    )
    assert errs == []


def test_explicit_project_in_tree_is_checked(tmp_path, monkeypatch):
    root = _tree(tmp_path, monkeypatch, project_line="project: ppg:staging:d")
    other = root / "ppg" / "staging" / "d"
    other.mkdir()
    (other / "project.yaml").write_text(
        "title: D\nrepositories:\n  - name: ubi8\n    arch: [x86_64]\n"
    )
    errs = _errors(root)
    # image `img` is not a package of ppg:staging:d, and ubi9 is not its repo
    assert len(errs) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_project_verify_qa_images.py -v`
Expected: FAIL with `AttributeError: module 'percona_obs.cmd_project' has no attribute '_validate_qa_image_refs'`

- [ ] **Step 3: Append `image_ref_errors` to `percona_obs/qa_images.py`**

```python
def image_ref_errors(
    entry: dict[str, Any],
    lane_project: str,
    project_dir: Callable[[str], Any],
    repositories_of: Callable[[Any], set[str]],
) -> list[str]:
    """Static checks for every image reference of one qa entry.

    *project_dir(project)* returns the tree directory of a colon-notation
    project (a ``pathlib.Path``); *repositories_of(dir)* its configured
    repository names.  A reference whose project is not a directory in the
    tree is skipped: it may exist only on OBS (e.g. a previous major whose
    tree was removed), and ``_validate_repo_path_refs`` applies the same rule.
    """
    errors: list[str] = []
    for name, value in (entry.get("parameters") or {}).items():
        if not is_image_ref(value):
            continue
        project = value.get("project") or lane_project
        pdir = project_dir(project)
        if not (pdir / "project.yaml").is_file():
            continue
        image = value["image"]
        if not (pdir / image).is_dir():
            errors.append(
                f"qa.parameters.{name}: image '{image}' is not a package of "
                f"project '{project}'"
            )
        repository = value["repository"]
        if repository not in repositories_of(pdir):
            errors.append(
                f"qa.parameters.{name}: repository '{repository}' is not defined "
                f"by project '{project}'"
            )
    return errors
```

- [ ] **Step 4: Add `_validate_qa_image_refs` to `percona_obs/cmd_project.py`** (after `_validate_env_vars`)

```python
def _validate_qa_image_refs(
    root: Path, env_vars: "dict[str, str] | None"
) -> list[tuple[Path, str]]:
    """Check that qa: image references name packages/repositories in the tree.

    Loads each project's QA lanes the way `qa show` does (project block plus
    package blocks, `_shared/` reached through the per-major links) and runs
    the static checks of ``qa_images.image_ref_errors``.  Release trees are
    skipped like the other validators.  Loader errors (a malformed block)
    are reported against the project.yaml; unresolved ``${VAR}`` tokens are
    already reported by ``_validate_env_vars`` and are not repeated here.
    """
    from .cmd_qa import _load_qa_lanes  # cmd_qa imports this module
    from .qa_images import image_ref_errors

    errors: list[tuple[Path, str]] = []
    configs: dict[Path, set[str]] = {}

    def repositories_of(pdir: Path) -> set[str]:
        if pdir not in configs:
            cfg = _load_project_config_with_inheritance(pdir, env_vars)
            configs[pdir] = {r["name"] for r in cfg.get("repositories", []) or []}
        return configs[pdir]

    for yaml_path in _project_yaml_files(root):
        proj = yaml_path.parent
        if _is_under_release_project(proj) or proj == common.REPO_ROOT:
            continue
        project = ":".join(proj.relative_to(common.REPO_ROOT).parts)
        try:
            lanes = _load_qa_lanes(project, env_vars or {})
        except SystemExit as exc:
            msg = str(exc)
            if "${" in msg or "unresolv" in msg.lower():
                continue  # reported by _validate_env_vars
            errors.append((yaml_path, msg.removeprefix("error: ")))
            continue
        for lane in lanes:
            for entry in lane.entries:
                for msg in image_ref_errors(
                    entry, project, resolve_project_path, repositories_of
                ):
                    where = f"{lane.package}: " if lane.package else ""
                    errors.append((yaml_path, where + msg))
    return errors
```

`resolve_project_path`, `_load_project_config_with_inheritance` (both in the `from .common import (...)` block) and `from . import common` are already imported in `cmd_project.py`; nothing to add.

- [ ] **Step 5: Wire into `cmd_project_verify`**

After `env_errors = _validate_env_vars(scan_root, env_vars)` add:

```python
    qa_image_errors = _validate_qa_image_refs(scan_root, env_vars)
```

After the `path_ref_errors` printing loop add:

```python
    for yaml_path, msg in qa_image_errors:
        rel = yaml_path.relative_to(REPO_ROOT.parent)
        print(f"error: {rel}: {msg}", file=sys.stderr)
```

And extend the exit condition:

```python
    if (
        ref_errors
        or repo_path_errors
        or env_errors
        or scm_errors
        or path_ref_errors
        or qa_image_errors
    ):
        sys.exit(1)
```

In `tests/test_project_verify_offline.py::_stub_validators`, add `"_validate_qa_image_refs"` to the tuple of stubbed names.

- [ ] **Step 6: Run the tests and the real tree**

Run: `venv/bin/pytest tests/test_project_verify_qa_images.py tests/test_project_verify_offline.py -v`
Expected: all PASS

Run: `venv/bin/python -m percona_obs -R isv:percona -e 'REMOTE_OBS_ORG_INTERCONNECT:' project verify --offline`
Expected: exit 0 (no image references in the tree yet).

- [ ] **Step 7: Format, type-check, commit**

```bash
venv/bin/black percona_obs/ && venv/bin/pyright && venv/bin/pytest tests/ -q
git add percona_obs/qa_images.py percona_obs/cmd_project.py tests/test_project_verify_qa_images.py tests/test_project_verify_offline.py
git commit -s -m "project verify: check qa image references against the tree"
```

---

### Task 5: CI plumbing — PR profiles carry the fallback rootprj

**Goal:** PR runs (`obs-pr-check.yml`, and `obs-qa-run.yml` with `pr_number`) resolve image references against the PR project with the instance's production root as fallback; the nightly and production dispatches are untouched; the decisions show up in the job logs.

**Files:**
- Modify: `.github/scripts/resolve_qa_instance.py` (~line 143-150, outputs dict)
- Modify: `.github/scripts/list_qa_matrix.py` (~line 134-144, after the `subprocess.run`)
- Modify: `.github/workflows/obs-pr-check.yml` (detect-qa-matrix "Write CI profile" ~line 629-660; merge-qa-matrix jq ~line 774-782; qa job "Write CI profile" ~line 845-870)
- Modify: `.github/workflows/obs-qa-run.yml` (resolve outputs ~line 86-92; both "Write CI profile" steps ~line 140-160 and ~line 227-250)
- Test: `tests/test_list_qa_matrix.py`, `tests/test_manual_qa_scripts.py` (the resolver script's existing test module; add one test)

**Acceptance Criteria:**
- [ ] `resolve_qa_instance.py` writes `instance_rootprj=<instance rootprj>` to `$GITHUB_OUTPUT` for both PR and production dispatches, and `rootprj` keeps its current meaning.
- [ ] `list_qa_matrix.py` prints `qa show`'s stderr to its own stderr on success (prefixed per project), so the decisions are in the detect log.
- [ ] In `obs-pr-check.yml`, both PR CI profiles contain `image-fallback-rootprj: <matrix.instance.rootprj>`; the merged matrix carries `instance_rootprj`.
- [ ] In `obs-qa-run.yml`, both CI profiles contain the key only when `inputs.pr_number` is non-empty.
- [ ] `obs-nightly-qa.yml` is unchanged.
- [ ] `yamllint`-free sanity: `python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/obs-pr-check.yml .github/workflows/obs-qa-run.yml` exits 0.

**Verify:** `venv/bin/pytest tests/test_list_qa_matrix.py tests/test_manual_qa_scripts.py -v` → all PASS; the YAML parse one-liner exits 0.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_list_qa_matrix.py`:

```python
def test_qa_show_stderr_is_forwarded(monkeypatch, capsys, tmp_path):
    """Image-reference decisions are printed by `qa show` on stderr; the detect
    job must show them, so a successful run's stderr is forwarded."""
    import subprocess
    from types import SimpleNamespace

    m = _load()
    monkeypatch.setenv("OBS_APIURL", "http://obs")
    monkeypatch.setenv("OBS_PROJECT", "isv:percona:PR:pr-1")
    monkeypatch.delenv("QA_TYPES", raising=False)
    monkeypatch.delenv("QA_PACKAGES_PRESENT_ONLY", raising=False)
    monkeypatch.setattr("osc.conf.get_config", lambda **k: None)
    monkeypatch.setattr(
        "percona_obs.obs_api._fetch_obs_subproject_names",
        lambda apiurl, root: {"isv:percona:PR:pr-1:ppg:staging:18:containers"},
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=0,
            stdout='[{"project":"ppg:staging:18:containers","package":"","name":"ubi9"}]',
            stderr="  image x (ppg:staging:18:containers) → REPOSITORY = r  [fallback: not in p]\n",
        ),
    )
    m.main()
    captured = capsys.readouterr()
    assert "fallback" in captured.err
    assert "ppg:staging:18:containers" in captured.err
```

In `tests/test_manual_qa_scripts.py`, find the existing test that runs `resolve_qa_instance.py::main` with a fake `GITHUB_OUTPUT` and add next to it:

```python
def test_resolver_emits_instance_rootprj_for_pr_and_production(tmp_path, monkeypatch):
    """`instance_rootprj` is the production root in both modes; `rootprj` keeps
    its meaning (PR subproject when pr_number is set)."""
    import json as _json

    mod = _load("resolve_qa_instance")  # this module's existing script loader
    instances = [
        {
            "name": "labs",
            "apiurl": "https://obs.example",
            "rootprj": "isv:percona",
            "pr_rootprj": "isv:percona:PR",
            "include_repos": "UBI_*,ubi*,images",
            "qa_types": "containers",
        }
    ]
    for pr, expected_root in (("", "isv:percona"), ("7", "isv:percona:PR:pr-7")):
        out = tmp_path / f"out-{pr or 'prod'}"
        out.write_text("")
        monkeypatch.setenv("OBS_INSTANCES", _json.dumps(instances))
        monkeypatch.setenv("QA_PROJECT", "ppg:staging:18:containers")
        monkeypatch.setenv("QA_PR_NUMBER", pr)
        monkeypatch.setenv("QA_PACKAGE", "")
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        mod.main()
        lines = dict(l.split("=", 1) for l in out.read_text().splitlines())
        assert lines["instance_rootprj"] == "isv:percona"
        assert lines["rootprj"] == expected_root
```

`tests/test_manual_qa_scripts.py` already defines `_load(name)` (importlib loader over `.github/scripts/<name>.py`) and tests `resolve_qa_instance`; place the new test after `test_resolve_ambiguous_fails`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_list_qa_matrix.py tests/test_manual_qa_scripts.py -v -k "forwarded or instance_rootprj"`
Expected: FAIL (`KeyError: 'instance_rootprj'`; the forwarded-stderr assertion fails).

- [ ] **Step 3: Scripts**

`.github/scripts/resolve_qa_instance.py`, in the `outputs` dict add:

```python
        "instance_rootprj": str(inst.get("rootprj", "") or ""),
```

and extend the module docstring line that lists the outputs with `instance_rootprj -- the instance's production root, in both modes (fallback for qa: image references)`.

`.github/scripts/list_qa_matrix.py`, right after the `if result.returncode != 0:` block (which `continue`s), add:

```python
        if result.stderr.strip():
            # `qa show` reports image-reference decisions (which rootprj each
            # image path got) on stderr; keep them in the detect log.
            for line in result.stderr.rstrip().splitlines():
                print(f"  {project}: {line.strip()}", file=sys.stderr)
```

- [ ] **Step 4: `obs-pr-check.yml`**

In the `detect-qa-matrix` job's "Write CI profile" step, add to `env:`:

```yaml
          OBS_MAIN_ROOTPRJ: ${{ matrix.instance.rootprj }}
```

and in the heredoc, after the `${OBS_REGISTRY:+registry: ${OBS_REGISTRY}}` line:

```yaml
          image-fallback-rootprj: ${OBS_MAIN_ROOTPRJ}
```

In `merge-qa-matrix`'s jq program, after `instance_registry: ($i.registry // ""),` add:

```
                  instance_rootprj: ($i.rootprj // ""),
```

In the `qa` job's "Write CI profile" step, add to `env:`:

```yaml
          OBS_MAIN_ROOTPRJ: ${{ matrix.instance_rootprj }}
```

and the same `image-fallback-rootprj: ${OBS_MAIN_ROOTPRJ}` line after the registry line. Update the comment above that step ("same registry → same ${OBS_CONTAINER_REGISTRY}") to also say "same fallback root → same image-reference decisions".

- [ ] **Step 5: `obs-qa-run.yml`**

In the `resolve` job outputs add:

```yaml
      instance_rootprj: ${{ steps.resolve.outputs.instance_rootprj }}
```

In both "Write CI profile" steps (detect and run), add to `env:`:

```yaml
          OBS_MAIN_ROOTPRJ: ${{ needs.resolve.outputs.instance_rootprj }}
          QA_PR_NUMBER: ${{ inputs.pr_number }}
```

and after the registry line in each heredoc:

```yaml
          ${QA_PR_NUMBER:+image-fallback-rootprj: ${OBS_MAIN_ROOTPRJ}}
```

Add a comment above: `# PR dispatches test the PR subproject; images that were not promoted there live under the production root, so qa: image references fall back to it.`

- [ ] **Step 6: Run the tests and parse the workflows**

Run: `venv/bin/pytest tests/test_list_qa_matrix.py tests/test_manual_qa_scripts.py -v`
Expected: all PASS

Run: `venv/bin/python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/obs-pr-check.yml .github/workflows/obs-qa-run.yml && echo ok`
Expected: `ok`

Run: `git diff --stat -- .github/workflows/obs-nightly-qa.yml`
Expected: empty.

- [ ] **Step 7: Commit**

```bash
git add .github/scripts/resolve_qa_instance.py .github/scripts/list_qa_matrix.py .github/workflows/obs-pr-check.yml .github/workflows/obs-qa-run.yml tests/test_list_qa_matrix.py tests/test_manual_qa_scripts.py
git commit -s -m "ci: PR QA profiles carry image-fallback-rootprj; log image decisions"
```

---

### Task 6: Documentation

**Goal:** The `qa:` schema, the decision rule and the profile key are documented where the existing QA and profile docs live.

**Files:**
- Modify: `docs/PERCONA_OBS_TOOL.md` (`### \`qa:\` block schema` ~line 717; the sentence "The tool never calls OBS for QA." ~line 740; the `${VAR}` paragraph ~line 829; the profile section ~line 61-140)
- Modify: `.github/copilot-instructions.md` (profile example ~line 240-254)

**Acceptance Criteria:**
- [ ] The schema block shows an image reference with all three keys and their meaning.
- [ ] A new subsection `#### Image references` states the decision table from *Design*, the rendered path format, that lists/matrix axes cannot hold references, and the `WITH_POSTGIS` limitation.
- [ ] "The tool never calls OBS for QA." is replaced by: "The tool calls OBS from `qa show` / `qa run` only to resolve image references when `image-fallback-rootprj` is set (one package listing per project)."
- [ ] The profile section documents `image-fallback-rootprj` (and the `--image-fallback-rootprj` flag), stating CI writes it into PR profiles only.
- [ ] `copilot-instructions.md`'s profile example gains the key with a one-line comment.

**Verify:** `grep -n "image-fallback-rootprj" docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md` → at least 3 hits; `grep -c "never calls OBS for QA" docs/PERCONA_OBS_TOOL.md` → 0.

**Steps:**

- [ ] **Step 1: Schema block** — extend the YAML in `### \`qa:\` block schema`:

```yaml
    IMAGE_PARAM:                        # image reference: rendered to a registry path
      image: percona-pgbouncer          #   OBS package name of the image (required)
      repository: ubi9                  #   OBS repository = last path segment (required)
      project: ppg:staging:18:containers   # defaults to the lane's project
```

- [ ] **Step 2: New subsection** — insert before `#### Status contexts`:

```markdown
#### Image references

A parameter whose value is a mapping with an `image:` key names a container image by
its OBS package; the parameter name is irrelevant (`REPOSITORY`, `OLD_DOCKER_REPOSITORY`,
…). `qa show` / `qa run` render it to
`<OBS_CONTAINER_REGISTRY>/<rootprj>/<project>/<repository>` (colons → `/`, lower-cased)
and choose the root project per image:

| `image-fallback-rootprj` set? | image listed in `<rootprj>:<project>` on OBS? | root used |
|---|---|---|
| no | not queried | the current rootprj |
| yes | yes (promoted into the PR project) | the current rootprj |
| yes | no | the fallback rootprj |

PR projects hold only promoted packages, and the registry publishes an image only under
the project that built it, so a PR that promotes one image must still pull its siblings
from the production root. CI writes `image-fallback-rootprj: <production root>` into the PR
profiles; the nightly and production dispatches have no fallback and never query OBS.
Each decision is printed on stderr (`image <pkg> (<project>) → <PARAM> = <path> [present|fallback|no-fallback: …]`).
`project verify` checks that `image` is a package directory of `project` and that
`repository` is one of its repositories (references to projects not in the tree are skipped).

Image references are not allowed inside list values, so they cannot be matrix axes. A lane
whose pipeline picks the image from an axis (`docker-server-parallel` appends
`-with-postgis` when `WITH_POSTGIS=true`) names one image; when only the other one was
promoted, that lane tests the fallback image.
```

- [ ] **Step 3: Replace the OBS sentence and extend the `${VAR}` paragraph** — replace "The tool never calls OBS for QA." with the sentence from the acceptance criteria; append to the `${VAR}` paragraph: "Image references (mappings with `image:`) are rendered after substitution; see *Image references*."

- [ ] **Step 4: Profile section** — after `### \`registry\`: the container registry host` add:

```markdown
### `image-fallback-rootprj`: where unpromoted images live

`qa:` image references (see *Image references* under *Triggering Jenkins QA pipelines*)
render against the profile's `rootprj`. When the profile also carries
`image-fallback-rootprj: isv:percona`, an image that the current root project does not
hold is rendered against that root instead. CI writes the key into PR profiles only
(`obs-pr-check.yml`, `obs-qa-run.yml` with a PR number); `--image-fallback-rootprj ROOTPRJ`
overrides it on the command line. Setting it makes `qa show` / `qa run` list the packages
of each referenced project once.
```

- [ ] **Step 5: `copilot-instructions.md`** — in the profile example add after the `registry:` lines:

```yaml
# image-fallback-rootprj: isv:percona  # PR profiles only: root that holds images the PR did not promote
```

and append to the **Container registry.** paragraph: "`qa:` parameters may name an image (`image:`/`repository:`/`project:` mapping) instead of spelling the path; `percona_obs/qa_images.py` renders it against `rootprj`, or against the profile's `image-fallback-rootprj` when the current root does not hold the package."

- [ ] **Step 6: Commit**

```bash
git add docs/PERCONA_OBS_TOOL.md .github/copilot-instructions.md
git commit -s -m "docs: qa image references and image-fallback-rootprj"
```

---

### Task 7: Convert the container lanes in the tree to image references

**Goal:** Every `REPOSITORY` / `OLD_DOCKER_REPOSITORY` in the staging container projects names its image, so PR runs stop pointing at registry paths that do not exist.

**Files:**
- Modify: `root/ppg/staging/_shared/containers/project.yaml` (3 lanes, lines ~152/165/178)
- Modify: `root/ppg/staging/common/containers/project.yaml` (3 lanes, lines ~178/191/204)
- Modify: `root/ppg/staging/common/extras/containers/project.yaml` (1 lane, line ~78)
- Modify: `root/ppg/staging/16/extras/containers/project.yaml`, `root/ppg/staging/17/extras/containers/project.yaml`, `root/ppg/staging/18/extras/containers/project.yaml` (2 lanes each: lines ~66, ~75, ~79)
- Test: `tests/test_container_registry.py` (extend the tree test)

**Acceptance Criteria:**
- [ ] `grep -rn 'OBS_CONTAINER_REGISTRY' root/ppg/staging --include=project.yaml` returns no lines (all string forms converted; release trees are not touched and contain none today).
- [ ] For every converted lane, `qa show <project> --json` run with `-R isv:percona` and no fallback renders exactly the string the old form rendered (compare against `git stash`-ed output, see Step 3).
- [ ] `venv/bin/python -m percona_obs -R isv:percona -e 'REMOTE_OBS_ORG_INTERCONNECT:' project verify --offline` exits 0.
- [ ] `tests/test_container_registry.py::test_tree_has_no_hardcoded_registry_in_rootprj_urls` is extended to also assert no non-release `project.yaml` contains `${OBS_CONTAINER_REGISTRY}`.

**Verify:** the three commands above plus `venv/bin/pytest tests/ -q` → all PASS.

**Steps:**

- [ ] **Step 1: Record the baseline rendering** (before editing):

```bash
for p in ppg:staging:18:containers ppg:staging:17:containers ppg:staging:16:containers \
         ppg:staging:common:containers ppg:staging:common:extras:containers \
         ppg:staging:18:extras:containers ppg:staging:17:extras:containers ppg:staging:16:extras:containers; do
  venv/bin/python -m percona_obs -R isv:percona -e 'REMOTE_OBS_ORG_INTERCONNECT:' qa show "$p" --json \
    | venv/bin/python -c 'import json,sys; [print(e["status_context"], k, v) for e in json.load(sys.stdin) for k,v in sorted(e["params"].items()) if "REPOSITORY" in k]'
done > /tmp/claude-1000/qa-baseline.txt 2>/dev/null
wc -l /tmp/claude-1000/qa-baseline.txt
```

(Use the session scratchpad directory instead of `/tmp/claude-1000` if one is listed. `qa show` initialises osc, so an oscrc must exist; `-P <profile>` with a `rootprj: isv:percona` profile works equally and needs no OBS traffic without a fallback.)

- [ ] **Step 2: Edit the YAML**

`root/ppg/staging/_shared/containers/project.yaml`, for each of the three lanes replace

```yaml
      REPOSITORY: ${OBS_CONTAINER_REGISTRY}/${OBS_CONTAINER_REGISTRY_ROOTPRJ}/ppg/staging/%!{PG_MAJOR_VERSION}/containers/ubi8
```

with (same for `ubi9`, `ubi10`):

```yaml
      REPOSITORY:
        image: percona-distribution-postgresql   # WITH_POSTGIS=true appends -with-postgis in Jenkins
        repository: ubi8
```

`root/ppg/staging/common/containers/project.yaml`, three lanes:

```yaml
      REPOSITORY:
        image: percona-distribution-postgresql-upgrade
        repository: ubi8          # ubi9 / ubi10 in the other two lanes
```

`root/ppg/staging/common/extras/containers/project.yaml`:

```yaml
    REPOSITORY:
      image: percona-distribution-postgresql-upgrade-custom
      repository: ubi9
```

`root/ppg/staging/{16,17,18}/extras/containers/project.yaml`, first lane (`docker-server-parallel-generic`) and the `ppg-obs-upgrade` lane's `REPOSITORY`:

```yaml
      REPOSITORY:
        image: percona-distribution-postgresql-custom
        repository: ubi9
```

and the `ppg-obs-upgrade` lane's `OLD_DOCKER_REPOSITORY` (previously hard-coded to `isv/percona`, i.e. always production; with the fallback it still resolves to production unless the PR promoted the previous major's custom image):

```yaml
      OLD_DOCKER_REPOSITORY:
        image: percona-distribution-postgresql-custom
        project: ppg:staging:%!{PG_PREV_MAJOR_VERSION}:extras:containers
        repository: ubi9
```

Keep the indentation of each file (the extras files use a list under `qa:` with 6-space parameter indent; `common/extras` uses a single mapping with 4-space indent). Do not touch any `project.yaml` under `root/ppg/releases/`.

- [ ] **Step 3: Compare the rendering against the baseline**

Re-run the Step 1 loop into `/tmp/claude-1000/qa-after.txt` and:

```bash
diff /tmp/claude-1000/qa-baseline.txt /tmp/claude-1000/qa-after.txt && echo identical
```

Expected: `identical`. (On the production root, with the default registry and no fallback, image references render byte-for-byte the old strings; `OLD_DOCKER_REPOSITORY` renders `registry.opensuse.org/isv/percona/ppg/staging/<prev>/extras/containers/ubi9` in both.)

- [ ] **Step 4: Verify the tree and extend the tree test**

Run: `venv/bin/python -m percona_obs -R isv:percona -e 'REMOTE_OBS_ORG_INTERCONNECT:' project verify --offline`
Expected: exit 0. (`16/extras` references `ppg:staging:15:extras:containers`, which is not in the tree and is skipped.)

In `tests/test_container_registry.py::test_tree_has_no_hardcoded_registry_in_rootprj_urls`, extend the offender condition so a file is also an offender when `"${OBS_CONTAINER_REGISTRY}" in text`, and update the docstring: "The non-release tree names images with image references; no lane spells a registry path."

Run: `venv/bin/pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add root/ppg/staging tests/test_container_registry.py
git commit -s -m "containers: name QA images with image references instead of registry paths"
```

---

## Rollout notes (not tasks)

- PR #124 edits the same `qa:` blocks (new `docker-server-parallel` / `docker-component-parallel` lanes). Whichever lands second rebases: if this plan lands first, #124's new lanes should use image references (`percona-pgbackrest`, `percona-pgbouncer` in `ppg:staging:common:tools:containers`, server images as above); if #124 lands first, Task 7 converts its lanes too.
- First PR run after merge: check the detect-qa-matrix log for the `image … [present|fallback: …]` lines and that the labs lane's rendered paths exist in the registry (`obs.pg.labs.percona.com/isv/percona/...` for fallback, `.../isv/percona/pr/pr-N/...` for promoted).
- The `OBS_INSTANCES` variable needs no change: `rootprj` is already present per instance.
