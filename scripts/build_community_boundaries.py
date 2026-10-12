"""One-off: build data/reference/community_boundaries.parquet, the place
boundaries the curation step uses to say which community a crash is in.

Source: US Census Bureau TIGER/Line place boundaries for Maryland -
incorporated cities and towns plus census-designated places (Silver Spring,
Bethesda, Germantown...). Public domain, and the same definition of each
place the Census publishes population for.

The output is committed, not downloaded at refresh time: boundaries change at
most once a year, and a weekly refresh should not fail because census.gov is
slow. Rerun this when a new TIGER vintage matters, then rebuild the curated
tables.

It is stored as ring vertices rather than geometries so curation can test
points against it in plain SQL, with no spatial extension to install on the
refresh runner. This script is the only place that needs one.

Usage:
    python scripts/build_community_boundaries.py
"""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mocolens.processing.transforms.vision_zero import (  # noqa: E402
    BOUNDARIES_PATH, LAT_MAX, LAT_MIN, LON_MAX, LON_MIN,
)

VINTAGE = 2024
SOURCE_URL = f"https://www2.census.gov/geo/tiger/TIGER{VINTAGE}/PLACE/tl_{VINTAGE}_24_place.zip"


def main() -> None:
    con = duckdb.connect(":memory:")
    con.execute("INSTALL spatial")
    con.execute("LOAD spatial")

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "places.zip"
        print(f"Downloading {SOURCE_URL}")
        urllib.request.urlretrieve(SOURCE_URL, archive)
        # Every Maryland place that reaches into the bounding box curation
        # already uses for "a plausible Montgomery County coordinate". That
        # keeps a few neighbours along the county line, which is correct: a
        # crash geocoded just across it is labelled with where it actually is.
        places = con.execute(f"""
            SELECT NAME, NAMELSAD, ST_AsGeoJSON(geom)
            FROM ST_Read('/vsizip/{archive.as_posix()}/tl_{VINTAGE}_24_place.shp')
            WHERE ST_Intersects(geom, ST_MakeEnvelope({LON_MIN}, {LAT_MIN}, {LON_MAX}, {LAT_MAX}))
            ORDER BY NAME
        """).fetchall()

    rows = []
    ring_id = 0
    for name, full_name, geojson in places:
        geometry = json.loads(geojson)
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        kind = full_name.removeprefix(name).strip()  # "city", "town", "village", "CDP"
        for polygon in polygons:
            # Outer ring and holes alike: the even-odd test curation runs
            # treats a hole as "outside" without being told which is which.
            for ring in polygon:
                ring_id += 1
                rows += [(name, kind, ring_id, seq, lon, lat) for seq, (lon, lat) in enumerate(ring)]

    con.execute("CREATE TABLE vertices (community VARCHAR, kind VARCHAR, ring INTEGER, seq INTEGER, lon DOUBLE, lat DOUBLE)")
    con.executemany("INSERT INTO vertices VALUES (?, ?, ?, ?, ?, ?)", rows)
    BOUNDARIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM vertices ORDER BY ring, seq) TO '{BOUNDARIES_PATH.as_posix()}' (FORMAT PARQUET)")
    print(f"{len(places)} places, {ring_id} rings, {len(rows):,} vertices -> {BOUNDARIES_PATH} "
          f"({BOUNDARIES_PATH.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
