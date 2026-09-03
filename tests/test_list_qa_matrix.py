"""Typing of OBS projects in the QA matrix script (.github/scripts/list_qa_matrix.py)."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "list_qa_matrix", Path(__file__).parent.parent / ".github/scripts/list_qa_matrix.py"
)
assert _SPEC is not None


def _load():
    assert _SPEC is not None
    mod = importlib.util.module_from_spec(_SPEC)
    assert _SPEC.loader is not None
    _SPEC.loader.exec_module(mod)
    return mod


def test_qa_project_type():
    m = _load()
    assert m.qa_project_type("x:ppg:staging:18:containers") == "containers"
    assert m.qa_project_type("x:ppg:releases:17:containers:ubi9") == "containers"
    assert m.qa_project_type("x:ppg:staging:17:extras:containers") == "containers"
    assert m.qa_project_type("x:ppg:staging:17:tarballs") == "packages"
    assert m.qa_project_type("x:ppg:staging:17") == "packages"
