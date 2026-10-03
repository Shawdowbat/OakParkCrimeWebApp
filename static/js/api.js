// Thin wrapper around the backend JSON API.

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    let message = `Request failed: ${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.error) message = body.error;
    } catch (err) {
      // Not JSON; keep the status message.
    }
    throw new Error(message);
  }
  return res.json();
}

function fetchRoutes(from, to, { start = "", end = "" } = {}) {
  const params = new URLSearchParams({ from: `${from.lat},${from.lon}`, to: `${to.lat},${to.lon}` });
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  return fetchJson(`/api/route?${params}`);
}

function geocodePlace(query) {
  return fetchJson(`/api/geocode?${new URLSearchParams({ q: query })}`);
}

function reverseGeocode(lat, lon) {
  return fetchJson(`/api/reverse?${new URLSearchParams({ lat, lon })}`);
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

function fetchStreets() {
  return fetchJson("/api/streets");
}

function fetchSummary(filters) {
  return fetchJson(`/api/summary?${filterParams(filters)}`);
}

function fetchIncidents(filters, limit = 500) {
  const params = filterParams(filters);
  params.set("limit", limit);
  return fetchJson(`/api/incidents?${params}`);
}
