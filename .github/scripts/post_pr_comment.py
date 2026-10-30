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
  RELEASE_OUTCOME    Outcome of the pre-release populate step (informational;
                     the comment is rendered from PRERELEASE_REPORT).
  POLL_OUTCOME       Outcome of the OBS-build poll step (or empty when
                     polling has not happened yet — e.g. on the sync side).
  OBS_INSTANCE       Name of the OBS instance this comment is about (empty
                     for a single-instance setup).  Each instance owns one
                     comment: the marker and the heading carry the name.

Reads (when present):
  /tmp/prerelease-report.json Release PR only (path overridable via
                              PRERELEASE_REPORT): JSON list of
                              {project, prerelease, outcome, source_commit}
                              written by obs-release-pr.yml.
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


def render_prerelease_comment(
    marker: str,
    suffix: str,
    report: list[dict],
    web_url: str,
    run_url: str,
    timestamp: str,
    pr_number: str,
    repo: str,
) -> str:
    """Markdown for a release PR: one row per pre-release project.

    ``report`` is the list written by obs-release-pr.yml:
    ``[{project, prerelease, outcome, source_commit}]``.
    """
    if not report:
        heading = "## OBS Release PR — ⚠️ no pre-release populated" + suffix
    elif all(r.get("outcome") == "success" for r in report):
        heading = "## OBS Release PR — ✅ Pre-release populated" + suffix
    else:
        heading = "## OBS Release PR — ❌ Pre-release population failed" + suffix
    lines = [
        marker,
        heading,
        "",
        "Release QA runs against the pre-release projects below once the `qa-release` "
        "label is on the PR; nothing is built in OBS.",
        "",
        "| Release | Pre-release project | Populate | Source commit |",
        "|---|---|---|---|",
    ]
    for r in report:
        pre = r.get("prerelease", "")
        outcome = r.get("outcome", "")
        icon = {"success": "✅", "failure": "❌"}.get(outcome, "⚠️")
        commit = (r.get("source_commit") or "")[:12]
        lines.append(
            f"| `{r.get('project', '')}` | [{pre}]({web_url}/project/show/{pre}) "
            f"| {icon} {outcome} | `{commit}` |"
        )
    lines += [
        "",
        f"Repopulate without a push: `gh workflow run obs-release-pr.yml -f pr_number={pr_number}`",
        f"Details: [workflow run]({run_url}).",
        "",
        f"> _Updated: {timestamp}_",
    ]
    return "\n".join(lines)


def main() -> None:
    pr_number = os.environ["PR_NUMBER"]
    repo = os.environ["GITHUB_REPOSITORY"]
    obs_web_url = os.environ["OBS_WEB_URL"].rstrip("/")
    obs_pr_rootprj = os.environ["OBS_PR_ROOTPRJ"]
    is_release_pr = os.environ.get("IS_RELEASE_PR") == "true"
    sync_ok = os.environ.get("SYNC_OUTCOME") == "success"
    release_outcome = os.environ.get("RELEASE_OUTCOME", "")
    poll_outcome = os.environ.get("POLL_OUTCOME", "")
    instance = os.environ.get("OBS_INSTANCE", "")
    marker = (
        f"<!-- obs-pr-check:{instance} -->" if instance else "<!-- obs-pr-check -->"
    )
    suffix = f" ({instance})" if instance else ""
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
        try:
            report = json.load(
                open(os.environ.get("PRERELEASE_REPORT", "/tmp/prerelease-report.json"))
            )
        except (OSError, json.JSONDecodeError):
            report = []
        body = render_prerelease_comment(
            marker,
            suffix,
            report if isinstance(report, list) else [],
            obs_web_url,
            workflow_run_url,
            timestamp,
            pr_number,
            repo,
        )
        lines = body.split("\n")
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
            heading = "## OBS Build Check — ✅ Builds passed" + suffix
        elif poll_outcome == "failure":
            heading = "## OBS Build Check — ❌ Builds failed" + suffix
        elif poll_outcome == "cancelled":
            heading = "## OBS Build Check — ⏱️ Build polling cancelled" + suffix
        else:
            heading = "## OBS Build Check" + suffix

        lines = [
            marker,
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
            marker,
            "## OBS Build Check — ❌ Sync failed" + suffix,
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
            f'[.[] | select(.body | contains("{marker}"))] | last | .id // empty',
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
