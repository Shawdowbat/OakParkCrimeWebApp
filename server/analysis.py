"""Analysis of the Oak Park crime incident CSV.

The CSV has one row per *charge*, so an incident with several charges appears
on several rows. Everything here works on de-duplicated incidents.

Coordinates are recorded at block level ("800 Block N Cuyler Ave"), so many
incidents share the exact same point. The map therefore aggregates incidents
into one point per block rather than one dot per incident.
"""

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "crime-incidents-oak-park.csv"


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


def aggregate_locations(incidents, top_types=5):
    """Group incidents by block into a GeoJSON FeatureCollection, busiest first."""
    groups = defaultdict(list)
    for i in incidents:
        groups[(i.latitude, i.longitude)].append(i)

    features = []
    for (lat, lon), group in groups.items():
        type_counts = Counter(t for i in group for t in i.types)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": {
                "location": Counter(i.location for i in group).most_common(1)[0][0],
                "zone": Counter(i.zone for i in group).most_common(1)[0][0],
                "count": len(group),
                "top_types": type_counts.most_common(top_types),
                "crime_against": dict(Counter(c for i in group for c in i.crime_against)),
                "latest_date": max(i.date for i in group),
            },
        })
    features.sort(key=lambda f: f["properties"]["count"], reverse=True)
    return {"type": "FeatureCollection", "features": features}


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
