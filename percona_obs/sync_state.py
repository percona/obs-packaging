"""Local manifest of the last-synced git SHA per OBS package.

The manifest lets ``sync push --skip-unchanged`` decide "nothing to do" with
zero OBS API calls: if the recorded SHA matches HEAD's history for the package
directory (and nothing is dirty), the package is skipped without even fetching
the OBS revision comment.  The manifest lives under ``.cache/sync_state/`` —
persisted between CI runs by actions/cache — and is keyed by (apiurl, rootprj)
so different profiles/instances never share entries.

The manifest is an optimization layer only: a missing, stale, or evicted
manifest falls back to the OBS revision-comment check, and any doubt there
falls back to the normal promote path whose MD5 comparison is authoritative.

Two properties keep a manifest entry honest:

- Cleanliness is a *tree-diff* against the recorded SHA (``git diff sha..HEAD``),
  not a commit-log check.  A history rewrite (e.g. resetting away an unpushed
  commit that was already uploaded) produces an empty log but a non-empty
  diff, so the package correctly routes to promote.
- Recording requires HEAD to be pushed and the package inputs (directory plus
  inherited macros.yaml files) to be clean, so the SHA durably names exactly
  the content that was uploaded.
"""

import hashlib
import json
from pathlib import Path

from .common import _REPO_DIR, logger
from .git_utils import (
    _has_package_content_changes_since,
    _inherited_macros_files,
    _is_path_dirty,
    _macros_changed_since,
)

_SYNC_STATE_DIR = _REPO_DIR / ".cache" / "sync_state"


def _manifest_path(apiurl: str, rootprj: str) -> Path:
    key = hashlib.sha256(f"{apiurl}|{rootprj}".encode()).hexdigest()[:16]
    return _SYNC_STATE_DIR / f"{key}.json"


def load_manifest(apiurl: str, rootprj: str) -> dict[str, str]:
    """Return the {'project/package': 'short-sha'} manifest, or {} when absent/corrupt."""
    path = _manifest_path(apiurl, rootprj)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def save_manifest(apiurl: str, rootprj: str, manifest: dict[str, str]) -> None:
    """Atomically write the manifest (tmp file + rename)."""
    path = _manifest_path(apiurl, rootprj)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning(f"sync-state manifest save failed: {exc}")


def manifest_entry_clean(
    manifest: dict[str, str], key: str, package_path: Path
) -> bool:
    """Return True when the manifest SHA for *key* is present and nothing changed.

    Runs the same local git checks as the OBS-comment fast path — package
    content diff against the SHA, uncommitted edits, inherited macros — but
    requires no API call.  The content check is a tree diff (``git diff
    sha..HEAD``) rather than a commit log so that history rewrites which
    change the tree (e.g. ``git reset --hard`` past an uploaded commit) are
    always detected, even when the recorded SHA is not an ancestor of HEAD.
    """
    sha = manifest.get(key)
    if not sha:
        return False
    if _has_package_content_changes_since(sha, package_path):
        return False
    if _is_path_dirty(package_path):
        return False
    if _macros_changed_since(sha, package_path):
        return False
    return True


def record_or_invalidate(
    manifest: dict[str, str],
    key: str,
    head_sha: str | None,
    head_pushed: bool,
    package_path: Path,
    invalidate: bool = True,
) -> None:
    """Record *head_sha* for *key* when it can honestly represent the upload.

    Honest means: HEAD is pushed (an unpushed SHA can be reset away, leaving
    a stale entry whose emptiness would wrongly claim OBS matches) and the
    package inputs — the package directory and its inherited macros.yaml
    files — carry no uncommitted edits (uploaded content would bake in state
    no SHA represents).

    When the conditions fail:

    - ``invalidate=True`` (promote path): drop any existing entry — the
      upload that just happened invalidated whatever the old entry claimed.
    - ``invalidate=False`` (skip path): leave the manifest untouched — the
      package was just verified clean against its existing state, so an
      existing entry is still valid; it just cannot be refreshed to HEAD.
    """
    if (
        head_sha
        and head_pushed
        and not _is_path_dirty(package_path, *_inherited_macros_files(package_path))
    ):
        manifest[key] = head_sha
    elif invalidate:
        manifest.pop(key, None)
