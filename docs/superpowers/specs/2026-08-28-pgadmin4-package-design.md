# pgAdmin 4 on UBI-9 — sub-project 4: the `percona-pgadmin4` package design

**Date:** 2026-08-28
**Status:** approved in brainstorming, awaiting spec review
**Parent:** `2026-08-26-pgadmin4-tooling-design.md` (decomposition §4); depends on SP2
(`local-npm-registry`) and SP3 (`2026-08-26-pgadmin4-py312-stack-design.md`).
**Scope of this document:** the `percona-pgadmin4` source package in `ppg:devel:pgadmin`
(UBI 9 only), the SP3 stack changes needed to move from `REL-9_9` to `REL-9_17`, and the
package's shape as the basis of a pgAdmin container image (SP5, separate spec).

## 1. Goal

Package pgAdmin 4 **9.17** as RPMs built from the git tag with the `node_modules` service
chain from SP1 and the Python 3.12 stack from SP3, such that (a) a UBI-9 host can run it
behind Apache httpd + mod_wsgi, (b) a UBI-9 container image (SP5) can run it under
gunicorn exactly like upstream's official image, and (c) configuration works through
`/etc/pgadmin/config_system.py` on hosts and `PGADMIN_CONFIG_*` environment variables in
containers. No `percona_obs` code changes.

## 2. Findings that shaped the design

### 2.1 Upstream and openSUSE packaging (facts checked 2026-08-27/28)

- **Release artefacts:** `pkg/src/build.sh` builds `pgadmin4-<ver>.tar.gz` (the git files
  plus `web/commit_hash`, with the `git:hash` npm script neutralised) and a separate
  `pgadmin4-<ver>-docs.tar.gz` (Sphinx HTML). Only the source tarball + `.asc` are
  published, and the download server keeps just the last seven releases (v9.11–v9.17 on
  2026-08-27) — **9.9 is no longer downloadable**. Building from the git tag via `obs_scm`
  (SP1 decision) is what makes any given version reproducible.
