%global short_name      pgpool-II
%global pgmajorversion  17
%global pghome          /usr/pgsql-%{pgmajorversion}

%global _varrundir      %{_localstatedir}/run/pgpool
%global _varlogdir      %{_localstatedir}/log/pgpool
%global _varlibdir      %{_localstatedir}/lib/pgpool

# pcp_* tools are all the same binary (hardlinked); suppress duplicate build-id errors
%undefine _unique_build_ids

Summary:        pgpool-II connection pooling server for PostgreSQL %{pgmajorversion}
Name:           percona-pgpool-II-pg%{pgmajorversion}
Version:        1.0.0
Release:        1%{?dist}
License:        BSD
URL:            https://www.pgpool.net/
Source0:        pgpool2-%{version}.tar.gz

BuildRequires:  percona-postgresql%{pgmajorversion}-devel
BuildRequires:  bison flex
BuildRequires:  pam-devel
BuildRequires:  openssl-devel
%if 0%{?suse_version}
BuildRequires:  openldap2-devel
%else
BuildRequires:  openldap-devel
%endif
BuildRequires:  libtool autoconf automake gcc
%if 0%{?suse_version}
BuildRequires:  libxslt-tools libxslt docbook_4 docbook-xsl-stylesheets docbook-dsssl-stylesheets openjade
%else
BuildRequires:  jade libxslt docbook-dtds docbook-style-xsl docbook-style-dsssl
%endif
%if 0%{?rhel} >= 8 || 0%{?suse_version}
BuildRequires:  llvm-devel clang-devel clang
%endif
%if 0%{?rhel} >= 9
BuildRequires:  libmemcached-awesome-devel
%else
BuildRequires:  libmemcached-devel
%endif
BuildRequires:  systemd
Requires:       percona-postgresql%{pgmajorversion} >= %{pgmajorversion}
%if 0%{?rhel}
Requires(post):   systemd-sysv
%endif
Requires(post):   systemd
Requires(preun):  systemd
Requires(postun): systemd

%description
pgpool-II is a middleware that works between PostgreSQL servers and a
PostgreSQL database client. It provides connection pooling, replication,
load balancing, and limiting of exceeding connections.

%package devel
Summary:        Development headers and libraries for pgpool-II
Requires:       %{name} = %{version}-%{release}

%description devel
Development headers and libraries for building pgpool-II client applications.

%package extensions
Summary:        PostgreSQL %{pgmajorversion} extensions for pgpool-II
Requires:       %{name} = %{version}-%{release}

%description extensions
PostgreSQL extensions (pgpool-recovery, pgpool_adm) for use with pgpool-II.

%prep
%setup -q -n pgpool2-%{version}

%build
libtoolize
autoreconf --force --install
%configure \
    --sysconfdir=%{_sysconfdir}/%{short_name} \
    --with-pgsql=%{pghome} \
    --with-pgsql-includedir=%{pghome}/include/ \
    --with-openssl \
    --with-pam \
    --with-ldap \
    --with-memcached=%{_usr} \
    --disable-static \
    --disable-rpath
make -C src/parser gram.h gram_minimal.h
make %{?_smp_mflags}
make %{?_smp_mflags} -C doc

%install
export PATH=%{pghome}/bin:$PATH
make %{?_smp_mflags} DESTDIR=%{buildroot} install

# install PostgreSQL extensions
make %{?_smp_mflags} DESTDIR=%{buildroot} install -C src/sql/pgpool-recovery
make %{?_smp_mflags} DESTDIR=%{buildroot} install -C src/sql/pgpool_adm

