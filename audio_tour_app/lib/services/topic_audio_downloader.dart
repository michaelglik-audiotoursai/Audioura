// [LOCAL-907E] Keeps the region-topic audio ("fillings") on the phone.
//
// When a tour is downloaded, the ZIP carries `fillings.json` (the item list, no audio). After the
// tour's OWN audio is saved, [downloadForTour] fetches every item's MP3 into the tour folder as
// `topic_<segment_id>.mp3`, one at a time, in the background. A download that fails never fails
// the tour: that item is recorded in `topic_audio_status.json` and [applyLocal] hides it from the
// player. The player prefers the local file over the server URL.
library topic_audio_downloader;

import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/endpoints.dart';
import 'fillings_model.dart';
import 'webview_topic_audio.dart' show joinTopicAudioUrl;

typedef TopicFetch = Future<List<int>?> Function(String url);

class TopicAudioDownloader {
  static const statusFile = 'topic_audio_status.json';

  static String localName(int segmentId) => 'topic_$segmentId.mp3';

  static Future<List<int>?> _httpFetch(String url) async {
    try {
      final r = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 90));
      if (r.statusCode != 200 || r.bodyBytes.isEmpty) return null;
      return r.bodyBytes;
    } catch (_) {
      return null;
    }
  }

  /// Downloads every item's audio of the tour in [tourPath]. Returns the segment ids that failed.
  /// Never throws.
  static Future<List<int>> downloadForTour(
    String tourPath, {
    Future<String> Function()? baseUrl,
    TopicFetch? fetch,
  }) async {
    final failed = <int>[];
    try {
      final plan = await FillingsPlan.loadFromTourDir(tourPath);
      if (plan.isEmpty) return failed;
      final base = await (baseUrl ?? () => Endpoints.base(Service.mapDelivery))();
      final get = fetch ?? _httpFetch;
      final ok = <int>[];
      final seen = <int>{};
      for (final leg in plan.legs) {
        for (final item in leg.items) {
          if (!seen.add(item.segmentId)) continue;
          final dest = File('$tourPath/${localName(item.segmentId)}');
          try {
            if (await dest.exists() && await dest.length() > 0) {
              ok.add(item.segmentId);
              continue;
            }
            final bytes = await get(joinTopicAudioUrl(base, item.audioUrl));
            if (bytes == null || bytes.isEmpty) throw StateError('no audio');
            final part = File('${dest.path}.part');
            await part.writeAsBytes(bytes, flush: true);
            await part.rename(dest.path);
            ok.add(item.segmentId);
          } catch (_) {
            failed.add(item.segmentId);
            try {
              final part = File('${dest.path}.part');
              if (await part.exists()) await part.delete();
            } catch (_) {}
          }
        }
      }
      await File('$tourPath/$statusFile')
          .writeAsString(jsonEncode({'ok': ok, 'failed': failed}));
    } catch (_) {}
    return failed;
  }

  /// The plan the player should use: items saved in the tour folder play from the file; items whose
  /// download failed are hidden; anything not tried yet keeps its server URL.
  static Future<FillingsPlan> applyLocal(FillingsPlan plan, String tourPath) async {
    if (plan.isEmpty) return plan;
    final failed = <int>{};
    try {
      final f = File('$tourPath/$statusFile');
      if (await f.exists()) {
        final j = jsonDecode(await f.readAsString());
        if (j is Map && j['failed'] is List) {
          for (final x in j['failed'] as List) {
            if (x is num) failed.add(x.toInt());
          }
        }
      }
    } catch (_) {}
    final legs = <FillingLeg>[];
    for (final leg in plan.legs) {
      final items = <FillingItem>[];
      for (final item in leg.items) {
        final local = File('$tourPath/${localName(item.segmentId)}');
        if (await local.exists() && await local.length() > 0) {
          items.add(item.withAudioUrl(Uri.file(local.path).toString()));
        } else if (!failed.contains(item.segmentId)) {
          items.add(item);
        }
      }
      if (items.isNotEmpty) legs.add(leg.withItems(items));
    }
    return legs.isEmpty ? FillingsPlan.empty : FillingsPlan(legs);
  }
}
