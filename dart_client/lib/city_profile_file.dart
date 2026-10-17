// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// Finds and loads the city profile for the CLI tools — the same file the planner
// reads, so a tool and the planner always agree on the geography.
import 'dart:io';

import 'city_profile.dart';

export 'city_profile.dart';

/// Order: --profile, $SMARTROUTE_DATA_DIR/city_profile.json, then the planner's
/// bundled profile relative to the cwd, the script and the executable.
File findCityProfile(String? explicit) {
  const rel = 'smart-route-planning-agent/src/data/city_profile.json';
  final dataDir = Platform.environment['SMARTROUTE_DATA_DIR'] ?? '';
  final scriptDir = File.fromUri(Platform.script).parent.path;
  final exeDir = File(Platform.resolvedExecutable).parent.path;
  final candidates = <String>[
    if (explicit != null && explicit.isNotEmpty) explicit,
    if (dataDir.isNotEmpty) '$dataDir/city_profile.json',
    rel, // cwd == repo root
    '../$rel', // cwd == dart_client
    '$scriptDir/../../$rel', // dart run: bin/ -> repo
    '$exeDir/$rel',
    '$exeDir/../$rel',
  ];
  // An explicit or env-selected profile must exist: falling back to the bundled
  // city would silently report from the wrong place.
  final pinned = (explicit != null && explicit.isNotEmpty) || dataDir.isNotEmpty;
  for (final p in pinned ? candidates.take(1) : candidates) {
    if (File(p).existsSync()) return File(p);
  }
  throw StateError('Could not find the city profile. Set --profile <path> or '
      'SMARTROUTE_DATA_DIR, or run from the repo. Tried:\n  '
      '${(pinned ? candidates.take(1) : candidates).join("\n  ")}');
}

CityProfile loadCityProfile(String? explicit) =>
    CityProfile.parse(findCityProfile(explicit).readAsStringSync());
