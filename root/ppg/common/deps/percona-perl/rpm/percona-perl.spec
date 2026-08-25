# PERCONA PACKAGE for ppg:common:deps (RockyLinux_8 and RockyLinux_9 only).
#
# /opt-prefixed Perl runtime consumed by the Percona PostgreSQL binary
# tarball (QA items 3 and 7 of the 2026-07 tarball QA round).
#
# Why this exists: the tarball bundles the RPM-built plperl.so, which
# dlopens libperl and then loads strict.pm/POSIX.pm from the @INC paths
# COMPILED INTO that libperl. The distro libperl's compiled @INC points at
# /usr/share/perl5 and /usr/lib64/perl5 — paths that do not exist on the
# tarball's target hosts — so plperl only worked when the server was
# started through an env-exporting wrapper (PERL5LIB), and QA proved any
# wrapper bypass breaks it. This package builds Perl from source with
# every install path compiled to /opt/percona-perl, so plperl.so works
# with ZERO environment variables — the official tarball's mechanism.
#
# ABI constraint (load-bearing): plperl.so is linked against the distro
# libperl (DT_NEEDED libperl.so.5.26 on EL8, libperl.so.5.32 on EL9) and
# was compiled against the distro perl's config.h. The version MUST equal
# the distro perl per base (5.26.3 on EL8, 5.32.1 on EL9) and the
# ABI-relevant Configure options MUST match the distro build. The
# Configure invocation below replicates the Rocky Linux perl config_args
# (captured verbatim from `perl -V:config_args` on Rocky 8.10
# perl-5.26.3-423.el8_10 and Rocky 9 perl-5.32.1-483.el9) minus:
#   - all path flags (-Dprefix/-Dprivlib/-Darchlib/... -> /opt/percona-perl,
#     flat lib/<version> layout so libperl lands at lib/<version>/CORE/,
#     exactly where the tarball points plperl.so's RUNPATH);
#   - toolchain dressing (-Dccflags hardening specs, -Dldflags,
#     -Dccdlflags, -Dcf_by, -Doptimize=none + -DDEBUGGING=-g): replaced by
#     %%{optflags} and Configure's defaults. NOT ABI-relevant. Note the
#     distro's -Dccdlflags override is deliberately NOT replicated: the
#     default ccdlflags embed an rpath to <archlib>/CORE, which our
#     off-path /opt layout needs so bin/perl finds libperl.so.5.xx;
#   - -Dusedtrace: SDT probes are interpreter-internal, no ABI effect,
#     and would add a systemtap-sdt-devel BuildRequires;
#   - -Dshrpdir=/usr/lib64: default (archlib/CORE) is what we want;
#   - -Di_gdbm: gdbm-devel is not in the default EL9 repos; i_gdbm only
#     gates the optional GDBM_File module, never loaded by plperl or any
#     tarball component, and does not affect the libperl ABI.
# Everything ABI-relevant is kept identical: usethreads, useithreads,
# useshrplib, use64bitint, uselargefiles, useperlio, archname
# <arch>-linux-thread-multi, d_semctl_semun, the *_r_proto overrides,
# usesitecustomize, and -Dlibperl so the SONAME matches plperl.so's
# DT_NEEDED exactly.
#
# The full core module set is kept (strict, POSIX, Safe, Opcode are
# load-bearing for plperl/plperlu). Man pages and pod documentation ship
# as upstream installs them (under the /opt prefix, like the official
# tarball's percona-perl/man tree).
#
# The name is deliberately distinct from the distro perl and everything
# installs under /opt/percona-perl: nothing shadows system packages.
# ppg:common:deps is publish=false project-wide.

%global perl_prefix /opt/percona-perl

# PERCONA: version MUST track the distro perl of each build base (see the
# ABI constraint above). The SONAME must equal plperl.so's DT_NEEDED.
%if 0%{?rhel} == 8
%global perl_version 5.26.3
%global perl_soname libperl.so.5.26
%else
%global perl_version 5.32.1
%global perl_soname libperl.so.5.32
%endif

