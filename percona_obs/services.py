import hashlib
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .common import (
    _REPO_DIR,
    apply_env_substitution,
    _print_ok,
    _print_pending,
    _print_same,
    logger,
)

_OBS_SERVICE_DIR = Path("/usr/lib/obs/service")
_SKIP_MODES = {"serveronly", "disabled"}

_SERVICE_PREFIX_RE = re.compile(r"^_service:[^:]+:")


def _strip_service_prefix(name: str) -> str:
    """Strip the ``_service:<name>:`` prefix that OBS service binaries add."""
    return _SERVICE_PREFIX_RE.sub("", name)


def _is_kiwi_service(name: str) -> bool:
    """Return True if *name* is an OBS kiwi-image helper service.

    Kiwi services (kiwi_label_helper, kiwi_metainfo_helper, kiwi_import, …)
    require kiwi tooling and image-build context that isn't available locally;
    they're left to run server-side at buildtime on the OBS build workers.
    """
    return name.startswith("kiwi_")


# Cache directories (relative to the repo root, ignored by git)
_CACHE_DIR = _REPO_DIR / ".cache"
_OBS_SCM_CACHE_DIR = _CACHE_DIR / "obs_scm"
_SVC_CACHE_DIR = _CACHE_DIR / "services"

# Matches the subdir param of obs_scm services that fetch packaging files
# from this repo (e.g. "root/ppg/17/percona-haproxy/debian" or the variable
# form "${DEBIAN_PACKAGE_DIRECTORY}" / "${RPM_PACKAGE_DIRECTORY}").
_PACKAGING_SUBDIR_RE = re.compile(
    r"root/.+/(?:debian|rpm)$"
    r"|\$\{DEBIAN_PACKAGE_DIRECTORY\}"
    r"|\$\{RPM_PACKAGE_DIRECTORY\}"
)


def _has_manual_services(service_file: Path) -> bool:
    """Return True if any service in *service_file* declares mode="manual"."""
    try:
        root = ET.parse(service_file).getroot()
    except (ET.ParseError, OSError):
        return False
    return any(svc.get("mode") == "manual" for svc in root.findall("service"))


def _has_runnable_services(service_file: Path) -> bool:
    """Return True if any service can be run locally (not serveronly/disabled)."""
    try:
        root = ET.parse(service_file).getroot()
    except (ET.ParseError, OSError):
        return False
    return any(
        svc.get("mode", "") not in _SKIP_MODES for svc in root.findall("service")
    )


def _get_upstream_obs_scm_info(
    service_file: Path,
) -> tuple[str, str, str] | None:
    """Return (filename_prefix, url, revision) for the upstream obs_scm service.

    Packaging obs_scm services (whose subdir matches _PACKAGING_SUBDIR_RE —
    either a literal path like root/.+/debian or the variable form
    ${DEBIAN_PACKAGE_DIRECTORY} / ${RPM_PACKAGE_DIRECTORY}) are ignored.
    Returns None if zero or more than one upstream obs_scm services are found,
    or if filename/url params are missing.
    """
    upstream: list[ET.Element] = []
    for svc in ET.parse(service_file).getroot().findall("service"):
        if svc.get("name") != "obs_scm":
            continue
        subdir_el = svc.find("param[@name='subdir']")
        if subdir_el is not None and _PACKAGING_SUBDIR_RE.match(
            (subdir_el.text or "").strip()
        ):
            continue
        upstream.append(svc)

    if len(upstream) != 1:
        return None

    svc = upstream[0]
    filename = ""
    url = ""
    revision = "HEAD"
    for p in svc.findall("param"):
        name = p.get("name", "")
        val = (p.text or "").strip()
        if name == "filename":
            filename = val
        elif name == "url":
            url = val
        elif name == "revision":
            revision = val

    if not filename or not url:
        return None
    return filename, url, revision


