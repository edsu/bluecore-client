"""Accepting a Blue Core URI wherever a UUID is expected."""

import pytest

from bluecore_client.errors import BluecoreError
from bluecore_client.identifiers import extract_uuid

UUID = "4403fbce-ba01-5a4e-a8fc-03fc71caf56d"


def test_a_bare_uuid_passes_through():
    assert extract_uuid(UUID) == UUID


def test_a_work_uri():
    assert extract_uuid(f"https://dev.bcld.info/works/{UUID}") == UUID


def test_a_uri_with_the_api_prefix():
    assert extract_uuid(f"https://bcld.info/api/works/{UUID}") == UUID


def test_a_trailing_slash_is_ignored():
    assert extract_uuid(f"https://bcld.info/works/{UUID}/") == UUID


def test_surrounding_whitespace_is_ignored():
    """Pasting from a terminal or a browser tends to bring whitespace along."""
    assert extract_uuid(f"  https://bcld.info/works/{UUID}\n") == UUID


def test_an_http_uri_works_too():
    assert extract_uuid(f"http://localhost:3000/works/{UUID}") == UUID


def test_a_matching_expected_type_is_accepted():
    assert extract_uuid(f"https://bcld.info/works/{UUID}", expected="works") == UUID


def test_a_mismatched_type_is_reported_helpfully():
    """Pasting an Instance URI into a Work lookup should say so, not 404."""
    with pytest.raises(BluecoreError, match="points at instances, not works"):
        extract_uuid(f"https://bcld.info/instances/{UUID}", expected="works")


def test_the_message_points_at_the_right_command():
    with pytest.raises(BluecoreError, match="Try the hub command instead"):
        extract_uuid(f"https://bcld.info/hubs/{UUID}", expected="works")


def test_an_unrecognized_path_segment_is_left_alone():
    """Don't second-guess a URI shape we don't know about."""
    assert extract_uuid(f"https://example.org/things/{UUID}", expected="works") == UUID


def test_a_uri_with_no_path_is_an_error():
    with pytest.raises(BluecoreError, match="No identifier found"):
        extract_uuid("https://bcld.info")


@pytest.mark.parametrize(
    "kind", ["works", "instances", "hubs", "resources", "profiles"]
)
def test_every_resource_type_is_recognized(kind):
    assert extract_uuid(f"https://bcld.info/{kind}/{UUID}", expected=kind) == UUID
