"""Regressions for problems found in review of the initial commit.

Each of these failed before its fix, so they exist to stop the behaviour
drifting back rather than to describe anything new.
"""

import json

import pytest
from typer.testing import CliRunner

from bluecore_client import BluecoreClient, config
from bluecore_client.cli.app import app
from bluecore_client.cli.context import Settings
from bluecore_client.errors import APIError, AuthError, BluecoreError, NotFound
from bluecore_client.identifiers import extract_uuid
from tests.conftest import API_URL, KEYCLOAK_URL

runner = CliRunner()
BASE = ["--api-url", API_URL, "--keycloak-url", KEYCLOAK_URL]
CREDENTIALS = ["--username", "developer", "--password", "123456"]


@pytest.fixture(autouse=True)
def fresh_settings():
    from bluecore_client.cli.context import settings

    defaults = Settings()
    for name in vars(defaults):
        setattr(settings, name, getattr(defaults, name))
    yield


class TestConfigPrecedence:
    """An explicit argument has to beat the environment, not lose to it."""

    def test_explicit_bluecore_url_beats_the_api_url_variable(self, monkeypatch):
        monkeypatch.setenv("API_URL", "http://local.example/api")

        resolved = config.resolve(
            bluecore_url="https://remote.bcld.info", load_dotenv=False
        )

        assert resolved.api_url == "https://remote.bcld.info/api"

    def test_explicit_bluecore_url_beats_the_keycloak_variable(self, monkeypatch):
        monkeypatch.setenv("KEYCLOAK_EXTERNAL_URL", "http://local.example/keycloak")

        resolved = config.resolve(
            bluecore_url="https://remote.bcld.info", load_dotenv=False
        )

        assert resolved.keycloak_url == "https://remote.bcld.info/keycloak"

    def test_explicit_api_url_still_wins_over_everything(self, monkeypatch):
        monkeypatch.setenv("API_URL", "http://local.example/api")

        resolved = config.resolve(
            api_url="http://explicit/api",
            bluecore_url="https://remote.bcld.info",
            load_dotenv=False,
        )

        assert resolved.api_url == "http://explicit/api"

    def test_the_environment_is_still_used_when_nothing_is_passed(self, monkeypatch):
        monkeypatch.setenv("API_URL", "http://local.example/api")

        assert config.resolve(load_dotenv=False).api_url == "http://local.example/api"

    def test_load_profiles_reads_from_the_host_it_was_given(
        self, httpx_mock, monkeypatch, token_response
    ):
        """The bug this guards: with API_URL set, it copied local to local."""
        monkeypatch.setenv("API_URL", API_URL)
        token_response()
        httpx_mock.add_response(
            url="https://remote.bcld.info/api/search/profile?limit=50&offset=0",
            json={
                "results": [{"uri": "https://remote/profiles/p1", "data": {}}],
                "total": 1,
            },
        )
        httpx_mock.add_response(
            url=f"{API_URL}/profiles/",
            method="POST",
            status_code=201,
            json={"uri": "https://local/profiles/new"},
        )

        result = runner.invoke(
            app,
            [*BASE, *CREDENTIALS, "load", "profiles", "https://remote.bcld.info"],
        )

        assert result.exit_code == 0
        reads = [r for r in httpx_mock.get_requests() if "search/profile" in str(r.url)]
        assert len(reads) == 1
        assert "remote.bcld.info" in str(reads[0].url), "must read from the remote"


