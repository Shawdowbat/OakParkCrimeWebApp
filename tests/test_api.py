"""API and analysis tests. Run with: pytest"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import analysis
from server.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_charges_collapse_into_incidents():
    incidents = analysis.load_incidents()
    ids = [i.incident_id for i in incidents]
    assert len(ids) == len(set(ids))
    assert any(len(i.offenses) > 1 for i in incidents)


def test_location_counts_add_up():
    incidents = analysis.load_incidents()
    geojson = analysis.aggregate_locations(incidents)
    assert sum(f["properties"]["count"] for f in geojson["features"]) == len(incidents)
    counts = [f["properties"]["count"] for f in geojson["features"]]
    assert counts == sorted(counts, reverse=True)


def test_index(client):
    assert client.get("/").status_code == 200


def test_options(client):
    data = client.get("/api/options").get_json()
    assert "Robbery" in data["types"]
    assert data["min_date"] <= data["max_date"]


def test_map_points_geojson(client):
    data = client.get("/api/map-points").get_json()
    assert data["type"] == "FeatureCollection"
    lon, lat = data["features"][0]["geometry"]["coordinates"]
    assert 41.8 < lat < 42.0 and -87.9 < lon < -87.7


def test_map_points_filtered(client):
    data = client.get("/api/map-points?type=Robbery&start=2024-01-01&end=2024-12-31").get_json()
    summary = client.get("/api/summary?type=Robbery&start=2024-01-01&end=2024-12-31").get_json()
    assert sum(f["properties"]["count"] for f in data["features"]) == summary["total"]
    assert summary["by_year"] == [["2024", summary["total"]]]


def test_incidents_limit_and_dates(client):
    data = client.get("/api/incidents?start=2022-01-01&end=2022-01-31&limit=10").get_json()
    assert len(data["incidents"]) <= 10
    for inc in data["incidents"]:
        assert "2022-01-01" <= inc["date"] <= "2022-01-31"
