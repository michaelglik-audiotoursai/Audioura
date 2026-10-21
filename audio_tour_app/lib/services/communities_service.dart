// [LOCAL-690] Communities client — the networked client (D657 / D658 + addenda).
//
// The MODELS and pure UI rules live in communities_models.dart (dependency-free,
// unit-tested). This file adds the HTTP client over Service.userDb and re-
// exports the models so existing imports of communities_service.dart keep
// working.
//
//   POST /communities                         create (owner)
//   GET  /communities/<id>?user_id=...         the community page
//   GET  /communities/by-code/<code>?user_id   resolve an invite code (join)
//   POST /communities/<id>/join {user_id}      free join
//   POST /communities/<id>/episodes            owner adds MP3 links
//   POST /communities/<id>/import-feed         owner imports the RSS feed
//   GET  /communities/<id>/episodes?user_id    list episodes (active members)
//   POST /communities/<id>/report              report -> owner
//   GET  /communities/map                      Listed communities for the map
//   GET  /communities/mine?user_id=...          joined communities (Listen origin)
//
// A community PASS is bought through IapService's /purchases/verify flow with a
// pass product id (audioura.pass.*) and the community_id — the SAME path a tour
// purchase takes. This service only reads/writes the community model.

import '../config/endpoints.dart';
import 'communities_models.dart';

export 'communities_models.dart';

/// The thin network client over Service.userDb.
///
/// LOCAL-694: Service.userDb is NOT hosted by the Storied backend, so every
/// call here can fail with a connection-refused (SocketException) rather than
/// an HTTP status. Each method swallows transport errors and non-JSON bodies
/// and returns the SAME safe default it returns for a non-200 (null / empty
/// list / false), so the Communities screens render their empty state instead
/// of crashing. [isAvailable] lets a whole screen ask once and show a short
/// explanatory empty state.
class CommunitiesService {
  /// A cheap probe: is the Communities feature (Service.userDb) reachable on
  /// the current backend? Returns false on Storied (service absent). A screen
  /// can call this once to decide between its normal UI and a "Preview only"
  /// empty state. Never throws.
  static Future<bool> isAvailable() async {
    try {
      // /communities/map is an unauthenticated read; any HTTP answer (even a
      // 404) proves the service is reachable. Only a transport error means
      // "absent".
      await Endpoints.get(Service.userDb, '/communities/map');
      return true;
    } catch (e) {
      if (Endpoints.isServiceAbsentError(e)) return false;
      // An unexpected error is treated as unavailable too — safer than
      // pretending the feature works.
      return false;
    }
  }

