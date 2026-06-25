import 'dart:io' show Platform;
import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../screens/debug_log_viewer_screen.dart';

/// Central error handler — translates HTTP status codes into user-friendly messages
/// and offers optional "Report this problem" via prefilled mailto.
class ErrorHandlerService {
  /// Returns a user-friendly message for the given HTTP status code.
  /// NEVER shows raw status codes to users.
  static String friendlyMessage(int statusCode, {String? serverMessage}) {
    switch (statusCode) {
      case 401:
        return 'Audioura couldn\'t connect securely. Please make sure you have the latest version of the app, then try again.';
      case 402:
        return serverMessage ?? 'This content requires a subscription.';
      case 403:
        return 'Access denied. Please update the app or contact support.';
      case 404:
        return 'The requested content was not found. It may have been removed.';
      case 429:
        return 'Daily limit reached. Please try again tomorrow.';
      case 500:
      case 502:
      case 503:
        return 'Our servers are temporarily unavailable. Please try again in a few minutes.';
      default:
        if (statusCode >= 500) {
          return 'Server error. Please try again later.';
        }
        return 'Something went wrong. Please try again.';
    }
  }

  /// Shows an error snackbar with a friendly message and optional "Report" action.
  static void showError(BuildContext context, {
    required int statusCode,
    String? endpoint,
    String? serverMessage,
  }) {
    final message = friendlyMessage(statusCode, serverMessage: serverMessage);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: statusCode == 402 ? Colors.orange : Colors.red,
        duration: const Duration(seconds: 8),
        action: SnackBarAction(
          label: 'Report',
          textColor: Colors.white,
          onPressed: () => _reportProblem(context, statusCode: statusCode, endpoint: endpoint),
        ),
      ),
    );
  }

  /// Shows a "Couldn't connect — tap to retry" widget instead of false "no content" state.
  static Widget connectionErrorWidget({required VoidCallback onRetry}) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
          const SizedBox(height: 16),
          const Text(
            'Couldn\'t connect to Audioura',
            style: TextStyle(fontSize: 16, color: Colors.grey),
          ),
          const SizedBox(height: 8),
          ElevatedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Tap to retry'),
          ),
        ],
      ),
    );
  }

  /// Opens a prefilled mailto with diagnostic info. User reviews before sending.
  static Future<void> _reportProblem(BuildContext context, {
    int? statusCode,
    String? endpoint,
  }) async {
    try {
      final packageInfo = await PackageInfo.fromPlatform();
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id') ?? 'unknown';
      final serverMode = prefs.getString('server_mode') ?? 'cloud';
      final now = DateTime.now();

      // Get last 20 debug log lines
      final logs = prefs.getStringList('debug_logs') ?? [];
      final recentLogs = logs.length > 20 ? logs.sublist(logs.length - 20) : logs;

      final subject = Uri.encodeComponent('Audioura Problem Report — ${statusCode ?? "Error"}');
      final body = Uri.encodeComponent(
        'Problem Report (you can review before sending)\n'
        '─────────────────────────────\n'
        'Timestamp: ${now.toIso8601String()} (UTC: ${now.toUtc().toIso8601String()})\n'
        'Endpoint: ${endpoint ?? "unknown"}\n'
        'HTTP Status: ${statusCode ?? "N/A"}\n'
        'App Version: ${packageInfo.version}+${packageInfo.buildNumber}\n'
        'Platform: ${Platform.operatingSystem} ${Platform.operatingSystemVersion}\n'
        'Server Mode: $serverMode\n'
        'Device ID: $userId\n'
        '─────────────────────────────\n'
        'Recent log:\n${recentLogs.join("\n")}\n'
        '─────────────────────────────\n'
        'Description of what happened:\n[Please describe what you were doing]\n',
      );

      final mailtoUri = Uri.parse('mailto:info@audioura.com?subject=$subject&body=$body');

      if (await canLaunchUrl(mailtoUri)) {
        await launchUrl(mailtoUri);
      } else {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Could not open email. Please contact info@audioura.com directly.'),
              backgroundColor: Colors.orange,
            ),
          );
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('ERROR_HANDLER: Failed to open report email: $e');
    }
  }
}
