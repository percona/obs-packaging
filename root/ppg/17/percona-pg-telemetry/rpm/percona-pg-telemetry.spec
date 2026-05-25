%define pg_version %!{PG_MAJOR_VERSION}
%define pg_name percona-postgresql%{pg_version}

%if 0%{?rhel} >= 8
%global gts_version 14
%endif

%global sname percona-pg-telemetry
%global pgrel %{pg_version}
%global pginstdir /usr/pgsql-%{pg_version}/

Summary:        Statistics collector for PostgreSQL
Name:           %{sname}%{pgrel}
Version:        1.2.0
Release:        1%{?dist}
License:        PostgreSQL
Source0:        %{sname}-%{version}.tar.gz
URL:            https://github.com/percona/percona_pg_telemetry

%if "%{pg_name}" == ""
ExclusiveArch:  do_not_build
Name:           %{sname}
%endif

BuildRequires: %{pg_name}-devel
BuildRequires: clang
BuildRequires: llvm
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
%if 0%{?suse_version}
BuildRequires: chrpath
%endif

Requires:       percona-telemetry-agent
Conflicts:      %{sname}%{pgrel}
Obsoletes:      %{sname}%{pgrel} <= %{version}-%{release}
Epoch:          1
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, Inc

%description
The percona_pg_telemetry is an extension for Percona telemetry data collection for PostgreSQL.

%prep
%setup -q -n %{sname}-%{version}


%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
USE_PGXS=1 PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags}


%install
%{__rm} -rf %{buildroot}
USE_PGXS=1 PATH=%{pginstdir}/bin:$PATH %{__make} %{?_smp_mflags} install DESTDIR=%{buildroot}
%{__install} -d %{buildroot}%{pginstdir}/share/extension
%{__install} -m 755 README.md %{buildroot}%{pginstdir}/share/extension/README-percona_pg_telemetry
%if 0%{?suse_version}
# Add ldconfig entry for PostgreSQL library path
%{__install} -d %{buildroot}%{_sysconfdir}/ld.so.conf.d
echo "%{pginstdir}/lib" > %{buildroot}%{_sysconfdir}/ld.so.conf.d/percona-postgresql%{pgrel}.conf
# Strip RPATH since we're using system-wide library path configuration
chrpath --delete %{buildroot}%{pginstdir}/lib/percona_pg_telemetry.so 2>/dev/null || :
%endif


%clean
%{__rm} -rf %{buildroot}

%pre -n %{sname}%{pgrel}
if [ $1 == 1 ]; then
  if ! getent passwd postgres > /dev/null 2>&1; then
    groupadd -g 26 -o -r postgres >/dev/null 2>&1 || :
    /usr/sbin/useradd -M -g postgres -o -r -d /var/lib/pgsql -s /bin/bash \
        -c "PostgreSQL Server" -u 26 postgres >/dev/null 2>&1 || :
  fi
fi

%post -n %{sname}%{pgrel}
if getent group percona-telemetry > /dev/null 2>&1; then
  usermod -a -G percona-telemetry postgres || :
  install -d -m 2775 -o postgres -g percona-telemetry /usr/local/percona/telemetry/pg || :
else
  install -d -m 2775 -o postgres -g postgres /usr/local/percona/telemetry/pg || :
fi
%if 0%{?suse_version}
# Update dynamic linker cache for new library path
/sbin/ldconfig
%endif

%postun -n %{sname}%{pgrel}
rm -rf /usr/local/percona/telemetry/pg
%if 0%{?suse_version}
# Update dynamic linker cache after package removal
/sbin/ldconfig
%endif

%files
%defattr(755,root,root,755)
%dir %{pginstdir}/lib
%dir %{pginstdir}/lib/bitcode/percona_pg_telemetry
%dir %{pginstdir}/share
%dir %{pginstdir}/share/extension
%doc %{pginstdir}/share/extension/README-percona_pg_telemetry
%{pginstdir}/lib/percona_pg_telemetry.so
%{pginstdir}/share/extension/percona_pg_telemetry--*.sql
%{pginstdir}/share/extension/percona_pg_telemetry.control
%{pginstdir}/lib/bitcode/percona_pg_telemetry*.bc
%{pginstdir}/lib/bitcode/percona_pg_telemetry/*.bc
%if 0%{?suse_version}
%config(noreplace) %{_sysconfdir}/ld.so.conf.d/percona-postgresql%{pgrel}.conf
%endif


%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PG_TELEMETRY_VERSION}-1
- Update to upstream version %!{PG_TELEMETRY_VERSION}
