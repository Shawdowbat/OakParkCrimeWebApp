"""Build data/street_segments.geojson: Oak Park streets split into blocks.

Fetches named streets from OpenStreetMap (Overpass API), cuts them at every
intersection with a differently named street, and joins the pieces OSM splits
mid-block, so each output feature is one block of one street.

Run from the project root:  python scripts/build_street_segments.py
Pass a path to a saved Overpass JSON response to skip the download.
"""

import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

OUT_FILE = Path(__file__).resolve().parent.parent / "data" / "street_segments.geojson"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Oak Park plus a margin so the boundary streets (Harlem, Austin, North Ave,
# Roosevelt) are complete.
BBOX = (41.862, -87.810, 41.912, -87.770)
QUERY = (
    "[out:json][timeout:60];"
    'way["highway"~"^(trunk|primary|secondary|tertiary|unclassified|residential|living_street|service)$"]["name"]'
    f"({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});out geom;"
)


def fetch_ways():
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": "OakParkCrimeMap/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)["elements"]


def split_at_intersections(ways):
    """Cut each way at nodes shared with a differently named street.

    Named service roads (private lanes, courts) get segments of their own but
    don't cut the public streets they join.
    """
    names_at_node = defaultdict(set)
    for way in ways:
        if way["tags"].get("highway") == "service":
            continue
        for node in way["nodes"]:
            names_at_node[node].add(way["tags"]["name"])
    intersections = {n for n, names in names_at_node.items() if len(names) > 1}

    pieces = []
    for way in ways:
        name = way["tags"]["name"]
        highway = way["tags"]["highway"]
        nodes = way["nodes"]
        coords = [(round(p["lon"], 6), round(p["lat"], 6)) for p in way["geometry"]]
        start = 0
        for i in range(1, len(nodes)):
            if nodes[i] in intersections or i == len(nodes) - 1:
                pieces.append({
                    "name": name, "highway": highway,
                    "nodes": nodes[start:i + 1], "coords": coords[start:i + 1],
                })
                start = i
    return pieces, intersections


# Busiest first; a block merged from pieces of mixed class keeps the busier one.
HIGHWAY_RANK = ["trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service"]


def busier(a, b):
    rank = {h: i for i, h in enumerate(HIGHWAY_RANK)}
    return a if rank.get(a, len(rank)) <= rank.get(b, len(rank)) else b


def merge_mid_block_splits(pieces, intersections):
    """Join same-street pieces that meet at a node that isn't an intersection."""
    by_name = defaultdict(list)
    for piece in pieces:
        by_name[piece["name"]].append(piece)

    merged = []
    for name, group in by_name.items():
        alive = set(range(len(group)))
        changed = True
        while changed:
            changed = False
            ends = defaultdict(list)
            for idx in alive:
                ends[group[idx]["nodes"][0]].append(idx)
                ends[group[idx]["nodes"][-1]].append(idx)
            for node, idxs in ends.items():
                if node in intersections or len(idxs) != 2 or idxs[0] == idxs[1]:
                    continue
                a, b = group[idxs[0]], group[idxs[1]]
                if a["nodes"][-1] != node:
                    a = {**a, "nodes": a["nodes"][::-1], "coords": a["coords"][::-1]}
                if b["nodes"][0] != node:
                    b = {**b, "nodes": b["nodes"][::-1], "coords": b["coords"][::-1]}
                group[idxs[0]] = {
                    "name": name,
                    "highway": busier(a["highway"], b["highway"]),
                    "nodes": a["nodes"] + b["nodes"][1:],
                    "coords": a["coords"] + b["coords"][1:],
                }
                alive.discard(idxs[1])
                changed = True
                break
        merged.extend(group[idx] for idx in sorted(alive))
    return merged


def main():
    if len(sys.argv) > 1:
        ways = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["elements"]
    else:
        ways = fetch_ways()
    ways = [w for w in ways if w.get("type") == "way" and w.get("geometry")]
    pieces, intersections = split_at_intersections(ways)
    segments = merge_mid_block_splits(pieces, intersections)

    features = [
        {
            "type": "Feature",
            "id": i,
            "geometry": {"type": "LineString", "coordinates": seg["coords"]},
            "properties": {"name": seg["name"], "highway": seg["highway"]},
        }
        for i, seg in enumerate(segments)
        if len(seg["coords"]) >= 2
    ]
    OUT_FILE.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"{len(ways)} ways -> {len(features)} block segments -> {OUT_FILE}")


if __name__ == "__main__":
    main()
