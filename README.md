# Smart Route Planning on the Atsign Platform

A migration of Intel's [Smart Route Planning Agent](https://github.com/open-edge-platform/edge-ai-suites/tree/release-2026.0.0/metro-ai-suite/smart-route-planning-agent)
to the Atsign Platform. Intel's LangGraph reasoning is **reused unchanged**; the
transport is replaced with encrypted, port-less, policy-gated identity-to-identity
messaging, and a Flutter commuter app + reused-Gradio operator console are added.

**Docs:** [PRD.md](PRD.md) (non-technical) · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) ·
[atsign-migration-assessment.md](atsign-migration-assessment.md) ·
[path-comparison-and-recommendation.md](path-comparison-and-recommendation.md) ·
[blueprints/](blueprints/) · platform reference: [ATPLATFORM_GUIDELINES.md](ATPLATFORM_GUIDELINES.md) ·
**production:** [GETTING_STARTED_PRODUCTION.md](GETTING_STARTED_PRODUCTION.md).

> For the Atsign Platform SDK reference (patterns, init, comms), see
> `ATPLATFORM_GUIDELINES.md`. This file is the **project-specific** reference.

---

## Architecture

```
phone camera ──on-device detection──┐   (intersection_app, Flutter)
cameras ─stream→ intersection agents┤
                 weather feed       ├─notify(encrypted)→ Smart Route Planner ─┬─push→ Commuter app (Flutter)
                 traffic-trends feed│   (LangGraph, headless)                 └─push→ Operator console (Gradio)
                 planned-events feed┘            │  asks ↑ RPC
                                              Policy Engine (default-deny)
```

- Every participant is an **atSign**. Data flows as encrypted notifications under the
  `smartroute` namespace. No open inbound ports anywhere.
- The planner subscribes to all publishers, **policy-checks** each (default-deny), caches
  the records, runs Intel's unmodified graph, and **pushes** the optimal route + reroute
  alerts to the commuter app and operator console.
- An intersection can be a **phone**: `intersection_app/` counts model cars on-device with
  ML Kit and publishes the same `live_traffic` record as its own atSign. Video never leaves
  the device — only a small encrypted count.

## atSign role map (`config/ee_atsigns.json`)

| Role | EE atSign | Production (vanity) |
|------|-----------|---------------------|
| planner | `@alpha` | `@smartroute_planner` |
| intersection — Market St / 5th Ave / Broadway | `@bravo` / `@charlie` / `@delta` | `@intxn_market_st` / `@intxn_5th_ave` / `@intxn_broadway` |
| weather / traffic-trends / events feed | `@echo` / `@foxtrot` / `@golf` | `@weather_feed` / `@traffic_trends_feed` / `@events_feed` |
| operator | `@hotel` | `@route_operator` |
| policy engine / admin | `@juliet` / `@kilo` | `@route_policy` / `@route_policy_admin` |
| commuter | `@india` | `@commuter01` |

Switch profiles with `ATSIGN_PROFILE=ee` (default) or `ATSIGN_PROFILE=vanity`.

## Records (all under the `smartroute` namespace)

| Record | Direction | Payload (model) |
|--------|-----------|-----------------|
| `live_traffic` | intersection → planner | `LiveTrafficData` |
| `weather` | weather feed → planner | `WeatherData` |
| `traffic_trends` | traffic-trends feed → planner | `TrafficTrendsData` |
| `planned_events` | events feed → planner | `PlannedEventsData` |
| `policy` | policy engine → planner **and policy admin** | `{grants: [atSign], issued_by}` |
| `admin` | policy admin → policy engine | `{grants: [atSign], version}` |

The **policy engine owns the rule set**, stored as encrypted records in its own atSign, so a
grant or revocation survives a restart of anything. The admin page states what the engine
mirrors back to it, never its own assumption, and the planner enforces the last set it was
given (default-deny until it has one).
| `route` | planner → commuter | `RoutePush` (route, route label, distance, reason, rerouted, points) |
| `status` | planner → operator | `StatusPush` (+ route geometry) |
| `request` | commuter → planner | `{source, destination}`: sets the planned trip when both are city-profile locations |

The wire format **is** Intel's `schema.py` Pydantic models serialized to JSON — Python and
Dart interoperate (verified in `validation/`).

## Reuse map (KEEP / SWAP / ADD)

- **KEEP (unchanged):** `agents/route_planner.py` (LangGraph), `planner_state.py`,
  `route_service.py`, `utils/*`, `schema.py`, GPX routes, `map_creator.py`, Gradio patterns.
  *(One line re-enabled in `route_planner.py`: the static-optimizer stack Intel shipped commented out.)*
- **SWAP (read the subscription cache instead of polling/CSV):** `controllers/live_traffic.py`,
  `weather_report.py`, `traffic_trends.py`, `planned_events.py` — class + `RouteStatusInterface`
  unchanged; originals kept as `*.intel-orig`.
- **ADD (new):** `src/atsign/*` (wire, roles, atsign_io, cache, messages, publishers,
  policy_engine, operator_console), `scripts/*`, `commuter_app/` and `intersection_app/`
  (Flutter), `dart_client/*` (pure-Dart tools), `validation/*`.

