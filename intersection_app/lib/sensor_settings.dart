// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// Everything the operator configures, as one serialisable value.
//
// Flutter-free so the encoding is unit-testable; the atSign I/O lives in
// settings_store.dart.
import 'dart:convert';

import 'city_profile.dart';
import 'traffic_report.dart';

class SensorSettings {
  final IntersectionConfig config;

  /// Which entry of [CityProfile.reportPresets] the location came from, so the picker can
  /// restore the same selection (the coordinates live in [config]).
  final String preset;

  final int intervalSeconds;

  /// Only count objects while the labeler recognises a vehicle.
  final bool gateOnly;

  /// Minimum confidence for a detection to count.
  final double minConfidence;

  const SensorSettings({
    this.config = const IntersectionConfig(),
    this.preset = '',
    this.intervalSeconds = 5,
    this.gateOnly = true,
    this.minConfidence = 0.30,
  });

  /// First-run settings for a city: report from its first preset location (a
  /// report point, else an intersection), so no geography is baked into the app.
  factory SensorSettings.forProfile(CityProfile profile) {
    final presets = profile.reportPresets;
    if (presets.isEmpty) return const SensorSettings();
    final first = presets.entries.first;
    return SensorSettings(
      config: IntersectionConfig(latitude: first.value[0], longitude: first.value[1]),
      preset: first.key,
    );
  }

  Map<String, dynamic> toJson() => {
        'plannerAtSign': config.plannerAtSign,
        'intersectionName': config.intersectionName,
        'latitude': config.latitude,
        'longitude': config.longitude,
        'densityPerCar': config.densityPerCar,
        'ttlMillis': config.ttlMillis,
        'preset': preset,
        'intervalSeconds': intervalSeconds,
        'gateOnly': gateOnly,
        'minConfidence': minConfidence,
      };

  String encode() => jsonEncode(toJson());

  /// Rebuild from stored JSON. Anything missing or malformed falls back to that
  /// field of [fallback] (normally [SensorSettings.forProfile]) rather than losing
  /// the whole configuration.
  static SensorSettings fromJson(Map<String, dynamic> json,
      {SensorSettings fallback = const SensorSettings()}) {
    T pick<T>(String key, T defaultValue) {
      final value = json[key];
      return value is T ? value : defaultValue;
    }

    // ints/doubles arrive from JSON as num
    double number(String key, double defaultValue) {
      final value = json[key];
      return value is num ? value.toDouble() : defaultValue;
    }

    int integer(String key, int defaultValue) {
      final value = json[key];
      return value is num ? value.toInt() : defaultValue;
    }

    return SensorSettings(
      config: IntersectionConfig(
        plannerAtSign: pick('plannerAtSign', fallback.config.plannerAtSign),
        intersectionName: pick('intersectionName', fallback.config.intersectionName),
        latitude: number('latitude', fallback.config.latitude),
        longitude: number('longitude', fallback.config.longitude),
        densityPerCar: integer('densityPerCar', fallback.config.densityPerCar),
        ttlMillis: integer('ttlMillis', fallback.config.ttlMillis),
      ),
      preset: pick('preset', fallback.preset),
      intervalSeconds: integer('intervalSeconds', fallback.intervalSeconds),
      gateOnly: pick('gateOnly', fallback.gateOnly),
      minConfidence: number('minConfidence', fallback.minConfidence),
    );
  }

  /// Decode stored text; returns [fallback] if it is absent or unreadable.
  static SensorSettings decode(String? text,
      {SensorSettings fallback = const SensorSettings()}) {
    if (text == null || text.trim().isEmpty) return fallback;
    try {
      final decoded = jsonDecode(text);
      if (decoded is! Map<String, dynamic>) return fallback;
      return fromJson(decoded, fallback: fallback);
    } catch (_) {
      return fallback;
    }
  }
}
