"""Output serializations: JSON by default, RDF on request.

A single resource is serialized by the API. A result set can't be -- collection
endpoints only ever return JSON-LD -- so those are converted here, which is
what these mostly cover.
"""

import json

import pytest
from rdflib import Graph
from typer.testing import CliRunner

from bluecore_client import rdf
from bluecore_client.cli.app import app
from bluecore_client.cli.context import Settings
from bluecore_client.errors import BluecoreError
from bluecore_client.formats import Output
from tests.conftest import API_URL, KEYCLOAK_URL

runner = CliRunner()
BASE = ["--api-url", API_URL, "--keycloak-url", KEYCLOAK_URL]

CONTEXT = {
    "@vocab": "http://id.loc.gov/ontologies/bibframe/",
    "bflc": "http://id.loc.gov/ontologies/bflc/",
}

WORK_GRAPH = {
    "@context": "https://dev.bcld.info/api/context.jsonld",
    "@id": "https://dev.bcld.info/works/w1",
    "@type": ["Work", "Text"],
    "title": [{"@type": "Title", "mainTitle": "Moon handbooks"}],
}


@pytest.fixture(autouse=True)
def fresh_settings():
    from bluecore_client.cli.context import settings

    defaults = Settings()
    for name in vars(defaults):
        setattr(settings, name, getattr(defaults, name))
    yield


def search_response(count=2, total=None):
    return {
        "results": [
            {
                "uuid": f"w{n}",
                "uri": f"https://dev.bcld.info/works/w{n}",
                "data": {**WORK_GRAPH, "@id": f"https://dev.bcld.info/works/w{n}"},
            }
            for n in range(count)
        ],
        "total": total if total is not None else count,
    }


class TestOutputEnum:
    @pytest.mark.parametrize(
        "output,expected",
        [
            (Output.TEXT, "jsonld"),
            (Output.JSON, "json"),
            (Output.JSONLD, "jsonld"),
            (Output.TURTLE, "ttl"),
            (Output.RDFXML, "rdf"),
            (Output.NTRIPLES, "nt"),
            (Output.SINOPIA, "vnd.sinopia.json"),
        ],
    )
    def test_each_output_maps_to_an_api_format(self, output, expected):
        """Every output has to correspond to something the API can serve."""
        assert output.format_key == expected

    def test_text_is_the_only_streaming_output(self):
        """Everything else is one document, so it has to be buffered."""
        streaming = [o for o in Output if not o.is_document]
        assert streaming == [Output.TEXT]

    def test_rdf_outputs_are_the_ones_needing_conversion(self):
        assert {o for o in Output if o.is_rdf} == {
            Output.TURTLE,
            Output.RDFXML,
            Output.NTRIPLES,
        }


class TestRdfConversion:
    def test_a_graph_becomes_turtle(self):
        turtle = rdf.serialize([WORK_GRAPH], "turtle", context=CONTEXT)

        assert "Moon handbooks" in turtle
        Graph().parse(data=turtle, format="turtle")  # round-trips

    def test_several_graphs_merge_into_one(self):
        graphs = [
            {**WORK_GRAPH, "@id": "https://dev.bcld.info/works/w1"},
            {**WORK_GRAPH, "@id": "https://dev.bcld.info/works/w2"},
        ]

        graph = rdf.to_graph(graphs, context=CONTEXT)
        subjects = {str(s) for s in graph.subjects()}

        assert "https://dev.bcld.info/works/w1" in subjects
        assert "https://dev.bcld.info/works/w2" in subjects

    def test_the_context_is_inlined_rather_than_fetched(self, httpx_mock):
        """A remote @context would otherwise be fetched once per document."""
        rdf.serialize([WORK_GRAPH] * 5, "ntriples", context=CONTEXT)

        assert httpx_mock.get_requests() == [], "should not have hit the network"

    def test_graphs_of_unwraps_collection_records(self):
        records = search_response(2)["results"]

        graphs = rdf.graphs_of(records)

        assert len(graphs) == 2
        assert all("@id" in g for g in graphs)

    def test_graphs_of_passes_through_a_bare_graph(self):
        assert rdf.graphs_of([WORK_GRAPH]) == [WORK_GRAPH]

    def test_graphs_of_skips_records_with_no_graph(self):
        assert rdf.graphs_of([{"uuid": "w1"}]) == []

    def test_an_unknown_serialization_says_what_is_available(self):
        with pytest.raises(BluecoreError, match="not an RDF serialization"):
            rdf.serialize([WORK_GRAPH], "yaml")

    def test_unparseable_json_ld_names_the_resource(self):
        with pytest.raises(BluecoreError, match="works/broken"):
            rdf.to_graph(
                [
                    {
                        "@id": "https://dev.bcld.info/works/broken",
                        "@context": {"@base": ["not", "valid"]},
                    }
                ]
            )


class TestSingleResourceOutput:
    def test_turtle_comes_from_the_api_not_from_us(self, httpx_mock, token_response):
        """The deployment's own serialization beats converting locally."""
        token_response()
        httpx_mock.add_response(
            url=f"{API_URL}/works/w1",
            text="<https://dev.bcld.info/works/w1> a bf:Work .",
        )

        result = runner.invoke(app, [*BASE, "-o", "turtle", "work", "view", "w1"])

        assert result.exit_code == 0
        assert "a bf:Work" in result.stdout
        assert httpx_mock.get_requests()[-1].headers["Accept"] == "text/turtle"

    @pytest.mark.parametrize(
        "output,media_type",
        [
            ("json", "application/json"),
            ("jsonld", "application/ld+json"),
            ("rdfxml", "application/rdf+xml"),
            ("ntriples", "application/n-triples"),
            ("sinopia", "application/vnd.sinopia+json"),
        ],
    )
    def test_each_output_asks_the_api_for_the_right_thing(
        self, httpx_mock, output, media_type
    ):
        httpx_mock.add_response(url=f"{API_URL}/works/w1", json={}, text=None)

        runner.invoke(app, [*BASE, "-o", output, "work", "view", "w1"])

        assert httpx_mock.get_requests()[-1].headers["Accept"] == media_type

    def test_the_default_is_json_ld(self, httpx_mock):
        httpx_mock.add_response(url=f"{API_URL}/works/w1", json=WORK_GRAPH)

        result = runner.invoke(app, [*BASE, "work", "view", "w1"])

        assert result.exit_code == 0
        assert "Moon handbooks" in result.stdout
        assert httpx_mock.get_requests()[-1].headers["Accept"] == "application/ld+json"