## Repo layout

```
smart-route-planning-agent/   Intel app (sparse clone) + src/atsign/ integration + SWAP'd controllers
commuter_app/                 Flutter commuter app (at_client_flutter + flutter_map)
intersection_app/             Flutter intersection sensor: camera + ML Kit -> live_traffic
scripts/                      onboarding + planner service/subscriber + receivers + run_demo.sh
dart_client/                  pure-Dart at_client programs: change_route (demo tool) + interop tests
config/ee_atsigns.json        role -> atSign map
blueprints/                   Path A (NoPorts) + Path B (native, 16/18) blueprints
validation/                   SDK + Python<->Dart interop proof (the de-risking spike)
```

## Run it (local ephemeral environment)

```bash
# 1. Start the EE (fresh image: it ships a valid cert; the cached one may be expired)
docker run -d --name atsign-ee --add-host vip.ve.atsign.zone:127.0.0.1 \
  -e DNS_FQDN=vip.ve.atsign.zone -e FIRST_PORT=2500 \
  -p 64:64 -p 2500-2540:2500-2540 atsigncompany/ephemeral

# 2. One-time: project venv with all deps
python3 -m venv .venv && . .venv/bin/activate
pip install "atsdk>=0.2.72" pydantic langgraph==1.0.9 gpxpy folium "gradio>=6.7.0"

# 3. Set up the terminal (venv + EE keystore + PYTHONPATH) — use a dedicated terminal
source scripts/env.sh

# 4. One-time: onboard the role atSigns
python scripts/onboard_all_ee.py
```

**A. Live system (recommended) — runs continuously:**
```bash
bash scripts/start_stack.sh &                 # policy + planner + 6 publishers + operator console + policy admin
# operator console -> http://127.0.0.1:7865 · policy admin -> http://127.0.0.1:8090
python scripts/trigger_incident.py            # inject congestion -> console flips to 🚨 REROUTE (clears in ~60s)
# ...or change the route from PURE DART (proves Dart can drive the system too):
(cd dart_client && HOME=/tmp/eehome dart run bin/change_route.dart \
   --atsign @bravo --root-domain vip.ve.atsign.zone)            # reroute (add --density 0 to clear)
bash scripts/stop_stack.sh                     # stop everything
```

**B. One-shot demos (run with the stack stopped — they manage their own policy):**
```bash
bash scripts/run_demo.sh             # policy -> pushed reroute -> commuter alert + operator status
python scripts/planner_run.py        # single reroute + push
python scripts/onboarding_finale.py  # a new intersection joins live (policy-gated)
```

Flutter apps — both sign-in screens let you pick the **root server** (production or the
`vip.ve.atsign.zone` test env) and your atSign:

```bash
cd commuter_app     && flutter run   # the driver's view: route + reroute alerts
cd intersection_app && flutter run   # a phone AS an intersection (needs a real device)
```

The intersection app replaces a simulated publisher with a real sensor: point it at model
cars and the planner reroutes. Its settings are stored as a **self key in the atSign's own
keystore**, so they follow the identity rather than the device. See
[intersection_app/README.md](intersection_app/README.md) for the density multiplier and
on-route location presets that make a reroute fire.

## Running in another city

Nothing about the Bay Area is in the code: the planner, the publishers, the scripts and
the apps take their geography from a **data directory** and the **city profile** inside it.
The bundled `smart-route-planning-agent/src/data/` is the San Francisco Bay Area and stays
the default; point `SMARTROUTE_DATA_DIR` at another directory to run somewhere else.

### Data directory layout

```text
$SMARTROUTE_DATA_DIR/            # default: smart-route-planning-agent/src/data
├── city_profile.json            # required: the geography (schema below)
├── routes/*.gpx                 # required: one file per route; the file name is the route id
├── csv/weather_report.csv       # conditions the feed publishers replay
├── csv/traffic_trends.csv       #   (atsign.publishers.feed); header-only files are fine
├── csv/planned_events.csv
└── config.json                  # Intel's legacy REST host list; `{}` is fine
```

`config.py` reads the variable once, at import: set it in the environment of **every**
Python process (planner service, publishers, scripts). A data directory without a
`city_profile.json` is an error, never a silent fallback to the Bay Area. The Dart CLI tools
read `$SMARTROUTE_DATA_DIR/city_profile.json` too (or `--profile <file>`). The Flutter
apps carry a copy as `assets/city_profile.json`; replace it and rebuild.

### City profile (`city_profile.json`)

JSON Schema: [`smart-route-planning-agent/src/data/city_profile.schema.json`](smart-route-planning-agent/src/data/city_profile.schema.json);
loader and validation: `smart-route-planning-agent/src/city_profile.py`.

