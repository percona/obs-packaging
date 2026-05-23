Name:           perl-JSON
Version:        4.03
Release:        1%{?dist}
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
# Exclude provides for modules belonging to separate CPAN distributions
%global __provides_exclude %{?__provides_exclude:%__provides_exclude|}perl\(JSON::(Boolean|PP|PP::IncrParser)\)
# Exclude auto-requires for bundled internal modules (self-deps)
%global __requires_exclude %{?__requires_exclude:%__requires_exclude|}perl\(JSON::(backportPP|backportPP::Boolean|backportPP::Compat5005|backportPP::Compat5006)\)
# Explicit provides for bundled backportPP modules (auto-provide may be suppressed)
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
