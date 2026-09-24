"""``${OBS_CONTAINER_REGISTRY}``: the profile ``registry`` key and its precedence."""

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import percona_obs.cli as cli
import percona_obs.cmd_profile as cmd_profile
import percona_obs.cmd_qa as cmd_qa
import percona_obs.common as common
from percona_obs.common import (
    DEFAULT_CONTAINER_REGISTRY,
    parse_env_overrides,
    registry_env_override,
)


@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    d = tmp_path / ".profile"
    d.mkdir()
    monkeypatch.setattr(cmd_profile, "_PROFILES_DIR", d)
    return d


@pytest.fixture(autouse=True)
def _reset_default_filter():
    common.set_default_repository_filter(None)
    yield
    common.set_default_repository_filter(None)


# --- the helper ------------------------------------------------------------------


def test_registry_env_override():
    assert registry_env_override(None) == (
        f"OBS_CONTAINER_REGISTRY:{DEFAULT_CONTAINER_REGISTRY}"
    )
    assert registry_env_override("") == (
        f"OBS_CONTAINER_REGISTRY:{DEFAULT_CONTAINER_REGISTRY}"
    )
    assert registry_env_override("registry.example.com") == (
        "OBS_CONTAINER_REGISTRY:registry.example.com"
    )
    assert parse_env_overrides([registry_env_override("reg.local")]) == {
        "OBS_CONTAINER_REGISTRY": "reg.local"
    }


# --- profile create --registry ---------------------------------------------------


