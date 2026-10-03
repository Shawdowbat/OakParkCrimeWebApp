"""Safe walking routes over Oak Park's street blocks.

The street network is the block segments from analysis.all_segments(): each
block is an edge between the intersections at its two ends. An edge costs its
length, scaled up for crime on that block and for how busy the street is, so
the cheapest path is the one that best avoids both. Incidents recorded at an
intersection add a fixed cost to passing through it.

Danger scores come from the incidents in the chosen date window (the map's
time frame) across all crime types, so a route doesn't change when someone
narrows the map to one crime type. Routes stay inside the village limits,
where the crime data applies.
"""

import heapq
import itertools
import math
from collections import defaultdict
from functools import lru_cache
from typing import NamedTuple

from server import analysis

WALK_MPS = 1.2  # a child's walking pace, about 2.7 mph
BIKE_MPS = 3.5  # a child's cycling pace, about 8 mph

# Extra cost per meter on top of the meter itself, by OSM road class.
TRAFFIC_PENALTY = {"trunk": 3.0, "primary": 3.0, "secondary": 1.8, "tertiary": 0.7, "unclassified": 0.2}
BUSY_CLASSES = {"trunk", "primary", "secondary"}
# Crime multiplies a block's cost by 1 + CRIME_WEIGHT * log(1 + score / CRIME_SCALE):
# a moderate block (5 pts/yr) costs ~2x, a high one (15) ~3x, the worst ~6.5x.
CRIME_WEIGHT = 1.5
CRIME_SCALE = 5.0
HIGH_DANGER = analysis.DANGER_LEVELS[-1]["min_score"]
INTERSECTION_PENALTY_M = 25
# Cost, in meters, of changing streets.
TURN_PENALTY_M = 60
INTERSECTION_SNAP_M = 40
# The alternative route pays this multiple to reuse a block of the safest route.
REUSE_PENALTY = 3.0
MAX_OVERLAP = 0.85
MAX_SNAP_M = 300


class RouteError(ValueError):
    pass


class Edge(NamedTuple):
    u: tuple
    v: tuple
    coords: tuple
    length: float
    name: str
    highway: str
    segment_id: int


class Network(NamedTuple):
    """The street layout, which doesn't depend on the date window."""
    edges: list
    adjacency: dict
    street_keys: list  # analysis.street_key() of each edge's name


class Graph(NamedTuple):
    edges: list
    adjacency: dict
    street_keys: list
    edge_danger: list  # danger score of each edge for the date window
    node_danger: dict


def _meters(lon1, lat1, lon2, lat2):
    mx = 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lon2 - lon1) * mx, (lat2 - lat1) * 110_540)


def _length(coords):
    return sum(_meters(*a, *b) for a, b in zip(coords, coords[1:]))


@lru_cache(maxsize=1)
def street_network():
    edges = []
    adjacency = defaultdict(list)
    for seg in analysis.all_segments():
        # Named service roads only touch public streets mid-block, so they
        # would be dead ends in the graph. Streets outside the village are
        # left out because the crime data stops at its limits: they would
        # look crime-free when they are really unmeasured.
        if seg.highway == "service" or seg.coords[0] == seg.coords[-1] or not analysis.inside_oak_park(seg.coords):
            continue
        edge = Edge(seg.coords[0], seg.coords[-1], seg.coords, _length(seg.coords), seg.name, seg.highway, seg.id)
        adjacency[edge.u].append(len(edges))
        adjacency[edge.v].append(len(edges))
        edges.append(edge)
    street_keys = [analysis.street_key(edge.name) for edge in edges]
    return Network(edges, dict(adjacency), street_keys)


@lru_cache(maxsize=4096)
def _nearest_node(lon, lat):
    """The intersection within INTERSECTION_SNAP_M of a point, or None."""
    nearest = min(street_network().adjacency, key=lambda n: _meters(lon, lat, *n))
    return nearest if _meters(lon, lat, *nearest) <= INTERSECTION_SNAP_M else None


