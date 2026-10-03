# Oak Park Safe Routes

**Helping Oak Park parents find safer ways for their kids to get where they're going.**

Whether your child walks to school, bikes to the library, or heads to a friend's house or the park, Oak Park Safe Routes suggests walking routes that steer around blocks with more reported crime and away from busy streets. It's built for parents on the go, so it works best on a phone and can be added to your home screen like an app.

> **Please read:** this app shows *reported* incidents only. A green street is not a guarantee of safety, and the routes are suggestions, not official safe-route designations. Walk new routes with your child first, teach them to stay alert, and use your own judgment. **In an emergency, call 911.**

---

## For parents

### Plan a safe route in three steps

1. **Choose a starting point.** Type your address, tap **◎ Use my current location**, or tap **📍** and then tap the map.
2. **Choose where your child is going.** Start typing a school, park or library to pick it from the list, or enter any Oak Park address.
3. **Tap "Find safe routes".**

You'll get **two routes** drawn in purple on the map. The bold line is the one currently selected; tap the other line or its card to switch. Each route card shows:

- **How long it takes**, at a child's pace: walking (about 2.7 mph) and biking (about 8 mph)
- **Distance**, and how much longer it is than the most direct way
- **Whether it passes any high-crime blocks**
- **How much of it runs along busy streets** like Harlem Ave, North Ave, Madison St, Lake St, Chicago Ave or Roosevelt Rd

Below the cards are **turn-by-turn directions**, written simply so you can go over them with your child. Any step on a busy street or a high-crime block is flagged with a ⚠ so you know where to remind them to use crosswalks or take extra care.

Not quite right? **Drag the A or B pin** to adjust a spot, or tap **⇅** to plan the trip home.

### Places kids go, built in

Oak Park's schools are on the map and in the destination list. That's every District 97 elementary and middle school, OPRF and Fenwick high schools, and several private schools. Any school not on the list can be found by typing its address. Parks, the Public Library, train stations, police and fire stations, and hospitals are also included. Use the layer menu (top right of the map) to show or hide each group.

### Reading the map

Every street in Oak Park is colored by how much reported crime happened on that block:

- **Green**: no incidents, or only minor ones
- **Orange**: some incidents
- **Red**: more serious or more frequent incidents

Dots mark incidents reported at intersections. Tap any street to see what was reported there and when.

