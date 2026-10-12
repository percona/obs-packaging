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
    assert qa_images.registry_path(
        "reg.example", "isv:percona:PR:pr-124", "ppg:staging:18:containers", "ubi9"
    ) == "reg.example/isv/percona/pr/pr-124/ppg/staging/18/containers/ubi9"


def test_registry_path_matches_the_string_form_on_production():
    # What `${OBS_CONTAINER_REGISTRY}/${OBS_CONTAINER_REGISTRY_ROOTPRJ}/ppg/staging/18/containers/ubi9`
    # renders today with rootprj isv:percona and the default registry.
    assert qa_images.registry_path(
        "registry.opensuse.org", "isv:percona", "ppg:staging:18:containers", "ubi9"
    ) == "registry.opensuse.org/isv/percona/ppg/staging/18/containers/ubi9"
