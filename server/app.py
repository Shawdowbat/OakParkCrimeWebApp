"""Flask backend for the Oak Park Crime web app.

Serves the front end from templates/static and exposes a JSON API over the
crime incident analysis in server/analysis.py.

All data endpoints accept the same filter query params:
  type          - incident_type, e.g. "Robbery"
  crime_against - "Person", "Property" or "Society"
  start, end    - inclusive date range, YYYY-MM-DD
"""

import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from server import analysis

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)


def filtered_incidents():
    return analysis.filter_incidents(
        analysis.load_incidents(),
        incident_type=request.args.get("type"),
        crime_against=request.args.get("crime_against"),
        start=request.args.get("start"),
        end=request.args.get("end"),
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/options")
def options():
    """Incident types, categories and the date span, for the filter controls."""
    return jsonify(analysis.filter_options(analysis.load_incidents()))


@app.route("/api/map-points")
def map_points():
    """GeoJSON with one point per block, carrying its incident count."""
    return jsonify(analysis.aggregate_locations(filtered_incidents()))


@app.route("/api/summary")
def summary():
    """Totals and breakdowns by type, category, zone and year."""
    return jsonify(analysis.summarize(filtered_incidents()))


@app.route("/api/incidents")
def incidents():
    """Individual incidents, newest first. Extra param: limit (default 500)."""
    rows = filtered_incidents()
    limit = request.args.get("limit", default=500, type=int)
    return jsonify({
        "count": len(rows),
        "incidents": [i.to_dict() for i in reversed(rows[-limit:])] if limit > 0 else [],
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
