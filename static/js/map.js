// Leaflet map with one dot per block, area proportional to incident count.

const OAK_PARK_BOUNDS = [[41.865, -87.806], [41.9093, -87.7742]];
const MIN_RADIUS = 5;
const MAX_RADIUS = 22;

// ---------------------------------------------------------------------------
// CARTO basemap API key (from https://clausa.app.carto.com/ > Developers >
// API keys). Left empty, the map falls back to CARTO's keyless tiles.
// ---------------------------------------------------------------------------
const MAP_API_KEY = "cb1_48ts_1_3bb1cf30bf0c9d89d66eaeed";

const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const CARTO_ATTRIBUTION = `${OSM_ATTRIBUTION} &copy; <a href="https://carto.com/attributions">CARTO</a>`;
const ESRI_ATTRIBUTION = "Imagery &copy; Esri, Maxar, Earthstar Geographics";

const LIGHT_BASEMAP = "Detailed streets";
const DARK_BASEMAP = "Dark";

function cartoLayer(style) {
  const url = MAP_API_KEY
    ? `https://basemaps.cartocdn.com/rastertiles/${style}/{z}/{x}/{y}.png?key=${MAP_API_KEY}`
    : `https://{s}.basemaps.cartocdn.com/rastertiles/${style}/{z}/{x}/{y}{r}.png`;
  return L.tileLayer(url, { attribution: CARTO_ATTRIBUTION, subdomains: "abcd", maxZoom: 19 });
}

// "Detailed streets" is the OpenStreetMap house style: buildings, trees,
// parks, shops and schools are all drawn in color once zoomed in.
function buildBasemaps() {
  return {
    [LIGHT_BASEMAP]: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: OSM_ATTRIBUTION,
      maxZoom: 19,
    }),
    Voyager: cartoLayer("voyager"),
    Satellite: L.layerGroup([
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        attribution: ESRI_ATTRIBUTION,
        maxZoom: 19,
      }),
      cartoLayer("voyager_only_labels"),
    ]),
    [DARK_BASEMAP]: cartoLayer("dark_all"),
  };
}

function buildLandmarkOverlays() {
  const overlays = {};
  for (const category of LANDMARK_CATEGORIES) {
    const icon = L.divIcon({
      className: "landmark-marker",
      html: `<span style="--landmark-color: ${category.color}">${category.icon}</span>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
    const markers = category.places.map((place) =>
      L.marker([place.lat, place.lon], { icon, pane: "landmarks", alt: place.name }).bindTooltip(
        () => buildLandmarkTooltip(category, place),
        { direction: "top", offset: [0, -14], className: "dot-tooltip" },
      ),
    );
    overlays[`<span class="layer-icon">${category.icon}</span>${category.label}`] = L.layerGroup(markers);
  }
  return overlays;
}

const MapButtons = L.Control.extend({
  options: { position: "topleft" },

  onAdd(map) {
    const bar = L.DomUtil.create("div", "leaflet-bar map-buttons");
    this.addButton(bar, "⌂", "Reset view to all of Oak Park", () => map.fitBounds(OAK_PARK_BOUNDS));
    this.addButton(bar, "⛶", "Toggle full screen", () => {
      if (document.fullscreenElement) document.exitFullscreen();
      else map.getContainer().requestFullscreen();
    });
    document.addEventListener("fullscreenchange", () => map.invalidateSize());
    L.DomEvent.disableClickPropagation(bar);
    return bar;
  },

  addButton(bar, text, title, onClick) {
    const button = L.DomUtil.create("a", "", bar);
    button.href = "#";
    button.role = "button";
    button.title = title;
    button.setAttribute("aria-label", title);
    button.textContent = text;
    L.DomEvent.on(button, "click", (e) => {
      L.DomEvent.preventDefault(e);
      onClick();
    });
  },
});

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
    this.map = L.map(elementId, { renderer: this.renderer, scrollWheelZoom: true, maxZoom: 19 });
    this.map.fitBounds(OAK_PARK_BOUNDS);
    // Landmarks sit above the incident dots (overlay pane, 400) but below popups.
    this.map.createPane("landmarks").style.zIndex = 450;
    this.dots = L.layerGroup().addTo(this.map);
    this.lastData = null;

    this.basemaps = buildBasemaps();
    this.base = null;
    this.userPickedBase = false;
    this.settingBase = false;
    this.map.on("baselayerchange", (e) => {
      this.base = e.layer;
      if (!this.settingBase) this.userPickedBase = true;
    });
    this.applyTheme();

    const landmarks = buildLandmarkOverlays();
    for (const layer of Object.values(landmarks)) layer.addTo(this.map);
    L.control
      .layers(this.basemaps, landmarks, { collapsed: window.innerWidth < 700 })
      .addTo(this.map);
    L.control.scale({ metric: false }).addTo(this.map);
    new MapButtons().addTo(this.map);

    darkQuery.addEventListener("change", () => {
      this.applyTheme();
      if (this.lastData) this.render(this.lastData);
    });
  }

  // Follows the OS light/dark setting until the user picks a basemap themselves.
  applyTheme() {
    if (this.userPickedBase) return;
    const next = this.basemaps[darkQuery.matches ? DARK_BASEMAP : LIGHT_BASEMAP];
    if (next === this.base) return;
    this.settingBase = true;
    if (this.base) this.map.removeLayer(this.base);
    next.addTo(this.map);
    this.base = next;
    this.settingBase = false;
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

function buildLandmarkTooltip(category, place) {
  const root = document.createElement("div");

  const name = document.createElement("div");
  name.className = "tt-value";
  name.textContent = place.name;

  const kind = document.createElement("div");
  kind.className = "tt-label tt-category";
  kind.style.setProperty("--landmark-color", category.color);
  kind.textContent = category.label;

  root.append(name, kind);
  if (place.address) {
    const address = document.createElement("div");
    address.className = "tt-label";
    address.textContent = place.address;
    root.appendChild(address);
  }
  return root;
}

function formatDate(isoDate) {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
