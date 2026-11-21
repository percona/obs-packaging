# Package dependency QA

Every night, before the Jenkins tests even matter, we ask three simple
questions about the packages in each staging project
(`ppg:staging:14` … `ppg:staging:19`):

1. **Do the RPM and the Debian package ask for the same things?**
2. **Does every extension ask for the PostgreSQL server it belongs to?**
3. **Can every package actually be installed on every OS we ship for?**

A "no" to any of them is almost always a packaging mistake that a customer
would hit on the very first `dnf install` or `apt install`.

## Why we need this

Our Jenkins tests install packages *by name* and then test them. They never
look at what a package *declares* it needs. So these bugs slipped through:

| Bug we found (Nov 2026) | Question that catches it |
|---|---|
| The PG 17 RPM server required pg_tde, the Debian one did not | 1 |
| `percona-pg-tde17` installs on a machine with no PostgreSQL server (both formats) | 2 |
| `percona-pgaudit17-llvmjit` cannot be installed on any EL version (a missing `Epoch` in its Requires) | 3 |
| `percona-patroni-consul` cannot be installed on any EL version (needs `consul`, which no repository has) | 3 |

## How it works

Every package repository publishes an **index**: a list of all its packages
and, for each one, what it needs (RPM: `Requires`/`Recommends`; Debian:
`Depends`/`Recommends`). Checks 1 and 2 only read these indexes. Check 3 also
starts small throw-away containers. Nothing is installed anywhere for real.

### 1. RPM vs Debian parity

The same product is packaged twice: once as RPM (`rpm/*.spec`) and once for
Debian (`debian/control`). When someone changes one file, they can forget the
other.

For each package, we list which *other Percona packages* it depends on, in
the RPM repository and in the Debian repository, and compare the two lists.
Names are compared after removing the differences between the formats
(`percona-pg_tde17` and `percona-pg-tde17` both become `perconapgtde`).

We compare several pairs (Rocky 8/9/10 against Debian 12, and Rocky 9 against
Debian 13 and Ubuntu 22.04/24.04/26.04). The report says where each
difference was seen: in **all** pairs means the two formats differ; in only
one pair means one distribution differs.

### 2. Every extension depends on its server

An extension (pg_tde, pgaudit, PostGIS, pg_stat_monitor, …) is useless
without the server, and must belong to the server of the same major. So every
extension package must depend on:

- RPM: `percona-postgresql<major>-server`
- Debian: `percona-postgresql-<major>` (or `postgresql-<major>`, which it provides)

It may do so indirectly. For example, the PostGIS tiger geocoder depends on
PostGIS, which depends on the server, and that is fine. Depending only on
`libpq` does not count, because the operating system's own libpq also
provides it.

Which packages are "extensions"? Packages whose name contains the major as a
number of its own (`percona-pg_tde17`, `percona-postgresql-17-pgaudit`),
except client tools, documentation, headers, libraries and debug symbols. The
list of exceptions is in the config file.

This check finds bugs that check 1 cannot. When *both* formats forget the
server, they still agree with each other.

### 3. Every package installs

For every OS, we start a clean container of that OS, add our OBS repository,
and ask the package manager: "could you install this package?" We do this for
every package in the repository.

- **Rocky Linux 8/9/10:** `dnf repoclosure`, with EPEL and CRB/PowerTools
  enabled, because our install docs ask for them.
  We also run it once *without* EPEL/CRB. Packages that only fail then are
  listed as information ("needs EPEL/CRB") so that we keep the install docs
  right. They are not failures.
- **Debian 12/13, Ubuntu 22.04/24.04/26.04:** `apt-get install --simulate`
  for every package.

## When it runs

It runs as part of **OBS Nightly QA**, in the job
**`Package deps / ppg:staging:<major>`**. There is one job per major, and it
follows the same schedule as the rest of the nightly (Monday PG 14 …
Saturday PG 19; a manual run with `all` checks every major). It needs no
Jenkins and no OBS login. It takes about 30 minutes per major, mostly for
check 3.

## How to read the result

Open the job and look at its **Summary**. There is one section per check:

- **1.** A table of differences: *package* requires *dependency*, declared in
  one format and missing in the other, and in which repository pairs.
- **2.** A table of extensions that do not depend on the server, and in which
  repositories.
- **3.** A table of packages that cannot be installed, with what is missing.
  Below it is the "needs EPEL/CRB" list, collapsed.

The job is **red** when any check finds something that is not allowlisted.
The raw results (JSON) are attached to the run as the `package-deps-<major>`
artifact.

## What to do when it is red

1. **Is it a real bug?** In most cases yes. File a ticket for the build team,
   and paste the row from the summary. Leave the job red until the fix
   reaches OBS. Red is the reminder.
2. **Is it intended?** For example, Debian packages depend on
   `postgresql-common` and RPM packages do not, by design. Add an entry under
   that check's `allowed:` list in `.github/package-deps-qa.yaml`, **with a
   reason**. Never allowlist a bug just to make the job green.
3. **Could not check / not published?** "Not published" means the project
   does not build for that OS (for example, no Debian 12 for PG 16 tde). That
   is fine. "Could not check" means the container or the download failed.
   Re-run the job.

## Run it yourself

You need Python 3 with `pyyaml`. For check 3 you also need Docker.

```bash
P=isv:percona:ppg:staging:17
python3 .github/scripts/package_dep_parity.py  --project $P     # 1, about a minute
python3 .github/scripts/package_server_dep.py  --project $P     # 2, about a minute
python3 .github/scripts/package_installable.py --project $P     # 3, about 30 minutes
```

Each one prints the same report that the nightly job shows. Add `--strict`
to get exit code 1 on findings, and `--repos RockyLinux_9,Debian_12` (for
check 3) to try fewer OSes.

## Limits

- Only amd64 is checked. arm64 packages usually have the same dependencies,
  but this is not checked.
- Check 1 only compares dependencies on packages from the *same* OBS
  repository. Dependencies on OS packages, such as `python3-cdiff`, are not
  compared. Check 3 still catches them when they cannot be installed.
- UBI repositories (container images) and openSUSE are not checked.

## Files

| File | What it is |
|---|---|
| `.github/package-deps-qa.yaml` | OS lists, exceptions and the allowlists (with reasons) |
| `.github/scripts/package_dep_parity.py` | Check 1 |
| `.github/scripts/package_server_dep.py` | Check 2 |
| `.github/scripts/package_installable.py` | Check 3 |
| `.github/workflows/obs-nightly-qa.yml` | The `package-deps` job |
| `tests/test_package_*.py` | Unit tests, built from the real bugs above |
