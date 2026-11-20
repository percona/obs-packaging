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


# --- scope_poll_projects ------------------------------------------------------

from percona_obs.common import scope_poll_projects  # noqa: E402

PR = "root:PR:pr-9"
STAGING, DEVEL_TOOLS = f"{PR}:ppg:staging:19", f"{PR}:ppg:devel:common:tools"
KNOWN = {PR, f"{PR}:ppg:staging", STAGING, f"{PR}:ppg:devel:common", DEVEL_TOOLS}


def test_scope_without_a_report_is_the_whole_tree():
    discovered = {STAGING, DEVEL_TOOLS}
    assert scope_poll_projects(discovered, KNOWN, None, None) == (
        discovered,
        discovered,
        set(),
    )


def test_scope_report_naming_the_package_less_root_is_trusted():
    # The first sync of a PR creates its root project and reports it; the root
    # holds no packages, which used to read as naming drift and drop the report.
    discovered = {STAGING, DEVEL_TOOLS}
    all_projects, monitored, stray = scope_poll_projects(
        discovered, KNOWN, {PR, DEVEL_TOOLS}, None
    )
    assert stray == set()
    assert monitored == {DEVEL_TOOLS}
    assert all_projects == discovered


def test_scope_report_naming_an_undeclared_project_falls_back_to_the_tree():
    discovered = {STAGING, DEVEL_TOOLS}
    _all, monitored, stray = scope_poll_projects(
        discovered, KNOWN, {f"{PR}:ppg:renamed"}, None
    )
    assert stray == {f"{PR}:ppg:renamed"}
    assert monitored == discovered


def test_scope_drops_projects_the_pr_did_not_create():
    # Report dropped, and only the devel project exists on OBS: the staging
    # project must not be polled, or the poll waits for results that never come.
    all_projects, monitored, _stray = scope_poll_projects(
        {STAGING, DEVEL_TOOLS}, KNOWN, None, {PR, DEVEL_TOOLS}
    )
    assert all_projects == monitored == {DEVEL_TOOLS}


def test_scope_is_empty_when_the_pr_created_nothing_to_poll():
    all_projects, monitored, _stray = scope_poll_projects({STAGING}, KNOWN, None, {PR})
    assert all_projects == monitored == set()
