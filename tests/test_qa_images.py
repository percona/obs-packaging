"""Image references in qa: parameters: shape and path rendering."""

import pytest

from percona_obs import qa_images


def test_is_image_ref_requires_mapping_with_image_key():
    assert qa_images.is_image_ref({"image": "percona-pgbouncer", "repository": "ubi9"})
    assert not qa_images.is_image_ref("reg/ubi9")
    assert not qa_images.is_image_ref({"repository": "ubi9"})
    assert not qa_images.is_image_ref(["a", "b"])
    assert not qa_images.is_image_ref(None)


@pytest.mark.parametrize(
    "ref, needle",
    [
        ({"repository": "ubi9"}, "image"),
        ({"image": "", "repository": "ubi9"}, "image"),
        ({"image": "x"}, "repository"),
        ({"image": "x", "repository": 9}, "repository"),
        ({"image": "x", "repository": "ubi9", "project": 18}, "project"),
        ({"image": "x", "repository": "ubi9", "tag": "18"}, "tag"),
    ],
)
def test_validate_image_ref_rejects_bad_shapes(ref, needle):
    with pytest.raises(SystemExit) as exc:
        qa_images.validate_image_ref(ref, "ppg:staging:18:containers", "REPOSITORY")
    msg = str(exc.value)
    assert "ppg:staging:18:containers" in msg
    assert "REPOSITORY" in msg
    assert needle in msg


def test_validate_image_ref_accepts_minimal_and_full():
    qa_images.validate_image_ref({"image": "x", "repository": "ubi9"}, "p", "R")
    qa_images.validate_image_ref(
        {"image": "x", "repository": "ubi9", "project": "ppg:staging:17:containers"},
        "p",
        "R",
    )


def test_registry_path_lowercases_and_slashes():
    assert (
        qa_images.registry_path(
            "reg.example", "isv:percona:PR:pr-124", "ppg:staging:18:containers", "ubi9"
        )
        == "reg.example/isv/percona/pr/pr-124/ppg/staging/18/containers/ubi9"
    )


def test_registry_path_lowercases_repository():
    assert qa_images.registry_path("reg.example", "isv:percona", "ppg:c", "UBI9") == (
        "reg.example/isv/percona/ppg/c/ubi9"
    )


def test_registry_path_matches_the_string_form_on_production():
    # What `${OBS_CONTAINER_REGISTRY}/${OBS_CONTAINER_REGISTRY_ROOTPRJ}/ppg/staging/18/containers/ubi9`
    # renders today with rootprj isv:percona and the default registry.
    assert (
        qa_images.registry_path(
            "registry.opensuse.org", "isv:percona", "ppg:staging:18:containers", "ubi9"
        )
        == "registry.opensuse.org/isv/percona/ppg/staging/18/containers/ubi9"
    )


# --- resolver -------------------------------------------------------------------


class _Lister:
    """Injected OBS listing: records calls, answers from a fixed map."""

    def __init__(self, present: dict[str, set[str]]):
        self.present = present
        self.calls: list[str] = []

    def __call__(self, obs_project: str) -> set[str]:
        self.calls.append(obs_project)
        return self.present.get(obs_project, set())


def _resolver(fallback, lister, repos=None):
    return qa_images.ImageResolver(
        registry="reg.example",
        rootprj="isv:percona:PR:pr-5",
        fallback_rootprj=fallback,
        list_packages=lister,
        list_repositories=None if repos is None else _Lister(repos),
    )


def test_no_fallback_never_queries_obs():
    lister = _Lister({})
    d = _resolver(None, lister).decide(
        "REPOSITORY",
        {"image": "img", "repository": "ubi9"},
        "ppg:staging:18:containers",
    )
    assert lister.calls == []
    assert (d.rootprj, d.reason) == ("isv:percona:PR:pr-5", "no-fallback")
    assert d.value == "reg.example/isv/percona/pr/pr-5/ppg/staging/18/containers/ubi9"


def test_present_image_uses_current_rootprj():
    lister = _Lister({"isv:percona:PR:pr-5:ppg:staging:18:containers": {"img"}})
    d = _resolver("isv:percona", lister).decide(
        "REPOSITORY",
        {"image": "img", "repository": "ubi9"},
        "ppg:staging:18:containers",
    )
    assert (d.rootprj, d.reason) == ("isv:percona:PR:pr-5", "present")
    assert d.value.startswith("reg.example/isv/percona/pr/pr-5/")


def test_absent_image_falls_back():
    lister = _Lister({"isv:percona:PR:pr-5:ppg:staging:18:containers": {"other"}})
    d = _resolver("isv:percona", lister).decide(
        "REPOSITORY",
        {"image": "img", "repository": "ubi9"},
        "ppg:staging:18:containers",
    )
    assert (d.rootprj, d.reason) == ("isv:percona", "fallback")
    assert d.value == "reg.example/isv/percona/ppg/staging/18/containers/ubi9"
    assert d.obs_project == "isv:percona:PR:pr-5:ppg:staging:18:containers"


