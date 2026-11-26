# RockyLinux_N vs UBI_N equivalence report for ppg:staging:18

Generated 2026-11-24 from repository metadata only (`repodata/repomd.xml` and the
`primary` file it references; no RPM downloaded).

- Rocky side: `https://download.opensuse.org/repositories/isv:/percona:/ppg:/staging:/18/RockyLinux_N/`
- UBI side: `https://download.obs.pg.labs.percona.com/isv:/percona:/ppg:/staging:/18/UBI_N/`

Method: x86_64 and noarch binary packages only (`src` ignored); `-debuginfo` and
`-debugsource` packages skipped; packages keyed by name; for versioned
Requires/Provides entries the release part of the version-release is dropped
(epoch kept) before taking set differences; `rpmlib(...)` requires ignored. No
package name had several versions on either side, so no "newest wins" choice was
needed.

Classification: **expected** = UBI-only rebuild of a RHEL library that UBI lacks
(icu, libproxy, libusbx, qhull, qt5-qtbase, snappy on UBI_9) or UBI-only product,
or Rocky-only because the distro ships it on UBI 10 (python3-dns on N=10).
**unexplained** = anything else; no explanation is invented.

## RockyLinux_8 vs UBI_8

Skipped debug packages: 46 Rocky, 45 UBI.

| Packages | Count |
|---|---|
| Rocky (after skips) | 105 |
| UBI (after skips) | 103 |
| In both | 103 |
| Only Rocky | 2 |
| Only UBI | 0 |
| In both with Requires diff | 8 |
| In both with Provides diff | 1 |

Only Rocky (both unexplained):
- `percona-pg_stat_monitor18-llvmjit`
- `percona-pgpool-II-pg18-pcp`

Requires/Provides differences (all unexplained). Package releases differ between
the sides (Rocky is a newer build, e.g. `1.1.0-7.2.el8` vs `1.1.0-5.12.el8`), so
part of this may be build skew, but the metadata does differ:

| Package | Only in Rocky | Only in UBI |
|---|---|---|
| percona-pg_oidc_validator18 | Req: `percona-postgresql18-libs >= 18.7`, `percona-postgresql18-server` | |
| percona-pg_repack18 | Req: `percona-postgresql18`, `percona-postgresql18-libs >= 18.7` | Req: `postgresql18` |
| percona-pg_stat_monitor18 | Req: `percona-postgresql18-libs(x86-64) >= 18.7`, `percona-postgresql18-server` | Req: `percona-postgresql18` |
| percona-pg_tde18 | Req: `percona-postgresql18-libs`, `percona-postgresql18-server` | |
| percona-pgpool-II-pg18 | Req: `percona-postgresql18-libs >= 18.7`, `percona-postgresql18-server`; Prov: `group(postgres)`, `user(postgres)` | Prov: `libpgpoolpcp.so.3()(64bit)` |
| percona-pgpool-II-pg18-devel | | Req: `libpgpoolpcp.so.3()(64bit)` |
| percona-postgis35_18 | Req: `percona-postgresql18-libs >= 18.7` | |
| percona-postgresql18-contrib | Req: `percona-postgresql18-server >= 18.7.1` | |

## RockyLinux_9 vs UBI_9

Skipped debug packages: 46 Rocky, 46 UBI.

| Packages | Count |
|---|---|
| Rocky (after skips) | 105 |
| UBI (after skips) | 137 |
| In both | 105 |
| Only Rocky | 0 |
| Only UBI | 32 |
| In both with Requires diff | 1 |
| In both with Provides diff | 0 |

Only UBI (all 32 expected: RHEL library rebuilds UBI_9 lacks):
- icu: `icu`, `libicu`, `libicu-devel`, `libicu-doc`
- libproxy: `libproxy`, `libproxy-bin`, `libproxy-devel`, `libproxy-gnome`, `libproxy-webkitgtk4`, `python3-libproxy`
- libusbx: `libusbx`, `libusbx-devel`, `libusbx-devel-doc`, `libusbx-tests-examples`
- qhull: `qhull`, `qhull-devel`, `libqhull`, `libqhull_p`, `libqhull_r`
- qt5-qtbase: `qt5-qtbase`, `qt5-qtbase-common`, `qt5-qtbase-devel`, `qt5-qtbase-examples`, `qt5-qtbase-gui`, `qt5-qtbase-mysql`, `qt5-qtbase-odbc`, `qt5-qtbase-postgresql`, `qt5-qtbase-private-devel`, `qt5-qtbase-static`, `qt5-qtbase-tests`
- snappy: `snappy`, `snappy-devel`

Requires/Provides differences (unexplained):

| Package | Only in Rocky | Only in UBI |
|---|---|---|
| SFCGAL (same `2.3.0-3.3.el9` on both) | Req: `libboost_serialization.so.1.78.0()(64bit)` | Req: `libboost_serialization.so.1.75.0()(64bit)` |

## RockyLinux_10 vs UBI_10

Skipped debug packages: 46 Rocky, 46 UBI.

| Packages | Count |
|---|---|
| Rocky (after skips) | 104 |
| UBI (after skips) | 103 |
| In both | 103 |
| Only Rocky | 1 |
| Only UBI | 0 |
| In both with Requires diff | 0 |
| In both with Provides diff | 7 |

Only Rocky (expected: distro ships it on UBI 10): `python3.12-dns`.

Provides differences (unexplained). In seven packages the same Provides entries
differ only by epoch: the UBI build declares `EQ 1:<ver>` where Rocky declares
`EQ <ver>` (no epoch). Releases also differ (Rocky `-4.4.el10`, UBI `-1.3.el10`).
Packages: `python3.12-attrs`, `python3.12-dateutil`, `python3.12-jmespath`,
`python3.12-prettytable`, `python3.12-psutil`, `python3.12-six`,
`python3.12-wcwidth`. Each has the Provides `python-X`, `python3-X`, `python3.12-X`
(psutil also `python3.12-psutil(x86-64)`) at `EQ <ver>` on Rocky and `EQ 1:<ver>`
on UBI. Example: `python3.12-attrs` Rocky `python3-attrs = 22.1.0`, UBI
`python3-attrs = 1:22.1.0`. Requires are identical in all seven.

## Unexplained differences

| N | Only-Rocky packages | Only-UBI packages | Packages with Requires or Provides diff | Total |
|---|---|---|---|---|
| 8 | 2 | 0 | 8 | 10 |
| 9 | 0 | 0 | 1 | 1 |
| 10 | 0 | 0 | 7 | 7 |

Expected differences: 32 UBI-only packages on N=9, 1 Rocky-only package on N=10.

**Unexplained difference count: 18 packages (10 on N=8, 1 on N=9, 7 on N=10).**