class TestContextNeverRaises:
    """as_rdf has to survive a deployment that doesn't serve a usable context."""

    def test_an_html_body_gives_none_rather_than_raising(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld",
            text="<html>not json</html>",
            headers={"content-type": "text/html"},
        )

        assert client.context() is None

    def test_a_failed_fetch_is_remembered_not_retried(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld", text="<html>nope</html>"
        )

        client.context()
        client.context()
        client.context()

        calls = [r for r in httpx_mock.get_requests() if "context" in str(r.url)]
        assert len(calls) == 1, "the failure should be cached too"

    def test_a_context_given_as_an_array_is_declined(self, httpx_mock, client):
        """Legal JSON-LD, but not usable as an inline substitute."""
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld",
            json={"@context": ["https://example.org/a", "https://example.org/b"]},
        )

        assert client.context() is None

    def test_rdf_output_survives_a_missing_context(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld", text="<html>nope</html>"
        )
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=20&offset=0",
            json={
                "results": [
                    {
                        "uri": "https://dev.bcld.info/works/w1",
                        "data": {
                            "@context": {
                                "@vocab": "http://id.loc.gov/ontologies/bibframe/"
                            },
                            "@id": "https://dev.bcld.info/works/w1",
                            "@type": ["Work"],
                        },
                    }
                ],
                "total": 1,
            },
        )

        result = runner.invoke(app, [*BASE, "-o", "turtle", "search", "moon"])

        assert result.exit_code == 0, "should not traceback"
        assert "works/w1" in result.stdout


class TestLimitAboveThePageCap:
    def test_a_limit_over_the_cap_keeps_fetching(self, httpx_mock):
        """--limit 150 used to print 100 and say nothing about the rest."""
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=0",
            json={
                "results": [
                    {"uri": f"https://dev.bcld.info/works/w{n}"} for n in range(100)
                ],
                "total": 500,
            },
        )
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=100",
            json={
                "results": [
                    {"uri": f"https://dev.bcld.info/works/w{n}"}
                    for n in range(100, 200)
                ],
                "total": 500,
            },
        )

        result = runner.invoke(app, [*BASE, "search", "moon", "--limit", "150"])

        assert result.exit_code == 0
        assert result.stdout.count("https://dev.bcld.info/works/") == 150
        assert "Showing 150 of 500" in result.output

    def test_a_limit_within_the_page_still_costs_one_request(self, httpx_mock):
        """Chaining pages must not cost an extra fetch when it isn't needed."""
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=5&offset=0",
            json={
                "results": [
                    {"uri": f"https://dev.bcld.info/works/w{n}"} for n in range(5)
                ],
                "total": 99,
            },
        )

        result = runner.invoke(app, [*BASE, "search", "moon", "--limit", "5"])

        assert result.exit_code == 0
        searches = [r for r in httpx_mock.get_requests() if "search" in str(r.url)]
        assert len(searches) == 1


class TestChangesJsonShape:
    """Empty and non-empty output must be the same shape."""

    def test_non_empty_is_an_envelope(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/1",
            json={"orderedItems": [{"type": "Update", "object": {"id": "w1"}}]},
        )
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/2",
            status_code=404,
            json={"detail": "not found"},
        )

        result = runner.invoke(app, [*BASE, "-o", "json", "changes", "list", "works"])

        payload = json.loads(result.stdout)
        assert payload["activities"][0]["type"] == "Update"

    def test_empty_is_the_same_envelope(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/1",
            json={"orderedItems": []},
        )

        result = runner.invoke(app, [*BASE, "-o", "json", "changes", "list", "works"])

        payload = json.loads(result.stdout)
        assert payload["activities"] == []
        assert payload["total"] == 0

    def test_an_object_given_as_a_bare_iri(self, httpx_mock):
        """Activity Streams allows this; it used to raise AttributeError."""
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/1",
            json={
                "orderedItems": [
                    {"type": "Update", "object": "https://dev.bcld.info/works/w1"}
                ]
            },
        )
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/2",
            status_code=404,
            json={"detail": "not found"},
        )

        result = runner.invoke(app, [*BASE, "changes", "list", "works"])

        assert result.exit_code == 0
        assert "works/w1" in result.stdout


class TestZeroLimit:
    def test_limit_zero_returns_nothing(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=1&offset=0",
            json={"results": [{"uri": "https://dev.bcld.info/works/w1"}], "total": 9},
        )

        result = runner.invoke(app, [*BASE, "-o", "json", "search", "moon", "-n", "0"])

        assert json.loads(result.stdout)["results"] == []


