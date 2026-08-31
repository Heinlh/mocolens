"""Fetches full datasets from Socrata (Montgomery County's open-data platform)."""
import httpx

PAGE_SIZE = 5000


def fetch_all(source: dict, client: httpx.Client | None = None) -> list[dict]:
    """Page through a Socrata dataset via $limit/$offset and return all records."""
    url = source["url"].rstrip("/")
    if not url.endswith(".json"):
        url += ".json"

    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)
    records: list[dict] = []
    try:
        offset = 0
        while True:
            resp = client.get(url, params={"$limit": PAGE_SIZE, "$offset": offset})
            resp.raise_for_status()
            page = resp.json()
            records.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
    finally:
        if owns_client:
            client.close()
    return records
