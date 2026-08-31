"""Smoke tests for the extract layer: manifest change-detection and Socrata paging.

No network — httpx.MockTransport stands in for the real API.
"""
import httpx

from mocolens.ingestion.api import socrata
from mocolens.ingestion.documents import manifest


def test_manifest_change_detection():
    existing = {"http_etag": "abc", "content_hash": "old"}

    # same etag -> unchanged
    assert not manifest.has_changed(existing, etag="abc", last_modified=None, new_hash="whatever")
    # no etag/last-modified match, hash changed -> changed
    assert manifest.has_changed(existing, etag=None, last_modified=None, new_hash="new")
    # no manifest record at all -> always new
    assert manifest.has_changed(None, etag=None, last_modified=None, new_hash="new")


def test_manifest_roundtrip(tmp_path):
    path = tmp_path / "manifest.jsonl"
    records = {"id1": {"document_id": "id1", "source_url": "https://x/1.pdf"}}
    manifest.save(path, records)
    assert manifest.load(path) == records


def test_socrata_pagination():
    page1 = [{"id": i} for i in range(socrata.PAGE_SIZE)]
    page2 = [{"id": socrata.PAGE_SIZE}]
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["$offset"])
        calls.append(offset)
        return httpx.Response(200, json=page1 if offset == 0 else page2)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    records = socrata.fetch_all({"url": "https://example.test/resource/abcd.json"}, client=client)

    assert len(records) == socrata.PAGE_SIZE + 1
    assert calls == [0, socrata.PAGE_SIZE]
