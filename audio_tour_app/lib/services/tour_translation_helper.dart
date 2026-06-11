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
              await DebugLogHelper.addDebugLog('TRANSLATE: No ID returned for $lang');
              continue;
            }
            try {
              final translatedUri = await Endpoints.url(Service.mapDelivery, '/download-tour/$translatedId');
              final translatedResponse = await http.get(translatedUri).timeout(const Duration(seconds: 120));
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
  static Map<String, dynamic>? _extractTranslatedIds(Map<String, dynamic> result) {
    if (result.containsKey('translated_tour_ids')) {
      return result['translated_tour_ids'] as Map<String, dynamic>?;
    }
    final translations = result['translations'] as Map<String, dynamic>?;
    if (translations == null) return null;
    return translations.map((lang, val) {
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
    final actualStops = _countStopsFromZip(zipBytes);
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

  /// Count stops from ZIP content by checking tour.json or counting MP3s.
  static int _countStopsFromZip(List<int> zipBytes) {
    try {
      final archive = ZipDecoder().decodeBytes(zipBytes);
      for (final file in archive) {
        if (file.name == 'tour.json' && file.isFile) {
          final jsonContent = String.fromCharCodes(file.content as List<int>);
          final tourData = json.decode(jsonContent);
          if (tourData['stops'] != null && tourData['stops'] is List) {
            return (tourData['stops'] as List).length;
          }
        }
      }
      // Fallback: count MP3 files
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
