"""API tests. Run with: pytest"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index(client):
    res = client.get("/")
    assert res.status_code == 200


def test_incidents(client):
    res = client.get("/api/incidents?limit=5")
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] > 0
    assert len(data["incidents"]) <= 5


def test_incident_types(client):
    res = client.get("/api/incident-types")
    assert res.status_code == 200
    assert len(res.get_json()) > 0


def test_date_filter(client):
    res = client.get("/api/incidents?start=2022-01-01&end=2022-01-31&limit=10")
    assert res.status_code == 200
    for inc in res.get_json()["incidents"]:
        assert "2022-01-01" <= inc["date"] <= "2022-01-31"
