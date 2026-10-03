"""Analysis of the Oak Park crime incident CSV.

The CSV has one row per *charge*, so an incident with several charges appears
on several rows. Everything here works on de-duplicated incidents.

Coordinates are recorded at block level ("800 Block N Cuyler Ave"), so many
incidents share the exact same point. The map therefore aggregates incidents
per block, drawn as that block's stretch of street where one can be matched
in the OpenStreetMap data and as a point otherwise (intersections such as
"Lake St / N Taylor Ave", and streets OSM doesn't have).
"""

import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "crime-incidents-oak-park.csv"
# Street blocks from OpenStreetMap, built by scripts/build_street_segments.py.
STREETS_FILE = DATA_FILE.parent / "street_segments.geojson"
# A block's point must lie this close to a same-named street to be drawn on it.
MAX_SNAP_METERS = 60
# Village limits as (south, west, north, east): Roosevelt Rd, Harlem Ave,
# North Ave and Austin Blvd. The street file extends past them.
OAK_PARK_LIMITS = (41.86532, -87.80498, 41.90912, -87.77494)
LIMITS_TOLERANCE = 0.0003  # about 30 m, so the boundary streets themselves count

# How dangerous each incident type is to be around, from 1 (minor, no threat
# to bystanders) to 25 (gravest). The scale is steep on purpose so a single
# violent crime outweighs a run of petty thefts. An incident with several
# types counts at its most severe type.
SEVERITY_WEIGHTS = {
    "Homicide Offenses": 25,
    "Kidnapping/Abduction": 20,
    "Sex Offenses": 20,
    "Robbery": 12,
    "Weapon Law Violations": 10,
    "Arson": 10,
    "Drug/Narcotic Offenses": 8,
    "Assault Offenses": 6,
    "Driving Under the Influence": 5,
    "Burglary/Breaking & Entering": 4,
    "Motor Vehicle Theft": 3,
    "Extortion/Blackmail": 3,
    "Prostitution Offenses": 3,
    "Pornography/Obscene Material": 3,
    "Destruction/Damage/Vandalism of Property": 2,
    "Stolen Property Offenses": 2,
    "Animal Cruelty": 2,
    "Larceny/Theft Offenses": 1,
    "Fraud Offenses": 1,
    "Counterfeiting/Forgery": 1,
}
DEFAULT_SEVERITY = 1

# A block's danger score is its summed incident severity per year. Levels are
# fixed (not relative to the current view) so colors mean the same thing under
# every filter. With all data, ~60% of blocks are low, ~27% moderate, ~14% high.
DANGER_LEVELS = [
    {"key": "low", "label": "Low", "min_score": 0},
    {"key": "moderate", "label": "Moderate", "min_score": 5},
    {"key": "high", "label": "High", "min_score": 15},
]


@dataclass
class Incident:
    incident_id: str
    label: str
    date: str
    time: str
    location: str
    zone: str
    latitude: float
    longitude: float
    types: set = field(default_factory=set)
    offenses: list = field(default_factory=list)
    crime_against: set = field(default_factory=set)

    def to_dict(self):
        return {
            "incident_id": self.incident_id,
            "label": self.label,
            "date": self.date,
            "time": self.time,
            "location": self.location,
            "zone": self.zone,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "types": sorted(self.types),
            "offenses": self.offenses,
            "crime_against": sorted(self.crime_against),
        }


@lru_cache(maxsize=1)
def load_incidents(path=DATA_FILE):
    """Read the CSV and collapse charge rows into incidents, oldest first."""
    incidents = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            inc = incidents.get(row["incident_id"])
            if inc is None:
                try:
                    lat, lon = float(row["latitude"]), float(row["longitude"])
                except ValueError:
                    continue
                inc = incidents[row["incident_id"]] = Incident(
                    incident_id=row["incident_id"],
                    label=row["incident_id_label"],
                    date=row["date"],
                    time=row["time"],
                    location=row["location"],
                    zone=row["zone_label"],
                    latitude=lat,
                    longitude=lon,
                )
            inc.types.add(row["incident_type"])
            inc.crime_against.add(row["crime_against"])
            if row["offense_description"] not in inc.offenses:
                inc.offenses.append(row["offense_description"])
    return tuple(sorted(incidents.values(), key=lambda i: (i.date, i.time)))


