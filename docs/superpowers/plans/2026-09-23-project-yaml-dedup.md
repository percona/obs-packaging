# project.yaml Merge-Based Inheritance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace whole-field inheritance of `repositories`/`project-config` with root-to-leaf merge semantics so every `project.yaml` under `root/` holds only its delta, with zero effective change on OBS.

**Architecture:** A new module `percona_obs/project_config.py` folds `project.yaml` and tier-level `subprojects.yaml` layers from `root/` down to the target project; `common._load_project_config_with_inheritance` becomes an alias so all existing consumers switch at once. A throwaway gate script renders every non-release project before and after the yaml rewrite and compares meta XML byte-for-byte and prjconf per repository as effective line sets.

**Tech Stack:** Python 3 (`percona_obs/` package), PyYAML, pytest (`tests/`), black, pyright. All commands run from the worktree root `/home/rdias/Work/percona-obs-packaging/.claude/worktrees/project-yaml-dedup` with `venv/bin/...`.

**Spec:** `docs/superpowers/specs/2026-09-23-project-yaml-dedup-design.md` (read it first; Section 1 is the contract every task implements).

## Global Constraints

- **Never touch `root/ppg/releases/<V>/**`.** The only permitted new file under `root/ppg/releases/` is `root/ppg/releases/subprojects.yaml` containing `standalone: true`.
- **The gate must pass** (`gate.py check`, Task 0) after Task 4 and Task 5 with only the allowlisted difference: the package-less `root`, `root/ppg/staging` and `root/ppg/devel` projects lose `Prefer: libverto-libev` and `Prefer: Lmod` (the `root/ppg/releases` tier loses them too but the gate skips everything under `releases/`). Never widen the allowlist to make it pass; fix the yaml instead.
- **Meta XML byte-identical for every non-release project.** Path order inside a repository is semantic in OBS. Repository element order must not change either.
- **Provenance header format is exactly** `# --- from <repo-relative path> ---` (e.g. `# --- from root/ppg/staging/subprojects.yaml ---`), one blank line between contributions.
- **Substitution stays text-level**: `%!{}` then `${}` on the raw file text before YAML parsing. Ancestor layers use `strict=False`; the target's own `project.yaml` uses `strict=True`.
- **Every commit:** `venv/bin/black percona_obs/` then `venv/bin/pyright` must both pass before committing. Use `git commit -s`. No `Co-Authored-By` lines (CLAUDE.md rule).
- **Never `git push`, never open a PR** (user rule). The user does that.
- Errors from the resolver are `SystemExit("error: <repo-relative file>: <message>")`, matching the rest of the tool.

**User decisions (already made):**
- Main pain to remove is drift (one place to edit), not onboarding cost or diff size.
- Releases stay materialized snapshots; only live tiers are deduplicated.
- Approach A (merge semantics on inheritance) over include-fragments or templates.
- Prepend-by-default for repository paths; `debuginfo`/`publish`/`build` join the inherited set.
- Generated prjconf carries a provenance comment per contribution.
- `project render` is delivered as flags on the existing `project config` command (planning amendment, spec §Amendments 4).

---

## File Structure

| File | Responsibility |
|---|---|
| `percona_obs/project_config.py` (new) | The resolver: chain discovery, layer loading, merge rules, provenance rendering, validation errors. No OBS or CLI knowledge. |
| `percona_obs/common.py` | `apply_macro_substitution(strict=)`; `_load_project_config_with_inheritance` becomes an alias to the resolver. |
| `percona_obs/cmd_project.py` | Four plain-loader call sites switch to the resolver; `project config` gains `--resolved` / `--diff`. |
| `percona_obs/cli.py` | Two new flags on the `project config` parser. |
| `tests/test_project_config_merge.py` (new) | Fixture-tree tests for every merge rule. |
| `tests/test_project_release.py` | One new test: delta source → materialized release mirror. |
| `root/**/project.yaml`, `root/ppg/{staging,devel,releases}/subprojects.yaml` | The data rewrite. |
| `.github/copilot-instructions.md`, `docs/PERCONA_OBS_TOOL.md`, `root/README.md` | Documentation. |
| scratchpad `gate.py` | Throwaway migration gate (not committed). |

---

### Task 0: Migration gate script and baseline capture

**Goal:** Capture, before any change, the rendered meta XML and per-repository effective prjconf of all 40 non-release projects, and have a `check` mode that fails on any non-allowlisted difference.

**Files:**
- Create: `/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/f9f9945b-a972-4e60-b125-3021ee36cb33/scratchpad/gate.py` (throwaway; if that directory does not exist, create any scratch directory outside the repo and use it consistently in later tasks)
- Create: `<scratchpad>/gate-baseline/*.json` (40 files)

**Acceptance Criteria:**
- [ ] `gate.py capture <dir>` prints `captured 40 projects into <dir>`
- [ ] `gate.py check <dir>` on the unchanged tree prints `GATE PASSED` and exits 0
- [ ] `gate.py effective root/ppg/staging/17 openSUSE_Tumbleweed` lists exactly 6 lines (`Ignore: postgresql`, `Ignore: postgresql-server`, `Ignore: postgresql18-server`, `Prefer: percona-postgresql17-server`, `Prefer: python313-python-dateutil`, `Prefer: python313-six`)

**Verify:** `venv/bin/python <scratchpad>/gate.py check <scratchpad>/gate-baseline` → `GATE PASSED`

**Steps:**

- [ ] **Step 1: Write the gate script**

```python
"""Throwaway migration gate for the project.yaml dedup (not committed).

  gate.py capture <dir>                      render every non-release project into <dir>/<proj>.json
  gate.py check   <dir> [--allow-loss L1;L2 --allow-projects P1,P2]
                                             re-render and compare; exit 1 on any non-allowlisted difference
  gate.py effective <project-dir> [<repo>]   print the effective prjconf lines per repository

Per project:
  * meta XML (build_project_meta, rootprj "ROOT", env vars unsubstituted) must be byte-identical.
  * prjconf is compared per repository as a sorted multiset of *effective* lines: comments and
    blank lines dropped, `%if "%_repository" == "A" || ...` blocks kept only for the repositories
    they name.  Block order and provenance comments are therefore irrelevant.
  * --allow-loss lists lines (';'-separated) that the projects in --allow-projects (','-separated,
    repo-relative like root/ppg/staging) may lose.  Nothing else is tolerated.
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")
from percona_obs.common import (  # noqa: E402
    REPO_ROOT,
    _is_release_dir,
    _load_project_config_with_inheritance,
    build_project_meta,
)

_IF_RE = re.compile(r"^%if\s+(.*)$")
_REPO_RE = re.compile(r'"%_repository"\s*==\s*"([^"]+)"')


def _is_release(p: Path) -> bool:
    return any(
        _is_release_dir(a) or a.name == "releases"
        for a in [p, *p.parents]
        if a.is_relative_to(REPO_ROOT)
    )


def project_dirs() -> list[Path]:
    return sorted(
        p.parent for p in REPO_ROOT.rglob("project.yaml") if not _is_release(p.parent)
    )


def effective_prjconf(text: str, repo_names: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {r: [] for r in repo_names}
    active: "set[str] | None" = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _IF_RE.match(line)
        if m:
            if active is not None:
                raise SystemExit(f"nested %if not supported: {line}")
            names = _REPO_RE.findall(m.group(1))
            if not names or len(names) != m.group(1).count("=="):
                raise SystemExit(f"unsupported %if form: {line}")
            active = set(names)
            continue
        if line == "%endif":
            active = None
            continue
        if line.startswith("%else") or line.startswith("%elif"):
            raise SystemExit(f"unsupported directive: {line}")
        for r in repo_names:
            if active is None or r in active:
                out[r].append(line)
    if active is not None:
        raise SystemExit("unterminated %if")
    return {r: sorted(v) for r, v in out.items()}


def render(p: Path) -> dict:
    cfg = _load_project_config_with_inheritance(p, None)
    obs_name = "ROOT" if p == REPO_ROOT else "ROOT:" + ":".join(p.relative_to(REPO_ROOT).parts)
    repos = cfg.get("repositories", [])
    meta = build_project_meta(
        obs_name,
        cfg.get("title", ""),
        cfg.get("description", ""),
        repos,
        "ROOT",
        publish=cfg.get("publish"),
        build=cfg.get("build"),
        debuginfo=cfg.get("debuginfo"),
    )
    return {
        "meta": meta,
        "prjconf": effective_prjconf(cfg.get("project-config") or "", [r["name"] for r in repos]),
    }


def _key(p: Path) -> str:
    return "__".join(p.relative_to(REPO_ROOT.parent).parts)


def capture(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    dirs = project_dirs()
    for p in dirs:
        (out / f"{_key(p)}.json").write_text(json.dumps(render(p), indent=1, sort_keys=True))
    print(f"captured {len(dirs)} projects into {out}")


def check(base: Path, allow_loss: set[str], allow_projects: set[str]) -> None:
    bad = 0
    seen: set[str] = set()
    for p in project_dirs():
        f = base / f"{_key(p)}.json"
        seen.add(f.name)
        rel = p.relative_to(REPO_ROOT.parent).as_posix()
        if not f.is_file():
            print(f"NEW PROJECT (no baseline): {rel}")
            bad += 1
            continue
        want = json.loads(f.read_text())
        got = render(p)
        if got["meta"] != want["meta"]:
            bad += 1
            print(f"META DIFFERS: {rel}")
            for l in difflib.unified_diff(
                want["meta"].splitlines(), got["meta"].splitlines(), "baseline", "now", lineterm="", n=1
            ):
                print("   ", l)
        if got["prjconf"] != want["prjconf"]:
            tolerated = True
            lines = []
            for r in sorted(set(want["prjconf"]) | set(got["prjconf"])):
                a, b = want["prjconf"].get(r, []), got["prjconf"].get(r, [])
                if a == b:
                    continue
                missing = [x for x in a if x not in b]
                extra = [x for x in b if x not in a]
                if extra or not (rel in allow_projects and set(missing) <= allow_loss):
                    tolerated = False
                lines.append(f"    [{r}] missing={missing} extra={extra}")
            if tolerated:
                print(f"prjconf loss tolerated (allowlist): {rel}")
            else:
                bad += 1
                print(f"PRJCONF DIFFERS: {rel}")
                print("\n".join(lines))
    for f in base.glob("*.json"):
        if f.name not in seen:
            print(f"PROJECT GONE: {f.stem.replace('__', '/')}")
            bad += 1
    print("GATE PASSED" if not bad else f"GATE FAILED ({bad} differences)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["capture", "check", "effective"])
    ap.add_argument("target")
    ap.add_argument("repo", nargs="?")
    ap.add_argument("--allow-loss", default="")
    ap.add_argument("--allow-projects", default="")
    a = ap.parse_args()
    if a.cmd == "capture":
        capture(Path(a.target))
    elif a.cmd == "check":
        check(
            Path(a.target),
            {x for x in a.allow_loss.split(";") if x},
            {x for x in a.allow_projects.split(",") if x},
        )
    else:
        r = render(REPO_ROOT.parent / a.target)["prjconf"]
        for repo in [a.repo] if a.repo else r:
            print(f"[{repo}]")
            for l in r[repo]:
                print("   ", l)
```

