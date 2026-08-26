"""Output redirected to a file can be fed straight back in.

The loading workflow parses uploads with format="json-ld" and nothing else, so
anything the client emits in another serialization has to be converted before
it is sent -- otherwise the upload is accepted and then fails inside Airflow,
long after the call returned.
"""

import json

import pytest
from rdflib import Graph
from rdflib.compare import isomorphic
from typer.testing import CliRunner

from bluecore_client import BluecoreClient
from bluecore_client.cli.app import app
from bluecore_client.cli.context import Settings
from bluecore_client.errors import BluecoreError
from bluecore_client.formats import Output
from tests.conftest import API_URL, KEYCLOAK_URL

runner = CliRunner()
BASE = ["--api-url", API_URL, "--keycloak-url", KEYCLOAK_URL]
CREDENTIALS = ["--username", "developer", "--password", "123456"]

CONTEXT = {"@vocab": "http://id.loc.gov/ontologies/bibframe/"}
GRAPH = {
    "@context": "https://dev.bcld.info/api/context.jsonld",
    "@id": "https://dev.bcld.info/works/w1",
    "@type": ["Work"],
    "title": [{"@type": "Title", "mainTitle": "Moon handbooks"}],
}


@pytest.fixture(autouse=True)
def fresh_settings():
    from bluecore_client.cli.context import settings

    defaults = Settings()
    for name in vars(defaults):
        setattr(settings, name, getattr(defaults, name))
    yield


@pytest.fixture
def search_result(httpx_mock):
    httpx_mock.add_response(
        url=f"{API_URL}/context.jsonld",
        json={"@context": CONTEXT},
        is_reusable=True,
        is_optional=True,
    )
    httpx_mock.add_response(
        url=f"{API_URL}/search/?q=moon&type=all&limit=20&offset=0",
        json={
            "results": [{"uri": "https://dev.bcld.info/works/w1", "data": GRAPH}],
            "total": 1,
        },
    )


class TestJsonLdIsAGraph:
    """It used to emit the API envelope, which could not be loaded back."""

    def test_search_as_jsonld_is_a_graph(self, search_result):
        result = runner.invoke(app, [*BASE, "-o", "jsonld", "search", "moon"])

        document = json.loads(result.stdout)
        assert "@graph" in document or "@id" in document
        assert "results" not in document, "not the API envelope"

    def test_it_parses_as_the_loader_would(self, search_result):
        result = runner.invoke(app, [*BASE, "-o", "jsonld", "search", "moon"])

        graph = Graph()
        graph.parse(data=result.stdout, format="json-ld")
        assert len(graph) > 0

    def test_json_still_gives_the_api_envelope(self, search_result):
        """Scripts wanting total and per-record metadata keep it."""
        result = runner.invoke(app, [*BASE, "-o", "json", "search", "moon"])

        document = json.loads(result.stdout)
        assert set(document) == {"total", "results"}

    def test_jsonld_and_turtle_describe_the_same_graph(self, httpx_mock):
        for _ in range(2):
            httpx_mock.add_response(
                url=f"{API_URL}/search/?q=moon&type=all&limit=20&offset=0",
                json={
                    "results": [
                        {"uri": "https://dev.bcld.info/works/w1", "data": GRAPH}
                    ],
                    "total": 1,
                },
            )
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld",
            json={"@context": CONTEXT},
            is_reusable=True,
        )

        as_jsonld = runner.invoke(app, [*BASE, "-o", "jsonld", "search", "moon"])
        as_turtle = runner.invoke(app, [*BASE, "-o", "turtle", "search", "moon"])

        a, b = Graph(), Graph()
        a.parse(data=as_jsonld.stdout, format="json-ld")
        b.parse(data=as_turtle.stdout, format="turtle")
        assert isomorphic(a, b)

    def test_change_feeds_are_left_as_activity_streams(self, httpx_mock):
        """Those are already JSON-LD; merging them as BIBFRAME makes no sense."""
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/1",
            json={"orderedItems": [{"type": "Update", "object": {"id": "w1"}}]},
        )
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/2",
            status_code=404,
            json={"detail": "not found"},
        )

        result = runner.invoke(app, [*BASE, "-o", "jsonld", "changes", "list"])

        assert set(json.loads(result.stdout)) == {"total", "activities"}

    def test_jsonld_is_treated_as_a_graph_output(self):
        assert Output.JSONLD.emits_graph
        assert not Output.JSON.emits_graph
        assert not Output.JSONLD.is_rdf, "it is still a JSON syntax"


