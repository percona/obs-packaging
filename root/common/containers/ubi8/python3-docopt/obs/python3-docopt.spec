%global python3_sitelib %(python3.9 -c "import sysconfig; print(sysconfig.get_path('purelib'))")

Name:           python39-docopt
Version:        0.6.2
Release:        3
Summary:        Pythonic argument parser using docstrings
License:        MIT
URL:            http://docopt.org
Source0:        docopt-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python39-pip
BuildRequires:  python39-setuptools
# Explicit dist provides since docopt 0.6.2 only creates egg-info
Provides:       python3dist(docopt) = 0.6.2
Provides:       python3.9dist(docopt) = 0.6.2

%description
docopt creates beautiful command-line interfaces. It is used by KIWI
(the OS image builder) for CLI argument parsing.

%prep
%setup -q -n docopt-%{version}

%install
python3 -m pip install --no-build-isolation --no-deps --prefix=/usr --root=%{buildroot} .

%files
%license LICENSE-MIT
%{python3_sitelib}/docopt*
%{python3_sitelib}/__pycache__/docopt*
