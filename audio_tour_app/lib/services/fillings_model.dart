// [LOCAL-908] The `fillings` payload from LOCAL-907 (D772): optional region
// topics played on the way between two stops.
//
//   "fillings": [{"leg": 0, "after_stop": 1, "minutes": 37.4,
//                 "items": [{"segment_id": 12, "title": "...", "theme": "history",
//                            "minutes": 12.7, "audio_url": "...|null",
//                            "credit_line": "..."}]}]
//
// `leg` is 0-based (leg 0 = Stop 1 -> Stop 2); `after_stop` is the 1-based
// number of the stop the leg follows. The FIRST item is the default auto-play.
//
// Optional extras the app understands when the server adds them (907 does not
// send them today, so every one has a safe default):
//   item.sentence_ends  List<num>  second offsets where a sentence ends
//   item.sources        List<{title,url}> | item.source_url  String
//   item.language       String     language of the topic audio
//
// Parsing is tolerant: a malformed leg/item is skipped, never thrown. A tour
// with no `fillings` yields [FillingsPlan.empty] and the player behaves exactly
// as it did before this feature.
library fillings_model;

import 'dart:convert';
import 'dart:io';

class FillingSource {
  final String title;
  final String url;
  const FillingSource(this.title, this.url);
}

class FillingItem {
  final int segmentId;
  final String title;
  final String theme;
  final double minutes;
  final String audioUrl;
  final String creditLine;
  final List<double> sentenceEnds;
  final List<FillingSource> sources;
  final String? language;

  const FillingItem({
    required this.segmentId,
    required this.title,
    required this.theme,
    required this.minutes,
    required this.audioUrl,
    this.creditLine = '',
    this.sentenceEnds = const [],
    this.sources = const [],
    this.language,
  });

  /// [LOCAL-907E] The same item playing from [url] (a file saved in the tour folder).
  FillingItem withAudioUrl(String url) => FillingItem(
        segmentId: segmentId,
        title: title,
        theme: theme,
        minutes: minutes,
        audioUrl: url,
        creditLine: creditLine,
        sentenceEnds: sentenceEnds,
        sources: sources,
        language: language,
      );

  /// Whole minutes for display ("12 min"), never below 1.
  int get minutesLabel => minutes < 1 ? 1 : minutes.round();

  /// "history" -> "History".
  String get themeLabel => theme.isEmpty
      ? ''
      : theme[0].toUpperCase() + theme.substring(1).replaceAll('_', ' ');

  /// The link shown next to the credit line: an explicit source, else the first
  /// URL found in the credit line, else null (no link is shown).
  String? get sourcesUrl {
    if (sources.isNotEmpty) return sources.first.url;
    final m = RegExp(r'https?://[^\s)]+').firstMatch(creditLine);
    return m?.group(0);
  }

  static FillingItem? tryParse(dynamic j) {
    if (j is! Map) return null;
    final id = j['segment_id'];
    final segmentId = id is num ? id.toInt() : int.tryParse('$id');
    final title = (j['title'] ?? '').toString().trim();
    // The app can only play a topic that has audio. `audio_url: null` means
    // the audio is not rendered yet, so it is not offered.
    final url = (j['audio_url'] ?? '').toString().trim();
    if (segmentId == null || title.isEmpty || url.isEmpty) return null;
    final m = j['minutes'];
    final ends = <double>[];
    final rawEnds = j['sentence_ends'];
    if (rawEnds is List) {
      for (final e in rawEnds) {
        if (e is num && e >= 0) ends.add(e.toDouble());
      }
      ends.sort();
    }
    final sources = <FillingSource>[];
    final rawSources = j['sources'];
    if (rawSources is List) {
      for (final s in rawSources) {
        if (s is Map && (s['url'] ?? '').toString().startsWith('http')) {
          sources.add(FillingSource(
              (s['title'] ?? '').toString(), s['url'].toString()));
        }
      }
    }
    final single = (j['source_url'] ?? '').toString();
    if (sources.isEmpty && single.startsWith('http')) {
      sources.add(FillingSource('', single));
    }
    final lang = (j['language'] ?? '').toString().trim();
    return FillingItem(
      segmentId: segmentId,
      title: title,
      theme: (j['theme'] ?? '').toString().trim(),
      minutes: m is num ? m.toDouble() : double.tryParse('$m') ?? 0,
      audioUrl: url,
      creditLine: (j['credit_line'] ?? '').toString().trim(),
      sentenceEnds: ends,
      sources: sources,
      language: lang.isEmpty ? null : lang.toLowerCase(),
    );
  }
}

