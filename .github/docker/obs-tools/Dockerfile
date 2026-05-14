FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Base tools + Go compiler + libarchive
# golang-go: required by obs-service-go_modules (runs `go mod download/vendor/verify`)
# libarchive13t64: C library required by the libarchive-c Python binding used by go_modules
# perl: required by obs-service-set-version (Perl script)
# build-essential: C compiler/headers for any pip packages that compile C extensions
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg git jq sudo \
        python3.11 python3.11-venv python3-pip \
        golang-go libarchive13t64 build-essential perl \
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
RUN python3.11 -m venv /opt/obs-tools/venv && \
    /opt/obs-tools/venv/bin/pip install --quiet --upgrade pip && \
    /opt/obs-tools/venv/bin/pip install --quiet -r /tmp/obs-tools-requirements.txt && \
    /opt/obs-tools/venv/bin/pip install --quiet libarchive-c && \
    rm /tmp/obs-tools-requirements.txt

# Put venv bin first so `python3`, `python`, `pip` in any step resolve here.
# go_modules' shebang (#!/usr/bin/env python3) picks up the venv Python too.
ENV PATH="/opt/obs-tools/venv/bin:${PATH}"
