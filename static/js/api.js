// Thin wrapper around the backend JSON API.

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

function filterParams({ type = "", crimeAgainst = "", start = "", end = "" } = {}) {
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (crimeAgainst) params.set("crime_against", crimeAgainst);
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  return params;
}

function fetchOptions() {
  return fetchJson("/api/options");
}

function fetchMapPoints(filters) {
  return fetchJson(`/api/map-points?${filterParams(filters)}`);
}

function fetchSummary(filters) {
  return fetchJson(`/api/summary?${filterParams(filters)}`);
}

function fetchIncidents(filters, limit = 500) {
  const params = filterParams(filters);
  params.set("limit", limit);
  return fetchJson(`/api/incidents?${params}`);
}
