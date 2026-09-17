# pgAdmin 4 Container Image (SP5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `percona-pgadmin4` UBI-9 container image in a new
`ppg:devel:pgadmin:containers` OBS project from the SP1–SP4 RPMs, with an entrypoint
"compatible where it counts" with `dpage/pgadmin4`.

**Architecture:** House container pattern (obs/Dockerfile package, `#!BuildTag`,
`%!{VAR}` macros, `FROM percona-ubi-minimal:latest`); an image-owned `entrypoint.sh`
layers container-only behavior (secrets `_FILE`, servers.json/preferences import,
TLS validation, OpenShift random-UID fixup, external-config-DB check) over the RPM's
`percona-pgadmin4-gunicorn` launcher and `exec`s it. Clients `percona-postgresql14..18`
wired into `DEFAULT_BINARY_PATHS`.

**Tech Stack:** OBS docker builds (podman engine), bash entrypoint, podman smoke tests.

**Spec:** `docs/superpowers/specs/2026-09-02-pgadmin4-container-design.md`

## Global Constraints

- All sync pushes go through PR #12 (`git push percona pgadmin-sp1`); **ask the user
  before every push** (standing ruling). `-P isv` writes are dry-run only; `-P isv-pr`
  dry-run is the local verification profile.
- Worktree `/home/rdias/Work/percona-obs-packaging/.claude/worktrees/pgadmin-sp1`,
  branch `pgadmin-sp1`. Commits `git commit -s`, no Claude attribution.
- The launcher (`/usr/bin/percona-pgadmin4-gunicorn`) already handles: first-run
  setup from `PGADMIN_DEFAULT_EMAIL/PASSWORD`, `PGADMIN_LISTEN_*` (defaults
  127.0.0.1:5050), `GUNICORN_*`, and TLS via `PGADMIN_ENABLE_TLS=true` →
  `/certs/server.cert` + `/certs/server.key`. The entrypoint must NOT reimplement
  those; it prepares the environment and execs the launcher.
- Image identity: name `percona-pgadmin4`, tags `%!{PGADMIN_VERSION}-<RELEASE>`,
  `%!{PGADMIN_VERSION}`, `latest`; UID 5050, group 0; port 8080; volume
  `/var/lib/pgadmin`.
- `DEFAULT_BINARY_PATHS` keys use pgAdmin's `pg`/`pg-NN` names; values are
  `/usr/pgsql-NN/bin`; `pg-13` stays unset (no PG 13 in the tree).

**User decisions (already made):**
- Compat envelope: "compatible where it counts" — env contract incl. `_FILE` secrets,
  servers.json/preferences import, TLS via /certs, OpenShift random-UID fixup; port
  8080, fixed UID 5050, no capped python / PUID remapping / postfix (2026-09-02).
- PG clients: all available majors 14–18 with `DEFAULT_BINARY_PATHS` wired (2026-09-02).
- Entrypoint ownership: approach A — image-owned script over the RPM launcher
  (2026-09-02).
- Project layout §1 and design §§2–4 approved as presented (2026-09-02).

---

### Task 1: Containers project skeleton + Dockerfile

**Goal:** The `ppg:devel:pgadmin:containers` project definition, the pgadmin project
macros file, and the image package's Dockerfile + LICENSE (everything static; the
entrypoint script is Task 2).

**Files:**
- Create: `root/ppg/devel/pgadmin/macros.yaml`
- Create: `root/ppg/devel/pgadmin/containers/project.yaml`
- Create: `root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/Dockerfile`
- Create: `root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/LICENSE`

**Acceptance Criteria:**
- [ ] `python3 -c "import yaml; yaml.safe_load(open('root/ppg/devel/pgadmin/containers/project.yaml'))"` passes; same for `macros.yaml`.
- [ ] Dockerfile contains all three `#!BuildTag` lines, `FROM percona-ubi-minimal:latest`, installs `percona-pgadmin4 percona-pgadmin4-gunicorn percona-postgresql14 … percona-postgresql18`, pins UID 5050, `EXPOSE 8080`, `VOLUME /var/lib/pgadmin`, `USER 5050`, `ENTRYPOINT`.
- [ ] LICENSE is the PostgreSQL licence text from pgAdmin upstream (non-empty, mentions "PostgreSQL").
- [ ] No reference to `common:deps:build` in project.yaml (dropped per spec §7).

**Verify:** `python3 -c "import yaml,sys; yaml.safe_load(open('root/ppg/devel/pgadmin/containers/project.yaml')); yaml.safe_load(open('root/ppg/devel/pgadmin/macros.yaml')); print('yaml OK')"` → `yaml OK`; `grep -c '^#!BuildTag' root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/Dockerfile` → `3`.

**Steps:**

- [ ] **Step 1: macros.yaml**

`root/ppg/devel/pgadmin/macros.yaml`:

