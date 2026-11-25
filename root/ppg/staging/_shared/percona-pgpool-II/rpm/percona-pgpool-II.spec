%global short_name      pgpool-II
%global pgmajorversion  %!{PG_MAJOR_VERSION}
%define pgminorversion %!{PG_VERSION}

%if 0%{?rhel} >= 8 && 0%{?rhel} <= 9
%global gts_version 14
%endif
%global pghome          /usr/pgsql-%{pgmajorversion}

%global _varrundir      %{_localstatedir}/run/pgpool
%global _varlogdir      %{_localstatedir}/log/pgpool
%global _varlibdir      %{_localstatedir}/lib/pgpool

%{!?runselftest:%global runselftest 0}

# EL-10 and Fedora >= 44: ship a local SELinux policy module that lets
# sshd_session_t search/read the postgres user's home dir (postgresql_db_t),
# so that SSH pubkey auth via ~/.ssh/authorized_keys works for the failover
# and online recovery scripts on hosts without a PostgreSQL server package:
%if 0%{?rhel} >= 10 || 0%{?fedora} >= 44
%global sshd_selinux 1
%else
%global sshd_selinux 0
%endif

# On RHEL 10, libmemcached comes from pgdg-libmemcached-awesome (EPEL is not
# needed), which does not provide its sonames; it is found through the rpath:
%if 0%{?rhel} == 10
%global __requires_exclude ^lib(hashkit|memcached|memcachedutil)\\.so
%global memcached_dir %{pgdg_libmemcachedinstdir}
%else
%global memcached_dir %{_includedir}/libmemcached
%endif

# pcp_* tools are all the same binary (hardlinked); suppress duplicate build-id errors
%undefine _unique_build_ids

Summary:        pgpool-II connection pooling server for PostgreSQL %{pgmajorversion}
Name:           percona-pgpool-II-pg%{pgmajorversion}
Version:        1.0.0
Release:        %!{PKG_REVISION}%{?dist}
License:        BSD
URL:            https://www.pgpool.net/
Source0:        pgpool2-%{version}.tar.gz
Source1:        pgpool-II-sshd-selinux.te
Source2:		    pgpool-II.sysconfig
Source6:		    pgpool-II-sysusers.conf
Source7:		    pgpool-II-tmpfiles.d
Source8:		    pgpool-II-check.sh
Source9:		    pgpool-II.service
Patch0:         pgpool_socket_dir.patch
Patch1:         pcp_unix_domain_path.patch
Patch2:         pgpool_log.patch
Patch3:         pgpool.conf.sample.patch

%if 0%{?pgminorversion:1}
# pgminorversion is the PostgreSQL minor release that the build servers
# build against (global/Makefile.global): require at least that one, at
# build time and at runtime.
# The other postgresqlNN-* dependencies need no version here: the PostgreSQL
# subpackages require each other's exact version-release (all of them pin
# the client package, which pins -libs), so the server, contrib etc. follow
# -devel at build time and -libs at runtime.
BuildRequires:	percona-postgresql%{pgmajorversion}-devel >= %{pgminorversion}
Requires:	percona-postgresql%{pgmajorversion}-libs >= %{pgminorversion}
%endif

BuildRequires:  bison flex
BuildRequires:  pam-devel
BuildRequires:  openssl-devel
%if 0%{?suse_version}
BuildRequires:  openldap2-devel
%else
BuildRequires:  openldap-devel
%endif
BuildRequires:  libtool autoconf automake gcc
%if 0%{?gts_version}
BuildRequires:  gcc-toolset-%{gts_version}-gcc gcc-toolset-%{gts_version}-gcc-c++ gcc-toolset-%{gts_version}-annobin-plugin-gcc
%endif
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
%if %runselftest
BuildRequires:	percona-postgresql%{pgmajorversion}-server percona-postgresql%{pgmajorversion}-contrib
BuildRequires:	pgdg-srpm-macros >= 2.0.0 openssl iputils
%if 0%{?suse_version}
BuildRequires:	procps
%else
BuildRequires:	procps-ng
%endif
%endif
BuildRequires:  systemd
%if %sshd_selinux
BuildRequires:  selinux-policy-devel
%endif
Requires:       percona-postgresql%{pgmajorversion} >= %{pgmajorversion}
Requires:       percona-postgresql%{pgmajorversion}-server
Requires:       %{name}-pcp = %{version}-%{release}
%if 0%{?rhel}
Requires(post):   systemd-sysv
%endif
Requires(post):   systemd
Requires(preun):  systemd
Requires(postun): systemd

