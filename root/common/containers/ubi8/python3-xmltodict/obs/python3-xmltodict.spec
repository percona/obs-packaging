%global python39_sitelib %(python3.9 -c "import sysconfig; print(sysconfig.get_path('purelib'))")

Name:           python39-xmltodict
Version:        0.14.2
Release:        1
Summary:        Makes working with XML feel like you are working with JSON
License:        MIT
URL:            https://github.com/martinblech/xmltodict
Source0:        xmltodict-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python39-setuptools

%description
xmltodict is a Python module that makes working with XML feel like
working with JSON. It is used by KIWI for XML processing.

%prep
%setup -q -n xmltodict-%{version}

%install
python3.9 setup.py install --root=%{buildroot} --prefix=/usr

%files
%license LICENSE
%{python39_sitelib}/xmltodict*
%{python39_sitelib}/__pycache__/xmltodict*
