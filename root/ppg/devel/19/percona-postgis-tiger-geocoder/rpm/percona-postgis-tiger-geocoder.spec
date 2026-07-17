%global pgmajor %!{PG_MAJOR_VERSION}

%define pgmajorversion %{pgmajor}
%define pginstdir /usr/pgsql-%{pgmajorversion}
%global sname postgis_tiger_geocoder

%global debug_package %{nil}

Summary:	Geocoder and reverse geocoder for US TIGER data
Name:		percona-postgis-tiger-geocoder%{pgmajorversion}
Version:	1.0.0
Release:	1%{?dist}
License:	GPLv2
Source0:	%{name}-%{version}.tar.gz
URL:		https://git.osgeo.org/gitea/postgis/postgis_tiger_geocoder
BuildArch:	noarch
BuildRequires:	percona-postgresql%{pgmajorversion}-devel perl
Requires:	postgresql%{pgmajorversion}-server
# CREATE EXTENSION postgis_tiger_geocoder requires the postgis and
# fuzzystrmatch (contrib) extensions to be installed.
Requires:	postgis3_%{pgmajorversion}
Requires:	percona-postgresql%{pgmajorversion}-contrib

%description
The postgis_tiger_geocoder PostgreSQL extension provides a geocoder and
reverse geocoder that works with US Census TIGER (Topologically
Integrated Geographic Encoding and Referencing) data. It was formerly
distributed as part of PostGIS and is now maintained as a standalone
SQL-only extension. It requires the postgis and fuzzystrmatch
extensions at CREATE EXTENSION time.

%prep
%setup -q

%build
PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags}

%install
%{__rm} -rf %{buildroot}
PATH=%{pginstdir}/bin:$PATH %{__make} install DESTDIR=%{buildroot}

%files
%defattr(-,root,root,-)
%doc README.md NEWS.md
%license COPYING
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%{pginstdir}/share/extension/%{sname}.control
%{pginstdir}/share/extension/%{sname}*.sql

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{POSTGIS_TIGER_GEOCODER_VERSION}-1
- Initial packaging of the standalone postgis_tiger_geocoder extension
