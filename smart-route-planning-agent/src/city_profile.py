# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
City profile: every piece of geography the planner, publishers and scripts need,
read from `city_profile.json` in the data directory instead of from code.

The bundled `data/city_profile.json` is the San Francisco Bay Area profile the
project has always shipped. To run in another city, point SMARTROUTE_DATA_DIR at a
folder holding `routes/*.gpx`, `csv/*.csv` and a `city_profile.json` for that city.
The schema is documented in the repository README ("Running in another city") and
in `data/city_profile.schema.json`.

Kept free of other project imports so config.py can load it first.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_ZOOM = 10
DEFAULT_AVG_SPEED_KMH = 80.0


class CityProfileError(ValueError):
    """The city profile is missing, unreadable or inconsistent."""


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CityProfileError(f"{where} must be a number, got {value!r}")
    return float(value)


def _point(raw: Any, where: str) -> dict:
    if not isinstance(raw, dict):
        raise CityProfileError(f"{where} must be an object with lat and lon")
    lat = _number(raw.get("lat"), f"{where}.lat")
    lon = _number(raw.get("lon"), f"{where}.lon")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise CityProfileError(f"{where} ({lat}, {lon}) is not a valid coordinate")
    return {"lat": lat, "lon": lon}


def _named_point(raw: Any, where: str) -> dict:
    point = _point(raw, where)
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise CityProfileError(f"{where}.name must be a non-empty string")
    return {"name": name, **point}


def location_label(location: dict) -> str:
    """The label a location is known by in trips and requests.

    Mirrors MapDataParser.get_start_end_locations: the GPX waypoint's <desc> when it
    has one, else its <name>.
    """
    return location.get("desc") or location["name"]


def normalise(raw: Any) -> dict:
    """Validate a parsed profile and fill optional fields with neutral defaults."""
    if not isinstance(raw, dict):
        raise CityProfileError("the profile must be a JSON object")

    version = raw.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise CityProfileError(
            f"schema_version {version!r} is not supported (expected {SCHEMA_VERSION})"
        )

    raw_locations = raw.get("locations")
    if not isinstance(raw_locations, list) or len(raw_locations) < 2:
        raise CityProfileError("locations must list at least two places")
    locations = []
    for i, loc in enumerate(raw_locations):
        entry = _named_point(loc, f"locations[{i}]")
        desc = loc.get("desc")
        if desc is not None and not isinstance(desc, str):
            raise CityProfileError(f"locations[{i}].desc must be a string")
        entry["desc"] = desc or ""
        locations.append(entry)
    labels = [location_label(loc) for loc in locations]
    if len(set(labels)) != len(labels):
        raise CityProfileError(f"location labels must be unique: {labels}")

    trip = raw.get("default_trip") or {}
    if not isinstance(trip, dict):
        raise CityProfileError("default_trip must be an object")
    source = trip.get("source", labels[0])
    destination = trip.get("destination", labels[-1])
    for key, value in (("source", source), ("destination", destination)):
        if find_location(locations, value) is None:
            raise CityProfileError(
                f"default_trip.{key} {value!r} is not one of the locations {labels}"
            )
    source = location_label(find_location(locations, source))
    destination = location_label(find_location(locations, destination))

    ignored = raw.get("ignored_routes", [])
    if not isinstance(ignored, list) or not all(isinstance(r, str) for r in ignored):
        raise CityProfileError("ignored_routes must be a list of GPX file names")

    route_labels = raw.get("route_labels", {})
    if not isinstance(route_labels, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in route_labels.items()
    ):
        raise CityProfileError("route_labels must map GPX file names to strings")

    raw_map = raw.get("map") or {}
    if not isinstance(raw_map, dict):
        raise CityProfileError("map must be an object")
    if "centre" in raw_map:
        centre = _point(raw_map["centre"], "map.centre")
    else:
        centre = {
            "lat": sum(loc["lat"] for loc in locations) / len(locations),
            "lon": sum(loc["lon"] for loc in locations) / len(locations),
        }
    zoom = raw_map.get("zoom", DEFAULT_ZOOM)
    if isinstance(zoom, bool) or not isinstance(zoom, int) or not 1 <= zoom <= 20:
        raise CityProfileError(f"map.zoom must be an integer 1-20, got {zoom!r}")

    raw_intersections = raw.get("intersections", {})
    if not isinstance(raw_intersections, dict):
        raise CityProfileError("intersections must map a role to {name, lat, lon}")
    intersections = {
        role: _named_point(spec, f"intersections.{role}")
        for role, spec in raw_intersections.items()
    }

    raw_points = raw.get("report_points", [])
    if not isinstance(raw_points, list):
        raise CityProfileError("report_points must be a list of {name, lat, lon}")
    report_points = [
        _named_point(p, f"report_points[{i}]") for i, p in enumerate(raw_points)
    ]

    speed = _number(raw.get("avg_speed_kmh", DEFAULT_AVG_SPEED_KMH), "avg_speed_kmh")
    if speed <= 0:
        raise CityProfileError("avg_speed_kmh must be positive")

    attribution = raw.get("attribution", "")
    if not isinstance(attribution, str):
        raise CityProfileError("attribution must be a string")

    return {
        "schema_version": SCHEMA_VERSION,
        "name": str(raw.get("name", "")),
        "locations": locations,
        "default_trip": {"source": source, "destination": destination},
        "ignored_routes": list(ignored),
        "route_labels": dict(route_labels),
        "map": {"centre": centre, "zoom": zoom},
        "intersections": intersections,
        "report_points": report_points,
        "avg_speed_kmh": speed,
        "attribution": attribution,
    }


def find_location(locations: list[dict], text: Any) -> dict | None:
    """The location whose name or desc equals `text` exactly (the GPX matching rule)."""
    if not isinstance(text, str) or not text:
        return None
    for loc in locations:
        if text in (loc["name"], loc.get("desc")):
            return loc
    return None


def load(path: Path) -> dict:
    """Read and validate a city profile file."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise CityProfileError(
            f"no city profile at {path}. Every data directory needs a city_profile.json "
            "(see 'Running in another city' in the README)."
        ) from None
    except json.JSONDecodeError as e:
        raise CityProfileError(f"{path} is not valid JSON: {e}") from None
    try:
        return normalise(raw)
    except CityProfileError as e:
        raise CityProfileError(f"{path}: {e}") from None