- [ ] **Step 2: Capture the baseline and self-check**

Run (from the worktree root, `S` = scratchpad directory):
```bash
S=/tmp/claude-1000/-home-rdias-Work-percona-obs-packaging/f9f9945b-a972-4e60-b125-3021ee36cb33/scratchpad
venv/bin/python $S/gate.py capture $S/gate-baseline
venv/bin/python $S/gate.py check $S/gate-baseline
venv/bin/python $S/gate.py effective root/ppg/staging/17 openSUSE_Tumbleweed
```
Expected: `captured 40 projects …`, `GATE PASSED`, and the 6 lines listed in the acceptance criteria.

- [ ] **Step 3: No commit** (scratchpad only). Record the scratchpad path used; Tasks 4, 5 and 7 need it.

---

### Task 1: Resolver module with merge semantics (TDD)

**Goal:** `percona_obs/project_config.py::resolve_project_config` implements spec Section 1, `common.apply_macro_substitution` gets `strict`, and `common._load_project_config_with_inheritance` delegates to the resolver; all covered by `tests/test_project_config_merge.py`.

**Files:**
- Create: `percona_obs/project_config.py`
- Modify: `percona_obs/common.py` (`apply_macro_substitution` ~line 180; `_load_project_config_with_inheritance` ~line 724)
- Test: `tests/test_project_config_merge.py`

**Acceptance Criteria:**
- [ ] All tests in `tests/test_project_config_merge.py` pass
- [ ] Whole suite passes (`venv/bin/python -m pytest -q tests`) — 279 pre-existing tests plus the new ones
- [ ] `venv/bin/black percona_obs/` and `venv/bin/pyright` pass

**Verify:** `venv/bin/python -m pytest -q tests/test_project_config_merge.py` → all passed

**Note:** after this task `gate.py check` is expected to FAIL on the untouched yaml tree: a child that today lists the same repository names as its parent now gets its paths prepended to the parent's, and its prjconf appended. That is exactly what Tasks 4–5 fix. Run the gate for information only and paste its summary line in the commit message body.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_project_config_merge.py`:

```python
"""Unit tests for percona_obs.project_config (merge-based project.yaml inheritance)."""

import os
from pathlib import Path

import pytest

import percona_obs.common as common
from percona_obs.project_config import resolve_project_config

_ROOT_REPOS = """\
repositories:
  - name: RockyLinux_9
    paths:
      - subproject: common:deps:build
        repository: RockyLinux_9
      - project: ${REMOTE}RockyLinux:9
        repository: standard
    archs: [x86_64, aarch64]
  - name: Debian_12
    paths:
      - project: ${REMOTE}Debian:12
        repository: standard
    archs: [x86_64]
"""

_ROOT_PRJCONF = """\
project-config: |
  %if "%_repository" == "Debian_12"
  Release: <CI_CNT>.<B_CNT>.bookworm
  %endif
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Build root/ from {relpath: text}; a root macros.yaml is always present."""

    def make(files: dict, macros: str = "- ROOT_MACRO: r\n") -> Path:
        root = tmp_path / "root"
        root.mkdir(exist_ok=True)
        (root / "macros.yaml").write_text(macros)
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        monkeypatch.setattr(common, "REPO_ROOT", root)
        return root

    return make


def _names(cfg):
    return [r["name"] for r in cfg["repositories"]]


def _paths(cfg, name):
    repo = next(r for r in cfg["repositories"] if r["name"] == name)
    return [(p.get("subproject") or p.get("project"), p["repository"]) for p in repo["paths"]]


def _directives(cfg):
    return [l for l in cfg["project-config"].splitlines() if l and not l.startswith("#")]


# --- plain inheritance -----------------------------------------------------


def test_child_without_fields_inherits_root_repos_and_prjconf(repo):
    root = repo({"project.yaml": _ROOT_REPOS + _ROOT_PRJCONF, "a/project.yaml": "title: A\n"})
    cfg = resolve_project_config(root / "a")
    assert cfg["title"] == "A"
    assert _names(cfg) == ["RockyLinux_9", "Debian_12"]
    assert _paths(cfg, "RockyLinux_9") == [
        ("common:deps:build", "RockyLinux_9"),
        ("${REMOTE}RockyLinux:9", "standard"),
    ]
    assert cfg["project-config"].startswith("# --- from root/project.yaml ---\n%if")
    assert _directives(cfg) == ['%if "%_repository" == "Debian_12"', "Release: <CI_CNT>.<B_CNT>.bookworm", "%endif"]


def test_missing_project_yaml_resolves_from_ancestors(repo):
    root = repo({"project.yaml": _ROOT_REPOS, "a/obs/_service": ""})
    cfg = resolve_project_config(root / "a")
    assert _names(cfg) == ["RockyLinux_9", "Debian_12"]
    assert "title" not in cfg


# --- project-config --------------------------------------------------------


def test_prjconf_concatenates_with_provenance_headers(repo):
    root = repo(
        {
            "project.yaml": _ROOT_PRJCONF,
            "a/project.yaml": "project-config: |\n\n  Prefer: foo\n\n",
        }
    )
    cfg = resolve_project_config(root / "a")
    assert cfg["project-config"] == (
        "# --- from root/project.yaml ---\n"
        '%if "%_repository" == "Debian_12"\n'
        "Release: <CI_CNT>.<B_CNT>.bookworm\n"
        "%endif\n"
        "\n"
        "# --- from root/a/project.yaml ---\n"
        "Prefer: foo\n"
    )


def test_project_config_inherit_false_discards_ancestors(repo):
    root = repo(
        {
            "project.yaml": _ROOT_PRJCONF,
            "a/project.yaml": "project-config-inherit: false\nproject-config: |\n  Prefer: only\n",
            "a/b/project.yaml": "project-config: |\n  Prefer: child\n",
        }
    )
    assert _directives(resolve_project_config(root / "a")) == ["Prefer: only"]
    # descendants inherit from a onwards, not from root
    assert _directives(resolve_project_config(root / "a" / "b")) == ["Prefer: only", "Prefer: child"]


def test_empty_prjconf_everywhere_leaves_key_absent(repo):
    root = repo({"project.yaml": _ROOT_REPOS, "a/project.yaml": "title: A\n"})
    assert "project-config" not in resolve_project_config(root / "a")


# --- repositories ----------------------------------------------------------


def test_new_repository_with_archs_is_appended(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "repositories:\n  - name: images\n    paths:\n"
                "      - subproject: common:containers:ubi9\n        repository: images\n"
                "    archs: [x86_64]\n"
            ),
        }
    )
    cfg = resolve_project_config(root / "a")
    assert _names(cfg) == ["RockyLinux_9", "Debian_12", "images"]
    assert _paths(cfg, "images") == [("common:containers:ubi9", "images")]


def test_patch_for_unknown_repository_is_an_error(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "repositories:\n  - name: Debian_21\n    paths:\n"
                "      - subproject: x\n        repository: Debian_21\n"
            ),
        }
    )
    with pytest.raises(SystemExit, match=r"root/a/project.yaml: repository 'Debian_21' is not inherited"):
        resolve_project_config(root / "a")


def test_known_repository_paths_are_prepended_and_archs_replaced(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "repositories:\n  - name: RockyLinux_9\n    paths:\n"
                "      - subproject: ppg:common:deps\n        repository: RockyLinux_9\n"
                "  - name: Debian_12\n    archs: [x86_64, aarch64]\n"
                "    paths:\n      - subproject: ppg:common:deps\n        repository: Debian_12\n"
            ),
        }
    )
    cfg = resolve_project_config(root / "a")
    assert _paths(cfg, "RockyLinux_9") == [
        ("ppg:common:deps", "RockyLinux_9"),
        ("common:deps:build", "RockyLinux_9"),
        ("${REMOTE}RockyLinux:9", "standard"),
    ]
    rocky = next(r for r in cfg["repositories"] if r["name"] == "RockyLinux_9")
    assert rocky["archs"] == ["x86_64", "aarch64"]  # inherited
    deb = next(r for r in cfg["repositories"] if r["name"] == "Debian_12")
    assert deb["archs"] == ["x86_64", "aarch64"]  # replaced


def test_paths_replace(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "repositories:\n  - name: RockyLinux_9\n    paths-replace: true\n    paths:\n"
                "      - subproject: only\n        repository: RockyLinux_9\n"
            ),
        }
    )
    assert _paths(resolve_project_config(root / "a"), "RockyLinux_9") == [("only", "RockyLinux_9")]


def test_remove_repository(repo):
    root = repo(
        {"project.yaml": _ROOT_REPOS, "a/project.yaml": "repositories:\n  - name: Debian_12\n    remove: true\n"}
    )
    assert _names(resolve_project_config(root / "a")) == ["RockyLinux_9"]


def test_remove_unknown_repository_is_an_error(repo):
    root = repo(
        {"project.yaml": _ROOT_REPOS, "a/project.yaml": "repositories:\n  - name: Debian_21\n    remove: true\n"}
    )
    with pytest.raises(SystemExit, match=r"cannot remove unknown repository 'Debian_21'"):
        resolve_project_config(root / "a")


def test_remove_with_extra_keys_is_an_error(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": "repositories:\n  - name: Debian_12\n    remove: true\n    archs: [x86_64]\n",
        }
    )
    with pytest.raises(SystemExit, match=r"remove: true entry may only carry 'name'"):
        resolve_project_config(root / "a")


def test_unknown_repository_entry_key_is_an_error(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": "repositories:\n  - name: Debian_12\n    path: []\n",
        }
    )
    with pytest.raises(SystemExit, match=r"unknown key\(s\) \['path'\]"):
        resolve_project_config(root / "a")


def test_repositories_inherit_false(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "repositories-inherit: false\nrepositories:\n  - name: ssl3\n    paths:\n"
                "      - subproject: a\n        repository: RockyLinux_9\n    archs: [x86_64]\n"
            ),
        }
    )
    cfg = resolve_project_config(root / "a")
    assert _names(cfg) == ["ssl3"]
    assert "repositories-inherit" not in cfg


# --- path-prefix -----------------------------------------------------------


def test_path_prefix_applies_to_every_repo_with_token_substitution(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": (
                "path-prefix:\n  - subproject: ppg:staging:17\n    repository: \"%_repository\"\n"
            ),
        }
    )
    cfg = resolve_project_config(root / "a")
    assert _paths(cfg, "RockyLinux_9")[0] == ("ppg:staging:17", "RockyLinux_9")
    assert _paths(cfg, "Debian_12")[0] == ("ppg:staging:17", "Debian_12")
    assert "path-prefix" not in cfg


def test_path_prefix_layers_concatenate_child_first(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/subprojects.yaml": "path-prefix:\n  - subproject: tier\n    repository: \"%_repository\"\n",
            "a/b/project.yaml": "path-prefix:\n  - subproject: leaf\n    repository: \"%_repository\"\n",
        }
    )
    assert _paths(resolve_project_config(root / "a" / "b"), "Debian_12")[:3] == [
        ("leaf", "Debian_12"),
        ("tier", "Debian_12"),
        ("${REMOTE}Debian:12", "standard"),
    ]


def test_path_prefix_entry_validation(repo):
    root = repo({"project.yaml": _ROOT_REPOS, "a/project.yaml": "path-prefix:\n  - repository: x\n"})
    with pytest.raises(SystemExit, match=r"path-prefix entry"):
        resolve_project_config(root / "a")


# --- subprojects.yaml ------------------------------------------------------


def test_subprojects_yaml_applies_to_descendants_only(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "tier/project.yaml": "title: Tier\n",
            "tier/subprojects.yaml": (
                "debuginfo:\n  RockyLinux_9: true\n"
                "repositories:\n  - name: RockyLinux_9\n    paths:\n"
                "      - subproject: ppg:common:deps\n        repository: RockyLinux_9\n"
                "project-config: |\n  Prefer: tier-only\n"
            ),
            "tier/17/project.yaml": "title: Seventeen\n",
        }
    )
    tier = resolve_project_config(root / "tier")
    assert "debuginfo" not in tier
    assert _paths(tier, "RockyLinux_9")[0] == ("common:deps:build", "RockyLinux_9")
    assert "project-config" not in tier
    leaf = resolve_project_config(root / "tier" / "17")
    assert leaf["debuginfo"] == {"RockyLinux_9": True}
    assert _paths(leaf, "RockyLinux_9")[0] == ("ppg:common:deps", "RockyLinux_9")
    assert _directives(leaf) == ["Prefer: tier-only"]
    assert "# --- from root/tier/subprojects.yaml ---" in leaf["project-config"]


def test_subprojects_yaml_may_use_leaf_macros(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "tier/project.yaml": "title: Tier\n",
            "tier/subprojects.yaml": "project-config: |\n  Prefer: percona-postgresql%!{PG_MAJOR_VERSION}-server\n",
            "tier/17/project.yaml": "title: S\n",
            "tier/17/macros.yaml": "- PG_MAJOR_VERSION: 17\n",
            "tier/other/project.yaml": "project-config-inherit: false\nproject-config: |\n  Prefer: x\n",
        }
    )
    assert _directives(resolve_project_config(root / "tier" / "17")) == ["Prefer: percona-postgresql17-server"]
    # the tier itself and an opted-out descendant never see the undefined macro
    assert "project-config" not in resolve_project_config(root / "tier")
    assert _directives(resolve_project_config(root / "tier" / "other")) == ["Prefer: x"]


def test_leftover_macro_in_resolved_config_is_an_error(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "tier/subprojects.yaml": "project-config: |\n  Prefer: percona-postgresql%!{PG_MAJOR_VERSION}-server\n",
            "tier/x/project.yaml": "title: X\n",
        }
    )
    with pytest.raises(SystemExit, match=r"root/tier/x/project.yaml: undefined macro %!\{PG_MAJOR_VERSION\}"):
        resolve_project_config(root / "tier" / "x")


def test_subprojects_yaml_rejects_unknown_keys(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "tier/subprojects.yaml": "title: nope\n",
            "tier/x/project.yaml": "title: X\n",
        }
    )
    with pytest.raises(SystemExit, match=r"root/tier/subprojects.yaml: unknown key\(s\) \['title'\]"):
        resolve_project_config(root / "tier" / "x")


def test_symlinked_subprojects_yaml(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "staging/subprojects.yaml": "project-config: |\n  Prefer: shared\n",
            "devel/17/project.yaml": "title: D\n",
        }
    )
    os.symlink("../staging/subprojects.yaml", root / "devel" / "subprojects.yaml")
    cfg = resolve_project_config(root / "devel" / "17")
    assert _directives(cfg) == ["Prefer: shared"]
    assert "# --- from root/devel/subprojects.yaml ---" in cfg["project-config"]


def test_standalone_drops_every_ancestor_layer(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS + _ROOT_PRJCONF,
            "releases/project.yaml": "title: R\n",
            "releases/subprojects.yaml": "standalone: true\n",
            "releases/17/project.yaml": (
                "repositories:\n  - name: RockyLinux_9\n    paths:\n"
                "      - subproject: frozen\n        repository: RockyLinux_9\n    archs: [x86_64]\n"
                "project-config: |\n  Prefer: frozen\n"
            ),
            "releases/17/tarballs/project.yaml": (
                "repositories:\n  - name: RockyLinux_9\n    paths:\n"
                "      - subproject: frozen-tarballs\n        repository: RockyLinux_9\n    archs: [x86_64]\n"
            ),
        }
    )
    # the tier itself still inherits from root
    assert _names(resolve_project_config(root / "releases")) == ["RockyLinux_9", "Debian_12"]
    r17 = resolve_project_config(root / "releases" / "17")
    assert _paths(r17, "RockyLinux_9") == [("frozen", "RockyLinux_9")]
    assert _directives(r17) == ["Prefer: frozen"]
    tb = resolve_project_config(root / "releases" / "17" / "tarballs")
    assert _paths(tb, "RockyLinux_9") == [("frozen-tarballs", "RockyLinux_9")]
    assert "project-config" not in tb


def test_standalone_must_be_alone(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "r/subprojects.yaml": "standalone: true\nproject-config: |\n  Prefer: x\n",
            "r/17/project.yaml": "title: X\n",
        }
    )
    with pytest.raises(SystemExit, match=r"standalone: true must be the only key"):
        resolve_project_config(root / "r" / "17")


# --- flags and leaf-only keys ------------------------------------------------


def test_flags_child_wins_and_null_resets(repo):
    root = repo(
        {
            "project.yaml": _ROOT_REPOS + "publish: false\n",
            "a/subprojects.yaml": "debuginfo:\n  RockyLinux_9: true\n  Debian_12: true\n",
            "a/b/project.yaml": "debuginfo:\n  RockyLinux_9: true\n",
            "a/c/project.yaml": "debuginfo: ~\npublish:\n  RockyLinux_9: true\n",
            "a/d/project.yaml": "title: D\n",
        }
    )
    assert resolve_project_config(root / "a" / "b")["debuginfo"] == {"RockyLinux_9": True}
    assert resolve_project_config(root / "a" / "b")["publish"] is False
    c = resolve_project_config(root / "a" / "c")
    assert "debuginfo" not in c
    assert c["publish"] == {"RockyLinux_9": True}
    d = resolve_project_config(root / "a" / "d")
    assert d["debuginfo"] == {"RockyLinux_9": True, "Debian_12": True}


def test_title_description_name_qa_are_leaf_only(repo):
    root = repo(
        {
            "project.yaml": "title: Root\ndescription: R\nname: custom:root\nqa:\n  pipeline: p\n",
            "a/project.yaml": "publish: false\n",
        }
    )
    cfg = resolve_project_config(root / "a")
    for key in ("title", "description", "name", "qa"):
        assert key not in cfg
    assert cfg["publish"] is False


def test_alias_in_common_delegates(repo):
    root = repo({"project.yaml": _ROOT_REPOS, "a/project.yaml": "title: A\n"})
    assert common._load_project_config_with_inheritance(root / "a") == resolve_project_config(root / "a")


def test_env_vars_are_substituted(repo):
    root = repo({"project.yaml": _ROOT_REPOS, "a/project.yaml": "title: A\n"})
    cfg = resolve_project_config(root / "a", {"REMOTE": "openSUSE.org:"})
    assert _paths(cfg, "Debian_12") == [("openSUSE.org:Debian:12", "standard")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest -q tests/test_project_config_merge.py`
