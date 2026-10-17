# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""The commuter's trip request and the intersection publisher's location, from the profile."""
import json

import pytest

from atsign.publishers.intersection import resolve_location
from atsign.trip import Trip, parse_request


# ---- trip requests (scripts/planner_service.py) --------------------------------
def test_trip_starts_as_the_profile_default():
    assert Trip().get() == ("Alpha Town", "Beta Town")


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"source": "Alpha Town", "destination": "Gamma"}, ("Alpha Town", "Gamma")),
        ({"source": "Beta", "destination": "Alpha"}, ("Beta Town", "Alpha Town")),  # by <name>
    ],
)
def test_requests_naming_profile_locations_are_honoured(payload, expected):
    trip = Trip()
    assert trip.request(json.dumps(payload)) == expected
    assert trip.get() == expected


@pytest.mark.parametrize(
    "value",
    [
        json.dumps({"source": "Alpha Town", "destination": "Nowhere"}),
        json.dumps({"source": "alpha town", "destination": "Beta Town"}),
        json.dumps({"source": "Alpha Town", "destination": "Alpha"}),  # same place
        json.dumps({"source": "Alpha Town"}),
        json.dumps(["Alpha Town", "Beta Town"]),
        "not json",
        None,
    ],
)
def test_other_requests_are_ignored_and_the_trip_stands(value):
    trip = Trip()
    assert trip.request(value) is None
    assert trip.get() == ("Alpha Town", "Beta Town")
    assert parse_request(value) is None


def test_a_trip_without_a_route_is_ignored():
    from agents.route_planner import RoutePlanner
    from config import IGNORED_ROUTES

    rp = RoutePlanner()

    def has_route(src, dst):
        return bool(rp._find_new_shortest_available_route(src, dst, IGNORED_ROUTES)[0])

    trip = Trip()
    # both are profile locations, but every route runs Alpha -> Beta
    assert trip.request(json.dumps({"source": "Beta Town", "destination": "Alpha Town"}),
                        has_route=has_route) is None
    assert trip.get() == ("Alpha Town", "Beta Town")
    assert trip.request(json.dumps({"source": "Alpha", "destination": "Beta"}),
                        has_route=has_route) == ("Alpha Town", "Beta Town")


# ---- intersection publisher ------------------------------------------------------
def test_intersection_location_comes_from_the_profile():
    assert resolve_location("intxn_main", env={}) == ("Main St & Middle Rd", 10.002, 20.05)


def test_arguments_override_the_profile():
    assert resolve_location("intxn_main", name="Elsewhere", lat=1.5, env={}) == (
        "Elsewhere", 1.5, 20.05)


def test_environment_overrides_the_profile():
    env = {"SMARTROUTE_INTERSECTION_NAME": "Env St", "SMARTROUTE_INTERSECTION_LAT": "3.25",
           "SMARTROUTE_INTERSECTION_LON": "4.5"}
    assert resolve_location("intxn_main", env=env) == ("Env St", 3.25, 4.5)
    # explicit arguments still win over the environment
    assert resolve_location("intxn_main", lat=9.0, env=env) == ("Env St", 9.0, 4.5)


def test_a_role_missing_from_the_profile_needs_coordinates():
    with pytest.raises(SystemExit, match="not in"):
        resolve_location("intxn_market_st", env={})
    assert resolve_location("intxn_market_st", lat=1.0, lon=2.0, env={}) == (
        "intxn_market_st", 1.0, 2.0)
