"""Pre-release (hop 1) project meta: branch redirection without branch fallbacks.

``sync prerelease`` passes ``branch_rootprj``/``active_projects`` and
``branch_fallbacks=False``.  With False, ``build_project_meta`` emits no path
to the production counterpart of the project itself and no production fallback
for active subprojects, so a first-ever release (no production release project
yet) does not trip repository_access_failure.  The redirected external path
(``common:containers:ubi9``) is kept.  The default (True) is pinned too, since
``sync push --branch-from`` depends on it.
"""

import xml.etree.ElementTree as ET

from percona_obs.common import build_project_meta

_REPOS = [
    {
        "name": "ubi9",
        "archs": ["x86_64"],
        "paths": [
            {"subproject": "ppg:releases:17", "repository": "UBI_9"},
            {"subproject": "common:containers:ubi9", "repository": "images"},
        ],
    }
]
_ACTIVE = {"PR:pr-5:ppg:releases:17", "PR:pr-5:ppg:releases:17:containers"}


def _ubi9_paths(**kwargs):
    xml = build_project_meta(
        "PR:pr-5:ppg:releases:17:containers",
        "title",
        "desc",
        _REPOS,
        "PR:pr-5",
        branch_rootprj="prod",
        active_projects=_ACTIVE,
        **kwargs,
    )
    root = ET.fromstring(xml)
    assert root.find("build") is None
    repo = root.find("repository[@name='ubi9']")
    return [(p.get("project"), p.get("repository")) for p in repo.findall("path")]


def test_prerelease_meta_has_no_branch_fallbacks_and_keeps_external_paths():
    assert _ubi9_paths(branch_fallbacks=False) == [
        ("PR:pr-5:ppg:releases:17", "UBI_9"),
        ("prod:common:containers:ubi9", "images"),
    ]


def test_default_branch_fallbacks_still_emits_production_paths():
    paths = _ubi9_paths()
    assert ("prod:ppg:releases:17", "UBI_9") in paths
    assert ("prod:ppg:releases:17:containers", "ubi9") in paths