Expected: collection error `ModuleNotFoundError: No module named 'percona_obs.project_config'`.

- [ ] **Step 3: Add `strict` to `apply_macro_substitution`**

In `percona_obs/common.py`, change the signature and the undefined-macro branch:

```python
def apply_macro_substitution(
    text: str,
    macros: dict[str, str],
    source: Path | None = None,
    strict: bool = True,
) -> str:
    """Replace every ``%!{VAR}`` token in *text* with the value from *macros*.

    ... (keep the existing docstring) ...

    With ``strict=False`` an undefined token is left in place instead of
    raising; ``project_config.resolve_project_config`` uses this for ancestor
    layers, whose macros may only be defined further down the tree, and
    reports leftovers on the *resolved* configuration instead.
    """
```
and inside `_replace`:
```python
        if var not in macros:
            if not strict:
                return m.group(0)
            loc = f"{source}: " if source else ""
            raise SystemExit(
                f"error: {loc}undefined macro %!{{{var}}} — " "define it in macros.yaml"
            )
```

- [ ] **Step 4: Write the resolver**

Create `percona_obs/project_config.py`:

```python
"""Effective OBS project configuration: merge the project.yaml chain root → leaf.

Design: docs/superpowers/specs/2026-09-23-project-yaml-dedup-design.md.

For a project P with directory chain root/ = A0, A1, …, An = P the layers are
folded in this order::

    A0/project.yaml, A0/subprojects.yaml, A1/project.yaml, A1/subprojects.yaml, …, P/project.yaml

``project.yaml`` applies to the project itself and is inherited by its
descendants; ``subprojects.yaml`` applies to strict descendants only.  A
``subprojects.yaml`` holding just ``standalone: true`` makes every strict
descendant resolve from its own project.yaml alone.

Merge rules, applied per layer in fold order:

repositories
    merged by ``name``.  Unknown name with ``archs`` → appended.  Unknown name
    without ``archs`` → error (a patch for a typo'd name).  Known name → its
    ``paths`` are prepended (``paths-replace: true`` replaces instead) and
    ``archs`` replaces when given.  ``remove: true`` drops the repository.
path-prefix
    concatenated child-first and prepended to every repository at the end;
    ``%_repository`` in ``repository`` becomes the repository name.
project-config
    concatenated, each contribution under a ``# --- from <file> ---`` header.
debuginfo / publish / build
    whole value, child wins; ``null`` resets to unset.
repositories-inherit: false / project-config-inherit: false
    discard what earlier layers accumulated for that field.
title / description / name / qa (and any unknown key)
    never inherited; copied from the leaf only.

Macro substitution uses the leaf's macro set.  Ancestor layers are substituted
leniently (undefined tokens stay) so a tier may reference macros that only its
descendants define; a token left in the *resolved* config is an error.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from percona_obs import common

SUBPROJECTS_FILE = "subprojects.yaml"
REPO_TOKEN = "%_repository"

LEAF_ONLY_KEYS = ("title", "description", "name", "qa")
FLAG_KEYS = ("debuginfo", "publish", "build")
MERGED_KEYS = ("repositories", "project-config", *FLAG_KEYS)
CONTROL_KEYS = frozenset(
    {"repositories-inherit", "project-config-inherit", "path-prefix", "standalone"}
)
SUBPROJECTS_ALLOWED_KEYS = frozenset({*MERGED_KEYS, *CONTROL_KEYS})
REPO_ENTRY_KEYS = frozenset({"name", "paths", "archs", "paths-replace", "remove"})


def _label(path: Path) -> str:
    """Repo-relative POSIX path (``root/ppg/staging/subprojects.yaml``) for messages/headers."""
    try:
        return path.relative_to(common.REPO_ROOT.parent).as_posix()
    except ValueError:
        return path.as_posix()


def _err(path: Path, msg: str) -> SystemExit:
    return SystemExit(f"error: {_label(path)}: {msg}")


def _chain(project_path: Path) -> list[Path]:
    """Directories from REPO_ROOT down to *project_path* (inclusive)."""
    root = common.REPO_ROOT
    if project_path == root or not project_path.is_relative_to(root):
        return [project_path]
    parts = project_path.relative_to(root).parts
    return [root.joinpath(*parts[:i]) for i in range(len(parts) + 1)]


def _load_layer(
    path: Path,
    macros: dict[str, str],
    env_vars: dict[str, str] | None,
    strict: bool,
) -> dict:
    """Load one YAML layer with ``%!{}`` then ``${}`` substitution on the raw text."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if macros:
        text = common.apply_macro_substitution(text, macros, source=path, strict=strict)
    if env_vars:
        text = common.apply_env_substitution(text, env_vars, source=path)
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise _err(path, "expected a mapping at the top level")
    return data


def _merge_repositories(base: list[dict], entries: list, source: Path) -> list[dict]:
    out = [copy.deepcopy(r) for r in base]
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("name"):
            raise _err(source, f"repository entry without a name: {entry!r}")
        name = str(entry["name"])
        unknown = sorted(set(entry) - REPO_ENTRY_KEYS)
        if unknown:
            raise _err(source, f"repository {name!r}: unknown key(s) {unknown}")
        index = {r["name"]: i for i, r in enumerate(out)}
        if entry.get("remove"):
            if set(entry) != {"name", "remove"}:
                raise _err(source, f"repository {name!r}: remove: true entry may only carry 'name'")
            if name not in index:
                raise _err(source, f"cannot remove unknown repository {name!r}")
            del out[index[name]]
            continue
        if name not in index:
            if "archs" not in entry:
                raise _err(
                    source,
                    f"repository {name!r} is not inherited from any ancestor; "
                    "add archs: to define a new repository, or fix the name",
                )
            new = {k: copy.deepcopy(v) for k, v in entry.items() if k != "paths-replace"}
            new.setdefault("paths", [])
            out.append(new)
            continue
        current = out[index[name]]
        new_paths = list(copy.deepcopy(entry.get("paths") or []))
        if entry.get("paths-replace"):
            current["paths"] = new_paths
        else:
            current["paths"] = new_paths + list(current.get("paths") or [])
        if "archs" in entry:
            current["archs"] = copy.deepcopy(entry["archs"])
    return out


def _apply_path_prefix(repos: list[dict], prefixes: list[dict], source: Path) -> list[dict]:
    if not prefixes:
        return repos
    for p in prefixes:
        if (
            not isinstance(p, dict)
            or "repository" not in p
            or ("subproject" in p) == ("project" in p)
        ):
            raise _err(
                source,
                "path-prefix entry must have 'repository' and exactly one of "
                f"'subproject'/'project': {p!r}",
            )
    out = []
    for repo in repos:
        pre = [
            {**p, "repository": str(p["repository"]).replace(REPO_TOKEN, repo["name"])}
            for p in prefixes
        ]
        out.append({**repo, "paths": pre + list(repo.get("paths") or [])})
    return out


def render_project_config(parts: list[tuple[str, str]]) -> str:
    """Join ``(label, text)`` contributions with provenance headers."""
    return "\n\n".join(f"# --- from {label} ---\n{text}" for label, text in parts) + "\n"


def _check_no_macro_leftovers(value: Any, own_path: Path) -> None:
    if isinstance(value, str):
        m = common._MACRO_RE.search(value)
        if m:
            raise _err(
                own_path,
                f"undefined macro {m.group(0)} in the resolved configuration "
                "(inherited from an ancestor project.yaml/subprojects.yaml) — "
                "define it in macros.yaml or opt out of the inherited field",
            )
    elif isinstance(value, dict):
        for v in value.values():
            _check_no_macro_leftovers(v, own_path)
    elif isinstance(value, list):
        for v in value:
            _check_no_macro_leftovers(v, own_path)


def _fold(layers: list[tuple[Path, dict]], own: dict, own_path: Path) -> dict:
    repos: list[dict] = []
    prjconf: list[tuple[str, str]] = []
    prefixes: list[dict] = []
    flags: dict[str, Any] = {}
    for source, data in layers:
        if data.get("repositories-inherit") is False:
            repos = []
        repos = _merge_repositories(repos, data.get("repositories") or [], source)
        if data.get("project-config-inherit") is False:
            prjconf = []
        text = (data.get("project-config") or "").strip("\n")
        if text.strip():
            prjconf.append((_label(source), text))
        prefixes = [dict(p) for p in (data.get("path-prefix") or [])] + prefixes
        for key in FLAG_KEYS:
            if key in data:
                flags[key] = data[key]

    result: dict = {
        k: copy.deepcopy(v)
        for k, v in own.items()
        if k not in CONTROL_KEYS and k not in MERGED_KEYS
    }
    result["repositories"] = _apply_path_prefix(repos, prefixes, own_path)
    if prjconf:
        result["project-config"] = render_project_config(prjconf)
    for key, value in flags.items():
        if value is not None:
            result[key] = copy.deepcopy(value)
    return result


def resolve_project_config(
    project_path: Path, env_vars: dict[str, str] | None = None
) -> dict:
    """Return the effective configuration of the project at *project_path*.

    Keys: everything the leaf's own project.yaml declares except control keys,
    plus the merged ``repositories`` (always present, possibly empty),
    ``project-config`` (when any layer contributes text) and whichever of
    ``debuginfo``/``publish``/``build`` resolve to a non-null value.
    """
    macros = common.load_macros(project_path)
    layers: list[tuple[Path, dict]] = []
    standalone = False
    chain = _chain(project_path)
    for directory in chain[:-1]:
        pfile = directory / "project.yaml"
        layers.append((pfile, _load_layer(pfile, macros, env_vars, strict=False)))
        sfile = directory / SUBPROJECTS_FILE
        if sfile.exists():
            data = _load_layer(sfile, macros, env_vars, strict=False)
            unknown = sorted(set(data) - SUBPROJECTS_ALLOWED_KEYS)
            if unknown:
                raise _err(sfile, f"unknown key(s) {unknown}")
            if data.get("standalone"):
                if set(data) != {"standalone"}:
                    raise _err(sfile, "standalone: true must be the only key")
                standalone = True
            else:
                layers.append((sfile, data))
    own_path = project_path / "project.yaml"
    own = _load_layer(own_path, macros, env_vars, strict=True)
    if standalone:
        layers = []
    layers.append((own_path, own))
    resolved = _fold(layers, own, own_path)
    _check_no_macro_leftovers(resolved, own_path)
    return resolved
```

