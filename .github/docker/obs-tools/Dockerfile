# ---- cargo-builder stage: compile obs-service-cargo (cargo_vendor) ----
# Build artifacts (object files, registry cache) stay in this throwaway stage.
# The final image receives the compiled binary AND the minimal rust toolchain:
# cargo_vendor shells out to `cargo`/`rustc` at runtime, and the crate lockfiles
# it vendors are lockfile v4 (need cargo >= 1.78, newer than Ubuntu's apt 1.75).
FROM ubuntu:24.04 AS cargo-builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        build-essential curl git ca-certificates \
        libssl-dev libzstd-dev pkgconf && \
    rm -rf /var/lib/apt/lists/*

# --profile minimal: rustc + rust-std + cargo only (no docs/clippy) to keep the
# toolchain we copy into the final image small.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

# release-stripped: upstream's release profile + strip=true (no debug symbols).
RUN git clone --depth=1 https://github.com/openSUSE-Rust/obs-service-cargo.git /tmp/obs-service-cargo && \
    cd /tmp/obs-service-cargo && \
    cargo build --profile release-stripped

# ---- final image ----
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Base tools + libarchive
# libarchive13t64: C library required by the libarchive-c Python binding used by go_modules
# perl: required by obs-service-set-version (Perl script)
# build-essential: C compiler/headers for any pip packages that compile C extensions
# libssl3t64/libzstd1: runtime libs the cargo_vendor binary links against
# cpio: percona-obs extracts obs_scm .obscpio archives locally, and the
#       npm_lockfile service unpacks them before running npm
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg git jq sudo cpio \
        python3 python3-venv python3-pip \
        libarchive13t64 build-essential perl wget \
        libssl3t64 libzstd1 \
    && rm -rf /var/lib/apt/lists/*

# Pinned Go toolchain — required by obs-service-go_modules (runs
# `go mod download/vendor/verify`).  This is the SAME upstream tarball the
# golang-1.26 OBS package (root/common/deps/build/golang-1.26) repackages,
# versioned by the same GOLANG_VERSION macro in root/macros.yaml (passed as
# a build-arg by build-obs-image.yml).  GOTOOLCHAIN=local forbids go from
# auto-downloading a different toolchain per module go.mod, so
# `go mod vendor` output — and therefore the vendor tarballs the go_modules
# service uploads to OBS — can only change when GOLANG_VERSION is bumped
# deliberately.  If an upstream module starts requiring a newer Go,
# vendoring fails loudly instead of silently switching toolchains.
ARG GO_VERSION
RUN if [ -z "$GO_VERSION" ]; then \
        echo "GO_VERSION build-arg is required (from GOLANG_VERSION in root/macros.yaml)" >&2; \
        exit 1; \
    fi && \
    curl -fsSL "https://dl.google.com/go/go${GO_VERSION}.linux-$(dpkg --print-architecture).tar.gz" \
      | tar -C /usr/local -xz && \
    /usr/local/go/bin/go version
ENV PATH="/usr/local/go/bin:${PATH}" \
    GOTOOLCHAIN=local

# GitHub CLI — used in sync-main (create tags, push badge), obs-release
# (gh release create/edit), obs-stale-cleanup (gh pr list/comment),
# obs-pr-cleanup (gh pr view).  Not pre-installed on ubuntu:24.04 base image.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends gh && \
    rm -rf /var/lib/apt/lists/*

# openSUSE Tools repo → OBS service binaries
# obs-service-recompress pulls in its own compression library deps via apt.
# obs-service-node-modules: vendors npm dependencies (node_modules.obscpio +
# node_modules.spec.inc) from a package-lock.json; runs under /usr/bin/python3
# and needs python3-lxml.
RUN . /etc/os-release && \
    REPO_URL="https://download.opensuse.org/repositories/openSUSE:/Tools/xUbuntu_${VERSION_ID}" && \
    curl -fsSL "${REPO_URL}/Release.key" | gpg --dearmor > /usr/share/keyrings/obs-tools.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/obs-tools.gpg] ${REPO_URL}/ ./" \
      > /etc/apt/sources.list.d/obs-tools.list && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        obs-service-tar-scm obs-service-recompress \
        obs-service-set-version obs-service-download-url \
        obs-service-node-modules python3-lxml \
    && rm -rf /var/lib/apt/lists/*

# obs-service-go_modules (Python script, not packaged for Ubuntu)
RUN TMP=$(mktemp -d) && \
    git clone --depth=1 https://github.com/openSUSE/obs-service-go_modules.git "$TMP" && \
    install -m 755 "$TMP/go_modules" /usr/lib/obs/service/go_modules && \
    rm -rf "$TMP"

# Node.js 22 + npm — required by the repo-owned npm_lockfile service
# (tools/obs-services), which generates package-lock.json for packages whose
# frontend dependencies are vendored with node_modules (pgAdmin 4).  Major 22
# matches the nodejs:22 module stream those packages build against on UBI_9
# (ExpandFlags in root/ppg/devel/pgadmin/project.yaml) — bump both together.
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor -o /usr/share/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
      > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    node --version && npm --version

# npm_lockfile — repo-owned OBS-style service (tools/obs-services/README.md).
# Stdlib-only Python; its #!/usr/bin/env python3 resolves to the venv below.
COPY --chmod=755 tools/obs-services/npm_lockfile /usr/lib/obs/service/npm_lockfile
COPY --chmod=644 tools/obs-services/npm_lockfile.service /usr/lib/obs/service/npm_lockfile.service

# Python venv with all percona-obs dependencies
# Baked at /opt/obs-tools/venv; obs-setup symlinks $GITHUB_WORKSPACE/venv here
# so all existing `venv/bin/python -m percona_obs ...` calls work unchanged.
COPY requirements.txt /tmp/obs-tools-requirements.txt
RUN python3 -m venv /opt/obs-tools/venv && \
    /opt/obs-tools/venv/bin/pip install --quiet --upgrade pip && \
    /opt/obs-tools/venv/bin/pip install --quiet -r /tmp/obs-tools-requirements.txt && \
    /opt/obs-tools/venv/bin/pip install --quiet libarchive-c && \
    rm /tmp/obs-tools-requirements.txt

# Put venv bin first so `python3`, `python`, `pip` in any step resolve here.
# go_modules' shebang (#!/usr/bin/env python3) picks up the venv Python too.
ENV PATH="/opt/obs-tools/venv/bin:${PATH}"

# actions/checkout (a JS action) runs on the host runner, so its safe.directory
# setting goes into the host's git config, not the container's.  Without this,
# git refuses to operate in the mounted workspace and commands like
# `git diff origin/main...HEAD` fail with "Could not access ...".
RUN git config --system --add safe.directory '*'

# obs-service-cargo_vendor — built in the cargo-builder stage above.
# Vendors Cargo dependencies into the source tree.
COPY --from=cargo-builder /tmp/obs-service-cargo/target/release-stripped/cargo_vendor /usr/lib/obs/service/cargo_vendor
COPY --from=cargo-builder /tmp/obs-service-cargo/cargo_vendor.service /usr/lib/obs/service/cargo_vendor.service

# Rust toolchain cargo_vendor invokes at runtime. Copied from the builder stage
# (recent cargo, lockfile v4 capable) rather than apt (1.75, too old). .cargo/bin
# holds the rustup proxies; .rustup holds the actual toolchain. The build-time
# registry cache under .cargo/registry is intentionally NOT copied.
COPY --from=cargo-builder /root/.cargo/bin /root/.cargo/bin
COPY --from=cargo-builder /root/.rustup /root/.rustup
# Pin RUSTUP_HOME/CARGO_HOME to absolute paths: the copied cargo/rustc are
# rustup proxies that find the toolchain (and its default) under $HOME/.rustup,
# but GitHub Actions container jobs set HOME=/github/home, not /root — without
# this, rustup reports "no default toolchain configured".
ENV RUSTUP_HOME="/root/.rustup" \
    CARGO_HOME="/root/.cargo" \
    PATH="/root/.cargo/bin:${PATH}"
