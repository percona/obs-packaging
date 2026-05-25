%global python3_sitelib %(python3.9 -c "import sysconfig; print(sysconfig.get_path('purelib'))")

Name:           python39-tomli
Version:        2.4.1
Release:        1
Summary:        A lil' TOML parser
License:        MIT
URL:            https://github.com/hukkin/tomli
# Pre-built universal wheel to avoid flit_core bootstrap dependency
Source0:        tomli-%{version}-py3-none-any.whl
BuildArch:      noarch
BuildRequires:  python39-pip

%description
tomli is a Python library for parsing TOML. It is fully compatible
with TOML v1.0.0. Useful as a build-time dependency for packages that
need to read pyproject.toml on Python < 3.11.

%install
python3 -m pip install --no-deps \
    --prefix=/usr --root=%{buildroot} %{SOURCE0}

%files
%{python3_sitelib}/tomli*
