// Thin wrapper around the backend JSON API.

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

function fetchIncidents({ type = "", start = "", end = "", limit = 500 } = {}) {
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  params.set("limit", limit);
  return fetchJson(`/api/incidents?${params}`);
}

function fetchIncidentTypes() {
  return fetchJson("/api/incident-types");
}

function fetchStats() {
  return fetchJson("/api/stats");
}
