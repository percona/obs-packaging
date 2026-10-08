%global sname pgbouncer

Name:		percona-pgbouncer
Version:	1.0.0
Release:	1%{?dist}
Summary:	Lightweight connection pooler for PostgreSQL
License:	MIT and BSD
URL:		https://www.pgbouncer.org/
Packager:       Percona Development Team <https://jira.percona.com>
Vendor:         Percona, LLC
Source0:	%{name}-%{version}.tar.gz
Source2:	%{sname}.sysconfig
Source3:	%{sname}.logrotate
Source4:	%{sname}.service
Source5:	%{sname}-sysusers.conf
Source6:        %{sname}-tmpfiles.d
Patch0:		%{sname}-ini.patch

BuildRequires:	gcc libevent-devel >= 2.0 libtool pandoc systemd-devel
Requires:	libevent >= 2.0
%if 0%{?rhel} >= 8
Requires:	python3.12 python3.12-psycopg2
%else
Requires:	python3 python3-psycopg2
%endif
BuildRequires:	pam-devel

%if 0%{?suse_version} >= 1500
Requires:	libopenssl3
BuildRequires:	libopenssl-3-devel
%endif
%if 0%{?fedora} >= 43 || 0%{?rhel} >= 8
Requires:	openssl-libs >= 1.1.1k
BuildRequires:	openssl-devel
%endif

%if 0%{?fedora} >= 43 || 0%{?rhel} >= 8
BuildRequires:	c-ares-devel >= 1.13
Requires:	c-ares >= 1.13
%endif
%if 0%{?suse_version} >= 1500
BuildRequires:	c-ares-devel >= 1.13
Requires:	libcares2 >= 1.19
%endif

%if 0%{?suse_version} == 1500
BuildRequires:	openldap2-devel
Requires:	libldap-2_4-2
%endif
%if 0%{?suse_version} == 1600
BuildRequires:	openldap2-devel
Requires:	libldap-2
%endif
%if 0%{?suse_version} > 1600
BuildRequires:	openldap2-devel
Requires:	libldap-2_5-0
%endif
%if 0%{?fedora} >= 43 || 0%{?rhel} >= 8
BuildRequires:	openldap-devel
Requires:	openldap
%endif
%if 0%{?rhel} >= 8
BuildRequires:	python3.12
%endif

BuildRequires:		systemd
Requires:		systemd
%if !0%{?suse_version}
Requires(post):		systemd-sysv
%endif
Requires(post):		systemd
Requires(preun):	systemd
Requires(postun):	systemd

%if 0%{?suse_version}
Requires(pre):	shadow
%else
Requires:	/usr/sbin/useradd
%endif
Provides:   pgbouncer
Epoch:		1

%description
pgbouncer is a lightweight connection pooler for PostgreSQL.
pgbouncer uses libevent for low-level socket handling.


%prep
%setup -q
%patch -P 0 -p0


%build
./autogen.sh
sed -i.fedora \
 -e 's|-fomit-frame-pointer||' \
 -e '/BININSTALL/s|-s||' \
 configure

%configure \
        --datadir=%{_datadir} \
%if 0%{?rhel} >= 8
        --with-cares --disable-evdns \
%else
        --without-cares \
%endif
        --with-systemd \
        --with-ldap \
        --with-pam

%{__make} %{?_smp_mflags} V=1

%install
%{__rm} -rf %{buildroot}
%{__make} install DESTDIR=%{buildroot}
%{__install} -p -d %{buildroot}%{_sysconfdir}/%{sname}/
%{__install} -p -d %{buildroot}%{_sysconfdir}/sysconfig
%{__install} -p -m 644 %{SOURCE2} %{buildroot}%{_sysconfdir}/sysconfig/%{sname}
%{__install} -p -m 644 etc/pgbouncer.ini %{buildroot}%{_sysconfdir}/%{sname}
%{__install} -p -m 700 etc/mkauth.py %{buildroot}%{_sysconfdir}/%{sname}/
%if 0%{?rhel} >= 8
sed -i 's|/usr/bin/env python3|/usr/bin/python3.12|' %{buildroot}%{_sysconfdir}/%{sname}/mkauth.py
%endif

%{__install} -d %{buildroot}%{_unitdir}
%{__install} -m 644 %{SOURCE4} %{buildroot}%{_unitdir}/%{sname}.service

%{__mkdir} -p %{buildroot}%{_tmpfilesdir}
%{__install} -m 0644 %{SOURCE6} %{buildroot}/%{_tmpfilesdir}/%{sname}.conf

# Install sysusers.d config file to allow rpm to create users/groups automatically.
%{__install} -m 0644 -D %{SOURCE5} %{buildroot}%{_sysusersdir}/%{name}.conf

%{__install} -d -m 755 %{buildroot}/var/run/%{sname}
%{__install} -p -d %{buildroot}%{_sysconfdir}/logrotate.d
%{__install} -p -m 644 %{SOURCE3} %{buildroot}%{_sysconfdir}/logrotate.d/%{sname}


%post
%systemd_post %{sname}.service
if [ ! -d %{_localstatedir}/log/pgbouncer ] ; then
%{__mkdir} -m 700 %{_localstatedir}/log/pgbouncer
fi
%{__chown} -R pgbouncer:pgbouncer %{_localstatedir}/log/pgbouncer
%{__chown} -R pgbouncer:pgbouncer %{_rundir}/%{sname} >/dev/null 2>&1 || :

%pre
%sysusers_create_package %{sname} %SOURCE5

%preun
%systemd_preun %{sname}.service

%postun
if [ $1 -eq 0 ]; then
%{__rm} -rf %{_rundir}/%{sname}
fi
%systemd_postun_with_restart %{sname}.service

%clean
%{__rm} -rf %{buildroot}

%files
%doc /usr/share/doc/%{sname}
%license COPYRIGHT
%dir %{_sysconfdir}/%{sname}
%{_bindir}/%{sname}
%config(noreplace) %{_sysconfdir}/%{sname}/%{sname}.ini
%ghost %{_rundir}/%{sname}
%{_tmpfilesdir}/%{sname}.conf
%{_sysusersdir}/%{name}.conf
%attr(644,root,root) %{_unitdir}/%{sname}.service
%config(noreplace) %{_sysconfdir}/sysconfig/%{sname}
%config(noreplace) %{_sysconfdir}/logrotate.d/%{sname}
%{_mandir}/man1/%{sname}.*
%{_mandir}/man5/%{sname}.*
%{_sysconfdir}/%{sname}/mkauth.py*
%attr(755,pgbouncer,pgbouncer) %dir /var/run/%{sname}

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PGBOUNCER_VERSION}-1
- Update to upstream version %!{PGBOUNCER_VERSION}
