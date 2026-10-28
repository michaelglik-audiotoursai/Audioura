import 'dart:convert';
import 'dart:io';
import 'package:archive/archive.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config/endpoints.dart';
import '../screens/debug_log_viewer_screen.dart';
import 'translation_service.dart';
import 'failure_reporter.dart';
import 'saved_tours_store.dart';

/// Shared translation-download logic used by both HomeScreen (at download time)
/// and MyToursScreen (translate existing tours on Listen page).
class TourTranslationHelper {
  /// Canonical list of supported translation languages.
  static const availableLanguages = <String, String>{
    'ru': 'Russian',
    'zh': 'Chinese',
    'fr': 'French',
    'es': 'Spanish',
    'de': 'German',
    'ja': 'Japanese',
    'ko': 'Korean',
    'pt': 'Portuguese',
    'it': 'Italian',
    'ar': 'Arabic',
  };

  /// Returns true if the tour metadata indicates this is a translated tour.
  static bool isTranslation(Map<String, dynamic> tour) {
    final val = tour['is_translation'];
    return val == true || val == 'true';
  }

  /// [LOCAL-780] The message shown when the non-English download failed on the
  /// Generate screen and the app falls back to playing the English copy, so the
  /// listener is never left with silence and no explanation. Names the language
  /// in full (e.g. "Russian") from [TourTranslationHelper.availableLanguages],
  /// falling back to the upper-cased code for an unknown one. PURE so the one
  /// wording is asserted in a test and reused from the screen.
  static String translationFallbackMessage(String langCode) {
    final name = availableLanguages[langCode] ?? langCode.toUpperCase();
    return "Couldn't download the $name version — showing English.";
  }

  /// [LOCAL-677B / D653] Should the ENGLISH tour be pulled to the phone?
  /// English is downloaded only when it is a selected language. A null
  /// selection means the default (English only). The server may still use
  /// English as an internal translation template regardless; this governs only
  /// what the LISTENER receives.
  static bool shouldDownloadEnglish(List<String>? languages) =>
      languages == null || languages.contains('en');

  /// [LOCAL-677B / D653] The non-English languages to download as translations.
  static List<String> translationLanguages(List<String>? languages) =>
      (languages ?? const <String>[]).where((l) => l != 'en').toList();

  /// Translates a tour and downloads each translated version as a new entry.
  /// Returns a list of language codes that failed.
  /// The English tour must already be saved before calling this.
  ///
  /// [LOCAL-760 / D708] When the server refused the whole request with 403
  /// translation_not_offered (a broadcast / organiser-audio tour), this is
  /// recorded in [lastTranslationNotOffered] so the caller shows the D708
  /// broadcast message rather than the misleading "older tour" wording. The flag
  /// is reset at the start of every call.
  static bool lastTranslationNotOffered = false;

