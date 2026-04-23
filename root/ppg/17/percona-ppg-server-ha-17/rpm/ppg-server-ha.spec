%global pgmajor 17
%global pgminorversion 9

Summary:        Percona selection of PostgreSQL %{pgmajor} HA components
Name:           percona-ppg-server-ha%{pgmajor}
Version:        %{pgmajor}.%{pgminorversion}
Release:        1%{?dist}
License:        PostgreSQL
Group:          Applications/Databases
URL:            https://www.percona.com/software/postgresql-distribution
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC

Requires:       etcd
Requires:       python3-etcd
Requires:       percona-patroni
Requires:       percona-haproxy
Requires:       percona-postgresql%{pgmajor}-server

BuildArch:      noarch

%description
Essential / key PostgreSQL %{pgmajor} high availability components.
Percona Distribution for PostgreSQL features core components, tools and add-ons
from the community, tested to work together in demanding enterprise environments.

%files

%changelog
* Thu Apr 23 2026 Percona Development Team <info@percona.com> - 17.9-1
- Initial build for Percona Distribution for PostgreSQL 17 HA bundle
