"""Tests for .github/scripts/package_installable.py (no containers: the
container output is the real output captured on 2026-11-21)."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "package_installable.py"
spec = importlib.util.spec_from_file_location("package_installable", SCRIPT)
pi = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pi
spec.loader.exec_module(pi)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def no_network_no_docker(monkeypatch):
    """Tests never reach OBS or Docker: every OBS repository is published and
    every image pulls. Tests that need otherwise override these."""
    monkeypatch.setattr(pi, "obs_repo_state", lambda repo, url, attempts=3: "published")
    monkeypatch.setattr(
        pi, "pull_images", lambda docker, images, attempts=3: {i: "" for i in images}
    )


EL9_WITH_EPEL = """Error: Repoclosure ended with unresolved dependencies (2) across 2 packages.
package: percona-patroni-consul-1:4.1.5-5.8.el9.x86_64 from obs
  unresolved deps (1):
    consul
package: percona-pgaudit17-llvmjit-1:17.2-2.2.el9.x86_64 from obs
  unresolved deps (1):
    percona-pgaudit17(x86-64) = 17.2-2.2.el9
RESULT ok checked=144
"""

EL9_BASE_ONLY = EL9_WITH_EPEL.replace(
    "RESULT ok checked=144",
    """package: percona-pgbackrest-1:2.60.1-2.2.el9.x86_64 from obs
  unresolved deps (1):
    libssh2
RESULT ok checked=144""",
)

DEB12 = """package: percona-example
     percona-example : Depends: python3-cdiff but it is not installable
    E: Unable to correct problems, you have held broken packages.
