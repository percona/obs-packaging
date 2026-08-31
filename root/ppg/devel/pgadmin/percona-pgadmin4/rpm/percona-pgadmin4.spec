# Ported from openSUSE's pgadmin4.spec (Factory) to EL9 + python3.12 for UBI-9.
# Bumps: change <param name="revision"> in obs/_service (REL-<major>_<minor>) and
# re-check web/requirements.txt against the python3-* packages of this project.
%global debug_package %{nil}
%global __ospython %{_bindir}/python3.12
%global python3_pkgprefix python3.12
%global python3_buildversion 3.12
%global __requires_exclude ^python3\\.12dist
%global python3_sitelib %(%{__ospython} -Esc "import sysconfig; print(sysconfig.get_path('purelib', vars={'platbase': '%{_prefix}', 'base': '%{_prefix}'}))")
%global pgadmin_dir %{python3_sitelib}/pgadmin4
%global pgadmin_user pgadmin
%global pgadmin_data %{_sharedstatedir}/pgadmin
%global pgadmin_log %{_localstatedir}/log/pgadmin
%global pgadmin_etc %{_sysconfdir}/pgadmin

Name:           percona-pgadmin4
Version:        1.0.0
Release:        1%{?dist}
Summary:        Management tool for PostgreSQL (pgAdmin 4, server mode)
License:        PostgreSQL
URL:            https://www.pgadmin.org
Vendor:         Percona, LLC
Packager:       Percona Development Team <https://jira.percona.com>

Source0:        %{name}-%{version}.tar.gz
Source1:        config_distro.py
Source2:        run_pgadmin.py
Source3:        gunicorn_config.py
Source4:        percona-pgadmin4-gunicorn
Source5:        percona-pgadmin4.service
Source6:        percona-pgadmin4.sysusers
Source7:        percona-pgadmin4.tmpfiles
Source8:        percona-pgadmin4-httpd.conf
Source9:        percona-pgadmin4-setup-web
Source20:       package-lock.json
# SourceNNNNN: npm tarballs vendored by the node_modules service (offset 10000)
Source100:      node_modules.spec.inc
%include        %{_sourcedir}/node_modules.spec.inc

# Help > Online Help opens the upstream documentation for the running version
# (no local Sphinx build; -doc ships the rst sources).
Patch1:         0001-help-menu-online-docs.patch
# openSUSE: do not fail at import time when the cloud SDKs are missing
Patch2:         0002-make-cloud-packages-optional.patch
# openSUSE: create data directories with os.makedirs (parents) instead of os.mkdir
Patch3:         0003-use-os-makedirs.patch

BuildArch:      noarch

BuildRequires:  python%{python3_buildversion}-devel
BuildRequires:  python%{python3_buildversion}-pip
BuildRequires:  python%{python3_buildversion}-setuptools
BuildRequires:  python%{python3_buildversion}-wheel
BuildRequires:  local-npm-registry
# The epoch is mandatory: EL9's nodejs carries Epoch 1, so a bare ">= 20"
# is satisfied by the distro's 1:16.20.2. Node >= 20 comes from our own
# common:deps:build nodejs package (CS9 nodejs:22 module port).
BuildRequires:  nodejs >= 1:22
BuildRequires:  npm
BuildRequires:  systemd-rpm-macros
# runtime stack, needed for the %%check import (cloud SDKs — boto3, azure-*, google-* — are
# not packaged; Patch2 makes the cloud deployment module tolerate their absence)
BuildRequires:  %{python3_pkgprefix}-flask
BuildRequires:  %{python3_pkgprefix}-flask-babel
BuildRequires:  %{python3_pkgprefix}-flask-compress
BuildRequires:  %{python3_pkgprefix}-flask-login
BuildRequires:  %{python3_pkgprefix}-flask-mail
BuildRequires:  %{python3_pkgprefix}-flask-migrate
BuildRequires:  %{python3_pkgprefix}-flask-paranoid
BuildRequires:  %{python3_pkgprefix}-flask-security-too
BuildRequires:  %{python3_pkgprefix}-flask-socketio
BuildRequires:  %{python3_pkgprefix}-flask-sqlalchemy
BuildRequires:  %{python3_pkgprefix}-flask-wtf
BuildRequires:  %{python3_pkgprefix}-wtforms
BuildRequires:  %{python3_pkgprefix}-werkzeug
BuildRequires:  %{python3_pkgprefix}-sqlalchemy
BuildRequires:  %{python3_pkgprefix}-sqlparse
BuildRequires:  %{python3_pkgprefix}-psycopg
BuildRequires:  %{python3_pkgprefix}-psycopg-c
BuildRequires:  %{python3_pkgprefix}-libpass
BuildRequires:  %{python3_pkgprefix}-bcrypt
BuildRequires:  %{python3_pkgprefix}-authlib
BuildRequires:  %{python3_pkgprefix}-pyotp
BuildRequires:  %{python3_pkgprefix}-qrcode
BuildRequires:  %{python3_pkgprefix}-ldap3
BuildRequires:  %{python3_pkgprefix}-gssapi
BuildRequires:  %{python3_pkgprefix}-sshtunnel
BuildRequires:  %{python3_pkgprefix}-paramiko
BuildRequires:  %{python3_pkgprefix}-keyring
BuildRequires:  %{python3_pkgprefix}-typer
BuildRequires:  %{python3_pkgprefix}-typing-extensions
BuildRequires:  %{python3_pkgprefix}-jsonformatter
BuildRequires:  %{python3_pkgprefix}-libgravatar
BuildRequires:  %{python3_pkgprefix}-user-agents
BuildRequires:  %{python3_pkgprefix}-pytz
BuildRequires:  %{python3_pkgprefix}-certifi
BuildRequires:  %{python3_pkgprefix}-dateutil
BuildRequires:  %{python3_pkgprefix}-psutil
BuildRequires:  python%{python3_buildversion}-cryptography
BuildRequires:  python%{python3_buildversion}-urllib3

