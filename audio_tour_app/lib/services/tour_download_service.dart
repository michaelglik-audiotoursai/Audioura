// [LOCAL-713 / D675] TourDownloadService — the ONE download+save path.
//
// The download of a tour to the phone (GET /download-tour/<id> on map-delivery,
// then resolve, extract and record it in `saved_tours`) was private to
// home_screen. LOCAL-713 lifts the SAVE + a thin DOWNLOAD wrapper here so the
// community-page Download button runs the EXACT SAME path a Home/Listen
// download uses (D675 §3: "never build a second path"). home_screen delegates
// its _saveTourToMyTours to [saveTourToMyTours] here, so there is a single
// implementation of the on-phone record contract.
//
// Pure of widgets/BuildContext: it only touches the network, the filesystem and
// SharedPreferences, so the community page and Home share it without any UI
// coupling. The caller owns the dialogs/snackbars.

import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/endpoints.dart';
import '../screens/debug_log_viewer_screen.dart';
import 'community_downloads.dart';
import 'downloaded_tour_meta.dart';
import 'tour_pricing_service.dart';

/// The outcome of a community-page download attempt.
enum TourDownloadStatus {
  /// Downloaded and saved to My Tours.
  ok,

  /// Already on the phone (nothing to do).
  alreadyOnPhone,

  /// The server refused because the caller is not an active member of the
  /// tour's community (402 membership_required). The caller opens the community
  /// page to join — the SAME flow a paid tour takes (D663 §3).
  membershipRequired,

  /// A transport error or a non-200/402 response. The caller shows a retry.
  failed,
}

/// The result of a download attempt, with the community id to open on a
/// membership_required refusal.
class TourDownloadResult {
  final TourDownloadStatus status;
  final int? communityId;

  const TourDownloadResult(this.status, {this.communityId});
}

class TourDownloadService {
  /// Download a tour to the phone and save it to My Tours — the SAME server
  /// path a Home/Listen download uses (GET /download-tour/<tourId> on
  /// map-delivery, then [saveTourToMyTours]). [tourId] is the SERVER tour id of
  /// the row to pull; for a non-original language the caller passes the
  /// translation's own tour id (that is how Home downloads a language too —
  /// a translation is a separate tour id). Idempotent: a tour already on the
  /// phone returns [TourDownloadStatus.alreadyOnPhone] without re-downloading.
  ///
  /// A 402 membership_required (a community tour the device has no active pass
  /// for) returns [TourDownloadStatus.membershipRequired] with the community id,
  /// so the caller opens the community page to join — never a second purchase
  /// path (D663 §3 / D665).
  static Future<TourDownloadResult> downloadAndSave(
    int tourId, {
    Map<String, dynamic>? sourceItem,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      // Already on the phone? (exact match by server/edit tour id — same check
      // Home does before downloading.)
      final saved = prefs.getStringList('saved_tours') ?? [];
      for (final s in saved) {
        try {
          final m = json.decode(s) as Map<String, dynamic>;
          if (m['tour_id'] == tourId.toString() ||
              m['server_tour_id'] == tourId.toString()) {
            return const TourDownloadResult(TourDownloadStatus.alreadyOnPhone);
          }
        } catch (_) {}
      }

      final userId = prefs.getString('user_id') ?? '';
      final base =
          await Endpoints.url(Service.mapDelivery, '/download-tour/$tourId');
      final params = Map<String, String>.from(base.queryParameters);
      if (userId.isNotEmpty) params['user_id'] = userId;
      final uri = base.replace(queryParameters: params.isEmpty ? null : params);

      final response = await http
          .get(uri, headers: await Endpoints.apiHeaders(Service.mapDelivery))
          .timeout(const Duration(seconds: 120));

      if (response.statusCode == 200) {
        await saveTourToMyTours(tourId, response.bodyBytes,
            sourceItem: sourceItem);
        return const TourDownloadResult(TourDownloadStatus.ok);
      }
      if (response.statusCode == 402) {
        // [LOCAL-701 / D663 §3] A community tour needs an active membership. The
        // body carries the community id; the caller opens that page to join.
        int? communityId;
        try {
          final body = json.decode(response.body);
          if (body is Map && body['error'] == 'membership_required') {
            final cid = body['community_id'];
            if (cid is int) {
              communityId = cid;
            } else if (cid is num) {
              communityId = cid.toInt();
            }
          }
        } catch (_) {}
        return TourDownloadResult(TourDownloadStatus.membershipRequired,
            communityId: communityId);
      }
      return const TourDownloadResult(TourDownloadStatus.failed);
    } catch (e) {
      await DebugLogHelper.addDebugLog('DOWNLOAD_SVC: download failed: $e');
      return const TourDownloadResult(TourDownloadStatus.failed);
    }
  }