%description
Pgpool-II is a middleware that works between PostgreSQL servers and a
PostgreSQL database client. It provides the following features:
 * Connection Pooling
 * Replication
 * Load Balancing
 * Limiting Exceeding Connections
 * Watchdog
 * In Memory Query Cache

%package devel
Summary:        Development headers and libraries for pgpool-II
Requires:       %{name} = %{version}-%{release}
Requires:       %{name}-pcp = %{version}-%{release}

%description devel
Development headers and libraries for building pgpool-II client applications.

%package extensions
Summary:        PostgreSQL %{pgmajorversion} extensions for pgpool-II
Requires:       %{name} = %{version}-%{release}

%description extensions
PostgreSQL extensions (pgpool-recovery, pgpool_adm) for use with pgpool-II.

%package -n %{name}-pcp
Summary:	PCP (Pgpool Control Protocol) files of Pgpool.

%description -n %{name}-pcp
PCP (Pgpool Control Protocol) files of Pgpool, shared across
multiple Pgpool installations.

%prep
%setup -q -n pgpool2-%{version}
%patch -P 0 -p0
%patch -P 1 -p0
%patch -P 2 -p0
%patch -P 3 -p0

%build
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
# We need this flag on SLES so that pgpool can find libmemched.
# Otherwise, we get "libmemcached.so: undefined reference to `pthread_once'" error.
%if 0%{?suse_version}
%if 0%{?suse_version} >= 1500
	export LDFLAGS='-lpthread'
%endif
%endif
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
export PATH=%{pghome}/bin/:$PATH
make %{?_smp_mflags}
make %{?_smp_mflags} -C doc
make %{?_smp_mflags} -C src/sql/pgpool_adm
make %{?_smp_mflags} -C src/sql/pgpool-recovery

%check
%if %runselftest
%pgdg_check_init
PGDG_PGINSTDIR=%{pghome}
PGPOOL_PREFIX=%{_prefix} PGPOOL_BINDIR=%{_bindir} PGPOOL_LIBDIR=%{_libdir}
PGPOOL_CONFDIR=%{_sysconfdir}/%{name}
. %{SOURCE8}
%endif

%install
%if 0%{?gts_version}
source /opt/rh/gcc-toolset-%{gts_version}/enable
%endif
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

%{__install} -d %{buildroot}%{_unitdir}
%{__install} -m 644 %{SOURCE9} %{buildroot}%{_unitdir}/pgpool.service

%{__install} -d %{buildroot}%{_sysconfdir}/sysconfig
%{__install} -m 644 %{SOURCE2} %{buildroot}%{_sysconfdir}/sysconfig/pgpool
%{__install} -m 0644 -D %{SOURCE6} %{buildroot}%{_sysusersdir}/pgpool-II.conf

%{__mkdir} -p %{buildroot}/%{_tmpfilesdir}
%{__install} -m 0644 %{SOURCE7} %{buildroot}/%{_tmpfilesdir}/%{name}.conf

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

# sudoers.d — allow postgres to run ip/arping for watchdog VIP
install -d %{buildroot}%{_sysconfdir}/sudoers.d
install -m 0440 src/redhat/pgpool_sudoers.d \
    %{buildroot}%{_sysconfdir}/sudoers.d/pgpool

%if %sshd_selinux
checkmodule -M -m -o pgpool_II_sshd_fix.mod %{SOURCE1}
semodule_package -o pgpool_II_sshd_fix.pp -m pgpool_II_sshd_fix.mod
install -d -m 755 %{buildroot}%{_datadir}/selinux/packages
install -m 644 pgpool_II_sshd_fix.pp %{buildroot}%{_datadir}/selinux/packages/
%endif

# var directories
mkdir -p %{buildroot}%{_varlogdir}
mkdir -p %{buildroot}%{_varlibdir}

# fix man page permissions (spurious execute bit from make install)
find %{buildroot}%{_mandir} -type f -exec chmod 644 {} \;

# remove static libs
rm -f %{buildroot}%{_libdir}/libpgpoolpcp.{a,la}

%pre
%sysusers_create_package %{name} %SOURCE6

