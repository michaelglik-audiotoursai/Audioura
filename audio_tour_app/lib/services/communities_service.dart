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
  ///
  /// [LOCAL-738 §3] Prefer [createResult] — it returns the server's real error
  /// + message on failure. This thin wrapper is kept for callers that only need
  /// the community (null on any failure).
  static Future<Community?> create(Map<String, dynamic> body) async =>
      (await createResult(body)).community;

  /// [LOCAL-738 §3 / Michael's review C2] Create a community and return the
  /// SERVER's outcome: on 201 the [Community]; on any error the server's `error`
  /// + `message` (e.g. "That community name is taken.", "$15 is not available
  /// as a pass price."). The form shows that exact message instead of the old
  /// generic guess. A transport failure (no HTTP answer) comes back with a
  /// short connection message and no community.
  static Future<CreateResult> createResult(Map<String, dynamic> body) async {
    try {
      final r = await Endpoints.post(Service.userDb, '/communities', body: body);
      final map = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 201 && map != null) {
        return CreateResult(community: Community.fromJson(map));
      }
      // A non-201 with a JSON error/message → show the server's own words.
      return CreateResult(
        error: map?['error'] as String?,
        message: (map?['message'] as String?) ??
            'Could not create the community (error ${r.statusCode}).',
      );
    } catch (_) {
      return const CreateResult(
        message: 'Could not reach the server. Check your connection and try '
            'again.',
      );
    }
  }

  /// [LOCAL-738 §2 / Michael's review C2b] The allowed pass PRICES for a NEW
  /// community, in price order, from the SERVER (GET /communities/pass-prices —
  /// built from the single APPLE_LIVE_PASS_PRODUCTS list). The create form's
  /// price chips come from here. Returns an empty list on any failure so the
  /// form can fall back to its $1/$5/$10/$20 default.
  static Future<List<PassPrice>> passPrices() async {
    try {
      final r = await Endpoints.get(Service.userDb, '/communities/pass-prices');
      final j = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && j != null) {
        final list = (j['prices'] as List?) ?? const [];
        return list
            .whereType<Map<String, dynamic>>()
            .map(PassPrice.fromJson)
            .toList(growable: false);
      }
    } catch (_) {}
    return const [];
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

  /// [LOCAL-728 / D691] Report a community, organiser or community tour to
  /// AUDIOURA. There is no user-level blocking — a member or organiser can only
  /// report. [reason] is a short reason code; [detail] is optional free text.
  /// Returns true on success (the caller then shows "Thanks — Audioura will
  /// review this.").
  static Future<bool> report(int id,
      {String? userId, String? reason, String? detail}) async {
    try {
      final body = <String, dynamic>{'user_id': userId, 'reason': reason};
      if (detail != null) body['detail'] = detail;
      final r = await Endpoints.post(Service.userDb, '/communities/$id/report',
          body: body);
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

  /// [LOCAL-754B / D658 addendum 2 / D708] Build (or edit) an ORGANISER-AUDIO
  /// tour from the organiser's own hosted audio (RSS/MP3 links). OWNER ONLY.
  /// [body] carries {user_id, tour_name, tour_type, visibility, rights_accepted,
  /// stops:[{name,lat,lng,text,audio_url}], tour_id? (edit)}. The server
  /// validates every audio URL and names the first failing stop.
  ///
  /// Returns [BuildAudioTourResult]: on 201/200 the {tour_id, source_kind,
  /// community_id, version}; on a 400/422 the server's error + message + the
  /// failing stop_name; on a transport error a short connection message.
  static Future<BuildAudioTourResult> buildAudioTour(
      int communityId, Map<String, dynamic> body) async {
    try {
      final r = await Endpoints.post(
          Service.userDb, '/communities/$communityId/build-audio-tour',
          body: body);
      final map = Endpoints.tryDecodeMap(r.body);
      if ((r.statusCode == 201 || r.statusCode == 200) && map != null) {
        final rawId = map['tour_id'];
        int? tourId;
        if (rawId is int) {
          tourId = rawId;
        } else if (rawId is num) {
          tourId = rawId.toInt();
        }
        return BuildAudioTourResult(
          tourId: tourId,
          sourceKind: map['source_kind'] as String?,
          communityId: communityId,
        );
      }
      return BuildAudioTourResult(
        error: map?['error'] as String?,
        stopName: map?['stop_name'] as String?,
        message: (map?['message'] as String?) ??
            'Could not build the tour (error ${r.statusCode}).',
      );
    } catch (_) {
      return const BuildAudioTourResult(
        message: 'Could not reach the server. Check your connection and try '
            'again.',
      );
    }
  }

  /// [LOCAL-760 / D709] OWNER-ONLY read of an organiser-audio tour's stops to
  /// PREFILL the builder when the organiser reopens it. Returns an
  /// [AudioTourDetail] on 200; null on 403 (a member), 404, or any transport
  /// error (the caller then opens the builder empty rather than failing).
  static Future<AudioTourDetail?> audioTourDetail(
      int communityId, int tourId, {String? userId}) async {
    try {
      final q = userId != null ? '?user_id=$userId' : '';
      final r = await Endpoints.get(Service.userDb,
          '/communities/$communityId/audio-tours/$tourId$q');
      final map = Endpoints.tryDecodeMap(r.body);
      if (r.statusCode == 200 && map != null) {
        return AudioTourDetail.fromJson(map);
      }
    } catch (_) {}
    return null;
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
}
