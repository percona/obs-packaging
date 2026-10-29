%global debug_package %{nil}
%if 0%{?rhel} && 0%{?rhel} >= 8
%global __ospython        %{_bindir}/python3.12
%global python3_pkgprefix python3.12
%global python3_buildversion 3.12
%global __requires_exclude ^python3\\.12dist
%else
%global __ospython        %{_bindir}/python3
%global python3_pkgprefix python3
%global python3_buildversion 3
%endif
%{expand: %%global py3ver %(echo `%{__ospython} -P -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" `)}
%global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '/usr', 'base': '%{_prefix}'}))")

Name:           %{python3_pkgprefix}-authlib
Version:        1.9.1
Release:        1%{?dist}
Summary:        The ultimate Python library in building OAuth and OpenID Connect servers and clients
License:        BSD-3-Clause
URL:            https://github.com/authlib/authlib
Source0:        https://files.pythonhosted.org/packages/source/A/Authlib/authlib-1.9.1.tar.gz
BuildArch:      noarch
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>
Epoch:          1

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
# runtime dependencies, also needed by the %check import test
BuildRequires:  python3.12-cryptography
BuildRequires:  python3.12-joserfc

Requires:       python3.12-cryptography
# authlib 1.7+ delegates JOSE (JWS/JWE/JWK/JWT) to joserfc
Requires:       python3.12-joserfc
# authlib.integrations.flask_client imports ..requests_client unconditionally,
# which needs requests (RHEL 9 package). Found by the Task 5 smoke test.
Requires:       python3.12-requests

%description
The ultimate Python library in building OAuth and OpenID Connect servers and clients.

Built for Python 3.12 from the PyPI sdist; part of the pgAdmin 4 (percona-pgadmin4) dependency stack.

%prep
%autosetup -p1 -n authlib-1.9.1

%build
%{__ospython} -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .

%install
%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix} dist/*.whl

%check
PYTHONPATH=%{buildroot}%{python3_sitelib} %{__ospython} -P -c "import authlib, authlib.oidc.core"

%files
%{python3_sitelib}/*

%changelog
* Thu Oct 29 2026 Percona Development Team <info@percona.com> - 1.9.1-1
- Update to Authlib 1.9.1 (CVE-2026-96760, CVE-2026-114615, CVE-2026-114616)
- Require python3.12-joserfc (new runtime dependency since 1.7)

* Thu Aug 27 2026 Percona Development Team <info@percona.com> - 1.6.12-1
- Package Authlib 1.6.12 for Python 3.12 (pgAdmin 4 dependency stack)
