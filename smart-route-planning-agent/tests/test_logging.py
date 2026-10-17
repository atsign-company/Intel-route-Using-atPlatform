#!/usr/bin/env python3
"""
Test script to verify logging functionality in the route agent.

Runs the whole LangGraph plan (direct -> static optimizers) on the synthetic
Two Town data directory (tests/fixtures/twotown, selected in conftest.py).
"""

import logging

from agents.route_planner import RoutePlanner
from config import DEFAULT_TRIP


def test_route_agent(caplog) -> None:
    """Test the route agent with logging"""
    caplog.set_level(logging.INFO)
    planner = RoutePlanner()

    source, destination = DEFAULT_TRIP
    route_state = planner.plan_route(source=source, destination=destination)

    print("\n" + "=" * 50)
    print("ROUTE INFO:")
    print(f"Direct Route: {route_state.get('direct_route', {})}")
    print(f"Optimal Route: {route_state.get('optimal_route', {})}")
    print(f"Is Sub-Optimal: {route_state.get('is_sub_optimal', False)}")
    print("=" * 50)

    assert route_state["direct_route"]["route_name"] == "twotown-direct.gpx"
    assert route_state["direct_route"]["distance"] > 0
    assert f"Planning route from {source} to {destination}" in caplog.text
    assert "Finding direct shortest route" in caplog.text
