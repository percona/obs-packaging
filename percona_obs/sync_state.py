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
"""

import hashlib
import json
from pathlib import Path

from .common import _REPO_DIR, logger
from .git_utils import (
    _has_package_changes_since,
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
    directory commits since the SHA, uncommitted edits, inherited macros —
    but requires no API call.
    """
    sha = manifest.get(key)
    if not sha:
        return False
    if _has_package_changes_since(sha, package_path):
        return False
    if _is_path_dirty(package_path):
        return False
    if _macros_changed_since(sha, package_path):
        return False
    return True
