"""API and analysis tests. Run with: pytest"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import analysis, routing
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


def test_index_is_installable_and_uses_versioned_assets(client):
    html = client.get("/").get_data(as_text=True)
    assert 'rel="manifest"' in html
    assert "/static/js/main.js?v=" in html
    assert client.get("/manifest.webmanifest").get_json()["display"] == "standalone"
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.mimetype
    assert client.get("/static/icons/icon-192.png").status_code == 200


def test_security_headers(client):
    headers = client.get("/").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_large_responses_are_gzipped(client):
    import gzip
    import json

    response = client.get("/api/map-points", headers={"Accept-Encoding": "gzip"})
    assert response.headers["Content-Encoding"] == "gzip"
    payload = json.loads(gzip.decompress(response.get_data()))
    assert payload["type"] == "FeatureCollection"
    assert len(response.get_data()) < 400_000
    route = client.get(
        "/api/route?from=41.89108,-87.78234&to=41.895,-87.79731", headers={"Accept-Encoding": "gzip"},
    )
    assert route.headers["Content-Encoding"] == "gzip"


def test_healthz(client):
    assert client.get("/healthz").get_json()["status"] == "ok"


def test_junk_dates_are_ignored(client):
    everything = client.get("/api/summary").get_json()["total"]
    assert client.get("/api/summary?start=junk&end=nope").get_json()["total"] == everything


def test_unknown_api_path_returns_json_404(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_reverse_rejects_out_of_range_coordinates(client):
    assert client.get("/api/reverse?lat=nan&lon=-87.79").status_code == 400
    assert client.get("/api/reverse?lat=200&lon=-87.79").status_code == 400


def test_rate_limiter_blocks_bursts():
    from server.app import RateLimiter

    limiter = RateLimiter(limit=3, window=60)
    assert [limiter.allow("1.2.3.4") for _ in range(4)] == [True, True, True, False]
    assert limiter.allow("5.6.7.8")


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


def test_streets_cover_oak_park_and_crime_blocks(client):
    streets = client.get("/api/streets").get_json()
    south, west, north, east = analysis.OAK_PARK_LIMITS
    tol = analysis.LIMITS_TOLERANCE
    for feature in streets["features"]:
        for lon, lat in feature["geometry"]["coordinates"]:
            assert west - tol <= lon <= east + tol and south - tol <= lat <= north + tol

    street_ids = {f["id"] for f in streets["features"]}
    crime_ids = {
        f["id"] for f in client.get("/api/map-points").get_json()["features"]
        if f["geometry"]["type"] == "LineString"
    }
    assert len(street_ids) > 1000
    assert len(crime_ids & street_ids) / len(crime_ids) > 0.95


BEYE_SCHOOL = "41.89108,-87.78234"
HOLMES_SCHOOL = "41.895,-87.79731"
VILLAGE_HALL = "41.87949,-87.77866"
OPRF = "41.89045,-87.78965"


def test_route_gives_two_routes_with_eta_and_directions(client):
    data = client.get(f"/api/route?from={BEYE_SCHOOL}&to={HOLMES_SCHOOL}").get_json()
    routes = data["routes"]
    assert len(routes) == 2
    assert routes[0]["label"] == "Safest route"
    for route in routes:
        assert route["distance_m"] > 500
        assert route["walk_minutes"] == max(1, round(route["distance_m"] / routing.WALK_MPS / 60))
        assert route["bike_minutes"] < route["walk_minutes"]
        assert len(route["geometry"]) >= 2
        assert route["steps"][0]["text"].startswith("Head ")
        assert route["steps"][-1]["text"] == "Arrive at your destination"


def test_routes_stay_inside_oak_park(client):
    south, west, north, east = analysis.OAK_PARK_LIMITS
    tol = analysis.LIMITS_TOLERANCE
    for route in client.get(f"/api/route?from={VILLAGE_HALL}&to={OPRF}").get_json()["routes"]:
        for lat, lon in route["geometry"]:
            assert west - tol <= lon <= east + tol and south - tol <= lat <= north + tol


def test_route_ends_near_requested_points(client):
    routes = client.get(f"/api/route?from={VILLAGE_HALL}&to={OPRF}").get_json()["routes"]
    start = [float(x) for x in VILLAGE_HALL.split(",")]
    end = [float(x) for x in OPRF.split(",")]
    for route in routes:
        assert routing._meters(start[1], start[0], route["geometry"][0][1], route["geometry"][0][0]) < 100
        assert routing._meters(end[1], end[0], route["geometry"][-1][1], route["geometry"][-1][0]) < 100


def test_safest_route_has_least_risk():
    graph = routing.street_graph()
    start = routing.snap(graph, 41.87949, -87.77866)
    end = routing.snap(graph, 41.89045, -87.78965)
    links = routing._virtual_links(graph, start, end)
    direct = routing._search(graph, links, lambda idx, length: length, safety=False)
    safest = routing._search(graph, links, lambda idx, length: routing.edge_cost(graph, idx, length))
    assert routing._exposure(graph, safest) < routing._exposure(graph, direct)


def test_route_danger_follows_the_time_frame():
    everything = routing.street_graph()
    one_year = routing.street_graph("2025-09-02", "2026-09-01")
    assert one_year.edges is everything.edges
    assert one_year.edge_danger != everything.edge_danger


def test_routing_and_map_agree_on_block_danger(client):
    window = "start=2024-09-02&end=2026-09-01"
    blocks = client.get(f"/api/map-points?{window}").get_json()["features"]
    map_danger = {f["id"]: f["properties"]["danger_score"] for f in blocks if f["id"] is not None}
    graph = routing.street_graph("2024-09-02", "2026-09-01")
    for edge, danger in zip(graph.edges, graph.edge_danger):
        assert danger == map_danger.get(edge.segment_id, 0.0)


def test_route_accepts_a_time_frame(client):
    response = client.get(f"/api/route?from={BEYE_SCHOOL}&to={HOLMES_SCHOOL}&start=2025-09-02&end=2026-09-01")
    assert response.status_code == 200
    assert client.get(f"/api/route?from={BEYE_SCHOOL}&to={HOLMES_SCHOOL}&start=junk").status_code == 200


def test_route_rejects_bad_and_far_away_input(client):
    assert client.get("/api/route?from=abc&to=1,2").status_code == 400
    response = client.get(f"/api/route?from=40.0,-80.0&to={OPRF}")
    assert response.status_code == 422
    assert "too far" in response.get_json()["error"]


def test_geocode_requires_a_query(client):
    assert client.get("/api/geocode?q=").status_code == 400


def test_incidents_limit_and_dates(client):
    data = client.get("/api/incidents?start=2022-01-01&end=2022-01-31&limit=10").get_json()
    assert len(data["incidents"]) <= 10
    for inc in data["incidents"]:
        assert "2022-01-01" <= inc["date"] <= "2022-01-31"
