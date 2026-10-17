# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
The trip the planner service plans: the city profile's default_trip until a
commuter asks for another with a `request.smartroute` record, {source, destination}.

A request is honoured only when both ends name locations in the city profile (by
the GPX waypoint <name> or <desc>, the same exact rule the route planner matches
on) and differ, and the planner has a route between them; anything else is ignored
and the current trip stands.
"""
import json
import threading
from typing import Callable, Optional, Tuple

from config import DEFAULT_TRIP, find_location


def parse_request(value) -> Optional[Tuple[str, str]]:
    """(source, destination) labels from a request payload, or None if not honourable."""
    try:
        data = json.loads(value) if isinstance(value, (str, bytes)) else value
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    source = find_location(data.get("source"))
    destination = find_location(data.get("destination"))
    if not source or not destination or source == destination:
        return None
    return source, destination


class Trip:
    """Thread-safe current trip: the subscriber thread writes, the planning loop reads."""

    def __init__(self, source: str = DEFAULT_TRIP[0], destination: str = DEFAULT_TRIP[1]):
        self._lock = threading.Lock()
        self._trip = (source, destination)

    def get(self) -> Tuple[str, str]:
        with self._lock:
            return self._trip

    def request(
        self, value, has_route: Optional[Callable[[str, str], bool]] = None
    ) -> Optional[Tuple[str, str]]:
        """Apply a commuter's request. Returns the new trip, or None if it was ignored.

        `has_route(source, destination)`, when given, must also be true: a trip with no
        GPX route would leave the commuter with nothing, so the current one stands.
        """
        trip = parse_request(value)
        if trip and has_route is not None and not has_route(*trip):
            return None
        if trip:
            with self._lock:
                self._trip = trip
        return trip
