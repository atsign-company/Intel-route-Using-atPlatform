#!/usr/bin/env python3
# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Long-running planner service (the real backend for the live stack).

Subscribes to `smartroute` (cache + policy enforcement, default-deny), and on a
timer runs Intel's unmodified realtime node over the cache, then PUSHES the
optimal route to the commuter and status to the operator. Trigger a reroute with
`scripts/trigger_incident.py`. Unlike `planner_run.py`, this does NOT publish its
own policy — it relies on the running policy engine, so it composes with the stack.

A commuter changes the trip with a `request` record, {"source": ..., "destination": ...},
honoured when both ends are locations in the city profile.

Run:  python scripts/planner_service.py
"""
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "smart-route-planning-agent", "src"))

from config import IGNORED_ROUTES, route_label  # noqa: E402
from agents.route_planner import RoutePlanner  # noqa: E402
from atsign import roles, wire, cache, messages  # noqa: E402
from atsign.trip import Trip  # noqa: E402
from atsign.atsign_io import AtPublisher, AtSubscriber  # noqa: E402

POLICY = roles.atsign_for("policy")
ALLOW: set = set()
_policy_at = [0.0]  # monotonic time of the last policy record; 0 = never received one
_denied_seen: dict = {}  # source -> last-logged monotonic time (throttle denial spam)
# The engine republishes every 30s, so nothing for this long means this planner is
# enforcing a rule set the engine no longer holds.
POLICY_STALE_S = 90.0

# The trip being planned: the city profile's default_trip until a commuter requests
# another (both ends must be profile locations, else the request is ignored).
TRIP = Trip()
RP = None  # the RoutePlanner, set in main() before the subscriber starts


def on_record(frm, key, value, raw):
    kn = wire.key_name_from_atkey(key)
    if kn == "request":
        # A commuter asking for a trip. Not a data feed, so not subject to the publisher
        # policy; only commuter atSigns may change the trip.
        if not roles.role_for_atsign(frm).startswith("commuter"):
            print(f"[planner-service] ignored trip request from {frm} (not a commuter)", flush=True)
        elif TRIP.request(value, has_route=_has_route):
            src, dst = TRIP.get()
            print(f"[planner-service] trip set by {frm}: {src} -> {dst}", flush=True)
        else:
            print(f"[planner-service] ignored trip request from {frm}: {value!r} "
                  "(both ends must be city-profile locations joined by a route)", flush=True)
        return
    if kn == "policy":
        if frm == POLICY:
            _policy_at[0] = time.monotonic()
            new_allow = set(json.loads(value).get("grants", []))
            revoked = ALLOW - new_allow
            ALLOW.clear()
            ALLOW.update(new_allow)
            # Purge cached data from any just-revoked publisher so revocation takes
            # effect this cycle — otherwise its incident lingers until TTL and the
            # planner keeps rerouting on data from a now-denied source (flicker).
            for src in revoked:
                dropped = cache.drop_source(src)
                print(f"[planner-service] policy revoked {src}; purged {dropped} cached record(s)")
            print(f"[planner-service] policy applied; ALLOW = {sorted(ALLOW)}", flush=True)
        return
    if frm not in ALLOW:
        # default-deny: record from a non-granted publisher. Log (throttled per source)
        # so enforcement is VISIBLE instead of a silent drop.
        now = time.monotonic()
        if now - _denied_seen.get(frm, 0) > 10:
            _denied_seen[frm] = now
            # Say how old the rule set is. A denial against a stale policy looks identical
            # to a correct one, which is exactly how a dead or unheard engine hides.
            if not _policy_at[0]:
                provenance = "no policy has ever been received"
            else:
                age = int(now - _policy_at[0])
                provenance = f"policy is {age}s old, {len(ALLOW)} publisher(s) granted"
                if age > POLICY_STALE_S:
                    provenance += (" — STALE: the engine publishes every 30s, so this "
                                   "denial may be wrong; check the policy engine")
            print(f"[planner-service] DENIED {kn} from {frm} "
                  f"(not granted — dropped; {provenance})", flush=True)
        return
    if kn == "live_traffic":
        cache.put_live_traffic(frm, wire.decode(kn, value))
    elif kn in ("weather", "traffic_trends", "planned_events"):
        cache.put_condition(kn, frm, wire.decode(kn, value))


def _has_route(src, dst):
    return bool(RP and RP._find_new_shortest_available_route(src, dst, list(IGNORED_ROUTES))[0])


def main():
    global RP
    me = roles.atsign_for("planner")
    RP = rp = RoutePlanner()
    threading.Thread(
        target=lambda: AtSubscriber(me, roles.namespace(), on_record).start(), daemon=True
    ).start()
    time.sleep(6)  # let the @alpha connection establish before opening a 2nd client (avoids a root-conn race)
    pub = AtPublisher(me)
    src, dst = TRIP.get()
    print(f"[planner-service] {me} running; planning every 8s, pushing to commuter+operator; trip {src} -> {dst}")
    last = None
    no_route_for = None

    while True:
        time.sleep(8)
        try:
            src, dst = TRIP.get()
            shortest, dist = rp._find_new_shortest_available_route(src, dst, list(IGNORED_ROUTES))
            if not shortest:
                if no_route_for != (src, dst):
                    print(f"[planner-service] no route from {src} to {dst} in the data directory")
                    no_route_for = (src, dst)
                continue
            no_route_for = None
            state = {
                "source": src, "destination": dst,
                "optimal_route": {"route_name": shortest, "distance": dist},
                "no_fly_list": list(IGNORED_ROUTES),
            }
            # Reset Intel's cross-call buffer so each cycle reflects only the current cache
            # (avoids stale-incident flapping when calling the node in a loop).
            rp.live_traffic_status_list = []
            result = rp.update_optimal_route_realtime(state)
            chosen = result["optimal_route"].get("route_name") or shortest
            cdist = result["optimal_route"].get("distance", dist)
            lt = result.get("live_traffic", {})
            rerouted = bool(lt) and chosen != shortest
            reason = (
                f"Severe congestion at {lt.get('intersection_name')} (density {lt.get('traffic_density')})"
                if rerouted else "No incidents on the optimal route"
            )
            pts = messages.route_points(chosen)
            pub.notify(roles.atsign_for("commuter01"), "route", messages.RoutePush(
                route_name=chosen, route_label=route_label(chosen), distance_km=cdist, reason=reason,
                rerouted=rerouted, points=pts,
            ).model_dump_json())
            pub.notify(roles.atsign_for("operator"), "status", messages.StatusPush(
                optimal_route=chosen, route_label=route_label(chosen), distance_km=cdist, reason=reason,
                rerouted=rerouted,
                agent_status="Active - rerouted" if rerouted else "Active - monitoring",
                intersections=[{"name": lt.get("intersection_name"), "density": lt.get("traffic_density")}] if lt else [],
                points=pts,
            ).model_dump_json())
            if (src, dst, chosen) != last:
                print(f"[planner-service] {src} -> {dst}: optimal={chosen} rerouted={rerouted} ({reason})")
                last = (src, dst, chosen)
        except Exception as e:
            print(f"[planner-service] loop error: {e}")


if __name__ == "__main__":
    main()
