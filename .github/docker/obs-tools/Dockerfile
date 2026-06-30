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

# Base tools + Go compiler + libarchive
# golang-go: required by obs-service-go_modules (runs `go mod download/vendor/verify`)
# libarchive13t64: C library required by the libarchive-c Python binding used by go_modules
# perl: required by obs-service-set-version (Perl script)
# build-essential: C compiler/headers for any pip packages that compile C extensions
# libssl3t64/libzstd1: runtime libs the cargo_vendor binary links against
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg git jq sudo \
        python3 python3-venv python3-pip \
        golang-go libarchive13t64 build-essential perl wget \
        libssl3t64 libzstd1 \
    && rm -rf /var/lib/apt/lists/*

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
RUN . /etc/os-release && \
    REPO_URL="https://download.opensuse.org/repositories/openSUSE:/Tools/xUbuntu_${VERSION_ID}" && \
    curl -fsSL "${REPO_URL}/Release.key" | gpg --dearmor > /usr/share/keyrings/obs-tools.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/obs-tools.gpg] ${REPO_URL}/ ./" \
      > /etc/apt/sources.list.d/obs-tools.list && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        obs-service-tar-scm obs-service-recompress \
        obs-service-set-version obs-service-download-url \
    && rm -rf /var/lib/apt/lists/*

# obs-service-go_modules (Python script, not packaged for Ubuntu)
RUN TMP=$(mktemp -d) && \
    git clone --depth=1 https://github.com/openSUSE/obs-service-go_modules.git "$TMP" && \
    install -m 755 "$TMP/go_modules" /usr/lib/obs/service/go_modules && \
    rm -rf "$TMP"

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
ENV PATH="/root/.cargo/bin:${PATH}"