class TestUploadConversion:
    def graph_file(self, tmp_path, suffix, serialization):
        source = Graph()
        source.parse(data=json.dumps({**GRAPH, "@context": CONTEXT}), format="json-ld")
        path = tmp_path / f"records{suffix}"
        path.write_text(source.serialize(format=serialization))
        return path, source

    @pytest.mark.parametrize(
        "suffix,serialization",
        [(".ttl", "turtle"), (".rdf", "xml"), (".nt", "nt"), (".jsonld", "json-ld")],
    )
    def test_every_serialization_uploads_as_json_ld(
        self, httpx_mock, client, tmp_path, suffix, serialization
    ):
        path, source = self.graph_file(tmp_path, suffix, serialization)
        httpx_mock.add_response(
            url=f"{API_URL}/batches/upload/", method="POST", json={"workflow_id": "w"}
        )

        client.batches.upload(path)

        sent = httpx_mock.get_requests()[-1].read()
        assert b"records.jsonld" in sent
        body = sent.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
        uploaded = Graph()
        uploaded.parse(data=body.decode(), format="json-ld")
        assert isomorphic(source, uploaded), "conversion must not lose triples"

    def test_an_archive_is_sent_untouched(self, httpx_mock, client, tmp_path):
        """The workflow unpacks these, and picks itself by extension."""
        archive = tmp_path / "records.zip"
        archive.write_bytes(b"PK\x03\x04 not really a zip")
        httpx_mock.add_response(
            url=f"{API_URL}/batches/upload/", method="POST", json={"workflow_id": "w"}
        )

        client.batches.upload(archive)

        sent = httpx_mock.get_requests()[-1].read()
        assert b"records.zip" in sent
        assert b"not really a zip" in sent

    def test_convert_false_sends_the_bytes_as_they_are(
        self, httpx_mock, client, tmp_path
    ):
        path, _ = self.graph_file(tmp_path, ".ttl", "turtle")
        httpx_mock.add_response(
            url=f"{API_URL}/batches/upload/", method="POST", json={"workflow_id": "w"}
        )

        client.batches.upload(path, convert=False)

        sent = httpx_mock.get_requests()[-1].read()
        assert b"records.ttl" in sent
        assert b"@prefix" in sent

    def test_an_unrecognizable_extension_is_reported(self, client, tmp_path):
        path = tmp_path / "records.whatever"
        path.write_text("something")

        with pytest.raises(BluecoreError, match="Cannot tell what"):
            client.batches.upload(path)

    def test_unparseable_content_names_the_format(self, client, tmp_path):
        path = tmp_path / "records.ttl"
        path.write_text("this is not turtle {{{")

        with pytest.raises(BluecoreError, match="Could not read records.ttl as turtle"):
            client.batches.upload(path)


class TestEndToEnd:
    def test_redirected_turtle_can_be_uploaded(
        self, httpx_mock, tmp_path, token_response, search_result
    ):
        """The whole point of the question: search > file > load."""
        token_response()

        # Redirect turtle to a file, the way a shell would.
        result = runner.invoke(app, [*BASE, "-o", "turtle", "search", "moon"])
        assert result.exit_code == 0
        saved = tmp_path / "moon.ttl"
        saved.write_text(result.stdout)

        httpx_mock.add_response(
            url=f"{API_URL}/batches/upload/",
            method="POST",
            json={"workflow_id": "wf-1"},
        )

        loaded = runner.invoke(app, [*BASE, *CREDENTIALS, "load", "file", str(saved)])

        assert loaded.exit_code == 0
        assert "wf-1" in loaded.output
        sent = httpx_mock.get_requests()[-1].read()
        assert b"moon.jsonld" in sent, "converted on the way out"

    def test_a_single_work_round_trips_through_update(
        self, httpx_mock, tmp_path, token_response
    ):
        token_response()
        httpx_mock.add_response(url=f"{API_URL}/works/w1", json=GRAPH)

        viewed = runner.invoke(app, [*BASE, "-o", "jsonld", "work", "view", "w1"])
        saved = tmp_path / "work.jsonld"
        saved.write_text(viewed.stdout)

        httpx_mock.add_response(
            url=f"{API_URL}/works/w1", method="PUT", json={"uuid": "w1"}
        )

        updated = runner.invoke(
            app, [*BASE, *CREDENTIALS, "work", "update", "w1", str(saved)]
        )

        assert updated.exit_code == 0
        assert json.loads(httpx_mock.get_requests()[-1].read()) == GRAPH


class TestLibraryHelper:
    def test_as_rdf_can_produce_json_ld(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld", json={"@context": CONTEXT}
        )

        document = json.loads(client.as_rdf(GRAPH, "jsonld"))

        assert "@context" in document

    def test_a_client_built_from_the_output_sees_the_same_graph(
        self, httpx_mock, client
    ):
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld", json={"@context": CONTEXT}
        )

        turtle = client.as_rdf(GRAPH, "turtle")
        jsonld = client.as_rdf(GRAPH, "jsonld")

        a, b = Graph(), Graph()
        a.parse(data=turtle, format="turtle")
        b.parse(data=jsonld, format="json-ld")
        assert isomorphic(a, b)


def test_bluecore_client_is_importable():
    assert BluecoreClient is not None
