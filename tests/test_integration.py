"""Tests against a running Blue Core API.

These are skipped unless you ask for them:

    uv run pytest -m integration

They need a real deployment. For a local one, follow the bluecore_api README --
bring up bluecore-workflows with docker compose, then run ./start-dev.sh -- and
point the tests at it:

    export BLUECORE_TEST_API_URL=http://localhost:3000
    export KEYCLOAK_EXTERNAL_URL=http://localhost:8081/keycloak/
    export API_KEYCLOAK_USER=developer
    export API_KEYCLOAK_PASSWORD=123456
"""

import os

import pytest

from bluecore_client import BluecoreClient, NotFound

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def live():
    api_url = os.environ.get("BLUECORE_TEST_API_URL")
    if not api_url:
        pytest.skip("set BLUECORE_TEST_API_URL to run integration tests")

    with BluecoreClient(api_url=api_url) as client:
        yield client


def test_can_authenticate(live):
    token = live.login()

    assert token
    assert token.count(".") == 2, "expected a JWT"


def test_search_returns_results(live):
    page = live.search("", limit=5).first()

    assert page.total is not None
    assert len(page) <= 5


def test_search_results_look_like_json(live):
    """Results come back as ordinary dictionaries."""
    page = live.search("", limit=1).first()
    if not page.items:
        pytest.skip("no data loaded in this deployment")

    item = page.items[0]

    assert isinstance(item, dict)
    assert "uuid" in item


def test_fetching_a_work_by_uuid(live):
    page = live.search("", type="WORKS", limit=1).first()
    if not page.items:
        pytest.skip("no Works loaded in this deployment")

    work = live.works.get(page.items[0]["uuid"])

    assert isinstance(work, dict)
    assert "@context" in work


def test_turtle_comes_back_as_text(live):
    page = live.search("", type="WORKS", limit=1).first()
    if not page.items:
        pytest.skip("no Works loaded in this deployment")

    turtle = live.works.get(page.items[0]["uuid"], format="ttl")

    assert isinstance(turtle, str)
    assert "<" in turtle


def test_a_missing_uuid_raises_not_found(live):
    with pytest.raises(NotFound):
        live.works.get("00000000-0000-0000-0000-000000000000")


def test_profiles_page(live):
    pages = live.profiles.list(limit=5)
    first = pages.first()

    assert first.total is not None


def test_change_document_feed(live):
    feed = live.changes.feed("works")

    assert isinstance(feed, dict)


def test_paging_reaches_every_item(live):
    """Walk a small collection twice and confirm the counts agree."""
    pages = live.profiles.list(limit=2)
    total = pages.first().total
    if not total:
        pytest.skip("no profiles loaded in this deployment")

    walked = list(pages)

    assert len(walked) == total
