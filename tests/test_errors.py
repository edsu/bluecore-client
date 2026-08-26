"""Error mapping: the right exception, carrying the API's own message."""

import pytest

from bluecore_client.errors import (
    APIError,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from tests.conftest import API_URL


def test_404_becomes_not_found_with_the_apis_detail(httpx_mock, client):
    httpx_mock.add_response(
        url=f"{API_URL}/works/missing",
        status_code=404,
        json={"detail": "Work missing not found"},
    )

    with pytest.raises(NotFound, match="Work missing not found"):
        client.works.get("missing")


def test_403_becomes_permission_denied(httpx_mock, client):
    httpx_mock.add_response(
        url=f"{API_URL}/works/w1",
        method="DELETE",
        status_code=403,
        json={"detail": "Not authorized"},
    )

    with pytest.raises(PermissionDenied, match="Not authorized"):
        client.works.delete("w1")


def test_422_reports_which_field_was_wrong(httpx_mock, client):
    httpx_mock.add_response(
        url=f"{API_URL}/works/",
        method="POST",
        status_code=422,
        json={
            "detail": [
                {"loc": ["body", "data"], "msg": "Field required", "type": "missing"}
            ]
        },
    )

    with pytest.raises(ValidationError, match="body.data: Field required"):
        client.works.create({})


def test_other_errors_keep_the_status_and_response(httpx_mock, client):
    httpx_mock.add_response(
        url=f"{API_URL}/export/",
        method="POST",
        status_code=503,
        json={"detail": "Airflow is unavailable"},
    )

    with pytest.raises(APIError) as caught:
        client.export("https://bcld.info/instances/abc", "a123")

    assert caught.value.status_code == 503
    assert "Airflow is unavailable" in str(caught.value)
    assert caught.value.response.status_code == 503


def test_a_non_json_error_body_still_produces_a_message(httpx_mock, client):
    httpx_mock.add_response(
        url=f"{API_URL}/works/w1", status_code=500, text="Internal Server Error"
    )

    with pytest.raises(APIError, match="Internal Server Error"):
        client.works.get("w1")


def test_the_failing_method_and_url_are_in_the_message(httpx_mock, client):
    httpx_mock.add_response(
        url=f"{API_URL}/works/w1", status_code=404, json={"detail": "nope"}
    )

    with pytest.raises(NotFound, match=r"GET http://testserver/api/works/w1"):
        client.works.get("w1")