  static Future<List<String>> downloadTranslatedVersions({
    required int tourId,
    required List<String> languages,
    required String parentEditTourId,
    Map<String, dynamic>? sourceItem,
  }) async {
    lastTranslationNotOffered = false;
    final failures = <String>[];
    final nonEnglish = languages.where((l) => l != 'en').toList();
    if (nonEnglish.isEmpty) return failures;

    try {
      await DebugLogHelper.addDebugLog('TRANSLATE: Requesting translation for tourId=$tourId languages: ${nonEnglish.join(", ")}');
      final result = await TranslationService.translateTour(tourId: tourId, languages: nonEnglish);

      // [LOCAL-760 / D708] A broadcast tour is refused 403 translation_not_offered
      // for the whole request — every requested language failed for the SAME
      // reason, so record it for the caller's message.
      if (result['status'] == 'error' &&
          result['error_code'] == 'translation_not_offered') {
        lastTranslationNotOffered = true;
        for (final lang in nonEnglish) failures.add(lang);
        await DebugLogHelper.addDebugLog(
            'TRANSLATE: refused translation_not_offered (broadcast tour)');
        return failures;
      }

      if (result['status'] == 'completed') {
        final translatedIds = _extractTranslatedIds(result);
        // [LOCAL-666] Per-language version/updated_at from the translate-with-audio
        // response, so each saved translation carries the SOURCE tour's version and
        // the My Tours list shows "v{n} · updated {Mon D}" for it just like English.
        final translations = result['translations'] as Map<String, dynamic>?;
        if (translatedIds != null) {
          for (final lang in nonEnglish) {
            final translatedId = translatedIds[lang];
            if (translatedId == null) {
              failures.add(lang);
              await DebugLogHelper.addDebugLog('TRANSLATE: Translation failed for $lang (id=null or status=failed)');
              continue;
            }
            final langEntry = translations?[lang];
            final version = (langEntry is Map) ? langEntry['version'] : null;
            final updatedAt = (langEntry is Map) ? langEntry['updated_at'] : null;
            try {
              // [LOCAL-677C / D654] Carry user_id so the server gate decides
              // the PER-LANGUAGE pay-before-download (D653): a paid translation
              // the device has not unlocked is refused here with 402 and the
              // language is reported as a failure (never a crash). [LOCAL-780]
              // Built by the ONE shared helper so the user_id is always
              // attached (the same fix the Generate screen needed).
              final tprefs = await SharedPreferences.getInstance();
              final tUserId = tprefs.getString('user_id') ?? '';
              // [LOCAL-794] Timestamped markers around every await on the path
              // from "translate completed" to "download-tour returns", so a
              // live run shows exactly which await ate Michael's 2.5-min gap
              // (DebugLogHelper itself is capped at 75 lines, so it is cheap).
              final tDlStart = DateTime.now();
              await DebugLogHelper.addDebugLog('TRANSLATE/MEASURE: ($lang) building download-tour URL');
              final translatedUri = await Endpoints.downloadTourUrl(translatedId);
              final tHeaders = await Endpoints.apiHeaders(Service.mapDelivery);
              await DebugLogHelper.addDebugLog(
                  'TRANSLATE/MEASURE: ($lang) URL+headers ready in '
                  '${DateTime.now().difference(tDlStart).inMilliseconds}ms — GET download-tour/$translatedId');
              final tGetStart = DateTime.now();
              final translatedResponse = await http.get(translatedUri, headers: tHeaders).timeout(const Duration(seconds: 120));
              await DebugLogHelper.addDebugLog(
                  'TRANSLATE/MEASURE: ($lang) download-tour HTTP ${translatedResponse.statusCode} in '
                  '${DateTime.now().difference(tGetStart).inMilliseconds}ms '
                  '(${translatedResponse.bodyBytes.length} bytes)');
              if (translatedResponse.statusCode == 200) {
                final prefs = await SharedPreferences.getInstance();
                final appDir = await getApplicationDocumentsDirectory();
                // [LOCAL-693B / D660 LEAD] Consumption is decided SERVER-SIDE
                // (the server spends the purchase when it finishes streaming the
                // zip). A paid translation is its own purchase (D653). The app
                // only reports FAILURE: if the bytes arrived but the zip cannot
                // be saved/validated, POST /tour/<id>/download-failed so the
                // server restores that purchase once (within 24h). No confirm on
                // success.
                try {
                  final tSaveStart = DateTime.now();
                  await DebugLogHelper.addDebugLog('TRANSLATE/MEASURE: ($lang) saving translated tour $translatedId');
                  await _saveTranslatedTour(translatedId, translatedResponse.bodyBytes, appDir.path, prefs, parentEditTourId, lang,
                      version: version, updatedAt: updatedAt, sourceItem: sourceItem, parentServerTourId: tourId);
                  await DebugLogHelper.addDebugLog(
                      'TRANSLATE/MEASURE: ($lang) save complete in '
                      '${DateTime.now().difference(tSaveStart).inMilliseconds}ms');
                } catch (saveError) {
                  failures.add(lang);
                  await DebugLogHelper.addDebugLog(
                      'TRANSLATE: save/validate failed ($lang) after bytes — '
                      'reporting download-failed: $saveError');
                  // [LOCAL-785 / D723] This save/validate-after-download failure
                  // was SILENT (only a debug log). Record it so it is counted.
                  FailureReporter.instance.report(
                    surface: 'translate',
                    errorCode: 'translation_save_or_validate_failed',
                    exceptionType: saveError.runtimeType.toString(),
                    message: 'save/validate failed ($lang) after bytes: $saveError',
                    tourId: translatedId.toString(),
                  );
                  final consumes =
                      translatedResponse.headers['x-download-consumes-unlock'];
                  if (consumes == '1') {
                    try {
                      await Endpoints.post(
                        Service.mapDelivery,
                        '/tour/$translatedId/download-failed',
                        body: {'user_id': tUserId, 'reason': 'save_or_validate_failed'},
                        timeout: const Duration(seconds: 15),
                      );
                    } catch (e) {
                      await DebugLogHelper.addDebugLog(
                          'TRANSLATE: download-failed report failed ($lang): $e');
                    }
                  }
                  continue;
                }
                await DebugLogHelper.addDebugLog('TRANSLATE: Saved translated tour ($lang) ID: $translatedId');
              } else {
                failures.add(lang);
                await DebugLogHelper.addDebugLog('TRANSLATE: Download failed ($lang): ${translatedResponse.statusCode}');
              }
            } catch (e) {
              failures.add(lang);
              await DebugLogHelper.addDebugLog('TRANSLATE: Error downloading ($lang): $e');
            }
          }
        } else {
          for (final lang in nonEnglish) failures.add(lang);
          await DebugLogHelper.addDebugLog('TRANSLATE: Unrecognized response shape');
        }
      } else {
        for (final lang in nonEnglish) failures.add(lang);
        await DebugLogHelper.addDebugLog('TRANSLATE: Failed: ${result["message"]}');
      }
    } catch (e) {
      for (final lang in nonEnglish) failures.add(lang);
      await DebugLogHelper.addDebugLog('TRANSLATE: Error: $e');
    }
    return failures;
  }

