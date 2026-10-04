import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../services/tour_share_service.dart';
import '../utils/share_code.dart';

/// [LOCAL-579] One entry point both My Tours and the tour player call to share a
/// tour. Shows a brief progress dialog while POST /tour/share runs, then either
/// a result sheet (the 8-char code, Copy, Share…) or a plain error SnackBar.
///
/// [audioTourId] is the tour's numeric id; [tourName] is its title (used in the
/// shared message). Never throws — the service maps every failure to a message.
Future<void> shareTour(
  BuildContext context, {
  required dynamic audioTourId,
  required String tourName,
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

  await _showShareResultSheet(context, code: result.code!, tourName: tourName);
}

/// The result sheet: a large, selectable code plus Copy and Share… actions.
Future<void> _showShareResultSheet(
  BuildContext context, {
  required String code,
  required String tourName,
}) {
  final message = buildShareMessage(tourName, code);
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
                'Anyone with this code can find "$tourName" from the Home page '
                'Search.',
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
                          subject: 'An Audioura tour for you',
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
