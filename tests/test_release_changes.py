import pytest
from percona_obs.release_changes import (
    CommitRef,
    classify_change,
    commit_line,
    packaging_commits,
    split_versrel,
)


@pytest.mark.parametrize(
    "versrel, expected",
    [
        ("2.60.0-4.2.el9", ("2.60.0", "4")),
        ("3.5.26-6.1", ("3.5.26", "6")),
        ("17.11-1", ("17.11", "1")),
        ("4.2.0-6+7.3.bookworm", ("4.2.0", "7")),
        ("2.9.0.post0-3.1.el8", ("2.9.0.post0", "3")),
        ("8.23.0-lp160.3.1", ("8.23.0", "3")),
        ("1.2-bp160.4.2", ("1.2", "4")),
        ("1.19", ("1.19", None)),
    ],
)
def test_split_versrel(versrel, expected):
    assert split_versrel(versrel) == expected


@pytest.mark.parametrize(
    "old, new, kind",
    [
        ("5.0-5.1.el10", "6.0-1.2.el10", "version"),
        (
            "2.4.1-4.3.el10",
            "2.4.0-3.1.el10",
            "version",
        ),  # downgrade is a version change
        ("17.1-5.6.el10", "17.1-6.2.el10", "packaging"),
        ("2.60.0-4.1.el10", "2.60.0-4.2.el10", "rebuild"),
        ("2.60.0-4.1.el10", "2.60.0-4.1.el10", "rebuild"),
        ("4.2.0-6+7.3.bookworm", "4.2.0-7.5", "rebuild"),
        ("4.2.0-6+7.3.bookworm", "4.2.0-8.1", "packaging"),
        ("1.19", "1.19", "rebuild"),
        ("8.23.0-3.2", "8.23.0-lp160.3.1", "rebuild"),
        ("8.23.0-3.2", "8.23.0-lp160.4.1", "packaging"),
        ("1.19", "1.19-2.1", "packaging"),
    ],
)
def test_classify_change(old, new, kind):
    assert classify_change(old, new) == kind


def test_packaging_commits_parses_git_log():
    seen = []

    def run_git(args):
        seen.append(args)
        return "a" * 40 + "\x00first\x1e\n" + "b" * 40 + "\x00second\x1e\n"

    commits = packaging_commits("P", "N", ["root/x/pkg", "root/_shared/pkg"], run_git)
    assert commits == [CommitRef("a" * 40, "first"), CommitRef("b" * 40, "second")]
    assert seen == [
        [
            "log",
            "--no-merges",
            "--reverse",
            "--format=%H%x00%s%x1e",
            "P..N",
            "--",
            "root/x/pkg",
            "root/_shared/pkg",
        ]
    ]


def test_packaging_commits_empty_output():
    assert packaging_commits("P", "N", ["p"], lambda args: "") == []


def test_commit_line_with_pr():
    c = CommitRef("a" * 40, "PG-2955 percona-pgaudit<N>-llvmjit is not installable")
    line = commit_line(c, "o/r", lambda sha: (310, "https://github.com/o/r/pull/310"))
    assert line == (
        "  - PG-2955 percona-pgaudit\\<N>-llvmjit is not installable "
        "([#310](https://github.com/o/r/pull/310))"
    )


def test_commit_line_without_pr_links_commit():
    c = CommitRef("abcdef1234" + "0" * 30, "direct push")
    assert commit_line(c, "o/r", lambda sha: None) == (
        "  - direct push ([abcdef1](https://github.com/o/r/commit/abcdef1234"
        + "0" * 30
        + "))"
    )


def test_commit_line_lookup_disabled():
    c = CommitRef("a" * 40, "subject")
    assert commit_line(c, "o/r", None) == "  - subject"
    assert commit_line(c, None, lambda sha: (1, "u")) == "  - subject"
