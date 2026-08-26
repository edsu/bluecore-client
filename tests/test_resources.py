"""The endpoint groups, and the content negotiation they rely on."""

import json

import pytest

from bluecore_client.errors import BluecoreError
from tests.conftest import API_URL

WORK_GRAPH = {
    "@context": {"@vocab": "http://id.loc.gov/ontologies/bibframe/"},
    "@id": "https://bcld.info/works/w1",
    "@type": ["Work", "Text"],
    "title": [{"@type": "Title", "mainTitle": "Le mal joli"}],
}


class TestFormats:
    """Format selection matters more than it looks: without an explicit
    Accept header the API falls through negotiation and returns an HTML page.
    """

    def test_json_ld_is_the_default(self, httpx_mock, client):
        httpx_mock.add_response(url=f"{API_URL}/works/w1", json=WORK_GRAPH)

        work = client.works.get("w1")

        assert work["@id"] == "https://bcld.info/works/w1"
        assert httpx_mock.get_requests()[-1].headers["Accept"] == "application/ld+json"

    def test_a_get_always_asks_for_something_specific(self, httpx_mock, client):
        httpx_mock.add_response(url=f"{API_URL}/works/w1", json=WORK_GRAPH)

        client.works.get("w1")

        accept = httpx_mock.get_requests()[-1].headers["Accept"]
        assert accept != "*/*", "a wildcard Accept gets an HTML page back"

    def test_turtle_comes_back_as_text(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/works/w1",
            text="<https://bcld.info/works/w1> a bf:Work .",
        )

        result = client.works.get("w1", format="ttl")

        assert isinstance(result, str)
        assert httpx_mock.get_requests()[-1].headers["Accept"] == "text/turtle"

    @pytest.mark.parametrize(
        "key,media_type",
        [
            ("jsonld", "application/ld+json"),
            ("json", "application/json"),
            ("ttl", "text/turtle"),
            ("rdf", "application/rdf+xml"),
            ("nt", "application/n-triples"),
            ("cbd.jsonld", "application/cbd+jsonld"),
            ("cbd.xml", "application/cbd+xml"),
            ("vnd.sinopia.json", "application/vnd.sinopia+json"),
        ],
    )
    def test_every_format_the_api_registers_is_reachable(
        self, httpx_mock, client, key, media_type
    ):
        httpx_mock.add_response(url=f"{API_URL}/works/w1", json={}, text=None)

        client.works.get("w1", format=key)

        assert httpx_mock.get_requests()[-1].headers["Accept"] == media_type

    def test_an_unknown_format_lists_the_real_ones(self, client):
        with pytest.raises(BluecoreError, match="Unknown format 'yaml'"):
            client.works.get("w1", format="yaml")


class TestWorks:
    def test_get(self, httpx_mock, client):
        httpx_mock.add_response(url=f"{API_URL}/works/w1", json=WORK_GRAPH)

        assert client.works.get("w1") == WORK_GRAPH

    def test_get_can_expand_the_graph(self, httpx_mock, client):
        httpx_mock.add_response(url=f"{API_URL}/works/w1?expand=true", json=WORK_GRAPH)

        client.works.get("w1", expand=True)

        assert "expand=true" in str(httpx_mock.get_requests()[-1].url)

    def test_create_sends_the_graph_as_raw_json_ld(self, httpx_mock, client):
        """The API unwraps an application/ld+json body itself, so the caller
        passes the graph rather than a string-in-an-envelope.
        """
        httpx_mock.add_response(
            url=f"{API_URL}/works/", method="POST", status_code=201, json={"uuid": "w1"}
        )

        client.works.create(WORK_GRAPH)

        request = httpx_mock.get_requests()[-1]
        assert request.headers["Content-Type"] == "application/ld+json"
        assert json.loads(request.read()) == WORK_GRAPH

    def test_update_puts(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/works/w1", method="PUT", json={"uuid": "w1"}
        )

        client.works.update("w1", WORK_GRAPH)

        assert httpx_mock.get_requests()[-1].method == "PUT"

    def test_delete(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/works/w1", method="DELETE", status_code=204
        )

        assert client.works.delete("w1") is None

    def test_embeddings(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/works/w1/embeddings", json={"embedding": [0.1, 0.2]}
        )

        assert client.works.embedding("w1") == {"embedding": [0.1, 0.2]}

    def test_get_accepts_a_blue_core_uri(self, httpx_mock, client):
        """So a URI found in the data can be followed without picking it apart."""
        httpx_mock.add_response(url=f"{API_URL}/works/w1", json=WORK_GRAPH)

        work = client.works.get("https://dev.bcld.info/works/w1")

        assert work == WORK_GRAPH

    def test_get_rejects_a_uri_for_a_different_type(self, client):
        from bluecore_client.errors import BluecoreError

        with pytest.raises(BluecoreError, match="points at instances, not works"):
            client.works.get("https://bcld.info/instances/i1")

    def test_there_is_no_list_because_the_api_has_no_collection_endpoint(self, client):
        """If bluecore_api gains GET /works/, add list() here."""
        assert not hasattr(client.works, "list")


