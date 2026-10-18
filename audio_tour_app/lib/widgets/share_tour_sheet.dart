import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../services/tour_share_service.dart';
import '../utils/share_code.dart';

/// [LOCAL-579] One entry point both My Tours and the tour player call to share a
/// tour. Shows a brief progress dialog while POST /tour/share runs, then either
/// a result sheet (the 8-char code, Copy, Share…) or a plain error SnackBar.
///
/// [audioTourId] is the tour's numeric id; [tourName] is its RAW title.
///
/// [LOCAL-710 / D672] The shared message is now shaped by [ShareTourDetails]:
/// a short title, the stop count + first stop, a short link, and a kind-specific
/// opening (free / paid / community). The caller passes what it already holds:
///   * [tourPath]       — the downloaded tour's folder, so we can read the first
///                        stop's name + address from audio_1.txt (omitted when
///                        unknown → the stops line degrades, never prints null);
///   * [stopCount]      — the tour's stop count, when the screen knows it;
///   * [isPaid]/[price] — for the paid opening + the "The tour price is $X." line;
///   * [communityName]  — present → a community opening + the download line.
///   * [shortTitle]      — [LOCAL-711 / D673] the server short_title, used for
///                        the email title + subject when non-empty (else the
///                        app's own shortTourTitle of the raw name).
/// Never throws — the service maps every failure to a message.
Future<void> shareTour(
  BuildContext context, {
  required dynamic audioTourId,
  required String tourName,
  String? tourPath,
  int? stopCount,
  bool isPaid = false,
  String? price,
  String? communityName,
  String? shortTitle,
}) async {
  // Brief, non-dismissible progress while the (idempotent) request runs.
  showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => const AlertDialog(
      content: Row(
        children: [
          CircularProgressIndicator(),
          SizedBox(width: 20),
          Expanded(child: Text('Creating share code…')),
        ],
      ),
    ),
  );

  final result = await TourShareService.share(audioTourId);

  // Gather the first stop's name + location from the downloaded tour, if we
  // have its path. Done before touching context again; never throws.
  final firstStop = await _readFirstStop(tourPath);

  if (!context.mounted) return;
  Navigator.of(context).pop(); // dismiss progress

  if (!result.ok) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(result.errorMessage ?? 'Sharing failed.'),
        backgroundColor: Colors.red,
      ),
    );
    return;
  }

  final details = buildShareTourDetails(
    rawTourName: tourName,
    code: result.code!,
    isPaid: isPaid,
    price: price,
    communityName: communityName,
    stopCount: stopCount ?? firstStop.stopCount,
    firstStopName: firstStop.name,
    firstStopLocation: firstStop.location,
    serverShortTitle: shortTitle,
  );

  await _showShareResultSheet(context, details: details);
}

/// [LOCAL-710 / D672] Assemble the [ShareTourDetails] from the raw facts a
/// sharing screen holds. Pure apart from its inputs — the city and tour type are
/// derived from the raw name / first-stop location, the short title from the raw
/// name. Kept here (not in share_code.dart) so share_code.dart stays free of
/// policy about which field wins; exposed for the sample-generating test.
ShareTourDetails buildShareTourDetails({
  required String rawTourName,
  required String code,
  bool isPaid = false,
  String? price,
  String? communityName,
  int? stopCount,
  String? firstStopName,
  String? firstStopLocation,
  String? serverShortTitle,
}) {
  final hasCommunity = (communityName ?? '').trim().isNotEmpty;
  final kind = hasCommunity
      ? ShareTourKind.community
      : (isPaid ? ShareTourKind.paid : ShareTourKind.free);
  // [LOCAL-711 / D673] Prefer the SERVER short_title when present; otherwise
  // fall back to the app's own shortTourTitle() of the raw name. A blank/space
  // server value counts as absent.
  final serverShort = (serverShortTitle ?? '').trim();
  final title =
      serverShort.isNotEmpty ? serverShort : shortTourTitle(rawTourName);
  return ShareTourDetails(
    title: title,
    code: code,
    kind: kind,
    price: isPaid ? price : null,
    communityName: hasCommunity ? communityName : null,
    stopCount: stopCount,
    firstStopName: firstStopName,
    firstStopLocation: firstStopLocation,
    city: cityFromLocation(firstStopLocation, rawTourName),
    tourType: tourTypeFromName(rawTourName),
  );
}

/// The first stop read off a downloaded tour's files: its display name (first
/// line of audio_1.txt) and its location (the `Address:` line), plus the number
/// of audio_N.txt files present (a stop-count fallback). All null/0 when the
/// path is unknown or unreadable — the message then omits the degraded parts.
class _FirstStop {
  final String? name;
  final String? location;
  final int? stopCount;
  const _FirstStop({this.name, this.location, this.stopCount});
}

Future<_FirstStop> _readFirstStop(String? tourPath) async {
  if (tourPath == null || tourPath.trim().isEmpty) return const _FirstStop();
  try {
    // Count audio_N.txt files for a stop-count fallback.
    int count = 0;
    while (await File('$tourPath/audio_${count + 1}.txt').exists()) {
      count++;
    }
    final first = File('$tourPath/audio_1.txt');
    if (!await first.exists()) {
      return _FirstStop(stopCount: count > 0 ? count : null);
    }
    final content = await first.readAsString();
    final lines = content.split('\n');
    final name = lines.isNotEmpty ? lines.first.trim() : '';
    final addrMatch = RegExp(r'Address:\s*(.+)').firstMatch(content);
    final address = addrMatch?.group(1)?.trim() ?? '';
    return _FirstStop(
      name: name.isEmpty ? null : name,
      location: address.isEmpty ? null : address,
      stopCount: count > 0 ? count : null,
    );
  } catch (_) {
    return const _FirstStop();
  }
}

/// The result sheet: a large, selectable code plus Copy and Share… actions.
Future<void> _showShareResultSheet(
  BuildContext context, {
  required ShareTourDetails details,
}) {
  final message = buildShareMessage(details);
  final subject = buildShareSubject(details);
  final code = details.code;
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    builder: (sheetContext) {
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Share this tour',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                'Anyone with this code can find "${details.title}" from the '
                'Home page Search.',
                style: const TextStyle(fontSize: 13, color: Colors.black54),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              // Large, selectable code.
              Container(
                padding: const EdgeInsets.symmetric(vertical: 16),
                decoration: BoxDecoration(
                  color: const Color(0xFFF2F4F6),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: SelectableText(
                  code,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 34,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 4,
                    fontFamily: 'monospace',
                    color: Color(0xFF2c3e50),
                  ),
                ),
              ),
              const SizedBox(height: 20),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      icon: const Icon(Icons.copy),
                      label: const Text('Copy code'),
                      onPressed: () async {
                        await Clipboard.setData(ClipboardData(text: code));
                        if (!sheetContext.mounted) return;
                        ScaffoldMessenger.of(sheetContext).showSnackBar(
                          const SnackBar(
                            content: Text('Code copied'),
                            duration: Duration(seconds: 2),
                          ),
                        );
                      },
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton.icon(
                      icon: const Icon(Icons.ios_share),
                      label: const Text('Share…'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF3498db),
                        foregroundColor: Colors.white,
                      ),
                      onPressed: () async {
                        // On iPad the share sheet needs an anchor rectangle.
                        final box =
                            sheetContext.findRenderObject() as RenderBox?;
                        final origin = box != null
                            ? box.localToGlobal(Offset.zero) & box.size
                            : null;
                        await Share.share(
                          message,
                          subject: subject,
                          sharePositionOrigin: origin,
                        );
                      },
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    },
  );
}
