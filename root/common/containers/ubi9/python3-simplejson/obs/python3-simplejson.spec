%global python3_platlib %(%{__python3} -c "import sysconfig; print(sysconfig.get_path('platlib'))")

Name:           python3-simplejson
Version:        3.19.3
Release:        1
Summary:        Simple, fast, extensible JSON encoder/decoder for Python
License:        MIT
URL:            https://github.com/simplejson/simplejson
Source0:        simplejson-%{version}.tar.gz
BuildRequires:  gcc
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools

%description
simplejson is a simple, fast, complete, correct and extensible JSON
encoder and decoder for Python. It is used by KIWI as a JSON library.

%prep
%setup -q -n simplejson-%{version}

%build
python3 setup.py build

%install
python3 setup.py install --root=%{buildroot} --prefix=/usr

%files
%license LICENSE.txt
%{python3_platlib}/simplejson*