Requires:       %{python3_pkgprefix}-flask
Requires:       %{python3_pkgprefix}-flask-babel
Requires:       %{python3_pkgprefix}-flask-compress
Requires:       %{python3_pkgprefix}-flask-login
Requires:       %{python3_pkgprefix}-flask-mail
Requires:       %{python3_pkgprefix}-flask-migrate
Requires:       %{python3_pkgprefix}-flask-paranoid
Requires:       %{python3_pkgprefix}-flask-security-too
Requires:       %{python3_pkgprefix}-flask-socketio
Requires:       %{python3_pkgprefix}-flask-sqlalchemy
Requires:       %{python3_pkgprefix}-flask-wtf
Requires:       %{python3_pkgprefix}-wtforms
Requires:       %{python3_pkgprefix}-werkzeug
Requires:       %{python3_pkgprefix}-sqlalchemy
Requires:       %{python3_pkgprefix}-sqlparse
Requires:       %{python3_pkgprefix}-psycopg
Requires:       %{python3_pkgprefix}-psycopg-c
Requires:       %{python3_pkgprefix}-libpass
Requires:       %{python3_pkgprefix}-bcrypt
Requires:       %{python3_pkgprefix}-authlib
Requires:       %{python3_pkgprefix}-pyotp
Requires:       %{python3_pkgprefix}-qrcode
Requires:       %{python3_pkgprefix}-ldap3
Requires:       %{python3_pkgprefix}-gssapi
Requires:       %{python3_pkgprefix}-sshtunnel
Requires:       %{python3_pkgprefix}-paramiko
Requires:       %{python3_pkgprefix}-keyring
Requires:       %{python3_pkgprefix}-typer
Requires:       %{python3_pkgprefix}-typing-extensions
Requires:       %{python3_pkgprefix}-jsonformatter
Requires:       %{python3_pkgprefix}-libgravatar
Requires:       %{python3_pkgprefix}-user-agents
Requires:       %{python3_pkgprefix}-pytz
Requires:       %{python3_pkgprefix}-certifi
Requires:       %{python3_pkgprefix}-dateutil
Requires:       %{python3_pkgprefix}-psutil
Requires:       python%{python3_buildversion}-cryptography
Requires:       python%{python3_buildversion}-setuptools
Requires:       python%{python3_buildversion}-urllib3
Requires(pre):  shadow-utils
Provides:       pgadmin4 = %{version}-%{release}
Suggests:       %{name}-doc

%description
pgAdmin 4 is the leading open source management tool for PostgreSQL. This
package installs the web application in server mode under
%{pgadmin_dir}, with distribution defaults in config_distro.py (data in
%{pgadmin_data}, logs in %{pgadmin_log}, site overrides in
%{pgadmin_etc}/config_system.py). Any setting can also be overridden with a
PGADMIN_CONFIG_<SETTING> environment variable. Install %{name}-gunicorn to run
it stand-alone (containers, systemd) or %{name}-httpd to serve it from Apache.

