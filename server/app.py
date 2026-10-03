"""Flask backend for Oak Park Safe Routes.

Serves the front end from templates/static and exposes a JSON API over the
crime incident analysis in server/analysis.py and the route planner in
server/routing.py.

The data endpoints accept the same filter query params:
  type          - incident_type, e.g. "Robbery"
  crime_against - "Person", "Property" or "Society"
  start, end    - inclusive date range, YYYY-MM-DD

Run locally with `python server/app.py`; in production run `wsgi:app` under
waitress (see README). Settings come from environment variables:
  PORT              - port to listen on (default 5000)
  FLASK_DEBUG       - "1" for auto-reload during development
  TRUST_PROXY_HOPS  - number of reverse proxies in front of the app (e.g. 1 on
                      Render/Railway/Fly), so rate limits see real client IPs
"""

import gzip
import os
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import date
from functools import lru_cache
from pathlib import Path

from flask import Flask, Response, json, jsonify, render_template, request, send_from_directory, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from server import analysis, geocode, routing

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
# Static URLs carry a version (see asset_url), so browsers may cache them for a year.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31_536_000
app.json.ensure_ascii = False

proxy_hops = int(os.environ.get("TRUST_PROXY_HOPS", "0"))
if proxy_hops:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxy_hops, x_proto=proxy_hops, x_host=proxy_hops)

DATA_MAX_AGE = 600  # seconds browsers may reuse data responses; the data only changes on deploy
GZIP_MIN_BYTES = 1024

# Map tiles, Leaflet from unpkg, and nothing else. Leaflet sets inline styles,
# hence 'unsafe-inline' for styles only.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://unpkg.com",
    "style-src 'self' 'unsafe-inline' https://unpkg.com",
    "img-src 'self' data: https://*.basemaps.cartocdn.com https://basemaps.cartocdn.com "
    "https://tile.openstreetmap.org https://server.arcgisonline.com https://unpkg.com",
    "connect-src 'self'",
    "manifest-src 'self'",
    "worker-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


# --- Helpers ----------------------------------------------------------------

def _iso_date(value):
    try:
        return date.fromisoformat(value).isoformat() if value else None
    except ValueError:
        return None


def _filters():
    """The filter params, normalized so junk values are ignored."""
    return (
        request.args.get("type") or None,
        request.args.get("crime_against") or None,
        _iso_date(request.args.get("start")),
        _iso_date(request.args.get("end")),
    )


def _filtered(incident_type, crime_against, start, end):
    return analysis.filter_incidents(
        analysis.load_incidents(), incident_type=incident_type, crime_against=crime_against, start=start, end=end,
    )


def _gzip_json(payload):
    return gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"), compresslevel=6)


def _cached_json_response(gzipped):
    """Serve pre-gzipped JSON, decompressing for the rare client without gzip."""
    if "gzip" in request.headers.get("Accept-Encoding", ""):
        response = Response(gzipped, mimetype="application/json")
        response.headers["Content-Encoding"] = "gzip"
    else:
        response = Response(gzip.decompress(gzipped), mimetype="application/json")
    response.headers["Vary"] = "Accept-Encoding"
    response.cache_control.public = True
    response.cache_control.max_age = DATA_MAX_AGE
    return response


def _coordinate_pair(value):
    try:
        lat, lon = (float(part) for part in value.split(","))
    except (AttributeError, ValueError):
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def _error(message, status):
    return jsonify({"error": message}), status


class RateLimiter:
    """At most `limit` requests per client IP in any `window` seconds."""

    def __init__(self, limit, window=60):
        self.limit = limit
        self.window = window
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key):
        now = time.monotonic()
        with self.lock:
            hits = self.hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self.hits) > 10_000:
                self.hits = defaultdict(deque, {k: v for k, v in self.hits.items() if v})
            return True


# Address lookups go to a shared public service, so they're limited hardest.
geocode_limit = RateLimiter(limit=30)
route_limit = RateLimiter(limit=60)


def _rate_limited(limiter):
    if limiter.allow(request.remote_addr or "unknown"):
        return None
    return _error("Too many requests. Please wait a minute and try again.", 429)


@app.context_processor
def asset_helpers():
    def asset_url(filename):
        """A static URL that changes whenever the file does, so it can be cached forever."""
        try:
            version = int((Path(app.static_folder) / filename).stat().st_mtime)
        except OSError:
            version = 0
        return url_for("static", filename=filename, v=version)
    return {"asset_url": asset_url}


@app.after_request
def finish_response(response):
    headers = response.headers
    headers.setdefault("X-Content-Type-Options", "nosniff")
    # OpenStreetMap and CARTO tile servers require a referrer; send the origin only.
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
    headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    if request.is_secure:
        headers.setdefault("Strict-Transport-Security", "max-age=31536000")

    compressible = response.mimetype in ("application/json", "text/html", "application/javascript", "text/css")
    if (
        compressible
        and not response.direct_passthrough
        and "Content-Encoding" not in headers
        and "gzip" in request.headers.get("Accept-Encoding", "")
        and response.status_code < 300
    ):
        body = response.get_data()
        if len(body) >= GZIP_MIN_BYTES:
            response.set_data(gzip.compress(body, compresslevel=6))
            headers["Content-Encoding"] = "gzip"
            headers.add("Vary", "Accept-Encoding")
    return response


