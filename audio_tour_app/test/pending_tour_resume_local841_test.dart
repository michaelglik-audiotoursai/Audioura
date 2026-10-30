// [LOCAL-841] Unit tests for the suspended-generation resume fix.
//
// Michael's coffee tour (503) was generated and stored on the cloud but never
// downloaded: iOS suspended the app while the Generate screen was polling, the
// in-screen loop died, and the job id was lost. The fix persists every in-flight
// request and finishes the download on the next start/resume.
//
// These tests pin the two testable units end-to-end with injected IO:
//   * PendingTourRequestsStore — add (idempotent) / load (skips corrupt) / remove.
//   * ResumeDecision.decide — the pure completed / failed / stale / waiting policy.
//   * PendingTourResumeHandler.run — completed downloads+saves+clears, failed
//     removes + reports, stale (>2h unknown) removes quietly.
//
// They can FAIL on purpose: drop the persist in the handler and the completed
// case stops saving; widen the stale cutoff and the stale case stops dropping.

import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/services/pending_tour_requests_store.dart';
import 'package:audio_tour_app_dev/services/pending_tour_resume_handler.dart';

/// Build a minimal tour zip (index.html + one mp3) as the orchestrator serves.
List<int> _tourZip() {
  final archive = Archive();
  final html = utf8.encode('<html><body>tour</body></html>');
  final mp3 = <int>[0, 1, 2, 3];
  archive.addFile(ArchiveFile('index.html', html.length, html));
  archive.addFile(ArchiveFile('stop1.mp3', mp3.length, mp3));
  return ZipEncoder().encode(archive)!;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // The handler's default surface and SavedToursRefresh are fine in the VM;
  // path_provider is injected via docsDirPath so no plugin channel is needed.
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('PendingTourRequestsStore', () {
    test('add then load round-trips all fields', () async {
      final prefs = await SharedPreferences.getInstance();
      final started = DateTime.utc(2026, 10, 30, 10, 0, 0);
      await PendingTourRequestsStore.add(
        prefs,
        PendingTourRequest(
          jobId: 'job-1',
          title: 'coffee tour',
          startedAt: started,
          clientRequestId: 'cli-abc',
          languages: const ['en', 'vi'],
          stopCount: '8',
        ),
      );
      final loaded = await PendingTourRequestsStore.load(prefs);
      expect(loaded, hasLength(1));
      expect(loaded.first.jobId, 'job-1');
      expect(loaded.first.title, 'coffee tour');
      expect(loaded.first.startedAt, started);
      expect(loaded.first.clientRequestId, 'cli-abc');
      expect(loaded.first.languages, ['en', 'vi']);
      expect(loaded.first.stopCount, '8');
    });

    test('add is idempotent on jobId (no duplicate entry)', () async {
      final prefs = await SharedPreferences.getInstance();
      final req = PendingTourRequest(
        jobId: 'job-dup',
        title: 't',
        startedAt: DateTime.utc(2026, 10, 30),
      );
      await PendingTourRequestsStore.add(prefs, req);
      await PendingTourRequestsStore.add(prefs, req);
      expect(await PendingTourRequestsStore.load(prefs), hasLength(1));
    });

    test('load skips a corrupt entry instead of losing the whole list',
        () async {
      final prefs = await SharedPreferences.getInstance();
      final good = jsonEncode(PendingTourRequest(
        jobId: 'good',
        title: 'ok',
        startedAt: DateTime.utc(2026, 10, 30),
      ).toJson());
      await prefs.setStringList(
          PendingTourRequestsStore.key, ['{not json', good, '42']);
      final loaded = await PendingTourRequestsStore.load(prefs);
      expect(loaded, hasLength(1));
      expect(loaded.first.jobId, 'good');
    });

    test('remove drops the matching jobId only', () async {
      final prefs = await SharedPreferences.getInstance();
      await PendingTourRequestsStore.add(
          prefs,
          PendingTourRequest(
              jobId: 'a', title: 'a', startedAt: DateTime.utc(2026)));
      await PendingTourRequestsStore.add(
          prefs,
          PendingTourRequest(
              jobId: 'b', title: 'b', startedAt: DateTime.utc(2026)));
      await PendingTourRequestsStore.remove(prefs, 'a');
      final loaded = await PendingTourRequestsStore.load(prefs);
      expect(loaded.map((r) => r.jobId), ['b']);
    });
  });

  group('ResumeDecision.decide', () {
    const young = Duration(minutes: 5);
    const old = Duration(hours: 3);

    test('completed -> download', () {
      expect(
        ResumeDecision.decide(
            httpOk: true, serverStatus: 'completed', notFound: false, age: young),
        ResumeAction.download,
      );
    });

    test('error / failed -> removeFailed', () {
      expect(
        ResumeDecision.decide(
            httpOk: true, serverStatus: 'error', notFound: false, age: young),
        ResumeAction.removeFailed,
      );
      expect(
        ResumeDecision.decide(
            httpOk: true, serverStatus: 'failed', notFound: false, age: young),
        ResumeAction.removeFailed,
      );
    });

    test('processing & young -> keepWaiting; processing & old -> removeStale',
        () {
      expect(
        ResumeDecision.decide(
            httpOk: true, serverStatus: 'processing', notFound: false, age: young),
        ResumeAction.keepWaiting,
      );
      expect(
        ResumeDecision.decide(
            httpOk: true, serverStatus: 'processing', notFound: false, age: old),
        ResumeAction.removeStale,
      );
    });

    test('404 & young -> keepWaiting; 404 & old -> removeStale', () {
      expect(
        ResumeDecision.decide(
            httpOk: false, notFound: true, age: young),
        ResumeAction.keepWaiting,
      );
      expect(
        ResumeDecision.decide(
            httpOk: false, notFound: true, age: old),
        ResumeAction.removeStale,
      );
    });

    test('network error & young -> keepWaiting (retry next pass)', () {
      expect(
        ResumeDecision.decide(
            httpOk: false, notFound: false, age: young),
        ResumeAction.keepWaiting,
      );
    });
  });

  group('PendingTourResumeHandler.run', () {
    late Directory tmp;

    setUp(() async {
      tmp = await Directory.systemTemp.createTemp('local841_resume_');
    });
    tearDown(() async {
      if (await tmp.exists()) await tmp.delete(recursive: true);
    });

    test('completed job is downloaded, saved to Listen, and cleared', () async {
      final prefs = await SharedPreferences.getInstance();
      await PendingTourRequestsStore.add(
        prefs,
        PendingTourRequest(
          jobId: 'job-c',
          title: 'coffee tour',
          startedAt: DateTime.now().toUtc(),
        ),
      );

      final zip = _tourZip();
      final ready = <PendingTourRequest>[];

      final result = await PendingTourResumeHandler.instance.run(
        prefs: prefs,
        docsDirPath: tmp.path,
        now: () => DateTime.now(),
        onReady: ready.add,
        httpGet: (url, {headers}) async {
          if (url.path.contains('/status/')) {
            return http.Response.bytes(
              utf8.encode(jsonEncode({
                'status': 'completed',
                'final_tour_id': '9001',
                'tour_title': 'Coffee & Vườn Thiên Giới',
                'coordinates': [10.77, 106.69],
              })),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }
          if (url.path.contains('/download/')) {
            // Must download by final_tour_id, not job id.
            expect(url.path, contains('/download/9001'));
            return http.Response.bytes(zip, 200);
          }
          return http.Response('not found', 404);
        },
      );

      expect(result.downloaded, 1);
      // Pending entry cleared.
      expect(await PendingTourRequestsStore.load(prefs), isEmpty);
      // Saved to Listen.
      final saved = prefs.getStringList('saved_tours') ?? [];
      expect(saved, hasLength(1));
      final tour = jsonDecode(saved.first) as Map<String, dynamic>;
      expect(tour['tour_id'], '9001');
      expect(tour['title'], 'Coffee & Vườn Thiên Giới');
      expect(tour['resumed'], true);
      // Files extracted to tours/<final_tour_id>.
      expect(
          await File('${tmp.path}/tours/9001/index.html').exists(), isTrue);
      // "Ready" surfaced once.
      expect(ready, hasLength(1));
      expect(ready.first.jobId, 'job-c');
    });

    test('failed job is removed and reported, nothing saved', () async {
      final prefs = await SharedPreferences.getInstance();
      await PendingTourRequestsStore.add(
        prefs,
        PendingTourRequest(
          jobId: 'job-f',
          title: 'bad place',
          startedAt: DateTime.now().toUtc(),
        ),
      );

      final failures = <String>[];
      final result = await PendingTourResumeHandler.instance.run(
        prefs: prefs,
        docsDirPath: tmp.path,
        onFailed: (req, reason) => failures.add(reason),
        httpGet: (url, {headers}) async => http.Response(
          jsonEncode({'status': 'error', 'message': 'No stops could be found.'}),
          200,
        ),
      );

      expect(result.failed, 1);
      expect(await PendingTourRequestsStore.load(prefs), isEmpty);
      expect(prefs.getStringList('saved_tours') ?? [], isEmpty);
      expect(failures.single, 'No stops could be found.');
    });

    test('stale (>2h) unknown job is removed quietly', () async {
      final prefs = await SharedPreferences.getInstance();
      await PendingTourRequestsStore.add(
        prefs,
        PendingTourRequest(
          jobId: 'job-s',
          title: 'old one',
          startedAt: DateTime.now().toUtc().subtract(const Duration(hours: 3)),
        ),
      );

      final ready = <PendingTourRequest>[];
      final failures = <String>[];
      final result = await PendingTourResumeHandler.instance.run(
        prefs: prefs,
        docsDirPath: tmp.path,
        onReady: ready.add,
        onFailed: (req, reason) => failures.add(reason),
        // Server does not know this job anymore.
        httpGet: (url, {headers}) async => http.Response('Job not found', 404),
      );

      expect(result.stale, 1);
      expect(await PendingTourRequestsStore.load(prefs), isEmpty);
      // Quiet: no ready banner, no failure reason.
      expect(ready, isEmpty);
      expect(failures, isEmpty);
    });

    test('still-processing young job is kept for the next pass', () async {
      final prefs = await SharedPreferences.getInstance();
      await PendingTourRequestsStore.add(
        prefs,
        PendingTourRequest(
          jobId: 'job-p',
          title: 'cooking',
          startedAt: DateTime.now().toUtc(),
        ),
      );

      final result = await PendingTourResumeHandler.instance.run(
        prefs: prefs,
        docsDirPath: tmp.path,
        httpGet: (url, {headers}) async => http.Response(
          jsonEncode({'status': 'processing', 'progress': 'Writing...'}),
          200,
        ),
      );

      expect(result.kept, 1);
      expect(await PendingTourRequestsStore.load(prefs), hasLength(1));
    });

    test('empty pending list is a no-op', () async {
      final prefs = await SharedPreferences.getInstance();
      final result = await PendingTourResumeHandler.instance.run(
        prefs: prefs,
        docsDirPath: tmp.path,
        httpGet: (url, {headers}) async {
          fail('should not hit the network with no pending requests');
        },
      );
      expect(result.downloaded, 0);
      expect(result.failed, 0);
      expect(result.stale, 0);
      expect(result.kept, 0);
    });
  });
}