  /// [LOCAL-746] RE-DOWNLOAD a community tour already on the phone and replace
  /// its content IN PLACE — the member picks up the organiser's edit. Unlike
  /// [downloadAndSave] (which short-circuits a tour already on the phone with
  /// alreadyOnPhone), this REPLACES the extracted files in the SAME tour folder
  /// and bumps the saved record's `version`/`updated_at`, keeping the same list
  /// entry (same title, same `path`) so Listen opens the new audio in place.
  ///
  /// SAFETY (LOCAL-746 Req 2): a failed re-download leaves the OLD copy intact —
  /// the member is never left with nothing. The new content is downloaded and
  /// decoded FIRST; only once a valid ZIP is in hand are the old files replaced.
  /// A transport error, a non-200, or an undecodable body returns
  /// [TourDownloadStatus.failed] WITHOUT touching the folder or the record.
  ///
  /// [tourId] is the SERVER/download id (the saved record's server_tour_id);
  /// [newVersion] is the server's current version (for the "v2 · updated" label)
  /// and [updatedAt] the ISO date the server reports (may be null). Returns
  /// [TourDownloadStatus.ok] on a successful replace, [failed] otherwise.
  static Future<TourDownloadResult> reDownloadAndReplace(
    int tourId, {
    required int newVersion,
    String? updatedAt,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();

      // Locate the held record by its server/edit id. Nothing to replace if the
      // tour is not actually on the phone (the planner only picks held tours, so
      // this is a guard, not an expected path).
      final saved = prefs.getStringList('saved_tours') ?? [];
      int recordIndex = -1;
      Map<String, dynamic>? record;
      for (var i = 0; i < saved.length; i++) {
        try {
          final m = Map<String, dynamic>.from(json.decode(saved[i]) as Map);
          if (m['server_tour_id'] == tourId.toString() ||
              m['tour_id'] == tourId.toString()) {
            recordIndex = i;
            record = m;
            break;
          }
        } catch (_) {}
      }
      if (record == null || recordIndex < 0) {
        await DebugLogHelper.addDebugLog(
            'DOWNLOAD_SVC: re-download $tourId — no held record, nothing to '
            'replace');
        return const TourDownloadResult(TourDownloadStatus.failed);
      }

      // 1) Fetch the NEW content first. Any non-200 keeps the old copy.
      final userId = prefs.getString('user_id') ?? '';
      final base =
          await Endpoints.url(Service.mapDelivery, '/download-tour/$tourId');
      final params = Map<String, String>.from(base.queryParameters);
      if (userId.isNotEmpty) params['user_id'] = userId;
      final uri = base.replace(queryParameters: params.isEmpty ? null : params);

      final response = await http
          .get(uri, headers: await Endpoints.apiHeaders(Service.mapDelivery))
          .timeout(const Duration(seconds: 120));
      if (response.statusCode != 200) {
        await DebugLogHelper.addDebugLog(
            'DOWNLOAD_SVC: re-download $tourId failed '
            'status=${response.statusCode} — keeping old copy');
        return const TourDownloadResult(TourDownloadStatus.failed);
      }

      final zipBytes = response.bodyBytes;

      // 2) Decode the new ZIP IN MEMORY before touching the old files, so an
      // undecodable body never destroys the working copy.
      final Archive archive;
      try {
        archive = ZipDecoder().decodeBytes(zipBytes);
      } catch (e) {
        await DebugLogHelper.addDebugLog(
            'DOWNLOAD_SVC: re-download $tourId — ZIP decode failed ($e), '
            'keeping old copy');
        return const TourDownloadResult(TourDownloadStatus.failed);
      }

      final path = record['path'] as String?;
      if (path == null || path.isEmpty) {
        return const TourDownloadResult(TourDownloadStatus.failed);
      }

      // 3) Replace the content IN PLACE. On web, the files live in prefs keyed by
      // the dir name; on device they live under the tour folder. We overwrite the
      // extracted files and tour.zip in the SAME location.
      if (kIsWeb) {
        final dirName = path.startsWith('web_tours/')
            ? path.substring('web_tours/'.length)
            : path;
        await prefs.setString('tour_zip_$dirName', base64Encode(zipBytes));
        for (final file in archive) {
          if (file.isFile) {
            final data = file.content as List<int>;
            await prefs.setString(
                'tour_file_${dirName}_${file.name}', base64Encode(data));
            String mimeType = 'application/octet-stream';
            if (file.name.endsWith('.html')) {
              mimeType = 'text/html';
            } else if (file.name.endsWith('.mp3')) {
              mimeType = 'audio/mpeg';
            } else if (file.name.endsWith('.json')) {
              mimeType = 'application/json';
            }
            await prefs.setString(
                'tour_file_${dirName}_${file.name}_mime', mimeType);
          }
        }
      } else {
        final dir = Directory(path);
        await dir.create(recursive: true);
        // Remove the previous extracted files (but keep the folder) so a shorter
        // new tour does not leave orphan stops behind. Then write the new ZIP +
        // extracted files.
        try {
          for (final entity in dir.listSync()) {
            if (entity is File) {
              await entity.delete();
            }
          }
        } catch (_) {}
        final zipFile = File('$path/tour.zip');
        await zipFile.writeAsBytes(zipBytes);
        for (final file in archive) {
          if (file.isFile) {
            final data = file.content as List<int>;
            final extractedFile = File('$path/${file.name}');
            await extractedFile.create(recursive: true);
            await extractedFile.writeAsBytes(data);
          }
        }
      }

      // [LOCAL-754B] If the edited tour is organiser-audio, re-fetch the remote
      // audio into the SAME folder so the replaced copy plays offline too. On
      // web the files live in prefs keyed by the dir name; on device beside
      // index.html. A failing stop keeps the (now replaced) files but surfaces
      // as failed so the member can retry.
      try {
        if (kIsWeb) {
          final dirName = path.startsWith('web_tours/')
              ? path.substring('web_tours/'.length)
              : path;
          await _fetchRemoteAudioWeb(zipBytes, dirName, prefs);
        } else {
          await _fetchRemoteAudioDevice(zipBytes, path);
        }
      } catch (e) {
        await DebugLogHelper.addDebugLog(
            'DOWNLOAD_SVC: re-download $tourId remote-audio fetch failed ($e)');
        return const TourDownloadResult(TourDownloadStatus.failed);
      }

      // 4) Bump the saved record's version/updated_at (and stop count) IN PLACE —
      // same title, same path, so Listen keeps the one entry and now opens v2.
      record['version'] = newVersion;
      record['tour_version'] = newVersion;
      if (updatedAt != null && updatedAt.isNotEmpty) {
        record['updated_at'] = updatedAt;
      }
      try {
        final stops = await _countTourStops(zipBytes);
        if (stops > 0) record['stops'] = stops.toString();
      } catch (_) {}

      saved[recordIndex] = json.encode(record);
      await prefs.setStringList('saved_tours', saved);
      // [LOCAL-752 C] A re-download also un-deletes the tour (same reason as the
      // initial save): drop its id from `deleted_tour_ids` so the refresh keeps
      // tracking it.
      await clearDeletedTourIds(prefs, [tourId]);
      await DebugLogHelper.addDebugLog(
          'DOWNLOAD_SVC: re-download $tourId replaced in place → v$newVersion');
      return const TourDownloadResult(TourDownloadStatus.ok);
    } catch (e) {
      await DebugLogHelper.addDebugLog(
          'DOWNLOAD_SVC: re-download $tourId threw ($e) — keeping old copy');
      return const TourDownloadResult(TourDownloadStatus.failed);
    }
  }

