import socket
import subprocess
import sys
from pathlib import Path

_REPO_DIR = Path(__file__).parent.parent
# Top of the packaging tree; mirrors common.REPO_ROOT.  Defined locally to keep
# this module free of an import cycle with common (which imports git_utils).
_REPO_ROOT = _REPO_DIR / "root"


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

    # Block only if there are unpushed commits that touch root/.
    # 'git log HEAD --not --remotes -- root/' lists commits reachable from
    # HEAD but not from any remote ref that change files under root/.
    result = subprocess.run(
        ["git", "log", "HEAD", "--not", "--remotes", "--oneline", "--", "root/"],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    if result.returncode != 0:
        print(f"error: git log failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    if result.stdout.strip():
        print("error: there are unpushed commits that modify root/.", file=sys.stderr)
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


def _has_package_content_changes_since(short_sha: str, package_path: Path) -> bool:
    """Return True if any file under package_path has net content changes since short_sha.

    Uses ``git diff --name-only`` (tree-state comparison) rather than ``git log``
    (commit counting).  This means:
    - Rebased commits with identical content are not counted as changes.
    - Reverted changes cancel out and are not counted.
    - Env-var substitution values baked into obs/ files at upload time do not
      appear here because the local templates still contain the raw ``${VAR}``
      tokens — those never change unless the template itself is edited.

    Returns True (treat as changed) if the SHA is unknown or git fails.
    """
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            f"{short_sha}..HEAD",
            "--",
            str(package_path),
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    if result.returncode != 0:
        return True
    return bool(result.stdout.strip())


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


def _is_path_dirty(*paths: Path) -> bool:
    """Return True if the working tree has uncommitted changes under any of *paths*.

    Covers staged, unstaged, and untracked files (``git status --porcelain``).
    The branch-decision fast path trusts committed git history, but the upload
    is built from the working tree, so uncommitted edits to inputs that feed a
    package's content must route the decision to the authoritative content check.

    With no paths given it returns False; on git error it returns True
    (safe default).
    """
    if not paths:
        return False
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", *(str(p) for p in paths)],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    if result.returncode != 0:
        return True  # git error — safe default: treat as dirty
    return bool(result.stdout.strip())


def _inherited_macros_files(package_path: Path) -> list[Path]:
    """Return the macros.yaml files inherited by package_path from ancestor dirs.

    Mirrors ``load_macros``' walk (REPO_ROOT .. package_path) but stops *above*
    the package directory: a macros.yaml inside package_path is already covered
    by the package-directory change checks.  These ancestor files declare macros
    that are substituted into the package's uploaded content.
    """
    files: list[Path] = []
    p = package_path.parent
    while True:
        macro_file = p / "macros.yaml"
        if macro_file.is_file():
            files.append(macro_file)
        if p == _REPO_ROOT or not p.is_relative_to(_REPO_ROOT):
            break
        p = p.parent
    return files


def _macros_changed_since(short_sha: str, package_path: Path) -> bool:
    """Return True if any macros.yaml inherited by package_path changed.

    Inherited (ancestor) macros are substituted into the package's uploaded
    content, so a change to one alters what would be uploaded even when no file
    inside package_path moved.  Considers both committed changes since short_sha
    and uncommitted working-tree edits, because the upload is built from the
    working tree rather than from committed history.

    Returns True (treat as changed) on git error (safe default).  A macros.yaml
    inside package_path is intentionally excluded — it is covered by the
    package-directory change checks.
    """
    files = _inherited_macros_files(package_path)
    if not files:
        return False
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            f"{short_sha}..HEAD",
            "--",
            *(str(f) for f in files),
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    if result.returncode != 0:
        return True  # unknown SHA or git error — safe default
    if result.stdout.strip():
        return True
    return _is_path_dirty(*files)


def _generate_sync_message() -> str:
    """Build the default OBS commit message from the current git state.

    Format: sync: <branch>@<short-sha> (<remote_url> or <hostname>)
    """

    def _git(*args: str) -> str:
        r = subprocess.run(
            ["git"] + list(args), capture_output=True, text=True, cwd=_REPO_DIR
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"

    short_sha = _git("rev-parse", "--short", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")

    # Discover which remote contains HEAD rather than assuming "origin".
    # `git branch -r --contains HEAD` returns lines like "  origin/main", "  upstream/main".
    # Pick the first remote name found; fall back to hostname.
    remote_name = ""
    for line in _git("branch", "-r", "--contains", "HEAD").splitlines():
        token = line.strip().split("/")[0]
        if token:
            remote_name = token
            break
    if remote_name:
        detail = _git("remote", "get-url", remote_name)
    else:
        detail = f"local changes on {socket.gethostname()}"

    return f"sync: {branch}@{short_sha} ({detail})"


def get_file_commit_time(path: Path) -> float | None:
    """Return the Unix timestamp of the last git commit that touched *path*.

    Returns None if the file has no commits (untracked or new/uncommitted).
    """
    result = subprocess.run(
        ["git", "log", "-1", "--format=%at", "--", str(path)],
        capture_output=True,
        text=True,
        cwd=_REPO_DIR,
    )
    ts = result.stdout.strip()
    return float(ts) if ts else None