def _parse_obs_scm_infos(
    svc_text: str,
    packaging_only: bool = False,
) -> list[tuple[str, str, str, str]]:
    """Parse obs_scm service entries from XML text already substituted with env vars.

    Returns (filename_prefix, url, revision, subdir) for each matching obs_scm
    service.  Services without a filename or url param are skipped.
    If packaging_only is True, only services whose subdir matches
    _PACKAGING_SUBDIR_RE are returned; otherwise all obs_scm services are returned.
    """
    results: list[tuple[str, str, str, str]] = []
    for svc in ET.fromstring(svc_text).findall("service"):
        if svc.get("name") != "obs_scm":
            continue
        subdir_el = svc.find("param[@name='subdir']")
        subdir = (subdir_el.text or "").strip() if subdir_el is not None else ""
        is_packaging = bool(subdir) and bool(_PACKAGING_SUBDIR_RE.match(subdir))
        if packaging_only and not is_packaging:
            continue
        filename = ""
        url = ""
        revision = "HEAD"
        for p in svc.findall("param"):
            name = p.get("name", "")
            val = (p.text or "").strip()
            if name == "filename":
                filename = val
            elif name == "url":
                url = val
            elif name == "revision":
                revision = val
        if filename and url:
            results.append((filename, url, revision, subdir))
    return results


def _get_all_obs_scm_infos(
    service_file: Path,
    env_vars: dict[str, str] | None = None,
) -> list[tuple[str, str, str, str]]:
    """Return (filename_prefix, url, revision, subdir) for every obs_scm service.

    Unlike _get_upstream_obs_scm_info, packaging obs_scm services (those whose
    subdir matches root/.+/debian or root/.+/rpm) are included.  Services that
    lack a filename or url param are silently skipped.

    If env_vars is provided, ${VAR} tokens in the service file are substituted
    before parsing so that URLs like ${PERCONA_OBS_PACKAGING_REPO} are resolved.
    """
    svc_text = service_file.read_text("utf-8")
    if env_vars:
        svc_text = apply_env_substitution(svc_text, env_vars, source=service_file)
    return _parse_obs_scm_infos(svc_text, packaging_only=False)


def _get_packaging_obs_scm_infos(
    service_file: Path,
    env_vars: dict[str, str] | None = None,
) -> list[tuple[str, str, str, str]]:
    """Return (filename_prefix, url, revision, subdir) for packaging obs_scm services only.

    Packaging services are those whose subdir matches _PACKAGING_SUBDIR_RE.
    Services without a filename or url param are skipped.

    If env_vars is provided, ${VAR} tokens in the service file are substituted
    before parsing so that URLs like ${PERCONA_OBS_PACKAGING_REPO} are resolved.
    """
    svc_text = service_file.read_text("utf-8")
    if env_vars:
        svc_text = apply_env_substitution(svc_text, env_vars, source=service_file)
    return _parse_obs_scm_infos(svc_text, packaging_only=True)


def _find_upstream_obs_scm_filename(service_file: Path) -> str | None:
    """Return the filename param of the single upstream source obs_scm service.

    Packaging obs_scm services (whose subdir matches _PACKAGING_SUBDIR_RE —
    either a literal path like root/.+/debian or the variable form
    ${DEBIAN_PACKAGE_DIRECTORY} / ${RPM_PACKAGE_DIRECTORY}) are ignored.
    Returns None — and logs a warning when manual services are present — if
    zero or more than one upstream obs_scm services are found.
    """
    upstream: list[ET.Element] = []
    for svc in ET.parse(service_file).getroot().findall("service"):
        if svc.get("name") != "obs_scm":
            continue
        subdir_el = svc.find("param[@name='subdir']")
        if subdir_el is not None and _PACKAGING_SUBDIR_RE.match(
            (subdir_el.text or "").strip()
        ):
            continue
        upstream.append(svc)

    if len(upstream) == 0:
        return None

    if len(upstream) > 1:
        logger.warning(
            f"{service_file}: found {len(upstream)} upstream obs_scm services; "
            "skipping service cache"
        )
        return None

    for p in upstream[0].findall("param"):
        if p.get("name") == "filename":
            return (p.text or "").strip() or None
    return None