  /// Save a downloaded tour ZIP to My Tours — the SINGLE implementation of the
  /// on-phone record contract (lifted verbatim from home_screen so Home and the
  /// community page write identical `saved_tours` records). [downloadId] is the
  /// server/download tour id; [zipBytes] is the ZIP body from /download-tour.
  static Future<void> saveTourToMyTours(
    int downloadId,
    List<int> zipBytes, {
    Map<String, dynamic>? sourceItem,
  }) async {
    final tourId = downloadId;
    try {
      await DebugLogHelper.addDebugLog(
          'DOWNLOAD_SVC: SAVE - Starting saveTourToMyTours');

      final prefs = await SharedPreferences.getInstance();

      String appDirPath;
      if (kIsWeb) {
        appDirPath = 'web_storage';
      } else {
        final appDir = await getApplicationDocumentsDirectory();
        appDirPath = appDir.path;
      }

      final resolveUri = await Endpoints.url(
          Service.tourIdResolution, '/tour/$tourId/resolve');
      final resolutionResponse = await http.get(resolveUri,
          headers: await Endpoints.apiHeaders(Service.tourIdResolution));

      String editTourId;
      String baseTourName = 'Downloaded Tour';
      bool isEditable = false;
      int? backendStopsCount;

      if (resolutionResponse.statusCode == 200) {
        try {
          final resolutionData = json.decode(resolutionResponse.body);
          if (resolutionData['status'] == 'success') {
            editTourId = resolutionData['edit_tour_id'] ?? tourId.toString();
            baseTourName = resolutionData['tour_name'] ?? 'Downloaded Tour';
            isEditable = resolutionData['editable'] ?? false;
            backendStopsCount = resolutionData['stops_count'];
          } else {
            throw Exception('Resolution failed: ${resolutionData['message']}');
          }
        } catch (e) {
          throw Exception('Failed to resolve tour ID $tourId: $e');
        }
      } else {
        // [LEAD review of LOCAL-713] Keep Home's original behaviour: surface the
        // server's own reason when it gives one (it explains holds, paid tours…).
        // [LOCAL-717 / D677 §4] Always log the raw HTTP status + body of the
        // failing /resolve so a dropped tour (e.g. tour 370's 409) is findable
        // in the logs instead of vanishing — the batch path also names it to the
        // user, but the single path's log must carry the same detail.
        await DebugLogHelper.addDebugLog(
            'DOWNLOAD_SVC: /tour/$tourId/resolve FAILED '
            'status=${resolutionResponse.statusCode} body=${resolutionResponse.body}');
        String errorMessage;
        try {
          final errorData = json.decode(resolutionResponse.body);
          errorMessage = 'Tour "$baseTourName" (ID: $tourId) could not be '
              'downloaded.\n\nError: ${errorData['message'] ?? 'Unknown error'}'
              '\n\nPlease contact your administrator with this information.';
        } catch (_) {
          errorMessage = 'Tour download failed (ID: $tourId).\n\nServer returned '
              'error ${resolutionResponse.statusCode}.\n\nPlease contact your '
              'administrator with this information.';
        }
        throw Exception(errorMessage);
      }

      final savedTours = prefs.getStringList('saved_tours') ?? [];
      final existingTours = savedTours
          .map((tour) => json.decode(tour) as Map<String, dynamic>)
          .toList();

      String finalTourName = baseTourName;
      int version = 1;
      while (existingTours.any((tour) => tour['title'] == finalTourName)) {
        version++;
        finalTourName = '$baseTourName (v$version)';
      }

      final safeName = finalTourName.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
      String tourDirPath;

      if (kIsWeb) {
        tourDirPath = 'web_tours/${safeName}_$editTourId';
      } else {
        final tourDir = Directory('$appDirPath/tours/${safeName}_$editTourId');
        await tourDir.create(recursive: true);
        tourDirPath = tourDir.path;
      }

      if (kIsWeb) {
        final zipBase64 = base64Encode(zipBytes);
        await prefs.setString('tour_zip_${safeName}_$editTourId', zipBase64);
        final archive = ZipDecoder().decodeBytes(zipBytes);
        for (final file in archive) {
          final filename = file.name;
          if (file.isFile) {
            final data = file.content as List<int>;
            final fileBase64 = base64Encode(data);
            await prefs.setString(
                'tour_file_${safeName}_${editTourId}_$filename', fileBase64);
            String mimeType = 'application/octet-stream';
            if (filename.endsWith('.html')) {
              mimeType = 'text/html';
            } else if (filename.endsWith('.mp3')) {
              mimeType = 'audio/mpeg';
            } else if (filename.endsWith('.json')) {
              mimeType = 'application/json';
            }
            await prefs.setString(
                'tour_file_${safeName}_${editTourId}_${filename}_mime',
                mimeType);
          }
        }
      } else {
        final zipFile = File('$tourDirPath/tour.zip');
        await zipFile.writeAsBytes(zipBytes);
        final archive = ZipDecoder().decodeBytes(zipBytes);
        for (final file in archive) {
          final filename = file.name;
          if (file.isFile) {
            final data = file.content as List<int>;
            final extractedFile = File('$tourDirPath/$filename');
            await extractedFile.create(recursive: true);
            await extractedFile.writeAsBytes(data);
          }
        }
      }

      // [LOCAL-754B / D658 addendum 2] Organiser-audio tour: the package has NO
      // MP3, only remote_audio.json ({stop N → the organiser's URL}). Fetch each
      // URL FROM THE ORGANISER'S HOST and save it as audio_N.mp3 next to
      // index.html, so the tour plays offline and the map/voice-control behave
      // exactly like a generated tour. One failing stop → the whole save fails
      // (no half-saved tour), naming the stop in the thrown message.
      await _fetchRemoteAudioIfPresent(zipBytes, tourDirPath, safeName,
          editTourId, prefs);

      int actualStops;
      if (backendStopsCount != null && backendStopsCount > 0) {
        actualStops = backendStopsCount;
      } else {
        actualStops = await _countTourStops(zipBytes);
      }

      final tourData = {
        'title': finalTourName,
        'path': tourDirPath,
        'created': DateTime.now().toIso8601String(),
        'stops': actualStops.toString(),
        'original_request': baseTourName,
        'tour_id': editTourId,
        // [LOCAL-719 / D677 addendum 1] Stamp the NUMERIC server/download id onto
        // the record. The download snackbar's "View" offers this id (the map
        // listing's `tour['id']`), and the pure planner matches a saved entry by
        // it (server_tour_id / tour_id / parent_server_tour_id). Without it a
        // plain downloaded original — whose `tour_id` is the NON-numeric edit id
        // (e.g. "2027698c") — matched nothing, so "View" fell back to merely
        // highlighting instead of opening (observed live on the emulator). It is
        // also the id the player keys `/unlock-state` on (LOCAL-677B).
        'server_tour_id': tourId.toString(),
        'editable': isEditable,
        'is_web_storage': kIsWeb,
      };
      if (sourceItem != null) {
        final v = sourceItem['version'];
        final updatedAt = sourceItem['updated_at'];
        if (v != null) tourData['version'] = v;
        if (updatedAt != null) tourData['updated_at'] = updatedAt;
        // [LOCAL-754B / D708] Carry the tour's source_kind onto the saved
        // record so Listen can hide Translate for an organiser-audio tour (the
        // server also refuses it 403). An ordinary/generated tour has none.
        final sk = sourceItem['source_kind'];
        if (sk is String && sk.trim().isNotEmpty) {
          tourData['source_kind'] = sk.trim();
        }
        // [LOCAL-745] Carry the community id onto the saved record so My Tours
        // can show Edit only to the community organiser (canEditTour). A
        // community download's sourceItem (new-tours row / map listing /
        // community page tour) carries community_id; an ordinary tour has none.
        final cid = sourceItem['community_id'];
        if (cid is int) {
          tourData['community_id'] = cid;
        } else if (cid is num) {
          tourData['community_id'] = cid.toInt();
        } else if (cid is String && int.tryParse(cid.trim()) != null) {
          tourData['community_id'] = int.parse(cid.trim());
        }
      }

      await _stampPaidSnapshot(tourData, tourId, sourceItem);

      savedTours.add(json.encode(tourData));
      await prefs.setStringList('saved_tours', savedTours);
      // [LOCAL-752 C] An explicit download un-deletes the tour: remove its id
      // from `deleted_tour_ids` so a later sync refresh (RefreshPlanner) no longer
      // skips it. Covers both the download id and the resolved edit id.
      await clearDeletedTourIds(prefs, [downloadId, editTourId]);
      await DebugLogHelper.addDebugLog(
          'DOWNLOAD_SVC: SAVE - saved "$finalTourName" at $tourDirPath');
    } catch (e) {
      await DebugLogHelper.addDebugLog('DOWNLOAD_SVC: Error saving tour: $e');
      rethrow;
    }
  }