- [ ] **Step 5: Turn the old function into an alias**

In `percona_obs/common.py`, replace the body of `_load_project_config_with_inheritance` (keep the name and signature) with:

```python
def _load_project_config_with_inheritance(
    project_path: Path,
    env_vars: dict[str, str] | None = None,
) -> dict:
    """Backward-compatible alias for ``project_config.resolve_project_config``.

    Kept so obs_api, cmd_sync, targets and cmd_project need no import changes.
    New code should import ``resolve_project_config`` directly.
    """
    from percona_obs.project_config import resolve_project_config

    return resolve_project_config(project_path, env_vars)
```
Remove the now-unused old loop body. (The local import avoids a circular import: `project_config` imports `common`.)

- [ ] **Step 6: Run the tests, format, type-check**

```bash
venv/bin/python -m pytest -q tests/test_project_config_merge.py
venv/bin/python -m pytest -q tests
venv/bin/black percona_obs/
venv/bin/pyright
```
Expected: new file all passed; whole suite passed; black `1 file reformatted` or `left unchanged`; pyright `0 errors`. If pyright complains about `m.group(0)` being `str | Any`, wrap in `str(...)`.

- [ ] **Step 7: Run the gate for information**

`venv/bin/python <scratchpad>/gate.py check <scratchpad>/gate-baseline | tail -3` — expected to FAIL on projects that define `repositories` today (duplicated paths). Do not fix anything; it is the input for Tasks 4–5.

- [ ] **Step 8: Commit**

```bash
git add percona_obs/project_config.py percona_obs/common.py tests/test_project_config_merge.py
git commit -s -m "project config: merge-based resolver for the project.yaml chain

Adds percona_obs.project_config.resolve_project_config: repositories merge
by name (prepend / paths-replace / remove), project-config concatenates
under provenance headers, path-prefix, subprojects.yaml tier files and
standalone, flags child-wins with null reset.  The old
_load_project_config_with_inheritance now delegates to it.

The yaml tree is not rewritten yet, so the migration gate fails on
projects that spell out their repositories today; Tasks 4-5 fix that."
```

---

### Task 2: Route every consumer through the resolver

**Goal:** The four plain-loader call sites in `cmd_project.py` use the resolver, so validators, `project status` and the release mirror see the effective configuration; the release mirror test proves a delta source yields a materialized mirror.

**Files:**
- Modify: `percona_obs/cmd_project.py` (`_repo_arch_pairs_from_yaml` ~line 242; `_validate_subproject_refs` ~line 354; `_validate_project_path_refs` ~line 387; `_write_release_tree` ~line 1407)
- Test: `tests/test_project_release.py` (append one test), `tests/test_project_config_merge.py` (append two validator tests)

**Acceptance Criteria:**
- [ ] `_validate_subproject_refs` reports a bad `subproject:` inherited from a tier `subprojects.yaml` against the *leaf* project's directory
- [ ] `_write_release_tree` writes a release mirror whose repositories include paths contributed by a tier `subprojects.yaml`
- [ ] Whole suite passes; black and pyright pass