def _read_obsinfo_commit(workdir: Path, filename_prefix: str) -> str | None:
    """Parse the commit hash from {filename_prefix}*.obsinfo in workdir.

    obs_scm writes the obsinfo as ``{filename}.obsinfo`` (no version suffix).
    The dash-version pattern is kept as a fallback for other tools that may
    include the version in the filename.
    """
    for pattern in (f"{filename_prefix}.obsinfo", f"{filename_prefix}-*.obsinfo"):
        for obsinfo in workdir.glob(pattern):
            for line in obsinfo.read_text(encoding="utf-8").splitlines():
                if line.startswith("commit:"):
                    return line.split(":", 1)[1].strip() or None
    return None


def _cache_lookup(commit_hash: str) -> list[str] | None:
    """Return cached artifact filenames for commit_hash, or None on miss."""
    entry = _SVC_CACHE_DIR / commit_hash
    if not entry.is_dir():
        return None
    files = [f.name for f in sorted(entry.iterdir()) if f.is_file()]
    return files if files else None


def _cache_store(commit_hash: str, workdir: Path, artifacts: list[str]) -> None:
    """Atomically copy artifacts from workdir into the service cache."""
    _SVC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=_SVC_CACHE_DIR, prefix="_tmp-"))
    try:
        for name in artifacts:
            shutil.copy2(workdir / name, tmp / name)
        final = _SVC_CACHE_DIR / commit_hash
        if final.exists():
            shutil.rmtree(final)
        tmp.rename(final)
        logger.debug(f"cached {len(artifacts)} manual artifact(s) under {final}")
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _obs_scm_cache_key(svc: ET.Element) -> str:
    """Return a stable cache key for an obs_scm service element.

    The key is the SHA256 of all sorted param name=value pairs, so any change
    to the service configuration (URL, revision, extract, versionformat, …)
    produces a different key.
    """
    parts = sorted(
        f"{p.get('name', '')}={(p.text or '').strip()}" for p in svc.findall("param")
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _remote_commit_exists(remote_url: str, sha: str) -> bool:
    """
    Return True if `sha` exists in `remote_url` (commit object), False otherwise.
    Uses subprocess.Popen for all git commands and a temporary repo.
    """

    _SHA1_RE = re.compile(r"^[0-9a-fA-F]{40}$")
    if not _SHA1_RE.fullmatch(sha):
        return False

    logger.debug(f"resolving git commit {sha} on {remote_url}")

    tmpdir = tempfile.mkdtemp(prefix="git-check-")
    try:

        def run(cmd):
            p = subprocess.Popen(
                cmd, cwd=tmpdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            try:
                out, err = p.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()
                p.communicate()
                return 124, b"", b""
            return p.returncode, out, err

        # init repo and add remote
        rc, _, _ = run(["git", "init", "-q"])
        if rc != 0:
            return False
        rc, _, _ = run(["git", "remote", "add", "origin", remote_url])
        if rc != 0:
            return False

        # attempt a shallow fetch of the SHA (may fail if remote doesn't expose it via refs)
        run(["git", "fetch", "--no-tags", "--depth=1", "origin", sha])

        # check for commit object existence
        rc, _, _ = run(["git", "cat-file", "-e", f"{sha}^{{commit}}"])
        return rc == 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _remote_reference_exists(remote_url: str, ref: str) -> str | None:
    patterns = [
        f"refs/heads/{ref}",
        f"refs/tags/{ref}^{{}}",
        f"refs/tags/{ref}",
    ]
    if ref.startswith("refs/"):
        patterns = [ref] + patterns
    try:
        logger.debug(f"resolving git revision {ref!r} on {remote_url}")
        proc = subprocess.Popen(
            ["git", "ls-remote", "--", remote_url] + patterns,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout_bytes, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            # Close pipes immediately so the drain in communicate() cannot
            # block on child processes that inherited the pipe descriptors
            # (e.g. git credential/transport helpers).
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            proc.wait()
            return None
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        if proc.returncode != 0 or not stdout.strip():
            return None
        ref_map = {}
        for line in stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                sha, ref = parts[0].strip(), parts[1].strip()
                ref_map[ref] = sha
        # Preference order: explicit ref path, branch, dereferenced annotated tag, lightweight tag
        if ref.startswith("refs/") and ref in ref_map:
            return ref_map[ref]
        branch_ref = f"refs/heads/{ref}"
        deref_tag_ref = f"refs/tags/{ref}^{{}}"
        lightweight_tag_ref = f"refs/tags/{ref}"
        if branch_ref in ref_map:
            return ref_map[branch_ref]
        if deref_tag_ref in ref_map:
            return ref_map[deref_tag_ref]
        if lightweight_tag_ref in ref_map:
            return ref_map[lightweight_tag_ref]
    except Exception:
        return None


def _git_head_sha(url: str, revision: str) -> str | None:
    """Return the resolved commit SHA of revision on a remote git repository.

    Tries branch ref first, then dereferenced annotated tag, then lightweight tag.
    If revision is already a full ref path (starts with "refs/"), it is tried
    directly and takes priority over the derived patterns — this supports refs
    like "refs/pull/42/head" used by GitHub PR workflows.
    Returns None if git is unavailable, the remote is unreachable, or
    no matching ref is found.
    """
    sha = _remote_reference_exists(url, revision)
    if sha is not None:
        return sha

    # revision not found, maybe it's a direct commit SHA; verify it exists in the remote
    if _remote_commit_exists(url, revision):
        return revision

    return None


def _git_tag_for_sha(url: str, sha: str) -> str | None:
    """Return the tag name whose commit SHA equals *sha* on a remote repository.

    Fetches all tags via ``git ls-remote --tags``.  Annotated tags are
    dereferenced (``^{}``) so the returned SHA is always the underlying commit,
    not the tag object.  Lightweight tags are included as a fallback.

    Returns None if no matching tag is found, git is unavailable, the remote
    is unreachable, or the call times out.
    """
    try:
        logger.debug(f"resolving tag for SHA {sha!r} on {url}")
        proc = subprocess.Popen(
            ["git", "ls-remote", "--tags", "--", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout_bytes, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            proc.wait()
            return None
        if proc.returncode != 0:
            return None
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        # Build tag_name → commit_sha mapping.  Dereferenced annotated tag
        # entries (refs/tags/v1.0.0^{}) take priority over lightweight ones
        # because they carry the actual commit SHA rather than the tag object SHA.
        tag_map: dict[str, str] = {}
        deref_tags: set[str] = set()
        for line in stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            ref_sha, ref = parts[0].strip(), parts[1].strip()
            if ref.endswith("^{}") and ref.startswith("refs/tags/"):
                tag = ref[len("refs/tags/") : -len("^{}")]
                tag_map[tag] = ref_sha
                deref_tags.add(tag)
            elif ref.startswith("refs/tags/"):
                tag = ref[len("refs/tags/") :]
                if tag not in deref_tags:
                    tag_map[tag] = ref_sha
        for tag, tag_sha in tag_map.items():
            if tag_sha == sha:
                return tag
        return None
    except Exception:
        return None


def _obs_scm_lookup(cache_key: str, head_sha: str) -> list[str] | None:
    """Return cached obs_scm output filenames for (cache_key, head_sha), or None."""
    entry = _OBS_SCM_CACHE_DIR / cache_key / head_sha
    if not entry.is_dir():
        return None
    files = [f.name for f in sorted(entry.iterdir()) if f.is_file()]
    return files if files else None


def _obs_scm_store(
    cache_key: str, head_sha: str, workdir: Path, filenames: list[str]
) -> None:
    """Atomically copy obs_scm output files from workdir into the obs_scm cache."""
    key_dir = _OBS_SCM_CACHE_DIR / cache_key
    key_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=key_dir, prefix="_tmp-"))
    try:
        for fname in filenames:
            shutil.copy2(workdir / fname, tmp / fname)
        final = key_dir / head_sha
        if final.exists():
            shutil.rmtree(final)
        tmp.rename(final)
        logger.debug(f"cached obs_scm output ({head_sha[:12]}) under {final}")
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _copy_local_packaging(obs_dir: Path, workdir: Path, pkg_label: str) -> None:
    """Copy debian/ and rpm/ packaging files from the local package directory.

    RPM: copy all files from ``<pkg>/rpm/`` into *workdir*.
    Debian: copy ``*.dsc`` files and compress the ``debian/`` directory into
    ``debian.tar.gz`` in *workdir*.
    """
    pkg_dir = obs_dir.parent
    rpm_dir = pkg_dir / "rpm"
    deb_dir = pkg_dir / "debian"
    if rpm_dir.is_dir():
        rpm_files = [f for f in sorted(rpm_dir.iterdir()) if f.is_file()]
        for f in rpm_files:
            shutil.copy2(f, workdir / f.name)
        logger.debug(
            f"copied {len(rpm_files)} file(s) from rpm/: "
            f"{[f.name for f in rpm_files]}"
        )
        _print_ok(f"packaging rpm/  {pkg_label}  ({len(rpm_files)} files)")
    if deb_dir.is_dir():
        dsc_files = sorted(deb_dir.glob("*.dsc"))
        for f in dsc_files:
            shutil.copy2(f, workdir / f.name)
        result = subprocess.run(
            [
                "tar",
                "czf",
                str(workdir / "debian.tar.gz"),
                "-C",
                str(pkg_dir),
                "debian",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit(
                f"error: creating debian.tar.gz failed:\n  {result.stderr.strip()}"
            )
        dsc_names = [f.name for f in dsc_files]
        logger.debug(f"created debian.tar.gz + copied {dsc_names}")
        _print_ok(
            f"packaging debian/  {pkg_label}  "
            f"(debian.tar.gz + {len(dsc_files)} .dsc)"
        )


def _run_local_services(
    obs_dir: Path,
    pkg_label: str = "",
    cache: bool = True,
    env_vars: dict[str, str] | None = None,
) -> Path:
    """Run all OBS services locally; return workdir path.

    Execution is split into three phases plus an extraction step:
      Phase 1 — non-manual, non-buildtime services (obs_scm etc.): for each
                obs_scm service a fast git ls-remote checks whether the remote
                HEAD matches a cached run; on a hit the cached files are restored
                and the obs_scm invocation is skipped entirely.  On a miss
                obs_scm runs normally and its output is stored to the cache.
      Cache check — after Phase 1 the upstream source obsinfo is read for its
                    commit hash.  On a cache hit Phase 2 manual service outputs
                    are restored from cache.
      Phase 2 — manual services (go_modules etc.): run on a cache miss.
                Results are stored to the service cache on success.
      Extraction — ``.obscpio`` archives are extracted via ``cpio``.
      Local packaging — debian/ and rpm/ files are copied from the local
                        package directory.
      Phase 3 — buildtime services (tar, recompress, set_version): always
                run (fast, deterministic local transforms).

    Modes "serveronly" and "disabled" are skipped entirely.
    Each service binary is expected at /usr/lib/obs/service/<name>.  If a
    binary is missing a warning is logged and the service is skipped.

    If *env_vars* is provided, ``${VAR}`` tokens in the ``_service`` file are
    substituted before parsing and before the file is written into the workdir.

    The caller owns cleanup of the returned workdir.

    Raises SystemExit on service failure.
    """
    service_file = obs_dir / "_service"
    svc_text = service_file.read_text("utf-8")
    if env_vars:
        svc_text = apply_env_substitution(svc_text, env_vars, source=service_file)
    svc_root = ET.fromstring(svc_text)

    workdir = Path(tempfile.mkdtemp(prefix="percona-obs-svc-"))
    for src in obs_dir.iterdir():
        if src.is_file():
            if src.name == "_service":
                (workdir / "_service").write_text(svc_text, "utf-8")
            else:
                shutil.copy2(src, workdir / src.name)

    def _run_one(svc: ET.Element) -> list[str]:
        """Invoke one service binary; return list of generated filenames."""
        name = svc.get("name", "")
        binary = _OBS_SERVICE_DIR / name
        if not binary.exists():
            raise SystemExit(
                f"error: service binary not found: {binary}\n"
                f"  Install the package that provides this service."
            )

        cmd: list[str] = [str(binary)]
        for param in svc.findall("param"):
            pname = param.get("name", "")
            pval = (param.text or "").strip()
            cmd += [f"--{pname}", pval]

        outdir = Path(tempfile.mkdtemp(prefix=f"percona-obs-svc-{name}-"))
        cmd += ["--outdir", str(outdir)]

        logger.debug(f"running service: {' '.join(cmd)}")
        _print_pending(f"service {name}  {pkg_label}")
        result = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True)
        if result.stdout:
            logger.debug(f"  stdout: {result.stdout.rstrip()}")
        if result.stderr:
            logger.debug(f"  stderr: {result.stderr.rstrip()}")

        if result.returncode != 0:
            shutil.rmtree(outdir, ignore_errors=True)
            shutil.rmtree(workdir, ignore_errors=True)
            raise SystemExit(
                f"error: service {name!r} exited with {result.returncode}:\n"
                f"  {result.stderr.strip() or '(no stderr output)'}"
            )

        generated: list[str] = []
        for out_file in sorted(outdir.iterdir()):
            if out_file.is_file():
                clean_name = _strip_service_prefix(out_file.name)
                shutil.move(str(out_file), str(workdir / clean_name))
                generated.append(clean_name)
        shutil.rmtree(outdir, ignore_errors=True)
        logger.debug(f"service {name!r} produced: {generated}")
        _print_ok(f"service {name}  {pkg_label}")
        return generated

    # ── Phase 1: non-manual, non-buildtime services (obs_scm, …) ────────────
    manual_svcs: list[ET.Element] = []
    buildtime_svcs: list[ET.Element] = []
    kiwi_svcs: list[ET.Element] = []
    for svc in svc_root.findall("service"):
        mode = svc.get("mode", "")
        if mode in _SKIP_MODES:
            logger.debug(f"skipping service {svc.get('name')!r} (mode={mode!r})")
            continue
        svc_name_for_filter = svc.get("name", "")
        if _is_kiwi_service(svc_name_for_filter):
            logger.debug(
                f"skipping kiwi service {svc_name_for_filter!r} — "
                f"runs server-side at buildtime"
            )
            _print_same(f"service {svc_name_for_filter}  {pkg_label}  (server-side)")
            kiwi_svcs.append(svc)
            continue
        if mode == "manual":
            manual_svcs.append(svc)
            continue
        if mode == "buildtime":
            buildtime_svcs.append(svc)
            continue

        svc_name = svc.get("name", "")

        # Skip packaging obs_scm services — debian/ and rpm/ files are
        # copied directly from the local package directory after Phase 3.
        if svc_name == "obs_scm":
            subdir_el = svc.find("param[@name='subdir']")
            subdir = (subdir_el.text or "").strip() if subdir_el is not None else ""
            if subdir and _PACKAGING_SUBDIR_RE.match(subdir):
                logger.debug(f"skipping packaging obs_scm (subdir={subdir!r})")
                continue

        if cache and svc_name == "obs_scm":
            # Resolve the remote HEAD SHA with a fast ls-remote before
            # deciding whether to run obs_scm (full clone) or restore from cache.
            obs_url = next(
                (
                    (p.text or "").strip()
                    for p in svc.findall("param")
                    if p.get("name") == "url"
                ),
                "",
            )
            obs_rev = next(
                (
                    (p.text or "").strip()
                    for p in svc.findall("param")
                    if p.get("name") == "revision"
                ),
                "HEAD",
            )
            obs_key = _obs_scm_cache_key(svc)
            _print_pending(f"service obs_scm  {pkg_label}")
            head_sha = _git_head_sha(obs_url, obs_rev) if obs_url else None
            if head_sha:
                cached_files = _obs_scm_lookup(obs_key, head_sha)
                if cached_files is not None:
                    cache_entry = _OBS_SCM_CACHE_DIR / obs_key / head_sha
                    for fname in cached_files:
                        shutil.copy2(cache_entry / fname, workdir / fname)
                    _print_same(f"service obs_scm  {pkg_label}  (cached)")
                    logger.debug(
                        f"obs_scm cache hit ({head_sha[:12]}): "
                        f"restored {len(cached_files)} file(s)"
                    )
                    continue
            # Cache miss or ls-remote failed: run obs_scm then store output.
            generated = _run_one(svc)
            if head_sha and generated:
                try:
                    _obs_scm_store(obs_key, head_sha, workdir, generated)
                except Exception as exc:
                    logger.warning(f"obs_scm cache store failed: {exc}")
        else:
            _run_one(svc)

    # ── Cache check ─────────────────────────────────────────────────────────
    # If the upstream source commit is unchanged, Phase 2 (manual services
    # like go_modules) can be restored from cache.  Phase 3 (buildtime
    # services) is always re-run since it's fast and deterministic.
    commit_hash: str | None = None
    manual_artifacts: list[str] = []
    if cache:
        upstream_filename = _find_upstream_obs_scm_filename(service_file)
        if upstream_filename:
            commit_hash = _read_obsinfo_commit(workdir, upstream_filename)
            if commit_hash:
                cached_names = _cache_lookup(commit_hash)
                if cached_names is not None:
                    for art_name in cached_names:
                        shutil.copy2(
                            _SVC_CACHE_DIR / commit_hash / art_name,
                            workdir / art_name,
                        )
                    for svc in manual_svcs:
                        _print_same(
                            f"service {svc.get('name', '?')}  {pkg_label}  (cached)"
                        )
                    logger.debug(
                        f"cache hit ({commit_hash[:12]}): "
                        f"skipping {len(manual_svcs)} manual service(s)"
                    )
                    manual_artifacts = list(cached_names)

    # ── Phase 2: manual services (go_modules, …) ─────────────────────────
    if not manual_artifacts:
        for svc in manual_svcs:
            manual_artifacts.extend(_run_one(svc))
        # Cache manual artifacts only (vendor tarballs etc.).
        if cache and commit_hash and manual_artifacts:
            try:
                _cache_store(commit_hash, workdir, manual_artifacts)
            except Exception as exc:
                logger.warning(f"cache store failed: {exc}")

    # ── Extract .obscpio archives ────────────────────────────────────────
    # Buildtime services (tar, recompress, set_version) expect extracted
    # directories, not .obscpio files.  The OBS build script extracts
    # these before running buildtime services; we replicate that here.
    for obscpio in sorted(workdir.glob("*.obscpio")):
        logger.debug(f"extracting {obscpio.name}")
        result = subprocess.run(
            [
                "cpio",
                "--extract",
                "--unconditional",
                "--preserve-modification-time",
                "--make-directories",
            ],
            input=obscpio.read_bytes(),
            capture_output=True,
            cwd=str(workdir),
        )
        if result.returncode != 0:
            raise SystemExit(
                f"error: cpio extract of {obscpio.name} failed:\n"
                f"  {result.stderr.decode('utf-8', errors='replace').strip()}"
            )
        obscpio.unlink()

    # ── Copy local packaging files ────────────────────────────────────────
    # Copy debian/ and rpm/ from the local package directory before
    # Phase 3 so that buildtime services like set_version can find
    # .dsc and .spec files.
    _copy_local_packaging(obs_dir, workdir, pkg_label)

    # ── Phase 3: buildtime services (tar, recompress, set_version) ────────
    # Always run — these are fast, deterministic local transforms.
    for svc in buildtime_svcs:
        _run_one(svc)

    # ── Cleanup: remove intermediates that should not be uploaded ─────────
    # If we skipped any kiwi services, keep a _service file in the upload
    # that contains only those skipped services so OBS runs them server-side
    # at buildtime.  Otherwise drop _service entirely.
    if kiwi_svcs:
        filtered_root = ET.Element("services")
        for svc in kiwi_svcs:
            filtered_root.append(svc)
        (workdir / "_service").write_bytes(ET.tostring(filtered_root, encoding="utf-8"))
    else:
        (workdir / "_service").unlink(missing_ok=True)
    for child in list(workdir.iterdir()):
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        elif child.suffix == ".obscpio":
            child.unlink()

    return workdir
