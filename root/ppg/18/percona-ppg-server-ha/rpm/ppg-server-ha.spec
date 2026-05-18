%global pgmajor %!{PG_MAJOR_VERSION}
%global pgminorversion %!{PG_MINOR_VERSION}

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
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PG_VERSION}-1
- Release of Percona Distribution for PostgreSQL %!{PG_MAJOR_VERSION} HA metapackage.
