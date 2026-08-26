"""Paged CLI output streams as pages arrive.

Buffering every page before printing is what made a large --all look like a
hang, so these tests pin the streaming behaviour rather than just the output.
"""

import json

import pytest
from typer.testing import CliRunner

from bluecore_client.cli import paging
from bluecore_client.cli.app import app
from bluecore_client.cli.context import Settings
from tests.conftest import API_URL, KEYCLOAK_URL

runner = CliRunner()

BASE = ["--api-url", API_URL, "--keycloak-url", KEYCLOAK_URL]


@pytest.fixture(autouse=True)
def fresh_settings():
    from bluecore_client.cli.context import settings

    defaults = Settings()
    for name in vars(defaults):
        setattr(settings, name, getattr(defaults, name))
    yield


def search_page(offset, uuids, total, limit=100):
    return {
        "results": [
            {"uuid": u, "uri": f"https://dev.bcld.info/works/{u}"} for u in uuids
        ],
        "total": total,
    }


class TestPageSize:
    def test_all_asks_for_the_biggest_page_the_api_allows(self):
        """/search/ declares maximum: 100, so --all should ask for exactly that."""
        assert paging.page_size(20, all=True, cap=paging.SEARCH_MAX_PAGE) == 100

    def test_without_all_the_page_matches_the_limit(self):
        """No point fetching 100 to show 5."""
        assert paging.page_size(5, all=False) == 5

    def test_a_limit_over_the_cap_is_clamped(self):
        assert paging.page_size(500, all=False, cap=paging.SEARCH_MAX_PAGE) == 100

    def test_a_zero_limit_still_asks_for_something(self):
        assert paging.page_size(0, all=False) == 1


class TestStreaming:
    def test_all_walks_every_page(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=0",
            json=search_page(0, [f"w{n}" for n in range(100)], 150),
        )
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=100",
            json=search_page(100, [f"w{n}" for n in range(100, 150)], 150),
        )

        result = runner.invoke(app, [*BASE, "search", "moon", "--all"])

        assert result.exit_code == 0
        assert result.stdout.count("https://dev.bcld.info/works/") == 150

    def test_without_all_only_one_page_is_fetched(self, httpx_mock):
        """A second request would be wasted work, since the page is the limit."""
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=5&offset=0",
            json=search_page(0, [f"w{n}" for n in range(5)], 999),
        )

        result = runner.invoke(app, [*BASE, "search", "moon", "--limit", "5"])

        assert result.exit_code == 0
        searches = [r for r in httpx_mock.get_requests() if "search" in str(r.url)]
        assert len(searches) == 1
        assert "Showing 5 of 999" in result.output

    def test_output_appears_before_the_last_page_is_fetched(self, httpx_mock):
        """The real test of streaming: page two fails, page one still printed."""
        import httpx

        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=0",
            json=search_page(0, [f"w{n}" for n in range(100)], 200),
        )
        httpx_mock.add_exception(
            httpx.ReadTimeout("too slow"),
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=100",
        )

        result = runner.invoke(app, [*BASE, "search", "moon", "--all"])

        assert result.exit_code == 1, "the timeout should still be reported"
        assert result.stdout.count("https://dev.bcld.info/works/") == 100, (
            "results from the first page should already be on screen"
        )
        assert "Could not reach" in result.output

    def test_json_buffers_because_it_has_to(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=0",
            json=search_page(0, ["w1", "w2"], 2),
        )

        result = runner.invoke(app, [*BASE, "-o", "json", "search", "moon", "--all"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["total"] == 2
        assert len(payload["results"]) == 2


class TestCounts:
    def test_the_count_reflects_what_was_printed(self, httpx_mock):
        """A collection that runs dry early shouldn't be reported as its total.

        Offset paging can hand back fewer records than promised, so the count
        line has to describe the rows that actually appeared.
        """
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=0",
            json={"results": [{"uri": "https://dev.bcld.info/works/w1"}], "total": 99},
        )
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=1",
            json={"results": [], "total": 99},
        )

        result = runner.invoke(app, [*BASE, "search", "moon", "--all"])

        assert result.exit_code == 0
        assert "1 result (99 reported by the API)" in result.output

    def test_a_matching_count_reads_plainly(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=0",
            json={
                "results": [
                    {"uri": f"https://dev.bcld.info/works/w{n}"} for n in range(3)
                ],
                "total": 3,
            },
        )

        result = runner.invoke(app, [*BASE, "search", "moon", "--all"])

        assert "3 results" in result.output
        assert "reported by the API" not in result.output


class TestProfileList:
    def test_shows_only_the_uri(self, httpx_mock):
        """A UUID is already inside its URI; printing both is just noise."""
        httpx_mock.add_response(
            url=f"{API_URL}/profiles/?limit=20&offset=0",
            json={
                "profiles": [
                    {
                        "uuid": "p1",
                        "uri": "https://dev.bcld.info/profiles/p1",
                        "data": {},
                    }
                ],
                "total": 1,
            },
        )

        result = runner.invoke(app, [*BASE, "profile", "list"])

        assert result.exit_code == 0
        assert result.stdout.strip() == "https://dev.bcld.info/profiles/p1"

    def test_all_streams_every_page(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/profiles/?limit=100&offset=0",
            json={
                "profiles": [
                    {"uri": f"https://dev.bcld.info/profiles/p{n}"} for n in range(100)
                ],
                "total": 101,
            },
        )
        httpx_mock.add_response(
            url=f"{API_URL}/profiles/?limit=100&offset=100",
            json={
                "profiles": [{"uri": "https://dev.bcld.info/profiles/p100"}],
                "total": 101,
            },
        )

        result = runner.invoke(app, [*BASE, "profile", "list", "--all"])

        assert result.exit_code == 0
        assert result.stdout.count("https://dev.bcld.info/profiles/") == 101


class TestResourceList:
    def test_shows_only_the_uri(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/resources/?limit=20&offset=0",
            json={
                "resources": [{"id": 657017, "uri": "https://dev.bcld.info/agents/a1"}],
                "total": 1,
            },
        )

        result = runner.invoke(app, [*BASE, "resource", "list"])

        assert result.exit_code == 0
        assert result.stdout.strip() == "https://dev.bcld.info/agents/a1"
        assert "657017" not in result.stdout


class TestChangesList:
    def test_streams_across_feed_pages(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/1",
            json={
                "orderedItems": [
                    {
                        "published": "2026-01-01T00:00:00Z",
                        "type": "Update",
                        "object": {"id": "https://dev.bcld.info/works/w1"},
                    }
                ]
            },
        )
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/2",
            json={
                "orderedItems": [
                    {
                        "published": "2026-01-02T00:00:00Z",
                        "type": "Create",
                        "object": {"id": "https://dev.bcld.info/works/w2"},
                    }
                ]
            },
        )
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/3",
            status_code=404,
            json={"detail": "not found"},
        )

        result = runner.invoke(app, [*BASE, "changes", "list", "works", "--all"])

        assert result.exit_code == 0
        assert "w1" in result.stdout
        assert "w2" in result.stdout
        assert "activities" in result.output

    def test_limit_stops_the_walk_early(self, httpx_mock):
        """It should stop requesting pages once it has enough."""
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/1",
            json={
                "orderedItems": [
                    {"published": "t", "type": "Update", "object": {"id": f"w{n}"}}
                    for n in range(5)
                ]
            },
        )

        result = runner.invoke(app, [*BASE, "changes", "list", "works", "--limit", "2"])

        assert result.exit_code == 0
        pages = [r for r in httpx_mock.get_requests() if "page/" in str(r.url)]
        assert len(pages) == 1, "should not have asked for a second page"
