"""Discovers document links from an approved seed page (§8.1). No recursion:
one seed page's own links only — never follows a discovered page as a new seed.
"""
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


def discover(source: dict, client: httpx.Client | None = None) -> list[str]:
    """Fetch a seed page and return links matching the source's allow-list."""
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0, follow_redirects=True)
    allowed_domains = set(source.get("allowed_domains", []))
    allowed_extensions = tuple("." + e.lstrip(".") for e in source.get("allowed_extensions", []))

    try:
        resp = client.get(source["url"])
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        links = []
        for tag in soup.find_all("a", href=True):
            absolute = urljoin(source["url"], tag["href"])
            parsed = urlparse(absolute)
            if allowed_domains and parsed.netloc not in allowed_domains:
                continue
            if allowed_extensions and not parsed.path.lower().endswith(allowed_extensions):
                continue
            links.append(absolute)
        return sorted(set(links))
    finally:
        if owns_client:
            client.close()
