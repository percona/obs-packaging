#!/usr/bin/env python3
"""Serve the PPG QA dashboard on an internal host.

Serves the page (static/) and its data (/data.json, kept in memory), and
refreshes the data in the background every --interval minutes. If a refresh
fails, the last good data is kept and the page shows when it was last
refreshed and why the latest refresh failed.

  python3 serve.py --demo                  # sample data, no tokens needed
  GITHUB_TOKEN=... python3 serve.py        # live data from GitHub + Jenkins

Python standard library only (plus PyYAML for the known-failures file).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import collect  # noqa: E402


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.data: dict[str, Any] | None = None
        self.error = ""

    def set(self, data: dict[str, Any]) -> None:
        with self.lock:
            self.data, self.error = data, ""

    def fail(self, error: str) -> None:
        with self.lock:
            self.error = error

    def payload(self) -> bytes:
        with self.lock:
            data = dict(
                self.data
                or {"majors": [], "failures": [], "details": {}, "running": None}
            )
            data["error"] = self.error
        return json.dumps(data).encode()


def demo_source() -> dict[str, Any]:
    import demo

    now = dt.datetime.now(dt.timezone.utc)
    data = collect.build_dashboard(
        demo.runs(now), demo.KNOWN, now, demo.build_info(now)
    )
    data["demo"] = True
    return data


def live_source(
    repo: str, cache_dir: Path, known_path: Path, use_jenkins: bool = True
) -> Callable[[], dict[str, Any]]:
    gh = collect.GitHub(repo, os.environ.get("GITHUB_TOKEN"))
    jenkins = collect.Jenkins(
        os.environ.get("JENKINS_USER"), os.environ.get("JENKINS_TOKEN")
    )

    def source() -> dict[str, Any]:
        jenkins.available = use_jenkins  # retry Jenkins at every refresh
        runs = collect.collect_runs(gh, cache_dir)
        info = collect.collect_build_info(jenkins, runs, cache_dir)
        now = dt.datetime.now(dt.timezone.utc)
        return collect.build_dashboard(runs, collect.load_known(known_path), now, info)

    return source


def refresher(
    state: State,
    source: Callable[[], dict[str, Any]],
    minutes: float,
    stop: threading.Event,
) -> None:
    while True:
        try:
            state.set(source())
        except Exception as err:  # keep serving the last good data
            state.fail(f"{type(err).__name__}: {err}")
            print(f"refresh failed: {err}", file=sys.stderr)
        if stop.wait(minutes * 60):
            return


def make_handler(state: State) -> type[SimpleHTTPRequestHandler]:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(HERE / "static"), **kwargs)

        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?")[0] == "/data.json":
                body = state.payload()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def log_message(self, fmt: str, *args: Any) -> None:
            pass

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--host",
        default="127.0.0.1",
        help="address to listen on (0.0.0.0: all interfaces)",
    )
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument(
        "--interval",
        type=float,
        default=collect.REFRESH_MINUTES,
        help="minutes between refreshes",
    )
    ap.add_argument(
        "--demo", action="store_true", help="serve sample data (no tokens needed)"
    )
    ap.add_argument(
        "--no-jenkins",
        action="store_true",
        help="don't read build details (durations, failing platforms) from Jenkins",
    )
    ap.add_argument("--repo", default=collect.REPO)
    ap.add_argument("--cache-dir", default=str(HERE / ".cache"))
    ap.add_argument(
        "--known", default=str(HERE.parents[1] / ".github" / "qa-known-failures.yaml")
    )
    args = ap.parse_args(argv)

    if not args.demo and not os.environ.get("GITHUB_TOKEN"):
        print(
            "GITHUB_TOKEN is not set (needed to download the QA reports). Use --demo for sample data.",
            file=sys.stderr,
        )
        return 2
    source = (
        demo_source
        if args.demo
        else live_source(
            args.repo, Path(args.cache_dir), Path(args.known), not args.no_jenkins
        )
    )
    state = State()
    stop = threading.Event()
    threading.Thread(
        target=refresher, args=(state, source, args.interval, stop), daemon=True
    ).start()
    for _ in range(600):  # first data, before saying we're ready (demo: instant)
        if state.data is not None or state.error:
            break
        time.sleep(0.1)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(
        f"QA dashboard on http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}/"
        + ("  (demo data)" if args.demo else "")
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