RESULT ok checked=95
"""


def test_repoclosure_output_is_parsed():
    status, checked, fails = pi.parse_output(EL9_WITH_EPEL)
    assert (status, checked) == ("ok", 144)
    assert fails == {
        "percona-patroni-consul": ["consul"],
        "percona-pgaudit17-llvmjit": ["percona-pgaudit17(x86-64) = 17.2-2.2.el9"],
    }


def test_apt_output_is_parsed():
    status, checked, fails = pi.parse_output(DEB12)
    assert (status, checked) == ("ok", 95)
    assert fails["percona-example"][0].startswith(
        "percona-example : Depends: python3-cdiff"
    )


def test_package_names_drop_the_version():
    assert (
        pi.package_name("percona-pgaudit17-llvmjit-1:17.2-2.2.el9.x86_64")
        == "percona-pgaudit17-llvmjit"
    )
    assert pi.package_name("python3.12-ydiff-1.4.2-1.el9.noarch") == "python3.12-ydiff"
    assert pi.package_name("percona-pg-tde17") == "percona-pg-tde17"


def test_el_needs_epel_is_information_and_failures_with_epel_are_failures(monkeypatch):
    outputs = {"1": EL9_WITH_EPEL, "0": EL9_BASE_ONLY}
    monkeypatch.setattr(
        pi,
        "run_container",
        lambda docker, image, script, env, timeout=3600: outputs[str(env["WITH_EPEL"])],
    )
    r = pi.check_repo("RockyLinux_9", "http://x/RockyLinux_9", "rocky:9", "docker")
    assert sorted(r["failures"]) == [
        "percona-patroni-consul",
        "percona-pgaudit17-llvmjit",
    ]
    assert r["needs_epel"] == {"percona-pgbackrest": ["libssh2"]}


def test_report_allowlist_and_unpublished_and_broken():
    results = {
        "RockyLinux_9": {
            "status": "ok",
            "checked": 144,
            "needs_epel": {"percona-pgbackrest": ["libssh2"]},
            "failures": {
                "percona-patroni-consul": ["consul"],
                "percona-pgaudit17-llvmjit": [
                    "percona-pgaudit17(x86-64) = 17.2-2.2.el9"
                ],
            },
        },
        "Debian_12": {
            "status": "not-published",
            "checked": 0,
            "failures": {},
            "needs_epel": {},
        },
        "Ubuntu_26.04": {
            "status": "container-failed",
            "checked": 0,
            "failures": {},
            "needs_epel": {},
        },
    }
    md, new, broken = pi.report_markdown(
        "isv:percona:ppg:staging:17",
        "17",
        results,
        [{"package": "percona-patroni-consul", "reason": "test"}],
    )
    assert list(new) == ["percona-pgaudit17-llvmjit"] and broken == {
        "Ubuntu_26.04": "container-failed"
    }
    assert "**1 package(s) cannot be installed**, 1 allowlisted" in md
    assert "Not published: Debian_12" in md and "Could not check" in md
    assert "| percona-pgbackrest | RockyLinux_9 | libssh2 |" in md


def test_main_fails_strict_and_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pi,
        "run_container",
        lambda docker, image, script, env, timeout=3600: (
            EL9_WITH_EPEL if "WITH_EPEL" in env else DEB12
        ),
    )
    out = tmp_path / "r.json"
    rc = pi.main(
        [
            "--project",
            "isv:percona:ppg:staging:17",
            "--repos",
            "RockyLinux_9,Debian_12",
            "--config",
            str(ROOT / ".github/package-deps-qa.yaml"),
            "--json",
            str(out),
            "--strict",
        ]
    )
    assert rc == 1
    data = json.loads(out.read_text())
    assert (
        set(data) == {"RockyLinux_9", "Debian_12"}
        and "percona-example" in data["Debian_12"]["failures"]
    )


def test_every_configured_repository_has_an_image():
    import yaml

    cfg = yaml.safe_load((ROOT / ".github/package-deps-qa.yaml").read_text())
    images = dict(pi.DEFAULT_IMAGES, **cfg["installable"]["images"])
    assert all(r in images for r in cfg["repos"]["rpm"] + cfg["repos"]["deb"])


def test_a_run_that_checks_nothing_fails_even_in_report_only_mode(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        pi,
        "run_container",
        lambda docker, image, script, env, timeout=3600: "RESULT not-published checked=0",
    )
    summary = tmp_path / "s.md"
    rc = pi.main(
        [
            "--project",
            "isv:percona:ppg:staging:17",
            "--repos",
            "RockyLinux_9,Debian_12",
            "--config",
            str(ROOT / ".github/package-deps-qa.yaml"),
            "--summary",
            str(summary),
        ]
    )
    assert rc == 2
    assert "**Nothing was checked**" in summary.read_text()


def test_unpublished_repositories_are_skipped_and_unreachable_ones_fail(
    tmp_path, monkeypatch
):
    states = {
        "RockyLinux_9": "published",
        "Debian_12": "not-published",
        "Ubuntu_24.04": "obs-unreachable",
    }
    monkeypatch.setattr(
        pi, "obs_repo_state", lambda repo, url, attempts=3: states[repo]
    )
    ran = []
    monkeypatch.setattr(
        pi,
        "run_container",
        lambda docker, image, script, env, timeout=3600: ran.append(image)
        or "RESULT ok checked=10",
    )
    summary = tmp_path / "s.md"
    rc = pi.main(
        [
            "--project",
            "isv:percona:ppg:staging:17",
            "--repos",
            ",".join(states),
            "--config",
            str(ROOT / ".github/package-deps-qa.yaml"),
            "--summary",
            str(summary),
            "--strict",
        ]
    )
    md = summary.read_text()
    assert rc == 1  # the unreachable repository fails with --strict
    assert (
        ran == ["docker.io/rockylinux/rockylinux:9"] * 2
    )  # no container for the other two
    assert "Not published: Debian_12" in md and "Ubuntu_24.04 (obs-unreachable)" in md


def test_a_mirror_failure_inside_the_container_is_a_failure_not_unpublished():
    out = "    Error: Failed to download metadata for repo 'epel'\nRESULT repo-unreachable checked=0"
    md, new, broken = pi.report_markdown(
        "p",
        "17",
        {
            "RockyLinux_9": dict(
                zip(
                    ("status", "checked", "failures", "needs_epel"),
                    (pi.parse_output(out)[0], 0, {}, {}),
                )
            )
        },
        [],
    )
    assert broken == {"RockyLinux_9": "repo-unreachable"} and "Not published" not in md


def test_each_image_is_pulled_once_and_a_failed_pull_is_reported(tmp_path, monkeypatch):
    pulls = []
    monkeypatch.setattr(
        pi,
        "pull_images",
        lambda docker, images, attempts=3: pulls.append(sorted(set(images)))
        or {
            i: ("toomanyrequests: rate limit" if "debian" in i else "") for i in images
        },
    )
    monkeypatch.setattr(
        pi,
        "run_container",
        lambda docker, image, script, env, timeout=3600: "RESULT ok checked=5",
    )
    summary = tmp_path / "s.md"
    pi.main(
        [
            "--project",
            "isv:percona:ppg:staging:17",
            "--repos",
            "RockyLinux_9,Debian_12",
            "--config",
            str(ROOT / ".github/package-deps-qa.yaml"),
            "--summary",
            str(summary),
        ]
    )
    assert pulls == [
        ["docker.io/library/debian:12", "docker.io/rockylinux/rockylinux:9"]
    ]
    assert (
        "Debian_12 (image-pull-failed: toomanyrequests: rate limit)"
        in summary.read_text()
    )


def test_allowlist_entry_without_package_is_refused():
    with pytest.raises(SystemExit, match="has no package"):
        pi.check_allowlist(
            [{"reason": "typo: packages instead of package", "packages": "x"}],
            "cfg.yaml",
        )


def test_reason_for_could_not_check_comes_from_the_container(monkeypatch):
    out = (
        "REASON Error: Failed to download metadata for repo 'epel': Cannot download repomd.xml\n"
        "RESULT repo-unreachable checked=0"
    )
    monkeypatch.setattr(
        pi, "run_container", lambda docker, image, script, env, timeout=3600: out
    )
    r = pi.check_repo("RockyLinux_9", "http://x/RockyLinux_9", "rocky:9", "docker")
    assert (
        r["status"] == "repo-unreachable"
        and "Failed to download metadata for repo 'epel'" in r["why"]
    )
    md, new, broken = pi.report_markdown("p", "17", {"RockyLinux_9": r}, [])
    assert "RockyLinux_9 (repo-unreachable: Error: Failed to download metadata" in md


def test_container_scripts_guard_epel_and_the_second_apt_update():
    assert (
        "could not install epel-release" in pi.EL_SCRIPT
        and "could not enable CRB/PowerTools" in pi.EL_SCRIPT
    )
    assert (
        'grep -qF "$URL"' in pi.DEB_SCRIPT
        and "RESULT repo-unreachable" in pi.DEB_SCRIPT
    )