Colors account for *how serious* each incident is, not just how many there were. One robbery counts as much as twelve thefts, and violent crimes count the most (see [How safety is judged](#how-safety-is-judged)).

### Choosing a time frame

Open **Map filters** and use the **Time frame** slider to look at the last 1 to 10 years (the default is 10). The street colors **and** the route suggestions both update to use only incidents from that period, so you can see what's been happening recently. You can also filter the map by crime type, although routes always consider every type of crime, since your child would encounter all of them.

### Add it to your phone's home screen

- **iPhone (Safari):** tap the Share button, then **Add to Home Screen**.
- **Android (Chrome):** tap the ⋮ menu, then **Add to Home screen** or **Install app**.

It opens full screen like a regular app.

### Tips for using it with your kids

- **Walk the route together first**, ideally at the same time of day your child will travel.
- **Point out the ⚠ steps**: where to cross busy streets, and blocks where they should stay alert.
- **Pick a backup.** The second route is a good alternative if the first one is blocked or doesn't feel right.
- **Know the safe spots along the way**: schools, the library, fire stations and open businesses where your child can go for help.

---

## How safety is judged

### Crime on each block

Every reported incident is weighted by how dangerous it is to be around, from 1 (minor) to 25 (gravest):

| Weight | Incident types |
|---|---|
| 25 | Homicide |
| 20 | Sex offenses, kidnapping |
| 12 | Robbery |
| 10 | Weapons violations, arson |
| 8 | Drugs/narcotics |
| 6 | Assault |
| 5 | Driving under the influence |
| 4 | Burglary |
| 3 | Motor vehicle theft, extortion, prostitution, obscene material |
| 2 | Vandalism, stolen property, animal cruelty |
| 1 | Theft, fraud, counterfeiting |

A block's **danger score** is the total weight of its incidents per year. Under 5 points a year is **low**, 5 to 15 is **moderate**, and 15 or more is **high**.

### Choosing routes

Each block's "cost" for routing is its length, increased by:

- **Crime on the block.** A moderate block counts about twice its length, a high one about three times, and the worst blocks over six times.
- **Traffic.** Harlem and North Ave count about 4 times their length; Madison, Lake, Chicago and Roosevelt about 3 times; Oak Park Ave, Ridgeland, Austin and similar streets about 1.7 times. Quiet residential streets count only their length.
- **Intersections with reported incidents.**
- **Each change of street.** This keeps routes simple enough for a child to remember.

The route with the lowest overall risk is labeled **Safest route**. The second route is a meaningfully different alternative. Routes stay inside Oak Park, because the crime data stops at the village limits and streets outside would wrongly look crime-free.

### Limitations to keep in mind

- **Reported incidents only.** Unreported incidents, time of day, lighting, construction and traffic signals aren't included.
- **Streets only.** Routes follow streets and don't use park paths or cut-throughs. They don't know about crossing guards.
- **The data covers January 2022 to September 2026**, about 13,500 incidents across Oak Park. Time frames longer than about 5 years show the same results.
- **Address search uses OpenStreetMap's free Nominatim service.** It's limited to Oak Park, and what you type is sent to that service.

---

## For developers

### Run it locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server\app.py
```

Then open http://localhost:5000. Phones on the same Wi-Fi can connect to `http://<your-computer's-IP>:5000`. (Set `FLASK_DEBUG=1` for auto-reload while editing.)

"Use my current location" only works over HTTPS or on `localhost`, so test it on a phone after deploying.

### Run the tests

```powershell
.venv\Scripts\python -m pytest
```

### Deploy

The app runs under [waitress](https://docs.pylonsproject.org/projects/waitress/), a production WSGI server that works on Linux, macOS and Windows.

- **Platforms that use a Procfile** (Render, Railway, Heroku): connect the repo. The included `Procfile` starts `waitress-serve ... wsgi:app`. Set `TRUST_PROXY_HOPS=1`.
- **Docker** (Fly.io, a VPS, Cloud Run):
  ```sh
  docker build -t safe-routes .
  docker run -p 8000:8000 safe-routes
  ```
  The image runs as a non-root user and has a health check on `/healthz`.

**Serve it over HTTPS** (every platform above does this for you). Phones need HTTPS for location sharing and home-screen install.

| Environment variable | Purpose |
|---|---|
| `PORT` | Port to listen on (default 5000 locally, 8000 in Docker) |
| `TRUST_PROXY_HOPS` | Number of reverse proxies in front of the app (usually `1` when hosted), so rate limits see real visitor IPs |
| `FLASK_DEBUG` | `1` for auto-reload in development only |

**Before going live:**

- Restrict the CARTO map key (`MAP_API_KEY` in `static/js/map.js`) to your domain in the CARTO dashboard. Browser map keys are always visible to visitors, which is expected, but a domain restriction stops others from using yours.
- Address search uses the public Nominatim service, which allows light use (at most 1 request per second, enforced by the app). If the app gets busy, switch `server/geocode.py` to a paid geocoder or a self-hosted Nominatim.

**Built-in protections:**
- Rate limits per visitor: 30 address lookups and 60 route requests a minute.
- Security headers, including a Content Security Policy.
- Gzip compression. The map data drops from about 1 MB to about 56 KB, which matters on cellular.
- Cache-busted static files.
- A service worker that makes the app installable and always fetches fresh data when online.

### Updating the data

- **Crime incidents:** replace `data/crime-incidents-oak-park.csv` (same columns) and redeploy.
- **Streets:** `python scripts/build_street_segments.py` re-downloads Oak Park's streets from OpenStreetMap and rebuilds `data/street_segments.geojson`.
- **Places:** schools, parks and other landmarks live in `static/js/landmarks.js`.
- **App icons:** `python scripts/make_icons.py` regenerates them.

### Project structure

```
OakParkCrimeWebApp/
├── server/
│   ├── app.py          # Flask app, JSON API, security headers, compression, rate limits
│   ├── analysis.py     # Incident loading, severity weights, danger scores, street matching
│   ├── routing.py      # Safe-route search, ETAs and turn-by-turn directions
│   └── geocode.py      # Address lookup (OpenStreetMap Nominatim), limited to Oak Park
├── templates/index.html
├── static/
│   ├── css/styles.css  # Phone-first layout
│   ├── js/
│   │   ├── api.js        # Fetch helpers for the API
│   │   ├── map.js        # Crime map: street colors, legend, basemaps, landmarks
│   │   ├── routing.js    # Route planner: inputs, pins, route cards, directions
│   │   ├── landmarks.js  # Schools, parks and other places
│   │   └── main.js       # Filters, time frame slider, stats, table
│   ├── sw.js             # Service worker (installable app)
│   ├── manifest.webmanifest
│   └── icons/
├── data/
│   ├── crime-incidents-oak-park.csv
│   └── street_segments.geojson
├── scripts/            # Data and icon build scripts
├── tests/test_api.py
├── wsgi.py             # Production entry point
├── Procfile
└── Dockerfile
```

### API

| Endpoint | Description |
|---|---|
| `/api/route?from=lat,lon&to=lat,lon` | Up to two safe walking routes with ETAs and directions; optional `start`, `end` dates |
| `/api/geocode?q=` | Oak Park places matching an address or name |
| `/api/reverse?lat=&lon=` | Street address for a point |
| `/api/map-points` | Blocks with incidents, as GeoJSON with danger scores |
| `/api/streets` | Every street block in Oak Park |
| `/api/summary` | Totals and breakdowns |
| `/api/incidents` | Individual incidents, newest first (`limit`, max 5000) |
| `/api/options` | Incident types, categories and the data's date span |
| `/healthz` | Health check |

The data endpoints accept the filters `type`, `crime_against`, `start` and `end` (dates as `YYYY-MM-DD`).

### Credits

Street, school and place data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors. Map tiles by [CARTO](https://carto.com/attributions), OpenStreetMap and Esri. Maps powered by [Leaflet](https://leafletjs.com/).