  /// Stamp the paid snapshot onto the record (lifted from home_screen so the
  /// record contract is identical). A community tour is covered by the pass, so
  /// this is inert for it (no price), but the same fields are written so My
  /// Tours / the player read a uniform record.
  static Future<void> _stampPaidSnapshot(
    Map<String, dynamic> tourData,
    int downloadId,
    Map<String, dynamic>? sourceItem,
  ) async {
    try {
      final serverId = downloadId.toString();
      bool isPaid = false;
      int? priceTier;
      String priceLabel = 'Free';
      String? originalLanguage;
      if (sourceItem != null) {
        final rawTier = sourceItem['price_tier'];
        if (rawTier is int) {
          priceTier = rawTier;
        } else if (rawTier is num) {
          priceTier = rawTier.toInt();
        } else if (rawTier is String) {
          priceTier = int.tryParse(rawTier);
        }
        // [LOCAL-740 / B3] A tour is PAID when the row says so OR carries a
        // positive price tier. The old code trusted ONLY `is_paid == true`, so
        // a tour that arrived with `price_tier > 0` but no explicit `is_paid`
        // flag (how map-delivery sends priced rows, and how a tour bought via
        // the pay-per-download / `tour_unlocks` path reaches the save) was
        // stamped `is_paid:false`. The delete-confirmation then treated it as
        // free and showed no warning (Michael's $5 "Massachusetts politics"
        // tour). This now matches every other paid check in the app
        // (home_screen, DeleteTourPrompt.isPaidTour): is_paid OR price_tier > 0.
        isPaid = sourceItem['is_paid'] == true ||
            (priceTier != null && priceTier > 0);
        final rawLabel = sourceItem['price_label'];
        if (rawLabel is String && rawLabel.trim().isNotEmpty) {
          priceLabel = rawLabel.trim();
        }
        final rawLang = sourceItem['original_language'];
        if (rawLang is String && rawLang.trim().isNotEmpty) {
          originalLanguage = rawLang.trim();
        }
      }

      bool unlocked = !isPaid;
      // [LOCAL-740 / B3] Consult the server unlock-state as a fallback. This
      // does double duty: (a) for a tour already known paid it records that THIS
      // device unlocked it (so the offline lock lifts), and (b) for a tour the
      // inline row did NOT mark paid, a `state.isPaid` of true reveals it IS a
      // paid tour the listener unlocked via `tour_unlocks` — so we stamp it paid
      // and the delete warning shows. Never throws out; if the check fails we
      // keep whatever the inline row told us.
      try {
        final state = await TourPricingService.unlockState(serverId);
        if (state.isPaid) {
          isPaid = true;
          unlocked = state.unlocked;
        } else if (isPaid && state.unlocked) {
          unlocked = true;
        }
      } catch (_) {}

      final meta = DownloadedTourMeta(
        serverTourId: serverId,
        priceTier: priceTier,
        isPaid: isPaid,
        unlocked: unlocked,
        priceLabel: priceLabel,
        originalLanguage: originalLanguage,
        tourVersion: null,
      );
      tourData.addAll(meta.toRecordFields());
    } catch (e) {
      await DebugLogHelper.addDebugLog('DOWNLOAD_SVC: paid snapshot skipped: $e');
    }
  }