class FillingLeg {
  final int leg; // 0-based
  final int afterStop; // 1-based
  final double minutes;
  final List<FillingItem> items;
  const FillingLeg({
    required this.leg,
    required this.afterStop,
    required this.minutes,
    required this.items,
  });

  /// "~35 min": nearest 5 from 10 up, else the nearest minute (a leg length is
  /// an estimate, so the tilde is honest).
  String get minutesLabel {
    final m = minutes;
    if (m >= 10) return '~${((m / 5).round() * 5)} min';
    return '~${m < 1 ? 1 : m.round()} min';
  }

  FillingLeg withItems(List<FillingItem> next) => FillingLeg(
      leg: leg, afterStop: afterStop, minutes: minutes, items: next);
}

class FillingsPlan {
  final List<FillingLeg> legs;
  const FillingsPlan(this.legs);
  static const FillingsPlan empty = FillingsPlan([]);

  bool get isEmpty => legs.isEmpty;

  /// The leg that follows the 1-based stop [afterStop], or null.
  FillingLeg? legAfterStop(int afterStop) {
    for (final l in legs) {
      if (l.afterStop == afterStop) return l;
    }
    return null;
  }

  /// Accepts the `fillings` list, or an object `{"fillings": [...]}` (the
  /// whole payload / tour.json). Anything else => [empty].
  static FillingsPlan parse(dynamic json) {
    dynamic list = json;
    if (json is Map) list = json['fillings'];
    if (list is! List) return empty;
    final legs = <FillingLeg>[];
    for (final raw in list) {
      if (raw is! Map) continue;
      final rawItems = raw['items'];
      if (rawItems is! List) continue;
      final items = <FillingItem>[];
      for (final r in rawItems) {
        final it = FillingItem.tryParse(r);
        if (it != null) items.add(it);
      }
      if (items.isEmpty) continue;
      final leg = raw['leg'];
      final after = raw['after_stop'];
      final legIdx = leg is num ? leg.toInt() : int.tryParse('$leg');
      var afterStop = after is num ? after.toInt() : int.tryParse('$after');
      afterStop ??= legIdx == null ? null : legIdx + 1;
      if (afterStop == null || afterStop < 1) continue;
      final m = raw['minutes'];
      legs.add(FillingLeg(
        leg: legIdx ?? afterStop - 1,
        afterStop: afterStop,
        minutes: m is num ? m.toDouble() : double.tryParse('$m') ?? 0,
        items: items,
      ));
    }
    return legs.isEmpty ? empty : FillingsPlan(legs);
  }

  /// Translations: a topic whose `language` differs from the tour's language is
  /// "English-only" (LOCAL-908 item 9). With [keepForeign] false (the default
  /// setting: hide) those items are removed; with true they stay playable and
  /// [hasForeign] lets the panel say "Topics available in English".
  FillingsPlan forLanguage(String? tourLanguage, {required bool keepForeign}) {
    final tl = (tourLanguage ?? '').trim().toLowerCase();
    if (tl.isEmpty) return this;
    final out = <FillingLeg>[];
    for (final l in legs) {
      final kept = l.items
          .where((i) => i.language == null || i.language == tl || keepForeign)
          .toList();
      if (kept.isNotEmpty) out.add(l.withItems(kept));
    }
    return out.isEmpty ? empty : FillingsPlan(out);
  }

  bool hasForeign(String? tourLanguage) {
    final tl = (tourLanguage ?? '').trim().toLowerCase();
    if (tl.isEmpty) return false;
    return legs.any(
        (l) => l.items.any((i) => i.language != null && i.language != tl));
  }

  /// Reads `fillings.json` (list or object) or `tour.json`'s `fillings` from an
  /// extracted tour folder. Never throws; a missing/garbled file => [empty].
  static Future<FillingsPlan> loadFromTourDir(String tourPath) async {
    for (final name in const ['fillings.json', 'tour.json']) {
      try {
        final f = File('$tourPath/$name');
        if (!await f.exists()) continue;
        final plan = parse(jsonDecode(await f.readAsString()));
        if (!plan.isEmpty) return plan;
      } catch (_) {}
    }
    return empty;
  }
}
