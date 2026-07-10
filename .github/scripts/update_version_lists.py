#!/usr/bin/env python3
"""Regenerate docs/versions/<dist>.md version-list files and update README.md.

Called from the "Update version lists" step in sync-main.yml, from the
standalone update-version-lists.yml workflow, and from obs-release.yml.

Environment variables
---------------------
GITHUB_EVENT_BEFORE
    The "before" SHA from the GitHub push event.  Set to the all-zeros SHA
    (or omit) to regenerate *all* dev distribution projects instead of only
    those touched by the current push.
GITHUB_SHA
    The current HEAD commit SHA (always set by GitHub Actions).

CLI arguments
-------------
--project <project_id>
    When given, regenerate only this one project (used by obs-release.yml to
    update a specific release project).  Skips the git-diff detection logic.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
ROOT_DIR = REPO_ROOT / "root"
VERSIONS_DIR = REPO_ROOT / "docs" / "versions"
README = REPO_ROOT / "README.md"

ZERO_SHA = "0" * 40

_ROW_PID_RE = re.compile(r"^\| `([^`]+)`")


# ---------------------------------------------------------------------------
# Project discovery helpers
# ---------------------------------------------------------------------------


def _project_entry(product: str, rest: list[str]) -> tuple[str, Path] | None:
    """Return (project_id, outfile) for a candidate distribution directory.

    ``rest`` contains the path segments after the product directory, e.g.
    ``["staging", "17"]`` or ``["releases", "17.9"]``.
    """
    if not rest:
        return None
    target = ROOT_DIR / product / Path(*rest)
    if not (target / "project.yaml").exists():
        return None

    project_id = ":".join([product] + rest)
    filename = "-".join([product] + rest) + ".md"
    return project_id, VERSIONS_DIR / filename


def find_all_distribution_projects() -> list[tuple[str, Path]]:
    """Return all distribution projects found under root/.

    The tree is a three-tier layout: ``releases/<v>`` (frozen), ``staging/<v>``
    (the full package sets — these are listed), and ``devel/<v>`` (dev-branch
    packages expected to fail builds — never listed). Only ``releases`` and
    ``staging`` are descended into one level to find per-version projects;
    ``devel`` and any other/unknown subdirectory (e.g. ``common``) are
    ignored rather than treated as a project themselves.
    """
    results: list[tuple[str, Path]] = []
    for product_dir in sorted(ROOT_DIR.iterdir()):
        if not product_dir.is_dir() or product_dir.name == "common":
            continue
        product = product_dir.name
        for sub in sorted(product_dir.iterdir()):
            if not sub.is_dir():
                continue
            if sub.name in ("releases", "staging"):
                for child in sorted(sub.iterdir()):
                    if child.is_dir():
                        entry = _project_entry(product, [sub.name, child.name])
                        if entry:
                            results.append(entry)
            # Devel builds are expected to fail and are never listed; any
            # other/unknown subdir under a product is ignored rather than
            # treated as a project itself.
    return results


def map_files_to_distribution_projects(
    changed_files: list[str],
) -> list[tuple[str, Path]]:
    """Map a list of changed file paths to the distribution projects they belong to.

    Only files under ``root/`` are considered.  Files under ``root/common/``
    are skipped.  Returns a deduplicated, sorted list.
    """
    seen: set[str] = set()
    results: list[tuple[str, Path]] = []

    for path in changed_files:
        if not path.startswith("root/"):
            continue
        parts = path[len("root/") :].split("/")
        if len(parts) < 2:
            continue
        product = parts[0]
        if product == "common":
            continue
        if parts[1] in ("releases", "staging") and len(parts) >= 3:
            rest = parts[1:3]
        else:
            # "devel/..." (expected-to-fail dev builds, never listed), bare
            # "releases"/"staging" container paths with no version segment,
            # or any other unrecognised top-level layout dir.
            continue

        key = ":".join([product] + rest)
        if key in seen:
            continue
        seen.add(key)

        entry = _project_entry(product, rest)
        if entry:
            results.append(entry)

    return sorted(results)


def is_release_project(project_id: str) -> bool:
    return ":releases:" in project_id


def get_latest_release_id(project_id: str) -> str:
    """Return the latest release-id from release.yaml for a release project.

    Reads root/<product>/releases/<major>/release.yaml, takes the last entry
    in the ``releases`` list (e.g. ``ppg/17.9-1``), and strips the
    ``<product>/`` prefix to return just the release-id (e.g. ``17.9-1``).
    Returns ``—`` if the file is absent or the list is empty.
    """
    import yaml

    parts = project_id.split(":")  # ["ppg", "releases", "17"]
    if len(parts) < 3 or parts[1] != "releases":
        return "—"
    product, major = parts[0], parts[2]
    release_yaml = ROOT_DIR / product / "releases" / major / "release.yaml"
    if not release_yaml.exists():
        return "—"
    data = yaml.safe_load(release_yaml.read_text(encoding="utf-8"))
    releases = data.get("releases") or []
    if not releases:
        return "—"
    last = releases[-1]  # e.g. "ppg/17.9-1"
    return last.split("/", 1)[1] if "/" in last else last


# ---------------------------------------------------------------------------
# README helpers
# ---------------------------------------------------------------------------


def file_to_project_id(path: Path) -> str:
    """Reverse the docs/versions/<product>-<devproj>.md → project_id mapping.

    ``ppg-staging-17.md``    → ``ppg:staging:17``
    ``ppg-releases-17.9.md`` → ``ppg:releases:17.9``
    """
    name = path.stem  # strip .md
    # "ppg-releases-17.9" → split on first "-" twice to handle release names
    # that may themselves contain hyphens (e.g. "17-9" is unlikely but safe).
    # Strategy: replace hyphens with colons, since product/devproj names don't
    # contain hyphens in practice.
    return name.replace("-", ":")


_VERSION_LISTS_DESCRIPTION = (
    "Per-distribution package version lists, updated automatically after every "
    "successful OBS build. Each file lists all packages and container images with "
    "the version and release number last successfully built on OBS."
)

_CURRENT_RELEASES_DESCRIPTION = (
    "Released package versions, published to the release OBS projects after "
    "each successful release tag."
)


def _make_row(
    f: Path,
    include_qa: bool,
    include_obs_link: bool,
    obs_web_url: str,
    obs_rootprj: str,
    version: str = "",
) -> str:
    """Build a single markdown table row for a version file."""
    pid = file_to_project_id(f)
    rel = f.relative_to(REPO_ROOT)
    if include_obs_link:
        obs_col = (
            f"[{obs_rootprj}:{pid}]" f"({obs_web_url}/project/show/{obs_rootprj}:{pid})"
        )
        vl_col = f"[{rel}]({rel})"
        if include_qa:
            return f"| `{pid}` | {obs_col} | {vl_col} | Not Available |"
        else:
            return f"| `{pid}` | {obs_col} | {vl_col} | {version} |"
    else:
        if include_qa:
            return f"| `{pid}` | [{rel}]({rel}) |"
        else:
            return f"| `{pid}` | [{rel}]({rel}) | {version} |"


def _build_section(
    heading: str,
    description: str,
    files: list[Path],
    include_qa: bool,
    include_obs_link: bool,
    obs_web_url: str,
    obs_rootprj: str,
) -> str:
    """Return the full markdown text for a new section."""
    if include_obs_link:
        if include_qa:
            header = "| Distribution | OBS Project | Package List | QA Status |"
            sep = "|---|---|---|---|"
        else:
            header = "| Distribution | OBS Project | Package List | Version |"
            sep = "|---|---|---|---|"
    else:
        if include_qa:
            header = "| Distribution | Package List |"
            sep = "|---|---|"
        else:
            header = "| Distribution | Package List | Version |"
            sep = "|---|---|---|"
    rows = "\n".join(
        _make_row(
            f,
            include_qa,
            include_obs_link,
            obs_web_url,
            obs_rootprj,
            version=(
                get_latest_release_id(file_to_project_id(f)) if not include_qa else ""
            ),
        )
        for f in files
    )
    return (
        f"\n## {heading}\n"
        f"\n{description}\n"
        "\n"
        f"{header}\n"
        f"{sep}\n"
        f"{rows}\n"
    )


def _upsert_section(
    content: str,
    heading: str,
    description: str,
    updated_files: list[Path],
    all_section_files: list[Path],
    include_qa: bool,
    include_obs_link: bool,
    obs_web_url: str,
    obs_rootprj: str,
) -> str:
    """Ensure the section exists and its rows are up to date.

    - If the section is absent: create it from scratch with all_section_files.
    - If it exists:
        - Rows for updated_files are rewritten (QA Status reset to Not Available).
        - Rows for files in all_section_files with no existing row are appended.
        - All other rows are left intact (preserving any QA badges).
    """
    section_heading_line = f"## {heading}"

    if f"\n{section_heading_line}\n" not in content:
        if not all_section_files:
            return content
        section = _build_section(
            heading,
            description,
            all_section_files,
            include_qa,
            include_obs_link,
            obs_web_url,
            obs_rootprj,
        )
        if "\n## Documentation\n" in content:
            return content.replace(
                "\n## Documentation\n", section + "\n## Documentation\n", 1
            )
        return content + section

    # Section exists: row-level updates.
    lines = content.splitlines(keepends=True)

    # Locate section boundaries.
    section_start: int | None = None
    section_end = len(lines)
    for i, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if stripped == section_heading_line:
            section_start = i
        elif (
            section_start is not None
            and re.match(r"^## ", stripped)
            and stripped != section_heading_line
        ):
            section_end = i
            break

    if section_start is None:
        return content

    # Build a map of existing project_id → line index.
    existing: dict[str, int] = {}
    for i in range(section_start, section_end):
        m = _ROW_PID_RE.match(lines[i])
        if m:
            existing[m.group(1)] = i

    # Remove rows for project_ids that no longer belong in this section
    # (e.g. a release row that used to live in "## Development Projects").
    valid_pids = {file_to_project_id(f) for f in all_section_files}
    stale = [idx for pid, idx in existing.items() if pid not in valid_pids]
    for idx in stale:
        lines[idx] = ""
    # Rebuild existing map after removals.
    existing = {pid: idx for pid, idx in existing.items() if pid in valid_pids}

    # Replace rows for files updated in this run.
    for f in updated_files:
        pid = file_to_project_id(f)
        if pid in existing:
            version = get_latest_release_id(pid) if not include_qa else ""
            lines[existing[pid]] = (
                _make_row(
                    f,
                    include_qa,
                    include_obs_link,
                    obs_web_url,
                    obs_rootprj,
                    version=version,
                )
                + "\n"
            )

    # Find where to append new rows: after the last data row, or after the
    # separator line if there are no data rows yet.
    last_data_idx: int | None = None
    sep_idx: int | None = None
    for i in range(section_start, section_end):
        if _ROW_PID_RE.match(lines[i]):
            last_data_idx = i
        elif re.match(r"^\|---", lines[i]):
            sep_idx = i

    if last_data_idx is not None:
        insert_at = last_data_idx + 1
    elif sep_idx is not None:
        insert_at = sep_idx + 1
    else:
        insert_at = section_end

    new_rows = [
        _make_row(
            f,
            include_qa,
            include_obs_link,
            obs_web_url,
            obs_rootprj,
            version=(
                get_latest_release_id(file_to_project_id(f)) if not include_qa else ""
            ),
        )
        + "\n"
        for f in all_section_files
        if file_to_project_id(f) not in existing
    ]
    if new_rows:
        lines[insert_at:insert_at] = new_rows

    return "".join(lines)


def update_readme(updated_files: list[Path], all_version_files: list[Path]) -> None:
    obs_web_url = os.environ.get("OBS_WEB_URL", "").rstrip("/")
    obs_rootprj = os.environ.get("OBS_ROOTPRJ", "")
    include_obs_link = bool(obs_web_url and obs_rootprj)

    dev_updated = [
        f for f in updated_files if not is_release_project(file_to_project_id(f))
    ]
    rel_updated = [
        f for f in updated_files if is_release_project(file_to_project_id(f))
    ]
    dev_all = [
        f for f in all_version_files if not is_release_project(file_to_project_id(f))
    ]
    rel_all = [
        f for f in all_version_files if is_release_project(file_to_project_id(f))
    ]

    content = README.read_text(encoding="utf-8")

    content = _upsert_section(
        content,
        "Development Projects",
        _VERSION_LISTS_DESCRIPTION,
        dev_updated,
        dev_all,
        include_qa=True,
        include_obs_link=include_obs_link,
        obs_web_url=obs_web_url,
        obs_rootprj=obs_rootprj,
    )
    content = _upsert_section(
        content,
        "Current Releases",
        _CURRENT_RELEASES_DESCRIPTION,
        rel_updated,
        rel_all,
        include_qa=False,
        include_obs_link=include_obs_link,
        obs_web_url=obs_web_url,
        obs_rootprj=obs_rootprj,
    )

    README.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(cmd: list[str], **kwargs) -> None:
    subprocess.run(cmd, check=True, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate version list files and update README.md."
    )
    parser.add_argument(
        "--project",
        default="",
        metavar="PROJECT_ID",
        help=(
            "Regenerate only this project (e.g. ppg:releases:17). "
            "Used by obs-release.yml to update a single release project."
        ),
    )
    args = parser.parse_args()

    before = os.environ.get("GITHUB_EVENT_BEFORE", ZERO_SHA)
    head = os.environ.get("GITHUB_SHA", "HEAD")

    if args.project:
        all_known = find_all_distribution_projects()
        projects = [(pid, outfile) for pid, outfile in all_known if pid == args.project]
        if not projects:
            print(f"Project {args.project!r} not found under root/", file=sys.stderr)
            sys.exit(1)
        print(f"Updating single project: {args.project}")
    elif before == ZERO_SHA:
        print(
            "GITHUB_EVENT_BEFORE is zero SHA — regenerating all dev distribution projects."
        )
        all_known = find_all_distribution_projects()
        projects = [
            (pid, outfile) for pid, outfile in all_known if not is_release_project(pid)
        ]
    else:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", before, head], text=True
        ).splitlines()
        print(
            f"Changed files ({len(changed)}): {changed[:10]}{'...' if len(changed) > 10 else ''}"
        )
        all_changed = map_files_to_distribution_projects(changed)
        # Release projects have their own trigger (obs-release.yml); skip them here.
        projects = [
            (pid, outfile)
            for pid, outfile in all_changed
            if not is_release_project(pid)
        ]

    if not projects:
        print("No distribution projects to update.")
        return

    print(f"Distribution projects to update: {[pid for pid, _ in projects]}")

    # Configure git and pull before writing any files so there are no unstaged
    # changes when rebase runs.
    run(
        ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
        cwd=REPO_ROOT,
    )
    run(["git", "config", "user.name", "github-actions[bot]"], cwd=REPO_ROOT)
    run(["git", "pull", "--rebase"], cwd=REPO_ROOT)

    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    for project_id, outfile in projects:
        print(f"  Generating {outfile.relative_to(REPO_ROOT)} for {project_id} ...")
        md = subprocess.check_output(
            [
                "venv/bin/python",
                "-m",
                "percona_obs",
                "-P",
                "main",
                "project",
                "versions",
                project_id,
                "--recursive",
                "--online",
                "--markdown",
            ],
            text=True,
            cwd=REPO_ROOT,
        )
        print(f"    Adding install instructions for {project_id} ...")
        install = subprocess.run(
            [
                "venv/bin/python",
                "-m",
                "percona_obs",
                "-P",
                "main",
                "project",
                "install",
                project_id,
                "--markdown",
            ],
            text=True,
            capture_output=True,
            cwd=REPO_ROOT,
        )
        if install.returncode == 0 and install.stdout.strip():
            md = md + "\n" + install.stdout
        outfile.write_text(md, encoding="utf-8")

    updated_files = [outfile for _, outfile in projects]
    all_version_files = sorted(VERSIONS_DIR.glob("*.md"))
    update_readme(updated_files, all_version_files)

    run(["git", "add", str(VERSIONS_DIR), str(README)], cwd=REPO_ROOT)

    result = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=REPO_ROOT)
    if result.returncode != 0:
        run(
            ["git", "commit", "-m", "ci: update version lists [skip ci]"],
            cwd=REPO_ROOT,
        )
        run(["git", "push"], cwd=REPO_ROOT)
        print("Version lists committed and pushed.")
    else:
        print("No changes to commit.")


if __name__ == "__main__":
    sys.exit(main())