def filter_incidents(incidents, incident_type=None, crime_against=None, start=None, end=None):
    """Filter incidents. Dates are inclusive YYYY-MM-DD strings."""
    return [
        i for i in incidents
        if (not incident_type or incident_type in i.types)
        and (not crime_against or crime_against in i.crime_against)
        and (not start or i.date >= start)
        and (not end or i.date <= end)
    ]


def filter_options(incidents):
    """Values for populating the front-end filter controls."""
    return {
        "types": sorted({t for i in incidents for t in i.types}),
        "crime_against": sorted({c for i in incidents for c in i.crime_against}),
        "min_date": incidents[0].date if incidents else None,
        "max_date": incidents[-1].date if incidents else None,
    }


def incident_severity(incident):
    return max((SEVERITY_WEIGHTS.get(t, DEFAULT_SEVERITY) for t in incident.types), default=DEFAULT_SEVERITY)


def danger_level(score):
    return [lvl for lvl in DANGER_LEVELS if score >= lvl["min_score"]][-1]["key"]


def window_years(all_incidents, start=None, end=None):
    """Length in years of the date window, defaulting to the data's own span."""
    if not all_incidents:
        return 1.0
    try:
        first = date.fromisoformat(start) if start else None
        last = date.fromisoformat(end) if end else None
    except ValueError:
        first = last = None
    first = first or date.fromisoformat(all_incidents[0].date)
    last = last or date.fromisoformat(all_incidents[-1].date)
    return max((last - first).days + 1, 1) / 365.25


_DIRECTIONS = {"n", "s", "e", "w", "north", "south", "east", "west"}
_STREET_TYPES = {
    "ave": "avenue", "st": "street", "blvd": "boulevard", "rd": "road", "ct": "court",
    "pl": "place", "dr": "drive", "pkwy": "parkway", "ln": "lane", "ter": "terrace",
    "trl": "trail", "sq": "square", "cir": "circle",
}


def street_key(name):
    """Normalize a street name so "N Oak Park Ave" matches "North Oak Park Avenue".

    A leading direction is dropped unless it is the name itself ("East Ave"),
    and spaces are removed so "Le Moyne" matches "Lemoyne".
    """
    words = [_STREET_TYPES.get(w, w) for w in re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()]
    if len(words) > 2 and words[0] in _DIRECTIONS:
        words = words[1:]
    return "".join(words)


class Segment(NamedTuple):
    """One block of one street. `coords` are (lon, lat) pairs."""
    name: str
    id: int
    coords: tuple
    highway: str


@lru_cache(maxsize=1)
def all_segments(path=STREETS_FILE):
    if not Path(path).exists():
        return ()
    return tuple(
        Segment(
            f["properties"]["name"],
            f["id"],
            tuple(tuple(c) for c in f["geometry"]["coordinates"]),
            f["properties"].get("highway", "residential"),
        )
        for f in json.loads(Path(path).read_text(encoding="utf-8"))["features"]
    )


@lru_cache(maxsize=1)
def load_street_segments():
    """Street blocks as {street_key: [(segment_id, ((lon, lat), ...)), ...]}."""
    by_street = defaultdict(list)
    for seg in all_segments():
        by_street[street_key(seg.name)].append((seg.id, seg.coords))
    return by_street


def inside_oak_park(coords):
    south, west, north, east = OAK_PARK_LIMITS
    tol = LIMITS_TOLERANCE
    return all(west - tol <= lon <= east + tol and south - tol <= lat <= north + tol for lon, lat in coords)


