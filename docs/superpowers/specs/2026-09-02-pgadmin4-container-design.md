# pgAdmin 4 container image (SP5) — `ppg:devel:pgadmin:containers`

**Date:** 2026-09-02 · **Status:** designed, awaiting plan
**Predecessors:** SP1 tooling (2026-08-26), SP3 py3.12 stack (2026-08-26), SP4
`percona-pgadmin4` (2026-08-28, §9 Outcomes 2026-09-02). This is the stated goal of the
whole pgAdmin effort: a container image built from the OBS-built RPMs.

## 1. Goal

A `percona-pgadmin4` container image for UBI 9, built by OBS in a new
`ppg:devel:pgadmin:containers` project from the `ppg:devel:pgadmin` RPMs, runtime
"compatible where it counts" with upstream `dpage/pgadmin4` (decision §3): same
environment contract including Docker-secret `_FILE` variants, `servers.json` /
`preferences.json` import, TLS via `/certs`, OpenShift random-UID tolerance — but
Percona house style where upstream is exotic: fixed non-root user, port 8080, no
capability-modified python, no PUID/su-exec remapping, no postfix.

## 2. Findings that shaped the design

### 2.1 House container pattern (read 2026-09-02)

`root/ppg/staging/18/containers/*`: a containers subproject has `project.yaml`
(repos `ubi8`/`ubi9`, paths to the staging RPM repos + `common:containers:ubiN`
`images`+`UBI_N` + EPEL/UBI/Rocky), and each image package is `obs/` only —
`Dockerfile` with `#!UseOBSRepositories`, `#!BuildVersion`, `#!BuildTag` directives and
`%!{VAR}` macros, plus `entrypoint.sh`/`LICENSE`/conf files `COPY`'d in. Base image is
`FROM percona-ubi-minimal:latest` (from `common:containers:ubi9`), packages installed
with `microdnf`, fixed non-root `USER`.

### 2.2 Upstream entrypoint inventory (pkg/docker/entrypoint.sh @ REL-9_17, 347 lines)

PUID/PGID remapping via su-exec (root-start case) + OpenShift passwd fixup;
CAP_NET_BIND_SERVICE-capped python copy for port 80/443 with restricted-context
detection falling back to 8080/8443; `file_env` secrets (`PGADMIN_DEFAULT_PASSWORD_FILE`,
`PGADMIN_CONFIG_CONFIG_DATABASE_URI_FILE`); one-time generation of `config_distro.py`
baking `PGADMIN_CONFIG_*` env at first launch; external-config-DB existence check
(`check_external_config_db`) deciding whether first-run setup runs; email validation +
first-run setup; `servers.json` / `preferences.json` / `PGPASS_FILE` import;
`sudo postfix start`; gunicorn exec (1 worker, `--threads`, timeout from
`SESSION_EXPIRATION_TIME`, `GUNICORN_*` knobs, `--keyfile/--certfile` when
`PGADMIN_ENABLE_TLS`).

