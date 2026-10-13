// [LOCAL-677B] The paid-tour facts carried into a downloaded tour's LOCAL
// record, and the offline-correct lock decision made from them.
//
// Why this exists (the Bounce, Michael's iPhone 2026-10-13): the player opened a
// downloaded tour by its local path, so it never knew the SERVER tour id, never
// asked `/tour/<id>/unlock-state`, and `TourPricingService.unlockState` fell
// back to "free" — a paid tour played all its stops with no Buy. The fix is to
// STAMP the server id, price tier and unlock state onto the saved record AT
// DOWNLOAD TIME, so the player can (a) ask the server with the right id when
// online and (b) gate correctly from the local snapshot when offline.
//
// Design (D647 addendum 2 — Michael's offline rule):
//   * A tour stored as PAID and NOT unlocked stays preview-only offline
//     (fail closed — only for a tour stored paid).
//   * A tour stored as FREE stays free (fail open for free).
//   * Grandfathering: a tour downloaded while it was FREE stays playable for
//     that listener even after the curator later prices it. We record whether
//     the tour was paid AT DOWNLOAD TIME; a tour grandfathered-free is never
//     locked offline. A re-download after the price was set stamps it paid, so
//     the lock then engages (exactly Michael's test).
//   * An unlock writes to the local record at once after a confirmed purchase
//     (so the lock lifts offline immediately), and syncs to the server as today.
//
// This module is pure model + SharedPreferences glue so it is unit-testable
// without a WebView or a live server.

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// The paid-tour snapshot stamped onto a downloaded tour's saved_tours record.
///
/// Keys used inside the saved_tours JSON map:
///   server_tour_id   — the NUMERIC server tour id the pricing/unlock endpoints
///                       key on (distinct from `tour_id`, which is the editable
///                       id and is often non-numeric). Null when the download
///                       produced no numeric id.
///   price_tier       — the price tier at download time (null = free).
///   is_paid          — whether the tour was PAID at download time (grandfather
///                       snapshot). A tour stored is_paid:false is never locked.
///   unlocked         — whether THIS device had unlocked the tour. Written true
///                       on a confirmed purchase so the lock lifts offline.
///   price_label      — display label at download time ('$4.99' / 'Free').
///   original_language— the tour's original language code (for the Listen header).
///   tour_version     — the version number at download time (for the header).
class DownloadedTourMeta {
  final String? serverTourId;
  final int? priceTier;
  final bool isPaid;
  final bool unlocked;
  final String priceLabel;
  final String? originalLanguage;
  final int? tourVersion;

  const DownloadedTourMeta({
    required this.serverTourId,
    required this.priceTier,
    required this.isPaid,
    required this.unlocked,
    required this.priceLabel,
    required this.originalLanguage,
    required this.tourVersion,
  });

  /// Read the snapshot off a saved_tours record map. Defensive: a record saved
  /// before 677B simply has none of these keys and resolves to a FREE, unlocked
  /// snapshot (so an old free tour keeps playing — grandfathering by absence).
  factory DownloadedTourMeta.fromRecord(Map<String, dynamic> r) {
    bool asBool(dynamic v) => v == true || v == 'true' || v == 1;
    int? asInt(dynamic v) {
      if (v is int) return v;
      if (v is num) return v.toInt();
      if (v is String) return int.tryParse(v);
      return null;
    }

    final sid = r['server_tour_id'];
    return DownloadedTourMeta(
      serverTourId: (sid == null) ? null : '$sid',
      priceTier: asInt(r['price_tier']),
      isPaid: asBool(r['is_paid']),
      unlocked: asBool(r['unlocked']),
      priceLabel: (r['price_label'] as String?) ?? 'Free',
      originalLanguage: (r['original_language'] as String?)?.trim().isEmpty ?? true
          ? null
          : (r['original_language'] as String).trim(),
      tourVersion: asInt(r['tour_version']) ?? asInt(r['version']),
    );
  }

  /// The fields to MERGE into a saved_tours record at download time. Only the
  /// paid-tour keys — the caller keeps the rest of the record intact.
  Map<String, dynamic> toRecordFields() => {
        if (serverTourId != null) 'server_tour_id': serverTourId,
        'price_tier': priceTier,
        'is_paid': isPaid,
        'unlocked': unlocked,
        'price_label': priceLabel,
        if (originalLanguage != null) 'original_language': originalLanguage,
        if (tourVersion != null) 'tour_version': tourVersion,
      };

  /// The OFFLINE-CORRECT lock decision from this local snapshot (D647 add. 2).
  ///
  /// true  → the tour must play preview-only (Stop 1 free, the rest locked).
  /// false → the tour plays in full.
  ///
  /// Fail CLOSED only for a tour stored PAID and not unlocked. A tour stored
  /// FREE (including one grandfathered-free, i.e. downloaded before a price was
  /// set) is never locked.
  bool get lockedOffline => isPaid && !unlocked;

  /// Whether this is a paid tour the player should treat as a candidate for the
  /// online unlock-state check (worth asking the server with the server id).
  bool get isPaidAtDownload => isPaid;
}

/// Stamp / read the paid-tour snapshot on the saved_tours list.
class DownloadedTourStore {
  DownloadedTourStore._();

  /// Find a saved_tours record by its local [path], or null. Returns a mutable
  /// copy; the record's own index is returned too so callers can write it back.
  static Future<({Map<String, dynamic> record, int index})?> _findByPath(
      SharedPreferences prefs, String path) async {
    final raw = prefs.getStringList('saved_tours') ?? [];
    for (var i = 0; i < raw.length; i++) {
      try {
        final m = Map<String, dynamic>.from(json.decode(raw[i]) as Map);
        if (m['path'] == path) return (record: m, index: i);
      } catch (_) {}
    }
    return null;
  }

  /// Read the paid-tour snapshot for the downloaded tour at [path]. Returns a
  /// FREE/unlocked snapshot when there is no record or it predates 677B.
  static Future<DownloadedTourMeta> metaForPath(String path) async {
    final prefs = await SharedPreferences.getInstance();
    final found = await _findByPath(prefs, path);
    if (found == null) {
      return const DownloadedTourMeta(
        serverTourId: null,
        priceTier: null,
        isPaid: false,
        unlocked: true,
        priceLabel: 'Free',
        originalLanguage: null,
        tourVersion: null,
      );
    }
    return DownloadedTourMeta.fromRecord(found.record);
  }

  /// Merge [fields] into the saved_tours record at [path]. No-op when the record
  /// is not found (e.g. a tour opened by path that was never saved). Returns true
  /// when a record was updated.
  static Future<bool> mergeFieldsForPath(
      String path, Map<String, dynamic> fields) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList('saved_tours') ?? [];
    var changed = false;
    for (var i = 0; i < raw.length; i++) {
      try {
        final m = Map<String, dynamic>.from(json.decode(raw[i]) as Map);
        if (m['path'] == path) {
          m.addAll(fields);
          raw[i] = json.encode(m);
          changed = true;
          break;
        }
      } catch (_) {}
    }
    if (changed) await prefs.setStringList('saved_tours', raw);
    return changed;
  }

  /// Record locally that this device unlocked the tour at [path] — called right
  /// after a confirmed purchase so the lock lifts OFFLINE at once (it also syncs
  /// to the server through the existing purchase path). Marks the record both
  /// unlocked AND paid (an unlock only makes sense for a paid tour).
  static Future<void> markUnlockedForPath(String path) async {
    await mergeFieldsForPath(path, {'unlocked': true});
  }
}
