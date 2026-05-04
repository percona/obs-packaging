"""Jenkins HTTP client used by `percona-obs qa`.

Stdlib-only (urllib + json + base64) so we do not pull in `requests`.
Mirrors the wire format of the curl-based trigger and queue/build polling
that `.github/workflows/obs-pr-qa.yml` and `.github/scripts/poll_jenkins.py`
used to perform.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

from .common import _PROFILES_DIR, logger


@dataclasses.dataclass
class JenkinsConfig:
    url: str
    user: str
    token: str

    @property
    def auth_header(self) -> dict[str, str]:
        creds = base64.b64encode(f"{self.user}:{self.token}".encode()).decode()
        return {"Authorization": f"Basic {creds}"}


def load_jenkins_config(profile_name: str | None) -> JenkinsConfig:
    """Resolve Jenkins URL + user + token.

    Precedence: env vars (JENKINS_URL, JENKINS_USER, JENKINS_API_TOKEN) override
    the optional ``jenkins:`` section of ``.profile/<name>.yaml``. The token is
    only ever read from the environment, never the profile.
    """
    url = os.environ.get("JENKINS_URL", "")
    user = os.environ.get("JENKINS_USER", "")
    token = os.environ.get("JENKINS_API_TOKEN", "")

    if profile_name and (not url or not user):
        path = _PROFILES_DIR / f"{profile_name}.yaml"
        if path.is_file():
            with path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            jcfg = data.get("jenkins") if isinstance(data, dict) else None
            if isinstance(jcfg, dict):
                if not url:
                    url = str(jcfg.get("url") or "")
                if not user:
                    user = str(jcfg.get("user") or "")

    missing: list[str] = []
    if not url:
        missing.append("JENKINS_URL (env) or jenkins.url (profile)")
    if not user:
        missing.append("JENKINS_USER (env) or jenkins.user (profile)")
    if not token:
        missing.append("JENKINS_API_TOKEN (env)")
    if missing:
        raise SystemExit("error: missing Jenkins credentials: " + ", ".join(missing))

    return JenkinsConfig(url=url.rstrip("/"), user=user, token=token)


def trigger(cfg: JenkinsConfig, job: str, params: dict[str, str]) -> str:
    """POST ``buildWithParameters`` and return the queue item URL.

    Returns the value of the ``Location`` response header (with a trailing
    slash), which Jenkins uses to identify the queued build. Raises
    RuntimeError on any non-201 response.
    """
    url = f"{cfg.url}/job/{urllib.parse.quote(job)}/buildWithParameters"
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            **cfg.auth_header,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            location = resp.headers.get("Location")
            if not location:
                raise RuntimeError(
                    f"Jenkins {url}: status {resp.status} but no Location header"
                )
            return location.rstrip("/") + "/"
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Jenkins {url}: HTTP {e.code}: {body_text[:200]}") from e


def _api_get(url: str, cfg: JenkinsConfig) -> dict:
    req = urllib.request.Request(url, headers=cfg.auth_header)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {body[:200]}") from e


def wait_for_start(cfg: JenkinsConfig, queue_url: str, timeout: int = 3600) -> str:
    """Poll a Jenkins queue item until the build starts; return the build URL.

    Raises RuntimeError if the queue item is cancelled or the timeout elapses.
    """
    queue_url = queue_url.rstrip("/") + "/"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            data = _api_get(queue_url + "api/json", cfg)
        except Exception as exc:
            logger.debug(f"queue poll error for {queue_url}: {exc}")
            time.sleep(10)
            continue
        if data.get("cancelled"):
            raise RuntimeError(f"build cancelled in queue: {queue_url}")
        executable = data.get("executable")
        if executable and executable.get("url"):
            return executable["url"].rstrip("/") + "/"
        time.sleep(10)
    raise RuntimeError(f"timeout waiting for build to start: {queue_url}")


def wait_for_finish(cfg: JenkinsConfig, build_url: str, timeout: int = 3600) -> str:
    """Poll a Jenkins build URL until it reaches a terminal state.

    Returns the result string (e.g. ``SUCCESS``, ``FAILURE``, ``ABORTED``).
    Raises RuntimeError on timeout.
    """
    build_url = build_url.rstrip("/") + "/"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            data = _api_get(build_url + "api/json", cfg)
        except Exception as exc:
            logger.debug(f"build poll error for {build_url}: {exc}")
            time.sleep(30)
            continue
        result = data.get("result")
        if result is not None:
            return str(result)
        time.sleep(30)
    raise RuntimeError(f"timeout waiting for build to complete: {build_url}")
