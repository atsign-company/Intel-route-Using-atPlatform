# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from enum import Enum
from pathlib import Path

import city_profile

# Configs and Constants for the Route Planner Application
#
# Geography is data, not code. Everything city-specific comes from the data
# directory: routes/*.gpx, csv/*.csv, config.json and city_profile.json. It
# defaults to ./data next to this file (the San Francisco Bay Area profile the
# project has always shipped); SMARTROUTE_DATA_DIR points it somewhere else.

DATA_DIR: Path = Path(
    os.environ.get("SMARTROUTE_DATA_DIR") or Path(__file__).parent / "data"
).resolve()

# Directory where GPX files reside. A route's id is its file name.
GPX_DIR: Path = DATA_DIR / "routes"

# Directory where route status (Weather, traffic, etc. ) data is stored
ROUTE_STATUS_DIR: Path = DATA_DIR / "csv"
CONFIG_FILE: Path = DATA_DIR / "config.json"
CITY_PROFILE_FILE: Path = DATA_DIR / "city_profile.json"

CITY_PROFILE: dict = city_profile.load(CITY_PROFILE_FILE)

# Every place a trip can start or end, by label: the GPX endpoint waypoint's
# <desc>, or its <name> when it has no <desc>.
DEFAULT_LOCATIONS: list[str] = [
    city_profile.location_label(loc) for loc in CITY_PROFILE["locations"]
]

# Coordinates mapping for locations
DEFAULT_LOCATION_COORDINATES: dict[str, list[float]] = {
    city_profile.location_label(loc): [loc["lat"], loc["lon"]]
    for loc in CITY_PROFILE["locations"]
}

# The trip planned until somebody asks for another one: (source, destination).
DEFAULT_TRIP: tuple[str, str] = (
    CITY_PROFILE["default_trip"]["source"],
    CITY_PROFILE["default_trip"]["destination"],
)

# Routes (GPX file names) the planner never offers.
IGNORED_ROUTES: list[str] = list(CITY_PROFILE["ignored_routes"])

# Human-readable names for routes, keyed by GPX file name.
ROUTE_LABELS: dict[str, str] = dict(CITY_PROFILE["route_labels"])

# Where maps open when there is no route to fit them to.
MAP_CENTRE: tuple[float, float] = (
    CITY_PROFILE["map"]["centre"]["lat"],
    CITY_PROFILE["map"]["centre"]["lon"],
)
MAP_ZOOM: int = CITY_PROFILE["map"]["zoom"]

# Intersection publishers by atSign role: role -> (name, lat, lon).
INTERSECTIONS: dict[str, tuple[str, float, float]] = {
    role: (spec["name"], spec["lat"], spec["lon"])
    for role, spec in CITY_PROFILE["intersections"].items()
}

# Average speed for travel-time estimates.
AVG_SPEED_KMH: float = CITY_PROFILE["avg_speed_kmh"]

# Credit for the route/map data (e.g. OpenStreetMap's ODbL notice).
ATTRIBUTION: str = CITY_PROFILE["attribution"]


def find_location(text: str) -> str | None:
    """Label of the profile location named `text` (its <name> or <desc>), else None."""
    loc = city_profile.find_location(CITY_PROFILE["locations"], text)
    return city_profile.location_label(loc) if loc else None


def route_label(route_name: str) -> str:
    """Human-readable name for a route id (GPX file name); the id itself if unlabelled."""
    return ROUTE_LABELS.get(route_name, route_name)


class CongestionLevel(Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"
    SEVERE = "Severe"


class IncidentStatus(Enum):
    CLEAR = "clear"
    ACCIDENT = "accident"
    CROWDING = "crowding"
    ROADBLOCK = "roadblock"
    MAINTENANCE = "maintenance"


class WeatherStatus(Enum):
    SUNNY = "sunny"
    CLOUDY = "cloudy"
    FOG = "fog"
    RAINY = "rain"
    SNOWY = "snow"
    CLEAR = "Clear"
    STORMY = "Severe thunderstorms"
    FIRE = "Roadside Fire"
    FLOOD = "Flash Floods"

    # Add a generic handler here so that any unknown weather status maps to CLEAR
    @classmethod
    def _missing_(cls, _):
        return cls.CLEAR


# Weather conditions that trigger alternate route search
ADVERSE_WEATHER_CONDITIONS = [
    WeatherStatus.FOG,
    WeatherStatus.RAINY,
    WeatherStatus.STORMY,
    WeatherStatus.SNOWY,
    WeatherStatus.FIRE,
    WeatherStatus.FLOOD,
]


class StaticOptimizerName(Enum):
    """
    An Enum to id all static route optimizers
    """

    TRAFFIC = "traffic_trend"
    WEATHER = "weather_conditions"
    PLANNED_EVENTS = "planned_events"

    # add a method which returns a detailed description of the optimizer
    def get_description(self) -> str:
        descriptions = {
            StaticOptimizerName.TRAFFIC: "Historical Traffic Trends",
            StaticOptimizerName.WEATHER: "Weather Conditions",
            StaticOptimizerName.PLANNED_EVENTS: "Planned Events",
        }
        return descriptions.get(self, "No description available.")


STATIC_ROUTE_OPTIMIZER_STACK: list[StaticOptimizerName] = [
    StaticOptimizerName.PLANNED_EVENTS,
    StaticOptimizerName.WEATHER,
    StaticOptimizerName.TRAFFIC,
]


class PlannerNode(Enum):
    """
    An Enum to identify all planning nodes
    """

    DIRECT = "direct_route_planner"
    OPTIMAL = "optimal_route_planner"
    REALTIME = "realtime_route_planner"


# Map styling
MAP_COLORS = {
    "main_route": "#4285F4",
    "optimal_route": "#13B513",
    "start_marker": "#0AB438",
    "blocked_routes_valid": "#FF0000",
    "blocked_routes_invalid": "#BB8B08",
    "route_incident": "#FA1B07",
    "no_incident": "#193A58",
    "end_marker": "#FF9D00",
    "waypoint": "#A47C02",
    "non_optimal_route_direct": "#9C9B9B",
    "non_optimal_route": "#726565",
}

# UI constants
APP_DETAILS = """# Welcome to Agentic AI Route Planning

## Select your start and end locations, then click 'Find Route' to begin route planning.

### The AI agent will:
 1. Analyse the shortest route between source and destination and load it.
 2. Analyze planned events, historical traffic trends and weather conditions along the shortest route and load an alternate optimized route, if needed.
 3. Continously monitor the live traffic conditions on the optimized route and update the route as needed in real-time.
"""

INITIAL_MAP_HTML = "<div style='text-align: center; padding: 50px; font-size: 18px; color: #666;'>Select locations and click 'Find Route' to see the route map</div>"
