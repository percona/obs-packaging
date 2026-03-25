import socket
import subprocess
import sys
from pathlib import Path

from .common import _REPO_DIR


def _check_git_clean() -> None:
    """Abort if the working tree has uncommitted changes under root/ or HEAD is not pushed to any remote."""
    # Uncommitted changes (staged or unstaged, including untracked) — scoped to
    # root/ so that changes to tooling files (percona_obs/, docs/, etc.) do not
    # block a packaging sync.
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "root/"],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    if result.returncode != 0:
        print(f"error: git status failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    if result.stdout.strip():
        print("error: there are uncommitted changes under root/.", file=sys.stderr)
        print(
            "       Commit or stash all changes before running this command.",
            file=sys.stderr,
        )
        sys.exit(1)

    # HEAD pushed to at least one remote
    result = subprocess.run(
        ["git", "branch", "-r", "--contains", "HEAD"],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    if result.returncode != 0:
        print(f"error: git failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    if not result.stdout.strip():
        print("error: HEAD commit has not been pushed to any remote.", file=sys.stderr)
        print("       Push your branch before running this command.", file=sys.stderr)
        sys.exit(1)


def _has_non_obs_package_changes_since(short_sha: str, package_path: Path) -> bool:
    """Return True if the net file-tree diff between short_sha and HEAD contains
    any file outside the obs/ subdirectory of package_path.

    Uses ``git diff --name-only`` which reports the *net* changes between the
    two tree states (reverted commits cancel out).  This is intentional: we
    want to know whether the packaging content that OBS will fetch is different,
    not merely whether any commits were made.

    Used to distinguish cosmetic obs/ rewrites (e.g. env-var substitutions)
    from real packaging changes (rpm/, debian/, package.yaml, etc.) so that the
    branch decision can skip the obsinfo check only when it is safe to do so.

    Returns True (treat as changed) if the SHA is unknown or git fails.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{short_sha}..HEAD", "--", str(package_path)],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    if result.returncode != 0:
        return True  # unknown SHA or git error — safe default
    if not result.stdout.strip():
        return False
    # git diff --name-only outputs paths relative to the repo root with
    # forward slashes on all platforms.
    try:
        obs_rel = str((package_path / "obs").relative_to(_REPO_DIR)) + "/"
    except ValueError:
        return True
    for line in result.stdout.splitlines():
        path = line.strip()
        if path and not path.startswith(obs_rel):
            return True
    return False


def _has_package_changes_since(short_sha: str, package_path: Path) -> bool:
    """Return True if the package directory has any git commits since short_sha.

    Checks the entire package directory (obs/, debian/, rpm/, package.yaml, etc.)
    so that changes to any packaging file also trigger a full sync.

    Returns True (treat as changed) if the SHA is unknown, git fails, or any
    commits are found. Returns False only when no commits touch the directory.
    """
    result = subprocess.run(
        ["git", "log", f"{short_sha}..HEAD", "--", str(package_path)],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    if result.returncode != 0:
        return True  # unknown SHA or git error — safe default: sync normally
    return bool(result.stdout.strip())


def _generate_sync_message(dirty: bool) -> str:
    """Build the default OBS commit message from the current git state.

    Normal:  sync: <branch>@<short-sha> (<remote_url>)
    Dirty:   sync: <branch>@<short-sha> (local changes on <hostname>)
    """

    def _git(*args: str) -> str:
        r = subprocess.run(
            ["git"] + list(args), capture_output=True, text=True, cwd=_REPO_DIR
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"

    short_sha = _git("rev-parse", "--short", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")

    if dirty:
        hostname = socket.gethostname()
        return f"sync: {branch}@{short_sha} (local changes on {hostname})"

    # Discover which remote contains HEAD rather than assuming "origin".
    # `git branch -r --contains HEAD` returns lines like "  origin/main", "  upstream/main".
    # Pick the first remote name found; fall back to "unknown" if none.
    remote_name = "unknown"
    for line in _git("branch", "-r", "--contains", "HEAD").splitlines():
        token = line.strip().split("/")[0]
        if token:
            remote_name = token
            break
    remote_url = (
        _git("remote", "get-url", remote_name)
        if remote_name != "unknown"
        else "unknown"
    )

    return f"sync: {branch}@{short_sha} ({remote_url})"
