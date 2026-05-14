%global pgmajor %!{PG_MAJOR_VERSION}
%global pgminorversion %!{PG_MINOR_VERSION}

Summary:        Percona base selection of PostgreSQL %{pgmajor} components
Name:           percona-ppg-server%{pgmajor}
Version:        %{pgmajor}.%{pgminorversion}
Release:        1%{?dist}
License:        PostgreSQL
Group:          Applications/Databases
URL:            https://www.percona.com/software/postgresql-distribution
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC
Epoch:          1

Requires:       percona-postgresql%{pgmajor}-server
Requires:       percona-postgresql-common >= %{pgmajor}.%{pgminorversion}
Requires:       percona-postgresql%{pgmajor}-contrib
Requires:       percona-pg-stat-monitor%{pgmajor}
Requires:       percona-pgaudit%{pgmajor} >= %{pgmajor}.%{pgminorversion}
Requires:       percona-pg_repack%{pgmajor}
Requires:       percona-wal2json%{pgmajor}

BuildArch:      noarch

%description
Essential / key PostgreSQL %{pgmajor} components.
Percona Distribution for PostgreSQL features core components, tools and add-ons
from the community, tested to work together in demanding enterprise environments.

%files

%changelog
* Thu Apr 23 2026 Percona Development Team <info@percona.com> - 17.9-1
- Initial build for Percona Distribution for PostgreSQL 17
