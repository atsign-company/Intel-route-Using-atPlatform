// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// The wire contract for a traffic report. Deliberately identical to
// dart_client/bin/change_route.dart (verified end-to-end against the planner):
// a `live_traffic.smartroute` record, encrypted to the planner atSign, TTL 60s.
//
// Flutter-free on purpose, so the payload logic is unit-testable without a device.
import 'dart:convert';

import 'package:at_client/at_client.dart';

/// Where this phone is pretending to be, and who to report to.
class IntersectionConfig {
  /// Name of the intersection. The planner caches by (sender, intersection_name),
  /// so a distinct name is its own cache slot.
  final String intersectionName;

  /// Must be ON the planner's current route for a reroute to occur — the planner
  /// only reacts to congestion at a trackpoint of the route it is considering.
  /// There is no geographic default here: the app starts from the city profile's
  /// first report location (see [SensorSettings.forProfile]).
  final double latitude;
  final double longitude;

  /// The planner's atSign (profile-dependent: @alpha in the EE, your @…_planner
  /// in production).
  final String plannerAtSign;

  /// Reported density = detected cars x densityPerCar. The planner reroutes above
  /// its threshold of 10, so a handful of model cars needs a multiplier to matter.
  final int densityPerCar;

  /// Record lifetime. After this the planner's cache drops it and the route
  /// reverts on its own — the same self-clearing behaviour as the CLI tool.
  final int ttlMillis;

  const IntersectionConfig({
    this.intersectionName = 'Model intersection (phone)',
    this.latitude = 0.0,
    this.longitude = 0.0,
    this.plannerAtSign = '@smartroute_planner',
    this.densityPerCar = 15,
    this.ttlMillis = 60000,
  });

  IntersectionConfig copyWith({
    String? intersectionName,
    double? latitude,
    double? longitude,
    String? plannerAtSign,
    int? densityPerCar,
    int? ttlMillis,
  }) {
    return IntersectionConfig(
      intersectionName: intersectionName ?? this.intersectionName,
      latitude: latitude ?? this.latitude,
      longitude: longitude ?? this.longitude,
      plannerAtSign: plannerAtSign ?? this.plannerAtSign,
      densityPerCar: densityPerCar ?? this.densityPerCar,
      ttlMillis: ttlMillis ?? this.ttlMillis,
    );
  }
}

/// Builds and sends `live_traffic` records as this device's atSign.
class TrafficReporter {
  final AtClient atClient;
  final String namespace;

  TrafficReporter(this.atClient, {this.namespace = 'smartroute'});

  /// The record's key: shared from us to the planner, expiring after the TTL.
  AtKey buildKey(IntersectionConfig config, String me) {
    return AtKey()
      ..key = 'live_traffic'
      ..namespace = namespace
      ..sharedBy = me
      ..sharedWith = config.plannerAtSign
      ..metadata = (Metadata()..ttl = config.ttlMillis);
  }

  /// The payload — Intel's LiveTrafficData shape, which the planner's Pydantic
  /// model parses unchanged.
  String buildPayload(IntersectionConfig config, int density, {DateTime? now}) {
    return jsonEncode({
      'location_coordinates': {
        'latitude': config.latitude,
        'longitude': config.longitude,
      },
      'intersection_name': config.intersectionName,
      'timestamp': (now ?? DateTime.now()).toIso8601String(),
      'traffic_density': density,
      'traffic_description': 'on-device detection: $density vehicles',
      'weather_status': 'Clear',
      'incident_status': density > 12 ? 'crowding' : 'clear',
    });
  }

  /// Reported density for a number of detected cars.
  int densityFor(IntersectionConfig config, int cars) => cars * config.densityPerCar;

  /// Publish one report. Returns the notification status for display.
  Future<NotificationResult> send(IntersectionConfig config, int density) {
    final me = atClient.getCurrentAtSign()!;
    final key = buildKey(config, me);
    final payload = buildPayload(config, density);
    return atClient.notificationService
        .notify(NotificationParams.forUpdate(key, value: payload));
  }
}
