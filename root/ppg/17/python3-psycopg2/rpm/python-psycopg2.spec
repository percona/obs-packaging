%global srcname psycopg2

%if 0%{?rhel} && 0%{?rhel} >= 9
%global __ospython %{_bindir}/python3.12
%global python3_buildversion 3.12
%global __requires_exclude ^python3\\.12dist
%global python3_sitearch %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('platlib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")
%global python3_version 3.12
%else
%global __ospython %{_bindir}/python3
%global python3_buildversion 3
%endif

%if 0%{?rhel} && 0%{?rhel} >= 9
%global pkgprefix python3.12
%else
%global pkgprefix python3
%endif

Summary:        PostgreSQL database adapter for Python
Name:           %{pkgprefix}-%{srcname}
Version:        1.0.0
Release:        1%{?dist}
# The exceptions allow linking to OpenSSL and PostgreSQL's libpq
License:        LGPLv3+ with exceptions
URL:            http://initd.org/psycopg/
Source0:        psycopg2-%{version}.tar.gz
BuildRequires:  percona-postgresql17-devel
BuildRequires:  gcc
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-setuptools
# rename from python36-psycopg2
Provides:       python36-%{srcname} = %{version}-%{release}
Obsoletes:      python36-%{srcname} < 2.9.1-1


%description
Psycopg is the most popular PostgreSQL adapter for the Python programming
language. At its core it fully implements the Python DB API 2.0 specifications.
Several extensions allow access to many of the features offered by PostgreSQL.


%package tests
Summary:        Test suite for %{name}
Requires:       %{name} = %{version}-%{release}
# rename from python36-psycopg2-tests
Provides:       python36-%{srcname}-tests = %{version}-%{release}
Obsoletes:      python36-%{srcname}-tests < 2.9.1-1


%description tests
This sub-package delivers set of tests for the adapter.


%prep
%setup -q -n %{srcname}-%{version}
# delete shebangs
find -name \*.py | xargs sed -i -e '1 {/^#!/d}'
%if 0%{?suse_version} > 1600
# Python 3.13 removed the private _PyInterpreterState_Get(); use public API
sed -i 's/_PyInterpreterState_Get()/PyInterpreterState_Get()/g' psycopg/utils.c
%endif


%build
export CFLAGS=${RPM_OPT_FLAGS} LDFLAGS=${RPM_LD_FLAGS}
%{__ospython} setup.py build_ext --pg-config /usr/pgsql-17/bin/pg_config build

# Fix for wrong-file-end-of-line-encoding problem; upstream also must fix this.
for i in `find doc -iname "*.html"`; do sed -i 's/\r//' $i; done
for i in `find doc -iname "*.css"`; do sed -i 's/\r//' $i; done

# Get rid of a "hidden" file that rpmlint complains about
%{__rm} -f doc/html/.buildinfo


%install
export CFLAGS=${RPM_OPT_FLAGS} LDFLAGS=${RPM_LD_FLAGS}
%{__ospython} setup.py build_ext --pg-config /usr/pgsql-17/bin/pg_config install --no-compile --root %{buildroot}
%if !0%{?suse_version}
cp -r tests/ %{buildroot}%{python3_sitearch}/%{srcname}/tests/
for i in `find %{buildroot}%{python3_sitearch}/%{srcname}/tests/ -iname "*.py"`; do
  sed -i "s|#!/usr/bin/env python|#!/usr/bin/env %{__ospython}|" $i
done
%{__mkdir} -p %{buildroot}%{python3_sitearch}/%{srcname}/tests
%{__rm} -f %{buildroot}%{python3_sitearch}/%{srcname}/tests/test_async_keyword.py
%endif

%files
%license LICENSE
%doc AUTHORS NEWS README.rst
%{python3_sitearch}/%{srcname}
%{python3_sitearch}/%{srcname}-%{version}-py%{python3_version}.egg-info


%if !0%{?suse_version}
%files tests
%{python3_sitearch}/psycopg2/tests
%endif


%changelog
* Sun Mar 30 2026 Percona Build/Release Team <eng-build@percona.com> - 2.9.10-1
- Update to 2.9.10, use python3.12 on RHEL >= 9
* Mon Mar 10 2026 Percona Build/Release Team <eng-build@percona.com> - 2.9.5-1
- Release 2.9.5-1