  /// Create a community (owner). [body]'s `pass_products` are store product ids
  /// (audioura.pass.*) the community will offer; a free community passes none.
  static Future<Community?> create(Map<String, dynamic> body) async {
    try {
      final r = await Endpoints.post(Service.userDb, '/communities', body: body);
      final map = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 201 && map != null) {
        return Community.fromJson(map);
      }
    } catch (_) {}
    return null;
  }

  /// Resolve an invite/share code to a community (the join flow). Returns null
  /// when there is no community with that code (so the Home search can fall
  /// through to its "no tour with that code" message).
  static Future<Community?> resolveByCode(String code, {String? userId}) async {
    return (await resolveByCodeResult(code, userId: userId)).community;
  }

  /// [LOCAL-703 / D664] Resolve a code, distinguishing a CLOSED (archived)
  /// community from a non-existent one. The server returns 410 community_closed
  /// for an archived community (its invite code has stopped working); the Home
  /// search then shows "This community has closed." instead of the generic
  /// "no tour or community with that code". 200 → the community; 404/other →
  /// notFound; transport error → notFound (degrade gracefully).
  static Future<CodeResolution> resolveByCodeResult(String code,
      {String? userId}) async {
    try {
      final q = userId != null ? '?user_id=$userId' : '';
      final r =
          await Endpoints.get(Service.userDb, '/communities/by-code/$code$q');
      if (r.statusCode == 410) {
        return const CodeResolution(closed: true);
      }
      final map = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && map != null) {
        return CodeResolution(community: Community.fromJson(map));
      }
    } catch (_) {}
    return const CodeResolution();
  }

  static Future<Community?> get(int id, {String? userId}) async {
    try {
      final q = userId != null ? '?user_id=$userId' : '';
      final r = await Endpoints.get(Service.userDb, '/communities/$id$q');
      final map = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && map != null) {
        return Community.fromJson(map);
      }
    } catch (_) {}
    return null;
  }

  /// Free join (free communities only). Returns the refreshed community, or
  /// null (e.g. 402 for a paid community — the caller then shows the passes).
  static Future<Community?> joinFree(int id, String userId) async {
    try {
      final r = await Endpoints.post(Service.userDb, '/communities/$id/join',
          body: {'user_id': userId});
      final map = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && map != null) {
        return Community.fromJson(map);
      }
    } catch (_) {}
    return null;
  }

  static Future<List<CommunityMapPin>> mapPins() async {
    try {
      final r = await Endpoints.get(Service.userDb, '/communities/map');
      final j = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && j != null) {
        final list = (j['communities'] as List?) ?? const [];
        return list
            .whereType<Map<String, dynamic>>()
            .map(CommunityMapPin.fromJson)
            .toList(growable: false);
      }
    } catch (_) {}
    return const [];
  }

  static Future<List<JoinedCommunity>> mine(String userId) async {
    try {
      final r = await Endpoints.get(
          Service.userDb, '/communities/mine?user_id=$userId');
      final j = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && j != null) {
        final list = (j['communities'] as List?) ?? const [];
        return list
            .whereType<Map<String, dynamic>>()
            .map(JoinedCommunity.fromJson)
            .toList(growable: false);
      }
    } catch (_) {}
    return const [];
  }

  static Future<bool> report(int id, {String? userId, String? reason}) async {
    try {
      final r = await Endpoints.post(Service.userDb, '/communities/$id/report',
          body: {'user_id': userId, 'reason': reason});
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> addEpisodes(
      int id, String ownerUserId, List<Map<String, String>> episodes) async {
    try {
      final r = await Endpoints.post(Service.userDb, '/communities/$id/episodes',
          body: {'owner_user_id': ownerUserId, 'episodes': episodes});
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> importFeed(int id, String ownerUserId, {String? feedUrl}) async {
    try {
      final body = <String, dynamic>{'owner_user_id': ownerUserId};
      if (feedUrl != null) body['feed_url'] = feedUrl;
      final r = await Endpoints.post(
          Service.userDb, '/communities/$id/import-feed', body: body);
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// [LOCAL-700 §4] Is a community name free? Calls GET
  /// /communities/name-available?name= (case/space-insensitive, trimmed on the
  /// server). Returns true only on a 200 with available:true; ANY failure
  /// (transport error, non-200, malformed body) returns null so the caller can
  /// show a neutral "couldn't check" state rather than a false ✓ or ✗.
  static Future<bool?> nameAvailable(String name) async {
    try {
      final q = Uri.encodeQueryComponent(name);
      final r = await Endpoints.get(
          Service.userDb, '/communities/name-available?name=$q');
      final map = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && map != null && map['available'] is bool) {
        return map['available'] as bool;
      }
    } catch (_) {}
    return null;
  }

  /// [LOCAL-700 §4] Rotate a community's invite code (OWNER only). The old code
  /// stops working server-side. Returns the {join_code, invite_message} map on
  /// success, or null on any failure (owner mismatch 403, not found 404,
  /// transport error).
  static Future<Map<String, dynamic>?> regenerateCode(
      int id, String ownerUserId) async {
    try {
      final r = await Endpoints.post(
          Service.userDb, '/communities/$id/regenerate-code',
          body: {'owner_user_id': ownerUserId});
      final map = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && map != null) return map;
    } catch (_) {}
    return null;
  }

  /// [LOCAL-702 / D663 §1] The OWNER steps down as organiser (after a
  /// confirmation dialog). The community enters hand-over: closed to new
  /// members, "Looking for a new organiser". Returns the refreshed community, or
  /// null on failure.
  static Future<Community?> stepDown(int id, String ownerUserId) =>
      _postCommunity('/communities/$id/step-down',
          {'owner_user_id': ownerUserId});

  /// [LOCAL-702 / D663 §1] A member volunteers to take over a community in
  /// hand-over. Returns the refreshed community, or null on failure.
  static Future<Community?> offerOrganiser(int id, String userId) =>
      _postCommunity('/communities/$id/offer-organiser', {'user_id': userId});

  /// [LOCAL-702 / D663 §1] A volunteer withdraws their offer. Returns true on
  /// success.
  static Future<bool> withdrawOffer(int id, String userId) async {
    try {
      final r = await Endpoints.post(
          Service.userDb, '/communities/$id/withdraw-offer',
          body: {'user_id': userId});
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// [LOCAL-702 / D663 §1] The stepping-down owner picks a volunteer. Returns
  /// the refreshed community, or null on failure.
  static Future<Community?> pickOrganiser(
          int id, String ownerUserId, String memberUserId) =>
      _postCommunity('/communities/$id/pick-organiser',
          {'owner_user_id': ownerUserId, 'member_user_id': memberUserId});

  /// [LOCAL-702 / D663 §1] The picked member accepts and becomes the owner; the
  /// community reopens. Returns the refreshed community, or null on failure.
  static Future<Community?> acceptOrganiser(int id, String userId) =>
      _postCommunity('/communities/$id/accept-organiser', {'user_id': userId});

  /// [LOCAL-702 / D663 §1 (d)] The owner deletes a MEMBER-LESS community.
  /// Returns true on success; false when the community has members (409
  /// has_members), the caller is not the owner (403), or on any error.
  static Future<bool> deleteCommunity(int id, String ownerUserId) async {
    try {
      final r = await Endpoints.delete(Service.userDb, '/communities/$id',
          body: {'owner_user_id': ownerUserId});
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Shared helper: POST a body and parse the returned community page. Returns
  /// null on any non-200 or transport error (the screens then show their
  /// unchanged state).
  static Future<Community?> _postCommunity(
      String path, Map<String, dynamic> body) async {
    try {
      final r = await Endpoints.post(Service.userDb, path, body: body);
      final map = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && map != null) return Community.fromJson(map);
    } catch (_) {}
    return null;
  }

  // ─── [LOCAL-726 item 10] Block function (Apple Guideline 1.2) ──────────────

  /// A MEMBER blocks an organiser or another member within a community
  /// (kind 'member_block'): the blocked user's communities and community tours
  /// disappear from THIS user's own views. Affects only the blocker. Returns
  /// true on success.
  static Future<bool> blockUser(int communityId, String userId,
          String blockedUserId) =>
      _block(communityId, userId, blockedUserId, 'member_block', null);

  /// An ORGANISER removes and bars a member (kind 'organiser_bar'): the member's
  /// membership is removed and they cannot rejoin by code. Owner only. Returns
  /// true on success (false on 403 not-owner or any error).
  static Future<bool> barMember(int communityId, String ownerUserId,
          String memberUserId, {String? reason}) =>
      _block(communityId, ownerUserId, memberUserId, 'organiser_bar', reason);

  static Future<bool> _block(int communityId, String userId,
      String blockedUserId, String kind, String? reason) async {
    try {
      final body = <String, dynamic>{
        'user_id': userId,
        'blocked_user_id': blockedUserId,
        'kind': kind,
      };
      if (reason != null) body['reason'] = reason;
      final r = await Endpoints.post(
          Service.userDb, '/communities/$communityId/block', body: body);
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Lift a block the caller made. [kind] must match the block being lifted
  /// ('member_block' for a member's own block, 'organiser_bar' for an
  /// organiser's bar). Returns true on success.
  static Future<bool> unblockUser(int communityId, String userId,
      String blockedUserId, {String kind = 'member_block'}) async {
    try {
      final r = await Endpoints.post(
          Service.userDb, '/communities/$communityId/unblock',
          body: {
            'user_id': userId,
            'blocked_user_id': blockedUserId,
            'kind': kind,
          });
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// The OWNER's list of a community's members (for the member-row ⋯ menu).
  /// Owner only; returns an empty list on 403/any error.
  static Future<List<CommunityMember>> members(
      int communityId, String ownerUserId) async {
    try {
      final r = await Endpoints.get(Service.userDb,
          '/communities/$communityId/members?user_id=$ownerUserId');
      final j = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && j != null) {
        final list = (j['members'] as List?) ?? const [];
        return list
            .whereType<Map<String, dynamic>>()
            .map(CommunityMember.fromJson)
            .toList(growable: false);
      }
    } catch (_) {}
    return const [];
  }

  /// Everything THIS user has blocked, for Settings → Blocked. Returns an empty
  /// list on any error.
  static Future<List<CommunityBlock>> myBlocks(String userId) async {
    try {
      final r = await Endpoints.get(
          Service.userDb, '/communities/blocks?user_id=$userId');
      final j = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && j != null) {
        final list = (j['blocks'] as List?) ?? const [];
        return list
            .whereType<Map<String, dynamic>>()
            .map(CommunityBlock.fromJson)
            .toList(growable: false);
      }
    } catch (_) {}
    return const [];
  }
}
