// Leaflet map drawing each block as its stretch of street (or a dot where no
// street matched). Line width tracks incident count; color tracks danger score.

const OAK_PARK_BOUNDS = [[41.865, -87.806], [41.9093, -87.7742]];
const MIN_WIDTH = 2.5;
const MAX_WIDTH = 10;

// Danger score (points/yr) to color: green, through orange, to red. Hue, saturation
// and lightness are interpolated between stops on a log scale, since scores
// run from under 1 to over 200.
const DANGER_STOPS = [
  { score: 0, h: 120, s: 86, l: 34 },
  { score: 8, h: 30, s: 92, l: 52 },
  { score: 40, h: 0, s: 61, l: 52 },
];
const DANGER_TICKS = [0, 5, 15, 40];

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

// Square root so the busiest blocks don't drown out the rest.
function widthScale(maxCount) {
  return (count) => MIN_WIDTH + (MAX_WIDTH - MIN_WIDTH) * Math.sqrt((count - 1) / Math.max(maxCount - 1, 1));
}

function dangerPosition(score) {
  const max = DANGER_STOPS[DANGER_STOPS.length - 1].score;
  return Math.log1p(Math.min(Math.max(score, 0), max)) / Math.log1p(max);
}

function dangerColor(score) {
  const t = dangerPosition(score);
  let i = 1;
  while (i < DANGER_STOPS.length - 1 && t > dangerPosition(DANGER_STOPS[i].score)) i++;
  const a = DANGER_STOPS[i - 1];
  const b = DANGER_STOPS[i];
  const ta = dangerPosition(a.score);
  const f = Math.min(Math.max((t - ta) / (dangerPosition(b.score) - ta), 0), 1);
  const mix = (key) => a[key] + (b[key] - a[key]) * f;
  return `hsl(${mix("h").toFixed(1)}, ${mix("s").toFixed(1)}%, ${mix("l").toFixed(1)}%)`;
}

function dangerGradientCss() {
  const steps = 12;
  const max = DANGER_STOPS[DANGER_STOPS.length - 1].score;
  const colors = [];
  for (let k = 0; k <= steps; k++) {
    const score = Math.expm1((k / steps) * Math.log1p(max));
    colors.push(`${dangerColor(score)} ${((k / steps) * 100).toFixed(1)}%`);
  }
  return `linear-gradient(to right, ${colors.join(", ")})`;
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
    this.casings = L.layerGroup().addTo(this.map);
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
    this.casings.clearLayers();
    this.dots.clearLayers();

    const features = geojson.features;
    const maxCount = features.length ? features[0].properties.count : 1;
    const width = widthScale(maxCount);
    const ring = cssVar("--surface-1");
    const levels = levelsByKey(geojson.danger_levels);

    // Features arrive busiest first, so thin lines are drawn on top and stay hoverable.
    // Every casing sits in a layer below every line so casings never cut across
    // a neighboring block at an intersection.
    for (const feature of features) {
      const props = feature.properties;
      const color = dangerColor(props.danger_score);
      const w = width(props.count);
      let mark;
      if (feature.geometry.type === "LineString") {
        const latlngs = feature.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
        this.casings.addLayer(
          L.polyline(latlngs, { color: ring, weight: w + 3, opacity: 0.85, interactive: false }),
        );
        mark = L.polyline(latlngs, { color, weight: w, opacity: 0.95 });
        mark.on("mouseover", () => mark.setStyle({ weight: w + 3 }));
        mark.on("mouseout", () => mark.setStyle({ weight: w }));
      } else {
        const [lon, lat] = feature.geometry.coordinates;
        mark = L.circleMarker([lat, lon], {
          radius: w / 2 + 3,
          color: ring,
          weight: 2,
          fillColor: color,
          fillOpacity: 0.95,
        });
        mark.on("mouseover", () => mark.setStyle({ weight: 4 }));
        mark.on("mouseout", () => mark.setStyle({ weight: 2 }));
      }
      mark.bindTooltip(() => buildTooltip(props, levels), {
        direction: "top",
        sticky: true,
        offset: [0, -8],
        className: "dot-tooltip",
      });
      this.dots.addLayer(mark);
    }

    this.renderLegend(maxCount, width);
  }

  renderLegend(maxCount, width) {
    this.legendEl.replaceChildren();
    if (!this.lastData.features.length) return;

    const colorGroup = legendGroup("Danger (pts/yr)");
    const scale = document.createElement("div");
    scale.className = "legend-gradient";
    scale.setAttribute("role", "img");
    scale.setAttribute("aria-label", "Color scale from green (safer) through orange to red (more dangerous)");
    const bar = document.createElement("div");
    bar.className = "legend-gradient-bar";
    bar.style.background = dangerGradientCss();
    const ticks = document.createElement("div");
    ticks.className = "legend-gradient-ticks";
    DANGER_TICKS.forEach((value, index) => {
      const tick = document.createElement("span");
      tick.style.left = `${dangerPosition(value) * 100}%`;
      tick.textContent = index === DANGER_TICKS.length - 1 ? `${value}+` : String(value);
      ticks.appendChild(tick);
    });
    scale.append(bar, ticks);
    colorGroup.appendChild(scale);

    const sizeGroup = legendGroup("Incidents per block");
    const sizeColor = cssVar("--text-muted");
    const values = [...new Set([1, niceRound(maxCount / 4), maxCount])].filter((v) => v <= maxCount);
    const svgNs = "http://www.w3.org/2000/svg";
    for (const value of values) {
      const item = document.createElement("span");
      item.className = "legend-item";
      const svg = document.createElementNS(svgNs, "svg");
      svg.setAttribute("width", 30);
      svg.setAttribute("height", MAX_WIDTH + 4);
      svg.setAttribute("aria-hidden", "true");
      const line = document.createElementNS(svgNs, "line");
      line.setAttribute("x1", 6);
      line.setAttribute("x2", 24);
      line.setAttribute("y1", (MAX_WIDTH + 4) / 2);
      line.setAttribute("y2", (MAX_WIDTH + 4) / 2);
      line.setAttribute("stroke", sizeColor);
      line.setAttribute("stroke-width", width(value));
      line.setAttribute("stroke-linecap", "round");
      svg.appendChild(line);
      const label = document.createElement("span");
      label.textContent = value.toLocaleString();
      item.append(svg, label);
      sizeGroup.appendChild(item);
    }

    this.legendEl.append(colorGroup, sizeGroup);
  }
}

function legendGroup(titleText) {
  const group = document.createElement("div");
  group.className = "legend-group";
  const title = document.createElement("span");
  title.className = "legend-title";
  title.textContent = titleText;
  group.appendChild(title);
  return group;
}

function levelsByKey(levels) {
  return Object.fromEntries(levels.map((level) => [level.key, level]));
}

function buildTooltip(props, levels) {
  const root = document.createElement("div");

  const count = document.createElement("div");
  count.className = "tt-value";
  count.textContent = `${props.count.toLocaleString()} incident${props.count === 1 ? "" : "s"}`;

  const place = document.createElement("div");
  place.className = "tt-label";
  place.textContent = `${props.location} · ${props.zone}`;

  const danger = document.createElement("div");
  danger.className = "tt-danger";
  const swatch = document.createElement("span");
  swatch.className = "legend-swatch";
  swatch.style.background = dangerColor(props.danger_score);
  const dangerText = document.createElement("span");
  dangerText.textContent = `${levels[props.danger_level].label} danger · ${props.danger_score.toLocaleString()} pts/yr`;
  danger.append(swatch, dangerText);

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

  root.append(count, place, danger, list, latest);
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
