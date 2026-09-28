"""When a build poll may stop (percona_obs.common).

Two failure modes the PR-check poll hit on a multi-instance setup:

* an instance that synced nothing still monitored every project the local tree
  declares.  None of them exist there, so no result ever appears, ``total``
  stays 0 and the old ``total > 0`` rule could never be satisfied — the job
  span until its timeout.
* an instance that synced 85 packages was polled 30 s later, when OBS had
  scheduled 8 of them.  None were in flight *yet*, so the old rule declared the
  build terminal and reported a verdict on those 8.
"""

from percona_obs.common import builds_are_terminal, pending_upload_results

PRJ = {"root:ppg:staging:14", "root:ppg:common:deps"}


# --- pending_upload_results ---------------------------------------------------


def test_pending_lists_uploads_without_a_result():
    expected = {"root:ppg:staging:14/pgaudit", "root:ppg:staging:14/pgbouncer"}
    reported = {"root:ppg:staging:14/pgaudit"}
    assert pending_upload_results(expected, reported, PRJ) == {
        "root:ppg:staging:14/pgbouncer"
    }


def test_pending_ignores_uploads_outside_the_monitored_projects():
    # A package promoted into a project this leg does not monitor must not
    # hold the poll open forever.
    expected = {"root:ppg:devel:19/pg_tde"}
    assert pending_upload_results(expected, set(), PRJ) == set()


def test_pending_empty_when_everything_reported():
    expected = {"root:ppg:common:deps/boost"}
    assert (
        pending_upload_results(expected, {"root:ppg:common:deps/boost"}, PRJ) == set()
    )


def test_pending_handles_package_names_containing_no_slash_ambiguity():
    # rsplit keeps colon-separated project names intact.
    expected = {"root:ppg:staging:14/percona-postgresql-common"}
    assert pending_upload_results(expected, set(), PRJ) == expected


# --- builds_are_terminal ------------------------------------------------------


def test_scoped_run_that_uploaded_nothing_is_terminal():
    # The boo case: nothing synced, so no results will ever appear.
    assert builds_are_terminal(total=0, still_building=0, pending=0, scoped=True)


def test_scoped_run_waits_for_unscheduled_uploads():
    # The labs case: 8 results in, none in flight, but 77 not scheduled yet.
    assert not builds_are_terminal(total=8, still_building=0, pending=77, scoped=True)


def test_scoped_run_terminal_once_everything_reported():
    assert builds_are_terminal(total=85, still_building=0, pending=0, scoped=True)


def test_in_flight_builds_are_never_terminal():
    assert not builds_are_terminal(total=85, still_building=3, pending=0, scoped=True)
    assert not builds_are_terminal(total=85, still_building=3, pending=0, scoped=False)


def test_unscoped_empty_result_set_keeps_waiting():
    # Without a report an empty result set is ambiguous (OBS may not have
    # scheduled yet), so the previous fail-open behaviour is preserved.
    assert not builds_are_terminal(total=0, still_building=0, pending=0, scoped=False)


def test_unscoped_terminal_once_results_exist_and_settle():
    assert builds_are_terminal(total=12, still_building=0, pending=0, scoped=False)
