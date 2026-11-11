import 'dart:convert';
import 'dart:io';

/// [LOCAL-895] The single source of truth for the stop count stored in
/// `saved_tours[..]['stops']`.
///
/// The Listen list renders `'<stops> stops'` from that field. It used to be
/// written from the stop-count text box (default 10) or a literal '10', so an
/// 8-stop tour showed "10 stops". The real count, in order of preference:
///   (a) the `audio_N.mp3` files in the extracted tour folder,
///   (b) the server's `actual_stops` / `stops_count`,
///   (c) the length of the user's own stop list.
/// If none is known the result is null and the caller omits `stops` entirely
/// (the Listen card then renders the date only, LOCAL-484).

final RegExp _audioMp3 = RegExp(r'^audio_\d+\.mp3$');

/// Number of `audio_N.mp3` files directly in [tourDirPath]; null if the folder
/// is missing or holds none (unknown — never invent a number).
int? countAudioMp3s(String tourDirPath) {
  if (tourDirPath.isEmpty) return null;
  final dir = Directory(tourDirPath);
  if (!dir.existsSync()) return null;
  var count = 0;
  try {
    for (final e in dir.listSync()) {
      if (e is File && _audioMp3.hasMatch(e.uri.pathSegments.last)) count++;
    }
  } catch (_) {
    return null;
  }
  return count > 0 ? count : null;
}

int? _positive(Object? v) {
  final n = v is num ? v.toInt() : (v is String ? int.tryParse(v.trim()) : null);
  return (n != null && n > 0) ? n : null;
}

/// Server count from a `/status/<job>` body: `actual_stops`, else `stops_count`.
int? serverStopCount(Map<String, dynamic>? status) {
  if (status == null) return null;
  return _positive(status['actual_stops']) ?? _positive(status['stops_count']);
}

/// The real stop count, or null when unknown. Never reads the stop-count box.
int? resolveRealStopCount({
  String? tourDirPath,
  int? serverCount,
  int? userListLength,
}) {
  if (tourDirPath != null) {
    final onDisk = countAudioMp3s(tourDirPath);
    if (onDisk != null) return onDisk;
  }
  return _positive(serverCount) ?? _positive(userListLength);
}

/// `{'stops': '<n>'}` when known, else an empty map — spread into a saved-tour
/// entry with `...stopsEntry(count)`.
Map<String, String> stopsEntry(int? count) =>
    count == null ? const {} : {'stops': count.toString()};

/// One-time repair: for each entry whose folder exists and holds MP3s, fix
/// `stops` if it differs from the recount. Entries with no folder, no MP3s or
/// malformed JSON pass through untouched. Returns the new list and whether
/// anything changed.
({List<String> tours, bool changed}) repairSavedTourStops(
    List<String> savedTours) {
  final out = List<String>.from(savedTours);
  var changed = false;
  for (var i = 0; i < out.length; i++) {
    try {
      final decoded = jsonDecode(out[i]);
      if (decoded is! Map<String, dynamic>) continue;
      final path = decoded['path'];
      if (path is! String) continue;
      final real = countAudioMp3s(path);
      if (real == null) continue;
      if (decoded['stops']?.toString() == real.toString()) continue;
      decoded['stops'] = real.toString();
      out[i] = jsonEncode(decoded);
      changed = true;
    } catch (_) {
      continue;
    }
  }
  return (tours: out, changed: changed);
}
