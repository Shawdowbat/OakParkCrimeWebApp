"""Address lookup through OpenStreetMap's Nominatim service, limited to Oak Park.

Nominatim's usage policy asks for an identifying User-Agent, at most one
request per second, and caching of repeat lookups; all three are done here.
"""

import json
import threading
import time
import urllib.parse
import urllib.request
from functools import lru_cache

from server import analysis

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
USER_AGENT = "OakParkCrimeMap/1.0 (safe-route planner)"
MARGIN = 0.004  # degrees, so places on the boundary streets are found

_lock = threading.Lock()
_last_request = 0.0


class GeocodeError(RuntimeError):
    pass


def _get(path, params):
    global _last_request
    url = f"{NOMINATIM_URL}/{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _lock:
        wait = 1.0 - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)
        except (OSError, ValueError) as err:
            raise GeocodeError("The address lookup service is unavailable right now.") from err
        finally:
            _last_request = time.monotonic()


def _label(result, address_only=False):
    address = result.get("address", {})
    road = address.get("road")
    street = " ".join(p for p in (address.get("house_number"), road) if p) if road else ""
    name = None if address_only else result.get("name")
    if name and street and name != road:
        return f"{name}, {street}"
    return name or street or ", ".join(result.get("display_name", "").split(", ")[:2])


@lru_cache(maxsize=512)
def search(query):
    """Up to five places in Oak Park matching the query."""
    south, west, north, east = analysis.OAK_PARK_LIMITS
    results = _get("search", {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 5,
        "countrycodes": "us",
        "viewbox": f"{west - MARGIN},{north + MARGIN},{east + MARGIN},{south - MARGIN}",
        "bounded": 1,
    })
    return tuple(
        {"label": _label(r), "lat": float(r["lat"]), "lon": float(r["lon"])}
        for r in results
    )


@lru_cache(maxsize=512)
def reverse(lat, lon):
    """A short street address for a point, or None."""
    result = _get("reverse", {"lat": lat, "lon": lon, "format": "jsonv2", "addressdetails": 1, "zoom": 18})
    if not result or "error" in result:
        return None
    return _label(result, address_only=True)