  /// [LOCAL-754B / D658 addendum 2] Organiser-audio support. If the package
  /// contains remote_audio.json ({stop N → the organiser's audio URL}), download
  /// each URL and save it as audio_N.mp3 so the tour plays offline exactly like
  /// a generated tour. The audio lives on the ORGANISER's host — Audioura never
  /// stores it — so this is the phone fetching it directly. A package with NO
  /// remote_audio.json (an ordinary/generated tour that ships its own MP3s) is a
  /// no-op. One failing stop throws, NAMING the stop, so the caller fails the
  /// whole save rather than leaving a half-saved tour (D754).
  static Future<void> _fetchRemoteAudioIfPresent(
    List<int> zipBytes,
    String tourDirPath,
    String safeName,
    String editTourId,
    SharedPreferences prefs,
  ) async {
    if (kIsWeb) {
      final dirName = '${safeName}_$editTourId';
      await _fetchRemoteAudioWeb(zipBytes, dirName, prefs);
    } else {
      await _fetchRemoteAudioDevice(zipBytes, tourDirPath);
    }
  }

  /// Parse remote_audio.json from the ZIP into an ordered {stopNumber: url} map,
  /// or an empty map when the tour has no remote audio (an ordinary tour).
  static Map<int, String> _remoteAudioMap(List<int> zipBytes) {
    try {
      final archive = ZipDecoder().decodeBytes(zipBytes);
      for (final file in archive) {
        if (file.name == 'remote_audio.json' && file.isFile) {
          final decoded = json.decode(utf8.decode(file.content as List<int>));
          if (decoded is Map) {
            final out = <int, String>{};
            decoded.forEach((k, v) {
              final n = int.tryParse('$k');
              if (n != null && v is String && v.trim().isNotEmpty) {
                out[n] = v.trim();
              }
            });
            return out;
          }
        }
      }
    } catch (_) {}
    return const {};
  }

