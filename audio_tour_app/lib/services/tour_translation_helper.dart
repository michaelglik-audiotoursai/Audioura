import 'dart:convert';
import 'dart:io';
import 'package:archive/archive.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config/endpoints.dart';
import '../screens/debug_log_viewer_screen.dart';
import 'translation_service.dart';

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

  /// Translates a tour and downloads each translated version as a new entry.
  /// Returns a list of language codes that failed.
  /// The English tour must already be saved before calling this.
  static Future<List<String>> downloadTranslatedVersions({
    required int tourId,
    required List<String> languages,
    required String parentEditTourId,
  }) async {
    final failures = <String>[];
    final nonEnglish = languages.where((l) => l != 'en').toList();
    if (nonEnglish.isEmpty) return failures;

    try {
      await DebugLogHelper.addDebugLog('TRANSLATE: Requesting translation for tourId=$tourId languages: ${nonEnglish.join(", ")}');
      final result = await TranslationService.translateTour(tourId: tourId, languages: nonEnglish);

      if (result['status'] == 'completed') {
        final translatedIds = _extractTranslatedIds(result);
        if (translatedIds != null) {
          for (final lang in nonEnglish) {
            final translatedId = translatedIds[lang];
            if (translatedId == null) {
              failures.add(lang);
              await DebugLogHelper.addDebugLog('TRANSLATE: Translation failed for $lang (id=null or status=failed)');
              continue;
            }
            try {
              final translatedUri = await Endpoints.url(Service.mapDelivery, '/download-tour/$translatedId');
              final translatedResponse = await http.get(translatedUri, headers: await Endpoints.apiHeaders(Service.mapDelivery)).timeout(const Duration(seconds: 120));
              if (translatedResponse.statusCode == 200) {
                final prefs = await SharedPreferences.getInstance();
                final appDir = await getApplicationDocumentsDirectory();
                await _saveTranslatedTour(translatedId, translatedResponse.bodyBytes, appDir.path, prefs, parentEditTourId, lang);
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
  static Future<void> _saveTranslatedTour(dynamic tourId, List<int> zipBytes, String appDirPath, SharedPreferences prefs, String parentEditTourId, String lang) async {
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
    };
    savedTours.add(json.encode(tourData));
    await prefs.setStringList('saved_tours', savedTours);
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
