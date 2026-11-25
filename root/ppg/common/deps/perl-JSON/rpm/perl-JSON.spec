Name:           perl-JSON
Version:        4.03
Release:        %!{PKG_REVISION}%{?dist}
Summary:        Parse and convert to JSON (JavaScript Object Notation)
License:        GPL+ or Artistic
URL:            https://metacpan.org/release/JSON
Source0:        JSON-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  coreutils
BuildRequires:  make
BuildRequires:  perl-generators
BuildRequires:  perl-interpreter
BuildRequires:  perl(ExtUtils::MakeMaker)
BuildRequires:  perl(Test::More)
Requires:       perl(:MODULE_COMPAT_%(eval "`/usr/bin/perl -V:version`"; echo $version))
Requires:       perl(B)
Requires:       perl(Carp)
Requires:       perl(Encode)
Requires:       perl(Exporter)
Requires:       perl(Math::BigFloat)
Requires:       perl(Math::BigInt)
Requires:       perl(Scalar::Util)
Requires:       perl(bytes)
Requires:       perl(constant)
Requires:       perl(overload)
Requires:       perl(strict)
Requires:       perl(warnings)

%{?perl_default_filter}
# Auto-scanning by perl.prov/perl.req is disabled: all Requires and Provides
# are listed explicitly. The macros must expand to nothing so rpm skips the
# generator altogether. Do not point them at /bin/true: rpm writes the file
# list to the generator's stdin without ignoring SIGPIPE, so a generator that
# exits without reading it kills rpmbuild intermittently ("Broken pipe" after
# %%doc, seen on EL8 aarch64).
%global __perl_provides %{nil}
%global __perl_requires %{nil}
# Explicit provides: main module, backend marker, and bundled backportPP modules
Provides:       perl(JSON) = %{version}
Provides:       perl(JSON::Backend::PP)
Provides:       perl(JSON::backportPP)
Provides:       perl(JSON::backportPP::Boolean)
Provides:       perl(JSON::backportPP::Compat5005)
Provides:       perl(JSON::backportPP::Compat5006)

%description
This module converts between JSON (JavaScript Object Notation) and Perl
data structures. For JSON, see http://www.crockford.com/JSON/.

%prep
%autosetup -n JSON-%{version}

%build
/usr/bin/perl Makefile.PL INSTALLDIRS=vendor NO_PACKLIST=1 NO_PERLLOCAL=1
%{make_build}

%install
%{make_install}
%{_fixperms} %{buildroot}/*

%check
make test

%files
%doc Changes
%{perl_vendorlib}/*
%{_mandir}/man3/*

%changelog
* Thu May 21 2026 Percona Development <info@percona.com> - 4.03-1
- Initial packaging of perl-JSON for Percona OBS