Our RPM already covers the core better than upstream: `config_distro.py` applies
`PGADMIN_CONFIG_*` at every import (upstream bakes them once at first launch), and the
`-gunicorn` launcher handles `PGADMIN_DEFAULT_*` first-run setup, `PGADMIN_LISTEN_*`
and `GUNICORN_*` (proved by SP4's Task 5 smoke test).

### 2.3 `DEFAULT_BINARY_PATHS` (web/config.py)

Native pgAdmin setting: dict keyed `"pg"`, `"pg-13"`…`"pg-18"` (+ `"ppas-*"`), value =
directory with `psql`/`pg_dump`/`pg_dumpall`/`pg_restore` for that major; powers the
Backup/Restore/Maintenance dialogs and external Query Tool features. Empty (default) =
per-user manual configuration + the `Invalid binary path` warnings seen in SP4's smoke
test. Percona client RPMs (`percona-postgresqlNN`) install these tools to
`/usr/pgsql-NN/bin`. Our tree has staging majors 14–18 (no 13 — EOL).

## 3. Decisions (user, 2026-09-02)

| Topic | Decision |
|---|---|
| Compat envelope | **"Compatible where it counts":** env contract incl. `_FILE` secrets, `servers.json`/`preferences.json` import, TLS via `/certs`, OpenShift random-UID fixup, external-config-DB check; **port 8080 default**, fixed non-root user, no capped python / PUID remapping / postfix. Migration from `dpage/pgadmin4` = change one port mapping. |
| PG client binaries | **All available majors 14–18** (`percona-postgresql{14..18}`), `DEFAULT_BINARY_PATHS` wired to `/usr/pgsql-NN/bin`; `pg-13` stays empty (no PG 13 in the tree). |
| Entrypoint ownership | **Approach A:** image-owned `obs/entrypoint.sh` layered over the RPM launcher, `exec /usr/bin/percona-pgadmin4-gunicorn` at the end. Container concerns never enter the host RPM (one exception: TLS passthrough, §6). |
| Project | `root/ppg/devel/pgadmin/containers/` → `ppg:devel:pgadmin:containers`, repo `ubi9` only, x86_64 + aarch64. |
| UID | Pin the RPM-created `pgadmin` user to **UID 5050** (upstream's), group 0 membership for OpenShift; `USER 5050`. |
| Mail | Not shipped; users set `PGADMIN_CONFIG_MAIL_*` to an external relay. |

## 4. Project & package layout

```
root/ppg/devel/pgadmin/containers/
├── project.yaml                      # ppg:devel:pgadmin:containers
└── percona-pgadmin4/
    └── obs/
        ├── Dockerfile
        ├── entrypoint.sh
        └── LICENSE                   # PostgreSQL licence, → /licenses/
```

`project.yaml` repo `ubi9` (x86_64, aarch64), paths in order:

1. `ppg:devel:pgadmin` UBI_9 — the pgAdmin stack RPMs
2. `ppg:staging:{18,17,16,15,14}` UBI_9 — `percona-postgresqlNN` clients
3. `ppg:common:deps` UBI_9
4. `common:deps:build` UBI_9 — **dropped at plan time** (§7); the image install
   closure never touches it
5. `common:containers:ubi9` `images` + `UBI_9` — `percona-ubi-minimal`, kiwi helpers
6. `Fedora:EPEL:9 standard`, `RedHat:UBI-9 standard` — matches the house ubi9
   pattern (EPEL 9 + RedHat UBI-9 only, as shipped in `project.yaml`); the
   `Ignore`/`Substitute` rocky-release lines that appear alongside this repo
   list are base-image hygiene, not an extra content repo

Remember the OBS path rule: only the last path expands transitively — list content
repos explicitly (as the staging containers project does).

Macros: add `PGADMIN_VERSION: 9.17` to the pgadmin project's macros (shared knob with
the RPM `_service` revision `REL-9_17`; a version bump edits both together).

## 5. Dockerfile

```dockerfile
#!UseOBSRepositories
#!BuildVersion: %!{PGADMIN_VERSION}
#!BuildTag: percona-pgadmin4:<VERSION>-<RELEASE>
#!BuildTag: percona-pgadmin4:<VERSION>
#!BuildTag: percona-pgadmin4:latest

FROM percona-ubi-minimal:latest
```

- House labels (`name="Percona pgAdmin 4"`, vendor/summary/maintainer/authors);
  `LABEL version="%!{PGADMIN_VERSION}"`, `LABEL release`.
- `RUN microdnf -y update && microdnf -y install percona-pgadmin4
  percona-pgadmin4-gunicorn percona-postgresql14 percona-postgresql15
  percona-postgresql16 percona-postgresql17 percona-postgresql18 && microdnf clean all`
  (shadow-utils for `usermod` during build only if not already present).
- `RUN usermod -u 5050 -aG 0 pgadmin && chown -R 5050:0 /var/lib/pgadmin
  /var/log/pgadmin /run/pgadmin` — pin the sysusers-allocated UID; group 0 so an
  OpenShift random UID (gid 0) can write.
- Overridable defaults via `ENV` (Docker `-e` naturally overrides; `config_distro.py`
  applies them at every import):
  - `PGADMIN_CONFIG_DEFAULT_BINARY_PATHS="{'pg': '/usr/pgsql-18/bin', 'pg-14':
    '/usr/pgsql-14/bin', 'pg-15': '/usr/pgsql-15/bin', 'pg-16': '/usr/pgsql-16/bin',
    'pg-17': '/usr/pgsql-17/bin', 'pg-18': '/usr/pgsql-18/bin'}"`
  - `PGADMIN_LISTEN_ADDRESS=0.0.0.0`, `PGADMIN_LISTEN_PORT=8080`
- `COPY entrypoint.sh /usr/local/bin/entrypoint.sh`; `COPY LICENSE
  /licenses/LICENSE.Dockerfile`.
- `EXPOSE 8080`; `VOLUME /var/lib/pgadmin`; `USER 5050`;
  `ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]` (no CMD arguments needed).

## 6. Entrypoint contract (`entrypoint.sh`)

In order, then `exec /usr/bin/percona-pgadmin4-gunicorn`:

1. **OpenShift fixup:** if `whoami` fails (random UID) and `/etc/passwd` is writable,
   append `pgadminr:x:$(id -u):0:…:/var/lib/pgadmin:/sbin/nologin`.
2. **Secrets:** `file_env PGADMIN_DEFAULT_PASSWORD`;
   `file_env PGADMIN_CONFIG_CONFIG_DATABASE_URI` when its `_FILE` is set. Error out if
   both `VAR` and `VAR_FILE` are set (upstream semantics).
3. **External config DB:** if `PGADMIN_CONFIG_CONFIG_DATABASE_URI` is set, run
   pgAdmin's `check_external_config_db` (python3.12, `ast.literal_eval` unwrap as
   upstream does); an existing external config DB marks setup-not-needed.