class TestInstances:
    def test_cbd_is_available_here_only(self, httpx_mock, client):
        """bluecore_api returns 400 for a CBD of anything but an Instance."""
        httpx_mock.add_response(url=f"{API_URL}/instances/i1", json={"@id": "i1"})

        client.instances.cbd("i1")

        assert (
            httpx_mock.get_requests()[-1].headers["Accept"] == "application/cbd+jsonld"
        )
        assert not hasattr(client.works, "cbd")
        assert not hasattr(client.hubs, "cbd")

    def test_cbd_as_xml(self, httpx_mock, client):
        httpx_mock.add_response(url=f"{API_URL}/instances/i1", text="<rdf:RDF/>")

        result = client.instances.cbd("i1", xml=True)

        assert isinstance(result, str)


class TestProfiles:
    def test_create_wraps_data_as_a_json_string(self, httpx_mock, client):
        """Unlike the BIBFRAME routes, the profiles API wants data as a string."""
        httpx_mock.add_response(
            url=f"{API_URL}/profiles/", method="POST", status_code=201, json={}
        )

        client.profiles.create({"resourceTemplates": []})

        body = json.loads(httpx_mock.get_requests()[-1].read())
        assert body["data"] == '{"resourceTemplates": []}'

    def test_create_accepts_a_string_unchanged(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/profiles/", method="POST", status_code=201, json={}
        )

        client.profiles.create('{"already": "encoded"}')

        body = json.loads(httpx_mock.get_requests()[-1].read())
        assert body["data"] == '{"already": "encoded"}'

    def test_find_by_uri(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/profiles/?uri=https%3A%2F%2Fbcld.info%2Fprofiles%2Fp1",
            json={"uri": "https://bcld.info/profiles/p1"},
        )

        found = client.profiles.find("https://bcld.info/profiles/p1")

        assert found["uri"] == "https://bcld.info/profiles/p1"

    def test_search_uses_the_endpoint_that_carries_data(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/search/profile?limit=10&offset=0",
            json={"results": [{"uri": "p1", "data": {}}], "total": 1},
        )

        assert [p["uri"] for p in client.profiles.search()] == ["p1"]


class TestSearch:
    def test_search_is_callable_and_paged(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=emma&type=all&limit=20&offset=0",
            json={"results": [{"uri": "w1"}], "total": 1},
        )

        assert [r["uri"] for r in client.search("emma")] == ["w1"]

    def test_search_type_narrows_the_results(self, httpx_mock, client):
        from bluecore_client import SearchType

        httpx_mock.add_response(
            url=f"{API_URL}/search/?q=emma&type=works&limit=20&offset=0",
            json={"results": [], "total": 0},
        )

        list(client.search("emma", type=SearchType.WORKS))

        assert "type=works" in str(httpx_mock.get_requests()[-1].url)

    def test_a_limit_over_the_apis_cap_fails_before_the_request(self, client):
        with pytest.raises(ValueError, match="100 or less"):
            client.search("emma", limit=500)