  /// Device: fetch each remote audio URL and write audio_N.mp3 beside
  /// index.html. Throws (naming the stop) on a URL that will not download, so
  /// the caller can fail the whole save (no half-saved tour).
  static Future<void> _fetchRemoteAudioDevice(
      List<int> zipBytes, String tourDirPath) async {
    final remote = _remoteAudioMap(zipBytes);
    if (remote.isEmpty) return;
    for (final entry in remote.entries) {
      final n = entry.key;
      final url = entry.value;
      try {
        final resp = await http
            .get(Uri.parse(url))
            .timeout(const Duration(seconds: 120));
        if (resp.statusCode != 200 || resp.bodyBytes.isEmpty) {
          throw Exception('stop $n: HTTP ${resp.statusCode}');
        }
        final f = File('$tourDirPath/audio_$n.mp3');
        await f.create(recursive: true);
        await f.writeAsBytes(resp.bodyBytes);
      } catch (e) {
        await DebugLogHelper.addDebugLog(
            'DOWNLOAD_SVC: remote audio for stop $n failed: $e');
        throw Exception('Audio for stop $n could not be downloaded. '
            'Please retry.');
      }
    }
  }

  /// Web: fetch each remote audio URL and store it in prefs as
  /// tour_file_<dir>_audio_N.mp3 (+ its mime) so the web player serves it from
  /// local storage, matching the extracted-file scheme. Throws (naming the
  /// stop) on failure.
  static Future<void> _fetchRemoteAudioWeb(
      List<int> zipBytes, String dirName, SharedPreferences prefs) async {
    final remote = _remoteAudioMap(zipBytes);
    if (remote.isEmpty) return;
    for (final entry in remote.entries) {
      final n = entry.key;
      final url = entry.value;
      try {
        final resp = await http
            .get(Uri.parse(url))
            .timeout(const Duration(seconds: 120));
        if (resp.statusCode != 200 || resp.bodyBytes.isEmpty) {
          throw Exception('stop $n: HTTP ${resp.statusCode}');
        }
        await prefs.setString('tour_file_${dirName}_audio_$n.mp3',
            base64Encode(resp.bodyBytes));
        await prefs.setString(
            'tour_file_${dirName}_audio_$n.mp3_mime', 'audio/mpeg');
      } catch (e) {
        await DebugLogHelper.addDebugLog(
            'DOWNLOAD_SVC: remote audio (web) for stop $n failed: $e');
        throw Exception('Audio for stop $n could not be downloaded. '
            'Please retry.');
      }
    }
  }

