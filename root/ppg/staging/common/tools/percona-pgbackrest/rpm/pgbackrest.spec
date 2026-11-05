%define pgmajorversion %!{PG_MAJOR_VERSION}
%global pginstdir /usr/pgsql-%{pgmajorversion}

%{!?runselftest:%global runselftest 0}

# EL-10 and Fedora >= 44: ship a local SELinux policy module that lets
# sshd_session_t search/read the postgres user's home dir (postgresql_db_t),
# so that SSH pubkey auth via ~/.ssh/authorized_keys works:
%if 0%{?rhel} >= 10 || 0%{?fedora} >= 44
%global sshd_selinux 1
%else
%global sshd_selinux 0
%endif

# On RHEL, libssh2 comes from pgdg-libssh2 (EPEL is not needed), which does
# not provide its soname; it is found through the rpath:
%if 0%{?rhel}
%global __requires_exclude ^libssh2\\.so
%endif

%global sname pgbackrest

Summary:        Reliable PostgreSQL Backup & Restore
Name:           percona-pgbackrest
Version:        1.0.0
Release:        %!{PKG_REVISION}%{?dist}
License:        MIT
Group:          Applications/Databases
URL:            http://www.pgbackrest.org
Source:         %{name}-%{version}.tar.gz
Source1:        %{sname}.conf
Source2:	       %{sname}-tmpfiles.d
Source3:	       %{sname}.logrotate
Source4:	       %{sname}.service
Source6:        %{sname}-sysusers.conf
Source8:        %{sname}-sshd-selinux.te

BuildRequires:	gcc zlib-devel percona-postgresql%{pgmajorversion}-devel
BuildRequires:	libzstd-devel libxml2-devel meson
BuildRequires:	libssh2-devel libyaml-devel libcurl-devel >= 8.23.0

%if %sshd_selinux
BuildRequires:        selinux-policy-devel
%endif
%if %runselftest
# The smoke test runs a backup/restore cycle against the PostgreSQL it finds
BuildRequires:        percona-postgresql%{pgmajorversion}-server python3
%endif

%if 0%{?suse_version} >= 1500
Requires:	libopenssl3 libsystemd0
BuildRequires:	libopenssl-3-devel
%endif
%if 0%{?fedora} >= 42 || 0%{?rhel} >= 8
Requires:	openssl-libs >= 1.1.1k systemd-libs
BuildRequires:	openssl-devel
%endif

%if 0%{?fedora} >= 42 || 0%{?rhel} >= 8
Requires:	lz4-libs libzstd libssh2
BuildRequires:	lz4-devel bzip2-devel ninja-build
%endif
%if 0%{?suse_version} && 0%{?suse_version} >= 1500
Requires:	liblz4-1 libzstd1 libssh2-1 libsystemd0
BuildRequires:	liblz4-devel libbz2-devel ninja
%endif

Requires:	postgresql-libs

BuildRequires:		systemd, systemd-devel
# We require this to be present for %%{_prefix}/lib/tmpfiles.d
Requires:		systemd
Requires(post):		systemd
Requires(preun):	systemd
Requires(postun):	systemd

Epoch:		1
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC

%description
pgBackRest aims to be a simple, reliable backup and restore system that can
seamlessly scale up to the largest databases and workloads.

Instead of relying on traditional backup tools like tar and rsync, pgBackRest
implements all backup features internally and uses a custom protocol for
communicating with remote systems. Removing reliance on tar and rsync allows
for better solutions to database-specific backup challenges. The custom remote
protocol allows for more flexibility and limits the types of connections that
are required to perform a backup which increases security.

%prep
%setup -q -n %{sname}-%{version}

%build
export PG_CONFIG=/usr/pgsql-%{pgmajorversion}/bin/pg_config
export PKG_CONFIG_LIBDIR=/usr/pgsql-%{pgmajorversion}/lib/pkgconfig:/usr/lib64/pkgconfig
unset PKG_CONFIG_PATH
%{__install} -d build
%meson
%meson_build

%if %sshd_selinux
checkmodule -M -m -o %{sname}_sshd_fix.mod %{SOURCE8}
semodule_package -o %{sname}_sshd_fix.pp -m %{sname}_sshd_fix.mod
%endif