4. **First-run guard:** setup needed (no `/var/lib/pgadmin/pgadmin4.db` and no
   existing external config DB) → require `PGADMIN_DEFAULT_EMAIL` and a password
   (direct or `_FILE`); exit 1 with upstream's message otherwise.
5. **First-run init + imports:** when setup is needed, run the initialization once —
   `cd %{python3_sitelib}/pgadmin4 && PGADMIN_SETUP_EMAIL=… PGADMIN_SETUP_PASSWORD=…
   python3.12 setup.py setup-db` (the same init the RPM launcher performs; the
   launcher later sees `pgadmin4.db` exists and skips its own init — no double-run),
   then:
   - `servers.json`: `pgadmin4-cli load-servers "${PGADMIN_SERVER_JSON_FILE:-/pgadmin4/servers.json}"
     --user "$PGADMIN_DEFAULT_EMAIL"` if the file exists; `--replace` when
     `PGADMIN_REPLACE_SERVERS_ON_STARTUP=True` (which also runs on non-first boots,
     upstream semantics).
   - `preferences.json`: `pgadmin4-cli set-prefs "$PGADMIN_DEFAULT_EMAIL" --input-file
     "${PGADMIN_PREFERENCES_JSON_FILE:-/pgadmin4/preferences.json}"` if the file exists.
6. **TLS:** if `PGADMIN_ENABLE_TLS` is set and `/certs/server.cert` +
   `/certs/server.key` exist, `export PGADMIN_TLS_CERTFILE=/certs/server.cert
   PGADMIN_TLS_KEYFILE=/certs/server.key`; if the env is set but certs are missing,
   exit 1 with a clear message. (Default port stays 8080 either way; users map 8443
   outside.)

Not ported (documented in the image description): PUID/PGID remapping, capability
python / port 80, postfix, `PGPASS_FILE` (defer until asked — desktop-mode oriented).

## 7. RPM change (the single approach-A exception)

**Dropped at plan time (2026-09-02):** the shipped launcher already implements TLS —
`PGADMIN_ENABLE_TLS=true` adds `--certfile /certs/server.cert --keyfile
/certs/server.key` to the gunicorn command line (SP4 §5.7 delivered it). No RPM change
is needed; the entrypoint's TLS step (§6.6) reduces to validating that the cert pair
exists when `PGADMIN_ENABLE_TLS` is set, then passing the variable through.