```jsonc
{
  "schema_version": 1,                       // optional; only 1 is accepted
  "name": "Two Town",                        // optional display name
  "locations": [                             // required, ≥ 2: where trips start and end
    { "name": "Alpha", "desc": "Alpha Town", "lat": 10.0, "lon": 20.0 },
    { "name": "Beta",  "desc": "Beta Town",  "lat": 10.0, "lon": 20.1 }
  ],
  "default_trip": { "source": "Alpha Town", "destination": "Beta Town" },
                                             // optional; default first -> last location
  "ignored_routes": ["twotown-closed.gpx"],  // optional; GPX file names never offered
  "route_labels": { "twotown-direct.gpx": "Direct road" },   // optional; id -> label
  "map": { "centre": { "lat": 10.01, "lon": 20.05 }, "zoom": 12 },
                                             // optional; default mean of locations, zoom 10
  "intersections": {                         // optional; keyed by atSign role
    "intxn_main": { "name": "Main St & Middle Rd", "lat": 10.002, "lon": 20.05 }
  },
  "report_points": [                         // optional; extra known-good report spots
    { "name": "Direct road midpoint", "lat": 10.002, "lon": 20.05 }
  ],
  "avg_speed_kmh": 40,                       // optional; travel-time estimate, default 80
  "attribution": "Routes © OpenStreetMap contributors, ODbL."   // optional
}
```

- **locations** mirror the first and last `<wpt>` of the GPX files. A location's *label*
  (what trips, requests and dropdowns use) is its `desc`, else its `name`; a trip end
  matches a route when it equals the waypoint's `<name>` or `<desc>` **exactly**
  (case- and space-sensitive).
- **default_trip** is what `scripts/planner_service.py` plans until a commuter asks for
  another trip (`request` record): the request is honoured when both ends are profile
  locations with a route between them, otherwise it is logged and ignored.
- **intersections** are where `atsign.publishers.intersection --role <role>` reports from.
  `--name/--lat/--lon` or `SMARTROUTE_INTERSECTION_NAME/_LAT/_LON` override them (and with
  both coordinates a role need not be listed). The intersection app and
  `dart_client/bin/change_route.dart` offer `report_points` then `intersections` as their
  locations, the first being the default.
- **map**, **avg_speed_kmh** and **attribution** drive the map fallbacks and the route
  info box (Gradio UI) and the commuter app's opening view and credit line.

### GPX requirements

The planner's rules are simple and literal, so the data has to fit them:

1. **Identical endpoint waypoints.** Every route between two places starts with the same
   `<wpt>` (same `<name>`/`<desc>`) and ends with the same `<wpt>`; those are the
   profile's `locations`. Routes are directional: Beta → Alpha needs its own GPX files.
2. **The primary is strictly the shortest.** The direct route is the shortest offered
   route by `gpxpy` `length_3d()`; alternatives are tried in increasing length. Avoid ties
   (the winner of a tie is arbitrary). Put routes you keep but never want offered in
   `ignored_routes`.
3. **Intersections sit on the primary's track, exactly.** Live traffic matches a route
   only at a coordinate *equal* to one of its `<trkpt>`s (or endpoint `<wpt>`s) — no
   tolerance. Copy each intersection's `lat`/`lon` verbatim from a `<trkpt>` of the
   primary route; a point that is off by 1e-6 is delivered and ignored. A point shared by
   the alternative blocks it too. Only the first `<trk>` of a file is checked.
4. **Conditions are matched by a box.** Feed records match a trackpoint within ±0.005°
   (weather), ±0.0005° (traffic trends) or ±0.01° (planned events) in both latitude and
   longitude. They feed the static optimizers of the Gradio flow, not the planner
   service's realtime loop. The weather CSV `condition` must be a `WeatherStatus` value
   (`fog`, `rain`, `snow`, `cloudy`, `sunny`, `Clear`, ...): anything else reads as Clear.
5. **Credit the source.** Routes exported from OpenStreetMap (e.g. via OSRM/GraphHopper)
   are © OpenStreetMap contributors under the ODbL: say so in `attribution`, which the
   apps display beside the map.

`smart-route-planning-agent/tests/fixtures/twotown/` is a complete, minimal example: two
offered routes, one ignored route, one intersection on the primary.

### Tests

```bash
cd smart-route-planning-agent/src && python -m pytest ../tests -q
```

The tests run against the Two Town fixture (they set `SMARTROUTE_DATA_DIR` in
`tests/conftest.py`) and check, among other things, that the bundled profile still yields
the Bay Area values the code used to hard-wire.

## Status

Running end-to-end on both the local ephemeral environment and **real registered
atSigns** (see [GETTING_STARTED_PRODUCTION.md](GETTING_STARTED_PRODUCTION.md)).
Phases 0–9 in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) are complete, plus:

- **A phone as a real sensor** — `intersection_app/` detects model cars on-device and
  publishes live traffic reports; verified rerouting the planner from the camera.
- **Resilience hardening** — bounded publishes, a monitor liveness watchdog and
  self-healing reconnects, so a network change no longer wedges the stack
  (reproduced and fixed; see `validation/live_outage_test.py`).
- **Upstream fixes** — 7 pull requests merged into the Python SDK and released in
  `atsdk` 0.2.70/0.2.71; see [atsdk-upstream-status.md](atsdk-upstream-status.md).
