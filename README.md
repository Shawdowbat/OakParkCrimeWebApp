# Oak Park Crime Web App

A web app for exploring reported crime incidents in Oak Park, IL. Flask serves
a JSON API over the incident CSV; the front end is plain HTML/CSS/JS.

## Project structure

```
OakParkCrimeWebApp/
├── server/
│   └── app.py              # Flask app + JSON API
├── templates/
│   └── index.html          # Main page
├── static/
│   ├── css/styles.css
│   └── js/
│       ├── api.js          # Fetch helpers for the backend API
│       └── main.js         # Filters + incident table rendering
├── data/
│   └── crime-incidents-oak-park.csv
├── tests/
│   └── test_api.py
└── requirements.txt
```

## Getting started

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server\app.py
```

Then open http://localhost:5000.

## API

| Endpoint              | Description                                           |
|-----------------------|-------------------------------------------------------|
| `/api/incidents`      | Incidents; filter with `type`, `start`, `end`, `limit` |
| `/api/incident-types` | Distinct incident types                               |
| `/api/stats`          | Incident counts grouped by type                       |

## Tests

```powershell
pytest
```
