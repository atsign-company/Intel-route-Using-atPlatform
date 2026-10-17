// Cross-language interop spike — Dart publisher.
// Sends a LiveTrafficData-shaped notification to a target atSign (default @alpha).
// Run (keys in $HOME/.atsign/keys):
//   dart run bin/dart_publisher.dart --atsign @bravo --root-domain vip.ve.atsign.zone --to @alpha -v
import 'dart:convert';
import 'dart:io';
import 'package:at_client/at_client.dart';
import 'package:at_cli_commons/at_cli_commons.dart';
import 'package:interop_dart/city_profile_file.dart';

Future<void> main(List<String> args) async {
  final parser = CLIBase.createArgsParser(namespace: 'smartroute')
    ..addOption('to', help: 'recipient atSign', defaultsTo: '@alpha')
    ..addOption('profile',
        help: r"city_profile.json (default: $SMARTROUTE_DATA_DIR/city_profile.json, else the planner's bundled one)")
    ..addOption('intersection',
        help: 'intersection role in the city profile (default: intxn_market_st, else the first)');
  final cli = await CLIBase.fromCommandLineArgs(args, parser: parser, namespace: 'smartroute');
  final atClient = cli.atClient;
  final me = atClient.getCurrentAtSign()!;
  final a = parser.parse(args);
  final to = a['to'] as String;

  final intersections = loadCityProfile(a['profile'] as String?).intersections;
  final role = (a['intersection'] as String?) ??
      (intersections.containsKey('intxn_market_st') ? 'intxn_market_st' : intersections.keys.firstOrNull);
  final at = intersections[role];
  if (at == null) {
    stderr.writeln('[dart-pub] no intersection $role in the city profile');
    exit(2);
  }

  final key = AtKey()
    ..key = 'live_traffic'
    ..namespace = 'smartroute'
    ..sharedBy = me
    ..sharedWith = to
    ..metadata = (Metadata()..ttl = 60000);

  final payload = jsonEncode({
    'location_coordinates': {'latitude': at.lat, 'longitude': at.lon},
    'intersection_name': '${at.name} (from Dart)',
    'timestamp': DateTime.now().toIso8601String(),
    'traffic_density': 17,
    'traffic_description': 'sent by Dart at_client',
    'weather_status': 'Clear',
    'incident_status': 'crowding',
  });

  stdout.writeln('[dart-pub] $me -> $to  notifying live_traffic.smartroute');
  final res = await atClient.notificationService
      .notify(NotificationParams.forUpdate(key, value: payload));
  stdout.writeln('[dart-pub] status=${res.notificationStatusEnum} '
      'exception=${res.atClientException}');
  exit(0);
}
