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
    for feature in data["features"]:
        geometry = feature["geometry"]
        points = geometry["coordinates"] if geometry["type"] == "LineString" else [geometry["coordinates"]]
        for lon, lat in points:
            assert 41.8 < lat < 42.0 and -87.9 < lon < -87.7


def test_map_points_filtered(client):
    data = client.get("/api/map-points?type=Robbery&start=2024-01-01&end=2024-12-31").get_json()
    summary = client.get("/api/summary?type=Robbery&start=2024-01-01&end=2024-12-31").get_json()
    assert sum(f["properties"]["count"] for f in data["features"]) == summary["total"]
    assert summary["by_year"] == [["2024", summary["total"]]]


def test_every_incident_type_has_a_severity_weight():
    types = {t for i in analysis.load_incidents() for t in i.types}
    assert types <= set(analysis.SEVERITY_WEIGHTS)


def test_incident_counts_at_its_most_severe_type():
    inc = analysis.Incident("1", "", "2024-01-01", "", "", "", 0, 0, types={"Robbery", "Larceny/Theft Offenses"})
    assert analysis.incident_severity(inc) == analysis.SEVERITY_WEIGHTS["Robbery"]


def test_danger_level_thresholds():
    assert analysis.danger_level(0) == "low"
    assert analysis.danger_level(4.9) == "low"
    assert analysis.danger_level(5) == "moderate"
    assert analysis.danger_level(15) == "high"


def test_short_windows_are_not_scaled_up():
    incidents = analysis.load_incidents()
    assert analysis.window_years(incidents, "2024-01-01", "2024-01-31") < 1
    assert analysis.window_years(incidents, "bad-date", None) == analysis.window_years(incidents)
    one_month = analysis.aggregate_locations(incidents[:50], years=1 / 12)
    raw_total = sum(analysis.incident_severity(i) for i in incidents[:50])
    assert sum(f["properties"]["danger_score"] for f in one_month["features"]) == pytest.approx(raw_total, abs=0.5)


def test_map_points_carry_danger_levels(client):
    data = client.get("/api/map-points").get_json()
    keys = [level["key"] for level in data["danger_levels"]]
    assert keys == ["low", "moderate", "high"]
    assert {f["properties"]["danger_level"] for f in data["features"]} == set(keys)


def test_street_names_normalize_across_sources():
    assert analysis.street_key("N Oak Park Ave") == analysis.street_key("North Oak Park Avenue")
    assert analysis.street_key("North Ave") == analysis.street_key("West North Avenue")
    assert analysis.street_key("Le Moyne Pkwy") == analysis.street_key("Lemoyne Parkway")
    assert analysis.street_key("East Ave") != analysis.street_key("North Avenue")


def test_blocks_snap_to_their_street():
    segment = analysis.street_segment_for("1100 Block Lake St", 41.88838, -87.80247)
    assert segment is not None and len(segment[1]) >= 2
    assert analysis.street_segment_for("Lake St / N Taylor Ave", 41.8884, -87.7795) is None


def test_most_incidents_draw_as_street_lines(client):
    data = client.get("/api/map-points").get_json()
    on_lines = sum(f["properties"]["count"] for f in data["features"] if f["geometry"]["type"] == "LineString")
    total = sum(f["properties"]["count"] for f in data["features"])
    assert on_lines / total > 0.9


def test_incidents_limit_and_dates(client):
    data = client.get("/api/incidents?start=2022-01-01&end=2022-01-31&limit=10").get_json()
    assert len(data["incidents"]) <= 10
    for inc in data["incidents"]:
        assert "2022-01-01" <= inc["date"] <= "2022-01-31"
