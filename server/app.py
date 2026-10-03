"""Flask backend for the Oak Park Crime web app.

Serves the front end from templates/static and exposes a small JSON API
over the crime incident CSV in data/.
"""

import csv
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "crime-incidents-oak-park.csv"

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

_incidents_cache = None


def load_incidents():
    """Load and cache incidents from the CSV."""
    global _incidents_cache
    if _incidents_cache is None:
        with open(DATA_FILE, newline="", encoding="utf-8") as f:
            _incidents_cache = list(csv.DictReader(f))
    return _incidents_cache


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/incidents")
def incidents():
    """List incidents, filterable by type and date range.

    Query params:
      type  - filter by incident_type (exact match)
      start - earliest date, YYYY-MM-DD
      end   - latest date, YYYY-MM-DD
      limit - max rows to return (default 500)
    """
    rows = load_incidents()

    incident_type = request.args.get("type")
    if incident_type:
        rows = [r for r in rows if r["incident_type"] == incident_type]

    start = request.args.get("start")
    if start:
        rows = [r for r in rows if r["date"] >= start]

    end = request.args.get("end")
    if end:
        rows = [r for r in rows if r["date"] <= end]

    limit = request.args.get("limit", default=500, type=int)
    return jsonify({"count": len(rows), "incidents": rows[:limit]})


@app.route("/api/incident-types")
def incident_types():
    """Distinct incident types, for populating filter dropdowns."""
    types = sorted({r["incident_type"] for r in load_incidents()})
    return jsonify(types)


@app.route("/api/stats")
def stats():
    """Incident counts grouped by type."""
    counts = {}
    for r in load_incidents():
        counts[r["incident_type"]] = counts.get(r["incident_type"], 0) + 1
    return jsonify(counts)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
