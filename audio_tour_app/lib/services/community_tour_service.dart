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
}