```yaml
# Macros for the pgAdmin projects (ppg:devel:pgadmin and its :containers child).
# PGADMIN_VERSION is the single bump knob shared by the container tags; keep it
# in sync with the obs_scm revision (REL-<major>_<minor>) in
# percona-pgadmin4/obs/_service when bumping.
- PGADMIN_VERSION: 9.17
```

- [ ] **Step 2: project.yaml**

`root/ppg/devel/pgadmin/containers/project.yaml` (modelled on
`root/ppg/staging/18/containers/project.yaml`, ubi9 only; the `Prefer:
percona-postgresql18-libs` settles the `libpq.so.5` provider choice that five
co-installed client majors would otherwise leave ambiguous for `python3.12-psycopg-c`):

```yaml
title: Percona pgAdmin 4 container image
description: |
  Container image for pgAdmin 4 (percona-pgadmin4), built from the
  ppg:devel:pgadmin RPMs on UBI 9. Bundles the Percona PostgreSQL client
  binaries for majors 14-18 so pgAdmin's Backup/Restore and external
  Query Tool features work against any supported server version.
  Design: docs/superpowers/specs/2026-09-02-pgadmin4-container-design.md

repositories:
  - name: ubi9
    paths:
      - subproject: ppg:devel:pgadmin
        repository: UBI_9
      - subproject: ppg:staging:18
        repository: UBI_9
      - subproject: ppg:staging:17
        repository: UBI_9
      - subproject: ppg:staging:16
        repository: UBI_9
      - subproject: ppg:staging:15
        repository: UBI_9
      - subproject: ppg:staging:14
        repository: UBI_9
      - subproject: ppg:common:deps
        repository: UBI_9
      - subproject: common:containers:ubi9
        repository: images
      - subproject: common:containers:ubi9
        repository: UBI_9
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}Fedora:EPEL:9
        repository: standard
      - project: ${REMOTE_OBS_ORG_INTERCONNECT}RedHat:UBI-9
        repository: standard
    archs: [x86_64, aarch64]

project-config: |
  Type: docker
  BuildEngine: podman
  BuildFlags: sbom:spdx
  BuildFlags: sbom:cyclonedx
  PublishFlags: withsbom

  Preinstall: skopeo

  ExpandFlags: filterbasecontainerpkgs

  Prefer: redhat-release
  Prefer: glibc-minimal-langpack
  Prefer: gpgme
  Prefer: iptables-nft
  Prefer: percona-postgresql18-libs
  Ignore: rocky-release
  Substitute: rocky-release redhat-release
```

- [ ] **Step 3: Dockerfile**

`root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/Dockerfile`:

```dockerfile
#!UseOBSRepositories
#!BuildVersion: %!{PGADMIN_VERSION}
#!BuildTag: percona-pgadmin4:<VERSION>-<RELEASE>
#!BuildTag: percona-pgadmin4:<VERSION>
#!BuildTag: percona-pgadmin4:latest

FROM percona-ubi-minimal:latest

LABEL name="Percona pgAdmin 4" \
      description="pgAdmin 4 is the leading open source management tool for PostgreSQL. This image runs it in server mode under gunicorn, built from the Percona Distribution for PostgreSQL packages." \
      vendor="Percona" \
      summary="pgAdmin 4 management tool for PostgreSQL" \
      maintainer="Percona Development <info@percona.com>" \
      org.opencontainers.image.authors="info@percona.com"

LABEL version="%!{PGADMIN_VERSION}"
LABEL release="1"

RUN microdnf -y update && \
    microdnf -y install \
        percona-pgadmin4 \
        percona-pgadmin4-gunicorn \
        percona-postgresql14 \
        percona-postgresql15 \
        percona-postgresql16 \
        percona-postgresql17 \
        percona-postgresql18 && \
    microdnf clean all && rm -rf /var/cache/dnf /var/cache/yum

# Pin the sysusers-allocated pgadmin user to upstream's UID 5050, join group 0
# and make the writable trees group-0 writable so an OpenShift-assigned random
# UID (gid 0) can run; group-writable /etc/passwd enables the entrypoint's
# random-UID passwd fixup.
RUN usermod -u 5050 -aG 0 pgadmin && \
    mkdir -p /run/pgadmin && \
    chown -R 5050:0 /var/lib/pgadmin /var/log/pgadmin /run/pgadmin && \
    chmod -R g=u /var/lib/pgadmin /var/log/pgadmin /run/pgadmin && \
    chmod g=u /etc/passwd

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY LICENSE /licenses/LICENSE.Dockerfile

# Overridable defaults: docker/podman -e wins over ENV, and the RPM's
# config_distro.py applies PGADMIN_CONFIG_* at every import (better than
# upstream's bake-once). pg-13 stays unset: no PG 13 in the Percona tree.
ENV PGADMIN_CONFIG_DEFAULT_BINARY_PATHS="{'pg': '/usr/pgsql-18/bin', 'pg-14': '/usr/pgsql-14/bin', 'pg-15': '/usr/pgsql-15/bin', 'pg-16': '/usr/pgsql-16/bin', 'pg-17': '/usr/pgsql-17/bin', 'pg-18': '/usr/pgsql-18/bin'}" \
    PGADMIN_LISTEN_ADDRESS=0.0.0.0 \
    PGADMIN_LISTEN_PORT=8080 \
    HOME=/var/lib/pgadmin

EXPOSE 8080
VOLUME /var/lib/pgadmin

USER 5050

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

- [ ] **Step 4: LICENSE**

```bash
curl -sfL https://raw.githubusercontent.com/pgadmin-org/pgadmin4/REL-9_17/LICENSE \
  -o root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/LICENSE