- **openSUSE Factory `pgadmin4` 9.17:** builds from the tarball; `local-npm-registry
  %{_sourcedir} install --legacy-peer-deps --ignore-scripts` in `web/`, `npx eslint` +
  `npx webpack` (production), wheel via `pkg/pip/setup_pip.py bdist_wheel` with a
  `config_distro.py` written in `%build`, `%pyproject_install`; subpackages `doc`
  (copies `docs/*` — **the reStructuredText sources, no HTML**; its `HTML_HELP` setting is
  not a pgAdmin option, so the in-app help link is dead there), `web-uwsgi`, `desktop`,
  `system-user-pgadmin` (sysusers), optional `cloud`. Patches: `use-os-makedirs`,
  `make-cloud-packages-optional`, `fix-reproducible-builds`, `package_git_local`
  (pins `react-data-grid` to a published beta instead of the git URL), two stale ones.
  Runtime: systemd unit running `pgAdmin4.py` (Flask's built-in server) as user `pgadmin`,
  httpd `conf.d` snippet behind `<IfDefine PGADMIN>`, tmpfiles `/run/pgadmin4`, dirs
  `/var/lib/pgadmin{,/storage,/sessions}`, `/var/log/pgadmin`, `/etc/pgadmin/config_system.py`.
- **Upstream RHEL RPMs** (`pkg/redhat/build.sh`): a venv under `/usr/pgadmin4` (rejected
  by the SP1 decision), `pgadmin4-web` = httpd conf (`WSGIDaemonProcess pgadmin
  processes=1 threads=25`, `WSGIScriptAlias /pgadmin4 …/pgAdmin4.wsgi`) +
  `setup-web.sh` (runs `setup.py setup-db`, chowns dirs to `apache`, sets SELinux booleans
  `httpd_tmp_exec`, `httpd_can_network_connect`, `httpd_can_network_connect_db` and
  fcontexts `httpd_var_lib_t` for `/var/lib/pgadmin`, `httpd_log_t` for `/var/log/pgadmin`,
  enables httpd).
- **Upstream container** (`pkg/docker/`): runs **gunicorn** (`-w 1 --threads 25
  --bind [::]:80|443 --timeout <session expiry> --access-logfile - -c gunicorn_config.py
  run_pgadmin:app`, TLS via `/certs/server.{key,cert}` when `PGADMIN_ENABLE_TLS`),
  `run_pgadmin.py` = `builtins.SERVER_MODE = True; from pgAdmin4 import app`,
  `gunicorn_config.py` (JSON logging to stdout when `JSON_LOGGER`), entrypoint that
  appends every `PGADMIN_CONFIG_<NAME>=<value>` env var as `<NAME> = <value>` to
  `config_distro.py` (`true`/`false` normalised to Python), maps
  `PGADMIN_DEFAULT_EMAIL/PASSWORD` → pgAdmin's `PGADMIN_SETUP_EMAIL/PASSWORD` for
  `setup-db`, optional `servers.json` import, same `/var/lib/pgadmin` data dir.
- **pgAdmin internals (9.17):** `web/config.py` in `SERVER_MODE` uses `DATA_DIR
  /var/lib/pgadmin`, `LOG_FILE /var/log/pgadmin/pgadmin4.log`, `SQLITE_PATH
  <DATA_DIR>/pgadmin4.db`; `HELP_PATH` is a Flask *static folder* (a local directory —
  it cannot be a URL); the Help menu's "Online Help" entry is `url_for('help.static',
  filename='index.html')`; `DEFAULT_BINARY_PATHS` keys `pg`, `pg-13`…`pg-18`,
  `ppas*`; `config.py` imports `pgadmin.utils` and, via `evaluate_config`, `keyring`;
  `setup-db` is non-interactive when `PGADMIN_SETUP_EMAIL` and `PGADMIN_SETUP_PASSWORD`
  are set; `web/package.json` has `"packageManager": "yarn@4.15.0"` (must go for npm) and
  the `bundle` script ends with `git:hash`. `python3.12-mod_wsgi` (UBI-9 AppStream 4.9.4)
  installs `/usr/lib64/httpd/modules/mod_wsgi_python3.so` and
  `/etc/httpd/conf.modules.d/10-wsgi-python3.conf` (no `LoadModule` needed).

### 2.2 REL-9_9 → REL-9_17 closure delta (uv, Python 3.12, cloud extras excluded)

83 packages vs 80. **New:** `annotated-doc` 0.0.5 (typer), `certifi` 2026.6.17 (direct
requirement), `joserfc` 1.7.4 (Authlib 1.7; needs `cryptography >= 45.0.1`), `libpass`
1.9.3 (Flask-Security-Too 5.8; a passlib fork that installs the **`passlib`** module).
**Gone:** `importlib-resources`. **Bumped:** Authlib 1.7.2, Flask-Security-Too 5.8.2,
Flask-SocketIO 5.6.1, Flask-WTF 1.3.0, gssapi 1.11.1 (pins `Cython == 3.2.4`),
psycopg/psycopg-c 3.3.4, pytz 2026.3.post1, typer 0.26.8, and — reused from RHEL, not
built — setuptools 83, urllib3 2.7, psutil 7.2. (cryptography 49 was originally in the
reused-from-RHEL list at version 41; during execution it became a stack package at 49.0.0
— see §9 Outcomes.)

### 2.3 Sphinx cost (rejected option, kept for the record)

Building the HTML docs needs Sphinx on Python 3.12 (docs `conf.py` imports pgAdmin's
`config`): 13 pure-Python build-only packages (sphinx 9.1, docutils, alabaster, imagesize,
roman-numerals, snowballstemmer, six `sphinxcontrib-*` helpers, `sphinxcontrib-youtube`).

## 3. Decisions taken during brainstorming

| Topic | Decision |
|---|---|
| Version | **REL-9_17** (current). SP3 packages are bumped first (§6). Monthly bumps become routine follow-ups. |
| Docs / help | **openSUSE-style:** `-doc` ships the `.rst` sources; a patch points the Help menu's "Online Help" at `https://www.pgadmin.org/docs/pgadmin4/<release>.<revision>/`; `HELP_PATH` points at the `-doc` directory so the static route serves something. No Sphinx stack. |
| Primary runtime | **Containers (SP5): gunicorn**, like upstream's image. **Hosts: httpd + mod_wsgi** (upstream's RHEL packaging) or the systemd unit — which now runs **gunicorn**, not Flask's dev server (refinement of the earlier "systemd unit shipped disabled" idea: same shipped-disabled unit, production-grade server). |
| Package split (container-driven) | `percona-pgadmin4` (code, user, dirs, config; no web-server dependency) + `percona-pgadmin4-gunicorn` (launcher, gunicorn config, systemd unit; `Requires: python3.12-gunicorn`) + `percona-pgadmin4-httpd` (conf.d snippet, setup helper; `Requires: httpd, python3.12-mod_wsgi`) + `percona-pgadmin4-doc`. An image installs base + `-gunicorn`; a host installs base + `-httpd` or `-gunicorn`. |
| Configuration | `config_distro.py` (Percona defaults, §5.3) **also applies `PGADMIN_CONFIG_<NAME>` environment variables at import time** (upstream's container semantics, done in Python so it works for services too); `/etc/pgadmin/config_system.py` (`%config(noreplace)`) for host overrides. |
| Authlib | **Stay on 1.6.12** (originally: no `joserfc`, which would need cryptography ≥ 45 — RHEL had 41). pgAdmin's `Authlib==1.7.*` pin is relaxed like its urllib3/setuptools pins. **Amended during execution (§9):** cryptography is now a stack package at 49.0.0, so the joserfc blocker is gone — the Authlib 1.7 + joserfc bump is now possible and deferred as a follow-up. authlib additionally gained an explicit `Requires: python3.12-requests` (its flask integration imports it unconditionally; found by the smoke test). |
| passlib → libpass | Flask-Security-Too 5.8 requires `libpass`, which installs the `passlib` module: package `python3-libpass` with `Provides: %{python3_pkgprefix}-passlib` and `Conflicts: %{python3_pkgprefix}-passlib < 1.9`, and remove `python3-passlib`. |
| Frontend lockfile drift | SP1 ruling stands: `package-lock.json` is generated at sync time; npm's resolution drift from upstream's `yarn.lock` is accepted (bounded by the per-commit service cache). |
| Not shipped | `-desktop`, `-uwsgi`, cloud support (azure/boto3/google), Debian, HTML docs. (This row originally also listed "upgrading cryptography" — overturned during execution, see §9.) |
| Names | `Name: percona-pgadmin4`, `Provides: pgadmin4 = %{version}`; user/group `pgadmin`; URL path `/pgadmin4`; unit `percona-pgadmin4.service`. |

## 4. Package layout

```
root/ppg/devel/pgadmin/percona-pgadmin4/
├── package.yaml
├── obs/_service
└── rpm/
    ├── percona-pgadmin4.spec
    ├── config_distro.py                     # Percona defaults + PGADMIN_CONFIG_* env overrides
    ├── run_pgadmin.py                       # WSGI entry for gunicorn (SERVER_MODE, app)
    ├── gunicorn_config.py                   # upstream's, adapted (stdout logging, JSON option)
    ├── percona-pgadmin4-gunicorn            # launcher script (/usr/bin)
    ├── percona-pgadmin4.service             # systemd unit → the launcher, user pgadmin
    ├── percona-pgadmin4.sysusers            # u pgadmin - "pgAdmin 4" /var/lib/pgadmin
    ├── percona-pgadmin4.tmpfiles            # d /run/pgadmin4 0755 pgadmin pgadmin -
    ├── percona-pgadmin4-httpd.conf          # /etc/httpd/conf.d snippet
    ├── percona-pgadmin4-setup-web           # setup-db + SELinux + httpd helper (/usr/bin)
    ├── 0001-help-menu-online-docs.patch
    ├── 0002-make-cloud-packages-optional.patch   # from openSUSE
    └── 0003-use-os-makedirs.patch                # from openSUSE
```

### 4.1 `obs/_service`

```xml
<services>
  <service name="obs_scm">
    <param name="url">https://github.com/pgadmin-org/pgadmin4.git</param>
    <param name="scm">git</param>
    <param name="revision">REL-9_17</param>
    <param name="versionformat">@PARENT_TAG@</param>
    <param name="versionrewrite-pattern">REL-(\d+)_(\d+)</param>
    <param name="versionrewrite-replacement">\1.\2</param>
    <param name="filename">percona-pgadmin4</param>
  </service>
  <service name="npm_lockfile" mode="manual">
    <param name="archive">percona-pgadmin4-*.obscpio</param>
    <param name="subdir">web</param>
    <param name="npm-flags">--legacy-peer-deps</param>
  </service>
  <service name="node_modules" mode="manual">
    <param name="cpio">node_modules.obscpio</param>
    <param name="output">node_modules.spec.inc</param>
    <param name="source-offset">10000</param>
  </service>
  <service mode="buildtime" name="tar"/>
  <service mode="buildtime" name="recompress"><param name="file">*.tar</param><param name="compression">gz</param></service>
  <service mode="buildtime" name="set_version"/>
</services>
```
The exact `archive`/`npm-flags` parameter values are those SP1 verified end to end against
`REL-9_9`; the plan re-runs the dry run at `REL-9_17` before anything is pushed. Uploaded
set: `percona-pgadmin4-9.17.obscpio` + `.obsinfo`, `package-lock.json`,
`node_modules.obscpio` (~210 MB), `node_modules.spec.inc` — the last three are
drift-tolerant in the branch content check (SP1).

### 4.2 `package.yaml`

Title/description only (UBI_9-only project, no `build:` flags); description states the
four subpackages and that the image (SP5) consumes base + `-gunicorn`.

## 5. The spec

### 5.1 Header

`Name: percona-pgadmin4`, `Version: 1.0.0` (placeholder rewritten by `set_version` from
the obsinfo — repo convention for `obs_scm` packages), `Release: 1%{?dist}`,
`Summary: pgAdmin 4 — management tool for PostgreSQL (server mode)`, `License: PostgreSQL`,
`URL: https://www.pgadmin.org`, `BuildArch: noarch`, `Provides: pgadmin4 = %{version}`.
`Source0: percona-pgadmin4-%{version}.tar.gz`; `Source1..12` the files in `rpm/`;
`Source20: package-lock.json`; `Source100: node_modules.spec.inc`;
`%include %{_sourcedir}/node_modules.spec.inc` (brings the `Source10000+` npm tarballs
that OBS unpacks from `node_modules.obscpio` into `%{_sourcedir}`).

The same `python3.12` preamble as the SP3 template (`__ospython`, `python3_pkgprefix`,
`python3_sitelib`) so `%{python3_pkgprefix}-<name>` resolves the stack by name.

**BuildRequires:** `python%{python3_buildversion}-devel/-pip/-setuptools/-wheel`,
`local-npm-registry`, `nodejs >= 20`, `npm`, `systemd-rpm-macros`, plus every runtime
`Requires` below (so the `%check` import works). **Requires** (base package):
`%{python3_pkgprefix}-{authlib,bcrypt,certifi,flask,flask-babel,flask-compress,flask-login,
flask-mail,flask-migrate,flask-paranoid,flask-security-too,flask-socketio,flask-sqlalchemy,
flask-wtf,gssapi,jsonformatter,keyring,ldap3,libgravatar,libpass,paramiko,psycopg,psycopg-c,
pyotp,pytz,qrcode,sqlalchemy,sqlparse,sshtunnel,typer,user-agents,werkzeug,wtforms,psutil,
dateutil}`, `python3.12-cryptography` (stack package 1:49.0.0 since §9's crypto pivot;
originally reused from RHEL at 41) and `python3.12-{urllib3,setuptools}` (RHEL, no floors);
`Requires(pre): shadow-utils` (sysusers compat). `Suggests: percona-pgadmin4-doc`.

### 5.2 Subpackages

| Subpackage | Contents | Requires |
|---|---|---|
| `percona-pgadmin4-gunicorn` | `/usr/bin/percona-pgadmin4-gunicorn`, `%{python3_sitelib}/pgadmin4/{run_pgadmin,gunicorn_config}.py`, `%{_unitdir}/percona-pgadmin4.service` (not enabled), `%{_tmpfilesdir}/percona-pgadmin4.conf` | `percona-pgadmin4 = %{version}-%{release}`, `%{python3_pkgprefix}-gunicorn`; `%systemd_post/preun/postun_with_restart` scriptlets |
| `percona-pgadmin4-httpd` | `%config(noreplace) /etc/httpd/conf.d/percona-pgadmin4.conf`, `/usr/bin/percona-pgadmin4-setup-web` | `percona-pgadmin4 = %{version}-%{release}`, `httpd`, `python3.12-mod_wsgi`; `Recommends: policycoreutils-python-utils` |
| `percona-pgadmin4-doc` | `/usr/share/doc/percona-pgadmin4/en_US/` (the `docs/en_US` tree: `*.rst`, `images/`, `theme/`) | — |

### 5.3 `%prep`

`%autosetup -p1 -n percona-pgadmin4-%{version}`, then:
- write `web/commit_hash` from the obsinfo (`grep ^commit: %{_sourcedir}/*.obsinfo`) and
  `sed` the `git:hash` script in `web/package.json` to `exit 0` (what the release tarball
  does); delete the `"packageManager": "yarn@…"` line;
- `sed -i 's,/usr/bin/env python3,%{__ospython},' web/pgacloud/pgacloud.py`; `chmod -x`
  fonts, `docs/en_US/theme/pgadmin4/static/style.css`, `theme.conf`,
  `web/pgadmin/misc/bgprocess/process_executor.py`, `web/*/*/*/*.js` (openSUSE's rpmlint set);
- `cd web && local-npm-registry %{_sourcedir} install --legacy-peer-deps --ignore-scripts`
  (offline `npm install` from the unpacked tarballs; if the git-sourced `react-data-grid`
  cannot be served this way, carry openSUSE's `package_git_local.patch`).

### 5.4 `%build`

- `cd web && NODE_ENV=production NODE_OPTIONS=--max-old-space-size=3072 npx webpack
  --config webpack.config.js` (eslint pass skipped — lint, not build);
  `rm -rf node_modules package-lock.json yarn.lock`.
- Wheel as openSUSE: `mkdir -p pip-build/pgadmin4 && cp -a web/* pip-build/pgadmin4`,
  `echo 'recursive-include pgadmin4 *' > pip-build/MANIFEST.in`, delete `.gitignore`/
  `.coverage*`, copy `%{SOURCE_config_distro}` to `pip-build/pgadmin4/config_distro.py`,
  `%{SOURCE_run_pgadmin}` and `%{SOURCE_gunicorn_config}` next to it,
  `cd pip-build && %{__ospython} ../pkg/pip/setup_pip.py bdist_wheel`.

**`config_distro.py` (installed as `%{python3_sitelib}/pgadmin4/config_distro.py`):**
```python
import ast, os
SERVER_MODE = True
MINIFY_HTML = False
UPGRADE_CHECK_ENABLED = False
HELP_PATH = '/usr/share/doc/percona-pgadmin4/en_US'
DEFAULT_BINARY_PATHS = {
    "pg": "/usr/pgsql-18/bin",
    "pg-13": "/usr/pgsql-13/bin", "pg-14": "/usr/pgsql-14/bin", "pg-15": "/usr/pgsql-15/bin",
    "pg-16": "/usr/pgsql-16/bin", "pg-17": "/usr/pgsql-17/bin", "pg-18": "/usr/pgsql-18/bin",
}
# Container-style overrides: PGADMIN_CONFIG_<NAME>=<python literal>; true/false accepted.
for _k, _v in os.environ.items():
    if _k.startswith('PGADMIN_CONFIG_'):
        _lit = {'true': 'True', 'false': 'False'}.get(_v.strip().lower(), _v)
        try:
            globals()[_k[len('PGADMIN_CONFIG_'):]] = ast.literal_eval(_lit)
        except (ValueError, SyntaxError):
            globals()[_k[len('PGADMIN_CONFIG_'):]] = _v
```
Precedence (pgAdmin's own): `config.py` < `config_distro.py` < `config_local.py` <
`/etc/pgadmin/config_system.py`. Env overrides therefore sit at the distro level; host
admins still win via `config_system.py`, which is what a host wants and what a container
never has.

### 5.5 `%install`

`%{__ospython} -m pip install --no-deps --no-index --root %{buildroot} --prefix %{_prefix}
pip-build/dist/*.whl` → `%{python3_sitelib}/pgadmin4/` (incl. `pgAdmin4.wsgi`,
`config_distro.py`, `run_pgadmin.py`, `gunicorn_config.py`), `%{_bindir}/pgadmin4`,
`%{_bindir}/pgadmin4-cli`. Then: `install -m 0755` the two scripts to `%{_bindir}`;
unit → `%{_unitdir}`; tmpfiles → `%{_tmpfilesdir}`; sysusers → `%{_sysusersdir}`; httpd
conf → `%{_sysconfdir}/httpd/conf.d/`; `install -d` `/var/lib/pgadmin` (0750),
`/var/lib/pgadmin/storage` (0755), `/var/lib/pgadmin/sessions` (0700), `/var/log/pgadmin`
(0750), `/etc/pgadmin` (0750) with `config_system.py` containing only
`# Site overrides for pgAdmin 4 (see config.py); SERVER_MODE is set in config_distro.py`;
docs: `cp -pr docs/en_US` → `%{_docdir}/percona-pgadmin4/en_US` (`.gitignore` removed);
`%{__ospython} -P -c` byte-compile is left to brp.

### 5.6 Scriptlets, users, directories

- `%pre` (base): `%sysusers_create_compat %{SOURCE_sysusers}` → `pgadmin` system user/group,
  home `/var/lib/pgadmin`, no shell login (works without systemd — plain `useradd` — so
  container image builds succeed).
- `%files` (base): `%license LICENSE`, `%doc README.md`, `%{_bindir}/pgadmin4{,-cli}`,
  `%{python3_sitelib}/pgadmin4/` (excluding the two gunicorn files, which belong to
  `-gunicorn`), `%{python3_sitelib}/pgadmin4-*.dist-info/`,
  `%dir %attr(0750,root,pgadmin) /etc/pgadmin`, `%config(noreplace) %attr(0640,root,pgadmin)
  /etc/pgadmin/config_system.py`, `%dir %attr(0750,pgadmin,pgadmin) /var/lib/pgadmin`,
  `%dir %attr(0755,pgadmin,pgadmin) /var/lib/pgadmin/storage`, `%dir %attr(0700,pgadmin,pgadmin)
  /var/lib/pgadmin/sessions`, `%dir %attr(0750,pgadmin,pgadmin) /var/log/pgadmin`,
  `%{_sysusersdir}/percona-pgadmin4.conf`.
- `-gunicorn`: `%post %systemd_post percona-pgadmin4.service` + `%tmpfiles_create`;
  `%preun %systemd_preun`; `%postun %systemd_postun_with_restart`; `%ghost %dir
  %attr(0755,pgadmin,pgadmin) /run/pgadmin4`.
- No scriptlet runs `setup-db`, touches SELinux or enables httpd (admin- or entrypoint-driven).

### 5.7 The gunicorn launcher (`/usr/bin/percona-pgadmin4-gunicorn`)

POSIX sh, mirrors upstream's entrypoint exec line so SP5's entrypoint can just call it:
```sh
#!/bin/sh
# Serve pgAdmin 4 with gunicorn. Environment (all optional, upstream-compatible names):
#   PGADMIN_LISTEN_ADDRESS (default 127.0.0.1), PGADMIN_LISTEN_PORT (default 5050),
#   PGADMIN_ENABLE_TLS (set → bind 0.0.0.0:443 with /certs/server.key + server.cert),
#   GUNICORN_THREADS (25), GUNICORN_ACCESS_LOGFILE (-), GUNICORN_LIMIT_REQUEST_LINE (8190),
#   PGADMIN_CONFIG_* (see config_distro.py).
set -e
APP=/usr/lib/python3.12/site-packages/pgadmin4
cd "$APP"
TIMEOUT=$(/usr/bin/python3.12 -P -c 'import config; print(config.SESSION_EXPIRATION_TIME * 86400)')
if [ -n "${PGADMIN_ENABLE_TLS}" ]; then
  BIND="${PGADMIN_LISTEN_ADDRESS:-0.0.0.0}:${PGADMIN_LISTEN_PORT:-443}"
  TLS="--keyfile /certs/server.key --certfile /certs/server.cert"
else
  BIND="${PGADMIN_LISTEN_ADDRESS:-127.0.0.1}:${PGADMIN_LISTEN_PORT:-5050}"; TLS=""
fi
exec /usr/bin/gunicorn-3.12 --limit-request-line "${GUNICORN_LIMIT_REQUEST_LINE:-8190}" \
  --limit-request-fields "${GUNICORN_LIMIT_REQUEST_FIELDS:-100}" \
  --limit-request-field_size "${GUNICORN_LIMIT_REQUEST_FIELD_SIZE:-8190}" \
  --timeout "$TIMEOUT" --bind "$BIND" -w 1 --threads "${GUNICORN_THREADS:-25}" \
  --access-logfile "${GUNICORN_ACCESS_LOGFILE:--}" $TLS -c gunicorn_config.py run_pgadmin:app
```
(`gunicorn-3.12` is the console script name the `python3-gunicorn` package installs;
the plan fixes the exact name from the built RPM.) Host defaults bind `127.0.0.1:5050`
(no privileged port for user `pgadmin`); the image (SP5) sets address/port via env.
`percona-pgadmin4.service`: `User=pgadmin`, `Group=pgadmin`, `ExecStart=/usr/bin/percona-pgadmin4-gunicorn`,
`Environment=PYTHONDONTWRITEBYTECODE=1`, `Restart=on-failure`, `RuntimeDirectory=pgadmin4`,
`WantedBy=multi-user.target`. `gunicorn_config.py` = upstream's (`SERVER_SOFTWARE`, access
log format, JSON logging when `JSON_LOGGER`), `run_pgadmin.py` = upstream's two lines.

### 5.8 httpd (`-httpd`)

`/etc/httpd/conf.d/percona-pgadmin4.conf`:
```apache
WSGIDaemonProcess pgadmin user=pgadmin group=pgadmin processes=1 threads=25 python-path=/usr/lib/python3.12/site-packages/pgadmin4
WSGIScriptAlias /pgadmin4 /usr/lib/python3.12/site-packages/pgadmin4/pgAdmin4.wsgi
<Directory /usr/lib/python3.12/site-packages/pgadmin4/>
    WSGIProcessGroup pgadmin
    WSGIApplicationGroup %{GLOBAL}
    Require all granted
</Directory>
```
`percona-pgadmin4-setup-web` (root): (1) `runuser -u pgadmin -- /usr/bin/pgadmin4-cli
setup-db` (non-interactive with `PGADMIN_SETUP_EMAIL`/`PGADMIN_SETUP_PASSWORD`, else
prompts); (2) if `selinuxenabled`: `setsebool -P httpd_can_network_connect on
httpd_can_network_connect_db on httpd_tmp_exec on`, `semanage fcontext -a -t httpd_var_lib_t
'/var/lib/pgadmin(/.*)?'`, `-t httpd_log_t '/var/log/pgadmin(/.*)?'`, `restorecon -R`
(skips with a notice if `semanage` is missing); (3) if systemd is running (`[ -d /run/systemd/system ]`)
and `--no-service` was not given: `systemctl enable --now httpd` (or `reload`); prints the URL
`http://<hostname>/pgadmin4/`. Because both httpd (via `WSGIDaemonProcess user=pgadmin`) and
gunicorn run as `pgadmin`, the data directory never changes owner between modes.

### 5.9 Patches

1. `0001-help-menu-online-docs.patch`: in `web/pgadmin/help/__init__.py` the "Online Help"
   item's `url` becomes `'https://www.pgadmin.org/docs/pgadmin4/%s.%s/' % (config.APP_RELEASE,
   config.APP_REVISION)`; the `help.static` blueprint stays (serving `HELP_PATH`).
2. openSUSE `make-cloud-packages-optional.patch` (cloud module import guarded — we ship no
   azure/boto3/google).
3. openSUSE `use-os-makedirs.patch`.
Refreshed or dropped during the build loop if they no longer apply to 9.17. Not carried:
`fix-python3-crypto-call` (obsolete), `fix-reproducible-builds` (optional determinism),
`support-new-azure-mgmt-rdbms` (cloud), `package_git_local` (only if §5.3's fallback triggers).

### 5.10 `%check`

`PYTHONPATH=%{buildroot}%{python3_sitelib}/pgadmin4 %{__ospython} -P -c "import config,
run_pgadmin"` — imports pgAdmin's `config` (→ `pgadmin.utils`, `keyring`, `branding`,
`config_distro`) and the WSGI entry (→ `pgAdmin4.app`, the whole Flask app graph). This
proves the stack (with Authlib 1.6.12) loads, without a database or network. If
`run_pgadmin` needs a writable data dir at import, the check sets
`PGADMIN_CONFIG_DATA_DIR=%{_builddir}/pgadmin-data` through the new env mechanism.

## 6. SP3 stack changes for REL-9_17 (first plan task)

| Change | Package | Detail |
|---|---|---|
| keep | `python3-authlib` 1.6.12 | see §3 (Authlib ruling) |
| bump | `python3-flask-security-too` | 5.6.2 → 5.8.2; `Requires` gain `%{python3_pkgprefix}-libpass >= 1.9.3`, `flask >= 3.1.1`, `email-validator >= 2.3.0`; drop `passlib`, `importlib-resources` |
| bump | `python3-flask-socketio` | 5.5.1 → 5.6.1 |
| bump | `python3-flask-wtf` | 1.2.2 → 1.3.0 |
| bump | `python3-gssapi` | 1.10.1 → 1.11.1 (`Cython == 3.2.4`) |
| bump | `python3-cython` | 3.1.3 → 3.2.4 |
| bump | `python3-psycopg`, `python3-psycopg-c` | 3.2.10 → 3.3.4 (lock-step) |
| bump | `python3-pytz` | 2025.2 → 2026.3.post1 |
| bump | `python3-typer` | 0.19.2 → 0.26.8; `Requires` gain `annotated-doc >= 0.0.2`, `rich >= 13.8.0` |
| new | `python3-annotated-doc` 0.0.5 | pure, pdm-backend |
| new | `python3-certifi` 2026.6.17 | pure, setuptools (MPL-2.0); direct pgAdmin requirement |
| new | `python3-libpass` 1.9.3 | pure, hatchling; `Provides: %{python3_pkgprefix}-passlib = 1.9.3`, `Conflicts: %{python3_pkgprefix}-passlib < 1.9`; `%check` imports `passlib` |
| new | `python3-gunicorn` 26.2.0 | pure, setuptools (MIT); no runtime deps; ships the `gunicorn` console script |
| remove | `python3-passlib`, `python3-importlib-resources` | superseded / unused |
| reuse (unchanged) | cryptography 41, setuptools 68, urllib3 1.26, psutil 6.1.1 | pgAdmin pins 49 / 83 / 2.7 / 7.2 relaxed as in SP3 |

All follow the SP3 template and rules (`python -P` in `%check`, PEP 639 `%prep` sed where
the new sdist needs it, runtime deps mirrored as BuildRequires, PyPI sdist via
`download_url`). Result: 74 packages in `ppg:devel:pgadmin` before `percona-pgadmin4`.
The SP3 spec's §4 inventory is updated in the same commit.

## 7. Documentation

- `root/README.md`: the `devel/pgadmin/` paragraph names `percona-pgadmin4` and its
  subpackages, the three-service source chain, and the container relationship (SP5).
- `docs/PERCONA_OBS_TOOL.md` "Vendoring npm dependencies": one paragraph of real-package
  facts (artifact sizes, first-sync duration, cache behaviour) once measured.
- The `percona-pgadmin4` spec header comment documents the bump procedure (change
  `revision`; re-check `requirements.txt` against the stack).
- SP3 spec §4/§8 updated for the 9.17 changes; this spec gets a §9 outcomes section after
  the build loop; PR #12 body gains an SP4 section.

## 8. Verification

**Local, read-only:** `rpmspec -P` on the rendered spec; `sync push --dry-run -P isv-pr
ppg:devel:pgadmin percona-pgadmin4` (runs `obs_scm` → `npm_lockfile` → `node_modules` for
real at `REL-9_17`; expect the 5-file upload set; first run downloads ~1 400 npm tarballs,
later runs are cached); dry runs of two bumped SP3 packages.

**OBS via PR #12 (each step its own push, approved individually):**
1. SP3 changes (§6) → `ppg:devel:pgadmin` green again (74 packages × 2 archs).
2. `percona-pgadmin4` → `succeeded` on UBI_9 (noarch; both archs build). RPM content
   checks (from the public `_binary` listing or `rpm -qlp` of the downloaded RPM):
   `%{python3_sitelib}/pgadmin4/pgAdmin4.wsgi`, `/usr/bin/pgadmin4`, `/usr/bin/pgadmin4-cli`,
   `/usr/bin/percona-pgadmin4-gunicorn`, `/usr/bin/percona-pgadmin4-setup-web`, the unit,
   sysusers, tmpfiles, httpd conf, `-doc`'s `en_US/` tree.

**Smoke test with OBS-built RPMs (proposed; consumes OBS artefacts, runs outside OBS):**
in a UBI-9 container with the PR project's UBI_9 repo enabled: install `percona-pgadmin4
percona-pgadmin4-gunicorn`, `PGADMIN_SETUP_EMAIL=… PGADMIN_SETUP_PASSWORD=… runuser -u pgadmin
-- pgadmin4-cli setup-db`, `PGADMIN_LISTEN_ADDRESS=0.0.0.0 PGADMIN_LISTEN_PORT=8080 runuser -u
pgadmin -- percona-pgadmin4-gunicorn &`, `curl -s -o /dev/null -w '%{http_code}'
http://localhost:8080/login` → `200`; and a second container with `-httpd`:
`percona-pgadmin4-setup-web --no-service`, `httpd -DFOREGROUND &`, `curl …/pgadmin4/login`
→ `200`. This is the acceptance for "the wiring works"; it is also the dry run of SP5's
entrypoint.

## 9. Risks

| Risk | Mitigation |
|---|---|
| `local-npm-registry install` cannot serve the git-sourced `react-data-grid` | carry openSUSE's `package_git_local.patch` (published beta); SP1 saw the `node_modules` service clone it, so the tarball is in the cpio. **What actually shipped (§9):** no patch — `%prep` rewrites package.json + the lockfile to a `file:` reference to that vendored tarball. |
| webpack memory/time on OBS workers | `NODE_OPTIONS=--max-old-space-size=3072`; workers have ≥ 4 GB; nodejs:22 stream. |
| Authlib 1.6.12 vs pgAdmin 9.17 | `%check` imports the app graph; the container smoke test logs in. If 1.7-only APIs are used: bump Authlib, add `joserfc`, and decide cryptography (49 via Rust) then. |
| `import run_pgadmin` in `%check` wants a writable `DATA_DIR`/log | `PGADMIN_CONFIG_DATA_DIR`/`LOG_FILE` env overrides in `%check` (the new mechanism). |
| Gunicorn console-script name (`gunicorn` vs `gunicorn-3.12`) | fixed from the built `python3-gunicorn` RPM before the launcher is final. |
| 210 MB `node_modules.obscpio` upload/time | measured in SP1's dry run; first real push happens in step 2 — a timeout makes SP1 §10's deferred chunked-md5/upload work a task. |
| SELinux on bare-metal hosts | the helper applies upstream's booleans/fcontexts; containers are permissive; an enforcing-host test is a QA follow-up. |
| OBS rebuild storms (DoD path-repo refreshes) | expected, as in SP3; nothing to do. |

### Outcomes (2026-09-02)

- OBS (`isv:percona:PR:pr-12:ppg:devel:pgadmin` + `common:deps:build`, UBI_9): **10 fix
  rounds** across Tasks 4/5 —
  - sync: `npm_lockfile` missing from the obs-tools image (image builds only from main)
    → PR #17 (Dockerfile + service on main), rebase;
  - sync: `node_modules` cannot `ssh`-clone `react-data-grid` → `git url.insteadOf`
    SSH→HTTPS in the shared obs-setup action;
  - `python3-psycopg-c`: 3.3.4 declares extensions via `[[tool.setuptools.ext-modules]]`
    (setuptools ≥ 74.1; RHEL has 68) → `%prep` setup.py shim (the 3.2.x layout);
  - `percona-pgadmin4`: EL9 rpm 4.16 expands the `%install` macro inside a `%build`
    comment → "second %install" parse error → `%%`-escape section keywords in comments;
  - `percona-pgadmin4`: `@fortawesome/fontawesome-free: "latest"` — npm dist-tags don't
    exist in local-npm-registry's offline packuments (ETARGET) → `%prep` pins the range
    to the lockfile's version (dynamic);
  - `percona-pgadmin4`: npm fetches the `react-data-grid` git dependency from
    codeload.github.com (no network in OBS) → `%prep` rewrites package.json + lockfile
    to the `file:` tarball the `node_modules` service vendors;
  - **nodejs 22.23.1** (new package, `common:deps:build`): the buildroot resolved
    nodejs 16 — EL9 DoD repos expose only the default module stream, and
    `nodejs >= 20` is epoch-broken (EL9 nodejs has Epoch 1, so `1:16.20.2 >= 20`);
    ported the CS9 `nodejs:22` module spec (stream-nodejs-22-rhel-9.9.0), sources from
    the public CS9 lookaside; one skipped test (`internet/test-dgram-membership.js`
    needs a multicast interface; OBS VMs are loopback-only); consumers now require
    `nodejs >= 1:22`;
  - `percona-pgadmin4`: 35 auto-generated **rich-form** `python3.12dist()` requires
    (from `pkg==X.Y.*` pins; rich deps start with `(` and escaped the `^`-anchored
    `__requires_exclude`) made the RPM uninstallable → unanchored exclude;
  - **cryptography 49 pivot** (user decision 2026-09-01, overturning §3's
    keep-RHEL-41): pgAdmin's `crypto.py` imports CFB8 from
    `cryptography.hazmat.decrepit` (added in 43; the old location is removed in 49) →
    new stack packages `python3-maturin` 1.15.0 (PEP 517 backend of every
    cryptography ≥ 43; binary cargo-built offline, sdist's pure-python shim — bypasses
    its setuptools ≥ 77 bootstrap), `python3-cffi` 2.1.1 (Epoch 1 > RHEL 1.x;
    cryptography 49 needs cffi ≥ 2.0; `+Requires pycparser`), `python3-cryptography`
    49.0.0 (Epoch 1 > RHEL 41; maturin + `cargo_vendor`, system OpenSSL; two OBS
    rounds: unpackaged `cffi-gen-src` console script, missing
    `python3.12-setuptools` BuildRequires — build.rs compiles the cffi module via a
    python snippet);
  - `python3-authlib`: `+Requires python3.12-requests` (RHEL) — its flask integration
    imports `..requests_client` unconditionally (first-start crash in the smoke test).

  Final `_result`: 82/82 packages succeeded on UBI_9 x86_64 + aarch64 in
  `ppg:devel:pgadmin`; `common:deps:build` (local-npm-registry, nodejs) all succeeded;
  repository published on download.opensuse.org.
- Stack for 9.17: 9 bumps, 4 additions (annotated-doc, certifi, libpass, gunicorn) — plus
  the 3 crypto-pivot additions (maturin, cffi, cryptography) — 2 removals (passlib,
  importlib-resources), 5 `_aggregate`s of `ppg:common:deps`.
- Container smoke test (podman,
  `ubi9/ubi@sha256:ae8730de9161f4e98dbe22fef5eba494b0bfe5886be8dc3c4ff687c2e954daf6`,
  installing `percona-pgadmin4-9.17-6.3.noarch` from the published PR repo):
  gunicorn — `INSTALL OK`, `ENV OK 7` (PGADMIN_CONFIG_* env mapping), `HTTP 200` for
  `/login`, `SETUP OK` (pgadmin4.db created from PGADMIN_DEFAULT_*), `VERSION OK 9.17`
  (page marker `ver=91700`); httpd — `INSTALL OK`, `CONF PRESENT`, `Syntax OK`,
  `wsgi_module (shared)`, `SETUP-WEB OK`. Logs: scratchpad `smoke/gunicorn.log`,
  `smoke/httpd.log` (quoted in the SDD ledger).
- Decisions changed during execution: **cryptography reuse-RHEL-41 → stack package
  49.0.0** (user, 2026-09-01 — "the original keep-41 ruling was cost-driven; the stack
  already does offline cargo builds and EL9 ships rust 1.92 ≥ the 1.83 MSRV"); the
  Authlib-1.7/joserfc follow-up this unblocks is deferred. **Node ≥ 20 from a distro
  stream → own CS9 port** (user, 2026-08-31). Both recorded in §2.2/§3 amendments above.
- Deferred minor: `percona-pgadmin4-setup-web` calls `hostname` (absent in minimal
  UBI-9), so its final info line prints an empty host; cosmetic — the SP5 image uses
  gunicorn.

## 10. Out of scope

`-desktop`, `-uwsgi`, cloud support, Debian/Ubuntu, HTML documentation, upgrading
setuptools/urllib3 beyond RHEL's (cryptography moved in scope during execution — §9),
the container image itself (SP5: Dockerfile,
entrypoint mapping `PGADMIN_DEFAULT_EMAIL/PASSWORD` → `setup-db`, `servers.json` import,
TLS certificate handling).
