"""Unit tests for project release mirror regeneration (percona_obs.cmd_project)."""

import argparse
from pathlib import Path

import pytest
import yaml

import percona_obs.cmd_project as cmd_project
from percona_obs.cmd_project import _rewrite_subproject_paths, _write_release_tree


def _staging_tree(tmp_path: Path) -> Path:
    src = tmp_path / "root/ppg/staging/17"
    (src).mkdir(parents=True)
    (src / "project.yaml").write_text("repositories: []\n")
    (src / "containers").mkdir()
    (src / "containers" / "project.yaml").write_text(
        yaml.dump(
            {
                "repositories": [
                    {
                        "name": "ubi9",
                        "paths": [
                            {"subproject": "ppg:staging:17", "repository": "UBI_9"},
                            {
                                "subproject": "common:containers:ubi9",
                                "repository": "images",
                            },
                        ],
                        "archs": ["x86_64"],
                    },
                ]
            }
        )
    )
    (src / "tarballs").mkdir()
    (src / "tarballs" / "project.yaml").write_text(
        yaml.dump(
            {
                "publish": {"RockyLinux_9": False},
                "repositories": [
                    {
                        "name": "ssl3",
                        "paths": [
                            {
                                "subproject": "ppg:staging:17:tarballs",
                                "repository": "RockyLinux_9",
                            },
                        ],
                        "archs": ["x86_64"],
                    },
                ],
            }
        )
    )
    return src


def test_rewrite_keeps_self_references():
    repos = [
        {
            "name": "ssl3",
            "paths": [
                {
                    "subproject": "ppg:staging:17:tarballs",
                    "repository": "RockyLinux_9",
                }
            ],
            "archs": ["x86_64"],
        }
    ]
    out = _rewrite_subproject_paths(repos, "ppg:staging:17", "ppg:releases:17")
    assert out[0]["paths"] == [
        {"subproject": "ppg:releases:17:tarballs", "repository": "RockyLinux_9"}
    ]


def test_write_release_tree_creates_all_mirrors_and_deletes_stale(
    tmp_path, monkeypatch
):
    src = _staging_tree(tmp_path)
    monkeypatch.setattr(cmd_project, "_REPO_DIR", tmp_path)
    rel = tmp_path / "root/ppg/releases/17"
    # simulate the pre-restructure leftover
    (rel / "containers" / "ubi9").mkdir(parents=True)
    (rel / "containers" / "ubi9" / "project.yaml").write_text("build: false\n")

    written = _write_release_tree(
        rel,
        {"build": False, "repositories": []},
        src,
        "ppg:staging:17",
        "ppg:releases:17",
        "ppg",
        "17",
    )
    assert (rel / "project.yaml").is_file()
    assert (rel / "containers" / "project.yaml").is_file()
    assert (rel / "tarballs" / "project.yaml").is_file()
    assert not (rel / "containers" / "ubi9").exists()  # stale dir deleted
    tarballs = yaml.safe_load((rel / "tarballs" / "project.yaml").read_text())
    assert tarballs["build"] is False
    assert tarballs["publish"] == {"RockyLinux_9": False}  # publish carried over
    assert (
        tarballs["repositories"][0]["paths"][0]["subproject"]
        == "ppg:releases:17:tarballs"
    )
    assert len(written) == 3


def test_tier_validation_rejects_devel(monkeypatch):
    args = argparse.Namespace(
        project="ppg:devel:18",
        rootprj="home:Admin",
        apiurl=None,
        release_name=None,
        release_id=None,
    )

    monkeypatch.setattr(cmd_project, "resolve_project_path", lambda pid: Path("/nope"))
    with pytest.raises(SystemExit, match="staging-tier"):
        cmd_project.cmd_project_release(args)