@lru_cache(maxsize=16)
def street_graph(start=None, end=None):
    """The street network with danger scores for incidents dated start..end."""
    network = street_network()
    all_incidents = analysis.load_incidents()
    incidents = analysis.filter_incidents(all_incidents, start=start, end=end)
    years = analysis.window_years(all_incidents, start=start, end=end)
    blocks = analysis.aggregate_locations(incidents, years=years)["features"]

    block_danger = {f["id"]: f["properties"]["danger_score"] for f in blocks if f["id"] is not None}
    edge_danger = [block_danger.get(edge.segment_id, 0.0) for edge in network.edges]

    node_danger = defaultdict(float)
    for f in blocks:
        if f["geometry"]["type"] == "Point":
            node = _nearest_node(*f["geometry"]["coordinates"])
            if node is not None:
                node_danger[node] += f["properties"]["danger_score"]
    return Graph(network.edges, network.adjacency, network.street_keys, edge_danger, dict(node_danger))


def risk_per_meter(graph, idx):
    """How much worse than a quiet, crime-free street each meter of this block is."""
    crime = CRIME_WEIGHT * math.log1p(graph.edge_danger[idx] / CRIME_SCALE)
    return crime + TRAFFIC_PENALTY.get(graph.edges[idx].highway, 0.0)


def edge_cost(graph, idx, length):
    return length * (1 + risk_per_meter(graph, idx))


def _node_cost(graph, node):
    danger = graph.node_danger.get(node, 0.0)
    return INTERSECTION_PENALTY_M * math.log1p(danger / CRIME_SCALE) if danger else 0.0


# --- Snapping a location onto the street network ---------------------------

class Snap(NamedTuple):
    edge_index: int
    position: float  # meters from the edge's u end


def snap(graph, lat, lon):
    """The nearest point on any street block to (lat, lon)."""
    best = None
    for idx, edge in enumerate(graph.edges):
        distance = analysis.distance_to_line_m(lat, lon, edge.coords)
        if best is None or distance < best[0]:
            best = (distance, idx)
    if best is None or best[0] > MAX_SNAP_M:
        return None
    edge = graph.edges[best[1]]
    return Snap(best[1], _position_along(edge.coords, lat, lon))


def _position_along(coords, lat, lon):
    mx = 111_320 * math.cos(math.radians(lat))
    my = 110_540
    best = (math.inf, 0.0)
    walked = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        dx, dy = (x2 - x1) * mx, (y2 - y1) * my
        ax, ay = (lon - x1) * mx, (lat - y1) * my
        length_sq = dx * dx + dy * dy
        t = 0.0 if length_sq == 0 else max(0.0, min(1.0, (ax * dx + ay * dy) / length_sq))
        distance = math.hypot(ax - t * dx, ay - t * dy)
        if distance < best[0]:
            best = (distance, walked + t * math.sqrt(length_sq))
        walked += math.sqrt(length_sq)
    return best[1]


def _cut(coords, start_m, end_m):
    """The part of a polyline between two distances along it, in travel order."""
    if start_m > end_m:
        return _cut(coords, end_m, start_m)[::-1]
    out = []
    walked = 0.0
    for a, b in zip(coords, coords[1:]):
        piece = _meters(*a, *b)
        lo, hi = walked, walked + piece
        if hi >= start_m and lo <= end_m and piece > 0:
            if not out:
                f = (start_m - lo) / piece
                out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            if hi <= end_m:
                out.append(b)
            else:
                f = (end_m - lo) / piece
                out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
                break
        walked = hi
    if len(out) < 2:
        out = [coords[0], coords[0]] if not out else out * 2
    return tuple(out)


# --- Search -----------------------------------------------------------------

START, END = "start", "end"


def _virtual_links(graph, start, end):
    """Partial-block links from the start point and into the end point."""
    links = defaultdict(list)
    s_edge, e_edge = graph.edges[start.edge_index], graph.edges[end.edge_index]
    links[START].append((s_edge.u, start.edge_index, _cut(s_edge.coords, start.position, 0)))
    links[START].append((s_edge.v, start.edge_index, _cut(s_edge.coords, start.position, s_edge.length)))
    links[e_edge.u].append((END, end.edge_index, _cut(e_edge.coords, 0, end.position)))
    links[e_edge.v].append((END, end.edge_index, _cut(e_edge.coords, e_edge.length, end.position)))
    if start.edge_index == end.edge_index:
        links[START].append((END, start.edge_index, _cut(s_edge.coords, start.position, end.position)))
    return links