@app.errorhandler(404)
def not_found(err):
    if request.path.startswith("/api/"):
        return _error("Not found.", 404)
    return err


@app.errorhandler(500)
def server_error(err):
    if request.path.startswith("/api/"):
        return _error("Something went wrong on our end. Please try again.", 500)
    return err


# --- Pages ------------------------------------------------------------------

@app.route("/")
def index():
    response = Response(render_template("index.html"))
    response.cache_control.no_cache = True
    return response


@app.route("/sw.js")
def service_worker():
    """Served from the root so the worker's scope covers the whole site."""
    response = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript", max_age=0)
    response.cache_control.no_cache = True
    return response


@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(app.static_folder, "manifest.webmanifest",
                               mimetype="application/manifest+json", max_age=86400)


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "incidents": len(analysis.load_incidents())})


# --- Data API -----------------------------------------------------------------

@lru_cache(maxsize=1)
def _options_gz():
    return _gzip_json(analysis.filter_options(analysis.load_incidents()))


@app.route("/api/options")
def options():
    """Incident types, categories and the date span, for the filter controls."""
    return _cached_json_response(_options_gz())


# Gzipped bytes are ~10x smaller than the payloads, so many filter
# combinations fit in memory.
@lru_cache(maxsize=128)
def _map_points_gz(incident_type, crime_against, start, end):
    years = analysis.window_years(analysis.load_incidents(), start=start, end=end)
    return _gzip_json(analysis.aggregate_locations(_filtered(incident_type, crime_against, start, end), years=years))


@app.route("/api/map-points")
def map_points():
    """GeoJSON with one feature per block, carrying its incident count and danger level."""
    return _cached_json_response(_map_points_gz(*_filters()))


@lru_cache(maxsize=1)
def _streets_gz():
    return _gzip_json(analysis.oak_park_streets())


@app.route("/api/streets")
def streets():
    """Every street block in Oak Park, drawn as the crime-free base layer."""
    response = _cached_json_response(_streets_gz())
    response.cache_control.max_age = 86400
    return response


@lru_cache(maxsize=128)
def _summary_gz(incident_type, crime_against, start, end):
    return _gzip_json(analysis.summarize(_filtered(incident_type, crime_against, start, end)))


@app.route("/api/summary")
def summary():
    """Totals and breakdowns by type, category, zone and year."""
    return _cached_json_response(_summary_gz(*_filters()))


@app.route("/api/incidents")
def incidents():
    """Individual incidents, newest first. Extra param: limit (default 500, max 5000)."""
    rows = _filtered(*_filters())
    limit = min(request.args.get("limit", default=500, type=int), 5000)
    return jsonify({
        "count": len(rows),
        "incidents": [i.to_dict() for i in reversed(rows[-limit:])] if limit > 0 else [],
    })


# --- Routing and address lookup -------------------------------------------------

@app.route("/api/route")
def route():
    """Up to two safe walking routes. Params: from, to as "lat,lon"; optional
    start, end (YYYY-MM-DD) limit which incidents count toward safety."""
    limited = _rate_limited(route_limit)
    if limited:
        return limited
    start = _coordinate_pair(request.args.get("from"))
    end = _coordinate_pair(request.args.get("to"))
    if not start or not end:
        return _error('Give "from" and "to" as "lat,lon".', 400)
    try:
        routes = routing.plan_routes(
            *start, *end,
            start_date=_iso_date(request.args.get("start")),
            end_date=_iso_date(request.args.get("end")),
        )
    except routing.RouteError as err:
        return _error(str(err), 422)
    return jsonify({"routes": routes})


@app.route("/api/geocode")
def geocode_search():
    """Places in Oak Park matching the "q" param."""
    query = (request.args.get("q") or "").strip()
    if not query:
        return _error("Enter an address or place.", 400)
    limited = _rate_limited(geocode_limit)
    if limited:
        return limited
    try:
        return jsonify({"results": list(geocode.search(query[:200]))})
    except geocode.GeocodeError as err:
        return _error(str(err), 502)


@app.route("/api/reverse")
def geocode_reverse():
    """A short address for the "lat" and "lon" params."""
    point = _coordinate_pair(f"{request.args.get('lat')},{request.args.get('lon')}")
    if not point:
        return _error("Give lat and lon.", 400)
    limited = _rate_limited(geocode_limit)
    if limited:
        return limited
    try:
        return jsonify({"label": geocode.reverse(round(point[0], 5), round(point[1], 5))})
    except geocode.GeocodeError as err:
        return _error(str(err), 502)


def warm_caches():
    """Load data and build the default views up front so the first visitor isn't slow."""
    analysis.load_incidents()
    routing.street_graph()
    _options_gz()
    _streets_gz()


if __name__ == "__main__":
    # Development server. Listens on all interfaces so phones on the same
    # Wi-Fi can connect; the interactive debugger stays off because it allows
    # remote code execution.
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
        use_debugger=False,
    )
