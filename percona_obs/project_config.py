"""Effective OBS project configuration: merge the project.yaml chain root → leaf.

Design: docs/superpowers/specs/2026-09-23-project-yaml-dedup-design.md.

For a project P with directory chain root/ = A0, A1, …, An = P the layers are
folded in this order::

    A0/project.yaml, A0/subprojects.yaml, A1/project.yaml, A1/subprojects.yaml, …, P/project.yaml

``project.yaml`` applies to the project itself and is inherited by its
descendants; ``subprojects.yaml`` applies to the *direct* children of its
directory only.  The one exception is a ``subprojects.yaml`` holding just
``standalone: true``: it is recursive and makes every strict descendant
resolve from its own project.yaml alone.

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
    discard what earlier layers accumulated for that field
    (``repositories-inherit: false`` also discards accumulated ``path-prefix``
    entries).
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
                raise _err(
                    source,
                    f"repository {name!r}: remove: true entry may only carry 'name'",
                )
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
            new = {
                k: copy.deepcopy(v) for k, v in entry.items() if k != "paths-replace"
            }
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


def _apply_path_prefix(
    repos: list[dict], prefixes: list[dict], source: Path
) -> list[dict]:
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
    return (
        "\n\n".join(f"# --- from {label} ---\n{text}" for label, text in parts) + "\n"
    )


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
            # Opting out of the inherited repositories also drops the
            # inherited path-prefix rules: they describe how the parent's
            # repositories resolve, not this project's own list.
            repos = []
            prefixes = []
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
                standalone = True  # recursive: freezes every descendant
            elif directory == project_path.parent:
                # Ordinary subprojects.yaml content reaches direct children only.
                layers.append((sfile, data))
    own_path = project_path / "project.yaml"
    own = _load_layer(own_path, macros, env_vars, strict=True)
    if standalone:
        layers = []
    layers.append((own_path, own))
    resolved = _fold(layers, own, own_path)
    _check_no_macro_leftovers(resolved, own_path)
    return resolved