def _search(graph, links, cost_of, safety=True):
    """Dijkstra from START to END. Returns [(edge_index, coords, length), ...].

    The search state is (intersection, street arrived on), so changing streets
    can carry a cost: that keeps routes from zig-zagging block by block, which
    a child would find hard to follow. With safety=False only distance counts.
    """
    tie = itertools.count()
    origin = (START, None)
    best = {origin: 0.0}
    came_from = {}
    heap = [(0.0, next(tie), origin)]
    goal = None
    while heap:
        cost, _, state = heapq.heappop(heap)
        node, street = state
        if node == END:
            goal = state
            break
        if cost > best[state]:
            continue
        steps = [
            (edge.v if edge.u == node else edge.u, idx,
             edge.coords if edge.u == node else edge.coords[::-1], edge.length)
            for idx in graph.adjacency.get(node, ())
            for edge in (graph.edges[idx],)
        ]
        steps += [(nxt, idx, coords, _length(coords)) for nxt, idx, coords in links.get(node, ())]
        for nxt, idx, coords, length in steps:
            next_street = graph.street_keys[idx]
            new_cost = cost + cost_of(idx, length)
            if safety and nxt != END:
                new_cost += _node_cost(graph, nxt)
            if safety and street is not None and next_street != street:
                new_cost += TURN_PENALTY_M
            next_state = (nxt, next_street)
            if new_cost < best.get(next_state, math.inf):
                best[next_state] = new_cost
                came_from[next_state] = (state, idx, coords, length)
                heapq.heappush(heap, (new_cost, next(tie), next_state))
    if goal is None:
        return None
    legs = []
    state = goal
    while state != origin:
        state, idx, coords, length = came_from[state]
        legs.append((idx, coords, length))
    return legs[::-1]


def _overlap(legs, other):
    shared = {idx for idx, _, _ in other}
    total = sum(length for _, _, length in legs) or 1.0
    return sum(length for idx, _, length in legs if idx in shared) / total


# --- Describing a route -----------------------------------------------------

def _bearing(a, b):
    dx = (b[0] - a[0]) * math.cos(math.radians(a[1]))
    dy = b[1] - a[1]
    return math.degrees(math.atan2(dx, dy)) % 360


def _start_bearing(coords):
    for b in coords[1:]:
        if _meters(*coords[0], *b) > 3:
            return _bearing(coords[0], b)
    return _bearing(coords[0], coords[-1])


def _end_bearing(coords):
    for a in reversed(coords[:-1]):
        if _meters(*a, *coords[-1]) > 3:
            return _bearing(a, coords[-1])
    return _bearing(coords[0], coords[-1])


COMPASS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]


def _turn(angle):
    side = "right" if angle > 0 else "left"
    size = abs(angle)
    if size < 30:
        return "Continue onto"
    if size < 60:
        return f"Slight {side} onto"
    if size < 150:
        return f"Turn {side} onto"
    return f"Make a U-turn onto"


def _directions(graph, legs):
    groups = []
    for idx, coords, length in legs:
        edge = graph.edges[idx]
        key = analysis.street_key(edge.name)
        if groups and groups[-1]["key"] == key:
            group = groups[-1]
            group["coords"] += coords[1:]
        else:
            group = {"key": key, "name": edge.name, "coords": list(coords), "length": 0.0,
                     "busy": False, "high_crime": False}
            groups.append(group)
        group["length"] += length
        group["busy"] |= edge.highway in BUSY_CLASSES
        group["high_crime"] |= graph.edge_danger[idx] >= HIGH_DANGER

    # Fold slivers (from snapping onto a cross street) into the next street.
    groups = [g for i, g in enumerate(groups) if g["length"] >= 8 or i == len(groups) - 1] or groups

    steps = []
    for i, group in enumerate(groups):
        if i == 0:
            text = f"Head {COMPASS[round(_start_bearing(group['coords']) / 45) % 8]} on {group['name']}"
        else:
            angle = (_start_bearing(group["coords"]) - _end_bearing(groups[i - 1]["coords"]) + 180) % 360 - 180
            text = f"{_turn(angle)} {group['name']}"
        steps.append({
            "text": text,
            "distance_m": round(group["length"]),
            "busy_street": group["busy"],
            "high_crime": group["high_crime"],
        })
    steps.append({"text": "Arrive at your destination", "distance_m": 0, "busy_street": False, "high_crime": False})
    return steps