%install
export PG_CONFIG=/usr/pgsql-%{pgmajorversion}/bin/pg_config
%meson_install
%{__install} -D -d -m 0755 %{buildroot}%{perl_vendorlib} %{buildroot}%{_bindir}
%{__install} -D -d -m 0700 %{buildroot}/%{_sharedstatedir}/%{sname}
%{__install} -D -d -m 0700 %{buildroot}/var/log/%{sname}
%{__install} -D -d -m 0700 %{buildroot}/var/spool/%{sname}
%{__install} -D -d -m 0755 %{buildroot}%{_sysconfdir}
%{__install} %{SOURCE1} %{buildroot}/%{_sysconfdir}/%{sname}.conf

# Install logrotate file:
%{__install} -p -d %{buildroot}%{_sysconfdir}/logrotate.d
%{__install} -p -m 644 %{SOURCE3} %{buildroot}%{_sysconfdir}/logrotate.d/%{sname}

# Install unit file:
%{__install} -d %{buildroot}%{_unitdir}
%{__install} -m 644 %{SOURCE4} %{buildroot}%{_unitdir}/%{sname}.service

%{__install} -m 0644 -D %{SOURCE6} %{buildroot}%{_sysusersdir}/%{sname}.conf

%{__mkdir} -p %{buildroot}/%{_tmpfilesdir}
%{__install} -m 0644 %{SOURCE2} %{buildroot}/%{_tmpfilesdir}/%{sname}.conf

%if %sshd_selinux
%{__install} -d -m 755 %{buildroot}%{_datadir}/selinux/packages
%{__install} -m 644 %{sname}_sshd_fix.pp %{buildroot}%{_datadir}/selinux/packages/
%endif

%check
%if %runselftest
# Upstream's smoke test for packagers: initdb, stanza-create, check, full and
# incremental backups, then a restore of the latter, against every supported
# PostgreSQL found on the system. When run as root, it drops to the postgres
# user.
%meson_test --suite smoke -v
%endif

%pre
%sysusers_create_package %{sname} %SOURCE6

%post
if [ $1 -eq 1 ] ; then
   /usr/bin/systemctl daemon-reload >/dev/null 2>&1 || :
   %if 0%{?suse_version} >= 1500
   %service_add_pre %{sname}.service
   %else
   %systemd_post %{sname}.service
   %endif
fi

%if %sshd_selinux
%{_sbindir}/selinuxenabled 2>/dev/null && \
        %{_sbindir}/semodule -i %{_datadir}/selinux/packages/%{sname}_sshd_fix.pp >/dev/null 2>&1 || :
%endif

%preun
if [ $1 -eq 0 ] ; then
	# Package removal, not upgrade
	/usr/bin/systemctl --no-reload disable %{sname}.service >/dev/null 2>&1 || :
	/usr/bin/systemctl stop %{sname}.service >/dev/null 2>&1 || :
fi

%postun
/usr/bin/systemctl daemon-reload >/dev/null 2>&1 || :

if [ $1 -ge 1 ] ; then
	# Package upgrade, not uninstall
	/usr/bin/systemctl try-restart %{sname}.service >/dev/null 2>&1 || :
fi

%if %sshd_selinux
if [ $1 -eq 0 ] ; then
        # Package removal, not upgrade
        %{_sbindir}/selinuxenabled 2>/dev/null && \
                %{_sbindir}/semodule -r %{sname}_sshd_fix >/dev/null 2>&1 || :
fi
%endif

%files
%defattr(-,root,root)
%license LICENSE
%{_bindir}/%{sname}
%config(noreplace) %attr (644,root,root) %{_sysconfdir}/%{sname}.conf
%config(noreplace) %{_sysconfdir}/logrotate.d/%{sname}
%{_tmpfilesdir}/%{sname}.conf
%{_sysusersdir}/%{sname}.conf
%{_unitdir}/%{sname}.service
%if %sshd_selinux
%{_datadir}/selinux/packages/%{sname}_sshd_fix.pp
%endif
%attr(-,postgres,postgres) /var/log/%{sname}
%attr(-,postgres,postgres) %{_sharedstatedir}/%{sname}
%attr(-,postgres,postgres) /var/spool/%{sname}

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PGBACKREST_VERSION}-1
- Update to upstream version %!{PGBACKREST_VERSION}
