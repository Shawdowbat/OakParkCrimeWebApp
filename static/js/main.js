// Wires the filter controls to the map, summary tiles and locations table.

const els = {
  dataSpan: document.getElementById("data-span"),
  period: document.getElementById("period-filter"),
  start: document.getElementById("start-date"),
  end: document.getElementById("end-date"),
  category: document.getElementById("category-filter"),
  type: document.getElementById("type-filter"),
  reset: document.getElementById("reset-filters"),
  total: document.getElementById("stat-total"),
  locations: document.getElementById("stat-locations"),
  topType: document.getElementById("stat-top-type"),
  topTypeCount: document.getElementById("stat-top-type-count"),
  busiest: document.getElementById("stat-busiest"),
  busiestCount: document.getElementById("stat-busiest-count"),
  tableBody: document.querySelector("#locations-table tbody"),
};

const crimeMap = new CrimeMap("map", "map-legend");
let options = null;
let requestId = 0;

function addOptions(select, values, labelFn = (v) => v) {
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = labelFn(value);
    select.appendChild(option);
  }
}

function setupFilters() {
  els.dataSpan.textContent = `${formatDate(options.min_date)} to ${formatDate(options.max_date)}`;
  for (const input of [els.start, els.end]) {
    input.min = options.min_date;
    input.max = options.max_date;
  }

  const firstYear = Number(options.min_date.slice(0, 4));
  const lastYear = Number(options.max_date.slice(0, 4));
  const years = [];
  for (let y = lastYear; y >= firstYear; y--) years.push(String(y));
  addOptions(els.period, years);
  addOptions(els.category, options.crime_against);
  addOptions(els.type, options.types);

  els.period.addEventListener("change", () => {
    const year = els.period.value;
    els.start.value = year ? `${year}-01-01` : "";
    els.end.value = year ? `${year}-12-31` : "";
    refresh();
  });
  for (const input of [els.start, els.end]) {
    input.addEventListener("change", () => {
      els.period.value = "";
      refresh();
    });
  }
  els.category.addEventListener("change", refresh);
  els.type.addEventListener("change", refresh);
  els.reset.addEventListener("click", () => {
    for (const el of [els.period, els.start, els.end, els.category, els.type]) el.value = "";
    refresh();
  });
}

function currentFilters() {
  return {
    type: els.type.value,
    crimeAgainst: els.category.value,
    start: els.start.value,
    end: els.end.value,
  };
}

function renderSummary(summary) {
  els.total.textContent = summary.total.toLocaleString();
  els.locations.textContent = summary.locations.toLocaleString();

  const [topType, topTypeCount] = summary.by_type[0] || ["–", 0];
  els.topType.textContent = topType;
  els.topTypeCount.textContent = topTypeCount ? `${topTypeCount.toLocaleString()} incidents` : "";

  const busiest = summary.busiest_location;
  els.busiest.textContent = busiest ? busiest.location : "–";
  els.busiestCount.textContent = busiest ? `${busiest.count.toLocaleString()} incidents` : "";
}

function renderTable(geojson) {
  els.tableBody.replaceChildren();
  const top = geojson.features.slice(0, 25);
  if (!top.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "empty";
    cell.textContent = "No incidents match the current filters.";
    row.appendChild(cell);
    els.tableBody.appendChild(row);
    return;
  }
  const levels = levelsByKey(geojson.danger_levels);
  for (const { properties: p } of top) {
    const row = document.createElement("tr");
    const cells = [
      [p.location, ""],
      [p.zone, ""],
      [p.count.toLocaleString(), "num"],
      [`${levels[p.danger_level].label} (${p.danger_score.toLocaleString()})`, ""],
      [p.top_types[0][0], ""],
      [formatDate(p.latest_date), ""],
    ];
    for (const [text, cls] of cells) {
      const td = document.createElement("td");
      td.textContent = text;
      if (cls) td.className = cls;
      row.appendChild(td);
    }
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = dangerColor(p.danger_score);
    row.children[3].prepend(swatch);
    els.tableBody.appendChild(row);
  }
}

async function refresh() {
  const id = ++requestId;
  const filters = currentFilters();
  crimeMap.setLoading(true);
  try {
    const [points, summary] = await Promise.all([fetchMapPoints(filters), fetchSummary(filters)]);
    if (id !== requestId) return;
    crimeMap.render(points);
    renderSummary(summary);
    renderTable(points);
  } catch (err) {
    console.error(err);
    if (id === requestId) els.total.textContent = "Error";
  } finally {
    if (id === requestId) crimeMap.setLoading(false);
  }
}

fetchOptions()
  .then((opts) => {
    options = opts;
    setupFilters();
    return refresh();
  })
  .catch((err) => {
    console.error(err);
    els.dataSpan.textContent = "data failed to load";
  });