class TestErrorBodies:
    def test_a_json_array_error_body_keeps_the_status(self, httpx_mock, client):
        """A gateway can answer with an array; that must not become a TypeError."""
        httpx_mock.add_response(url=f"{API_URL}/works/w1", status_code=502, json=[])

        with pytest.raises(APIError) as caught:
            client.works.get("w1")

        assert caught.value.status_code == 502

    def test_a_json_string_error_body_keeps_the_status(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/works/w1", status_code=502, json="gateway error"
        )

        with pytest.raises(APIError) as caught:
            client.works.get("w1")

        assert caught.value.status_code == 502

    def test_a_keycloak_array_body_does_not_break_the_message(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{KEYCLOAK_URL}/realms/bluecore/protocol/openid-connect/token",
            method="POST",
            status_code=400,
            json=[],
        )

        with (
            BluecoreClient(
                api_url=API_URL,
                keycloak_url=KEYCLOAK_URL,
                username="u",
                password="p",
                load_dotenv=False,
            ) as connection,
            pytest.raises(AuthError, match="Keycloak rejected the login"),
        ):
            connection.login()

    def test_a_401_carries_its_status_and_response(self, httpx_mock, client):
        """So `except APIError` covers 401 like every other status."""
        # The client retries a 401 once with a fresh token, so both attempts
        # need an answer.
        httpx_mock.add_response(
            url=f"{API_URL}/works/w1",
            status_code=401,
            json={"detail": "nope"},
            is_reusable=True,
        )

        with pytest.raises(APIError) as caught:
            client.works.get("w1")

        assert isinstance(caught.value, AuthError)
        assert caught.value.status_code == 401
        assert caught.value.response is not None

    def test_not_found_is_still_distinct(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/works/w1", status_code=404, json={"detail": "gone"}
        )

        with pytest.raises(NotFound):
            client.works.get("w1")


class TestCollectionUri:
    def test_a_collection_uri_is_rejected(self):
        """/works has no identifier, and used to request /works/works."""
        with pytest.raises(BluecoreError, match="is a collection, not a single work"):
            extract_uuid("https://dev.bcld.info/works", expected="works")

    def test_a_collection_uri_with_a_trailing_slash_is_rejected(self):
        with pytest.raises(BluecoreError, match="collection"):
            extract_uuid("https://dev.bcld.info/works/", expected="works")

    def test_a_real_identifier_still_passes(self):
        assert (
            extract_uuid("https://dev.bcld.info/works/abc", expected="works") == "abc"
        )


class TestProfileCopyRobustness:
    def test_a_record_without_data_is_skipped_not_fatal(
        self, httpx_mock, token_response
    ):
        token_response()
        httpx_mock.add_response(
            url="https://remote.bcld.info/api/search/profile?limit=50&offset=0",
            json={
                "results": [
                    {"uri": "https://remote/profiles/broken"},
                    {"uri": "https://remote/profiles/ok", "data": {}},
                ],
                "total": 2,
            },
        )
        httpx_mock.add_response(
            url=f"{API_URL}/profiles/",
            method="POST",
            status_code=201,
            json={"uri": "https://local/profiles/new"},
        )

        result = runner.invoke(
            app,
            [*BASE, *CREDENTIALS, "load", "profiles", "https://remote.bcld.info"],
        )

        assert "no profile data" in result.output
        assert "Loaded 1 of 2" in result.output


class TestMarkupEscaping:
    def test_bracketed_values_survive_the_fields_display(self, httpx_mock):
        """rich silently swallows an unknown tag, losing the text."""
        result = runner.invoke(
            app,
            [
                "--api-url",
                API_URL,
                "--keycloak-url",
                KEYCLOAK_URL,
                "--username",
                "u[electronic resource]",
                "--password",
                "p",
                "whoami",
            ],
        )

        assert result.exit_code == 0
        assert "[electronic resource]" in result.stdout