# PERCONA: this is a self-contained /opt runtime. Do not leak perl(...)
# provides (they would satisfy other packages' perl-module deps in the
# repo) and do not require perl(...)/libperl (self-contained; libperl is
# our own file). ELF requires on system libs (glibc, libxcrypt, libdb)
# are kept.
%global __provides_exclude_from ^%{perl_prefix}/.*$
%global __requires_exclude ^(perl\\(|libperl)
# PERCONA: keep our /opt/percona-perl/bin/perl shebangs untouched.
%undefine __brp_mangle_shebangs

Name:           percona-perl
Version:        %{perl_version}
Release:        1%{?dist}
Summary:        Perl runtime under /opt/percona-perl for the Percona PostgreSQL binary tarball
License:        GPL-1.0-or-later OR Artistic-1.0-Perl
URL:            https://www.perl.org/
# PERCONA: both distro-matched versions ship as sources; %%{?rhel} picks.
Source0:        perl-5.26.3.tar.gz
Source1:        perl-5.32.1.tar.gz
# PERCONA: 5.26-only — build against libxcrypt's crypt.h (no
# current_saltbits member); upstream dropped the code in 5.28.
Patch0:         perl-5.26.3-crypt-libxcrypt.patch

BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  redhat-rpm-config
BuildRequires:  libxcrypt-devel
BuildRequires:  libdb-devel
BuildRequires:  findutils
BuildRequires:  tar
BuildRequires:  gzip

%description
Perl %{perl_version} built from the upstream source with every install
path compiled to /opt/percona-perl, matching the distro perl version and
ABI-relevant configuration so the RPM-built plperl.so resolves this
libperl (SONAME %{perl_soname}) and its compiled-in @INC without any
environment variables. Consumed by the Percona PostgreSQL binary tarball
build; not intended for standalone installation.

%prep
%if 0%{?rhel} == 8
%setup -q -n perl-%{perl_version}
%patch0 -p1
%else
%setup -q -T -b 1 -n perl-%{perl_version}
%endif

%build
./Configure -des \
    -Dcc=gcc \
    -Doptimize="%{optflags}" \
    -Dversion=%{perl_version} \
    -Dmyhostname=localhost \
    -Dperladmin=root@localhost \
    -Dprefix=%{perl_prefix} \
    -Dsiteprefix=%{perl_prefix} \
    -Dvendorprefix=%{perl_prefix} \
    -Dprivlib=%{perl_prefix}/lib/%{perl_version} \
    -Darchlib=%{perl_prefix}/lib/%{perl_version} \
    -Dsitelib=%{perl_prefix}/lib/%{perl_version} \
    -Dsitearch=%{perl_prefix}/lib/%{perl_version} \
    -Dvendorlib=%{perl_prefix}/lib/%{perl_version} \
    -Dvendorarch=%{perl_prefix}/lib/%{perl_version} \
    -Dscriptdir=%{perl_prefix}/bin \
    -Dlibperl=%{perl_soname} \
    -Darchname=%{_arch}-linux-thread-multi \
    -Dusethreads \
    -Duseithreads \
    -Duseshrplib \
    -Duse64bitint \
    -Duselargefiles \
    -Duseperlio \
    -Dd_semctl_semun \
    -Di_db \
    -Ui_ndbm \
    -Ui_gdbm \
    -Di_shadow \
    -Di_syslog \
    -Dman3ext=3pm \
    -Dinstallusrbinperl=n \
    -Ubincompat5005 \
    -Uversiononly \
    -Dpager='/usr/bin/less -isr' \
    -Dd_gethostent_r_proto \
    -Ud_endhostent_r_proto \
    -Ud_sethostent_r_proto \
    -Ud_endprotoent_r_proto \
    -Ud_setprotoent_r_proto \
    -Ud_endservent_r_proto \
    -Ud_setservent_r_proto \
    -Dusesitecustomize

make %{?_smp_mflags}

%install
make install DESTDIR=%{buildroot}

# PERCONA: unversioned libperl.so symlink next to the real SONAME file,
# same convenience link the distro ships in its CORE directory.
ln -sf %{perl_soname} %{buildroot}%{perl_prefix}/lib/%{perl_version}/CORE/libperl.so

%files
%license Copying Artistic
%{perl_prefix}

%changelog
* Tue Jul 28 2026 Percona Build/Release Team <eng-build@percona.com> - 5.26.3-1
- Initial /opt/percona-perl runtime for the Percona PostgreSQL binary
  tarball: distro-matched Perl (5.26.3 on EL8, 5.32.1 on EL9) built from
  upstream source with Rocky's ABI-relevant Configure options and all
  paths compiled to /opt/percona-perl, so the RPM-built plperl.so works
  with zero environment variables (tarball QA items 3 and 7).
