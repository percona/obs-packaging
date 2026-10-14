"""Rendering of the pre-release PR comment (.github/scripts/post_pr_comment.py)."""

import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).parent.parent / ".github/scripts"


def _load():
    spec = importlib.util.spec_from_file_location(
        "post_pr_comment", _SCRIPTS / "post_pr_comment.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_REPORT = [
    {
        "project": "ppg:releases:18",
        "prerelease": "isv:percona:PR:pr-7:ppg:releases:18",
        "outcome": "success",
        "source_commit": "9e9d9738c0ffee1234567890",
    },
    {
        "project": "ppg:releases:17",
        "prerelease": "isv:percona:PR:pr-7:ppg:releases:17",
        "outcome": "failure",
        "source_commit": "9e9d9738c0ffee1234567890",
    },
]


def test_render_failure_when_any_project_failed():
    m = _load()
    out = m.render_prerelease_comment(
        "<!-- m -->", " (boo)", _REPORT, "https://obs", "https://run", "now", "7", "o/r"
    )
    assert out.startswith(
        "<!-- m -->\n## OBS Release PR — ❌ Pre-release population failed (boo)"
    )
    assert (
        "[isv:percona:PR:pr-7:ppg:releases:18](https://obs/project/show/isv:percona:PR:pr-7:ppg:releases:18)"
        in out
    )
    assert "9e9d9738c0ff" in out and "9e9d9738c0ffee1234567890" not in out
    assert "gh workflow run obs-release-pr.yml -f pr_number=7" in out
    assert "https://run" in out


def test_render_success_and_empty():
    m = _load()
    ok = [dict(_REPORT[0])]
    assert "✅ Pre-release populated" in m.render_prerelease_comment(
        "<!-- m -->", "", ok, "https://obs", "r", "t", "7", "o/r"
    )
    assert "⚠️ no pre-release populated" in m.render_prerelease_comment(
        "<!-- m -->", "", [], "https://obs", "r", "t", "7", "o/r"
    )
