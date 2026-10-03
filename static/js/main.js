// Wires up the filter controls and renders the incident table.

const typeFilter = document.getElementById("type-filter");
const startDate = document.getElementById("start-date");
const endDate = document.getElementById("end-date");
const applyButton = document.getElementById("apply-filters");
const incidentCount = document.getElementById("incident-count");
const tableBody = document.querySelector("#incidents-table tbody");

async function populateTypeFilter() {
  const types = await fetchIncidentTypes();
  for (const t of types) {
    const option = document.createElement("option");
    option.value = t;
    option.textContent = t;
    typeFilter.appendChild(option);
  }
}

function renderIncidents(incidents) {
  tableBody.innerHTML = "";
  for (const inc of incidents) {
    const row = document.createElement("tr");
    for (const value of [inc.date, inc.time, inc.incident_type, inc.offense_description, inc.location]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    }
    tableBody.appendChild(row);
  }
}

async function refresh() {
  const data = await fetchIncidents({
    type: typeFilter.value,
    start: startDate.value,
    end: endDate.value,
  });
  incidentCount.textContent = data.count.toLocaleString();
  renderIncidents(data.incidents);
}

applyButton.addEventListener("click", refresh);

populateTypeFilter().then(refresh).catch((err) => {
  console.error(err);
  incidentCount.textContent = "error loading data";
});
