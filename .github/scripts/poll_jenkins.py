#!/usr/bin/env python3
"""Poll a Jenkins job queue item until the build completes, then report the result.

Prints BUILD_URL and BUILD_RESULT to stdout when the build finishes.
Exits 0 on SUCCESS, 1 on any other result or timeout.

Required environment variables:
  JENKINS_URL           Jenkins base URL (e.g. https://ci.example.com)
  JENKINS_USER          Jenkins username for Basic auth
  JENKINS_API_TOKEN     Jenkins API token for Basic auth
  JENKINS_QUEUE_URL     Queue item URL from buildWithParameters Location header

Optional environment variables:
  JENKINS_POLL_TIMEOUT  Total seconds to wait for the build (default: 3600)
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

jenkins_url = os.environ["JENKINS_URL"].rstrip("/")
jenkins_user = os.environ["JENKINS_USER"]
jenkins_token = os.environ["JENKINS_API_TOKEN"]
queue_url = os.environ["JENKINS_QUEUE_URL"].rstrip("/") + "/"
timeout = int(os.environ.get("JENKINS_POLL_TIMEOUT", "3600"))

_creds = base64.b64encode(f"{jenkins_user}:{jenkins_token}".encode()).decode()
_auth_header = {"Authorization": f"Basic {_creds}"}


def _api_get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_auth_header)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {body[:200]}") from e


deadline = time.monotonic() + timeout

# Phase 1: wait for the queued item to become an active build
print(f"Waiting for Jenkins build to start: {queue_url}", flush=True)
build_url: str | None = None
while time.monotonic() < deadline:
    try:
        data = _api_get(queue_url + "api/json")
    except Exception as exc:
        print(f"Warning: queue poll error: {exc}", file=sys.stderr, flush=True)
        time.sleep(10)
        continue
    if data.get("cancelled"):
        print("Build was cancelled in queue", file=sys.stderr)
        sys.exit(1)
    executable = data.get("executable")
    if executable:
        build_url = executable["url"].rstrip("/") + "/"
        print(f"Build started: {build_url}", flush=True)
        break
    time.sleep(10)

if build_url is None:
    print("Timeout waiting for Jenkins build to start", file=sys.stderr)
    sys.exit(1)

# Phase 2: poll the build until it reaches a terminal state
print(f"Polling build result: {build_url}", flush=True)
while time.monotonic() < deadline:
    try:
        data = _api_get(build_url + "api/json")
    except Exception as exc:
        print(f"Warning: build poll error: {exc}", file=sys.stderr, flush=True)
        time.sleep(30)
        continue
    result = data.get("result")
    if result is not None:
        print(f"BUILD_URL={build_url}")
        print(f"BUILD_RESULT={result}")
        sys.exit(0 if result == "SUCCESS" else 1)
    time.sleep(30)

print("Timeout waiting for Jenkins build to complete", file=sys.stderr)
sys.exit(1)
