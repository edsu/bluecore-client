"""Syntax highlighting for RDF output.

The rule that matters: highlight when someone is looking, never when the output
is going somewhere else. An escape sequence in a redirected .ttl file would
make it unparseable.
"""

import json

import pytest
from pygments.lexers import get_lexer_by_name
from rdflib import Graph
from typer.testing import CliRunner

from bluecore_client import rdf
from bluecore_client.cli import ui
from bluecore_client.cli.app import app
from bluecore_client.cli.context import Settings
from bluecore_client.formats import Output
from tests.conftest import API_URL, KEYCLOAK_URL

runner = CliRunner()
BASE = ["--api-url", API_URL, "--keycloak-url", KEYCLOAK_URL]

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


class TestLexerNames:
    """Pygments has some sharp aliases in this area."""

    def test_every_configured_lexer_exists(self):
        for output, lexer in ui.LEXERS.items():
            assert get_lexer_by_name(lexer), f"{output} -> {lexer}"

    def test_turtle_is_named_in_full(self):
        """ "ttl" is Tera Term macro in pygments, not Turtle."""
        assert ui.LEXERS["turtle"] == "turtle"
        assert get_lexer_by_name("turtle").name == "Turtle"
        assert get_lexer_by_name("ttl").name != "Turtle"

    def test_ntriples_borrows_the_turtle_lexer(self):
        """There is no N-Triples lexer, and "nt" is NestedText."""
        assert ui.LEXERS["ntriples"] == "turtle"
        assert get_lexer_by_name("nt").name != "Turtle"

    def test_every_rdf_output_has_a_lexer(self):
        for output in Output:
            if output.is_rdf:
                assert str(output) in ui.LEXERS


class TestRedirectedOutputStaysClean:
    """CliRunner captures stdout, so these all run the non-terminal path."""

    def register(self, httpx_mock):
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

    @pytest.mark.parametrize("output", ["turtle", "rdfxml", "ntriples"])
    def test_no_escape_sequences(self, httpx_mock, output):
        self.register(httpx_mock)

        result = runner.invoke(app, [*BASE, "-o", output, "search", "moon"])

        assert result.exit_code == 0
        assert "\x1b" not in result.stdout

    def test_turtle_still_parses(self, httpx_mock):
        self.register(httpx_mock)

        result = runner.invoke(app, [*BASE, "-o", "turtle", "search", "moon"])

        graph = Graph()
        graph.parse(data=result.stdout, format="turtle")
        assert len(graph) > 0

    def test_rdfxml_still_parses(self, httpx_mock):
        self.register(httpx_mock)

        result = runner.invoke(app, [*BASE, "-o", "rdfxml", "search", "moon"])

        graph = Graph()
        graph.parse(data=result.stdout, format="xml")
        assert len(graph) > 0

    def test_json_stays_machine_readable(self, httpx_mock):
        self.register(httpx_mock)

        result = runner.invoke(app, [*BASE, "-o", "json", "search", "moon"])

        assert json.loads(result.stdout)["total"] == 1

    def test_a_single_resource_in_turtle_is_untouched(self, httpx_mock):
        body = "<https://dev.bcld.info/works/w1> a <http://x/Work> .\n"
        httpx_mock.add_response(url=f"{API_URL}/works/w1", text=body)

        result = runner.invoke(app, [*BASE, "-o", "turtle", "work", "view", "w1"])

        assert result.stdout == body


class TestHighlightingOnATerminal:
    def test_emit_code_highlights_when_stdout_is_a_terminal(self, monkeypatch):
        printed = []
        monkeypatch.setattr(ui, "out", _FakeTerminal(printed))

        ui.emit_code("@prefix : <http://example.org/> .", "turtle")

        assert len(printed) == 1
        from rich.syntax import Syntax

        assert isinstance(printed[0], Syntax), "should render through rich"

    def test_emit_code_prints_plainly_otherwise(self, capsys, monkeypatch):
        monkeypatch.setattr(ui, "out", _FakeNonTerminal())

        ui.emit_code("@prefix : <http://example.org/> .", "turtle")

        assert capsys.readouterr().out == "@prefix : <http://example.org/> .\n"

    def test_a_trailing_newline_is_not_doubled(self, capsys, monkeypatch):
        monkeypatch.setattr(ui, "out", _FakeNonTerminal())

        ui.emit_code("one line\n", "turtle")

        assert capsys.readouterr().out == "one line\n"


class TestRdfxmlSerializer:
    def test_rdfxml_uses_the_same_serializer_as_the_api(self):
        """as_rdfxml in bluecore_api serializes with "xml"."""
        assert rdf.SERIALIZERS["rdfxml"] == "xml"

    def test_rdfxml_round_trips_without_warnings(self, recwarn):
        text = rdf.serialize([GRAPH], "rdfxml", context=CONTEXT)

        graph = Graph()
        graph.parse(data=text, format="xml")
        assert len(graph) > 0
        ignored = [w for w in recwarn if "ignored" in str(w.message)]
        assert ignored == [], "pretty-xml warns about dropped assertions; xml does not"


class _FakeTerminal:
    is_terminal = True
    width = 100

    def __init__(self, sink):
        self._sink = sink

    def print(self, renderable, *args, **kwargs):
        self._sink.append(renderable)


class _FakeNonTerminal:
    is_terminal = False
    width = 80

    def print(self, *args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("should have used plain print")
