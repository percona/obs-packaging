%global srcname psycopg2


Summary:        PostgreSQL database adapter for Python
Name:           python3-%{srcname}
Version:        1.0.0
Release:        1%{?dist}
# The exceptions allow linking to OpenSSL and PostgreSQL's libpq
License:        LGPLv3+ with exceptions
URL:            http://initd.org/psycopg/
Source0:        psycopg2-%{version}.tar.gz
# https://github.com/psycopg/psycopg2/blob/2_7_5/doc/src/install.rst#prerequisites
BuildRequires:  percona-postgresql17-devel
BuildRequires:  gcc
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
# For RHEL 9 with Python 3.12
%if 0%{?rhel}
BuildRequires:  python3.12-setuptools
%endif
# rename from python36-psycopg2
Provides:       python36-%{srcname} = %{version}-%{release}
Obsoletes:      python36-%{srcname} < 2.9.1-1


%description
Psycopg is the most popular PostgreSQL adapter for the Python programming
language. At its core it fully implements the Python DB API 2.0 specifications.
Several extensions allow access to many of the features offered by PostgreSQL.


%package tests
Summary:        Test suite for python3-%{srcname}
Requires:       python3-%{srcname} = %{version}-%{release}
# rename from python36-psycopg2-tests
Provides:       python36-%{srcname}-tests = %{version}-%{release}
Obsoletes:      python36-%{srcname}-tests < 2.9.1-1


%description tests
This sub-package delivers set of tests for the adapter.


%prep
%setup -q -n %{srcname}-%{version}
# delete shebangs
find -name \*.py | xargs sed -i -e '1 {/^#!/d}'


%build
export CFLAGS=${RPM_OPT_FLAGS} LDFLAGS=${RPM_LD_FLAGS}
  python3 setup.py build_ext --pg-config /usr/pgsql-17/bin/pg_config build

# Fix for wrong-file-end-of-line-encoding problem; upstream also must fix this.
for i in `find doc -iname "*.html"`; do sed -i 's/\r//' $i; done
for i in `find doc -iname "*.css"`; do sed -i 's/\r//' $i; done

# Get rid of a "hidden" file that rpmlint complains about
%{__rm} -f doc/html/.buildinfo


%install
export CFLAGS=${RPM_OPT_FLAGS} LDFLAGS=${RPM_LD_FLAGS}
  python3 setup.py build_ext --pg-config /usr/pgsql-17/bin/pg_config install --no-compile --root %{buildroot}
cp -r tests/ %{buildroot}%{python3_sitearch}/%{srcname}/tests/
for i in `find %{buildroot}%{python3_sitearch}/%{srcname}/tests/ -iname "*.py"`; do
  sed -i 's|#!/usr/bin/env python|#!/usr/bin/python3|' $i
done


# Copy tests directory:
%{__mkdir} -p %{buildroot}%{python3_sitearch}/%{srcname}/
%{__cp} -rp tests %{buildroot}%{python3_sitearch}/%{srcname}/tests
%{__rm} -f %{buildroot}%{python3_sitearch}/%{srcname}/tests/test_async_keyword.py

%files
%license LICENSE
%doc AUTHORS NEWS README.rst
%{python3_sitearch}/%{srcname}
%{python3_sitearch}/%{srcname}-%{version}-py%{python3_version}.egg-info


%files tests
%{python3_sitearch}/psycopg2/tests


%changelog
* Mon Mar 10 2026 Percona Build/Release Team <eng-build@percona.com> - 2.9.5-1
- Release 2.9.5-1