class TestBatches:
    def test_from_url(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/batches/",
            method="POST",
            json={"uri": "https://example.org/x.jsonld", "workflow_id": "abc"},
        )

        result = client.batches.from_url("https://example.org/x.jsonld")

        assert result["workflow_id"] == "abc"
        assert json.loads(httpx_mock.get_requests()[-1].read()) == {
            "uri": "https://example.org/x.jsonld"
        }

    def test_upload_sends_multipart(self, httpx_mock, client, tmp_path):
        upload = tmp_path / "batch.jsonld"
        upload.write_text('{"@id": "x"}')
        httpx_mock.add_response(
            url=f"{API_URL}/batches/upload/", method="POST", json={"workflow_id": "abc"}
        )

        client.batches.upload(upload)

        request = httpx_mock.get_requests()[-1]
        assert request.headers["Content-Type"].startswith("multipart/form-data")
        assert b"batch.jsonld" in request.read()


class TestChangeDocuments:
    def test_feed(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/feed", json={"totalItems": 3}
        )

        assert client.changes.feed("works")["totalItems"] == 3

    def test_walking_pages_stops_at_the_end_of_the_feed(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/1",
            json={"orderedItems": [{"id": "a"}, {"id": "b"}]},
        )
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/2",
            json={"orderedItems": [{"id": "c"}]},
        )
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/works/page/3",
            status_code=404,
            json={"detail": "not found"},
        )

        activities = list(client.changes.activities("works"))

        assert [a["id"] for a in activities] == ["a", "b", "c"]

    def test_an_empty_page_also_ends_the_walk(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/instances/page/1",
            json={"orderedItems": []},
        )

        assert list(client.changes.activities("instances")) == []

    @pytest.mark.parametrize(
        "kind", ["work", "works", "Works", "instance", "instances"]
    )
    def test_feed_names_are_forgiving(self, httpx_mock, client, kind):
        normalized = "works" if kind.lower().startswith("work") else "instances"
        httpx_mock.add_response(
            url=f"{API_URL}/change_documents/{normalized}/feed", json={}
        )

        client.changes.feed(kind)

    def test_an_unknown_feed_name_says_what_is_valid(self, client):
        with pytest.raises(ValueError, match="Choose 'works' or 'instances'"):
            client.changes.feed("hubs")


class TestExportAndConvert:
    def test_export_is_callable(self, httpx_mock, client):
        httpx_mock.add_response(
            url=f"{API_URL}/export/", method="POST", json={"workflow_id": "abc"}
        )

        result = client.export("https://bcld.info/instances/i1", "a123")

        assert result["workflow_id"] == "abc"
        assert json.loads(httpx_mock.get_requests()[-1].read()) == {
            "instance_uri": "https://bcld.info/instances/i1",
            "local_id": "a123",
        }

    def test_marc_to_bibframe_posts_raw_marc(self, httpx_mock, client, tmp_path):
        marc = tmp_path / "record.mrc"
        marc.write_bytes(b"00123nam")
        httpx_mock.add_response(
            url=f"{API_URL}/marc2bibframe", method="POST", json={"@id": "x"}
        )

        client.convert.marc_to_bibframe(marc)

        request = httpx_mock.get_requests()[-1]
        assert request.headers["Content-Type"] == "application/marc"
        assert request.read() == b"00123nam"

    def test_marc_to_xml_returns_text(self, httpx_mock, client, tmp_path):
        marc = tmp_path / "record.mrc"
        marc.write_bytes(b"00123nam")
        httpx_mock.add_response(
            url=f"{API_URL}/marc2xml", method="POST", text="<record/>"
        )

        assert client.convert.marc_to_xml(marc) == "<record/>"
