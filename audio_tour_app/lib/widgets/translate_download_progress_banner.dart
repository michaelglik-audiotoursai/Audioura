// [LOCAL-794] The app-wide progress row for a background translate-download.
//
// Hosted by MainScreen OUTSIDE the tab IndexedStack (like the bottom bar), so
// it stays visible while the user switches tabs and keeps using the app — the
// replacement for the old app-blocking modal spinner. It shows the current
// phase label (from [TranslateDownloadJob.label]), an indeterminate progress
// bar, and a Cancel that asks the running job to stop at its next checkpoint.
//
// Renders nothing when no job is active (`controller.active.value == null`), so
// the host can place it unconditionally.

import 'package:flutter/material.dart';

import '../services/translate_download_manager.dart';

/// Key on the row so widget tests can find it while a job runs.
const Key kTranslateDownloadRowKey = Key('translate_download_progress_row');

/// Key on the Cancel button.
const Key kTranslateDownloadCancelKey = Key('translate_download_cancel');

class TranslateDownloadProgressBanner extends StatelessWidget {
  final TranslateDownloadController controller;

  const TranslateDownloadProgressBanner({super.key, required this.controller});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<TranslateDownloadJob?>(
      valueListenable: controller.active,
      builder: (context, job, _) {
        if (job == null) return const SizedBox.shrink();
        return Material(
          color: const Color(0xFFEFF4FF),
          child: SafeArea(
            top: false,
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                key: kTranslateDownloadRowKey,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          job.label,
                          key: const Key('translate_download_label'),
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            color: Color(0xFF1B3A7A),
                          ),
                        ),
                      ),
                      TextButton(
                        key: kTranslateDownloadCancelKey,
                        onPressed: controller.cancel,
                        child: const Text('Cancel'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  const LinearProgressIndicator(
                    key: Key('translate_download_bar'),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