  /// [LOCAL-680] The server row id of [lang]'s translation of [tourId], creating
  /// the translation if it does not exist yet. A paid translation is bought by
  /// THIS id (D653: each language row unlocks separately). Null on failure.
  static Future<int?> translatedRowId(int tourId, String lang) async {
    try {
      final result = await TranslationService.translateTour(tourId: tourId, languages: [lang]);
      if (result['status'] != 'completed') return null;
      final id = _extractTranslatedIds(result)?[lang];
      if (id is int) return id;
      if (id is num) return id.toInt();
      return int.tryParse('$id');
    } catch (e) {
      await DebugLogHelper.addDebugLog('TRANSLATE: translatedRowId($tourId, $lang) failed: $e');
      return null;
    }
  }

  /// Handles both response shapes from the translation service.
  /// Returns null for languages with status='failed' or id=null.
  static Map<String, dynamic>? _extractTranslatedIds(Map<String, dynamic> result) {
    if (result.containsKey('translated_tour_ids')) {
      return result['translated_tour_ids'] as Map<String, dynamic>?;
    }
    final translations = result['translations'] as Map<String, dynamic>?;
    if (translations == null) return null;
    return translations.map((lang, val) {
      // Detect failed translations: {id: null, status: "failed"}
      if (val is Map && (val['status'] == 'failed' || val['id'] == null)) {
        return MapEntry(lang, null);
      }
      final id = val is Map ? val['id'] : val;
      return MapEntry(lang, id);
    });
  }

