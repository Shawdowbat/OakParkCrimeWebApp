// Leaflet map with one dot per block, area proportional to incident count.

const OAK_PARK_BOUNDS = [[41.865, -87.806], [41.9093, -87.7742]];
const MIN_RADIUS = 5;
const MAX_RADIUS = 22;

const TILE_URLS = {
  light: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
  dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
};
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Area, not radius, tracks the count so big blocks don't visually overstate.
function radiusScale(maxCount) {
  return (count) => Math.max(MIN_RADIUS, MAX_RADIUS * Math.sqrt(count / Math.max(maxCount, 1)));
}

function niceRound(n) {
  if (n <= 10) return Math.max(1, Math.round(n));
  const magnitude = 10 ** Math.floor(Math.log10(n));
  return Math.round(n / magnitude) * magnitude;
}

class CrimeMap {
  constructor(elementId, legendId) {
    this.legendEl = document.getElementById(legendId);
    // Canvas tolerance widens each dot's hit area beyond its painted pixels.
    this.renderer = L.canvas({ tolerance: 8 });
    this.map = L.map(elementId, { renderer: this.renderer, scrollWheelZoom: true });
    this.map.fitBounds(OAK_PARK_BOUNDS);
    this.dots = L.layerGroup().addTo(this.map);
    this.tiles = null;
    this.lastData = null;

    this.applyTheme();
    darkQuery.addEventListener("change", () => {
      this.applyTheme();
      if (this.lastData) this.render(this.lastData);
    });
  }

  applyTheme() {
    if (this.tiles) this.tiles.remove();
    this.tiles = L.tileLayer(darkQuery.matches ? TILE_URLS.dark : TILE_URLS.light, {
      attribution: TILE_ATTRIBUTION,
      subdomains: "abcd",
      maxZoom: 19,
    }).addTo(this.map);
  }

  setLoading(loading) {
    this.map.getContainer().classList.toggle("is-loading", loading);
  }

  render(geojson) {
    this.lastData = geojson;
    this.dots.clearLayers();

    const features = geojson.features;
    const maxCount = features.length ? features[0].properties.count : 1;
    const radius = radiusScale(maxCount);
    const fill = cssVar("--series-1");
    const ring = cssVar("--surface-1");

    // Features arrive busiest first, so small dots are drawn on top and stay hoverable.
    for (const feature of features) {
      const [lon, lat] = feature.geometry.coordinates;
      const props = feature.properties;
      const dot = L.circleMarker([lat, lon], {
        radius: radius(props.count),
        color: ring,
        weight: 2,
        fillColor: fill,
        fillOpacity: 0.6,
      });
      dot.bindTooltip(() => buildTooltip(props), { direction: "top", className: "dot-tooltip" });
      dot.on("mouseover", () => dot.setStyle({ fillOpacity: 0.95 }));
      dot.on("mouseout", () => dot.setStyle({ fillOpacity: 0.6 }));
      this.dots.addLayer(dot);
    }

    this.renderLegend(maxCount, radius, fill, ring);
  }

  renderLegend(maxCount, radius, fill, ring) {
    this.legendEl.replaceChildren();
    if (!this.lastData.features.length) return;

    const values = [...new Set([1, niceRound(maxCount / 4), maxCount])].filter((v) => v <= maxCount);
    const title = document.createElement("span");
    title.className = "legend-title";
    title.textContent = "Incidents per block";
    this.legendEl.appendChild(title);

    const svgNs = "http://www.w3.org/2000/svg";
    for (const value of values) {
      const r = radius(value);
      const item = document.createElement("span");
      item.className = "legend-item";
      const svg = document.createElementNS(svgNs, "svg");
      const size = MAX_RADIUS * 2 + 4;
      svg.setAttribute("width", size);
      svg.setAttribute("height", size);
      svg.setAttribute("aria-hidden", "true");
      const circle = document.createElementNS(svgNs, "circle");
      circle.setAttribute("cx", size / 2);
      circle.setAttribute("cy", size / 2);
      circle.setAttribute("r", r);
      circle.setAttribute("fill", fill);
      circle.setAttribute("fill-opacity", "0.6");
      circle.setAttribute("stroke", ring);
      circle.setAttribute("stroke-width", "2");
      svg.appendChild(circle);
      const label = document.createElement("span");
      label.textContent = value.toLocaleString();
      item.append(svg, label);
      this.legendEl.appendChild(item);
    }
  }
}

function buildTooltip(props) {
  const root = document.createElement("div");

  const count = document.createElement("div");
  count.className = "tt-value";
  count.textContent = `${props.count.toLocaleString()} incident${props.count === 1 ? "" : "s"}`;

  const place = document.createElement("div");
  place.className = "tt-label";
  place.textContent = `${props.location} · ${props.zone}`;

  const list = document.createElement("ul");
  list.className = "tt-types";
  for (const [type, n] of props.top_types) {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = type;
    const num = document.createElement("span");
    num.className = "tt-num";
    num.textContent = n.toLocaleString();
    li.append(name, num);
    list.appendChild(li);
  }

  const latest = document.createElement("div");
  latest.className = "tt-label";
  latest.textContent = `Most recent: ${formatDate(props.latest_date)}`;

  root.append(count, place, list, latest);
  return root;
}

function formatDate(isoDate) {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
