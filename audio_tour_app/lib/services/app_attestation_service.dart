import 'dart:convert';
import 'dart:io' show Platform;
import 'package:crypto/crypto.dart';
import '../screens/debug_log_viewer_screen.dart';

/// Platform attestation service.
/// Android: Play Integrity API token.
/// iOS: App Attest assertion via MethodChannel.
/// Returns null if attestation is unavailable (dev/emulator/unsupported).
class AppAttestationService {
  /// Returns a platform-appropriate attestation token tied to [requestBody].
  /// Nonce = SHA-256 of the request body, preventing replay attacks.
  /// Never throws — logs failures and returns null so the request can proceed.
  static Future<String?> getToken(Map<String, dynamic> requestBody) async {
    try {
      final nonce = _generateNonce(requestBody);
      if (Platform.isAndroid) {
        return await _getPlayIntegrityToken(nonce);
      } else if (Platform.isIOS) {
        return await _getAppAttestToken(nonce);
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('ATTEST: Failed to get token: $e');
    }
    return null;
  }

  /// SHA-256 of the JSON-encoded request body, used as nonce.
  static String _generateNonce(Map<String, dynamic> requestBody) {
    final bodyString = jsonEncode(requestBody);
    final bytes = utf8.encode(bodyString);
    return sha256.convert(bytes).toString();
  }

  /// Android: Play Integrity API token.
  /// Phase 3 implementation — currently returns null (stub).
  static Future<String?> _getPlayIntegrityToken(String nonce) async {
    // TODO: Phase 3 — integrate play_integrity plugin
    // 1. Call IntegrityManager.requestIntegrityToken(nonce: nonce, cloudProjectNumber: PROJECT_NUMBER)
    // 2. Return the token string
    await DebugLogHelper.addDebugLog('ATTEST: Play Integrity not yet implemented (Phase 3)');
    return null;
  }

  /// iOS: App Attest assertion via MethodChannel.
  /// Phase 4 implementation — currently returns null (stub).
  /// iOS-AQ will implement the native Swift side (AppAttestHandler.swift).
  /// MethodChannel contract:
  ///   Channel: 'com.audioura.app/attestation'
  ///   Method: 'getAssertion'
  ///   Args: {'nonce': String}
  ///   Returns: String (base64-encoded assertion) or null
  static Future<String?> _getAppAttestToken(String nonce) async {
    // TODO: Phase 4 — MethodChannel to native DCAppAttestService
    // final channel = MethodChannel('com.audioura.app/attestation');
    // final result = await channel.invokeMethod<String>('getAssertion', {'nonce': nonce});
    // return result;
    await DebugLogHelper.addDebugLog('ATTEST: App Attest not yet implemented (Phase 4)');
    return null;
  }
}
