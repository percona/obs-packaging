"""Unit tests for percona_obs.cdn_wait (OBS and HTTP monkeypatched)."""

import argparse

import pytest

import percona_obs.cdn_wait as cw


def test_url_spellings_plus_checked_raw_and_encoded():
    assert cw.url_spellings("h", "a:b/R/all/x_1+2_all.deb") == [
        "https://h/repositories/a:/b/R/all/x_1+2_all.deb",
        "https://h/repositories/a:/b/R/all/x_1%2B2_all.deb",
    ]
    assert cw.url_spellings("h", "a/R/noarch/x-1.noarch.rpm") == [
        "https://h/repositories/a/R/noarch/x-1.noarch.rpm"
    ]


def test_arch_independent_files(monkeypatch):
    tree = {
        ("P",): ["Debian_12", "RockyLinux_9"],
        ("P", "Debian_12"): ["Packages", "all", "amd64"],
        ("P", "Debian_12", "all"): ["a_all.deb", "Packages"],
        ("P", "RockyLinux_9"): ["noarch", "x86_64", "repodata"],
        ("P", "RockyLinux_9", "noarch"): ["b.noarch.rpm"],
    }
    monkeypatch.setattr(
        cw, "_published_entries", lambda apiurl, *path: tree.get(path, [])
    )
    assert cw.arch_independent_files("http://obs", "P") == [
        "P/Debian_12/all/a_all.deb",
        "P/RockyLinux_9/noarch/b.noarch.rpm",
    ]


def test_stale_files_compares_each_spelling(monkeypatch):
    heads = {
        "https://o/repositories/P/R/all/x_1+2_all.deb": ("new", "10"),
        "https://o/repositories/P/R/all/x_1%2B2_all.deb": ("new", "10"),
        "https://c/repositories/P/R/all/x_1+2_all.deb": ("old", "12"),
        "https://c/repositories/P/R/all/x_1%2B2_all.deb": ("new", "10"),
        "https://o/repositories/P/R/all/y_all.deb": ("", ""),
        "https://c/repositories/P/R/all/y_all.deb": ("", ""),
    }
    monkeypatch.setattr(cw, "_head", lambda url: heads[url])
    assert cw.stale_files(["P/R/all/x_1+2_all.deb", "P/R/all/y_all.deb"], "o", "c") == [
        "https://c/repositories/P/R/all/x_1+2_all.deb",
        "https://c/repositories/P/R/all/y_all.deb",
    ]


def _args(**kw):
    base = dict(
        projects=["ppg:releases:18"],
        rootprj="PR",
        apiurl="http://obs",
        origin="o",
        cdn="c",
        timeout=0,
        interval=0,
    )
    return argparse.Namespace(**{**base, **kw})


def test_cmd_fails_listing_stale_after_timeout(monkeypatch, capsys):
    monkeypatch.setattr(cw, "_fetch_obs_subproject_names", lambda a, p: {p + ":sub"})
    seen = []
    monkeypatch.setattr(
        cw,
        "arch_independent_files",
        lambda apiurl, prj: seen.append(prj) or [f"{prj}/R/all/f.deb"],
    )
    monkeypatch.setattr(cw, "stale_files", lambda paths, o, c: paths[:1])
    with pytest.raises(SystemExit):
        cw.cmd_qa_wait_cdn(_args())
    assert seen == ["PR:ppg:releases:18", "PR:ppg:releases:18:sub"]
    assert "PR:ppg:releases:18/R/all/f.deb" in capsys.readouterr().err


def test_cmd_retries_until_clean(monkeypatch):
    monkeypatch.setattr(cw, "_fetch_obs_subproject_names", lambda a, p: set())
    monkeypatch.setattr(cw, "arch_independent_files", lambda a, p: ["x"])
    rounds = iter([["x"], []])
    monkeypatch.setattr(cw, "stale_files", lambda paths, o, c: next(rounds))
    monkeypatch.setattr(cw.time, "sleep", lambda s: None)
    cw.cmd_qa_wait_cdn(_args(timeout=60))