grep -q "PostgreSQL" root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/LICENSE
```

- [ ] **Step 5: Verify + commit**

```bash
python3 -c "import yaml; yaml.safe_load(open('root/ppg/devel/pgadmin/containers/project.yaml')); yaml.safe_load(open('root/ppg/devel/pgadmin/macros.yaml')); print('yaml OK')"
grep -c '^#!BuildTag' root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/Dockerfile   # → 3
git add root/ppg/devel/pgadmin/macros.yaml root/ppg/devel/pgadmin/containers
git commit -s -m "pgadmin: containers project + percona-pgadmin4 image Dockerfile (SP5)"
```

---

### Task 2: entrypoint.sh (with local bash tests)

**Goal:** The container entrypoint implementing spec §6, tested locally with a bash
harness (no container needed).

**Files:**
- Create: `root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/entrypoint.sh`

**Acceptance Criteria:**
- [ ] `bash -n entrypoint.sh` passes; `shellcheck entrypoint.sh` passes if shellcheck is installed (warnings SC2312-class acceptable, errors not).
- [ ] Local harness (Step 3) passes: `file_env` sets from file, errors when both VAR and VAR_FILE set; first-run guard errors without email/password; TLS guard errors when `PGADMIN_ENABLE_TLS=true` but certs missing.
- [ ] The script ends with `exec /usr/bin/percona-pgadmin4-gunicorn` and never reimplements launcher behavior (no gunicorn invocation, no setup-db when the DB exists).

**Verify:** `bash -n root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/entrypoint.sh && bash $SCRATCH/sp5/test-entrypoint.sh` → all `PASS` lines, no `FAIL`.

**Steps:**

- [ ] **Step 1: Write entrypoint.sh**

```bash
#!/bin/bash
# percona-pgadmin4 container entrypoint.
#
# Prepares the container environment (secrets, first-run setup, servers.json /
# preferences.json import, TLS validation, OpenShift random-UID tolerance) and
# execs the RPM launcher /usr/bin/percona-pgadmin4-gunicorn, which owns the
# gunicorn command line, PGADMIN_LISTEN_*/GUNICORN_* handling and TLS wiring
# (PGADMIN_ENABLE_TLS=true -> /certs/server.cert + /certs/server.key).
#
# Environment honored here (upstream dpage/pgadmin4 names):
#   PGADMIN_DEFAULT_EMAIL, PGADMIN_DEFAULT_PASSWORD[_FILE]
#   PGADMIN_CONFIG_CONFIG_DATABASE_URI[_FILE]
#   PGADMIN_SERVER_JSON_FILE (default /pgadmin4/servers.json)
#   PGADMIN_PREFERENCES_JSON_FILE (default /pgadmin4/preferences.json)
#   PGADMIN_REPLACE_SERVERS_ON_STARTUP ("True" to re-import with --replace)
#   PGADMIN_ENABLE_TLS ("true"; certs must exist in /certs)
set -euo pipefail

PGADMIN_DIR=/usr/lib/python3.12/site-packages/pgadmin4
SQLITE_PATH="${PGADMIN_CONFIG_SQLITE_PATH:-/var/lib/pgadmin/pgadmin4.db}"

# --- OpenShift random-UID fixup -------------------------------------------
# Under an arbitrary UID (gid 0) there is no passwd entry; some libraries need
# one. /etc/passwd is group-0 writable (image build).
if ! whoami >/dev/null 2>&1; then
    if [ -w /etc/passwd ]; then
        echo "pgadmin:x:$(id -u):0:pgadmin user:/var/lib/pgadmin:/sbin/nologin" >> /etc/passwd
    fi
fi

