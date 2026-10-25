// LOCAL-764 A — the Subscribed build must talk to its OWN cloud host.
//
// Context (endpoints.dart / D708): in cloud mode the app picks a base URL by
// track. Before this task there were two: Beta (`https://api.audioura.com`) and
// Storied (`https://storied-api.audioura.com`). The Subscribed build
// (Config.isSubscribedBuild, APP_TRACK=subscribed) is its own stack and must
// use `https://subscribed-api.audioura.com` — NOT Beta's gateway (which has no
// routes for user-api / communities / IAP / recovery / pricing). Beta and
// Storied behaviour must stay byte-for-byte unchanged (Track B promise).
//
// `Config.isSubscribedBuild` is a compile-time const, so a single test process
// cannot flip it between tracks. The host selection is therefore exercised
// through `Endpoints.baseForTrack(service, track)` — the @visibleForTesting
// seam that `base()` itself uses after resolving `cloudTrack()`. This lets one
// ordinary `flutter test` run assert all three tracks without a per-track
// recompile, while `base()` stays the real code path.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/config/endpoints.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // The full Service enum — every service the app can address. The subscribed
  // host must be returned for ALL of them (no per-service exceptions).
  const allServices = Service.values;

  const beta = 'https://api.audioura.com';
  const storied = 'https://storied-api.audioura.com';
  const subscribed = 'https://subscribed-api.audioura.com';

  group('baseForTrack host selection by track', () {
    test('subscribed build -> subscribed host for EVERY service', () {
      for (final s in allServices) {
        expect(Endpoints.baseForTrack(s, 'subscribed'), subscribed,
            reason: 'Service.$s on the subscribed track must use the '
                'subscribed cloud host');
      }
    });

    test('storied track -> storied host for every service (unchanged)', () {
      for (final s in allServices) {
        expect(Endpoints.baseForTrack(s, 'storied'), storied,
            reason: 'Service.$s on storied must still use the storied host');
      }
    });

    test('beta track -> beta host for every service (unchanged)', () {
      for (final s in allServices) {
        expect(Endpoints.baseForTrack(s, 'beta'), beta,
            reason: 'Service.$s on beta must still use the default beta host');
      }
    });

    test('unknown/default track falls back to beta host (unchanged)', () {
      // A missing or unrecognised track must behave exactly as Beta did before
      // Subscribed existed — never leak the subscribed or storied host.
      expect(Endpoints.baseForTrack(Service.orchestrator, 'nonsense'), beta);
      expect(Endpoints.baseForTrack(Service.userDb, ''), beta);
    });
  });

  test('the three cloud hosts are distinct', () {
    final hosts = {
      Endpoints.baseForTrack(Service.orchestrator, 'beta'),
      Endpoints.baseForTrack(Service.orchestrator, 'storied'),
      Endpoints.baseForTrack(Service.orchestrator, 'subscribed'),
    };
    expect(hosts.length, 3,
        reason: 'beta, storied and subscribed must each have their own host');
  });
}