def test_listing_is_cached_per_project():
    lister = _Lister({})
    r = _resolver("isv:percona", lister)
    r.decide("A", {"image": "a", "repository": "ubi9"}, "ppg:staging:18:containers")
    r.decide("B", {"image": "b", "repository": "ubi8"}, "ppg:staging:18:containers")
    r.decide("C", {"image": "c", "repository": "ubi9"}, "ppg:staging:17:containers")
    assert lister.calls == [
        "isv:percona:PR:pr-5:ppg:staging:18:containers",
        "isv:percona:PR:pr-5:ppg:staging:17:containers",
    ]


def test_explicit_project_overrides_lane_project():
    lister = _Lister({"isv:percona:PR:pr-5:ppg:staging:17:extras:containers": {"old"}})
    d = _resolver("isv:percona", lister).decide(
        "OLD_DOCKER_REPOSITORY",
        {
            "image": "old",
            "repository": "ubi9",
            "project": "ppg:staging:17:extras:containers",
        },
        "ppg:staging:18:extras:containers",
    )
    assert d.project == "ppg:staging:17:extras:containers"
    assert d.reason == "present"
    assert (
        d.value
        == "reg.example/isv/percona/pr/pr-5/ppg/staging/17/extras/containers/ubi9"
    )


def test_resolve_entry_images_rewrites_in_place_and_in_order():
    lister = _Lister({"isv:percona:PR:pr-5:ppg:staging:18:containers": {"new"}})
    entry = {
        "pipeline": "p",
        "parameters": {
            "TAG": "18",
            "REPOSITORY": {"image": "new", "repository": "ubi9"},
            "OLD_DOCKER_REPOSITORY": {"image": "old", "repository": "ubi9"},
            "PLATFORMS": ["a", "b"],
        },
    }
    decisions = qa_images.resolve_entry_images(
        entry, "ppg:staging:18:containers", _resolver("isv:percona", lister)
    )
    assert [d.param for d in decisions] == ["REPOSITORY", "OLD_DOCKER_REPOSITORY"]
    assert [d.reason for d in decisions] == ["present", "fallback"]
    p = entry["parameters"]
    assert p["TAG"] == "18" and p["PLATFORMS"] == ["a", "b"]
    assert (
        p["REPOSITORY"]
        == "reg.example/isv/percona/pr/pr-5/ppg/staging/18/containers/ubi9"
    )
    assert (
        p["OLD_DOCKER_REPOSITORY"]
        == "reg.example/isv/percona/ppg/staging/18/containers/ubi9"
    )


def test_resolve_entry_images_without_refs_is_a_noop():
    entry = {"pipeline": "p", "parameters": {"X": "1"}}
    assert (
        qa_images.resolve_entry_images(
            entry, "ppg:staging:18", _resolver(None, _Lister({}))
        )
        == []
    )
    assert entry["parameters"] == {"X": "1"}


_P18 = "isv:percona:PR:pr-5:ppg:staging:18:containers"


def test_present_package_in_missing_repository_falls_back():
    d = _resolver("isv:percona", _Lister({_P18: {"img"}}), {_P18: {"ubi9"}}).decide(
        "REPOSITORY",
        {"image": "img", "repository": "ubi8", "project": "ppg:staging:18:containers"},
        "ppg:staging:common:upgrade:containers",
    )
    assert (d.rootprj, d.reason) == ("isv:percona", "fallback-repo")
    assert d.value == "reg.example/isv/percona/ppg/staging/18/containers/ubi8"


def test_empty_repository_list_narrows_nothing():
    r = _resolver("isv:percona", _Lister({_P18: {"img"}}), {})
    ref = {"image": "img", "repository": "ubi8"}
    assert r.decide("REPOSITORY", ref, "ppg:staging:18:containers").reason == "present"
    entry = {"pipeline": "p", "parameters": {"REPOSITORY": ref}}
    assert r.outside_slice(entry, "ppg:staging:18:containers") is None


def test_outside_slice_only_for_own_images():
    r = _resolver("isv:percona", _Lister({}), {_P18: {"ubi9"}})
    own = {"pipeline": "p", "parameters": {"R": {"image": "i", "repository": "ubi8"}}}
    named_own = {
        "pipeline": "p",
        "parameters": {
            "R": {"image": "i", "repository": "ubi10", "project": "ppg:staging:18:containers"}
        },
    }
    other = {
        "pipeline": "p",
        "parameters": {
            "R": {"image": "i", "repository": "ubi8", "project": "ppg:staging:17:containers"}
        },
    }
    in_slice = {"pipeline": "p", "parameters": {"R": {"image": "i", "repository": "ubi9"}}}
    assert r.outside_slice(own, "ppg:staging:18:containers") == "ubi8"
    assert r.outside_slice(named_own, "ppg:staging:18:containers") == "ubi10"
    assert r.outside_slice(other, "ppg:staging:18:containers") is None
    assert r.outside_slice(in_slice, "ppg:staging:18:containers") is None


def test_outside_slice_without_fallback_never_queries_obs():
    repos = _Lister({_P18: {"ubi9"}})
    r = qa_images.ImageResolver(
        registry="reg.example",
        rootprj="isv:percona:PR:pr-5",
        fallback_rootprj=None,
        list_packages=_Lister({}),
        list_repositories=repos,
    )
    entry = {"pipeline": "p", "parameters": {"R": {"image": "i", "repository": "ubi8"}}}
    assert r.outside_slice(entry, "ppg:staging:18:containers") is None
    assert repos.calls == []