# --- Docker-secret _FILE variants -----------------------------------------
# file_env VAR: honor VAR_FILE by reading VAR's value from the file; VAR and
# VAR_FILE together are an error (upstream semantics).
file_env() {
    local var="$1" fileVar="$1_FILE" val=""
    if [ -n "${!var:-}" ] && [ -n "${!fileVar:-}" ]; then
        echo "error: both ${var} and ${fileVar} are set (but are exclusive)" >&2
        exit 1
    fi
    if [ -n "${!fileVar:-}" ]; then
        if [ ! -r "${!fileVar}" ]; then
            echo "error: ${fileVar} is set to '${!fileVar}' but the file is not readable" >&2
            exit 1
        fi
        val="$(< "${!fileVar}")"
        export "${var}"="${val}"
        unset "${fileVar}"
    fi
}
file_env PGADMIN_DEFAULT_PASSWORD
file_env PGADMIN_CONFIG_CONFIG_DATABASE_URI

# --- External configuration database --------------------------------------
# When CONFIG_DATABASE_URI points at an existing, initialised external config
# DB, first-run setup must not run (and must not demand DEFAULT_EMAIL).
external_config_db_exists="False"
if [ -n "${PGADMIN_CONFIG_CONFIG_DATABASE_URI:-}" ]; then
    result=$(cd "${PGADMIN_DIR}/pgadmin/utils" && /usr/bin/python3.12 -c "
import os, ast
from check_external_config_db import check_external_config_db
raw = os.environ['PGADMIN_CONFIG_CONFIG_DATABASE_URI']
try:
    uri = ast.literal_eval(raw)
except (ValueError, SyntaxError):
    uri = raw
print(check_external_config_db(uri))
" 2>/dev/null) || true
    if [ -n "${result:-}" ]; then
        external_config_db_exists="${result}"
    fi
fi

# --- First-run setup + one-time imports ------------------------------------
if [ ! -e "${SQLITE_PATH}" ] && [ "${external_config_db_exists}" = "False" ]; then
    if [ -z "${PGADMIN_DEFAULT_EMAIL:-}" ] || [ -z "${PGADMIN_DEFAULT_PASSWORD:-}" ]; then
        echo 'You need to define the PGADMIN_DEFAULT_EMAIL and PGADMIN_DEFAULT_PASSWORD or PGADMIN_DEFAULT_PASSWORD_FILE environment variables.' >&2
        exit 1
    fi

    # Same init the launcher would run; the launcher sees the DB afterwards
    # and skips its own first-run branch (no double-init).
    (cd "${PGADMIN_DIR}" && \
        PGADMIN_SETUP_EMAIL="${PGADMIN_DEFAULT_EMAIL}" \
        PGADMIN_SETUP_PASSWORD="${PGADMIN_DEFAULT_PASSWORD}" \
        /usr/bin/python3.12 setup.py setup-db)

    server_json="${PGADMIN_SERVER_JSON_FILE:-/pgadmin4/servers.json}"
    if [ -f "${server_json}" ]; then
        /usr/bin/pgadmin4-cli load-servers "${server_json}" --user "${PGADMIN_DEFAULT_EMAIL}"
    fi

    prefs_json="${PGADMIN_PREFERENCES_JSON_FILE:-/pgadmin4/preferences.json}"
    if [ -f "${prefs_json}" ]; then
        /usr/bin/pgadmin4-cli set-prefs "${PGADMIN_DEFAULT_EMAIL}" --input-file "${prefs_json}"
    fi
elif [ "${PGADMIN_REPLACE_SERVERS_ON_STARTUP:-}" = "True" ]; then
    server_json="${PGADMIN_SERVER_JSON_FILE:-/pgadmin4/servers.json}"
    if [ -f "${server_json}" ]; then
        /usr/bin/pgadmin4-cli load-servers "${server_json}" --user "${PGADMIN_DEFAULT_EMAIL}" --replace
    fi
fi

# --- TLS pre-flight ---------------------------------------------------------
# The launcher wires the certs; fail early and clearly when they are missing.
if [ "${PGADMIN_ENABLE_TLS:-}" = "true" ]; then
    if [ ! -r /certs/server.cert ] || [ ! -r /certs/server.key ]; then
        echo 'PGADMIN_ENABLE_TLS is set but /certs/server.cert and/or /certs/server.key are missing or unreadable.' >&2
        exit 1
    fi
fi

exec /usr/bin/percona-pgadmin4-gunicorn
```

- [ ] **Step 2: Syntax checks**

```bash
bash -n root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/entrypoint.sh
command -v shellcheck >/dev/null && shellcheck root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/entrypoint.sh || echo "shellcheck not installed, skipped"
```

- [ ] **Step 3: Local harness (scratchpad, throwaway)**

Write `$SCRATCH/sp5/test-entrypoint.sh` and run it. It stubs the binaries the script
calls and exercises the pure-bash paths (no container):

```bash
#!/bin/bash
# Harness for entrypoint.sh's bash logic. Stubs /usr/bin binaries via PATH and
# a fake PGADMIN_DIR; each case runs the entrypoint in a subshell.
set -u
EP=root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/entrypoint.sh
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/pgadmin4/pgadmin/utils" "$T/data"
cat > "$T/bin/percona-pgadmin4-gunicorn" <<'EOF'
#!/bin/bash
echo "LAUNCHER EXEC"
EOF
cat > "$T/bin/pgadmin4-cli" <<'EOF'
#!/bin/bash
echo "CLI $*"
EOF
cat > "$T/bin/python3.12" <<'EOF'
#!/bin/bash
# stub: setup.py setup-db creates the db file
if [[ "$*" == *"setup-db"* ]]; then touch "${FAKE_DB}"; fi
echo "PY $*"
EOF
chmod +x "$T/bin/"*
run_ep() { (
    export PATH="$T/bin:$PATH" FAKE_DB="$T/data/pgadmin4.db" \
           PGADMIN_CONFIG_SQLITE_PATH="$T/data/pgadmin4.db"
    sed -e 's|/usr/bin/percona-pgadmin4-gunicorn|percona-pgadmin4-gunicorn|' \
        -e 's|/usr/bin/pgadmin4-cli|pgadmin4-cli|' \
        -e 's|/usr/bin/python3.12|python3.12|' \
        -e "s|PGADMIN_DIR=/usr/lib/python3.12/site-packages/pgadmin4|PGADMIN_DIR=$T/pgadmin4|" "$EP" > "$T/ep-under-test.sh"
    bash "$T/ep-under-test.sh"
) }
pass=0; fail=0
check() { local name="$1" want="$2" got="$3"
  if [[ "$got" == *"$want"* ]]; then echo "PASS: $name"; pass=$((pass+1));
  else echo "FAIL: $name — wanted '$want' in: $got"; fail=$((fail+1)); fi }

# 1. no email/password on first run -> error
out=$(run_ep 2>&1); check "first-run guard" "PGADMIN_DEFAULT_EMAIL" "$out"
# 2. password via _FILE + email -> setup + exec
echo secretpw > "$T/pw"
out=$(PGADMIN_DEFAULT_EMAIL=a@b.c PGADMIN_DEFAULT_PASSWORD_FILE="$T/pw" run_ep 2>&1)
check "file_env + setup + exec" "LAUNCHER EXEC" "$out"
check "setup-db ran" "PY setup.py setup-db" "$out"
# 3. both VAR and VAR_FILE -> error
out=$(PGADMIN_DEFAULT_EMAIL=a@b.c PGADMIN_DEFAULT_PASSWORD=x PGADMIN_DEFAULT_PASSWORD_FILE="$T/pw" run_ep 2>&1)
check "exclusive VAR/VAR_FILE" "exclusive" "$out"
# 4. second boot (db exists) -> straight exec, no setup
out=$(PGADMIN_DEFAULT_EMAIL=a@b.c PGADMIN_DEFAULT_PASSWORD=x run_ep 2>&1)
check "idempotent boot" "LAUNCHER EXEC" "$out"
[[ "$out" != *"setup-db"* ]] && { echo "PASS: no re-init"; pass=$((pass+1)); } || { echo "FAIL: re-init ran"; fail=$((fail+1)); }
# 5. TLS enabled without certs -> error
out=$(PGADMIN_DEFAULT_EMAIL=a@b.c PGADMIN_DEFAULT_PASSWORD=x PGADMIN_ENABLE_TLS=true run_ep 2>&1)
check "TLS pre-flight" "/certs/server.cert" "$out"
# 6. servers.json import on first run
rm -f "$T/data/pgadmin4.db"; echo '{}' > "$T/servers.json"
out=$(PGADMIN_DEFAULT_EMAIL=a@b.c PGADMIN_DEFAULT_PASSWORD=x PGADMIN_SERVER_JSON_FILE="$T/servers.json" run_ep 2>&1)
check "servers.json import" "CLI load-servers $T/servers.json --user a@b.c" "$out"
echo "---- $pass passed, $fail failed"; exit $((fail>0))
```

Run: `bash $SCRATCH/sp5/test-entrypoint.sh` → `6+ PASS`, `0 failed`.

- [ ] **Step 4: Commit**

```bash
git add root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/entrypoint.sh
git commit -s -m "pgadmin: container entrypoint (secrets, imports, TLS pre-flight, OpenShift fixup)"
```

---

### Task 3: Sync + OBS image build loop (controller-driven)

**Goal:** The containers project and image build green in the PR #12 OBS project, and
a runnable image artifact is obtained locally.

**Files:**
- Modify (only if the loop finds defects): files under
  `root/ppg/devel/pgadmin/containers/`; possibly `root/ppg/devel/pgadmin/macros.yaml`.

**Acceptance Criteria:**
- [ ] `sync push --dry-run` green for `ppg:devel:pgadmin:containers percona-pgadmin4` with `-P isv-pr`.
- [ ] User informed that PR #12 needs the `ubi9-images` label (in addition to `UBI_9`) before the check run; label added by the user.
- [ ] After push (user-approved) and PR check: `osc results isv:percona:PR:pr-12:ppg:devel:pgadmin:containers` shows `succeeded` for `percona-pgadmin4` on `ubi9` x86_64 (aarch64 too unless worker constraints say otherwise — record either way).
- [ ] A local image exists: `podman images` shows `percona-pgadmin4` loaded either via `podman pull` from the OBS registry (if the PR project publishes there) or via `osc getbinaries` + `podman load` — the working mechanism recorded in the ledger.

**Verify:** `venv/bin/osc -A https://api.opensuse.org results isv:percona:PR:pr-12:ppg:devel:pgadmin:containers --csv | grep percona-pgadmin4` → `succeeded`; `podman images --format '{{.Repository}}:{{.Tag}}' | grep percona-pgadmin4` → at least one tag.

**Steps:**

- [ ] **Step 1: Local dry-run**

```bash
venv/bin/python -m percona_obs -P isv-pr sync push --dry-run ppg:devel:pgadmin:containers percona-pgadmin4
```
Expected: project config + package staged, Dockerfile macro-rendered (`%!{PGADMIN_VERSION}` → `9.17`), `sync successful (dry run)`.

- [ ] **Step 2: Ask the user** (single question): approve the push AND add the
`ubi9-images` label to PR #12 (the `<flavor>-images` label maps to the new
`:containers` layout via `_IMAGES_REPO_RE`; without it the PR sync filters the
containers project out).

