"""Sample data for the QA dashboard's demo mode (serve.py --demo).

Builds realistic runs, the history shown in the design mockup, with dates
relative to "now", and goes through the same build_dashboard() as real data.
Build counts per major and the tickets are real; dates, run times and build
numbers are examples.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

PLATFORMS = [
    "debian-12",
    "debian-13",
    "ubuntu-jammy",
    "ubuntu-noble",
    "ubuntu-resolute",
    "rocky-8",
    "rocky-9",
    "rocky-10",
    "ol-8",
    "ol-9",
    "ol-10",
    "rhel-8",
    "rhel-9",
    "rhel-10",
]
TOTALS = {"14": 33, "15": 39, "16": 40, "17": 46, "18": 53, "19": 45}
NIGHT = {"14": 0, "15": 1, "16": 2, "17": 3, "18": 4, "19": 5}  # Mon=0 ... Sat=5

KNOWN = [
    {
        "ticket": "PG-2883",
        "title": "Minor upgrade · OS postgresql18-server conflict",
        "major": 18,
        "pipeline": "^ppg-upgrade-parallel$",
        "label": "minor-upgrade",
    },
    {
        "ticket": "PG-2885",
        "title": "Minor upgrade · percona-pg-telemetry not upgraded",
        "major": [14, 15, 16, 17],
        "pipeline": "^ppg-upgrade-parallel$",
        "label": "minor-upgrade",
    },
    {
        "ticket": "PG-2886",
        "title": "pg_tde_archive_decrypt output not decrypted",
        "major": 17,
        "pipeline": "^tde-core-parallel$",
    },
    {
        "ticket": "PG-2888",
        "title": "Tarball · PL/Python transforms crash the server",
        "major": 19,
        "pipeline": "^tarball-parallel-ssl35$",
    },
]

# failing builds: (pipeline, label) -> failed platforms
KMIP = ("tde-parallel", "default")
WAL = ("tde-parallel", "default")
MINOR = ("ppg-upgrade-parallel", "SCENARIO=pg-{m}-minor-upgrade")
ARCHIVE = ("tde-core-parallel", "default")
PLPY = ("tarball-parallel-ssl35", "default")
PGB = ("component-generic-parallel", "PRODUCT=pgbouncer")


def _builds(
    major: str, failing: dict[tuple[str, str], list[str]], n: int
) -> list[dict[str, Any]]:
    m = int(major)
    spec: list[tuple[str, list[str]]] = [
        ("docker-component-parallel", [f"COMPONENT=c{i}" for i in range(6)]),
        (
            "docker-server-parallel",
            [
                f"BASE=ubi{u},WITH_POSTGIS={p}"
                for u in (8, 9, 10)
                for p in ("true", "false")
            ],
        ),
        ("pgsm-parallel", ["default"]),
        (
            "ppg-multiOS-parallel",
            [
                f"IO_METHOD={i},SCENARIO=pg-{m}{s}"
                for s in ("", "-meta-server", "-meta-ha")
                for i in ("worker", "sync", "io_uring")
            ][: 9 if m >= 18 else 3],
        ),
        (
            "ppg-upgrade-parallel",
            [f"SCENARIO=pg-{m}-major-upgrade", f"SCENARIO=pg-{m}-minor-upgrade"],
        ),
        ("tarball-parallel-ssl1", ["default"]),
        ("tarball-parallel-ssl3", ["default"]),
        ("tarball-parallel-ssl35", ["default"]),
    ]
    if m <= 18:
        spec.append(
            (
                "docker-server-parallel-upgrade",
                (
                    [
                        f"BASE=ubi{u},WITH_POSTGIS={p}"
                        for u in (8, 9, 10)
                        for p in ("true", "false")
                    ]
                    if m > 14
                    else []
                ),
            )
        )
    if m >= 16 and m <= 18:
        spec.append(("docker-server-parallel-custom", ["default"]))
        spec.append(
            ("docker-server-parallel-custom-upgrade", ["default"] if m >= 17 else [])
        )
    if m >= 17:
        spec += [
            ("tde-auxiliary-parallel", ["default"]),
            ("tde-core-parallel", ["default"]),
            ("tde-parallel", ["default"]),
            (
                "tde-upgrade-parallel",
                ["SCENARIO=minor", "SCENARIO=major", "SCENARIO=tde-only"],
            ),
        ]
    rest = sum(len(labels) for _, labels in spec)
    spec.insert(
        0,
        (
            "component-generic-parallel",
            ["PRODUCT=pgbouncer"]
            + [f"PRODUCT=c{i}" for i in range(max(1, TOTALS[major] - rest) - 1)],
        ),
    )
    builds = []
    for pipeline, labels in spec:
        for label in labels:
            params: dict[str, Any] = {"VERSION": f"ppg-{m}.6", "PLATFORMS": PLATFORMS}
            if pipeline.endswith("-upgrade") and pipeline.startswith("docker"):
                params = {
                    "OLD_SERVER_VERSION": f"{m - 1}.11",
                    "NEW_SERVER_VERSION": f"{m}.6",
                }
            if "SCENARIO=" in label and pipeline == "ppg-multiOS-parallel":
                params["SCENARIO"] = label.split("SCENARIO=")[1]
            n += 1
            bad = failing.get((pipeline, label))
            builds.append(
                {
                    "pipeline": pipeline,
                    "label": label,
                    "params": params,
                    "result": "FAILURE" if bad is not None else "SUCCESS",
                    "build_url": f"https://pg.cd.percona.com/job/{pipeline}/{n}/",
                    "_bad": bad,
                }
            )
    return builds


def _night(now: dt.datetime, major: str, weeks_ago: int) -> dt.datetime:
    day = now.replace(hour=2, minute=0, second=0, microsecond=0)
    while day.weekday() != NIGHT[major] or day > now:
        day -= dt.timedelta(days=1)
    return day - dt.timedelta(weeks=weeks_ago)


def _plan(now: dt.datetime) -> list[tuple[str, str, dt.datetime, int, dict]]:
    """(major, event, start, minutes, failing) per run."""

    def mn(m: int) -> tuple[str, str]:
        return (MINOR[0], MINOR[1].format(m=m))

    p: list[tuple[str, str, dt.datetime, int, dict]] = []
    for m, kinds in (
        ("14", [{}, {}, {mn(14): ["debian-12", "ubuntu-noble"]}, {}, {}]),
        ("16", [{}, {}, {mn(16): ["debian-12", "ubuntu-noble"]}, {}, {}]),
    ):
        for i, f in enumerate(kinds):
            p.append((m, "schedule", _night(now, m, 4 - i), 50 + i % 3, f))
    deb = ["debian-12", "debian-13", "ubuntu-jammy", "ubuntu-noble", "ubuntu-resolute"]
    for i, f in enumerate([{}, {PGB: ["debian-12"]}, {}]):
        p.append(("15", "schedule", _night(now, "15", 3 - i), 55, f))
    p.append(
        (
            "15",
            "workflow_dispatch",
            _night(now, "15", 0) - dt.timedelta(days=4, hours=-9),
            54,
            {},
        )
    )
    a17 = {mn(17): deb}
    b17 = {mn(17): deb, ARCHIVE: ["debian-13"]}
    for i, f in enumerate([{}, {**a17, PGB: ["ubuntu-noble"]}, b17]):
        p.append(
            ("17", "schedule", _night(now, "17", 3 - i if i < 2 else 1), 66 + i, f)
        )
    p.append(
        (
            "17",
            "workflow_dispatch",
            _night(now, "17", 0) - dt.timedelta(days=2, hours=-10),
            64,
            b17,
        )
    )
    p.append(("17", "schedule", _night(now, "17", 0), 69, b17))
    k18 = {mn(18): ["rocky-10", "ol-10", "rhel-10"]}
    for i, (f, mins) in enumerate([({}, 72), (k18, 75), (k18, 73)]):
        p.append(("18", "schedule", _night(now, "18", 3 - i), mins, f))
    p.append(
        (
            "18",
            "workflow_dispatch",
            _night(now, "18", 0) - dt.timedelta(days=2, hours=-10),
            70,
            k18,
        )
    )
    p.append(
        (
            "18",
            "schedule",
            _night(now, "18", 0),
            118,
            {**k18, KMIP: ["rocky-8", "ol-8", "rhel-8"]},
        )
    )
    plpy = {PLPY: ["debian-13"]}
    p.append(
        (
            "19",
            "workflow_dispatch",
            _night(now, "19", 0) - dt.timedelta(days=4, hours=-11),
            85,
            {**plpy, ("pgsm-parallel", "default"): ["debian-12"]},
        )
    )
    for d in (3, 2, 1):
        p.append(
            (
                "19",
                "workflow_dispatch",
                _night(now, "19", 0) - dt.timedelta(days=d, hours=-11),
                86,
                plpy,
            )
        )
    rh = [
        "rocky-8",
        "rocky-9",
        "rocky-10",
        "ol-8",
        "ol-9",
        "ol-10",
        "rhel-8",
        "rhel-9",
        "rhel-10",
    ]
    p.append(("19", "schedule", _night(now, "19", 0), 91, {**plpy, WAL: rh}))
    return p


def runs(now: dt.datetime) -> list[dict[str, Any]]:
    out = []
    n = 1000
    for i, (major, event, start, minutes, failing) in enumerate(_plan(now)):
        builds = _builds(major, failing, n)
        n += 100
        out.append(
            {
                "id": 9000 + i,
                "url": f"https://github.com/percona/obs-packaging/actions/runs/{9000 + i}",
                "event": event,
                "workflow": (
                    "obs-nightly-qa.yml" if event == "schedule" else "obs-qa-run.yml"
                ),
                "status": "completed",
                "started_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "finished_at": (start + dt.timedelta(minutes=minutes)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "builds": builds,
            }
        )
    # PG 15's nightly, in progress: 21 of 39 builds reported so far
    start = now - dt.timedelta(minutes=38)
    builds = _builds("15", {}, n)[:21]
    out.append(
        {
            "id": 9999,
            "url": "https://github.com/percona/obs-packaging/actions/runs/9999",
            "event": "schedule",
            "status": "in_progress",
            "started_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "finished_at": None,
            "builds": builds,
            "running_majors": ["15"],
            "qa_jobs": {"total": 39, "done": 21, "failed": 0},
        }
    )
    # PG 16's last nightly, re-run and queued behind PG 15's (like re-running
    # failed jobs while another nightly runs)
    pg16 = [
        r
        for r in out
        if r["builds"]
        and r["builds"][0]["params"].get("VERSION", "").startswith("ppg-16.")
    ]
    last16 = max(pg16, key=lambda r: r["started_at"])
    last16.update(
        status="queued",
        attempt=2,
        attempt_started_at=(now - dt.timedelta(minutes=12)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    )
    out.sort(key=lambda r: r["started_at"], reverse=True)
    return out


def build_info(now: dt.datetime) -> dict[str, dict[str, Any]]:
    info: dict[str, dict[str, Any]] = {}
    for run in runs(now):
        for b in run["builds"]:
            mins = (
                101
                if (
                    b["pipeline"] == "tde-auxiliary-parallel"
                    and run["finished_at"]
                    and "-to-" not in b["label"]
                    and (
                        dt.datetime.fromisoformat(
                            run["finished_at"].replace("Z", "+00:00")
                        )
                        - dt.datetime.fromisoformat(
                            run["started_at"].replace("Z", "+00:00")
                        )
                    ).total_seconds()
                    > 100 * 60
                )
                else (52 if b["pipeline"] == "tde-auxiliary-parallel" else 25)
            )
            entry: dict[str, Any] = {"duration_s": mins * 60}
            if b["_bad"] is not None:
                entry["failed_platforms"] = b["_bad"]
            info[b["build_url"]] = entry
    return info
