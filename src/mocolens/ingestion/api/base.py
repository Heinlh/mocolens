"""Interface every structured-API extractor implements.

One implementation exists today (Socrata, see socrata.py). This Protocol
exists because §22 of the architecture doc plans for more API types
(ArcGIS, CKAN, custom) to be added per-domain later without touching the
runner.
"""
from typing import Protocol


class ApiFetcher(Protocol):
    def __call__(self, source: dict) -> list[dict]:
        """Fetch and return every record for one source config entry."""
        ...