def _describe(graph, legs, label, direct_m):
    distance = sum(length for _, _, length in legs)
    edges = [(graph.edges[idx], graph.edge_danger[idx], length) for idx, _, length in legs]
    geometry = []
    for _, coords, _ in legs:
        points = [[round(lat, 6), round(lon, 6)] for lon, lat in coords]
        geometry.extend(points[1:] if geometry and geometry[-1] == points[0] else points)
    high_blocks = {idx for idx, _, _ in legs if graph.edge_danger[idx] >= HIGH_DANGER}
    return {
        "label": label,
        "distance_m": round(distance),
        "walk_minutes": max(1, round(distance / WALK_MPS / 60)),
        "bike_minutes": max(1, round(distance / BIKE_MPS / 60)),
        "extra_vs_direct_m": max(0, round(distance - direct_m)),
        "busy_street_m": round(sum(length for edge, _, length in edges if edge.highway in BUSY_CLASSES)),
        "high_danger_blocks": len(high_blocks),
        "average_danger": round(sum(danger * length for _, danger, length in edges) / (distance or 1), 1),
        "max_danger": round(max((danger for _, danger, _ in edges), default=0.0), 1),
        "geometry": geometry,
        "steps": _directions(graph, legs),
    }


def plan_routes(from_lat, from_lon, to_lat, to_lon, start_date=None, end_date=None):
    """Up to two walking routes, safest first, judged on incidents dated start..end."""
    graph = street_graph(start_date or None, end_date or None)
    start, end = snap(graph, from_lat, from_lon), snap(graph, to_lat, to_lon)
    if start is None or end is None:
        raise RouteError("That location is too far from Oak Park's streets.")
    if start == end:
        raise RouteError("The start and destination are the same place.")

    links = _virtual_links(graph, start, end)
    safest = _search(graph, links, lambda idx, length: edge_cost(graph, idx, length))
    if safest is None:
        raise RouteError("No walking route connects those two places.")
    direct = _search(graph, links, lambda idx, length: length, safety=False)
    direct_m = sum(length for _, _, length in direct)

    used = {idx for idx, _, _ in safest}
    alternative = _search(
        graph, links,
        lambda idx, length: edge_cost(graph, idx, length) * (REUSE_PENALTY if idx in used else 1.0),
    )
    if not alternative or _overlap(alternative, safest) >= MAX_OVERLAP:
        alternative = direct if _overlap(direct, safest) < MAX_OVERLAP else None
    if alternative is None:
        return [_describe(graph, safest, "Safest route", direct_m)]

    # The search balances risk against distance; rank the two by total risk
    # alone so the one labeled safest really is.
    first, second = sorted([safest, alternative], key=lambda legs: _exposure(graph, legs))
    first_m = sum(length for _, _, length in first)
    second_m = sum(length for _, _, length in second)
    second_label = "Shorter route" if second_m < first_m else "Alternative route"
    return [
        _describe(graph, first, "Safest route", direct_m),
        _describe(graph, second, second_label, direct_m),
    ]


def _exposure(graph, legs):
    """Total risk along a route: crime and traffic per meter, plus risky intersections."""
    along = sum(length * risk_per_meter(graph, idx) for idx, _, length in legs)
    crossings = sum(_node_cost(graph, coords[-1]) for _, coords, _ in legs[:-1])
    return along + crossings
