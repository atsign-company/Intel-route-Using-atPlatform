# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Intersection agent publisher (demo) — stands in for a Smart Traffic Intersection
running Scene Intelligence. Publishes `live_traffic.smartroute` (LiveTrafficData)
to the planner, cycling vehicle density so the planner sees reroute-worthy values.

Where the intersection is comes from the city profile's `intersections` (keyed by
role). --name/--lat/--lon, or SMARTROUTE_INTERSECTION_NAME/_LAT/_LON, override it;
with both coordinates given, the role need not be in the profile at all.

Run (keys in $HOME/.atsign/keys):
    python -m atsign.publishers.intersection --role intxn_market_st --count 5
"""
import argparse
import os
import sys
import time

from schema import GeoCoordinates, LiveTrafficData
from config import CITY_PROFILE_FILE, INTERSECTIONS, IncidentStatus, WeatherStatus
from atsign import roles, wire

DENSITIES = [3, 6, 9, 14, 22, 30]


def resolve_location(role, name=None, lat=None, lon=None, env=None):
    """(name, lat, lon) for `role`: explicit values, then env, then the city profile."""
    env = os.environ if env is None else env
    name = name or env.get("SMARTROUTE_INTERSECTION_NAME") or None
    lat = lat if lat is not None else _float(env.get("SMARTROUTE_INTERSECTION_LAT"))
    lon = lon if lon is not None else _float(env.get("SMARTROUTE_INTERSECTION_LON"))
    base = INTERSECTIONS.get(role)
    if base is None and (lat is None or lon is None):
        known = ", ".join(sorted(INTERSECTIONS)) or "none"
        raise SystemExit(
            f"intersection role {role!r} is not in {CITY_PROFILE_FILE} (known: {known}); "
            "add it under 'intersections' or pass --lat and --lon"
        )
    base_name, base_lat, base_lon = base or (role, None, None)
    return (
        name or base_name,
        lat if lat is not None else base_lat,
        lon if lon is not None else base_lon,
    )


def _float(text):
    return float(text) if text not in (None, "") else None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, help="intersection atSign role, e.g. intxn_market_st")
    ap.add_argument("--name", help="intersection name (default: from the city profile)")
    ap.add_argument("--lat", type=float, help="latitude (default: from the city profile)")
    ap.add_argument("--lon", type=float, help="longitude (default: from the city profile)")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    name, lat, lon = resolve_location(args.role, args.name, args.lat, args.lon)

    from atsign.atsign_io import AtPublisher  # needs atsdk; imported only to publish

    me = roles.atsign_for(args.role)
    planner = roles.atsign_for("planner")
    pub = AtPublisher(me, verbose=args.verbose)
    print(f"[{args.role}] {me} -> {planner} publishing live_traffic.{roles.namespace()} "
          f"as {name!r} at ({lat}, {lon})")

    for i in range(args.count):
        density = DENSITIES[min(i, len(DENSITIES) - 1)]
        rec = LiveTrafficData(
            location_coordinates=GeoCoordinates(latitude=lat, longitude=lon),
            intersection_name=name,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            traffic_density=density,
            traffic_description=f"{name}: density {density}",
            weather_status=WeatherStatus.FLOOD if density > 20 else WeatherStatus.CLEAR,
            incident_status=IncidentStatus.CROWDING if density > 12 else IncidentStatus.CLEAR,
        )
        resp = pub.notify(planner, "live_traffic", wire.encode(rec))
        print(f"[{args.role}] sent #{i + 1}/{args.count} density={density} -> {resp}")
        if i < args.count - 1:
            time.sleep(args.interval)
    print(f"[{args.role}] done.")


if __name__ == "__main__":
    main(sys.argv[1:])