- [ ] **Step 3: Push, watch the PR check run, then watch OBS**

```bash
git push percona pgadmin-sp1
gh run list --repo percona/obs-packaging --branch pgadmin-sp1 --limit 1
# then the usual settle watch on isv:percona:PR:pr-12:ppg:devel:pgadmin:containers
```

- [ ] **Step 4: Fix loop** — any Dockerfile/prjconf failure (unresolvable install
closure, `have choice` provider errors, usermod UID collision → switch to `usermod -o`,
missing `Prefer:`) is fixed in `root/ppg/devel/pgadmin/containers/`, committed as
`pgadmin: fix <what> (image build)`, pushed with per-push user approval, until green.

- [ ] **Step 5: Obtain the image locally**

```bash
# probe the registry first (published PR container repos land here when enabled):
podman pull registry.opensuse.org/isv/percona/pr/pr-12/ppg/devel/pgadmin/containers/percona-pgadmin4:latest \
  || { venv/bin/osc -A https://api.opensuse.org getbinaries \
         isv:percona:PR:pr-12:ppg:devel:pgadmin:containers percona-pgadmin4 ubi9 x86_64 --destdir "$SCRATCH/sp5/bins"; \
       podman load -i "$SCRATCH/sp5/bins"/*.tar* ; }
```
Record which path worked in the ledger (spec §8 open item).