# install man pages built from doc
install -d %{buildroot}%{_mandir}/man1
install doc/src/sgml/man1/*.1 %{buildroot}%{_mandir}/man1
install -d %{buildroot}%{_mandir}/man8
install doc/src/sgml/man8/*.8 %{buildroot}%{_mandir}/man8

# config directories
install -d %{buildroot}%{_datadir}/%{short_name}
install -d %{buildroot}%{_sysconfdir}/%{short_name}
install -d %{buildroot}%{_sysconfdir}/%{short_name}/sample_scripts

# move sample scripts to their subdirectory
for f in failover.sh follow_primary.sh pgpool_remote_start \
          recovery_1st_stage replication_mode_recovery_1st_stage \
          replication_mode_recovery_2nd_stage escalation.sh \
          aws_eip_if_cmd.sh aws_rtb_if_cmd.sh; do
    [ -f %{buildroot}%{_sysconfdir}/%{short_name}/${f}.sample ] && \
        mv %{buildroot}%{_sysconfdir}/%{short_name}/${f}.sample \
           %{buildroot}%{_sysconfdir}/%{short_name}/sample_scripts/${f}.sample || true
done

# create active config files from samples
cp %{buildroot}%{_sysconfdir}/%{short_name}/pgpool.conf.sample \
   %{buildroot}%{_sysconfdir}/%{short_name}/pgpool.conf
cp %{buildroot}%{_sysconfdir}/%{short_name}/pcp.conf.sample \
   %{buildroot}%{_sysconfdir}/%{short_name}/pcp.conf
cp %{buildroot}%{_sysconfdir}/%{short_name}/pool_hba.conf.sample \
   %{buildroot}%{_sysconfdir}/%{short_name}/pool_hba.conf
touch %{buildroot}%{_sysconfdir}/%{short_name}/pool_passwd
touch %{buildroot}%{_sysconfdir}/%{short_name}/pgpool_node_id

# systemd service
install -d %{buildroot}%{_unitdir}
install -m 644 src/redhat/pgpool.service %{buildroot}%{_unitdir}/pgpool.service

# tmpfiles.d — runtime dir /run/pgpool
install -d -m 755 %{buildroot}%{_varrundir}
mkdir -p %{buildroot}%{_tmpfilesdir}
install -m 0644 src/redhat/pgpool_tmpfiles.d \
    %{buildroot}%{_tmpfilesdir}/%{name}.conf

# sysconfig
install -d %{buildroot}%{_sysconfdir}/sysconfig
install -m 644 src/redhat/pgpool_rhel.sysconfig \
    %{buildroot}%{_sysconfdir}/sysconfig/pgpool

# sudoers.d — allow postgres to run ip/arping for watchdog VIP
install -d %{buildroot}%{_sysconfdir}/sudoers.d
install -m 0440 src/redhat/pgpool_sudoers.d \
    %{buildroot}%{_sysconfdir}/sudoers.d/pgpool

# var directories
mkdir -p %{buildroot}%{_varlogdir}
mkdir -p %{buildroot}%{_varlibdir}

# remove static libs
rm -f %{buildroot}%{_libdir}/libpcp.{a,la}

%pre
groupadd -g 26 -o -r postgres >/dev/null 2>&1 || :
useradd -M -g postgres -o -r -d /var/lib/pgsql -s /bin/bash \
        -c "PostgreSQL Server" -u 26 postgres >/dev/null 2>&1 || :

%post
/sbin/ldconfig
%systemd_post pgpool.service

%preun
%systemd_preun pgpool.service

%postun
/sbin/ldconfig
%systemd_postun_with_restart pgpool.service

%files
%doc README TODO COPYING
%dir %{_datadir}/%{short_name}
%{_bindir}/pgpool
%{_bindir}/pcp_attach_node
%{_bindir}/pcp_detach_node
%{_bindir}/pcp_node_count
%{_bindir}/pcp_node_info
%{_bindir}/pcp_pool_status
%{_bindir}/pcp_proc_count
%{_bindir}/pcp_proc_info
%{_bindir}/pcp_promote_node
%{_bindir}/pcp_stop_pgpool
%{_bindir}/pcp_recovery_node
%{_bindir}/pcp_watchdog_info
%{_bindir}/pcp_reload_config
%{_bindir}/pcp_health_check_stats
%{_bindir}/pcp_log_rotate
%{_bindir}/pcp_invalidate_query_cache
%{_bindir}/pg_md5
%{_bindir}/pg_enc
%{_bindir}/pgpool_setup
%{_bindir}/watchdog_setup
%{_bindir}/pgproto
%{_bindir}/wd_cli
%{_mandir}/man8/*.8*
%{_mandir}/man1/*.1*
%{_datadir}/%{short_name}/insert_lock.sql
%{_datadir}/%{short_name}/pgpool.pam
%{_libdir}/libpcp.so.*
%{_tmpfilesdir}/%{name}.conf
%ghost %dir %{_sysconfdir}/sudoers.d
%{_sysconfdir}/sudoers.d/pgpool
%{_unitdir}/pgpool.service
%attr(0755,postgres,postgres) %dir %{_varlogdir}
%attr(0755,postgres,postgres) %dir %{_varlibdir}
%defattr(600,postgres,postgres,-)
%dir %{_sysconfdir}/%{short_name}
%{_sysconfdir}/%{short_name}/pgpool.conf.sample
%{_sysconfdir}/%{short_name}/pcp.conf.sample
%{_sysconfdir}/%{short_name}/pool_hba.conf.sample
%defattr(755,postgres,postgres,-)
%{_sysconfdir}/%{short_name}/sample_scripts/
%defattr(-,root,root,-)
%attr(600,postgres,postgres) %config(noreplace) %{_sysconfdir}/%{short_name}/pgpool.conf
%attr(600,postgres,postgres) %config(noreplace) %{_sysconfdir}/%{short_name}/pcp.conf
%attr(600,postgres,postgres) %config(noreplace) %{_sysconfdir}/%{short_name}/pool_hba.conf
%attr(600,postgres,postgres) %config(noreplace) %{_sysconfdir}/%{short_name}/pool_passwd
%attr(600,postgres,postgres) %config(noreplace) %{_sysconfdir}/%{short_name}/pgpool_node_id
%config(noreplace) %{_sysconfdir}/sysconfig/pgpool

%files devel
%{_includedir}/libpcp_ext.h
%{_includedir}/pcp.h
%{_includedir}/pool_process_reporting.h
%{_includedir}/pool_type.h
%{_libdir}/libpcp.so

%files extensions
%ghost %dir %{pghome}/lib
%ghost %dir %{pghome}/share
%ghost %dir %{pghome}/share/extension
%{pghome}/share/extension/pgpool-recovery.sql
%{pghome}/share/extension/pgpool_recovery--1.1.sql
%{pghome}/share/extension/pgpool_recovery--1.2.sql
%{pghome}/share/extension/pgpool_recovery--1.1--1.2.sql
%{pghome}/share/extension/pgpool_recovery--1.3.sql
%{pghome}/share/extension/pgpool_recovery--1.2--1.3.sql
%{pghome}/share/extension/pgpool_recovery--1.4.sql
%{pghome}/share/extension/pgpool_recovery--1.3--1.4.sql
%{pghome}/share/extension/pgpool_recovery.control
%{pghome}/lib/pgpool-recovery.so
%{pghome}/share/extension/pgpool_adm--1.0.sql
%{pghome}/share/extension/pgpool_adm--1.1.sql
%{pghome}/share/extension/pgpool_adm--1.0--1.1.sql
%{pghome}/share/extension/pgpool_adm--1.2.sql
%{pghome}/share/extension/pgpool_adm--1.1--1.2.sql
%{pghome}/share/extension/pgpool_adm--1.3.sql
%{pghome}/share/extension/pgpool_adm--1.2--1.3.sql
%{pghome}/share/extension/pgpool_adm--1.4.sql
%{pghome}/share/extension/pgpool_adm--1.3--1.4.sql
%{pghome}/share/extension/pgpool_adm--1.5.sql
%{pghome}/share/extension/pgpool_adm--1.4--1.5.sql
%{pghome}/share/extension/pgpool_adm--1.6.sql
%{pghome}/share/extension/pgpool_adm--1.5--1.6.sql
%{pghome}/share/extension/pgpool_adm.control
%{pghome}/lib/pgpool_adm.so
%ghost %dir %{pghome}/lib/bitcode
%dir %{pghome}/lib/bitcode/pgpool-recovery
%dir %{pghome}/lib/bitcode/pgpool_adm
%{pghome}/lib/bitcode/pgpool-recovery.index.bc
%{pghome}/lib/bitcode/pgpool-recovery/pgpool-recovery.bc
%{pghome}/lib/bitcode/pgpool_adm.index.bc
%{pghome}/lib/bitcode/pgpool_adm/pgpool_adm.bc

%changelog
* Tue Mar 10 2026 Percona Build/Release Team <eng-build@percona.com> - 4.7.0-1
- Release 4.7.0-1
