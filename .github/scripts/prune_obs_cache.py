#!/usr/bin/env python3
"""Prune stale percona-obs service-cache entries under .cache/.

Deletes content-addressed cache entries not used (restored or stored) by any
sync run in the last PRUNE_MAX_AGE_DAYS days (default 7), so the tree
persisted by actions/cache stops growing monotonically.  Run after the sync
step; the actions/cache post-step then saves the pruned tree.
"""

import os

from percona_obs.services import prune_cache

days = int(os.environ.get("PRUNE_MAX_AGE_DAYS", "7"))
deleted = prune_cache(days)
print(f"pruned {deleted} cache entrie(s) older than {days} day(s)")
