"""Pure helpers of the release-cut workflow (.github/scripts/release_cut.py)."""

import importlib.util
import json
from pathlib import Path

_SCRIPTS = Path(__file__).parent.parent / ".github/scripts"


def _load():
    spec = importlib.util.spec_from_file_location(
        "release_cut", _SCRIPTS / "release_cut.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_check_units():
    m = _load()
    assert len(m.check_units([], {"a": {}})) == 1
    errs = m.check_units(["a", "a"], {"a": {}})
    assert len(errs) == 1 and "a" in errs[0] and "repeated" in errs[0]
    assert m.check_units(["ppg:staging:18:containers"], {"ppg:staging:18": {}}) == [
        "ppg:staging:18:containers: not a release unit root"
    ]
    assert m.check_units(["a", "b"], {"a": {}, "b": {}}) == []
    assert m.check_units(["--help"], {"a": {}}) == ["--help: not a release unit root"]


def test_check_cli_rejects_option_like_token(capsys):
    m = _load()
    assert m.main(["check", "--", "--help"]) == 1
    assert "::error::--help: not a release unit root" in capsys.readouterr().out


_LOG = "# h\n\n## [18.6-10] - d\n\nA\n\n## [18.6-1] - d\n\nB\n"


def test_changelog_section():
    m = _load()
    assert m.changelog_section(_LOG, "18.6-1") == "## [18.6-1] - d\n\nB\n"
    assert m.changelog_section(_LOG, "18.6-10") == "## [18.6-10] - d\n\nA\n"
    assert m.changelog_section(_LOG, "18.6-2") is None
    assert m.changelog_section(_LOG, "18x6-1") is None


def _repo(tmp_path, units):
    (tmp_path / "docs/versions").mkdir(parents=True)
    listing = []
    for unit, rel_dir, entries, rid in units:
        d = tmp_path / rel_dir
        d.mkdir(parents=True)
        lines = ["releases:"]
        for e in entries:
            lines.append(
                f"  - {e}"
                if isinstance(e, str)
                else f"  - {{tag: {e[0]}, source_commit: {e[1]}}}"
            )
        (d / "release.yaml").write_text("\n".join(lines) + "\n")
        (d / "CHANGELOG.md").write_text(f"# c\n\n## [{rid}] - d\n\nbody {rid}\n")
        listing.append(
            {
                "unit": unit,
                "members": [unit],
                "release_project": "x",
                "release_dir": rel_dir,
            }
        )
    (tmp_path / "docs/versions/release-units.json").write_text(json.dumps(listing))


def test_release_id(tmp_path):
    m = _load()
    _repo(
        tmp_path,
        [
            ("u1", "r/18", ["ppg/18.6-5", ("ppg/18.6-6", "abc")], "18.6-6"),
            ("u2", "r/18x", ["ppg/extras-18.6-6"], "extras-18.6-6"),
        ],
    )
    assert m.release_id(tmp_path / "r/18") == "18.6-6"
    assert m.release_id(tmp_path / "r/18x") == "extras-18.6-6"


def test_summarize_cli(tmp_path, monkeypatch, capsys):
    m = _load()
    _repo(
        tmp_path,
        [
            ("u1", "r/18", [("ppg/18.6-6", "abc")], "18.6-6"),
            ("u2", "r/18x", ["ppg/extras-18.6-6"], "extras-18.6-6"),
        ],
    )
    monkeypatch.setattr(m, "REPO_DIR", tmp_path)
    out = tmp_path / "out.json"
    assert m.main(["summarize", "--out", str(out), "u1", "u2"]) == 0
    assert capsys.readouterr().out.strip() == "release: 18.6-6, extras-18.6-6"
    assert set(json.loads(out.read_text())) == {"u1", "u2"}


def test_summarize_missing_section_fails(tmp_path, monkeypatch, capsys):
    m = _load()
    _repo(tmp_path, [("u1", "r/18", ["ppg/18.6-6"], "18.6-6")])
    (tmp_path / "r/18/CHANGELOG.md").write_text("# c\n")
    monkeypatch.setattr(m, "REPO_DIR", tmp_path)
    assert m.main(["summarize", "--out", str(tmp_path / "o.json"), "u1"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""  # stdout is captured as the commit subject
    assert captured.err.startswith("::error::u1:")
