# Repo-owned OBS source services

Services here follow the OBS source-service contract (binary at
`/usr/lib/obs/service/<name>`, `--<param> <value>` pairs, `--outdir DIR`,
non-zero exit on failure) and are run **locally** by `percona-obs sync` for
services declared `mode="manual"` in a package's `obs/_service`. They never run
on the OBS server.

| Service | Purpose |
|---|---|
| `source_script` | Build the source tarball by running a script from the package's `obs/` directory on the `obs_scm` checkout, for upstreams whose release tarball comes out of a "dist" step (generated code, rendered docs) rather than being the git tree. The script runs with a cleared environment and, where `bwrap` can create a sandbox, without network; the directory it produces is packed reproducibly. Needs `cpio`; `bwrap` (bubblewrap) is optional. |
| `npm_lockfile` | Generate `package-lock.json` from an upstream source archive so the OBS `node_modules` service can vendor npm dependencies (upstreams that ship only `yarn.lock`, e.g. pgAdmin 4). Needs `npm` (Node.js ≥ 18) and `cpio` on the machine. |

## Installing locally

```sh
sudo install -m 755 tools/obs-services/npm_lockfile /usr/lib/obs/service/npm_lockfile
sudo install -m 644 tools/obs-services/npm_lockfile.service /usr/lib/obs/service/npm_lockfile.service
sudo install -m 755 tools/obs-services/source_script /usr/lib/obs/service/source_script
sudo install -m 644 tools/obs-services/source_script.service /usr/lib/obs/service/source_script.service
```

The obs-tools CI image (`.github/docker/obs-tools/Dockerfile`) installs them the
same way; changes under `tools/obs-services/` trigger an image rebuild.

## Testing

`venv/bin/pytest tests/test_npm_lockfile.py` — uses a fake `npm`, no network.
`venv/bin/pytest tests/test_source_script.py` — fake checkout and scripts, no network.
Format with `venv/bin/black tools/obs-services/npm_lockfile tools/obs-services/source_script`.