%post
/sbin/ldconfig
%systemd_post pgpool.service
systemd-tmpfiles --create %{_tmpfilesdir}/%{name}.conf 2>/dev/null || :
%if %sshd_selinux
%{_sbindir}/selinuxenabled 2>/dev/null && \
	%{_sbindir}/semodule -i %{_datadir}/selinux/packages/pgpool_II_sshd_fix.pp >/dev/null 2>&1 || :
%endif

%preun
%systemd_preun pgpool.service

%postun
/sbin/ldconfig
%systemd_postun_with_restart pgpool.service
%if %sshd_selinux
if [ $1 -eq 0 ] ; then
	# Package removal, not upgrade
	%{_sbindir}/selinuxenabled 2>/dev/null && \
		%{_sbindir}/semodule -r pgpool_II_sshd_fix >/dev/null 2>&1 || :
fi
%endif

%files
%doc README TODO INSTALL AUTHORS ChangeLog NEWS
%license COPYING
%dir %{_datadir}/%{short_name}
%{_bindir}/pgpool
%{_bindir}/pg_md5
%{_bindir}/pg_enc
%{_bindir}/pgpool_setup
%{_bindir}/watchdog_setup
%{_bindir}/pgproto
%{_mandir}/man8/*.8*
%{_mandir}/man1/*.1*
%{_datadir}/%{short_name}/insert_lock.sql
%{_datadir}/%{short_name}/pgpool.pam
%{_sysconfdir}/pgpool-II/*.sample*
%{_sysusersdir}/pgpool-II.conf
%{_tmpfilesdir}/%{name}.conf
%ghost %dir /run/pgpool
%dir %attr(0750,root,root) %{_sysconfdir}/sudoers.d
%{_sysconfdir}/sudoers.d/pgpool
%{_unitdir}/pgpool.service
%if %sshd_selinux
%{_datadir}/selinux/packages/pgpool_II_sshd_fix.pp
%endif
%attr(0755,postgres,postgres) %dir %{_varlogdir}
%attr(0755,postgres,postgres) %dir %{_varlibdir}
%defattr(600,postgres,postgres,-)
%dir %{_sysconfdir}/%{short_name}
%{_sysconfdir}/%{short_name}/pgpool.conf.sample
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

%files extensions
%ghost %dir %{pghome}/lib
%ghost %dir %{pghome}/share
%ghost %dir %{pghome}/share/extension
%{pghome}/lib/pgpool_adm.so
%{pghome}/lib/pgpool-recovery.so
%{pghome}/share/extension/pgpool_adm*.sql
%{pghome}/share/extension/pgpool_adm.control
%{pghome}/share/extension/pgpool-recovery.sql
%{pghome}/share/extension/pgpool_recovery*.sql
%{pghome}/share/extension/pgpool_recovery.control
%ghost %dir %{pghome}/lib/bitcode
%dir %{pghome}/lib/bitcode/pgpool-recovery
%dir %{pghome}/lib/bitcode/pgpool_adm
%{pghome}/lib/bitcode/pgpool-recovery.index.bc
%{pghome}/lib/bitcode/pgpool-recovery/pgpool-recovery.bc
%{pghome}/lib/bitcode/pgpool_adm.index.bc
%{pghome}/lib/bitcode/pgpool_adm/pgpool_adm.bc

%files -n %{name}-pcp
%{_bindir}/pcp_attach_node
%{_bindir}/pcp_detach_node
%{_bindir}/pcp_health_check_stats
%{_bindir}/pcp_invalidate_query_cache
%{_bindir}/pcp_log_rotate
%{_bindir}/pcp_node_count
%{_bindir}/pcp_node_info
%{_bindir}/pcp_pool_status
%{_bindir}/pcp_proc_count
%{_bindir}/pcp_proc_info
%{_bindir}/pcp_promote_node
%{_bindir}/pcp_recovery_node
%{_bindir}/pcp_reload_config
%{_bindir}/pcp_stop_pgpool
%{_bindir}/pcp_watchdog_info
%{_bindir}/wd_cli
%{_libdir}/libpgpoolpcp.so*

%changelog
* %!{FILE_MODIFY_DATE} Percona Development Team <info@percona.com> - %!{PGPOOL_VERSION}-1
- Update to upstream version %!{PGPOOL_VERSION}
