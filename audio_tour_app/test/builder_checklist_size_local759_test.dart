// [LOCAL-759 C] The organiser-audio builder's checklist shows each episode's
// SIZE and a running total of the ticked episodes ("3 episodes · 285 MB"), so
// the organiser knows what members will download (Michael's Salem tour).
//
// These pin the pure helpers the builder uses (formatBytes,
// tickedEpisodesTotalLabel) and that CommunityEpisode.metaLine now carries the
// size the server sends (LOCAL-759 C server side). Red on d816a251:
// tickedEpisodesTotalLabel does not exist, and the feed carried no size so
// metaLine had no "MB".

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';

void main() {
  group('formatBytes', () {
    test('MB for ≥ 1 MB, no decimals at ≥ 10 MB', () {
      expect(formatBytes(285 * 1024 * 1024), '285 MB');
      expect(formatBytes(131800000), '126 MB'); // 131.8 MB → rounded, ≥10
      expect(formatBytes((1.5 * 1024 * 1024).round()), '1.5 MB');
    });
    test('KB below 1 MB, empty for 0/negative', () {
      expect(formatBytes(500 * 1024), '500 KB');
      expect(formatBytes(0), '');
      expect(formatBytes(-5), '');
    });
  });

  group('tickedEpisodesTotalLabel', () {
    test('counts + sums the ticked episodes', () {
      // Michael's three Salem episodes: 72.5 + 80.9 + 131.8 ≈ 285 MB.
      final total = (72.5 + 80.9 + 131.8) * 1024 * 1024;
      expect(tickedEpisodesTotalLabel(3, total.round()), '3 episodes · 285 MB');
    });
    test('singular, and size dropped when unknown', () {
      expect(tickedEpisodesTotalLabel(1, 48 * 1024 * 1024), '1 episode · 48 MB');
      expect(tickedEpisodesTotalLabel(2, 0), '2 episodes');
    });
    test('none selected', () {
      expect(tickedEpisodesTotalLabel(0, 0), 'No episodes selected');
    });
  });

  group('CommunityEpisode.metaLine carries the size from the feed', () {
    test('size renders as MB in the meta line', () {
      const e = CommunityEpisode(
        position: 1,
        title: 'The Accusations Begin',
        audioUrl: 'https://mcdn.podbean.com/ep1.mp3',
        source: 'feed',
        date: '21 Oct 2025',
        duration: '48:12',
        sizeBytes: 76021760, // ≈ 72.5 MB
      );
      expect(e.metaLine, contains('73 MB')); // 76,021,760 B ≈ 72.5 → 73 (≥10 MB, no decimals)
      expect(e.metaLine, contains('48:12'));
      expect(e.metaLine, contains('21 Oct 2025'));
    });

    test('fromJson reads the server size/duration/date fields', () {
      final e = CommunityEpisode.fromJson({
        'position': 1,
        'title': 'T',
        'audio_url': 'https://h/e.mp3',
        'source': 'feed',
        'size': 84828160,
        'duration': '3600',
        'date': '28 Oct 2025',
      });
      expect(e.sizeBytes, 84828160);
      expect(e.duration, '3600');
      expect(e.date, '28 Oct 2025');
      expect(e.metaLine, contains('MB'));
    });
  });
}
