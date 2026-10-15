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
    try {
      final q = userId != null ? '?user_id=$userId' : '';
      final r =
          await Endpoints.get(Service.userDb, '/communities/by-code/$code$q');
      final map = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && map != null) {
        return Community.fromJson(map);
      }
    } catch (_) {}
    return null;
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
}