%package gunicorn
Summary:        Run pgAdmin 4 stand-alone under gunicorn
Requires:       %{name} = %{version}-%{release}
Requires:       %{python3_pkgprefix}-gunicorn
%{?systemd_requires}

%description gunicorn
Launcher script (%{_bindir}/percona-pgadmin4-gunicorn) and systemd unit that
serve pgAdmin 4 with gunicorn. Configured through the environment
(PGADMIN_LISTEN_ADDRESS/PORT, PGADMIN_ENABLE_TLS, PGADMIN_DEFAULT_EMAIL/PASSWORD,
PGADMIN_CONFIG_<SETTING>); this is the runtime used by container images. The
service is not enabled by default.

%package httpd
Summary:        Serve pgAdmin 4 from Apache httpd with mod_wsgi
Requires:       %{name} = %{version}-%{release}
Requires:       httpd
Requires:       python%{python3_buildversion}-mod_wsgi

%description httpd
Apache configuration (/pgadmin4 via mod_wsgi, one daemon process with 25
threads running as the pgadmin user) and the percona-pgadmin4-setup-web helper
that creates the configuration database, applies SELinux settings and
restarts httpd.

%package doc
Summary:        Documentation sources for pgAdmin 4
BuildArch:      noarch

%description doc
The reStructuredText sources of the pgAdmin 4 documentation
(%{_docdir}/%{name}/en_US). The rendered manual for the installed release is
online at https://www.pgadmin.org/docs/pgadmin4/; the application's Help menu
links there.

%prep
%autosetup -p1 -n %{name}-%{version}