def _create_args(**kw):
    base = dict(
        apiurl="https://labs",
        rootprj="percona",
        name="labs",
        env_overrides=[],
        profile=None,
        registry=None,
        include_repos=[],
        exclude_repos=[],
        include_projects=[],
        exclude_projects=[],
        narrow_repos=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_profile_create_registry_writes_and_round_trips(profiles_dir):
    cmd_profile.cmd_profile_create(_create_args(registry="registry.labs.example"))
    data = yaml.safe_load((profiles_dir / "labs.yaml").read_text())
    assert data["registry"] == "registry.labs.example"
    # scalar loader exposes it (no change needed there)
    assert cmd_profile._load_profile("labs")["registry"] == "registry.labs.example"

    # `-P labs profile create labs` without --registry keeps the value
    cmd_profile.cmd_profile_create(_create_args(profile="labs"))
    data2 = yaml.safe_load((profiles_dir / "labs.yaml").read_text())
    assert data2["registry"] == "registry.labs.example"

    # an explicit --registry replaces it
    cmd_profile.cmd_profile_create(_create_args(profile="labs", registry="other.host"))
    data3 = yaml.safe_load((profiles_dir / "labs.yaml").read_text())
    assert data3["registry"] == "other.host"


def test_profile_create_without_registry_omits_the_key(profiles_dir):
    cmd_profile.cmd_profile_create(_create_args(name="boo"))
    data = yaml.safe_load((profiles_dir / "boo.yaml").read_text())
    assert "registry" not in data


# --- precedence in main() --------------------------------------------------------


def _run_main(monkeypatch, argv: list[str]) -> list[str]:
    """Run ``cli.main()`` with a stub parser and return the final env_overrides.

    The stub mirrors the global flags main() touches and uses the local-only
    ``project`` command so no OBS connection is attempted.
    """
    captured: dict[str, list[str]] = {}

    def fake_build_parser() -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(prog="percona-obs")
        p.add_argument("-A", "--apiurl")
        p.add_argument("-R", "--rootprj")
        p.add_argument("-P", "--profile")
        p.add_argument("-e", "--env", action="append", default=[], dest="env_overrides")
        p.add_argument("--verbose", action="store_true", default=False)
        p.add_argument("command")
        p.set_defaults(
            func=lambda a: captured.__setitem__("env", list(a.env_overrides))
        )
        return p

    monkeypatch.setattr(cli, "build_parser", fake_build_parser)
    monkeypatch.setattr(cli.sys, "argv", ["percona-obs", *argv])
    cli.main()
    return captured["env"]


def test_registry_precedence(profiles_dir, monkeypatch):
    (profiles_dir / "p.yaml").write_text(
        "apiurl: http://a\nrootprj: R\nregistry: reg.profile\n"
    )
    # profile key beats the default
    env = parse_env_overrides(_run_main(monkeypatch, ["-P", "p", "project"]))
    assert env["OBS_CONTAINER_REGISTRY"] == "reg.profile"

    # an explicit -e beats the profile key
    env = parse_env_overrides(
        _run_main(
            monkeypatch,
            ["-P", "p", "-e", "OBS_CONTAINER_REGISTRY:reg.cli", "project"],
        )
    )
    assert env["OBS_CONTAINER_REGISTRY"] == "reg.cli"

    # the profile `env:` section also beats the `registry:` key
    (profiles_dir / "q.yaml").write_text(
        "apiurl: http://a\nrootprj: R\nregistry: reg.profile\n"
        "env:\n  - name: OBS_CONTAINER_REGISTRY\n    value: reg.env\n"
    )
    env = parse_env_overrides(_run_main(monkeypatch, ["-P", "q", "project"]))
    assert env["OBS_CONTAINER_REGISTRY"] == "reg.env"


def test_registry_default_without_profile(monkeypatch, profiles_dir):
    env = parse_env_overrides(_run_main(monkeypatch, ["-R", "R", "project"]))
    assert env["OBS_CONTAINER_REGISTRY"] == DEFAULT_CONTAINER_REGISTRY


def test_profile_command_is_not_polluted(profiles_dir, monkeypatch):
    # `profile create` must not bake the derived value into the new profile's
    # env section (it would shadow the profile's own `registry:` key).
    (profiles_dir / "p.yaml").write_text(
        "apiurl: http://a\nrootprj: R\nregistry: reg.profile\n"
    )
    env = _run_main(monkeypatch, ["-P", "p", "profile"])
    assert not any(e.startswith("OBS_CONTAINER_REGISTRY:") for e in env)


# --- rendering a qa block --------------------------------------------------------


def test_qa_block_renders_registry(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "ppg" / "staging" / "containers").mkdir(parents=True)
    (root / "macros.yaml").write_text("- M: 1\n")
    (root / "ppg" / "staging" / "containers" / "project.yaml").write_text(
        "title: C\n"
        "qa:\n"
        "  pipeline: ppg-container\n"
        "  parameters:\n"
        "    REPOSITORY: ${OBS_CONTAINER_REGISTRY}/${OBS_CONTAINER_REGISTRY_ROOTPRJ}/ppg\n"
        "    PLATFORM: [ubi9]\n"
        "  matrix: [PLATFORM]\n"
    )
    monkeypatch.setattr(common, "REPO_ROOT", root)

    args = SimpleNamespace(
        rootprj="isv:percona",
        env_overrides=[registry_env_override("registry.labs.example")],
    )
    env_vars = cmd_qa._qa_env_vars(args)
    assert env_vars["OBS_CONTAINER_REGISTRY"] == "registry.labs.example"
    entries = cmd_qa._load_qa_block("ppg:staging:containers", env_vars)
    assert entries is not None
    assert entries[0]["parameters"]["REPOSITORY"] == (
        "registry.labs.example/isv/percona/ppg"
    )

    # and the default when no profile declares one
    env_vars = cmd_qa._qa_env_vars(
        SimpleNamespace(
            rootprj="isv:percona", env_overrides=[registry_env_override(None)]
        )
    )
    entries = cmd_qa._load_qa_block("ppg:staging:containers", env_vars)
    assert entries is not None
    assert entries[0]["parameters"]["REPOSITORY"] == (
        f"{DEFAULT_CONTAINER_REGISTRY}/isv/percona/ppg"
    )


def test_tree_has_no_hardcoded_registry_in_rootprj_urls():
    """The non-release tree renders the host from ${OBS_CONTAINER_REGISTRY}."""
    repo_root = Path(__file__).resolve().parent.parent / "root"
    offenders = [
        str(p.relative_to(repo_root))
        for p in repo_root.rglob("project.yaml")
        if "releases" not in p.parts
        and "registry.opensuse.org/${OBS_CONTAINER_REGISTRY_ROOTPRJ}"
        in p.read_text(encoding="utf-8")
    ]
    assert offenders == []
