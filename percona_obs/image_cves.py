"""Container image CVE fixes, from the obs-dashboard CVE scan API.

``fetch_scans`` reads the scan rows of one image package, ``findings_by_repo``
reduces them to per-repository finding sets, and ``image_cve_lines`` renders
the CVEs a candidate image no longer carries relative to the previous one.
"""

import json
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable

_SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


@dataclass(frozen=True)
class Finding:
    id: str
    pkg: str
    installed: str
    fixed: str  # "" when the scanner names no fixing version
    severity: str  # upper case


Fetcher = Callable[[str], str]  # url -> response body


def fetch_scans(
    base_url: str, project: str, package: str, fetcher: Fetcher
) -> "list[dict[str, Any]]":
    query = urllib.parse.urlencode({"project": project, "package": package})
    url = f"{base_url.rstrip('/')}/api/cve/scans?{query}"
    data = json.loads(fetcher(url))
    if not isinstance(data, list):
        raise ValueError(f"unexpected dashboard response from {url}: not a list")
    return data


def findings_by_repo(rows: "list[dict[str, Any]]") -> "dict[str, set[Finding]]":
    """Union the findings of all architectures per repo.

    A row without ``findings`` (a clean image) still marks its repo as scanned.
    """
    result: "dict[str, set[Finding]]" = {}
    for row in rows:
        found = result.setdefault(row.get("repo", ""), set())
        for f in row.get("findings") or []:
            found.add(
                Finding(
                    id=f.get("id") or "",
                    pkg=f.get("pkg") or "",
                    installed=f.get("installed") or "",
                    fixed=f.get("fixed") or "",
                    severity=(f.get("severity") or "").upper(),
                )
            )
    return result


def _severity_rank(sev: str) -> "tuple[int, str]":
    if sev in _SEVERITY_ORDER:
        return (_SEVERITY_ORDER.index(sev), sev)
    return (len(_SEVERITY_ORDER), sev)


def image_cve_lines(
    keys: "list[str]",
    previous: "dict[str, set[Finding]]",
    candidate: "dict[str, set[Finding]]",
    candidate_pkgs: "dict[str, dict[str, str]]",
) -> "list[str]":
    """One entry per image whose CVEs were fixed, or that could not be compared."""
    lines: "list[str]" = []
    for key in keys:
        if key not in previous or key not in candidate:
            side = "candidate" if key in previous else "previous"
            lines.append(
                f"- Not scanned: {key} [container image] "
                f"(no dashboard scan of the {side} image)"
            )
            continue
        still_open = {f.id for f in candidate[key]}
        fixed = [f for f in previous[key] if f.id not in still_open]
        if not fixed:
            continue
        ids = {f.id for f in fixed}
        severities = sorted({f.severity for f in fixed}, key=_severity_rank)
        noun = "CVE" if len(ids) == 1 else "CVEs"
        out = [
            f"- {key} [container image]: fixes {len(ids)} "
            f"{'/'.join(severities)} {noun}"
        ]
        groups: "dict[tuple[str, str, str], set[str]]" = {}
        for f in fixed:
            groups.setdefault((f.pkg, f.installed, f.fixed), set()).add(f.id)
        pkgs = candidate_pkgs.get(key, {})
        for (pkg, installed, fix), gids in sorted(groups.items()):
            if pkg in pkgs:
                detail = f"{pkg} {installed} → {pkgs[pkg]}"
            elif fix:
                detail = f"{pkg} {installed} (fix: {fix})"
            else:
                detail = f"{pkg} {installed}"
            out.append(f"  - {detail}: {', '.join(sorted(gids))}")
        lines.append("\n".join(out))
    return lines
