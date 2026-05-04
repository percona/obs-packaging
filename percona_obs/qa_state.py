"""Persistent state for `qa run` / `qa retry` / `qa status` / `qa list`.

Each `qa run` invocation writes a single state file at
`.percona-obs/qa/<run-id>.json` capturing the resolved matrix, the parameters
sent to Jenkins, and one or more attempts per combo. `qa retry` re-uses this
file to identify failed combos and append new attempts; `qa status` re-polls
non-terminal attempts; `qa list` enumerates recent runs.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import secrets
import time
from pathlib import Path

from .common import REPO_ROOT, logger

_STATE_DIR = REPO_ROOT.parent / ".percona-obs" / "qa"

# Auto-GC retention: a run is considered finished when every combo has a
# terminal result; if the state file has been idle (no save_state) for at
# least this long, it is deleted by gc_old_runs().
GC_RETENTION_SECONDS = 24 * 60 * 60


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{secrets.token_hex(2)}"


@dataclasses.dataclass
class Attempt:
    triggered_at: str
    queue_url: str
    build_url: str | None = None
    result: str | None = None
    error: str | None = None


@dataclasses.dataclass
class Combo:
    label: str
    params: dict[str, str]
    attempts: list[Attempt] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class RunState:
    run_id: str
    project: str
    pipeline: str
    created_at: str
    combos: list[Combo]


def _state_path(run_id: str) -> Path:
    return _STATE_DIR / f"{run_id}.json"


def save_state(state: RunState) -> Path:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _state_path(state.run_id)
    payload = dataclasses.asdict(state)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def load_state(run_id: str) -> RunState:
    path = _state_path(run_id)
    if not path.is_file():
        raise SystemExit(f"error: qa run-id {run_id!r} not found at {path}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    combos = [
        Combo(
            label=c["label"],
            params=c["params"],
            attempts=[Attempt(**a) for a in c.get("attempts", [])],
        )
        for c in data["combos"]
    ]
    return RunState(
        run_id=data["run_id"],
        project=data["project"],
        pipeline=data["pipeline"],
        created_at=data["created_at"],
        combos=combos,
    )


def list_runs() -> list[RunState]:
    if not _STATE_DIR.is_dir():
        return []
    runs: list[RunState] = []
    for path in sorted(_STATE_DIR.glob("*.json"), reverse=True):
        try:
            runs.append(load_state(path.stem))
        except Exception:
            continue
    return runs


def is_run_terminal(state: RunState) -> bool:
    """Return True if every combo's latest attempt has a terminal result."""
    if not state.combos:
        return False
    return all(c.attempts and c.attempts[-1].result is not None for c in state.combos)


def gc_old_runs(retention_seconds: int = GC_RETENTION_SECONDS) -> int:
    """Delete state files for terminal runs idle for >= retention_seconds.

    "Idle" is measured by the file's mtime, which save_state() updates on
    every state transition. Returns the number of files deleted.
    """
    if not _STATE_DIR.is_dir():
        return 0
    cutoff = time.time() - retention_seconds
    deleted = 0
    for path in _STATE_DIR.glob("*.json"):
        try:
            if path.stat().st_mtime > cutoff:
                continue
            state = load_state(path.stem)
        except Exception:
            continue
        if is_run_terminal(state):
            try:
                path.unlink()
                deleted += 1
                logger.debug(f"qa gc: removed {path.name}")
            except OSError:
                pass
    return deleted


def write_report_json(state: RunState, path: Path) -> None:
    """Write a flattened report (latest attempt only) for CI consumption."""
    payload = {
        "run_id": state.run_id,
        "project": state.project,
        "pipeline": state.pipeline,
        "created_at": state.created_at,
        "combos": [
            {
                "label": c.label,
                "params": c.params,
                "queue_url": c.attempts[-1].queue_url if c.attempts else None,
                "build_url": c.attempts[-1].build_url if c.attempts else None,
                "result": c.attempts[-1].result if c.attempts else None,
                "error": c.attempts[-1].error if c.attempts else None,
            }
            for c in state.combos
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
