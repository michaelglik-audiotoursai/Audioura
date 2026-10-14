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

import 'dart:convert';
import '../config/endpoints.dart';
import 'communities_models.dart';

export 'communities_models.dart';

/// The thin network client over Service.userDb.
class CommunitiesService {
  /// Create a community (owner). [body]'s `pass_products` are store product ids
  /// (audioura.pass.*) the community will offer; a free community passes none.
  static Future<Community?> create(Map<String, dynamic> body) async {
    final r = await Endpoints.post(Service.userDb, '/communities', body: body);
    if (r.statusCode == 201) {
      return Community.fromJson(jsonDecode(r.body) as Map<String, dynamic>);
    }
    return null;
  }

  /// Resolve an invite/share code to a community (the join flow). Returns null
  /// when there is no community with that code (so the Home search can fall
  /// through to its "no tour with that code" message).
  static Future<Community?> resolveByCode(String code, {String? userId}) async {
    final q = userId != null ? '?user_id=$userId' : '';
    final r = await Endpoints.get(Service.userDb, '/communities/by-code/$code$q');
    if (r.statusCode == 200) {
      return Community.fromJson(jsonDecode(r.body) as Map<String, dynamic>);
    }
    return null;
  }

  static Future<Community?> get(int id, {String? userId}) async {
    final q = userId != null ? '?user_id=$userId' : '';
    final r = await Endpoints.get(Service.userDb, '/communities/$id$q');
    if (r.statusCode == 200) {
      return Community.fromJson(jsonDecode(r.body) as Map<String, dynamic>);
    }
    return null;
  }

  /// Free join (free communities only). Returns the refreshed community, or
  /// null (e.g. 402 for a paid community — the caller then shows the passes).
  static Future<Community?> joinFree(int id, String userId) async {
    final r = await Endpoints.post(Service.userDb, '/communities/$id/join',
        body: {'user_id': userId});
    if (r.statusCode == 200) {
      return Community.fromJson(jsonDecode(r.body) as Map<String, dynamic>);
    }
    return null;
  }

  static Future<List<CommunityMapPin>> mapPins() async {
    final r = await Endpoints.get(Service.userDb, '/communities/map');
    if (r.statusCode == 200) {
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      final list = (j['communities'] as List?) ?? const [];
      return list
          .whereType<Map<String, dynamic>>()
          .map(CommunityMapPin.fromJson)
          .toList(growable: false);
    }
    return const [];
  }

  static Future<List<JoinedCommunity>> mine(String userId) async {
    final r =
        await Endpoints.get(Service.userDb, '/communities/mine?user_id=$userId');
    if (r.statusCode == 200) {
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      final list = (j['communities'] as List?) ?? const [];
      return list
          .whereType<Map<String, dynamic>>()
          .map(JoinedCommunity.fromJson)
          .toList(growable: false);
    }
    return const [];
  }

  static Future<bool> report(int id, {String? userId, String? reason}) async {
    final r = await Endpoints.post(Service.userDb, '/communities/$id/report',
        body: {'user_id': userId, 'reason': reason});
    return r.statusCode == 200;
  }

  static Future<bool> addEpisodes(
      int id, String ownerUserId, List<Map<String, String>> episodes) async {
    final r = await Endpoints.post(Service.userDb, '/communities/$id/episodes',
        body: {'owner_user_id': ownerUserId, 'episodes': episodes});
    return r.statusCode == 200;
  }

  static Future<bool> importFeed(int id, String ownerUserId, {String? feedUrl}) async {
    final body = <String, dynamic>{'owner_user_id': ownerUserId};
    if (feedUrl != null) body['feed_url'] = feedUrl;
    final r = await Endpoints.post(Service.userDb, '/communities/$id/import-feed',
        body: body);
    return r.statusCode == 200;
  }
}