@lru_cache(maxsize=1)
def oak_park_streets():
    """Every street block inside the village, as a GeoJSON FeatureCollection."""
    features = [
        {
            "type": "Feature",
            "id": seg.id,
            "geometry": {"type": "LineString", "coordinates": [list(c) for c in seg.coords]},
            "properties": {"name": seg.name},
        }
        for seg in all_segments()
        if inside_oak_park(seg.coords)
    ]
    return {"type": "FeatureCollection", "features": features}


def distance_to_line_m(lat, lon, coords):
    """Meters from a point to a polyline, on a local flat-earth approximation."""
    mx = 111_320 * math.cos(math.radians(lat))
    my = 110_540
    best = math.inf
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        ax, ay = (x1 - lon) * mx, (y1 - lat) * my
        dx, dy = (x2 - x1) * mx, (y2 - y1) * my
        length_sq = dx * dx + dy * dy
        t = 0 if length_sq == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


@lru_cache(maxsize=None)
def street_segment_for(location, lat, lon):
    """The street block an incident location sits on, as (id, coords), or None."""
    match = re.match(r"^\d+ Block (.+)$", location)
    if not match:
        return None
    candidates = load_street_segments().get(street_key(match.group(1)), [])
    best = min(candidates, key=lambda seg: distance_to_line_m(lat, lon, seg[1]), default=None)
    if best is None or distance_to_line_m(lat, lon, best[1]) > MAX_SNAP_METERS:
        return None
    return best


def aggregate_locations(incidents, top_types=5, years=1.0):
    """Group incidents by block into a GeoJSON FeatureCollection, busiest first.

    Blocks matched to a street are LineStrings along that street; the rest are
    Points. `years` is the length of the filtered date window. Danger scores
    are per year, except that windows shorter than a year are not scaled up,
    so one incident in a one-month window doesn't read as twelve.
    """
    groups = defaultdict(list)
    geometries = {}
    for i in incidents:
        segment = street_segment_for(i.location, i.latitude, i.longitude)
        if segment:
            key = ("street", segment[0])
            geometries[key] = {"type": "LineString", "coordinates": [list(c) for c in segment[1]]}
        else:
            key = ("point", i.latitude, i.longitude)
            geometries[key] = {"type": "Point", "coordinates": [round(i.longitude, 6), round(i.latitude, 6)]}
        groups[key].append(i)

    per_year = max(years, 1.0)
    features = []
    for key, group in groups.items():
        type_counts = Counter(t for i in group for t in i.types)
        score = sum(incident_severity(i) for i in group) / per_year
        features.append({
            "type": "Feature",
            "id": key[1] if key[0] == "street" else None,
            "geometry": geometries[key],
            "properties": {
                "location": Counter(i.location for i in group).most_common(1)[0][0],
                "zone": Counter(i.zone for i in group).most_common(1)[0][0],
                "count": len(group),
                "top_types": type_counts.most_common(top_types),
                "crime_against": dict(Counter(c for i in group for c in i.crime_against)),
                "latest_date": max(i.date for i in group),
                "danger_score": round(score, 1),
                "danger_level": danger_level(score),
            },
        })
    features.sort(key=lambda f: f["properties"]["count"], reverse=True)
    return {"type": "FeatureCollection", "features": features, "danger_levels": DANGER_LEVELS}


def summarize(incidents):
    """Headline numbers and breakdowns for the summary panel."""
    locations = Counter(i.location for i in incidents)
    busiest = locations.most_common(1)
    return {
        "total": len(incidents),
        "locations": len({(i.latitude, i.longitude) for i in incidents}),
        "min_date": incidents[0].date if incidents else None,
        "max_date": incidents[-1].date if incidents else None,
        "busiest_location": {"location": busiest[0][0], "count": busiest[0][1]} if busiest else None,
        "by_type": Counter(t for i in incidents for t in i.types).most_common(),
        "by_crime_against": Counter(c for i in incidents for c in i.crime_against).most_common(),
        "by_zone": sorted(Counter(i.zone for i in incidents).items()),
        "by_year": sorted(Counter(i.date[:4] for i in incidents).items()),
    }
