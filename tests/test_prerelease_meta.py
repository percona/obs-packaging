"""Pre-release (hop 1) project meta: branch redirection without the self path.

``sync prerelease`` passes ``branch_rootprj``/``active_projects`` and
``self_branch_path=False``.  The expected paths below are the exact order
``build_project_meta`` emits for this input: PR subproject path, production
fallback for the active subproject, then the redirected external path.  The
production fallback is emitted because ``existing_branch_projects`` is None in
hop 1; no leading ``<path>`` to the production release project itself exists,
and no ``<build>`` section is emitted.
"""

import xml.etree.ElementTree as ET

from percona_obs.common import build_project_meta


def test_prerelease_meta_has_no_self_branch_path_and_keeps_external_paths():
    repos = [
        {
            "name": "ubi9",
            "archs": ["x86_64"],
            "paths": [
                {"subproject": "ppg:releases:17", "repository": "UBI_9"},
                {"subproject": "common:containers:ubi9", "repository": "images"},
            ],
        }
    ]
    xml = build_project_meta(
        "PR:pr-5:ppg:releases:17:containers",
        "title",
        "desc",
        repos,
        "PR:pr-5",
        branch_rootprj="prod",
        active_projects={
            "PR:pr-5:ppg:releases:17",
            "PR:pr-5:ppg:releases:17:containers",
        },
        self_branch_path=False,
    )
    root = ET.fromstring(xml)
    assert root.find("build") is None
    repo = root.find("repository[@name='ubi9']")
    paths = [(p.get("project"), p.get("repository")) for p in repo.findall("path")]
    assert paths == [
        ("PR:pr-5:ppg:releases:17", "UBI_9"),
        ("prod:ppg:releases:17", "UBI_9"),
        ("prod:common:containers:ubi9", "images"),
    ]
    assert not any(p == "prod:ppg:releases:17:containers" for p, _ in paths)