---

### Task 4: Container smoke matrix (podman)

**Goal:** Prove the OBS-built image behaves per the spec's runtime contract.

**USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Files:**
- Create: `$SCRATCH/sp5/smoke-image.sh` (scratch only; a failure here is an image
  defect → fix under `root/ppg/devel/pgadmin/containers/` via Task 3's loop).

**Acceptance Criteria:**
- [ ] T1 basic: `PGADMIN_DEFAULT_EMAIL/PASSWORD` → `HTTP 200` from `/login`, page marker `ver=91700`, restart of the same container volume boots without re-init (`SETUP OK` once).
- [ ] T2 secrets: `PGADMIN_DEFAULT_PASSWORD_FILE` works (`HTTP 200`); setting both PASSWORD and PASSWORD_FILE exits non-zero with the "exclusive" error.
- [ ] T3 servers.json: mounted file → `SERVERS IMPORTED` (sqlite row count ≥ 1 in the `server` table of `pgadmin4.db`).
- [ ] T4 TLS: mounted self-signed pair + `PGADMIN_ENABLE_TLS=true` → `curl -k https://…/login` returns 200; missing certs case exits non-zero with the pre-flight message.
- [ ] T5 binaries: all of `/usr/pgsql-{14..18}/bin/pg_dump` exist in the image AND `python3.12 -P -c "import config; print(config.DEFAULT_BINARY_PATHS['pg-16'])"` prints `/usr/pgsql-16/bin`.
- [ ] T6 OpenShift: `podman run --user 12345:0 …` reaches `HTTP 200` (passwd fixup path).
- [ ] Output captured to `$SCRATCH/sp5/smoke-image.log`; ledger quotes each T1–T6 token and the image tag/digest tested.

**Verify:** `bash $SCRATCH/sp5/smoke-image.sh 2>&1 | tee $SCRATCH/sp5/smoke-image.log | grep -E '^(T[1-6]) (PASS|FAIL)'` → six `PASS`, zero `FAIL`.

```json:metadata
{"files": ["root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/Dockerfile", "root/ppg/devel/pgadmin/containers/percona-pgadmin4/obs/entrypoint.sh"], "verifyCommand": "bash $SCRATCH/sp5/smoke-image.sh 2>&1 | tee $SCRATCH/sp5/smoke-image.log | grep -E '^(T[1-6]) (PASS|FAIL)'", "acceptanceCriteria": ["T1 login 200 + ver=91700 + idempotent restart", "T2 password _FILE works, both-set errors", "T3 servers.json imported (sqlite row)", "T4 TLS serves https 200, missing certs errors", "T5 pg_dump 14-18 present + DEFAULT_BINARY_PATHS resolves", "T6 --user 12345:0 boots to 200"], "userGate": true, "tags": ["user-gate"], "modelTier": "standard"}
```

**Steps:**

- [ ] **Step 1: Write `$SCRATCH/sp5/smoke-image.sh`**

The script runs each case against the locally loaded image (`IMG` env, default the
tag loaded in Task 3), using a helper that starts a container, polls
`http://127.0.0.1:PORT/login` (or https for T4) up to 90 s, and prints
`T<n> PASS`/`T<n> FAIL reason`:

```bash
#!/bin/bash
set -u
IMG="${IMG:-localhost/percona-pgadmin4:latest}"
D=$(mktemp -d); trap 'rm -rf "$D"' EXIT
EM=admin@example.com PW='Sm0keTest!pw'
wait_http() { # url insecure_flag
  for _ in $(seq 1 45); do
    code=$(curl -s ${2:-} -o "$D/page" -w '%{http_code}' "$1" 2>/dev/null) && [ "$code" = 200 ] && return 0
    sleep 2
  done; return 1
}
run() { podman run -d --rm "$@" "$IMG"; }

# T1 basic + idempotent restart
podman volume create sp5t1 >/dev/null
c=$(run -p 18081:8080 -v sp5t1:/var/lib/pgadmin -e PGADMIN_DEFAULT_EMAIL=$EM -e PGADMIN_DEFAULT_PASSWORD=$PW)
if wait_http http://127.0.0.1:18081/login && grep -q 'ver=91700' "$D/page"; then
  podman stop "$c" >/dev/null
  c=$(run -p 18081:8080 -v sp5t1:/var/lib/pgadmin -e PGADMIN_DEFAULT_EMAIL=$EM -e PGADMIN_DEFAULT_PASSWORD=$PW)
  wait_http http://127.0.0.1:18081/login && echo "T1 PASS" || echo "T1 FAIL restart"
else echo "T1 FAIL first boot"; fi
podman stop "$c" >/dev/null 2>&1; podman volume rm sp5t1 >/dev/null 2>&1

# T2 secrets
echo -n "$PW" > "$D/pwfile"
c=$(run -p 18082:8080 -v "$D/pwfile:/run/secrets/pw:ro,z" -e PGADMIN_DEFAULT_EMAIL=$EM -e PGADMIN_DEFAULT_PASSWORD_FILE=/run/secrets/pw)
wait_http http://127.0.0.1:18082/login && echo "T2a PASS" || echo "T2 FAIL file"
podman stop "$c" >/dev/null 2>&1
out=$(podman run --rm -v "$D/pwfile:/run/secrets/pw:ro,z" -e PGADMIN_DEFAULT_EMAIL=$EM -e PGADMIN_DEFAULT_PASSWORD=$PW -e PGADMIN_DEFAULT_PASSWORD_FILE=/run/secrets/pw "$IMG" 2>&1)
[ $? -ne 0 ] && echo "$out" | grep -q exclusive && echo "T2 PASS" || echo "T2 FAIL exclusive"

# T3 servers.json
cat > "$D/servers.json" <<'EOF'
{"Servers": {"1": {"Name": "smoke", "Group": "Servers", "Host": "db.example.com", "Port": 5432, "Username": "postgres", "MaintenanceDB": "postgres", "SSLMode": "prefer"}}}
EOF
podman volume create sp5t3 >/dev/null
c=$(run -p 18083:8080 -v sp5t3:/var/lib/pgadmin -v "$D/servers.json:/pgadmin4/servers.json:ro,z" -e PGADMIN_DEFAULT_EMAIL=$EM -e PGADMIN_DEFAULT_PASSWORD=$PW)
wait_http http://127.0.0.1:18083/login
n=$(podman exec "$c" python3.12 -P -c "import sqlite3; print(sqlite3.connect('/var/lib/pgadmin/pgadmin4.db').execute('select count(*) from server').fetchone()[0])")
[ "${n:-0}" -ge 1 ] && echo "T3 PASS" || echo "T3 FAIL count=$n"
podman stop "$c" >/dev/null 2>&1; podman volume rm sp5t3 >/dev/null 2>&1

# T4 TLS
mkdir -p "$D/certs"
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=localhost" \
  -keyout "$D/certs/server.key" -out "$D/certs/server.cert" >/dev/null 2>&1
chmod 644 "$D/certs/"*
c=$(run -p 18084:8080 -v "$D/certs:/certs:ro,z" -e PGADMIN_ENABLE_TLS=true -e PGADMIN_DEFAULT_EMAIL=$EM -e PGADMIN_DEFAULT_PASSWORD=$PW)
wait_http https://127.0.0.1:18084/login -k && echo "T4a PASS" || echo "T4 FAIL https"
podman stop "$c" >/dev/null 2>&1
out=$(podman run --rm -e PGADMIN_ENABLE_TLS=true -e PGADMIN_DEFAULT_EMAIL=$EM -e PGADMIN_DEFAULT_PASSWORD=$PW "$IMG" 2>&1)
[ $? -ne 0 ] && echo "$out" | grep -q '/certs/server.cert' && echo "T4 PASS" || echo "T4 FAIL missing-certs"

# T5 binaries
ok=1
for v in 14 15 16 17 18; do podman run --rm --entrypoint /bin/ls "$IMG" "/usr/pgsql-$v/bin/pg_dump" >/dev/null || ok=0; done
bp=$(podman run --rm --entrypoint /usr/bin/python3.12 --workdir /usr/lib/python3.12/site-packages/pgadmin4 "$IMG" -c "import config; print(config.DEFAULT_BINARY_PATHS['pg-16'])")
[ "$ok" = 1 ] && [ "$bp" = "/usr/pgsql-16/bin" ] && echo "T5 PASS" || echo "T5 FAIL ok=$ok bp=$bp"

# T6 OpenShift random UID
c=$(run -p 18086:8080 --user 12345:0 -e PGADMIN_DEFAULT_EMAIL=$EM -e PGADMIN_DEFAULT_PASSWORD=$PW)
wait_http http://127.0.0.1:18086/login && echo "T6 PASS" || echo "T6 FAIL"
podman stop "$c" >/dev/null 2>&1
```

- [ ] **Step 2: Run + capture**

```bash
bash $SCRATCH/sp5/smoke-image.sh 2>&1 | tee $SCRATCH/sp5/smoke-image.log | grep -E '^(T[1-6]a? )(PASS|FAIL)'
```
Expected: `T1..T6 PASS` (T2a/T4a are intermediate sub-checks), zero FAIL.

- [ ] **Step 3: Defects** — a FAIL is an image/entrypoint defect: fix under
`root/ppg/devel/pgadmin/containers/`, commit `pgadmin: fix <what> (image smoke)`, hand
to Task 3's push/build loop (per-push approval), re-run the whole matrix. Do not edit
the smoke script to pass.

- [ ] **Step 4: Ledger** — append log path, the six PASS tokens, image tag + digest
(`podman image inspect --format '{{.Digest}}' $IMG`).

---

### Task 5: Records — spec outcomes, PR #12, memory

**Goal:** Spec §8/§9 get the observed outcomes; PR #12 body gains the SP5 section;
memory updated.

**Files:**
- Modify: `docs/superpowers/specs/2026-09-02-pgadmin4-container-design.md`
- Modify (remote, with approval): PR #12 body via `gh pr edit`.

**Acceptance Criteria:**
- [ ] Spec gains an `### Outcomes (<date>)` section: fix rounds + causes, final OBS result, image size per arch, which acquisition path worked (registry vs getbinaries), the six smoke tokens with the log path, decisions changed during execution (or "none").
- [ ] The spec no longer states anything the delivered image contradicts (sweep: `usermod`, `Prefer`, `common:deps:build`, port, UID).
- [ ] PR #12 body has an "SP5 — container image" section (user-approved edit; no labels touched, no attribution).
- [ ] Committed `docs: SP5 outcomes` and pushed with approval; memory file updated with SP5 status.

**Verify:** `grep -n "Outcomes" docs/superpowers/specs/2026-09-02-pgadmin4-container-design.md` → one hit; `gh pr view 12 --repo percona/obs-packaging --json body -q .body | grep -c "SP5"` → ≥ 1.

**Steps:**

- [ ] **Step 1:** Append Outcomes to the spec (fill every value from the ledger/logs —
a placeholder left in the committed spec is a defect), amend any contradicted line.
- [ ] **Step 2:** `git add … && git commit -s -m "docs: SP5 outcomes (image build, smoke matrix)"`.
- [ ] **Step 3:** Draft the PR-body SP5 section into `$SCRATCH/sp5/pr12-body.md`
(fetch current body first), ask the user, then `gh pr edit 12 --repo
percona/obs-packaging --body-file …`.
- [ ] **Step 4:** Update
`~/.claude/projects/-home-rdias-Work-percona-obs-packaging/memory/pgadmin4-ubi9-effort.md`
with SP5 completion status.
