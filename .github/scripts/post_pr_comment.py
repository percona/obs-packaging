#!/usr/bin/env python3
"""Post (or update) the obs-pr-check status comment on a PR.

Driven entirely by environment variables so it can be reused from any job
that has the repo checked out and a GH_TOKEN available.

Required env vars (set by the workflow):
  PR_NUMBER          PR number to comment on.
  GITHUB_REPOSITORY  owner/repo (set automatically by GitHub Actions).
  OBS_WEB_URL        Base URL of the OBS web UI.
  OBS_PR_ROOTPRJ     Root OBS project for PRs (e.g. home:Admin:percona).
  WORKFLOW_RUN_URL   URL of the current workflow run.
  IS_RELEASE_PR      'true' if the PR is release-only.
  SYNC_OUTCOME       Outcome of the sync step ('success', 'failure', '').
  RELEASE_OUTCOME    Outcome of the release step ('success', 'failure', '').
  POLL_OUTCOME       Outcome of the OBS-build poll step (or empty when
                     polling has not happened yet — e.g. on the sync side).

Reads (when present):
  /tmp/sync-output.txt        Raw `sync push` output (parsed for counts).
  /tmp/obs-build-details.json Per-repo build status counts written by
                              poll_obs_builds.py.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess


def main() -> None:
    pr_number = os.environ["PR_NUMBER"]
    repo = os.environ["GITHUB_REPOSITORY"]
    obs_web_url = os.environ["OBS_WEB_URL"].rstrip("/")
    obs_pr_rootprj = os.environ["OBS_PR_ROOTPRJ"]
    is_release_pr = os.environ.get("IS_RELEASE_PR") == "true"
    sync_ok = os.environ.get("SYNC_OUTCOME") == "success"
    release_outcome = os.environ.get("RELEASE_OUTCOME", "")
    poll_outcome = os.environ.get("POLL_OUTCOME", "")
    workflow_run_url = os.environ["WORKFLOW_RUN_URL"]
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    pr_rootprj = f"{obs_pr_rootprj}:pr-{pr_number}"
    project_url = f"{obs_web_url}/project/show/{pr_rootprj}"

    # Read per-repo details JSON written by poll_obs_builds.py (if it ran).
    details: dict = {}
    try:
        details = json.load(open("/tmp/obs-build-details.json"))
    except (OSError, json.JSONDecodeError):
        pass

    if is_release_pr:
        if release_outcome == "success":
            heading = "## OBS Release Check — ✅ Release dry-run passed"
        elif release_outcome == "failure":
            heading = "## OBS Release Check — ❌ Release dry-run failed"
        elif release_outcome == "skipped":
            heading = "## OBS Release Check — ⏭️ Release test skipped"
        else:
            heading = "## OBS Release Check"

        # Derive the per-release OBS project links from the added release.yaml files.
        added = (
            subprocess.run(
                [
                    "git",
                    "diff",
                    "--name-only",
                    "--diff-filter=A",
                    "origin/main...HEAD",
                    "--",
                    "root/*/releases/*/release.yaml",
                ],
                capture_output=True,
                text=True,
            )
            .stdout.strip()
            .splitlines()
        )
        release_links = []
        for rf in added:
            rel_dir = rf.removeprefix("root/").removesuffix("/release.yaml")
            rel_project = rel_dir.replace("/", ":")
            obs_proj = f"{pr_rootprj}:{rel_project}"
            release_links.append(
                f"**[{obs_proj}]({obs_web_url}/project/show/{obs_proj})**"
            )
        projects_str = (
            ", ".join(release_links) if release_links else f"**{pr_rootprj}**"
        )

        lines = [
            "<!-- obs-pr-check -->",
            heading,
            "",
            "This PR adds a release record. No packages are built in OBS.",
            f"The release dry-run created {projects_str} on OBS.",
            "",
            f"> _Updated: {timestamp}_",
        ]
    elif sync_ok:
        try:
            output = open("/tmp/sync-output.txt").read()
        except OSError:
            output = ""

        # Aggregated packages produce '  @ <project>/<pkg>  → ...' lines.
        aggregated = len(re.findall(r"^  @ ", output, re.MULTILINE))
        # Promoted packages produce '  ~ N files ...' or '  + N files ...' lines.
        promoted = len(re.findall(r"^  [~+] \d+ files ", output, re.MULTILINE))

        # Determine heading based on poll outcome.
        if poll_outcome == "success":
            heading = "## OBS Build Check — ✅ Builds passed"
        elif poll_outcome == "failure":
            heading = "## OBS Build Check — ❌ Builds failed"
        elif poll_outcome == "cancelled":
            heading = "## OBS Build Check — ⏱️ Build polling cancelled"
        else:
            heading = "## OBS Build Check"

        lines = [
            "<!-- obs-pr-check -->",
            heading,
            "",
            f"Packages for this PR are being built at **[{pr_rootprj}]({project_url})**.",
            "",
            "| | Packages |",
            "|---|---|",
            f"| Built from PR sources | {promoted} |",
            f"| Reused from `main` binaries | {aggregated} |",
        ]

        if details:
            repos = details.get("repos", {})
            total = details.get("total", {})
            lines += [
                "",
                "| Repository | ✔ Succeeded | ✗ Failed | ⛔ Broken | ⚠ Unresolvable | — Excluded |",
                "|---|---|---|---|---|---|",
            ]
            for obs_repo, counts in sorted(repos.items()):
                lines.append(
                    f"| {obs_repo} "
                    f'| {counts.get("succeeded", 0)} '
                    f'| {counts.get("failed", 0)} '
                    f'| {counts.get("broken", 0)} '
                    f'| {counts.get("unresolvable", 0)} '
                    f'| {counts.get("excluded", 0)} |'
                )
            lines.append(
                f"| **Total** "
                f'| **{total.get("succeeded", 0)}** '
                f'| **{total.get("failed", 0)}** '
                f'| **{total.get("broken", 0)}** '
                f'| **{total.get("unresolvable", 0)}** '
                f'| **{total.get("excluded", 0)}** |'
            )

        lines += ["", f"> _Updated: {timestamp}_"]
    else:
        lines = [
            "<!-- obs-pr-check -->",
            "## OBS Build Check — ❌ Sync failed",
            "",
            f"The OBS sync step failed. See the [workflow run]({workflow_run_url}) for details.",
            "",
            f"> _Updated: {timestamp}_",
        ]

    body = "\n".join(lines)
    with open("/tmp/pr-comment.md", "w") as f:
        f.write(body)

    # Find an existing obs-pr-check comment to update; otherwise create one.
    # --paginate fetches all pages so the search works even when the PR
    # has more than 30 comments (GitHub API's default page size).
    result = subprocess.run(
        [
            "gh",
            "api",
            "--paginate",
            f"repos/{repo}/issues/{pr_number}/comments",
            "--jq",
            '[.[] | select(.body | contains("<!-- obs-pr-check -->"))] | last | .id // empty',
        ],
        capture_output=True,
        text=True,
    )
    comment_id = result.stdout.strip()

    if comment_id:
        subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/issues/comments/{comment_id}",
                "-X",
                "PATCH",
                "-F",
                "body=@/tmp/pr-comment.md",
            ],
            check=True,
        )
    else:
        subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/issues/{pr_number}/comments",
                "-X",
                "POST",
                "-F",
                "body=@/tmp/pr-comment.md",
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
