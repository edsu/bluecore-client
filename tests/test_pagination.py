"""Paging over collections."""

from bluecore_client.pagination import Page, Pages, read_page
from tests.conftest import API_URL


def envelope(key, items, total, links=None):
    return {key: items, "total": total, "links": links or {}}


def test_read_page_finds_the_items_under_the_endpoints_own_key():
    page = read_page(
        envelope("profiles", [{"uri": "a"}], 1), key="profiles", limit=10, offset=0
    )

    assert page.items == [{"uri": "a"}]
    assert page.total == 1


def test_read_page_falls_back_to_the_first_list_when_the_key_is_wrong():
    """The API names its collection differently per endpoint, so be forgiving."""
    page = read_page(
        envelope("resources", [{"uri": "a"}], 1), key="results", limit=10, offset=0
    )

    assert page.items == [{"uri": "a"}]


def test_has_more_uses_total_rather_than_a_full_page():
    """bluecore_api emits a next link on an exact final page; don't trust it."""
    page = Page(items=[1, 2], total=2, limit=2, offset=0, links={"next": "..."})

    assert not page.has_more


def test_has_more_when_there_are_more():
    page = Page(items=[1, 2], total=5, limit=2, offset=0)

    assert page.has_more


def test_has_more_falls_back_to_page_fullness_without_a_total():
    assert Page(items=[1, 2], total=None, limit=2, offset=0).has_more
    assert not Page(items=[1], total=None, limit=2, offset=0).has_more


def test_an_empty_page_is_the_end():
    assert not Page(items=[], total=10, limit=2, offset=0).has_more


def test_iterating_walks_every_page(httpx_mock, client):
    httpx_mock.add_response(
        url=f"{API_URL}/profiles/?limit=2&offset=0",
        json=envelope("profiles", [{"uri": "a"}, {"uri": "b"}], 5),
    )
    httpx_mock.add_response(
        url=f"{API_URL}/profiles/?limit=2&offset=2",
        json=envelope("profiles", [{"uri": "c"}, {"uri": "d"}], 5),
    )
    httpx_mock.add_response(
        url=f"{API_URL}/profiles/?limit=2&offset=4",
        json=envelope("profiles", [{"uri": "e"}], 5),
    )

    uris = [p["uri"] for p in client.profiles.list(limit=2)]

    assert uris == ["a", "b", "c", "d", "e"]


def test_iterating_stops_without_asking_for_an_empty_page(httpx_mock, client):
    """Total is a multiple of limit, so a naive walk would fetch one page too many."""
    httpx_mock.add_response(
        url=f"{API_URL}/profiles/?limit=2&offset=0",
        json=envelope("profiles", [{"uri": "a"}, {"uri": "b"}], 4),
    )
    httpx_mock.add_response(
        url=f"{API_URL}/profiles/?limit=2&offset=2",
        json=envelope("profiles", [{"uri": "c"}, {"uri": "d"}], 4),
    )

    uris = [p["uri"] for p in client.profiles.list(limit=2)]

    assert uris == ["a", "b", "c", "d"]
    collection_calls = [
        r for r in httpx_mock.get_requests() if "profiles" in str(r.url)
    ]
    assert len(collection_calls) == 2


def test_pages_yields_pages_with_their_metadata(httpx_mock, client):
    httpx_mock.add_response(
        url=f"{API_URL}/profiles/?limit=2&offset=0",
        json=envelope("profiles", [{"uri": "a"}, {"uri": "b"}], 3),
    )
    httpx_mock.add_response(
        url=f"{API_URL}/profiles/?limit=2&offset=2",
        json=envelope("profiles", [{"uri": "c"}], 3),
    )

    pages = list(client.profiles.list(limit=2).pages())

    assert len(pages) == 2
    assert pages[0].total == 3
    assert pages[0].offset == 0
    assert pages[1].offset == 2
    assert len(pages[0]) == 2


def test_first_fetches_only_one_page(httpx_mock, client):
    httpx_mock.add_response(
        url=f"{API_URL}/profiles/?limit=10&offset=0",
        json=envelope("profiles", [{"uri": "a"}], 100),
    )

    page = client.profiles.list().first()

    assert page.total == 100
    assert len(page) == 1


def test_offset_starts_where_asked(httpx_mock, client):
    httpx_mock.add_response(
        url=f"{API_URL}/profiles/?limit=2&offset=6",
        json=envelope("profiles", [{"uri": "g"}], 7),
    )

    assert [p["uri"] for p in client.profiles.list(limit=2, offset=6)] == ["g"]


def test_nothing_is_fetched_until_you_iterate(httpx_mock, client):
    """Pages are lazy, which is what makes them safe in a notebook.

    Nothing is requested here at all, not even the login.
    """
    pages = client.profiles.list()

    assert isinstance(pages, Pages)
    assert [r for r in httpx_mock.get_requests() if "profiles" in str(r.url)] == []
