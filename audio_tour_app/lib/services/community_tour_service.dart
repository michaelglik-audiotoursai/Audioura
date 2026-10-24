// [LOCAL-701] Community tour client (D663 §3) — the networked client.
//
// The MODELS and pure Generate-tab rules live in community_tour_models.dart
// (dependency-free, unit-tested). This file adds the HTTP client and re-exports
// the models so callers can import just this file.
//
//   GET  /communities/mine-owned?user_id=...   (userDb) owned communities
//                                              → the Generate "For:" selector
//   GET  /communities/<id>/tours?user_id=...   (orchestrator) a community's
//                                              tour list (members/owner only)
//   GET  /tour/<id>/community                  (orchestrator) a tour's tag
//
// Tagging a generated tour onto a community does NOT need a separate call: the
// Generate request itself carries community_id + community_visibility (see
// CommunityTourTarget.generateFields), and the orchestrator tags the stored
// tour after generation. This service is for the organiser selector and the
// community page's tour list.

import '../config/endpoints.dart';
import 'community_tour_models.dart';
import 'community_downloads.dart';
import 'device_service.dart';

export 'community_tour_models.dart';

class CommunityTourService {
  /// The communities this user OWNS, for the Generate tab's "For:" selector.
  /// Empty on any failure (transport error, non-200) — the selector then simply
  /// does not show (only organisers see it).
  static Future<List<OwnedCommunity>> ownedCommunities(String userId) async {
    try {
      final r = await Endpoints.get(
          Service.userDb, '/communities/mine-owned?user_id=$userId');
      final j = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && j != null) {
        final list = (j['communities'] as List?) ?? const [];
        return list
            .whereType<Map<String, dynamic>>()
            .map((m) => OwnedCommunity(
                  id: (m['id'] is num) ? (m['id'] as num).toInt() : 0,
                  name: (m['name'] ?? '') as String,
                  // [LOCAL-753 / D706] Carry the community's visibility so the
                  // Generate selector preselects public for a listed community.
                  visibility: (m['visibility'] ?? 'private') as String,
                ))
            .where((c) => c.id != 0)
            .toList(growable: false);
      }
    } catch (_) {}
    return const [];
  }

  /// The tours tagged to a community (the community page's episode-like tour
  /// list). The list is populated only for an active member or the owner;
  /// otherwise `tours` is empty and `isMember` is false. Null on a transport
  /// failure so the page can show its own empty state.
  static Future<CommunityTourList?> communityTours(int communityId,
      {String? userId}) async {
    try {
      final q = userId != null ? '?user_id=$userId' : '';
      final r = await Endpoints.get(
          Service.orchestrator, '/communities/$communityId/tours$q');
      final j = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && j != null) {
        return CommunityTourList.fromJson(j);
      }
    } catch (_) {}
    return null;
  }

  /// A single tour's community tag {community_id, community_visibility}, for the
  /// Origin menu. Returns (null, null) on any failure / an ordinary tour.
  static Future<Map<String, dynamic>?> tourTag(int tourId) async {
    try {
      final r =
          await Endpoints.get(Service.orchestrator, '/tour/$tourId/community');
      final j = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && j != null) return j;
    } catch (_) {}
    return null;
  }

  /// [LOCAL-713 / D675] The NEW community tours for this device across its
  /// ACTIVE memberships since [since] (blank = from the beginning). Returns the
  /// tours + the `server_time` to store as the next `since` after the downloads
  /// succeed. Null on a transport failure so the caller leaves `since`
  /// unchanged (never advance on failure). Served by Service.userDb (the same
  /// user-api the other community reads use).
  static Future<NewToursResult?> newTours(String userId, {String? since}) async {
    try {
      final q = StringBuffer('?user_id=$userId');
      if (since != null && since.isNotEmpty) {
        q.write('&since=${Uri.encodeQueryComponent(since)}');
      }
      final r =
          await Endpoints.get(Service.userDb, '/communities/new-tours$q');
      final j = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && j != null) {
        return NewToursResult.fromJson(j);
      }
    } catch (_) {}
    return null;
  }

  /// [LOCAL-746] The CURRENT (version, updated_at) of a tour from map-delivery's
  /// `/tour-info/<id>` — the SAME LOCAL-657 number the app already reads next to
  /// Downloads. Used by the sync-on-open to detect an organiser's in-place edit
  /// of a held community tour (the version rises when the tour is replaced).
  /// Returns null on any failure / a missing version, so the caller simply does
  /// not re-download that tour (never an error, never a spurious re-download).
  ///
  /// [LOCAL-755] Also carries `isOrganiserAudio` from the tour-info `source_kind`
  /// field ('organiser_audio'), so the held-tour refresh can skip an
  /// organiser-audio tour even when its saved record predates source_kind
  /// stamping (members are never pushed an organiser-audio update).
  static Future<({int version, String? updatedAt, bool isOrganiserAudio})?>
      serverTourVersion(int tourId) async {
    try {
      // [LOCAL-753 LEAD] /tour-info hides a members-only community tour from a
      // non-member (D707), so the version read must say who is asking —
      // without user_id every member's refresh got 404 and never updated.
      final uid = await DeviceService.getUserId();
      final q = uid.isNotEmpty ? '?user_id=${Uri.encodeComponent(uid)}' : '';
      final r =
          await Endpoints.get(Service.mapDelivery, '/tour-info/$tourId$q');
      final j = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && j != null) {
        final raw = j['version'];
        int? v;
        if (raw is int) {
          v = raw;
        } else if (raw is num) {
          v = raw.toInt();
        } else if (raw is String) {
          v = int.tryParse(raw);
        }
        if (v != null) {
          final sk = j['source_kind'];
          final isOrganiserAudio =
              sk is String && sk.trim() == 'organiser_audio';
          return (
            version: v,
            updatedAt: j['updated_at'] as String?,
            isOrganiserAudio: isOrganiserAudio,
          );
        }
      }
    } catch (_) {}
    return null;
  }
}
