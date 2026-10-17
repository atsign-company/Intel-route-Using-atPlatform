# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
The planner's rules on a synthetic two-route city (tests/fixtures/twotown):

  twotown-direct.gpx  Alpha Town -> Beta Town, the shortest offered route (primary)
  twotown-detour.gpx  Alpha Town -> Beta Town, a longer detour (the alternative)
  twotown-closed.gpx  Alpha Town -> Beta Town, shortest of all but in ignored_routes

The intersection "Main St & Middle Rd" sits on a trackpoint of the primary only.
"""
import time

import pytest

from agents.route_planner import RoutePlanner
from atsign import cache
from config import DEFAULT_TRIP, IGNORED_ROUTES, INTERSECTIONS, IncidentStatus, WeatherStatus
from controllers.threshold import ThresholdController
from schema import GeoCoordinates, LiveTrafficData

PRIMARY = "twotown-direct.gpx"
ALTERNATIVE = "twotown-detour.gpx"
SRC, DST = DEFAULT_TRIP
NAME, LAT, LON = INTERSECTIONS["intxn_main"]
CONGESTED = ThresholdController.TRAFFIC_DENSITY_THRESHOLD + 20


@pytest.fixture
def planner():
    return RoutePlanner()


def _report(lat, lon, density, name=NAME, source="@intxn_main"):
    cache.put_live_traffic(source, LiveTrafficData(
        location_coordinates=GeoCoordinates(latitude=lat, longitude=lon),
        intersection_name=name,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        traffic_density=density,
        traffic_description=f"{name}: density {density}",
        weather_status=WeatherStatus.CLEAR,
        incident_status=IncidentStatus.CROWDING if density > 12 else IncidentStatus.CLEAR,
    ))


def _realtime(planner):
    """What scripts/planner_service.py does each cycle."""
    shortest, dist = planner._find_new_shortest_available_route(SRC, DST, list(IGNORED_ROUTES))
    planner.live_traffic_status_list = []
    return planner.update_optimal_route_realtime({
        "source": SRC, "destination": DST,
        "optimal_route": {"route_name": shortest, "distance": dist},
        "no_fly_list": list(IGNORED_ROUTES),
    })


# ---- route choice -------------------------------------------------------------
def test_primary_is_the_strictly_shortest_offered_route(planner):
    primary, primary_km = planner._find_new_shortest_available_route(SRC, DST, IGNORED_ROUTES)
    alternative, alternative_km = planner._find_new_shortest_available_route(
        SRC, DST, IGNORED_ROUTES + [PRIMARY]
    )
    assert (primary, alternative) == (PRIMARY, ALTERNATIVE)
    assert primary_km < alternative_km


def test_ignored_routes_are_never_offered(planner):
    # twotown-closed.gpx is the shortest of all, so only ignored_routes keeps it out
    assert planner._find_new_shortest_available_route(SRC, DST, [])[0] == "twotown-closed.gpx"
    assert planner._find_new_shortest_available_route(SRC, DST, IGNORED_ROUTES)[0] == PRIMARY


@pytest.mark.parametrize("source", ["Alpha", "Alpha Town"])  # waypoint <name> or <desc>
def test_endpoints_match_waypoint_name_or_desc(planner, source):
    assert planner._find_new_shortest_available_route(source, "Beta", IGNORED_ROUTES)[0] == PRIMARY


@pytest.mark.parametrize("source", ["alpha town", "Alpha Town ", "Alpha, Town", "Gamma"])
def test_endpoints_must_match_exactly(planner, source):
    assert planner._find_new_shortest_available_route(source, DST, IGNORED_ROUTES) == ("", 0.0)


def test_direction_matters(planner):
    """Routes are matched first waypoint -> last waypoint; the reverse trip has none."""
    assert planner._find_new_shortest_available_route(DST, SRC, IGNORED_ROUTES) == ("", 0.0)


# ---- realtime reroute ---------------------------------------------------------
def test_no_live_traffic_keeps_the_primary(planner):
    result = _realtime(planner)
    assert result["optimal_route"]["route_name"] == PRIMARY
    assert result["is_sub_optimal"] is False


def test_congestion_on_the_primary_moves_the_commuter_to_the_alternative(planner):
    _report(LAT, LON, CONGESTED)
    result = _realtime(planner)
    assert result["optimal_route"]["route_name"] == ALTERNATIVE
    assert result["is_sub_optimal"] is False
    assert result["live_traffic"]["route_name"] == PRIMARY
    assert result["live_traffic"]["intersection_name"] == NAME
    assert result["live_traffic"]["traffic_density"] == CONGESTED


def test_light_traffic_on_the_primary_does_not_reroute(planner):
    _report(LAT, LON, ThresholdController.TRAFFIC_DENSITY_THRESHOLD)  # at, not above
    assert _realtime(planner)["optimal_route"]["route_name"] == PRIMARY


def test_congestion_must_be_at_an_exact_trackpoint(planner):
    """Live traffic matches trackpoints by exact float equality (proximity_factor 0)."""
    _report(LAT + 1e-6, LON, CONGESTED)
    assert _realtime(planner)["optimal_route"]["route_name"] == PRIMARY


def test_congestion_only_on_the_alternative_changes_nothing(planner):
    _report(10.04, 20.05, CONGESTED, name="Detour junction")  # a detour trackpoint
    result = _realtime(planner)
    assert result["optimal_route"]["route_name"] == PRIMARY
    assert result["is_sub_optimal"] is False


def test_congestion_everywhere_settles_on_the_least_congested_route(planner):
    _report(LAT, LON, CONGESTED + 10)
    _report(10.04, 20.05, CONGESTED, name="Detour junction", source="@intxn_detour")
    result = _realtime(planner)
    assert result["is_sub_optimal"] is True
    assert result["optimal_route"]["route_name"] == ALTERNATIVE


def test_rerouting_reverts_when_the_congestion_clears(planner):
    _report(LAT, LON, CONGESTED)
    assert _realtime(planner)["optimal_route"]["route_name"] == ALTERNATIVE
    _report(LAT, LON, 0)  # same (sender, intersection) slot: the report is replaced
    assert _realtime(planner)["optimal_route"]["route_name"] == PRIMARY