# The git tag is exported without .git: record the upstream commit the way
# pkg/src/build.sh does. (The "git:hash" npm script is never invoked -- %%build
# runs npx webpack directly, not the bundle/git:hash scripts -- so it is left
# alone rather than rewritten with a sed that cannot safely match upstream's
# escaped-quote value.)
awk '/^commit:/ {print $2}' %{_sourcedir}/%{name}.obsinfo > web/commit_hash
# Upstream pins Yarn via "packageManager"; npm refuses to run with it set.
sed -i -z 's/,\n *"packageManager": "[^"]*"//' web/package.json
# Executable bits and shebangs on files that end up in site-packages
chmod -x web/pgadmin/misc/cloud/*.py web/pgadmin/misc/cloud/utils/*.py 2>/dev/null || :
sed -i '1{/^#!/d}' web/pgadmin/misc/cloud/*.py web/pgadmin/misc/cloud/utils/*.py 2>/dev/null || :
find web/pgadmin -name '*.py' -perm /111 -exec chmod -x {} +
# Vendored npm dependencies: package-lock.json + tarballs served by local-npm-registry
cp %{SOURCE20} web/package-lock.json
# npm resolves dist-tags ("latest") against registry packument metadata that
# local-npm-registry's offline packuments do not carry (ETARGET at %%build):
# pin the one dist-tag range in package.json to the version the lockfile chose.
fa_ver=$(%{__ospython} -c "import json; print(json.load(open('web/package-lock.json'))['packages']['node_modules/@fortawesome/fontawesome-free']['version'])")
sed -i "s|\"@fortawesome/fontawesome-free\": \"latest\"|\"@fortawesome/fontawesome-free\": \"${fa_ver}\"|" web/package.json
grep -q "\"@fortawesome/fontawesome-free\": \"${fa_ver}\"" web/package.json
# react-data-grid is a git dependency (github…#<commit>): npm fetches git deps
# from codeload.github.com directly, bypassing the registry, and the build VM
# has no network (ENOTFOUND at %%build). The node_modules service vendors the
# pinned commit as react-data-grid-<commit>.tgz (git archive, package/ prefix,
# i.e. a valid npm tarball): rewrite the dependency to that file in both
# package.json and the lockfile. The stale git integrity hash is dropped — npm
# recomputes it for file: tarballs.
rdg_tgz=$(ls %{_sourcedir}/react-data-grid-*.tgz)
test -f "${rdg_tgz}"
%{__ospython} - "${rdg_tgz}" <<'PYEOF'
import json
import sys

tgz = "file:" + sys.argv[1]

with open("web/package.json") as f:
    pj = json.load(f)
assert "react-data-grid" in pj["dependencies"]
pj["dependencies"]["react-data-grid"] = tgz
with open("web/package.json", "w") as f:
    json.dump(pj, f, indent=2)

with open("web/package-lock.json") as f:
    lk = json.load(f)
lk["packages"][""]["dependencies"]["react-data-grid"] = tgz
entry = lk["packages"]["node_modules/react-data-grid"]
entry["resolved"] = tgz
entry.pop("integrity", None)
with open("web/package-lock.json", "w") as f:
    json.dump(lk, f, indent=2)
PYEOF

%build
# Frontend
pushd web
local-npm-registry %{_sourcedir} install --legacy-peer-deps --ignore-scripts --no-audit --no-fund
NODE_ENV=production NODE_OPTIONS=--max-old-space-size=3072 npx webpack --config webpack.config.js
rm -rf node_modules
popd

# Wheel (upstream's pip packaging helper; produces pgadmin4-<ver>-py3-none-any.whl).
# pkg/pip/setup_pip.py must run from a pip-build/ staging directory at the tree
# root -- it reads ../requirements.txt and ../web/ relative to its own cwd, and
# packages "pgadmin4" as a copy of web/ living next to that cwd (see
# pkg/pip/build.sh, which drives it the same way). build.sh itself needs .git,
# yarn and syft, none of which are available/needed here, so its file
# operations are reproduced directly instead of invoking the script:
#   build.sh:44-58  stage web/ (minus regression/) as pip-build/pgadmin4/ -- our
#                   cp -a already picks up commit_hash (build.sh:65-67) and the
#                   webpack-generated pgadmin/static/js/generated/* files
#                   (build.sh:69-73), since both already exist on disk here,
#                   unlike a bare git checkout where git ls-files would miss them
#   build.sh:75-89  also stages docs/ into the wheel -- skipped: the -doc
#                   subpackage already ships docs/en_US and duplicating ~39 MB
#                   of rst inside %{pgadmin_dir} is pointless
#   build.sh:92-97  copy LICENSE/README.md from the tree root into pip-build/pgadmin4/
#   build.sh:100-105 SBOM generation via syft -- skipped: not available/needed
#   build.sh:108-110 write a stub config_distro.py -- skipped: %%install installs
#                   our own config_distro.py over whatever setup_pip.py packaged
#   build.sh:113-114 MANIFEST.in -- needed, so setuptools includes the non-.py
#                   package data (html/css/js/rst) in the wheel
mkdir -p pip-build/pgadmin4
cp -a web/. pip-build/pgadmin4/
rm -rf pip-build/pgadmin4/regression
cp -a LICENSE README.md pip-build/pgadmin4/
echo 'recursive-include pgadmin4 *' > pip-build/MANIFEST.in
pushd pip-build
%{__ospython} ../pkg/pip/setup_pip.py bdist_wheel
popd

%install
%{__ospython} -m pip install --root %{buildroot} --no-deps --no-index --no-warn-script-location \
    pip-build/dist/pgadmin4-*.whl

# The launcher and httpd conf hard-code the site-packages path: assert it.
test "%{python3_sitelib}" = "%{_prefix}/lib/python%{python3_buildversion}/site-packages"

# distribution config + gunicorn entry points
install -m 0644 %{SOURCE1} %{buildroot}%{pgadmin_dir}/config_distro.py
install -m 0644 %{SOURCE2} %{buildroot}%{pgadmin_dir}/run_pgadmin.py
install -m 0644 %{SOURCE3} %{buildroot}%{pgadmin_dir}/gunicorn_config.py

# The wheel installs two console scripts (pkg/pip/setup_pip.py entry_points):
# pgadmin4 (pgadmin4.pgAdmin4:main) and pgadmin4-cli (pgadmin4.setup:main); both
# are packaged below in %%files.
# Data, log and configuration directories
install -d -m 0750 %{buildroot}%{pgadmin_data}
install -d -m 0755 %{buildroot}%{pgadmin_data}/storage
install -d -m 0700 %{buildroot}%{pgadmin_data}/sessions
install -d -m 0750 %{buildroot}%{pgadmin_log}
install -d -m 0750 %{buildroot}%{pgadmin_etc}
cat > %{buildroot}%{pgadmin_etc}/config_system.py <<'EOF'
# Site-specific pgAdmin 4 settings (highest precedence; imported after config_distro.py
# and config_local.py). Any setting from config.py may be set here, e.g.
#   DEFAULT_SERVER = '0.0.0.0'
#   MAX_LOGIN_ATTEMPTS = 3
EOF

# users and runtime dirs
install -D -m 0644 %{SOURCE6} %{buildroot}%{_sysusersdir}/%{name}.conf
install -D -m 0644 %{SOURCE7} %{buildroot}%{_tmpfilesdir}/%{name}.conf

# -gunicorn
install -D -m 0755 %{SOURCE4} %{buildroot}%{_bindir}/percona-pgadmin4-gunicorn
install -D -m 0644 %{SOURCE5} %{buildroot}%{_unitdir}/%{name}.service
install -d -m 0755 %{buildroot}/run/pgadmin4

# -httpd
install -D -m 0644 %{SOURCE8} %{buildroot}%{_sysconfdir}/httpd/conf.d/%{name}.conf
install -D -m 0755 %{SOURCE9} %{buildroot}%{_bindir}/percona-pgadmin4-setup-web

# -doc: rst sources (drop build tooling and editor artefacts)
install -d -m 0755 %{buildroot}%{_docdir}/%{name}
cp -a docs/en_US %{buildroot}%{_docdir}/%{name}/en_US
rm -f %{buildroot}%{_docdir}/%{name}/en_US/Makefile.sphinx \
      %{buildroot}%{_docdir}/%{name}/en_US/conf.py \
      %{buildroot}%{_docdir}/%{name}/en_US/build_code_snippet.py \
      %{buildroot}%{_docdir}/%{name}/en_US/.gitignore
find %{buildroot}%{_docdir}/%{name}/en_US -name '*.excalidraw' -delete
# LICENSE/README.md are not installed separately under %{_docdir}: both are
# already covered by %%license/%%doc from the tree root in %%files (a second copy
# under %{_docdir}/%{name}/ would match no %%files entry and fail as unpackaged).

# byte-compile with the interpreter that runs the app
%{__ospython} -m compileall -q -s %{buildroot} -p / %{buildroot}%{pgadmin_dir}

%check
PYTHONPATH=%{buildroot}%{pgadmin_dir} PGADMIN_CONFIG_HELP_PATH=/nonexistent \
    %{__ospython} -P -c "import config, config_distro; assert config.SERVER_MODE is True; assert config.HELP_PATH == '/nonexistent'"

%pre
%sysusers_create_compat %{SOURCE6}

%post gunicorn
%systemd_post %{name}.service
%tmpfiles_create %{_tmpfilesdir}/%{name}.conf

%preun gunicorn
%systemd_preun %{name}.service

%postun gunicorn
%systemd_postun_with_restart %{name}.service

%files
%license LICENSE
%doc README.md
%{pgadmin_dir}/
%{python3_sitelib}/pgadmin4-*.dist-info/
%{_bindir}/pgadmin4
%{_bindir}/pgadmin4-cli
%{_sysusersdir}/%{name}.conf
%dir %attr(0750,%{pgadmin_user},%{pgadmin_user}) %{pgadmin_data}
%dir %attr(0755,%{pgadmin_user},%{pgadmin_user}) %{pgadmin_data}/storage
%dir %attr(0700,%{pgadmin_user},%{pgadmin_user}) %{pgadmin_data}/sessions
%dir %attr(0750,%{pgadmin_user},%{pgadmin_user}) %{pgadmin_log}
%dir %attr(0750,root,%{pgadmin_user}) %{pgadmin_etc}
%config(noreplace) %attr(0640,root,%{pgadmin_user}) %{pgadmin_etc}/config_system.py

%files gunicorn
%{_bindir}/percona-pgadmin4-gunicorn
%{_unitdir}/%{name}.service
%{_tmpfilesdir}/%{name}.conf
%dir %attr(0755,%{pgadmin_user},%{pgadmin_user}) /run/pgadmin4

%files httpd
%config(noreplace) %{_sysconfdir}/httpd/conf.d/%{name}.conf
%{_bindir}/percona-pgadmin4-setup-web

%files doc
%docdir %{_docdir}/%{name}/en_US
%{_docdir}/%{name}/en_US/

%changelog
* Fri Aug 28 2026 Percona Development Team <https://jira.percona.com> - 1.0.0-1
- Initial percona-pgadmin4 package (pgAdmin 4, server mode) for UBI-9, ported
  from openSUSE's pgadmin4.spec: gunicorn and httpd/mod_wsgi runtimes, rst docs.
