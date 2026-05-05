#!/usr/bin/env python3
"""Regenerate docs/versions/<dist>.md version-list files and update README.md.

Called from the "Update version lists" step in sync-main.yml and from the
standalone update-version-lists.yml workflow.

Environment variables
---------------------
GITHUB_EVENT_BEFORE
    The "before" SHA from the GitHub push event.  Set to the all-zeros SHA
    (or omit) to regenerate *all* distribution projects instead of only those
    touched by the current push.
GITHUB_SHA
    The current HEAD commit SHA (always set by GitHub Actions).
"""

from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Project discovery helpers
# ---------------------------------------------------------------------------


def _project_entry(product: str, rest: list[str]) -> tuple[str, Path] | None:
    """Return (project_id, outfile) for a candidate distribution directory.

    ``rest`` contains the path segments after the product directory, e.g.
    ``["17"]`` or ``["releases", "17.9"]``.
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
    """Return all distribution projects found under root/."""
    results: list[tuple[str, Path]] = []
    for product_dir in sorted(ROOT_DIR.iterdir()):
        if not product_dir.is_dir() or product_dir.name == "common":
            continue
        product = product_dir.name
        for sub in sorted(product_dir.iterdir()):
            if not sub.is_dir():
                continue
            if sub.name == "releases":
                for rel in sorted(sub.iterdir()):
                    if rel.is_dir():
                        entry = _project_entry(product, ["releases", rel.name])
                        if entry:
                            results.append(entry)
            else:
                entry = _project_entry(product, [sub.name])
                if entry:
                    results.append(entry)
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
        if parts[1] == "releases" and len(parts) >= 3:
            rest = ["releases", parts[2]]
        else:
            rest = [parts[1]]

        key = ":".join([product] + rest)
        if key in seen:
            continue
        seen.add(key)

        entry = _project_entry(product, rest)
        if entry:
            results.append(entry)

    return sorted(results)


# ---------------------------------------------------------------------------
# README helpers
# ---------------------------------------------------------------------------


def file_to_project_id(path: Path) -> str:
    """Reverse the docs/versions/<product>-<devproj>.md → project_id mapping.

    ``ppg-17.md``          → ``ppg:17``
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


def update_readme(all_version_files: list[Path]) -> None:
    obs_web_url = os.environ.get("OBS_WEB_URL", "").rstrip("/")
    obs_rootprj = os.environ.get("OBS_ROOTPRJ", "")
    include_obs_link = bool(obs_web_url and obs_rootprj)

    content = README.read_text(encoding="utf-8")

    # Remove any existing "## Version Lists" section (up to the next ## heading
    # or end of file) so it can be regenerated in the correct position.
    content = re.sub(r"\n## Version Lists\n[\s\S]*?(?=\n## |\Z)", "", content)

    if not all_version_files:
        README.write_text(content, encoding="utf-8")
        return

    if include_obs_link:
        header = "| Distribution | OBS Project | Version List |"
        sep = "|---|---|---|"
        rows = "\n".join(
            (
                f"| `{file_to_project_id(f)}` "
                f"| [{obs_rootprj}:{file_to_project_id(f)}]"
                f"({obs_web_url}/project/show/{obs_rootprj}:{file_to_project_id(f)}) "
                f"| [{f.relative_to(REPO_ROOT)}]({f.relative_to(REPO_ROOT)}) |"
            )
            for f in all_version_files
        )
    else:
        header = "| Distribution | Version List |"
        sep = "|---|---|"
        rows = "\n".join(
            f"| `{file_to_project_id(f)}` | [{f.relative_to(REPO_ROOT)}]({f.relative_to(REPO_ROOT)}) |"
            for f in all_version_files
        )

    section = (
        "\n## Version Lists\n"
        f"\n{_VERSION_LISTS_DESCRIPTION}\n"
        "\n"
        f"{header}\n"
        f"{sep}\n"
        f"{rows}\n"
    )

    # Insert before "## Documentation" so the section appears right after the
    # repository introduction, not at the end of the file.
    if "\n## Documentation\n" in content:
        content = content.replace(
            "\n## Documentation\n", section + "\n## Documentation\n", 1
        )
    else:
        content += section

    README.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(cmd: list[str], **kwargs) -> None:
    subprocess.run(cmd, check=True, **kwargs)


def main() -> None:
    before = os.environ.get("GITHUB_EVENT_BEFORE", ZERO_SHA)
    head = os.environ.get("GITHUB_SHA", "HEAD")

    if before == ZERO_SHA:
        print(
            "GITHUB_EVENT_BEFORE is zero SHA — regenerating all distribution projects."
        )
        projects = find_all_distribution_projects()
    else:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", before, head], text=True
        ).splitlines()
        print(
            f"Changed files ({len(changed)}): {changed[:10]}{'...' if len(changed) > 10 else ''}"
        )
        projects = map_files_to_distribution_projects(changed)

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
        outfile.write_text(md, encoding="utf-8")

    # Rebuild README section from ALL existing version files (not just those
    # updated this run) so partial runs keep the table consistent.
    all_version_files = sorted(VERSIONS_DIR.glob("*.md"))
    update_readme(all_version_files)

    # Commit and push only when something actually changed.
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