  /// Count stops in a tour ZIP (lifted from home_screen).
  static Future<int> _countTourStops(List<int> zipBytes) async {
    try {
      final archive = ZipDecoder().decodeBytes(zipBytes);
      for (final file in archive) {
        if (file.name == 'tour.json' && file.isFile) {
          final jsonContent = String.fromCharCodes(file.content as List<int>);
          final tourData = json.decode(jsonContent);
          if (tourData['stops'] != null && tourData['stops'] is List) {
            return (tourData['stops'] as List).length;
          }
          int audioCount = 0;
          for (final audioFile in archive) {
            if (audioFile.name.endsWith('.mp3') && audioFile.isFile) {
              audioCount++;
            }
          }
          return audioCount > 0 ? audioCount : 10;
        }
      }
      int audioCount = 0;
      for (final file in archive) {
        if (file.name.endsWith('.mp3') && file.isFile) {
          audioCount++;
        }
      }
      if (audioCount > 0) return audioCount;
      // [LOCAL-754B] An organiser-audio package ships NO mp3 (the audio is
      // remote); count its remote_audio.json entries instead.
      for (final file in archive) {
        if (file.name == 'remote_audio.json' && file.isFile) {
          try {
            final decoded = json.decode(utf8.decode(file.content as List<int>));
            if (decoded is Map && decoded.isNotEmpty) return decoded.length;
          } catch (_) {}
        }
      }
      return 10;
    } catch (e) {
      await DebugLogHelper.addDebugLog('DOWNLOAD_SVC: Error counting stops: $e');
      return 10;
    }
  }
}