**Verify:** `venv/bin/python -m pytest -q tests/test_project_release.py tests/test_project_config_merge.py` → all passed

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_project_release.py`:

```python
def test_write_release_tree_materializes_delta_source(tmp_path, monkeypatch):
    """A staging subproject that only patches a tier subprojects.yaml still yields a full mirror."""
    import percona_obs.common as common

    root = tmp_path / "root"
    (root / "ppg/staging/17/extras").mkdir(parents=True)
    (root / "macros.yaml").write_text("- X: 1\n")
    (root / "project.yaml").write_text(
        yaml.dump(
            {
                "repositories": [
                    {
                        "name": "UBI_9",
                        "paths": [{"project": "ext:UBI-9", "repository": "standard"}],
                        "archs": ["x86_64"],
                    }
                ]
            }
        )
    )
    (root / "ppg/staging/subprojects.yaml").write_text(
        yaml.dump(
            {
                "repositories": [
                    {
                        "name": "UBI_9",
                        "paths": [{"subproject": "ppg:common:deps", "repository": "UBI_9"}],
                    }
                ],
                "project-config": "Prefer: shared\n",
            }
        )
    )
    (root / "ppg/staging/17/project.yaml").write_text("title: S17\n")
    (root / "ppg/staging/17/extras/project.yaml").write_text(
        yaml.dump(
            {
                "repositories": [
                    {
                        "name": "UBI_9",
                        "paths": [{"subproject": "ppg:staging:17", "repository": "UBI_9"}],
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(common, "REPO_ROOT", root)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    rel = root / "ppg/releases/17"
    _write_release_tree(
        rel, {"build": False, "repositories": []}, root / "ppg/staging/17",
        "ppg:staging:17", "ppg:releases:17", "ppg", "17",
    )
    extras = yaml.safe_load((rel / "extras" / "project.yaml").read_text())
    paths = [(p.get("subproject") or p.get("project"), p["repository"]) for p in extras["repositories"][0]["paths"]]
    assert paths == [
        ("ppg:releases:17", "UBI_9"),
        ("ppg:common:deps", "UBI_9"),
        ("ext:UBI-9", "standard"),
    ]
    assert extras["repositories"][0]["archs"] == ["x86_64"]
    assert "Prefer: shared" in extras["project-config"]
```

Append to `tests/test_project_config_merge.py`:

```python
# --- validators (cmd_project) ----------------------------------------------


def test_validate_subproject_refs_sees_inherited_paths(repo):
    from percona_obs.cmd_project import _validate_subproject_refs

    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "tier/project.yaml": "title: T\n",
            "tier/subprojects.yaml": (
                "repositories:\n  - name: RockyLinux_9\n    paths:\n"
                "      - subproject: does:not:exist\n        repository: RockyLinux_9\n"
            ),
            "tier/17/project.yaml": "title: S\n",
            "common/deps/build/project.yaml": "title: B\n",
        }
    )
    errors = _validate_subproject_refs(root)
    assert [(str(p.relative_to(root)), m.split(" (")[0]) for p, m in errors] == [
        ("tier/17/project.yaml", "subproject 'does:not:exist' not found"),
    ]


def test_validate_subproject_refs_surfaces_merge_errors(repo):
    from percona_obs.cmd_project import _validate_subproject_refs

    root = repo(
        {
            "project.yaml": _ROOT_REPOS,
            "a/project.yaml": "repositories:\n  - name: Debian_21\n    remove: true\n",
        }
    )
    with pytest.raises(SystemExit, match="cannot remove unknown repository"):
        _validate_subproject_refs(root)
```

Run: `venv/bin/python -m pytest -q tests/test_project_release.py tests/test_project_config_merge.py`
Expected: the three new tests FAIL (release mirror has only one path; validator sees no error / different path).

- [ ] **Step 2: Switch the four call sites**

In `percona_obs/cmd_project.py`:

(a) `_repo_arch_pairs_from_yaml` (inside `cmd_project_versions`): replace
`data = load_project_yaml(project_path / "project.yaml")` with
`data = _load_project_config_with_inheritance(project_path)`.

(b) `_validate_subproject_refs`: replace the loop head
```python
    for yaml_path in sorted(root.rglob("project.yaml")):
        config = load_project_yaml(yaml_path)
```
with
```python
    for yaml_path in sorted(root.rglob("project.yaml")):
        config = _load_project_config_with_inheritance(yaml_path.parent)
```
Errors keep being reported against `yaml_path` (the leaf project's file), which is where the user acts. Update the docstring: "References are validated on the *resolved* configuration, so a bad `subproject:` inherited from an ancestor `project.yaml` or `subprojects.yaml` is reported against every project that inherits it."

(c) `_validate_project_path_refs`: replace
```python
        config = load_yaml_with_env(
            yaml_path, env_vars, macros=load_macros(yaml_path.parent)
        )
```
with
```python
        config = _load_project_config_with_inheritance(yaml_path.parent, env_vars)
```
(The function already tolerates unresolved `${VAR}` tokens when `env_vars` is None, because the resolver leaves them literal exactly as `load_yaml_with_env` did.)

(d) `_write_release_tree`: replace
`source_sub_config = load_project_yaml(sub_path / "project.yaml")` with
`source_sub_config = _load_project_config_with_inheritance(sub_path)`.
Add to the docstring: "The source subproject is read through the resolver, so a delta-style staging subproject produces a fully materialized release mirror."

If `load_yaml_with_env` or `load_macros` become unused imports in `cmd_project.py`, remove them from the import list (pyright/black do not flag unused imports; check with `grep -n "load_yaml_with_env\|load_macros" percona_obs/cmd_project.py`).

- [ ] **Step 3: Run tests, format, type-check**

```bash
venv/bin/python -m pytest -q tests
venv/bin/black percona_obs/
venv/bin/pyright
```
Expected: all passed, `0 errors`.

- [ ] **Step 4: Commit**

```bash
git add percona_obs/cmd_project.py tests/test_project_release.py tests/test_project_config_merge.py
git commit -s -m "project: read repositories through the resolver everywhere

project versions, the two prepass validators and the release mirror writer
used the plain loader; with delta-style project.yaml files they must see
the effective configuration."
```

---

### Task 3: `project config --resolved` and `--diff`

**Goal:** `percona-obs project config [project] --resolved` prints the resolved YAML per project; `--diff` shows unified diffs of rendered meta and prjconf against live OBS.

**Files:**
- Modify: `percona_obs/cli.py` (`project_config_parser`, ~line 624)
- Modify: `percona_obs/cmd_project.py` (`cmd_project_config`, ~line 712)
- Test: `tests/test_project_config_merge.py` (one test for the YAML rendering helper)

**Acceptance Criteria:**
- [ ] `venv/bin/python -m percona_obs -R ROOT project config ppg:staging:17 --offline --resolved` prints a YAML document per project starting with a `# project ROOT:ppg:staging:17` comment line, containing `repositories:` and `project-config:`
- [ ] `--diff` without a profile exits with `error: --diff needs a profile (-P) to reach OBS`
- [ ] `--resolved` and `--diff` together exit with an argparse error (mutually exclusive)
- [ ] Whole suite, black, pyright pass

**Verify:** `venv/bin/python -m percona_obs -R ROOT project config ppg:staging:17 --offline --resolved | head -3` → `# project ROOT:ppg:staging:17` then YAML

**Steps:**

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_config_merge.py`:

```python
def test_render_resolved_yaml(repo):
    from percona_obs.cmd_project import _render_resolved_yaml

    root = repo({"project.yaml": _ROOT_REPOS, "a/project.yaml": "title: A\n"})
    out = _render_resolved_yaml("ROOT:a", resolve_project_config(root / "a"))
    assert out.startswith("# project ROOT:a\n")
    assert "repositories:" in out and "name: RockyLinux_9" in out
    assert out.endswith("\n")
```
Run: `venv/bin/python -m pytest -q tests/test_project_config_merge.py::test_render_resolved_yaml` → FAIL (ImportError).

- [ ] **Step 2: CLI flags**

In `percona_obs/cli.py`, after the `--offline` argument of `project_config_parser`:

```python
    project_config_mode = project_config_parser.add_mutually_exclusive_group()
    project_config_mode.add_argument(
        "--resolved",
        action="store_true",
        default=False,
        help="Print the resolved project.yaml (after inheritance and merging) as YAML "
        "instead of the meta XML and build config.",
    )
    project_config_mode.add_argument(
        "--diff",
        action="store_true",
        default=False,
        help="Show unified diffs of the rendered meta XML and build config against what "
        "OBS currently holds. Requires a profile (-P).",
    )
```
Update the parser `help=` to: "Show the project meta XML and build config that would be sent to OBS, the resolved project.yaml (--resolved), or a diff against OBS (--diff)."

- [ ] **Step 3: Implement in `cmd_project_config`**

Add near the top of `cmd_project.py` (module level, after imports):

```python
def _render_resolved_yaml(obs_project_name: str, config: dict) -> str:
    """YAML rendering of a resolved project configuration, for ``project config --resolved``."""
    return f"# project {obs_project_name}\n" + yaml.dump(
        config, default_flow_style=False, allow_unicode=True, sort_keys=False, width=100
    )
```
(`yaml` and `difflib` must be imported at the top of `cmd_project.py`; `yaml` already is, add `import difflib` if missing.)

In `cmd_project_config`, right after `env_vars` is finalised and before the osc initialisation, add:

```python
    if getattr(args, "diff", False) and not args.profile:
        raise SystemExit("error: --diff needs a profile (-P) to reach OBS")
    if getattr(args, "diff", False) and getattr(args, "offline", False):
        raise SystemExit("error: --diff and --offline are mutually exclusive")
```

In the per-project loop, immediately after `project_config = _load_project_config_with_inheritance(project_path, env_vars)`, add:

```python
        if getattr(args, "resolved", False):
            print(sep)
            print(_render_resolved_yaml(obs_project_name, project_config), end="")
            continue
```

Replace the tail of the loop (the four `print` calls for meta and config) with:

```python
        if getattr(args, "diff", False):
            assert apiurl is not None
            try:
                current_meta = _decode_obs_response(
                    osc.core.show_project_meta(apiurl, obs_project_name)
                )
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                current_meta = ""
            try:
                current_conf = _decode_obs_response(
                    osc.core.show_project_conf(apiurl, obs_project_name)
                ).strip()
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                current_conf = ""
            print(sep)
            print(_col(_BOLD, f"project {obs_project_name}"))
            if current_meta == "" and current_conf == "":
                print(_col(_DIM, "(not on OBS yet)"))
            meta_diff = list(
                difflib.unified_diff(
                    current_meta.strip().splitlines(), meta.strip().splitlines(),
                    "obs/_meta", "local/_meta", lineterm="",
                )
            )
            conf_diff = list(
                difflib.unified_diff(
                    current_conf.splitlines(), project_config_str.splitlines(),
                    "obs/_config", "local/_config", lineterm="",
                )
            )
            if not meta_diff and not conf_diff:
                print(_col(_DIM, "meta and config identical"))
            for line in meta_diff + conf_diff:
                print(line)
            print()
            continue

        print(sep)
        print(_col(_BOLD, f"project meta  {obs_project_name}"))
        print(meta)
        print()
        print(_col(_BOLD, f"project config  {obs_project_name}"))
        print(project_config_str if project_config_str else _col(_DIM, "(empty)"))
        print()
```
`urllib.error` is already imported in `cmd_project.py` (used by the release code); if not, add `import urllib.error`. Note the existing code merges OBS-managed elements into `meta` before this point, so the meta diff is against what sync would upload.

- [ ] **Step 4: Run, format, type-check, smoke-test**

```bash
venv/bin/python -m pytest -q tests
venv/bin/black percona_obs/
venv/bin/pyright
venv/bin/python -m percona_obs -R ROOT project config ppg:staging:17 --offline --resolved | head -3
venv/bin/python -m percona_obs -R ROOT project config ppg:staging:17 --diff; echo "exit=$?"
venv/bin/python -m percona_obs -R ROOT project config ppg:staging:17 --resolved --diff; echo "exit=$?"
```
Expected: tests pass; `0 errors`; YAML output; `error: --diff needs a profile (-P) to reach OBS` exit 1; argparse "not allowed with argument" exit 2.

- [ ] **Step 5: Commit**

```bash
git add percona_obs/cli.py percona_obs/cmd_project.py tests/test_project_config_merge.py
git commit -s -m "project config: --resolved prints the merged project.yaml, --diff compares with OBS"
```

---

### Task 4: Rewrite root, tiers, staging/<V>, devel/<V> as deltas

**Goal:** root, the two tier `subprojects.yaml` files, the twelve per-major files and the three `common`/`ppg/common` files express only their deltas, and the gate passes with the documented allowlist.

**Files:**
- Modify: `root/project.yaml`
- Modify: `root/common/deps/runtime/project.yaml`, `root/ppg/common/deps/project.yaml`, `root/common/deps/build/project.yaml`
- Create: `root/ppg/staging/subprojects.yaml`
- Create: `root/ppg/devel/subprojects.yaml` (symlink → `../staging/subprojects.yaml`)
- Modify: `root/ppg/staging/{14,15,16,17,18,19}/project.yaml`, `root/ppg/devel/{14,15,16,17,18,19}/project.yaml`

**Acceptance Criteria:**
- [ ] `gate.py check` prints `GATE PASSED` when run with `--allow-loss "Prefer: libverto-libev;Prefer: Lmod" --allow-projects root,root/ppg/staging,root/ppg/devel`, and prints `prjconf loss tolerated (allowlist):` for exactly those three projects
- [ ] Every one of the 12 per-major files is under 120 lines
- [ ] `venv/bin/python -m percona_obs project verify --offline` (or without a profile) prints `project verify: all checks passed`
- [ ] Whole test suite passes (`tests/test_macro_resolution.py` runs against the real tree)

**Verify:** `venv/bin/python <scratchpad>/gate.py check <scratchpad>/gate-baseline --allow-loss "Prefer: libverto-libev;Prefer: Lmod" --allow-projects root,root/ppg/staging,root/ppg/devel` → `GATE PASSED`

**Steps:**

- [ ] **Step 1: root/project.yaml**

Keep the `repositories:` block exactly as is. In `project-config:` delete these three lines and only these (the EL8 block loses two lines, the EL9 block loses one line plus its four-line comment about krb5-server that describes it):

```
  Prefer: libverto-libev      (in the RockyLinux_8 || UBI_8 block)
  Prefer: Lmod                (in the RockyLinux_8 || UBI_8 block)
  Prefer: libverto-libev      (in the RockyLinux_9 || RockyLinux_9.6 block, with its comment)
```
Leave every other line (including all existing comments) untouched. Add this comment as the first lines inside `project-config: |`:

```
  # Distro-wide build configuration inherited by every project under root/.
  # Project-specific lines live in the project's own project.yaml (or in a
  # tier's subprojects.yaml); the tool concatenates them and marks each block
  # with a "# --- from <file> ---" header.  See root/README.md.
```

- [ ] **Step 2: common/deps/runtime and ppg/common/deps get the moved Prefer lines**

Append to both `root/common/deps/runtime/project.yaml` and `root/ppg/common/deps/project.yaml`:

```yaml
project-config: |
  # libverto-libev / Lmod settle "have choice" reports for krb5-server and
  # friends in the common dependency projects.  They used to live in the root
  # project.yaml; the PPG projects never needed them, so they moved here.
  %if "%_repository" == "RockyLinux_8" || "%_repository" == "UBI_8"
  Prefer: libverto-libev
  Prefer: Lmod
  %endif

  %if "%_repository" == "RockyLinux_9" || "%_repository" == "RockyLinux_9.6"
  # krb5-server needs libverto-module-base, provided by both libverto-libev
  # and libverto-libevent on the 9.6 vault repo set ("have choice", seen on
  # pr-2 ppg:common:deps/krb5). Same pick as the EL8 block above.
  Prefer: libverto-libev
  %endif
```

- [ ] **Step 3: common/deps/build becomes a delta**

Replace the whole `project-config:` block of `root/common/deps/build/project.yaml` with:

```yaml
project-config: |
  %if "%_repository" == "RockyLinux_10"
  # Same llvm-libs / lapack / blas picks as the RockyLinux_9.6 block in the
  # root project.yaml: EPEL 10 ships compat llvm libs and the lapack64/blas64
  # split provides the same sonames as the LP64 packages.
  Prefer: llvm-libs
  Prefer: lapack
  Prefer: blas
  %endif
```
Leave `title`, `description`, `publish: false` untouched. (It has no `repositories:` block today.) Run the gate now (with the allowlist flags from the Verify line): the only failures must be the staging/devel majors. If `root/common/deps/build` or `runtime` or `ppg/common/deps*` show up, compare with `gate.py effective root/common/deps/build RockyLinux_10` against the baseline JSON and fix the text.

- [ ] **Step 4: root/ppg/staging/subprojects.yaml**

Create with exactly this content (comments included):

```yaml
# Configuration folded into every project below root/ppg/staging/ — the
# per-major staging projects and their subprojects.  It does NOT apply to the
# package-less ppg:staging container project itself.
#
# root/ppg/devel/subprojects.yaml is a symlink to this file: devel mirrors
# staging.  Per-major differences live in <V>/project.yaml.  Subprojects whose
# repository set is unrelated (tarballs, extras, containers) opt out with
# repositories-inherit: false / project-config-inherit: false.

debuginfo:
  RockyLinux_8: true
  RockyLinux_9: true
  RockyLinux_9.6: true
  RockyLinux_10: true
  openSUSE_Tumbleweed: true
  openSUSE_Leap_16: true

# Repository patches over the root definitions.  PPG projects resolve
# ppg:common:deps first, then common:deps:build, then the distro.  For the
# repositories where the root project.yaml lists the distro before
# common:deps:build the whole path list is restated (paths-replace) so that
# the emitted order stays exactly what OBS has today.
repositories:
  - name: RockyLinux_8
    paths:
      - subproject: ppg:common:deps
        repository: RockyLinux_8
  - name: RockyLinux_9
    paths:
      - subproject: ppg:common:deps
        repository: RockyLinux_9
  - name: RockyLinux_9.6
    paths:
      - subproject: ppg:common:deps
        repository: RockyLinux_9.6
  - name: UBI_9
    paths:
      - subproject: ppg:common:deps
        repository: UBI_9
  - name: UBI_8
    paths-replace: true
    paths:
      - subproject: common:deps:build
        repository: UBI_8
      - subproject: ppg:common:deps
        repository: UBI_8
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Fedora:EPEL:8
        repository: standard
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RedHat:UBI-8
        repository: standard
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:8
        repository: appstream
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:8
        repository: baseos
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RockyLinux:8
        repository: devel
  - name: Debian_12
    paths-replace: true
    paths:
      - subproject: ppg:common:deps
        repository: Debian_12
      - subproject: common:deps:build
        repository: Debian_12
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Debian:12
        repository: standard
  - name: Debian_13
    paths-replace: true
    paths:
      - subproject: ppg:common:deps
        repository: Debian_13
      - subproject: common:deps:build
        repository: Debian_13
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Debian:13
        repository: standard
  - name: Ubuntu_22.04
    paths-replace: true
    paths:
      - subproject: ppg:common:deps
        repository: Ubuntu_22.04
      - subproject: common:deps:build
        repository: Ubuntu_22.04
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Ubuntu:22.04
        repository: universe
  - name: Ubuntu_24.04
    paths-replace: true
    paths:
      - subproject: ppg:common:deps
        repository: Ubuntu_24.04
      - subproject: common:deps:build
        repository: Ubuntu_24.04
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Ubuntu:24.04
        repository: universe
  - name: Ubuntu_26.04
    paths:
      - subproject: ppg:common:deps
        repository: Ubuntu_26.04
  - name: openSUSE_Tumbleweed
    paths-replace: true
    paths:
      - subproject: ppg:common:deps
        repository: openSUSE_Tumbleweed
      - subproject: common:deps:build
        repository: openSUSE_Tumbleweed
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}openSUSE:Tumbleweed
        repository: standard
  - name: openSUSE_Leap_16
    paths-replace: true
    paths:
      - subproject: ppg:common:deps
        repository: openSUSE_Leap_16
      - subproject: common:deps:build
        repository: openSUSE_Leap_16
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}openSUSE:Leap:16.0
        repository: standard

# PPG-wide build configuration on top of the root project.yaml.
project-config: |
  %if "%_repository" == "RockyLinux_8" || "%_repository" == "UBI_8"
  Prefer: python3-devel
  Prefer: atlas
  %endif

  %if "%_repository" == "UBI_9"
  # Same toolchain module and hdf-libs pick as the RockyLinux_9 block in the
  # root project.yaml; UBI_9 is a PPG-only repository.
  ExpandFlags: module:llvm-toolset-rhel9
  # hdf-libs (EPEL split package) and hdf both provide libdf.so.0 and libmfhdf.so.0
  Prefer: hdf-libs
  %endif

  %if "%_repository" == "RockyLinux_10"
  Prefer: selinux-policy-targeted
  Prefer: hdf-libs

  Macros:
  %__brp_check_rpaths %{nil}
  :Macros
  %endif

  %if "%_repository" == "openSUSE_Tumbleweed" || "%_repository" == "openSUSE_Leap_16"
  # percona-postgresqlNN-server conflicts with the SUSE postgresql-server and
  # postgresqlNN-server packages (all own /var/lib/pgsql). The DNF stack
  # (pulled in by percona-telemetry-agent -> yum-utils) recommends the SUSE
  # server. Suppress those packages so that postgresql-server requirements
  # resolve to our server via its Provides.  Each major additionally ignores
  # the *other* major's system package in its own project.yaml.
  Prefer: percona-postgresql%!{PG_MAJOR_VERSION}-server
  # Our python3-dateutil and python3-six packages shadow the SUSE system packages
  # (python313-python-dateutil, python313-six). Prefer system packages so that
  # build deps like python3-dnf-plugins-core and python3-libmodulemd resolve correctly.
  Prefer: python313-python-dateutil
  Prefer: python313-six
  Ignore: postgresql-server
  Ignore: postgresql
  %endif
```

- [ ] **Step 5: root/ppg/devel/subprojects.yaml symlink**

```bash
ln -s ../staging/subprojects.yaml root/ppg/devel/subprojects.yaml
git add root/ppg/devel/subprojects.yaml   # git stores the symlink
```

- [ ] **Step 6: staging/17/project.yaml (template for 14, 15, 16)**

Replace the file's content with (keep the existing `title:`, `description:` and the entire `qa:` block verbatim from the current file; only `debuginfo:`, `repositories:` and `project-config:` change):

```yaml
title: Percona Distribution for PostgreSQL %!{PG_MAJOR_VERSION}
description: |
  Packages for Percona Distribution for PostgreSQL %!{PG_MAJOR_VERSION} — the server, extensions,
  HA components (Patroni, etcd, HAProxy, pgBouncer, pgPool-II), and companion tools.

# Repositories, debuginfo flags and the shared build configuration come from
# root/project.yaml and root/ppg/staging/subprojects.yaml.  Only what is
# specific to this major is declared here.
project-config: |
  %if "%_repository" == "openSUSE_Tumbleweed" || "%_repository" == "openSUSE_Leap_16"
  # Suppress the ppg:staging:18 system package so that this project does not
  # pick it up when both majors are present in the interconnect.
  Ignore: postgresql18-server
  %endif

  %if "%_repository" == "Debian_12" || "%_repository" == "Ubuntu_22.04"
  # Repackaged LLVM 21 (built for Debian 12) is only for PPG 18 JIT.
  # For PPG 14–17, Ignore it so builds use the distro LLVM packages.
  Ignore: libllvm21
  Ignore: llvm-21-runtime
  Ignore: llvm-21-linker-tools
  Ignore: libclang-cpp21
  Ignore: libclang-common-21-dev
  Ignore: libclang1-21
  Ignore: llvm-21-tools
  Ignore: llvm-21
  Ignore: llvm-21-dev
  Ignore: clang-21
  %endif

qa:
  ... (unchanged, copy verbatim from the current file) ...
```

Apply the same to `staging/14`, `staging/15`, `staging/16`: keep each file's own `title`, `description` and `qa` block, replace everything else with the block above (the per-major delta is identical for 14–17; the gate confirmed that).

- [ ] **Step 7: staging/18/project.yaml**

Same shape; `project-config` becomes:

```yaml
project-config: |
  %if "%_repository" == "openSUSE_Tumbleweed" || "%_repository" == "openSUSE_Leap_16"
  # Suppress the ppg:17 system package so that this project does not pick it
  # up when both majors are present in the interconnect.
  Ignore: postgresql17-server
  %endif

  %if "%_repository" == "Debian_12" || "%_repository" == "Ubuntu_22.04"
  # PG 18 JIT requires LLVM >= 19; use repackaged llvm-21 from common:deps:build.
  Prefer: llvm-21-dev
  Prefer: clang-21
  Substitute: llvm-dev llvm-21-dev
  Substitute: clang clang-21
  # Force the whole llvm-21 toolchain into every Debian 12 build root. clang-21/
  # llvm-21-dev pull the rest transitively but an inherited Ignore strips them,
  # and extensions (pgvector, postgis) need clang-21 for PGXS bitcode yet only
  # Build-Depend on the server-dev package. Support: beats the Ignore.
  Support: clang-21
  Support: llvm-21-dev
  Support: libllvm21
  Support: libclang-cpp21
  Support: libclang-common-21-dev
  Support: llvm-21-linker-tools
  Support: libclang1-21
  Support: llvm-21
  Support: llvm-21-runtime
  Support: llvm-21-tools
  Support: libc++-21-dev
  Support: libc++abi-21-dev
  Support: libc++1-21
  Support: libc++abi1-21
  %endif

  %if "%_repository" == "Debian_12"
  # Prefer repackaged llvm-21 over Bookworm's system LLVM 14.
  Ignore: libllvm14
  Ignore: llvm-14-runtime
  Ignore: llvm-14-linker-tools
  Ignore: libclang-cpp14
  Ignore: libclang-common-14-dev
  Ignore: libclang1-14
  Ignore: llvm-14-tools
  Ignore: llvm-14
  Ignore: llvm-14-dev
  Ignore: clang-14
  %endif
```

- [ ] **Step 8: staging/19/project.yaml**

Same shape as 18 with two differences: the SUSE block is split because the two repos ignore different packages today (preserve as-is; flagged in the spec as a probable typo to fix separately), and RockyLinux_10 gets the `ppg:common:deps` path:

```yaml
repositories:
  - name: RockyLinux_10
    paths:
      - subproject: ppg:common:deps
        repository: RockyLinux_10

project-config: |
  %if "%_repository" == "openSUSE_Tumbleweed"
  Ignore: postgresql18-server
  %endif

  %if "%_repository" == "openSUSE_Leap_16"
  Ignore: postgresql19-server
  %endif

  ... then the two llvm blocks exactly as in staging/18 ...
```

- [ ] **Step 9: devel/17/project.yaml (template for 14, 15, 16)**

```yaml
title: Percona Distribution for PostgreSQL %!{PG_MAJOR_VERSION} — Devel
description: |
  Development builds of Percona Distribution for PostgreSQL %!{PG_MAJOR_VERSION} components from unreleased branches. Build dependencies not built here resolve from ppg:staging:%!{PG_MAJOR_VERSION}.

# Repositories and the shared build configuration come from root/project.yaml
# and root/ppg/devel/subprojects.yaml (a symlink to the staging one).  Devel
# resolves everything it does not build itself from the matching staging
# project, and does not build for Debian 12.
debuginfo:
  RockyLinux_9: true
  RockyLinux_9.6: true
  openSUSE_Tumbleweed: true
  openSUSE_Leap_16: true
path-prefix:
  - subproject: ppg:staging:%!{PG_MAJOR_VERSION}
    repository: "%_repository"
repositories:
  - name: Debian_12
    remove: true

project-config: |
  ... exactly the staging/17 project-config block from Step 6 ...
```
Keep each devel file's own `title`/`description` (copy from the current file). devel has no `qa:` block.

- [ ] **Step 10: devel/18 and devel/19**

devel/18: as devel/17 but **without** the `repositories:` removal (devel/18 builds Debian_12) and with the staging/18 `project-config` block from Step 7.

devel/19: today it is a verbatim copy of staging/19 with no path to `ppg:staging:19` (preserved, flagged in the spec). Write:

```yaml
title: (copy current)
description: (copy current)
debuginfo:
  RockyLinux_9: true
  RockyLinux_9.6: true
  openSUSE_Tumbleweed: true
  openSUSE_Leap_16: true
repositories:
  - name: RockyLinux_10
    paths:
      - subproject: ppg:common:deps
        repository: RockyLinux_10
project-config: |
  ... exactly the staging/19 project-config block from Step 8 ...
```
No `path-prefix`, no `remove`.

- [ ] **Step 11: Gate, verify, tests**

```bash
S=<scratchpad>
venv/bin/python $S/gate.py check $S/gate-baseline --allow-loss "Prefer: libverto-libev;Prefer: Lmod" --allow-projects root,root/ppg/staging,root/ppg/devel
```
Expected at this point: `PRJCONF DIFFERS`/`META DIFFERS` only for projects not yet rewritten (tarballs, extras, containers, tde, common/containers, ppg/common/deps/tarballs, which now get duplicated inherited paths). No staging/<V>, devel/<V>, root, common/deps/*, ppg/common/deps may appear. For any that do, use `gate.py effective <dir> <repo>` and the baseline JSON to find the missing/extra line and fix the yaml, never the allowlist.

Then:
```bash
wc -l root/ppg/staging/*/project.yaml root/ppg/devel/*/project.yaml   # each < 120
venv/bin/python -m pytest -q tests
```

- [ ] **Step 12: Commit**

```bash
git add root/project.yaml root/common/deps root/ppg/common/deps/project.yaml root/ppg/staging/subprojects.yaml root/ppg/devel/subprojects.yaml root/ppg/staging/*/project.yaml root/ppg/devel/*/project.yaml
git commit -s -m "root: express staging/devel project.yaml as deltas over tier subprojects.yaml

Shared PPG repository patches, debuginfo flags and build configuration move
to root/ppg/staging/subprojects.yaml (devel symlinks to it); the twelve
per-major files keep only their own SUSE Ignore and llvm policy.  The two
Prefer lines that only the common dependency projects need move out of the
root project.yaml into those projects.  Rendered meta is byte-identical and
the effective prjconf per repository is unchanged for every buildable
project (migration gate)."
```

---

### Task 5: Opt-outs for unrelated subprojects and the releases marker

**Goal:** Every subproject whose repository set is unrelated to its parent declares `repositories-inherit: false` (and `project-config-inherit: false`, `debuginfo: ~` where needed); `root/ppg/releases/subprojects.yaml` freezes the release snapshots; the gate passes fully.

**Files:**
- Modify (add keys at the top, content otherwise unchanged): `root/ppg/staging/{14,15,16,17,18}/tarballs/project.yaml`, `root/ppg/staging/{16,17,18}/extras/project.yaml`, `root/ppg/staging/{16,17,18}/extras/containers/project.yaml`, `root/ppg/staging/{14,15,16,17,18}/containers/project.yaml`, `root/ppg/staging/16/tde/project.yaml`, `root/ppg/staging/containers/project.yaml`, `root/ppg/staging/extras/containers/project.yaml`, `root/common/containers/ubi8/project.yaml`, `root/common/containers/ubi9/project.yaml`, `root/ppg/common/deps/tarballs/project.yaml`
- Create: `root/ppg/releases/subprojects.yaml`

**Acceptance Criteria:**
- [ ] `gate.py check` with the allowlist flags prints `GATE PASSED` and `prjconf loss tolerated (allowlist):` for exactly `root`, `root/ppg/staging`, `root/ppg/devel`
- [ ] `git diff --stat` shows no change under `root/ppg/releases/` except the new `subprojects.yaml`
- [ ] `project verify` passes; whole suite passes

**Verify:** `venv/bin/python <scratchpad>/gate.py check <scratchpad>/gate-baseline --allow-loss "Prefer: libverto-libev;Prefer: Lmod" --allow-projects root,root/ppg/staging,root/ppg/devel` → `GATE PASSED`

**Steps:**

- [ ] **Step 1: Releases marker**

Create `root/ppg/releases/subprojects.yaml`:
```yaml
# Release snapshots are fully materialized by `percona-obs project release`
# and must not pick up later edits to root/ or staging: every project below
# this directory resolves from its own project.yaml alone.
standalone: true
```

- [ ] **Step 2: Opt-out header for the unrelated subprojects**

For each file in the Modify list, insert directly after the `description:` block (before `repositories:` or `publish:`/`debuginfo:`, whichever comes first) these lines, then leave the rest of the file untouched:

```yaml
# This project's repository set and build configuration are unrelated to its
# parent's: declare them in full here instead of patching the inherited ones.
repositories-inherit: false
project-config-inherit: false
```

For `root/ppg/common/deps/tarballs/project.yaml` insert **only** `repositories-inherit: false` (it has no `project-config:` of its own and must keep inheriting the one from `ppg/common/deps`, i.e. root's plus the moved `Prefer` lines).

Additionally add `debuginfo: ~` (with the comment `# no debuginfo repositories here; do not inherit the staging map`) to the files that have **no** `debuginfo:` key today: all tarballs (5), extras (3), extras/containers (3), containers (5), `root/ppg/staging/containers`, `root/ppg/staging/extras/containers`. Do **not** add it to `staging/16/tde` (it has its own map) nor to the `common/*` and `ppg/common/deps/tarballs` files (nothing above them defines debuginfo).

Exception, try first and keep if the gate passes: for the three `extras/project.yaml` files, omit `project-config-inherit: false` **and delete their `project-config:` block** — their only repository is `UBI_9`, whose effective lines equal the staging ones (the gate analysis showed this). If the gate reports `PRJCONF DIFFERS` for an extras project, restore its `project-config:` block and add `project-config-inherit: false` instead.

- [ ] **Step 3: Gate, verify, tests**

```bash
S=<scratchpad>
venv/bin/python $S/gate.py check $S/gate-baseline --allow-loss "Prefer: libverto-libev;Prefer: Lmod" --allow-projects root,root/ppg/staging,root/ppg/devel
venv/bin/python -m percona_obs project verify
venv/bin/python -m pytest -q tests
git status --short root/ppg/releases   # only ?? root/ppg/releases/subprojects.yaml
```
Expected: `GATE PASSED`; `project verify: all checks passed`; all tests pass.

Also run the render path that `sync` uses over the whole tree to make sure no project raises (this exercises `find_projects` + resolver for the release dirs too):
```bash
venv/bin/python -m percona_obs -R ROOT project config --offline --resolved > /dev/null && echo RENDER-OK
```

- [ ] **Step 4: Commit**

```bash
git add root/ppg/releases/subprojects.yaml root/ppg/staging root/common/containers root/ppg/common/deps/tarballs/project.yaml
git commit -s -m "root: opt unrelated subprojects out of inherited repositories; freeze releases

Tarballs, extras, containers, tde and the common container/tarball dependency
projects keep their full repository lists and build configuration and say
so with repositories-inherit/project-config-inherit: false.  A standalone
marker under root/ppg/releases/ keeps every release snapshot resolving from
its own file.  Migration gate: meta identical everywhere, effective prjconf
unchanged for every buildable project."
```

---

### Task 6: Documentation

**Goal:** The three documents that describe project.yaml describe the merge rules, `subprojects.yaml`, the opt-out keys and `project config --resolved/--diff`.

**Files:**
- Modify: `.github/copilot-instructions.md` (sections "Project Configuration (project.yaml)" and "Config inheritance", lines ~96–150; also fix the stale "Dynamically generated repository paths" paragraph, which describes ancestor path injection that `build_project_meta` no longer performs — its docstring says "No automatic ancestor-project paths are injected")
- Modify: `docs/PERCONA_OBS_TOOL.md` (new subsection after "Project configuration change detection", ~line 252)
- Modify: `root/README.md` (one paragraph in the section describing the tree, near line 394 "build repositories, and project configuration")

**Acceptance Criteria:**
- [ ] copilot-instructions "Config inheritance" section states the fold order, the `subprojects.yaml` rule, the repositories table, `path-prefix`, provenance headers, flag semantics, `standalone`, and contains the devel/17 example below
- [ ] PERCONA_OBS_TOOL.md documents `project config`, `--offline`, `--resolved`, `--diff`
- [ ] root/README.md has the "files are deltas" paragraph
- [ ] `grep -n "auto-injected" .github/copilot-instructions.md` returns nothing

**Verify:** `grep -c "subprojects.yaml" .github/copilot-instructions.md docs/PERCONA_OBS_TOOL.md root/README.md` → each ≥ 1

**Steps:**

- [ ] **Step 1: copilot-instructions.md**

Replace the "### Config inheritance" section and the "### Dynamically generated repository paths" section with:

````markdown
### Config inheritance and merging

A project's effective configuration is resolved by
`percona_obs/project_config.py::resolve_project_config`, folding these layers
from `root/` down to the project:

    root/project.yaml, root/subprojects.yaml, <tier>/project.yaml, <tier>/subprojects.yaml, …, <project>/project.yaml

- `project.yaml` applies to the project itself **and** is inherited by its descendants.
- `subprojects.yaml` (optional, next to a `project.yaml`) applies to **strict descendants only**.
  Allowed keys: `repositories`, `project-config`, `path-prefix`, `debuginfo`, `publish`, `build`,
  `repositories-inherit`, `project-config-inherit`, `standalone`. It may be a symlink
  (`root/ppg/devel/subprojects.yaml` → `../staging/subprojects.yaml`).
- `subprojects.yaml` containing only `standalone: true` makes every descendant resolve from its own
  `project.yaml` alone (`root/ppg/releases/`: release snapshots are frozen).
- `title`, `description`, `name`, `qa` are never inherited.

Merge rules per layer:

| Field | Rule |
|---|---|
| `repositories` | merged by `name`. Unknown name **with** `archs` → appended. Unknown name **without** `archs` → error (typo guard). Known name → its `paths` are **prepended**; `paths-replace: true` replaces them; `archs` replaces if given. `- name: X` + `remove: true` drops X. |
| `path-prefix` | list of path entries prepended to **every** repository; `"%_repository"` in `repository:` becomes the repo name. Layers concatenate child-first. |
| `project-config` | concatenated; each contribution is preceded by `# --- from <file> ---`. |
| `debuginfo`, `publish`, `build` | whole value, child wins; `~` (null) resets to unset. |
| `repositories-inherit: false`, `project-config-inherit: false` | discard what ancestors accumulated for that field. |

Example — `root/ppg/devel/17/project.yaml` says only what makes devel/17 different:

```yaml
title: Percona Distribution for PostgreSQL %!{PG_MAJOR_VERSION} — Devel
debuginfo: {RockyLinux_9: true, RockyLinux_9.6: true, openSUSE_Tumbleweed: true, openSUSE_Leap_16: true}
path-prefix:
  - subproject: ppg:staging:%!{PG_MAJOR_VERSION}   # resolve everything else from staging:17
    repository: "%_repository"
repositories:
  - name: Debian_12
    remove: true                                    # devel does not build Debian 12
project-config: |
  %if "%_repository" == "openSUSE_Tumbleweed" || "%_repository" == "openSUSE_Leap_16"
  Ignore: postgresql18-server
  %endif
```

The 13 distro repositories come from `root/project.yaml`; the PPG-specific paths, debuginfo map and
build configuration from `root/ppg/staging/subprojects.yaml`. Use
`percona-obs project config <project> --offline --resolved` to see the effective result and
`--diff` (with a profile) to compare it with OBS.

Macro substitution uses the target project's macro set. Ancestor layers may reference macros only
the descendants define (e.g. `%!{PG_MAJOR_VERSION}` in the staging tier); a token left unresolved
in the final configuration is an error.

Only the paths listed in the resolved `repositories` are emitted; `build_project_meta()` injects no
ancestor paths.
````

Also update the bullet list under "Each project directory may contain a `project.yaml`" so the example shows `paths-replace`/`remove` are optional keys, and add `subprojects.yaml` to the tree sketch at the top of the file (line ~31: `│       ├── subprojects.yaml    # config for the subprojects below (tiers only)`).

- [ ] **Step 2: docs/PERCONA_OBS_TOOL.md**

Insert after the "Project configuration change detection" subsection:

````markdown
### Inspecting the effective project configuration

`project.yaml` files are deltas: repositories, build configuration and flags are merged from
`root/project.yaml` down through tier-level `subprojects.yaml` files (see
`.github/copilot-instructions.md`, "Config inheritance and merging"). To see what a project
actually gets:

```sh
# Meta XML and build config exactly as sync would upload them (no OBS access)
percona-obs -R home:Admin:percona project config ppg:staging:17 --offline

# The merged project.yaml as YAML
percona-obs -R home:Admin:percona project config ppg:staging:17 --offline --resolved

# Unified diff of meta and build config against what OBS holds now
percona-obs -P dev project config ppg:staging:17 --diff
```

Without a project argument all projects under `root/` are shown. The build config carries one
`# --- from <file> ---` header per contributing file, so a line can be traced to its source.
````

- [ ] **Step 3: root/README.md**

After the sentence "The root `project.yaml` defines the top-level project …" (line ~394) add:

```markdown
Every other `project.yaml` is a **delta**: it inherits the root repositories and build
configuration, merged with the tier's `subprojects.yaml` (for example
`ppg/staging/subprojects.yaml`, which `ppg/devel/subprojects.yaml` symlinks), and declares only
what differs for that project. Subprojects with unrelated repository sets (tarballs, containers,
extras) opt out with `repositories-inherit: false`. Run
`percona-obs project config <project> --offline --resolved` to see the effective configuration;
the merge rules are in `.github/copilot-instructions.md`.
```

- [ ] **Step 4: Commit**

```bash
git add .github/copilot-instructions.md docs/PERCONA_OBS_TOOL.md root/README.md
git commit -s -m "docs: merge-based project.yaml inheritance, subprojects.yaml, project config --resolved/--diff"
```

---

### Task 7: Final verification

**Goal:** Prove the whole change is consistent: gate, tests, formatters, `project verify`, release generator smoke, and a review of the commit series.

**Files:** none modified unless a check fails.

**Acceptance Criteria:**
- [ ] `gate.py check` with the allowlist → `GATE PASSED`
- [ ] `venv/bin/python -m pytest -q tests` → all passed
- [ ] `venv/bin/black --check percona_obs/` → "would be left unchanged"; `venv/bin/pyright` → `0 errors`
- [ ] `venv/bin/python -m percona_obs project verify` → `project verify: all checks passed`
- [ ] `git diff --stat percona/main -- root/ppg/releases/` lists only `root/ppg/releases/subprojects.yaml`
- [ ] Line count of all non-release `project.yaml` files dropped from ~7000 to under ~3000 (`find root -name project.yaml -not -path '*/releases/*' | xargs wc -l | tail -1`)
- [ ] `git log --oneline percona/main..HEAD` shows the spec commits plus one commit per task (1–6)

**Verify:** all commands above.

**Steps:**

- [ ] **Step 1: Run everything**

```bash
S=<scratchpad>
venv/bin/python $S/gate.py check $S/gate-baseline --allow-loss "Prefer: libverto-libev;Prefer: Lmod" --allow-projects root,root/ppg/staging,root/ppg/devel
venv/bin/python -m pytest -q tests
venv/bin/black --check percona_obs/
venv/bin/pyright
venv/bin/python -m percona_obs project verify
git diff --stat percona/main -- root/ppg/releases/
find root -name project.yaml -not -path '*/releases/*' | xargs wc -l | tail -1
git log --oneline percona/main..HEAD
```

- [ ] **Step 2: Release-generator dry check**

`_write_release_tree` is covered by the unit test; additionally render the staging/17 subtree the way the release mirror reads it and confirm every subproject resolves with full repositories:
```bash
venv/bin/python - <<'EOF'
from pathlib import Path
from percona_obs.common import REPO_ROOT, find_projects, _load_project_config_with_inheritance
for name, path in find_projects(REPO_ROOT / "ppg/staging/17", "ppg:staging:17"):
    cfg = _load_project_config_with_inheritance(path)
    print(f"{name:40} repos={len(cfg['repositories']):2} prjconf_lines={len((cfg.get('project-config') or '').splitlines())}")
EOF
```
Expected: 13 repos for `ppg:staging:17`, 1 for `:extras`, 2 for `:containers`, 6 for `:tarballs`, 1 for `:extras:containers`, no exceptions.

- [ ] **Step 3: Report**

Do not push. Report to the user: commit list, gate summary line, the three allowlisted projects (plus the ungated `ppg:releases` tier) and what they lose, the two oddities preserved (devel/19 without staging path; staging/19 Leap `postgresql19-server`), and the first-sync consequence (prjconf text rewrite on every non-release project, no meta change).
