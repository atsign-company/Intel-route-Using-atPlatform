// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// The city profile: the geography a client works in, read from configuration
// rather than code. The planner's copy is smart-route-planning-agent/src/data/
// city_profile.json (schema: city_profile.schema.json beside it). The Flutter apps
// ship a copy as assets/city_profile.json (replace it to use another city); the
// Dart CLI tools read the planner's file (--profile or SMARTROUTE_DATA_DIR).
//
// Flutter-free so it is unit-testable. The same file is in commuter_app/lib and
// dart_client/lib; keep the three identical.
import 'dart:convert';

/// A named coordinate: a location, an intersection or a report point.
class NamedPoint {
  final String name;
  final double lat;
  final double lon;

  const NamedPoint(this.name, this.lat, this.lon);

  @override
  String toString() => '$name ($lat, $lon)';
}

class CityProfile {
  final String name;

  /// Places a trip can start or end, as their labels (a GPX waypoint's desc,
  /// else its name) — exactly what the planner matches a trip request against.
  final List<NamedPoint> locations;

  final String tripSource;
  final String tripDestination;

  /// Where the map opens before a route arrives.
  final double centreLat;
  final double centreLon;
  final int zoom;

  /// Intersection publishers by atSign role.
  final Map<String, NamedPoint> intersections;

  /// Known-good report locations (trackpoints on a planned route).
  final List<NamedPoint> reportPoints;

  /// Human-readable route names, keyed by GPX file name (the route id).
  final Map<String, String> routeLabels;

  /// Credit for the route and map data.
  final String attribution;

  const CityProfile({
    required this.name,
    required this.locations,
    required this.tripSource,
    required this.tripDestination,
    required this.centreLat,
    required this.centreLon,
    required this.zoom,
    this.intersections = const {},
    this.reportPoints = const [],
    this.routeLabels = const {},
    this.attribution = '',
  });

  List<String> get locationLabels => [for (final l in locations) l.name];

  /// Report locations offered to the user, by name: the report points, then the
  /// intersections. Each value is [lat, lon].
  Map<String, List<double>> get reportPresets => {
        for (final p in [...reportPoints, ...intersections.values]) p.name: [p.lat, p.lon],
      };

  /// The human-readable name for a route id; the id itself when unlabelled.
  String routeLabel(String routeName) => routeLabels[routeName] ?? routeName;

  static CityProfile parse(String text) {
    final decoded = jsonDecode(text);
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('city profile must be a JSON object');
    }
    return CityProfile.fromJson(decoded);
  }

  /// Mirrors smart-route-planning-agent/src/city_profile.py: required fields are
  /// checked, optional ones get the same neutral defaults.
  factory CityProfile.fromJson(Map<String, dynamic> json) {
    double number(Object? v, String where) {
      if (v is num) return v.toDouble();
      throw FormatException('$where must be a number, got $v');
    }

    NamedPoint point(Object? raw, String where, {String? name}) {
      if (raw is! Map) throw FormatException('$where must be an object with lat and lon');
      final n = name ?? raw['name'];
      if (n is! String || n.isEmpty) throw FormatException('$where.name must be a string');
      return NamedPoint(n, number(raw['lat'], '$where.lat'), number(raw['lon'], '$where.lon'));
    }

    final rawLocations = json['locations'];
    if (rawLocations is! List || rawLocations.length < 2) {
      throw const FormatException('locations must list at least two places');
    }
    final locations = <NamedPoint>[];
    final aliases = <String, String>{}; // name or desc -> label
    for (var i = 0; i < rawLocations.length; i++) {
      final raw = rawLocations[i];
      final desc = raw is Map ? raw['desc'] : null;
      final label = desc is String && desc.isNotEmpty ? desc : null;
      final loc = point(raw, 'locations[$i]', name: label);
      locations.add(loc);
      aliases[loc.name] = loc.name;
      final n = (raw as Map)['name'];
      if (n is String) aliases[n] = loc.name;
    }

    final trip = json['default_trip'] is Map ? json['default_trip'] as Map : const {};
    String end(Object? text, String fallback, String key) {
      if (text == null) return fallback;
      final label = aliases[text];
      if (label == null) throw FormatException('default_trip.$key $text is not a location');
      return label;
    }

    final map = json['map'] is Map ? json['map'] as Map : const {};
    final centre = map['centre'] == null
        ? NamedPoint(
            'centre',
            locations.map((l) => l.lat).reduce((a, b) => a + b) / locations.length,
            locations.map((l) => l.lon).reduce((a, b) => a + b) / locations.length,
          )
        : point(map['centre'], 'map.centre', name: 'centre');
    final zoom = map['zoom'] ?? 10;
    if (zoom is! int) throw FormatException('map.zoom must be an integer, got $zoom');

    final rawIntersections = json['intersections'] is Map ? json['intersections'] as Map : const {};
    final rawPoints = json['report_points'] is List ? json['report_points'] as List : const [];
    final rawLabels = json['route_labels'] is Map ? json['route_labels'] as Map : const {};

    return CityProfile(
      name: json['name'] is String ? json['name'] as String : '',
      locations: locations,
      tripSource: end(trip['source'], locations.first.name, 'source'),
      tripDestination: end(trip['destination'], locations.last.name, 'destination'),
      centreLat: centre.lat,
      centreLon: centre.lon,
      zoom: zoom,
      intersections: {
        for (final e in rawIntersections.entries)
          '${e.key}': point(e.value, 'intersections.${e.key}'),
      },
      reportPoints: [
        for (var i = 0; i < rawPoints.length; i++) point(rawPoints[i], 'report_points[$i]'),
      ],
      routeLabels: {for (final e in rawLabels.entries) '${e.key}': '${e.value}'},
      attribution: json['attribution'] is String ? json['attribution'] as String : '',
    );
  }
}
