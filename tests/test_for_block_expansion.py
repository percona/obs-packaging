"""Unit tests for ``expand_for_blocks`` (percona_obs.common).

Dockerfiles synced to OBS need every package name in a ``RUN <pkgmgr> install``
line to be a literal token: OBS statically scans those lines to pre-resolve
build dependencies, and cannot expand a real shell loop variable (see the
percona-distribution-postgresql-upgrade Dockerfile, which needs a near-
identical install block repeated once per older PG major version). This
``{{FOR var IN v1,v2,...}} ... {{ENDFOR}}`` block lets that block be authored
once and expanded into fully literal, repeated text before the file is synced,
so OBS only ever sees plain text with no loop construct in it.
"""

from percona_obs.common import expand_for_blocks


def test_no_for_block_is_unchanged():
    text = "FROM foo\nRUN microdnf install -y bar\n"
    assert expand_for_blocks(text) == text


def test_single_substitution_repeated_per_value():
    text = "{{FOR v IN 17,16,14}}\nRUN install pkg${v}\n{{ENDFOR}}\n"
    assert expand_for_blocks(text) == (
        "RUN install pkg17\nRUN install pkg16\nRUN install pkg14\n"
    )


def test_multiple_occurrences_of_var_in_one_block():
    text = "{{FOR v IN 17,16}}\nRUN a${v} && b${v}\n{{ENDFOR}}\n"
    assert expand_for_blocks(text) == "RUN a17 && b17\nRUN a16 && b16\n"


def test_text_outside_block_is_preserved():
    text = "before\n{{FOR v IN 1,2}}\nline${v}\n{{ENDFOR}}\nafter\n"
    assert expand_for_blocks(text) == "before\nline1\nline2\nafter\n"


def test_multiple_blocks_in_one_file():
    text = "{{FOR v IN 1,2}}\nA${v}\n{{ENDFOR}}\n{{FOR v IN 9,8}}\nB${v}\n{{ENDFOR}}\n"
    assert expand_for_blocks(text) == "A1\nA2\nB9\nB8\n"


def test_values_may_have_surrounding_whitespace():
    text = "{{FOR v IN 17, 16 , 14}}\npkg${v}\n{{ENDFOR}}\n"
    assert expand_for_blocks(text) == "pkg17\npkg16\npkg14\n"
