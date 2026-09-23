"""Slice selection: filter wiring, profile parsing, in-slice predicates (percona_obs.project_config)."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import percona_obs.cmd_profile as cmd_profile
import percona_obs.common as common
from percona_obs.project_config import (
    RepositoryFilter,
    project_slice_name,
    resolve_project_config,
)

_ROOT = """\
repositories:
  - name: RockyLinux_9
    paths:
      - subproject: common:deps:build
        repository: RockyLinux_9
    archs: [x86_64]
  - name: UBI_9
    paths:
      - subproject: common:deps:build
        repository: UBI_9
    archs: [x86_64]
debuginfo: {RockyLinux_9: true, UBI_9: true}
"""

LABS = RepositoryFilter(include_repos=("UBI_*", "ubi*", "images"))
BOO = RepositoryFilter(exclude_repos=("UBI_*", "ubi*", "images"))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    def make(files: dict) -> Path:
        root = tmp_path / "root"
        root.mkdir(exist_ok=True)
        (root / "macros.yaml").write_text("- M: 1\n")
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        monkeypatch.setattr(common, "REPO_ROOT", root)
        return root

    return make


@pytest.fixture(autouse=True)
def _reset_default_filter():
    common.set_default_repository_filter(None)
    yield
    common.set_default_repository_filter(None)


def _names(cfg):
    return [r["name"] for r in cfg["repositories"]]


# --- resolver wiring -------------------------------------------------------------


def test_project_slice_name(repo):
    root = repo({"project.yaml": _ROOT, "ppg/staging/17/project.yaml": "title: S\n"})
    assert project_slice_name(root) == ""
    assert project_slice_name(root / "ppg" / "staging" / "17") == "ppg:staging:17"


def test_resolve_with_explicit_filter(repo):
    root = repo({"project.yaml": _ROOT, "a/project.yaml": "title: A\n"})
    assert _names(resolve_project_config(root / "a", repo_filter=LABS)) == ["UBI_9"]
    boo = resolve_project_config(root / "a", repo_filter=BOO)
    assert _names(boo) == ["RockyLinux_9"]
    assert boo["debuginfo"] == {"RockyLinux_9": True}


def test_resolve_uses_process_default_and_explicit_empty_wins(repo):
    root = repo({"project.yaml": _ROOT, "a/project.yaml": "title: A\n"})
    assert common.get_default_repository_filter() is RepositoryFilter.EMPTY
    common.set_default_repository_filter(LABS)
    assert _names(resolve_project_config(root / "a")) == ["UBI_9"]
    assert _names(common._load_project_config_with_inheritance(root / "a")) == ["UBI_9"]
    assert _names(
        resolve_project_config(root / "a", repo_filter=RepositoryFilter.EMPTY)
    ) == [
        "RockyLinux_9",
        "UBI_9",
    ]


# --- profiles --------------------------------------------------------------------


@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    d = tmp_path / ".profile"
    d.mkdir()
    monkeypatch.setattr(cmd_profile, "_PROFILES_DIR", d)
    return d


def test_load_profile_filter(profiles_dir):
    (profiles_dir / "labs.yaml").write_text(
        "apiurl: https://labs\nrootprj: percona\n"
        "include-repositories: ['UBI_*', 'ubi*', images]\nexclude-projects: [common:containers:ubi8]\n"
    )
    (profiles_dir / "dev.yaml").write_text("apiurl: http://dev\nrootprj: home:Admin\n")
    f = cmd_profile._load_profile_filter("labs")
    assert f == RepositoryFilter(
        include_repos=("UBI_*", "ubi*", "images"),
        exclude_projects=("common:containers:ubi8",),
    )
    assert cmd_profile._load_profile_filter("dev") is RepositoryFilter.EMPTY
    assert cmd_profile._load_profile_filter("missing") is RepositoryFilter.EMPTY
    # scalar loader unchanged for apiurl/rootprj and drops the lists
    p = cmd_profile._load_profile("labs")
    assert p["apiurl"] == "https://labs" and p["rootprj"] == "percona"
    assert "include-repositories" not in p


def test_profile_create_writes_and_round_trips_filter(profiles_dir, capsys):
    args = SimpleNamespace(
        apiurl="https://labs",
        rootprj="percona",
        name="labs",
        env_overrides=[],
        profile=None,
        include_repos=["UBI_*,ubi*", "images"],
        exclude_repos=[],
        include_projects=[],
        exclude_projects=["common:containers:ubi8"],
        narrow_repos=[],
    )
    cmd_profile.cmd_profile_create(args)
    data = yaml.safe_load((profiles_dir / "labs.yaml").read_text())
    assert data["include-repositories"] == ["UBI_*", "ubi*", "images"]
    assert data["exclude-projects"] == ["common:containers:ubi8"]
    assert "exclude-repositories" not in data
    # -P labs profile create labs with no filter flags keeps the lists
    args2 = SimpleNamespace(
        apiurl="https://labs",
        rootprj="percona",
        name="labs",
        env_overrides=["X:1"],
        profile="labs",
        include_repos=[],
        exclude_repos=[],
        include_projects=[],
        exclude_projects=[],
        narrow_repos=[],
    )
    cmd_profile.cmd_profile_create(args2)
    data2 = yaml.safe_load((profiles_dir / "labs.yaml").read_text())
    assert data2["include-repositories"] == ["UBI_*", "ubi*", "images"]
    assert data2["env"] == [{"name": "X", "value": "1"}]
    cmd_profile.cmd_profile_list(SimpleNamespace())
    out = capsys.readouterr().out
    assert "include-repositories:" in out and "UBI_*, ubi*, images" in out


# --- predicates ------------------------------------------------------------------

from percona_obs.project_config import package_in_slice, project_in_slice  # noqa: E402

_TREE = {
    "project.yaml": _ROOT,
    "ppg/staging/17/project.yaml": "title: S\n",
    "ppg/staging/17/percona-postgresql/obs/_service": "",
    "ppg/staging/17/bison/obs/_service": "",
    "ppg/staging/17/bison/package.yaml": "build:\n  UBI_9: false\n",
    "ppg/staging/17/blanket/obs/_service": "",
    "ppg/staging/17/blanket/package.yaml": "build:\n  disable: true\n",
    "ppg/staging/17/containers/project.yaml": (
        "repositories-inherit: false\nrepositories:\n  - name: ubi9\n    paths: []\n    archs: [x86_64]\n"
    ),
    "ppg/staging/17/containers/image/obs/Dockerfile": "FROM scratch\n",
    "ppg/staging/extras/project.yaml": "repositories-inherit: false\n",
}


def test_project_in_slice(repo):
    root = repo(_TREE)
    s17 = root / "ppg/staging/17"
    assert project_in_slice(s17, repo_filter=RepositoryFilter.EMPTY)
    assert project_in_slice(s17, repo_filter=LABS)
    assert project_in_slice(s17, repo_filter=BOO)
    assert project_in_slice(root, repo_filter=LABS)  # root keeps UBI_9
    containers = s17 / "containers"
    assert project_in_slice(containers, repo_filter=LABS)
    assert not project_in_slice(containers, repo_filter=BOO)
    assert not project_in_slice(
        containers, repo_filter=RepositoryFilter(exclude_projects=("*:containers",))
    )
    # zero repositories: out everywhere, even unfiltered
    assert not project_in_slice(
        root / "ppg/staging/extras", repo_filter=RepositoryFilter.EMPTY
    )
    # pre-resolved config and cache are honoured
    cfg = resolve_project_config(containers, repo_filter=BOO)
    cache: dict[Path, bool] = {}
    assert not project_in_slice(containers, repo_filter=BOO, config=cfg, cache=cache)
    assert cache == {containers: False}
    cache[containers] = True
    assert project_in_slice(
        containers, repo_filter=BOO, cache=cache
    )  # cache is authoritative


def test_package_in_slice(repo):
    root = repo(_TREE)
    s17 = root / "ppg/staging/17"
    assert package_in_slice(s17 / "percona-postgresql", repo_filter=LABS)
    assert package_in_slice(s17 / "percona-postgresql", repo_filter=BOO)
    assert not package_in_slice(
        s17 / "bison", repo_filter=LABS
    )  # disabled on its only labs repo
    assert package_in_slice(s17 / "bison", repo_filter=BOO)
    assert package_in_slice(
        s17 / "blanket", repo_filter=LABS
    )  # shorthand map is not per-repo
    assert package_in_slice(s17 / "containers" / "image", repo_filter=LABS)
    assert not package_in_slice(
        s17 / "containers" / "image", repo_filter=BOO
    )  # project out
    # default filter applies when none is passed
    common.set_default_repository_filter(LABS)
    assert not package_in_slice(s17 / "bison")
    common.set_default_repository_filter(None)


def test_package_in_slice_mixed_build_map(repo):
    # A build: map that mixes the {disable,enable} shorthand with per-repo keys
    # is not the shorthand: the key set is not a subset, so the per-repository
    # branch decides and UBI_9 (the only repo LABS keeps) is false → out.
    root = repo(
        {
            **_TREE,
            "ppg/staging/17/mixed-disable/obs/_service": "",
            "ppg/staging/17/mixed-disable/package.yaml": (
                "build:\n  disable: true\n  UBI_9: false\n"
            ),
            "ppg/staging/17/mixed-enable/obs/_service": "",
            "ppg/staging/17/mixed-enable/package.yaml": (
                "build:\n  enable: true\n  UBI_9: false\n"
            ),
        }
    )
    s17 = root / "ppg/staging/17"
    assert not package_in_slice(s17 / "mixed-disable", repo_filter=LABS)
    assert not package_in_slice(s17 / "mixed-enable", repo_filter=LABS)
    # the plain shorthand keeps counting as building
    assert package_in_slice(s17 / "blanket", repo_filter=LABS)
    # BOO keeps RockyLinux_9, which neither map disables
    assert package_in_slice(s17 / "mixed-disable", repo_filter=BOO)
    assert package_in_slice(s17 / "mixed-enable", repo_filter=BOO)


# --- sync push targets -----------------------------------------------------------

from types import SimpleNamespace as _NS  # noqa: E402

from percona_obs.cmd_sync import _require_targets_in_slice, _slice_targets  # noqa: E402
from percona_obs.cmd_sync import _collect_chain_projects  # noqa: E402
from percona_obs.targets import (  # noqa: E402
    _iter_project_chain,
    iter_project_ancestors,
)


def _targets(root):
    s17 = root / "ppg/staging/17"
    return [
        ("ROOT:ppg:staging:17", s17 / "percona-postgresql"),
        ("ROOT:ppg:staging:17", s17 / "bison"),
        ("ROOT:ppg:staging:17:containers", s17 / "containers" / "image"),
    ]


def test_slice_targets_labs_and_boo(repo):
    root = repo(_TREE)
    cache: dict[Path, bool] = {}
    kept, skipped_projects, skipped_packages = _slice_targets(
        _targets(root), {}, LABS, cache
    )
    assert [p.name for _, p in kept] == ["percona-postgresql", "image"]
    assert skipped_projects == []
    assert skipped_packages == ["ROOT:ppg:staging:17/bison"]
    kept, skipped_projects, skipped_packages = _slice_targets(
        _targets(root), {}, BOO, {}
    )
    assert [p.name for _, p in kept] == ["percona-postgresql", "bison"]
    assert skipped_projects == ["ROOT:ppg:staging:17:containers"]
    assert skipped_packages == []
    kept, sp, sk = _slice_targets(_targets(root), {}, RepositoryFilter.EMPTY, {})
    assert len(kept) == 3 and sp == [] and sk == []


def test_require_targets_in_slice_errors(repo):
    root = repo(_TREE)
    full = _NS(project=None, package=None)
    _require_targets_in_slice(full, [("x", root)], [], [])  # kept → fine
    with pytest.raises(
        SystemExit, match="nothing to sync: every target is out of slice"
    ):
        _require_targets_in_slice(full, [], ["ROOT:a"], [])
    with pytest.raises(SystemExit, match=r"ppg:staging:17/bison is out of slice"):
        _require_targets_in_slice(
            _NS(project="ppg:staging:17", package="bison"),
            [],
            [],
            ["ROOT:ppg:staging:17/bison"],
        )
    with pytest.raises(
        SystemExit, match=r"project 'ppg:staging:17:containers' is out of slice"
    ):
        _require_targets_in_slice(
            _NS(project="ppg:staging:17:containers", package=None),
            [],
            ["ROOT:ppg:staging:17:containers"],
            [],
        )


def test_iter_project_chain_skips_out_of_slice_projects(repo):
    root = repo(_TREE)
    (root / "ppg/staging/extras/containers").mkdir()
    (root / "ppg/staging/extras/containers/project.yaml").write_text(
        "repositories-inherit: false\nrepositories:\n  - name: ubi9\n    paths: []\n    archs: [x86_64]\n"
    )
    (root / "ppg/staging/project.yaml").write_text("title: staging\n")
    (root / "ppg/project.yaml").write_text("title: ppg\n")
    cache: dict[Path, bool] = {}
    common.set_default_repository_filter(LABS)
    names = [
        n
        for _, n, _ in _iter_project_chain(
            "ROOT:ppg:staging:extras:containers",
            root / "ppg/staging/extras/containers",
            cache,
        )
    ]
    # root, ppg, ppg:staging keep UBI_9; ppg:staging:extras has zero repos → skipped
    assert names == [
        "ROOT",
        "ROOT:ppg",
        "ROOT:ppg:staging",
        "ROOT:ppg:staging:extras:containers",
    ]
    common.set_default_repository_filter(BOO)
    names = [
        n
        for _, n, _ in _iter_project_chain(
            "ROOT:ppg:staging:extras:containers",
            root / "ppg/staging/extras/containers",
            {},
        )
    ]
    assert names == ["ROOT", "ROOT:ppg", "ROOT:ppg:staging"]


def _extras_tree(repo):
    """_TREE plus an in-slice ppg:staging:extras:containers under the zero-repo extras."""
    root = repo(_TREE)
    (root / "ppg/staging/extras/containers").mkdir()
    (root / "ppg/staging/extras/containers/project.yaml").write_text(
        "repositories-inherit: false\nrepositories:\n  - name: ubi9\n    paths: []\n    archs: [x86_64]\n"
    )
    (root / "ppg/staging/extras/containers/image/obs").mkdir(parents=True)
    (root / "ppg/staging/extras/containers/image/obs/Dockerfile").write_text(
        "FROM scratch\n"
    )
    (root / "ppg/staging/project.yaml").write_text("title: staging\n")
    (root / "ppg/project.yaml").write_text("title: ppg\n")
    return root


def test_iter_project_ancestors_yields_out_of_slice_intermediate(repo):
    # The orphan cleanup deletes recursively, so ppg:staging:extras (zero
    # repositories, never created) must still be reported as local or it takes
    # its in-slice child with it.
    root = _extras_tree(repo)
    common.set_default_repository_filter(LABS)
    args = (
        "ROOT:ppg:staging:extras:containers",
        root / "ppg/staging/extras/containers",
    )
    assert [n for _, n, _ in iter_project_ancestors(*args)] == [
        "ROOT",
        "ROOT:ppg",
        "ROOT:ppg:staging",
        "ROOT:ppg:staging:extras",
        "ROOT:ppg:staging:extras:containers",
    ]
    assert "ROOT:ppg:staging:extras" not in [
        n for _, n, _ in _iter_project_chain(*args, {})
    ]


def test_collect_chain_projects_protects_but_never_creates(repo):
    root = _extras_tree(repo)
    common.set_default_repository_filter(LABS)
    targets = [
        (
            "ROOT:ppg:staging:extras:containers",
            root / "ppg/staging/extras/containers/image",
        )
    ]
    local_names, all_projects = _collect_chain_projects(targets, {}, None)
    created = {name for name, _ in all_projects.values()}
    # b = the zero-repo intermediate: protected from deletion, never created
    assert "ROOT:ppg:staging:extras" in local_names
    assert "ROOT:ppg:staging:extras" not in created
    # c = the in-slice leaf, and the root: both protected and created
    for name in ("ROOT", "ROOT:ppg:staging:extras:containers"):
        assert name in local_names and name in created

    # --branch-from: an in-slice project with no promoted package is neither
    # created nor protected (the orphan sweep must still remove the stale PR
    # subproject); the zero-repo ancestor stays protected.
    local_names, all_projects = _collect_chain_projects(targets, {}, {"ROOT"})
    created = {name for name, _ in all_projects.values()}
    assert "ROOT:ppg:staging:extras:containers" not in local_names
    assert "ROOT:ppg:staging:extras:containers" not in created
    assert "ROOT:ppg:staging:extras" in local_names
    assert "ROOT" in local_names and "ROOT" in created


# --- verify: repository path integrity -----------------------------------------

from percona_obs.cmd_project import _validate_repo_path_refs  # noqa: E402


def test_validate_repo_path_refs(repo):
    root = repo(
        {
            "project.yaml": _ROOT,
            "common/deps/build/project.yaml": "title: B\n",
            "ppg/staging/17/project.yaml": "title: S\n",
            "ppg/staging/17/containers/project.yaml": (
                "repositories-inherit: false\nrepositories:\n"
                "  - name: ubi9\n    archs: [x86_64]\n    paths:\n"
                "      - subproject: ppg:staging:17\n        repository: UBI_9\n"
                "      - subproject: ppg:staging:17\n        repository: UBI_8\n"
                "      - subproject: does:not:exist\n        repository: UBI_9\n"
                "      - subproject: ${OBS_X}:y\n        repository: UBI_9\n"
            ),
            "ppg/releases/17/release.yaml": "project: ppg:staging:17\n",
            "ppg/releases/17/project.yaml": (
                "repositories-inherit: false\nrepositories:\n"
                "  - name: Debian_11\n    archs: [x86_64]\n    paths:\n"
                "      - subproject: common:deps:build\n        repository: Debian_11\n"
            ),
        }
    )

    def msgs(errors):
        return [(str(p.relative_to(root)), m) for p, m in errors]

    # unfiltered: UBI_8 is not defined by ppg:staging:17 (root only has RockyLinux_9/UBI_9);
    # the release tree's Debian_11 path (which common:deps:build does not define either) is
    # skipped — release snapshots are frozen and may reference repositories the live tree no
    # longer carries.
    assert msgs(_validate_repo_path_refs(root, None)) == [
        (
            "ppg/staging/17/containers/project.yaml",
            "repository 'ubi9' paths to 'ppg:staging:17/UBI_8', which that subproject does not define",
        )
    ]
    # boo: containers itself is out of slice → nothing to check there
    common.set_default_repository_filter(BOO)
    assert _validate_repo_path_refs(root, None) == []
    # labs with staging excluded by project glob: the target is out of slice
    common.set_default_repository_filter(
        RepositoryFilter(
            include_repos=("UBI_*", "ubi*"), exclude_projects=("ppg:staging:17",)
        )
    )
    assert msgs(_validate_repo_path_refs(root, None)) == [
        (
            "ppg/staging/17/containers/project.yaml",
            "repository 'ubi9' paths to subproject 'ppg:staging:17', which is out of slice",
        ),
        (
            "ppg/staging/17/containers/project.yaml",
            "repository 'ubi9' paths to subproject 'ppg:staging:17', which is out of slice",
        ),
    ]


# --- profile create --narrow-repos -------------------------------------------------


def _create_args(profiles_dir, **over):
    base = dict(
        apiurl="https://x",
        rootprj="r",
        name="pr-1",
        env_overrides=[],
        profile=None,
        include_repos=[],
        exclude_repos=[],
        include_projects=[],
        exclude_projects=[],
        narrow_repos=[],
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_narrow_repos_intersects_with_instance_filter(profiles_dir):
    # labs instance narrowed by labels RockyLinux_9, ubi9-images (→ ubi9, UBI_9) and ssl*
    args = _create_args(
        profiles_dir,
        include_repos=["UBI_*,ubi*,images"],
        exclude_projects=["common:containers:ubi8"],
        narrow_repos=["RockyLinux_9,ubi9", "UBI_9", "ssl*"],
    )
    cmd_profile.cmd_profile_create(args)
    data = yaml.safe_load((profiles_dir / "pr-1.yaml").read_text())
    assert data["include-repositories"] == ["ubi9", "UBI_9"]
    assert data["exclude-projects"] == ["common:containers:ubi8"]
    # boo instance narrowed by the same labels keeps RockyLinux_9 and ssl*
    args = _create_args(
        profiles_dir,
        name="pr-2",
        exclude_repos=["UBI_*,ubi*,images"],
        narrow_repos=["RockyLinux_9,ubi9,UBI_9,ssl*"],
    )
    cmd_profile.cmd_profile_create(args)
    data = yaml.safe_load((profiles_dir / "pr-2.yaml").read_text())
    assert data["include-repositories"] == ["RockyLinux_9", "ssl*"]
    assert data["exclude-repositories"] == ["UBI_*", "ubi*", "images"]


def test_narrow_repos_empty_result_exits_3(profiles_dir):
    args = _create_args(
        profiles_dir, include_repos=["UBI_*"], narrow_repos=["RockyLinux_9,Debian_13"]
    )
    with pytest.raises(SystemExit) as exc:
        cmd_profile.cmd_profile_create(args)
    assert exc.value.code == 3
    assert not (profiles_dir / "pr-1.yaml").exists()