  /// Saves a translated tour ZIP to the local filesystem and SharedPreferences.
  static Future<void> _saveTranslatedTour(dynamic tourId, List<int> zipBytes, String appDirPath, SharedPreferences prefs, String parentEditTourId, String lang,
      {dynamic version, dynamic updatedAt, Map<String, dynamic>? sourceItem, int? parentServerTourId}) async {
    final archive = ZipDecoder().decodeBytes(zipBytes);
    String tourName = 'Translated Tour $tourId';
    // Try to extract tour name from ZIP manifest
    for (final file in archive) {
      if (file.name.endsWith('manifest.json') || file.name.endsWith('tour.json')) {
        try {
          final data = json.decode(utf8.decode(file.content as List<int>));
          tourName = data['tour_name'] ?? data['name'] ?? tourName;
          break;
        } catch (_) {}
      }
    }
    final safeName = tourName.replaceAll(RegExp(r'[^\w]'), '_').replaceAll(RegExp(r'_+'), '_').toLowerCase();
    final dirName = '${safeName}_${lang}_$tourId';
    final tourDir = Directory('$appDirPath/tours/$dirName');
    await tourDir.create(recursive: true);
    for (final file in archive) {
      if (!file.isFile) continue;
      final outFile = File('${tourDir.path}/${file.name}');
      await outFile.parent.create(recursive: true);
      await outFile.writeAsBytes(file.content as List<int>);
    }
    // Q5 fix: reuse already-decoded archive instead of decoding zipBytes a second time
    final actualStops = _countStopsFromArchive(archive);
    final savedTours = prefs.getStringList('saved_tours') ?? [];
    final tourData = {
      'title': tourName,
      'path': tourDir.path,
      'created': DateTime.now().toIso8601String(),
      'stops': actualStops.toString(),
      'original_request': tourName,
      'tour_id': tourId.toString(),
      'editable': false,
      'is_translation': true,
      'parent_tour_id': parentEditTourId.isEmpty ? null : parentEditTourId,
      // [LOCAL-716B] The TARGET language of this translation (e.g. 'ru'). Until
      // now the language lived only in the directory name, so "View" after a
      // "tour + translation" download could not tell which saved entry was the
      // language just downloaded. Stamping it here lets the View planner open
      // the exact language copy the user asked for (D358 field-test fix).
      'language': lang,
      // [LOCAL-716B / D358] The ORIGINAL (parent) tour's SERVER id. The snackbar
      // offers the original server id (e.g. 117); this translation's own
      // `tour_id`/`server_tour_id` are its OWN translated id (e.g. 437), and
      // `parent_tour_id` is the non-numeric EDIT id (often null when the resolve
      // endpoint is unavailable). Without this link the View matcher could not
      // tie the Russian copy to the offered 117 — exactly the Pixel-4 miss.
      if (parentServerTourId != null) 'parent_server_tour_id': parentServerTourId.toString(),
    };
    // [LOCAL-666] Persist the source version + updated date so the My Tours list can
    // label this translation (v{n} · updated {Mon D}) exactly like the English tour.
    // Additive: omitted entirely when the server sent none (an older map-delivery).
    if (version != null) tourData['version'] = version;
    if (updatedAt != null) tourData['updated_at'] = updatedAt;

    // [LOCAL-677B / D653] Every language copy carries the PRICE (a translation
    // inherits its source's price), but unlocks SEPARATELY. Stamp the price
    // snapshot onto THIS translation's local record keyed by the translation's
    // OWN server id, so the player gates it independently of the English copy:
    //   * server_tour_id = this translation's own id (its unlock is its own).
    //   * is_paid/price_tier/price_label = inherited from the source payload.
    //   * unlocked = false for a paid translation (needs its own purchase);
    //     true for a free tour. A later purchase of THIS language writes
    //     unlocked:true on this record only.
    //   * original_language = the source tour's original language (for the header).
    if (sourceItem != null) {
      final bool isPaid = sourceItem['is_paid'] == true;
      tourData['server_tour_id'] = tourId.toString();
      tourData['is_paid'] = isPaid;
      final rawTier = sourceItem['price_tier'];
      if (rawTier is int) {
        tourData['price_tier'] = rawTier;
      } else if (rawTier is num) {
        tourData['price_tier'] = rawTier.toInt();
      } else if (rawTier is String) {
        tourData['price_tier'] = int.tryParse(rawTier);
      }
      final rawLabel = sourceItem['price_label'];
      tourData['price_label'] =
          (rawLabel is String && rawLabel.trim().isNotEmpty) ? rawLabel.trim() : 'Free';
      tourData['unlocked'] = !isPaid; // paid translation starts locked (own unlock)
      final rawLang = sourceItem['original_language'];
      if (rawLang is String && rawLang.trim().isNotEmpty) {
        tourData['original_language'] = rawLang.trim();
      }
    }

    savedTours.add(json.encode(tourData));
    await SavedToursStore.save(prefs, savedTours);
  }

  /// Count stops from an already-decoded archive by checking tour.json or counting MP3s.
  static int _countStopsFromArchive(Archive archive) {
    try {
      for (final file in archive) {
        if (file.name == 'tour.json' && file.isFile) {
          final jsonContent = String.fromCharCodes(file.content as List<int>);
          final tourData = json.decode(jsonContent);
          if (tourData['stops'] != null && tourData['stops'] is List) {
            return (tourData['stops'] as List).length;
          }
        }
      }
      int count = 0;
      for (final file in archive) {
        if (file.name.endsWith('.mp3') && file.isFile) count++;
      }
      return count > 0 ? count : 1;
    } catch (_) {
      return 1;
    }
  }
}