class TestResultSetOutput:
    def context_response(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld",
            json={"@context": CONTEXT},
            is_reusable=True,
            is_optional=True,
        )

    def test_search_as_turtle(self, httpx_mock):
        self.context_response(httpx_mock)
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=20&offset=0",
            json=search_response(2),
        )

        result = runner.invoke(app, [*BASE, "-o", "turtle", "search", "moon"])

        assert result.exit_code == 0
        Graph().parse(data=result.stdout, format="turtle")
        assert "Moon handbooks" in result.stdout

    def test_search_as_ntriples(self, httpx_mock):
        self.context_response(httpx_mock)
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=20&offset=0",
            json=search_response(2),
        )

        result = runner.invoke(app, [*BASE, "-o", "ntriples", "search", "moon"])

        assert result.exit_code == 0
        assert result.stdout.count("<https://dev.bcld.info/works/w") >= 2

    def test_rdf_covers_every_page_with_all(self, httpx_mock):
        self.context_response(httpx_mock)
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=0",
            json=search_response(100, total=101),
        )
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=100&offset=100",
            json={
                "results": [
                    {
                        "uuid": "w100",
                        "uri": "https://dev.bcld.info/works/w100",
                        "data": {
                            **WORK_GRAPH,
                            "@id": "https://dev.bcld.info/works/w100",
                        },
                    }
                ],
                "total": 101,
            },
        )

        result = runner.invoke(app, [*BASE, "-o", "turtle", "search", "moon", "--all"])

        assert result.exit_code == 0
        graph = Graph()
        graph.parse(data=result.stdout, format="turtle")
        subjects = {str(s) for s in graph.subjects()}
        assert "https://dev.bcld.info/works/w100" in subjects, "last page included"

    def test_the_context_is_fetched_once_for_a_whole_result_set(self, httpx_mock):
        self.context_response(httpx_mock)
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=20&offset=0",
            json=search_response(20),
        )

        runner.invoke(app, [*BASE, "-o", "turtle", "search", "moon"])

        context_calls = [
            r for r in httpx_mock.get_requests() if "context.jsonld" in str(r.url)
        ]
        assert len(context_calls) == 1, "one fetch, not one per record"

    def test_profiles_as_turtle(self, httpx_mock):
        """Profiles hold Sinopia templates, not BIBFRAME, so say so plainly."""
        self.context_response(httpx_mock)
        httpx_mock.add_response(
            url=f"{API_URL}/profiles/?limit=20&offset=0",
            json={
                "profiles": [{"uuid": "p1", "uri": "https://x/profiles/p1"}],
                "total": 1,
            },
        )

        result = runner.invoke(app, [*BASE, "-o", "turtle", "profile", "list"])

        assert result.exit_code == 0
        assert "No RDF found" in result.output

    def test_changes_reject_rdf_with_a_reason(self, httpx_mock):
        """Rejected before any request, since no fetching could help."""
        result = runner.invoke(app, [*BASE, "-o", "turtle", "changes", "list"])

        assert result.exit_code == 1
        # The message is wrapped to the terminal, so match either side of it.
        assert "isn't available for activities" in result.output
        assert "BIBFRAME" in result.output
        assert httpx_mock.get_requests() == []

    def test_json_output_is_unaffected(self, httpx_mock):
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=20&offset=0",
            json=search_response(2),
        )

        result = runner.invoke(app, [*BASE, "-o", "json", "search", "moon"])

        assert json.loads(result.stdout)["total"] == 2


class TestLibraryHelper:
    def test_as_rdf_accepts_a_page(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld", json={"@context": CONTEXT}
        )
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=20&offset=0",
            json=search_response(2),
        )

        turtle = client.as_rdf(client.search("moon").first())

        assert "Moon handbooks" in turtle

    def test_as_rdf_accepts_a_single_graph(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld", json={"@context": CONTEXT}
        )

        result = client.as_rdf(WORK_GRAPH, "ntriples")

        assert "Moon handbooks" in result

    def test_context_is_cached_on_the_client(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld", json={"@context": CONTEXT}
        )

        assert client.context() == CONTEXT
        assert client.context() == CONTEXT  # no second request registered

    def test_a_deployment_without_a_context_still_works(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld", status_code=404, json={"detail": "nope"}
        )

        assert client.context() is None


class TestAnonymousRdf:
    def test_rdf_output_needs_no_credentials(self, httpx_mock):
        """Reads are anonymous, and converting is local, so this must too."""
        httpx_mock.add_response(
            url=f"{API_URL}/context.jsonld", json={"@context": CONTEXT}
        )
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=moon&type=all&limit=20&offset=0",
            json=search_response(1),
        )

        result = runner.invoke(app, [*BASE, "-o", "turtle", "search", "moon"])

        assert result.exit_code == 0
        assert [r for r in httpx_mock.get_requests() if "keycloak" in str(r.url)] == []