Other plan-time resolutions: `common:deps:build` is dropped from the repo paths (§4 —
nothing in the image's install closure needs the build tools); the `ubi9-images` PR
label already matches the new `:containers` layout generically
(`percona_obs/cmd_sync.py` `_IMAGES_REPO_RE` — a `:containers` project with a repo
named `ubi9`), so PR #12 needs the `ubi9-images` label added alongside `UBI_9`;
`percona-ubi-minimal` includes shadow-utils, so `usermod` is available at image build.

## 8. Verification

Task-5-style, against the OBS-built image (PR project):

- **Image acquisition:** preferred `podman pull` from the OBS registry
  (`registry.opensuse.org/<prj path>/percona-pgadmin4`); if PR container repos do not
  publish to the registry, `osc getbinaries` the image tarball and `podman load`. Pin
  the mechanics at plan time.
- **Smoke matrix (scripts + logs in scratchpad, tokens quoted in the ledger):**
  1. `PGADMIN_DEFAULT_EMAIL/PASSWORD` → `/login` HTTP 200, `ver=91700` marker.
  2. `PGADMIN_DEFAULT_PASSWORD_FILE` (mounted secret) works; both-set case errors.
  3. `servers.json` mounted → after start, `pgadmin4-cli` (or sqlite query) shows the
     imported server.
  4. TLS: mounted `/certs` + `PGADMIN_ENABLE_TLS` → `curl -k https://…/login` 200.
  5. Binary paths: all five `/usr/pgsql-NN/bin/pg_dump` exist; a python one-liner
     inside the container shows `config.DEFAULT_BINARY_PATHS['pg-16']` resolving.
  6. OpenShift simulation: `podman run --user 12345:0` still boots (passwd fixup).
- PR label: the containers project needs the PR filter to include the new project
  (the `<flavor>-images` label convention handles old+new layouts — verify it matches
  a `ppg:devel:pgadmin:containers` path or extend the mapping).

## 9. Risks

| Risk | Mitigation |
|---|---|
| `percona-postgresqlNN` client RPMs pull server/systemd deps into the image | check the closure in the first build; if heavy, switch to the client-only subpackage split Percona provides (verify exact names at plan time). |
| Five majors inflate the image | accepted by decision (§3); measure and record final size in outcomes. |
| `usermod -u 5050` collides with an existing UID in the base image | `usermod -o` or pre-create the user with `useradd -u 5050` before `microdnf install` (sysusers keeps the existing user). Resolve in the first build round. |
| PR project may not publish container images to the OBS registry | fallback `osc getbinaries` + `podman load` (§8). |
| `pgadmin4-cli load-servers/set-prefs` argument names differ from upstream `setup.py` | they are the same entry points (SP4 §5); verify `--user/--replace` flags in the fix loop. |
| First-run init in the entrypoint vs launcher double-run | the launcher skips when `pgadmin4.db` exists; entrypoint runs init only when setup is needed. Smoke test 1 covers restart-idempotence. |

### Outcomes (2026-09-02)

- OBS (`isv:percona:PR:pr-12:ppg:devel:pgadmin:containers`, repo `ubi9`): **1 image fix
  round** — the ENTRYPOINT failed with "not executable" (COPY preserves the mode-644
  source from the OBS payload; crun refuses exec) → `RUN chmod 0755` after the COPYs
  plus the x-bit on the committed source (afcd74f9). One CI wrinkle: adding the
  `ubi9-images` label triggered a skipped label-event run that auto-cancelled the push
  run; a re-run synced fine. Final: `percona-pgadmin4` **succeeded on x86_64 +
  aarch64**, tags `9.17-2.1` / `9.17` / `latest` (macros rendered correctly).
- Entrypoint hardening found in Task 2 review (spec §6 amendments, both harness-covered):
  `PGADMIN_REPLACE_SERVERS_ON_STARTUP=True` without `PGADMIN_DEFAULT_EMAIL` now fails
  with a clear error instead of `--user ""`; in external-config-DB mode the entrypoint
  unsets `PGADMIN_DEFAULT_EMAIL/PASSWORD` before exec so the launcher cannot
  double-init against the external DB.
- Image acquisition (spec §8 open item resolved, corrected 2026-09-02): the OBS
  registry DOES serve PR-project images — the path includes the repository name:
  `registry.opensuse.org/isv/percona/pr/pr-12/ppg/devel/pgadmin/containers/ubi9/percona-pgadmin4:latest`
  (the initial "name unknown" probe had omitted the `/ubi9/` segment; found by the
  user). `osc getbinaries` of the ~207 MB image tar + `podman load` works too.
  Loaded x86_64 image size: 650 MB (five PG client majors).
- Smoke matrix: **6/6 PASS** on `9.17-2.1`
  (digest `sha256:2bf4c37b4a5ae2774b3d1139f66e4cbfd9ddd51cd0ea878bf6632041bfb1bae2`) —
  T1 login 200 + `ver=91700` + idempotent restart; T2 password `_FILE` + both-set
  error; T3 servers.json imported; T4 TLS https 200 + missing-certs error; T5
  `pg_dump` 14–18 present + `DEFAULT_BINARY_PATHS['pg-16']` resolves; T6
  `--user 12345:0` boots. Log: scratchpad `sp5/smoke-image.log`; round-1 failure
  evidence and diagnosis in the SDD task-4 report.
- **Final-review fix wave (same day):** TLS truthiness (any non-empty
  `PGADMIN_ENABLE_TLS` now enables TLS, normalized to the launcher's literal
  `true` — `True`/`1` had silently served plaintext), external-config-DB probe
  crashes abort with a clear error, passwd fixup entry named `pgadminr`
  (1966c090). Matrix re-run on the final image `9.17-3.1`
  (`sha256:b6565aebcbffcd162a31bf0d348ccfe7c7b9221bf07922f67a5a70b71a483f88`):
  **6/6 PASS** plus an explicit `PGADMIN_ENABLE_TLS=True` HTTPS check.
- **Post-delivery login fix (2026-09-02, user-reported):** the container
  rendered `/login` but no credentials worked — every login bounced silently to
  `/login`. Root cause was a flask-security-too version incompatibility, not the
  image: FS-too 5.8.2 fixed issue #1212 by inverting `UserMixin.is_locked`
  (`LoginForm.validate` went from `if not user.is_locked()` in 5.8.1 to
  `if user.is_locked()` in 5.8.2), while pgAdmin 9.17's own `User.is_locked`
  still returns `True` for a *non-locked* user. Under the SP3-built 5.8.2 the
  form therefore treated every user as locked, failing validation *after* the
  password already verified (the error lands in WTForms `form_errors`, which
  pgAdmin's login view does not flash — hence the silent bounce). Fixed by
  pinning `python3-flask-security-too` to **5.8.1** (newest release matching
  pgAdmin's convention; within pgAdmin's own `5.8.*` pin; spec comment warns
  against re-advancing). Rebuilt image `9.17-3.2`
  (`sha256:9c565ad309a340011f86fda2dbc7f30e29e3ec996e204daf1681ba81ac46fbf2`).
  **Gate gap closed:** the smoke matrix only asserted `GET /login` == 200 and
  never performed a real authentication — a new **T7** now logs in for real
  (valid credentials must reach `/browser/`, a wrong password must return to
  `/login`); matrix re-run is **7/7 PASS**.
- Decisions changed during execution: none (the §6 entrypoint amendments and the chmod
  are within the approved design; controller rulings recorded in the SDD ledger).

## 10. Out of scope

Port 80/443 + capability python, PUID/PGID remapping, postfix/local mail,
`PGPASS_FILE` import, desktop mode, ubi8, Kubernetes manifests/operator integration,
publishing beyond the OBS-built tags, TLS cert generation (users bring certs).
