# PPG QA dashboard

An internal web page showing the state of PPG's OBS QA at a glance:

- **Overview**: one row per PG major (14–19) with failing / total builds,
  last run, run time (flagged when ≥ 50% slower than the median of the
  major's last 5 runs) and the last 5 runs; a "Running now" banner while a
  run is in progress; and **Failing now**, every current failure marked
  **NEW** or **KNOWN · ticket**, with failing platforms and *failing since*.
- **Major detail** (`#pg18`): summary, run times of the last 5 runs, and
  failing builds with the platforms that failed.

Data comes from GitHub Actions (the *OBS Nightly QA* and *OBS QA Run*
workflows and their `qa-report-*` artifacts) and Jenkins (build durations,
failing platforms), refreshed every 10 minutes. Known failures are listed in
[`.github/qa-known-failures.yaml`](../../.github/qa-known-failures.yaml).

## Try it (demo data, no tokens)

```bash
cd tools/qa-dashboard
python3 serve.py --demo
# open http://localhost:8080/
```

The demo builds realistic history (the design mockup's) with dates relative
to today, through the same code as live data.

## Live data

```bash
cd tools/qa-dashboard
export GITHUB_TOKEN=...      # fine-grained, read-only: Actions on percona/obs-packaging
# optional, if Jenkins needs a login to read build details:
export JENKINS_USER=... JENKINS_TOKEN=...
python3 serve.py             # http://localhost:8080/
```

`GITHUB_TOKEN` is required: GitHub only lets authenticated users download
workflow artifacts. Without Jenkins access the dashboard still works; only
build durations ("slowest build") and failing platforms are missing.

The first start reads the last 40 runs of each workflow, which takes a few
minutes. Finished runs and Jenkins builds are cached in `.cache/`, so later
refreshes only fetch new and running runs.

`python3 collect.py` writes the same data to `data.json` once and exits
(useful for checking a token, or from cron).

## Running it internally

Any Linux machine inside the network with Python 3.10+ and PyYAML (both in
obs-packaging's `requirements.txt`). The page has no login, so serve it only
on the internal network:

```bash
git clone https://github.com/percona/obs-packaging.git /opt/obs-packaging
cd /opt/obs-packaging && python3 -m venv venv && venv/bin/pip install -r requirements.txt
```

`/etc/systemd/system/qa-dashboard.service`:

```ini
[Unit]
Description=PPG QA dashboard
After=network-online.target

[Service]
User=qa-dashboard
WorkingDirectory=/opt/obs-packaging/tools/qa-dashboard
EnvironmentFile=/etc/qa-dashboard.env
ExecStart=/opt/obs-packaging/venv/bin/python serve.py --host 0.0.0.0 --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`/etc/qa-dashboard.env` (readable by `qa-dashboard` only, `chmod 600`):

```
GITHUB_TOKEN=...
```

```bash
sudo systemctl enable --now qa-dashboard
```

To pick up changes to the dashboard or to the known-failures file:
`git -C /opt/obs-packaging pull && sudo systemctl restart qa-dashboard`.

## Maintaining known failures

When a failure has a ticket, add it to `.github/qa-known-failures.yaml`
(format in the file's header) so it shows as KNOWN instead of NEW. Remove
the entry when the ticket is fixed.

## Files

| File | |
|---|---|
| `collect.py` | GitHub + Jenkins → dashboard data (`build_dashboard()` is pure and tested) |
| `serve.py` | Internal web server, background refresh |
| `demo.py` | Sample data for `--demo` |
| `static/` | The page (HTML, CSS, JS; no build step) |

Tests: `tests/test_qa_dashboard.py`.
